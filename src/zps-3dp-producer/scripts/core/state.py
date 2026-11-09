"""Paths, pipeline.toml, status.json, ledger, version dirs, and the admin commands no other module owns."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import shutil
import sys
import threading
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
RUNTIMES = ("claude", "codex")


def _edition() -> dict:
    """`runtime.json` that build.py writes into each edition; the source tree has none."""
    try:
        return json.loads((SKILL_DIR / "runtime.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


EDITION = _edition()
RUNTIME = os.environ.get("PRODUCER_RUNTIME") or EDITION.get("runtime") or "src"
SUFFIX = EDITION.get("suffix", "")
MODELS = EDITION.get("models") or {}
DELIVER = ROOT.parent / ("deliver" + ROOT.name.removeprefix("production") if ROOT.name.startswith("production")
                         else ROOT.name + "-deliver")
PORT = 8765
FEEDBACK_LOG_WARN = 12  # số dòng log feedback trước khi nhắc gộp
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
GATES = {"review", "review_human", "checks_human"}

STATES = {"draft", "todo", "running", "review", "reviewing", "fix", "evidence", "evidence_running", "waiting_human",
          "blocked", "done", "done_enabled"}
FINISHED = ("done", "done_enabled")
DEFAULT_TEXTURE_RES = 2048


class ProducerError(Exception):
    pass


def die(msg: str):
    raise ProducerError(msg)


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rel(p: Path) -> str:
    return os.path.relpath(p)


def write_atomic(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def runtime_guard():
    """A/B (§16): `production-<runtime>` belongs to that runtime; another edition must not write its ledger."""
    m = re.fullmatch(r"production-(\w+)", ROOT.name)
    if m and m[1] in RUNTIMES and RUNTIME in RUNTIMES and m[1] != RUNTIME:
        die(f"{ROOT} là thư mục của runtime {m[1]}, phiên này là {RUNTIME}: đặt PRODUCER_ROOT=production-{RUNTIME}")


def agent_name(short: str) -> str:
    return f"zps-3dp-{short}{SUFFIX}"


def agent_file(name: str) -> Path:
    d = SKILL_DIR / "agents"
    return d / name / f"{name}.md" if (d / name).is_dir() else d / f"{name}.md"


def model_of(generic: str | None) -> str | None:
    """The adapter's real model for `opus|sonnet|haiku` (edition `models`); null = the session's own model."""
    return MODELS.get(generic, generic) if generic else None


@contextlib.contextmanager
def locked(create: bool = False):
    """One writer at a time across P processes and board threads: flock on production/.lock."""
    runtime_guard()
    if create:
        ROOT.mkdir(parents=True, exist_ok=True)
    if not ROOT.is_dir():
        yield
        return
    import fcntl
    with open(ROOT / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def load_cfg() -> dict:
    p = ROOT / "pipeline.toml"
    if not p.exists():
        die(f"không thấy {p}. Chạy: producer.py init")
    try:
        cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as ex:
        die(f"{p} sai cú pháp TOML: {ex}")
    steps = cfg.get("steps") or die("pipeline.toml chưa có [[steps]]")
    ids = [s.get("id") or die("mỗi [[steps]] cần id") for s in steps]
    if len(set(ids)) != len(ids):
        die("step id bị trùng trong pipeline.toml")
    for i, s in enumerate(steps):
        s.setdefault("gate", "review")
        s.setdefault("outputs", [])
        s.setdefault("enabled", True)
        s.setdefault("uses", [])
        s.setdefault("top_fix", [])
        s.setdefault("inputs", ids[i - 1:i])
        s.setdefault("concept", None)
        s.setdefault("regions", [])
        s.setdefault("issues", [])
        s.setdefault("review_inputs", s["inputs"])
        s.setdefault("lock", None)
        s.setdefault("pilot", False)
        s.setdefault("script", None)
        s.setdefault("review_concept", None)
        if bad := [x for x in s["inputs"] if x not in ids[:i]]:
            die(f"step {s['id']}: inputs {', '.join(bad)} không phải bước trước nó")
        if bad := [x for x in s["issues"] if x not in s["inputs"]]:
            die(f"step {s['id']}: issues {', '.join(bad)} không nằm trong inputs của bước")
        if bad := [x for x in s["review_inputs"] if x not in s["inputs"]]:
            die(f"step {s['id']}: review_inputs {', '.join(bad)} không nằm trong inputs của bước")
        if s["gate"] not in GATES:
            die(f"step {s['id']}: gate phải là {' | '.join(sorted(GATES))}")
        if s["gate"] != "checks_human":
            s.get("agent") or die(f"step {s['id']}: thiếu agent")
            s.get("reviewer") or die(f"step {s['id']}: thiếu reviewer")
        elif not s.get("agent") and not s["script"]:
            die(f"step {s['id']}: gate checks_human cần agent hoặc script")
    pa = cfg.setdefault("paths", {})
    pa["approved"] = Path(os.path.expanduser(pa.get("approved", ""))) if pa.get("approved") else None
    pa["art_direction"] = Path(os.path.expanduser(pa.get("art_direction", ""))) if pa.get("art_direction") else None
    cfg.setdefault("preview", {}).setdefault("spec", "")
    cfg.setdefault("limits", {})
    r = cfg.setdefault("review", {})
    r.setdefault("max_fix_rounds", 3)
    r.setdefault("resume_rounds", 2)
    r.setdefault("reviewer_model", "opus")
    return cfg


def texture_res(st: dict) -> int:
    """`texture_res` of the asset card; null or no card: 2048 (texture-artist.md §2)."""
    card = Path(st["concept_dir"]) / "asset-card.yaml" if st.get("concept_dir") else None
    if card and card.is_file():
        import yaml
        r = (yaml.safe_load(card.read_text(encoding="utf-8")) or {}).get("texture_res")
        if isinstance(r, int) and not isinstance(r, bool) and r > 0:
            return r
    return DEFAULT_TEXTURE_RES


def outputs_of(step: dict, st: dict) -> list[str]:
    """`{id}` = asset id, `{res}` = texture_res."""
    res = texture_res(st) if any("{res}" in o for o in step["outputs"]) else None
    return [o.format(id=st["id"], res=res) for o in step["outputs"]]


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
    p = adir(aid) / "status.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        die(f"{p} hỏng: {ex}")


def save_st(st: dict):
    st["updated"] = now()
    write_atomic(ASSETS / st["id"] / "status.json", json.dumps(st, ensure_ascii=False, indent=2))


def all_status() -> list[dict]:
    if not ASSETS.exists():
        return []
    out = []
    for p in sorted(ASSETS.glob("*/status.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            out.append({"id": p.parent.name, "state": "blocked", "note": "status.json hỏng", "stage": "?", "broken": True})
    return out


def sort_key(st: dict):
    return (st.get("priority") or 2, st.get("deadline") or "9999-12-31", st["id"])


def ledger(line: str):
    with open(ROOT / "ledger.md", "a", encoding="utf-8") as f:
        f.write(f"- {now()} · {RUNTIME} · {line}\n")


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
    print("\n".join(lines[-a.tail:] if a.tail > 0 else []) or "(trống)")


def cleanup(a):
    st = load_st(a.id)
    if st["state"] not in FINISHED:
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
    if st["state"] not in FINISHED and not a.force:
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
        if rub.exists() and (gone := [s["id"] for s in cfg["steps"] if s["enabled"] and s.get("reviewer")
                                      and not re.search(rf"^## {s['id']}\s*$", rub.read_text(encoding="utf-8"), re.M)]):
            problems.append(f"{aid}: rubric.md thiếu mục {', '.join(f'## {g}' for g in gone)} của bước đang bật "
                            "(chép từ templates/rubrics/)")
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
    if problems:
        sys.exit(1)
