"""Paths, pipeline.toml, status.json, ledger, version dirs, and the admin commands no other module owns."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("LỖI: cần Python 3.11+ (tomllib).")

SKILL_DIR = Path(__file__).resolve().parents[2]
TEMPLATES = SKILL_DIR / "templates"
ROOT = Path(os.environ.get("PRODUCER_ROOT", "production"))
ASSETS = ROOT / "assets"
ARCHIVE = ROOT / "archive"
PORT = 8765
FEEDBACK_LOG_WARN = 12  # số dòng log feedback trước khi nhắc gộp
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
GATES = {"review", "review_human", "checks_human"}

STATES = {"draft", "todo", "running", "review", "reviewing", "fix", "waiting_human", "blocked", "done"}


class ProducerError(Exception):
    pass


def die(msg: str):
    raise ProducerError(msg)


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def rel(p: Path) -> str:
    return os.path.relpath(p)


def load_cfg() -> dict:
    p = ROOT / "pipeline.toml"
    if not p.exists():
        die(f"không thấy {p}. Chạy: producer.py init")
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    steps = cfg.get("steps") or die("pipeline.toml chưa có [[steps]]")
    ids = [s.get("id") or die("mỗi [[steps]] cần id") for s in steps]
    if len(set(ids)) != len(ids):
        die("step id bị trùng trong pipeline.toml")
    for s in steps:
        s.setdefault("gate", "review")
        s.setdefault("outputs", [])
        s.setdefault("enabled", True)
        s.setdefault("uses", [])
        s.setdefault("top_fix", [])
        if s["gate"] not in GATES:
            die(f"step {s['id']}: gate phải là {' | '.join(sorted(GATES))}")
        if s["gate"] != "checks_human":
            s.get("agent") or die(f"step {s['id']}: thiếu agent")
    pa = cfg.setdefault("paths", {})
    pa["approved"] = Path(os.path.expanduser(pa.get("approved", ""))) if pa.get("approved") else None
    pa["art_direction"] = Path(os.path.expanduser(pa.get("art_direction", ""))) if pa.get("art_direction") else None
    it = cfg.setdefault("intake", {})
    it.setdefault("min_images", 3)
    it.setdefault("type", "asset")
    it.setdefault("rubric", "rubrics/default.md")
    cfg.setdefault("preview", {}).setdefault("spec", "")
    r = cfg.setdefault("review", {})
    r.setdefault("max_fix_rounds", 3)
    r.setdefault("resume_rounds", 2)
    r.setdefault("final_human_gate", True)
    r.setdefault("reviewer_agent", "reviewer")
    r.setdefault("reviewer_model", "opus")
    return cfg


def step_of(cfg: dict, sid: str) -> tuple[int, dict]:
    for i, s in enumerate(cfg["steps"]):
        if s["id"] == sid:
            return i, s
    die(f"step '{sid}' không có trong pipeline.toml")


def adir(aid: str) -> Path:
    d = ASSETS / aid
    if not (d / "status.json").exists():
        die(f"không có asset '{aid}'")
    return d


def load_st(aid: str) -> dict:
    return json.loads((adir(aid) / "status.json").read_text(encoding="utf-8"))


def save_st(st: dict):
    st["updated"] = now()
    p = ASSETS / st["id"] / "status.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def all_status() -> list[dict]:
    if not ASSETS.exists():
        return []
    out = []
    for p in sorted(ASSETS.glob("*/status.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            out.append({"id": p.parent.name, "state": "blocked", "note": "status.json hỏng", "stage": "?"})
    return out


def sort_key(st: dict):
    return (st.get("priority") or 2, st.get("deadline") or "9999-12-31", st["id"])


def ledger(line: str):
    with open(ROOT / "ledger.md", "a", encoding="utf-8") as f:
        f.write(f"- {now()} · {line}\n")


def vdir(aid: str, step: str, n: int) -> Path:
    return ASSETS / aid / step / f"v{n}"


def rubric_approved(path: Path) -> bool:
    """Chỉ dòng đầu tiên quyết định: `<!-- status: approved -->`."""
    if not path.exists():
        return False
    first = path.read_text(encoding="utf-8").lstrip().splitlines()[:1]
    return bool(first) and bool(re.match(r"<!--\s*status:\s*approved\b", first[0]))


def rule(a):
    ledger(f"RULING: {a.text}")
    print("OK: đã ghi ruling")


def ledger_tail(a):
    p = ROOT / "ledger.md"
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("- ")] if p.exists() else []
    if a.rulings:
        lines = [l for l in lines if "RULING:" in l]
    print("\n".join(lines[-a.tail:]) or "(trống)")


def cleanup(a):
    st = load_st(a.id)
    if st["state"] != "done":
        die(f"{a.id} chưa done (state={st['state']}): vòng sửa sau còn cần work/ của bản trước")
    targets = []
    for vd in sorted((ASSETS / a.id).glob("*/v*/work")):
        step, n = vd.parent.parent.name, int(vd.parent.name[1:])
        if not a.all and st["approved"].get(step) == n:
            continue
        targets.append(vd)
    if not targets:
        print("Không có gì để dọn.")
        return
    if not a.yes:
        print("DRY-RUN — sẽ xoá (thêm --yes sau khi người dùng đồng ý):")
        print("\n".join(f"  {rel(t)}" for t in targets))
        return
    for t in targets:
        shutil.rmtree(t)
    ledger(f"{a.id} · cleanup {len(targets)} thư mục work/")
    print(f"Đã xoá {len(targets)} thư mục work/.")


def archive(a):
    from .board import build_outputs
    st = load_st(a.id)
    if st["state"] != "done" and not a.force:
        die(f"{a.id} chưa done (state={st['state']}); dùng --force nếu người dùng muốn bỏ")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ASSETS / a.id), str(ARCHIVE / a.id))
    ledger(f"{a.id} · archive")
    build_outputs(load_cfg())
    print(f"Đã chuyển {a.id} vào {rel(ARCHIVE)}/")


def validate(_a):
    from .hashes import AD_LINE, ad_readme
    cfg = load_cfg()
    ids = {s["id"] for s in cfg["steps"]}
    problems = []
    need = {"id", "title", "stage", "state", "versions", "approved", "fix_round"}
    for st in all_status():
        aid = st.get("id", "?")
        miss = need - st.keys()
        if miss:
            problems.append(f"{aid}: status.json thiếu {sorted(miss)}")
            continue
        if st["state"] not in STATES:
            problems.append(f"{aid}: state lạ '{st['state']}'")
        if st["stage"] not in ids:
            problems.append(f"{aid}: stage '{st['stage']}' không có trong pipeline.toml")
        fb = ASSETS / aid / "feedback.md"
        if fb.exists():
            log = fb.read_text(encoding="utf-8").split("## Log", 1)[-1]
            cnt = sum(1 for l in log.splitlines() if l.startswith("- "))
            if cnt > FEEDBACK_LOG_WARN:
                problems.append(f"{aid}: feedback.md có {cnt} dòng log → gộp vào mục Hiện hành, giữ 2 vòng gần nhất")
        rub = ASSETS / aid / "rubric.md"
        if rub.exists() and not re.search(r"^- [a-z0-9_]+:", rub.read_text(encoding="utf-8"), re.M):
            problems.append(f"{aid}: rubric.md chưa có tiêu chí dạng `- key: mô tả`")
    rd = ad_readme(cfg)
    if rd:
        listed = set()
        for line in rd.read_text(encoding="utf-8").split("## Thay đổi", 1)[0].splitlines():
            m = re.match(r"^\s*-\s*`?([^`\s]+\.md)`?", line)
            if m:
                listed.add(m.group(1))
                if not AD_LINE.match(line):
                    problems.append(f"art direction: `{m.group(1)}` thiếu tag `steps:` trong README")
        for f in rd.parent.glob("*.md"):
            if f.name != "README.md" and f.name not in listed:
                problems.append(f"art direction: `{f.name}` có trong thư mục nhưng README không liệt kê")
    elif cfg["paths"]["art_direction"]:
        problems.append("art direction: chưa có README.md (brief sẽ ghi 'chưa có art direction')")
    for r in sorted((ROOT / "rubrics").glob("*.md")):
        if not rubric_approved(r):
            problems.append(f"{rel(r)}: chưa duyệt (status: draft)")
    print("\n".join(problems) or "OK: không có lỗi")
