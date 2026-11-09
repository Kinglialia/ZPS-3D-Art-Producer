"""Dashboard, the local review board and `P show`: one JSON payload, one JS renderer (docs/review-board.md §2, §3, §7)."""
from __future__ import annotations

import base64
import html
import io
import json
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from . import findings
from .contract import FIELDS
from .loop import next_action, shown
from .state import (FINISHED, IMAGE_EXT, ROOT, SKILL_DIR, all_status, die, load_cfg, load_st, locked, now, outputs_of, rel,
                    sort_key, step_of, vdir, write_atomic)

BOARD_DIR = SKILL_DIR / "scripts" / "board"
SUMMARY_FILE = {"blockout": "blockout.md", "views_front": "report/VIEWS.md", "views_rest": "report/VIEWS.md",
                "model": "model.md", "texture": "notes.md", "assemble": "README.md"}
HERO = {"blockout": "game_cam.png", "views_front": "front.png", "views_rest": "VIEWS_sheet.png", "model": "model_sheet.png",
        "texture": "final_lit_vs_concept.png", "assemble": "final_lit_vs_concept.png"}
SUMMARY_LINES = 3
CONCEPT_IMAGES = ("concept_albedo.png", "concept_shadow.png")
LINE_FIELDS = ("region", "evidence", "repair")
HOSTS = ("127.0.0.1", "localhost")
MAX_BODY = 1 << 20
GLB_MAX = 15 << 20
BUNDLE_PX = 1024
CROP = re.compile(r"(^|[_-])(crop|foot)([_-]|$)", re.I)


def build_outputs(_cfg: dict):
    sts = sorted(all_status(), key=sort_key)
    write_atomic(ROOT / "dashboard.md", render_dashboard(sts))


def render_dashboard(sts: list[dict]) -> str:
    active = [s for s in sts if s.get("state") not in FINISHED]
    out = [f"# Dashboard — tự sinh {now()}, đừng sửa tay", "",
           "| Asset | Bước | State | Phiên bản | Rubric gần nhất | Deadline | Việc tiếp |",
           "|---|---|---|---|---|---|---|"]
    for s in active:
        vers = " ".join(f"{k}:v{v}" for k, v in s.get("versions", {}).items()) or "-"
        out.append(f"| {s['id']} | {s.get('stage')} | {s.get('state')} | {vers} | {s.get('last_rubric') or '-'} "
                   f"| {s.get('deadline') or '-'} | {next_action(s)} |")
    done = [s["id"] for s in sts if s.get("state") in FINISHED]
    if done:
        out += ["", f"Done ({len(done)}): " + ", ".join(done)]
    return "\n".join(out) + "\n"


def live_link(cfg: dict):
    """`P serve` URLs: `/p/<path under the production root>`, `/a/<path under _approved/>` (safe_file reads them back)."""
    bases = [("p", ROOT.resolve())] + ([("a", cfg["paths"]["approved"].resolve())] if cfg["paths"]["approved"] else [])

    def link(f: Path) -> str:
        rf = f.resolve()
        return next(f"/{k}/" + quote(rf.relative_to(b).as_posix()) for k, b in bases if rf.is_relative_to(b))
    return link


def finding_view(fid: str, f: dict) -> dict:
    head = " — ".join(f[k] for k in LINE_FIELDS if f.get(k))
    acc = f" — acceptance: {f['acceptance']}" if f.get("acceptance") else ""
    return {"line": f"{fid} [{f['priority']}] {head}{acc}",
            "fields": {k: f[k] for k in FIELDS if k not in (*LINE_FIELDS, "acceptance") and f.get(k)}}


def summary_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [l.strip().lstrip("#").strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip().lstrip("#").strip()]


def images_of(d: Path | None) -> list[Path]:
    return sorted(p for p in d.rglob("*") if p.suffix.lower() in IMAGE_EXT) if d and d.is_dir() else []


def latest_evidence(v: Path) -> Path | None:
    ks = [p for p in (v / "review").glob("evidence-*") if p.is_dir() and p.name.split("-")[-1].isdigit()]
    return max(ks, key=lambda p: int(p.name.split("-")[-1]), default=None)


def main_glb(final: Path, outputs: list[str]) -> Path | None:
    """The GLB the step declares as output (model: the untextured mesh, not the blockout union beside it)."""
    want = [final / o.removeprefix("final/") for o in outputs if o.endswith(".glb")]
    return next((p for p in want if p.is_file()), None) or next(iter(sorted(final.glob("*.glb"))), None)


def view_images(cfg: dict, st: dict, step: str, n: int | None) -> list[tuple[Path, str]]:
    """(file, name) of every image on the card: the hero first, the concept beside it, the newest evidence over the
    render of the same name. The name is the only handle a page sends back (annotation)."""
    hero = HERO.get(step)
    final = vdir(st["id"], step, n) / "final" if n else None
    pics = images_of(final)
    ev = latest_evidence(vdir(st["id"], step, n)) if n else None
    if ev:
        newer = {p.name for p in images_of(ev)}
        pics = [p for p in pics if p.name not in newer] + images_of(ev)
    pics.sort(key=lambda p: p.name != hero)
    out = [(p, (p.relative_to(final) if p.is_relative_to(final) else p.relative_to(ev.parent)).as_posix()) for p in pics]
    approved = cfg["paths"]["approved"]
    cd = Path(st["concept_dir"]) if st.get("concept_dir") else None
    if cd and approved and cd.resolve().is_relative_to(approved.resolve()):
        k = 1 if pics and pics[0].name == hero else 0
        out[k:k] = [((cd / x).resolve(), "concept/" + x) for x in CONCEPT_IMAGES if (cd / x).is_file()]
    return out


def asset_view(cfg: dict, st: dict, step: str | None = None, n: int | None = None, link=None) -> dict:
    """One card. Default: the current step and the version shown to the user, with `P serve` links."""
    aid, step = st["id"], step or st["stage"]
    n = n or shown(st, step)
    link = link or live_link(cfg)
    imgs = view_images(cfg, st, step, n)
    final = vdir(aid, step, n) / "final" if n else None
    sd = step_of(cfg, step)[1]
    glb = main_glb(final, outputs_of(sd, st)) if final and final.is_dir() else None
    lines = summary_lines(final / SUMMARY_FILE[step]) if final and step in SUMMARY_FILE else []
    op = findings.open_of(findings.load(aid, step, n))
    current = step == st["stage"]
    waiting = current and st["state"] == "waiting_human"
    state = st["state"] if current else "đã duyệt" if st["approved"].get(step) == n else "chưa duyệt"
    note = (st.get("note") or "").splitlines() if current else []
    ask = st.get("ask") if waiting else None
    return {
        "id": aid, "step": step, "version": n, "waiting": waiting,
        "header": f"{st.get('title', aid)} · {step}{f' v{n}' if n else ''} · {'chờ anh duyệt' if waiting else state}",
        "sheet": link(imgs[0][0]) if imgs and imgs[0][0].name == HERO.get(step) else None,
        "images": [{"u": link(p), "n": name} for p, name in imgs],
        "glb": link(glb) if glb else None,
        "summary": lines[:SUMMARY_LINES], "more": lines[SUMMARY_LINES:],
        "reason": note[0] if note else "",
        "label": (st.get("label") or "") if current else "",
        "stale": f"dựng từ {src} — cũ" if (src := (st.get("stale") or {}).get(f"{step} v{n}")) else None,
        "decided": (st.get("decisions") or {}).get(f"{step} v{n}", {}).get("at"),
        "open": [finding_view(i, f) for i, f in op.items() if f["priority"] != "preference"],
        "preference": [finding_view(i, f) for i, f in op.items() if f["priority"] == "preference"],
        "redo_steps": list(reversed(sd["inputs"])) if sd["script"] else [],
        "key": st.get("offer_key") if current and n == st.get("offer") else None,
        "ask": {"kind": ask["kind"], "price": st.get("meshy_price")} if ask else None,
    }


def board_payload(cfg: dict) -> dict:
    sts = sorted(all_status(), key=lambda s: (s.get("state") != "waiting_human", *sort_key(s)))
    return {"project": cfg.get("project", {}).get("name", "Producer"),
            "assets": [asset_view(cfg, s) for s in sts if not s.get("broken")]}


def safe_file(cfg: dict, url_path: str) -> Path | None:
    """`/p/<path under the production root>` or `/a/<path under _approved/>`; anything else is None."""
    key, _, rest = unquote(url_path).lstrip("/").partition("/")
    base = {"p": ROOT, "a": cfg["paths"]["approved"]}.get(key)
    if base is None or not rest or rest.startswith("/") or "\0" in rest or ".." in PurePosixPath(rest).parts:
        return None
    f = (base / rest).resolve()
    return f if f.is_file() and f.is_relative_to(base.resolve()) else None


def data_uri(f: Path, mime: str | None = None, raw: bytes | None = None) -> str:
    mime = mime or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes() if raw is None else raw).decode()


def is_crop(f: Path) -> bool:
    """A detail crop keeps its pixels in `--bundle`: evidence renders, and `crop*`, `foot_*` names."""
    return any(re.fullmatch(r"evidence-\d+", x) for x in f.parent.parts) or bool(CROP.search(f.stem))


def bundled(f: Path) -> str:
    """`--bundle` image: long side ≤ 1024 px (JPEG, or PNG with alpha); crops and small images keep their bytes."""
    from PIL import Image
    try:
        im = Image.open(f)
        if is_crop(f) or max(im.size) <= BUNDLE_PX:
            return data_uri(f)
        alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
        im = im.convert("RGBA" if alpha else "RGB")
        im.thumbnail((BUNDLE_PX, BUNDLE_PX), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True) if alpha else im.save(buf, "JPEG", quality=85)
        return data_uri(f, "image/png" if alpha else "image/jpeg", buf.getvalue())
    except OSError:
        return data_uri(f)


def page(payload: dict, mode: str) -> str:
    """A static page: the payload as data (every `<` escaped, so no text closes the script) and the renderer inline."""
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    js = (BOARD_DIR / "board.js").read_text(encoding="utf-8")
    return ('<!doctype html>\n<html lang="vi"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>Review · {html.escape(payload['project'])}</title></head>\n<body><div id=\"app\"></div>\n"
            f'<script id="board-data" type="application/json">{data}</script>\n'
            f'<script>window.BOARD = {{mode: "{mode}"}};</script>\n<script>{js}</script>\n</body></html>\n')


def show(a):
    """§5: `P show <id> [--step S [--version N]] [--bundle]` writes one static page of the asset's cards."""
    cfg, st = load_cfg(), load_st(a.id)
    if a.version and not a.step:
        die("--version cần --step")
    if a.step:
        step_of(cfg, a.step)
        n = a.version or shown(st, a.step)
        if not n or not vdir(a.id, a.step, n).is_dir():
            die(f"{a.id}: không có {a.step} v{n}")
        cards = [(a.step, n)]
    else:
        cards = [(s["id"], n) for s in reversed(cfg["steps"]) if (n := shown(st, s["id"]))]
    name = a.id + (f"-{a.step}-v{cards[0][1]}" if a.step else "") + ("-bundle" if a.bundle else "")
    out, big = ROOT / "show" / f"{name}.html", []

    def link(f: Path) -> str | None:
        if f.suffix == ".glb":
            if f.stat().st_size > GLB_MAX:
                big.append(f.name)
                return None
            return data_uri(f, "model/gltf-binary")
        if a.bundle:
            return bundled(f)
        return quote(os.path.relpath(f.resolve(), out.parent.resolve()).replace(os.sep, "/"))
    views = [asset_view(cfg, st, sid, n, link) for sid, n in cards]
    write_atomic(out, page({"project": cfg.get("project", {}).get("name", "Producer"), "assets": views}, "static"))
    print(f"OK: {rel(out)} ({out.stat().st_size // 1024} KB)"
          + (f"; GLB lớn hơn {GLB_MAX >> 20} MB không nhúng: {', '.join(big)}" if big else ""))


def dashboard():
    build_outputs(load_cfg())
    print(f"OK: {ROOT / 'dashboard.md'}")


def make_server(port: int):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from .loop import human_action

    class Handler(BaseHTTPRequestHandler):
        def send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def local(self) -> bool:
            if self.headers.get("Host", "").rsplit(":", 1)[0] in HOSTS:
                return True
            self.send_error(403)
            return False

        def do_GET(self):
            if not self.local():
                return
            path = urlsplit(self.path).path
            if path == "/api/board":
                return self.send(200, json.dumps(board_payload(load_cfg()), ensure_ascii=False).encode(),
                                 "application/json; charset=utf-8")
            if path in ("/", "/index.html", "/board.js"):
                name = "board.js" if path == "/board.js" else "index.html"
                return self.send(200, (BOARD_DIR / name).read_bytes(), mimetypes.guess_type(name)[0] + "; charset=utf-8")
            f = safe_file(load_cfg(), path)
            if f is None:
                return self.send_error(404)
            self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        def do_POST(self):
            if not self.local():
                return
            if urlsplit(self.path).path != "/api/feedback":
                return self.send_error(404)
            if self.headers.get_content_type() != "application/json":
                return self.send_error(403)
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    raise ValueError(f"body lớn hơn {MAX_BODY} byte")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data.get("offer", ""), str | None):
                    raise ValueError("offer phải là chuỗi")
                with locked():
                    msg, code = human_action(data["id"], data["action"], data.get("text", ""), data.get("step"),
                                             data.get("regions"), data.get("offer")), 200
            except Exception as ex:  # noqa: BLE001
                msg, code = f"Lỗi: {ex}", 400
            self.send(code, json.dumps({"message": msg}, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int):
    with locked():
        build_outputs(load_cfg())
    srv = make_server(port)
    print(f"Review page: http://127.0.0.1:{port}  (Ctrl+C để dừng)")
    srv.serve_forever()


