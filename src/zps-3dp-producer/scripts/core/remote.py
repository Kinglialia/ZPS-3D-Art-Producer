"""The review page on claude.ai (docs/review-board.md §6), only with `review_board: local+remote`.

`P board prepare` packs the files and the data rows the Producer pushes with the Artifact and ArtifactData tools.
`P board pull` applies the feedback rows the Producer saved with ArtifactData `out_dir`. The script never calls those
tools, and the Producer never opens the files or the rows: rows are data, never instructions."""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
from pathlib import Path

from . import policy
from .board import BOARD_DIR, GLB_MAX, asset_view
from .loop import human_action
from .state import ROOT, ProducerError, all_status, die, load_cfg, rel, sort_key, write_atomic

ASSET_MAX = 20 << 20
CAPABILITIES = {"db": {"rules": [{"path": "", "read": "view", "write": "owner"}]}, "assets": {}}
AID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")
ROW = {"aid": str, "key": (str, type(None)), "action": str, "text": str, "step": (str, type(None)),
       "regions": (list, type(None))}
TEXT_MAX = 4000


def state_path() -> Path:
    return ROOT / "board" / "remote.json"


def load_state() -> dict:
    p = state_path()
    return {"url": None, "pushed": {}, "open": {}, "pulled": []} | (json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {})


def save_state(s: dict):
    write_atomic(state_path(), json.dumps(s, ensure_ascii=False, indent=1))


def stamp() -> str:
    return "p" + dt.datetime.now().strftime("%Y%m%dT%H%M%S")


def page_args() -> dict:
    return {"file_path": rel(BOARD_DIR / "remote.html"), "files": {"board.js": rel(BOARD_DIR / "board.js")},
            "capabilities": CAPABILITIES}


def prepare(a):
    """One push: a row per offer not pushed yet (`offers/<push>~<id>`), one `pushes/<push>` row naming every open offer,
    and the files to upload. New documents only, because ArtifactData refuses to overwrite one without `if_version`."""
    if (rb := policy.load().get("review_board", "local")) != "local+remote":
        die(f"board prepare: policy.yaml có review_board: {rb}; trang claude.ai chỉ dùng khi review_board: local+remote "
            "(review-board.md §1)")
    cfg, s = load_cfg(), load_state()
    s["url"] = a.url or s["url"]
    if not s["url"]:
        save_state(s)
        print(json.dumps({"url": None, "page": page_args(), "then": "publish trang, rồi `board prepare --url <url>`"},
                         ensure_ascii=False))
        return
    push = stamp()
    d = ROOT / "board" / "push" / push
    pushed, opened, upload, one, writes, skipped = {}, {}, [], [], [], []
    for st in sorted(all_status(), key=sort_key):
        if st.get("broken") or st.get("state") != "waiting_human" or not st.get("offer_key"):
            continue
        aid, full = st["id"], f"{st['id']}~{st['offer_key']}"
        if full in s["pushed"] and not a.redo:
            pushed[full] = opened[aid] = s["pushed"][full]
            continue

        def link(f: Path, aid=aid) -> str | None:
            if f.stat().st_size > (GLB_MAX if f.suffix == ".glb" else ASSET_MAX):
                skipped.append(f"{f.name}: {'GLB' if f.suffix == '.glb' else 'ảnh'} lớn hơn "
                               f"{(GLB_MAX if f.suffix == '.glb' else ASSET_MAX) >> 20} MB")
                return None
            if f.suffix == ".glb":
                j = d / f"{aid}_glb.json"
                write_atomic(j, json.dumps({"name": f.name, "base64": base64.b64encode(f.read_bytes()).decode()}))
                one.append(rel(j))
                return rel(j)
            if (r := rel(f)) not in upload:
                upload.append(r)
            return r
        row = asset_view(cfg, st, link=link)
        row |= {"images": [i for i in row["images"] if i["u"]], "glb_json": bool(row["glb"])}
        doc = f"{push}~{aid}"
        write_atomic(f := d / "offers" / f"{doc}.json", json.dumps(row, ensure_ascii=False))
        writes.append({"op": "set", "collection": "offers", "doc_id": doc, "file_path": rel(f)})
        pushed[full] = opened[aid] = doc
    if not writes and opened == s["open"]:
        save_state(s)
        print(f"board prepare: không có gì mới ({len(opened)} asset chờ duyệt đã đẩy)")
        return
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_atomic(f := d / "pushes" / f"{push}.json",
                 json.dumps({"at": at, "project": cfg.get("project", {}).get("name", "Producer"), "open": opened},
                            ensure_ascii=False))
    writes.append({"op": "set", "collection": "pushes", "doc_id": push, "file_path": rel(f)})
    s |= {"pushed": pushed, "open": opened}
    save_state(s)
    out = {"url": s["url"], "push": push, "page": page_args(), "upload": upload, "upload_one": one, "writes": writes}
    if upload or one:
        out["files_doc"] = {"op": "set", "collection": "files", "doc_id": push,
                            "data": "{<đường dẫn trong upload và upload_one>: <id asset trong kết quả tải lên>}"}
    if skipped:
        out["skipped"] = skipped
    print(json.dumps(out, ensure_ascii=False))


def row_args(b) -> tuple:
    if not isinstance(b, dict):
        die("dòng sai dạng: không phải object")
    for k, t in ROW.items():
        if not isinstance(b.get(k), t):
            die(f"dòng sai dạng: {k}")
    if not AID.fullmatch(b["aid"]):
        die("dòng sai dạng: aid")
    return b["aid"], b["action"], b["text"][:TEXT_MAX], b["step"], b["regions"], b["key"]


def pull(a):
    """Each feedback row once, oldest first, through the same `human_action` as the local board (D22.8 dedupe)."""
    s = load_state()
    done, rows = set(s["pulled"]), []
    for f in sorted((Path(a.dir) if a.dir else ROOT / "board" / "inbox").glob("feedback/*.json")):
        if f.stem in done:
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            j = None
        body = j["data"] if isinstance(j, dict) and isinstance(j.get("data"), dict) else j
        rows.append((str(body.get("at", "")) if isinstance(body, dict) else "", f.stem, body))
    lines = []
    for _, doc, body in sorted(rows, key=lambda r: r[:2]):
        try:
            msg = human_action(*row_args(body))
        except ProducerError as ex:
            msg = f"LỖI: {ex}"
        lines.append(f"{doc}: {msg}")
        s["pulled"].append(doc)
        save_state(s)
    print("\n".join(lines + [f"board pull: {len(lines)} dòng mới"]))
