"""Paths, pipeline.toml, status.json, ledger, version dirs, and the admin commands no other module owns."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shlex
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
MODEL_NAMES = ("opus", "sonnet", "haiku")  # the runtime maps these to its real models (edition `models`)
MODEL_KEYS = ("model", "escalate_model", "reviewer_model")
# D31.3: hash, schema, export_check, Meshy topology and card counts (D30.6) never take an ACCEPTED_FAIL, whatever pipeline.toml says.
HARD_GATES = ("inputs.json", "package.json", "schema.json", "qa_export_check.json", "meshy.json", "counts.json")

STATES = {"draft", "todo", "running", "review", "reviewing", "fix", "evidence", "evidence_running", "waiting_human",
          "blocked", "done", "done_enabled"}
FINISHED = ("done", "done_enabled")
DEFAULT_TEXTURE_RES = 2048
OLD_VIEWS = ("views_front", "views_rest")  # the two view steps of v0.7.1 (D44.3); `migrate` makes them `views`
VIEWS = "views"
STEP_MAPS = ("versions", "approved", "approved_hash", "approved_at", "rejected", "locked", "inputs", "prior",
             "accepted_fail", "pending_redo", "waive_pending")


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


def codex_link(skill: Path) -> Path:
    """Where installer/codex_rules.py --write links a skill folder whose path needs shell quotes (same formula there)."""
    return (Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser() / "zps-3dp"
            / hashlib.sha1(str(skill).encode()).hexdigest()[:12])


def rule_dir(skill: Path) -> Path:
    """The skill folder as a Codex rule names it. A rule never matches a quoted program word (D46), so a path that
    needs quotes goes through codex_link when that link points at the skill; otherwise the real path."""
    if shlex.quote(str(skill)) == str(skill):
        return skill
    link = codex_link(skill)
    return link if link.is_symlink() and link.resolve() == skill.resolve() else skill


def rule_path(p: Path, skill: Path) -> Path:
    """p under the skill folder, spelled through rule_dir; p itself when nothing changes."""
    base, real = rule_dir(skill), p.parent.resolve() / p.name  # the venv python is a link out of the skill
    return base / real.relative_to(skill) if base != skill and real.is_relative_to(skill) else p


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


def stale_steps(steps: list[dict]) -> list[str]:
    """Keys of the shipped template that have no safe default, missing from the step of the same id: fix_copy_exclude
    (the fix-round worker no longer copies final/ itself) and the result JSONs of outputs (a check that never ran would
    pass). The other keys of a file made before the template fall back to a default."""
    tpl = {t["id"]: t for t in tomllib.loads((TEMPLATES / "pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    out = []
    for s in steps:
        if not (t := tpl.get(s.get("id"))):
            continue
        miss = ["fix_copy_exclude"] if "fix_copy_exclude" in t and "fix_copy_exclude" not in s else []
        if n := len({o for o in t.get("outputs", []) if o.endswith(".json")} - set(s.get("outputs", []))):
            miss.append(f"outputs ({n} JSON kết quả)")
        if miss:
            out.append(f"{s['id']} thiếu {', '.join(miss)}")
    return out


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
    if old := [x for x in ids if x in OLD_VIEWS]:
        die(f"{rel(p)} của v0.7.1 có bước {', '.join(old)}: thay hai khối [[steps]] đó bằng khối `{VIEWS}` của "
            f"{SKILL_DIR.name}/templates/pipeline.toml, đổi hai id đó thành `{VIEWS}` trong inputs, review_inputs của "
            "model và texture, rồi chạy `migrate <id>` cho mỗi asset mà `next` nêu (references/setup.md, mục Nâng cấp "
            "từ v0.7.1)")
    if stale := stale_steps(steps):
        die(f"{rel(p)} cũ hơn skill: {'; '.join(stale)}: chép các khóa đó từ {SKILL_DIR.name}/templates/pipeline.toml "
            "(references/setup.md, mục Nâng cấp từ v0.7.1)")
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
        s.setdefault("acceptable", [])
        if bad := [x for x in s["acceptable"] if x in HARD_GATES]:
            die(f"step {s['id']}: acceptable có gate cứng {', '.join(bad)} (D31.3: không bao giờ được ACCEPTED_FAIL)")
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
        for k in MODEL_KEYS:
            if k in s and s[k] not in MODEL_NAMES:
                die(f"step {s['id']}: {k} = {s[k]!r} phải là {' | '.join(MODEL_NAMES)}")
    pa = cfg.setdefault("paths", {})
    pa["approved"] = Path(os.path.expanduser(pa.get("approved", ""))) if pa.get("approved") else None
    pa["art_direction"] = Path(os.path.expanduser(pa.get("art_direction", ""))) if pa.get("art_direction") else None
    cfg.setdefault("preview", {}).setdefault("spec", "")
    cfg.setdefault("limits", {})
    r = cfg.setdefault("review", {})
    r.setdefault("max_fix_rounds", 3)
    r.setdefault("resume_rounds", 2)
    r.setdefault("max_direct_rounds", 2)
    r.setdefault("reviewer_model", "opus")
    if r["reviewer_model"] not in MODEL_NAMES:
        die(f"pipeline.toml [review] reviewer_model = {r['reviewer_model']!r} phải là {' | '.join(MODEL_NAMES)}")
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
    """`{id}` = asset id, `{res}` = texture_res. A side view outside the card's `views` is not an output (D35)."""
    from .asset_card import keep_output
    res = texture_res(st) if any("{res}" in o for o in step["outputs"]) else None
    return [o.format(id=st["id"], res=res) for o in step["outputs"] if keep_output(step, st, o)]


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


def read_st(aid: str) -> dict:
    p = adir(aid) / "status.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        die(f"{p} hỏng: {ex}")


def load_st(aid: str) -> dict:
    st = read_st(aid)
    if legacy(st):
        die(legacy_line(aid))
    return st


def legacy(st: dict) -> bool:
    """D44.3: a status.json of v0.7.1 that still names one of its two view steps."""
    return st.get("stage") in OLD_VIEWS or any(k in (st.get(f) or {}) for f in ("versions", "approved", "prior")
                                               for k in OLD_VIEWS)


def legacy_line(aid: str) -> str:
    return f"{aid}: status.json của v0.7.1 còn bước {'/'.join(OLD_VIEWS)} → chạy `migrate {aid}`"


def save_st(st: dict):
    st["updated"] = now()
    write_atomic(ASSETS / st["id"] / "status.json", json.dumps(st, ensure_ascii=False, indent=2))


def all_status() -> list[dict]:
    if not ASSETS.exists():
        return []
    out = []
    for p in sorted(ASSETS.glob("*/status.json")):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            out.append({"id": p.parent.name, "state": "blocked", "note": "status.json hỏng", "stage": "?", "broken": True})
            continue
        out.append({"id": p.parent.name, "stage": st.get("stage"), "state": st.get("state"), "versions": {},
                    "note": legacy_line(p.parent.name), "broken": True, "legacy": True} if legacy(st) else st)
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


def archive(a):
    from .board import build_outputs
    st = load_st(a.id)
    if st["state"] not in FINISHED and not a.force:
        die(f"{a.id} chưa done (state={st['state']}); dùng --force nếu người dùng muốn bỏ")
    if (ASSETS / a.id / "purge-pending.json").is_file():
        die(f"{a.id}: còn lệnh xóa D29 đang chờ (archive/ không được dọn): `keep {a.id}` hoặc `purge {a.id}` trước")
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
        if st.get("legacy"):
            problems.append(st["note"])
            continue
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
        if rub.exists() and (t := rub.read_text(encoding="utf-8")) != views_rubric(t)[0]:
            problems.append(f"{aid}: rubric.md của v0.7.1 còn mục {', '.join(OLD_VIEWS)} → chạy `migrate {aid}`")
            continue
        if rub.exists() and not re.search(r"^- [A-Za-z0-9_]+:", rub.read_text(encoding="utf-8"), re.M):
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


RUBRIC_KEY = re.compile(r"^- ([A-Za-z0-9_]+):")


def views_rubric(text: str) -> tuple[str, list[str]]:
    """D44.3: `## views_rest` becomes `## views` and `## views_front` goes. A key of the front section that the set
    section lacks moves to the end of `## views`, with its indented lines. Without a set section the front section
    becomes `## views`. Returns the text and the moved keys."""
    parts = [["", []]]
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            parts.append([line.strip()[3:], []])
        parts[-1][1].append(line)
    sec = dict(parts)
    front, rest = sec.get(OLD_VIEWS[0]), sec.get(OLD_VIEWS[1])
    have = {m[1].lower() for line in rest or [] if (m := RUBRIC_KEY.match(line))}
    add, moved, on = [], [], False
    for line in (front or [])[1:] if rest is not None else []:
        if m := RUBRIC_KEY.match(line):
            on = m[1].lower() not in have
            moved += [m[1]] if on else []
        elif not (line[:1].isspace() and line.strip()):
            on = False
        if on:
            add.append(line if line.endswith("\n") else line + "\n")
    out = []
    for name, lines in parts:
        if name == OLD_VIEWS[0] and rest is not None:
            continue
        if name in OLD_VIEWS:
            lines = [f"## {VIEWS}\n", *lines[1:]]
            if name == OLD_VIEWS[1] and add:
                k = len(lines)
                while k > 1 and not lines[k - 1].strip():
                    k -= 1
                lines = [*lines[:k - 1], lines[k - 1].rstrip("\n") + "\n", *add, *lines[k:]]
        out += lines
    return "".join(out), moved


def merge_readme(front: Path, merged: Path):
    """The NGOẠI LỆ lines of the front README join the NGOẠI LỆ section of the set README, where "không có" goes."""
    from assemble import section
    extra = [x for x in section(front, "NGOẠI LỆ") if x.strip().lower() not in ("không có", "none")]
    if not extra or not merged.is_file():
        return
    out, on, done = [], False, False
    for line in merged.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            on = "ngoại lệ" in line.lower() and not done
            out += [line, *(extra if on else [])]
            done = done or on
        elif not (on and line.strip().lower() == "không có"):
            out.append(line)
    merged.write_text("\n".join(out if done else [*out, "## NGOẠI LỆ", *extra]) + "\n", encoding="utf-8")


def merge_pair(aid: str, fv: int, rv: int) -> Path:
    """The final of the front, then the final of the set over it, as `views` v1. The set findings keep their ids; the
    open findings of the front join with new ids. Later notes that confirmed a set finding name the new version."""
    from . import findings
    d = vdir(aid, VIEWS, 1)
    if gone := [rel(vdir(aid, s, v) / "final") for s, v in zip(OLD_VIEWS, (fv, rv)) if not (vdir(aid, s, v) / "final").is_dir()]:
        die(f"{aid}: thiếu {', '.join(gone)}: không gộp được bộ view cũ; làm lại bước views bằng tay (references/setup.md)")
    if d.exists():
        shutil.rmtree(d)
    for sid, v in zip(OLD_VIEWS, (fv, rv)):
        shutil.copytree(vdir(aid, sid, v) / "final", d / "final", dirs_exist_ok=True)
    merge_readme(vdir(aid, OLD_VIEWS[0], fv) / "final" / "README.md", d / "final" / "README.md")
    doc = findings.load(aid, OLD_VIEWS[1], rv) or {"next_id": 1, "findings": {}}
    doc = doc | {"version": 1, "base": None, "top_fix": None, "pick": None, "findings": dict(doc["findings"])}
    for i, f in findings.open_of(findings.load(aid, OLD_VIEWS[0], fv)).items():
        doc["findings"][f"F{doc['next_id']}"] = f | {"evidence": f"{OLD_VIEWS[0]} v{fv} {i}: {f.get('evidence', '')}"}
        doc["next_id"] += 1
    findings.save(aid, VIEWS, doc)
    old = f"{OLD_VIEWS[1]} v{rv} "
    for p in (ASSETS / aid).glob("*/v*/findings.json"):
        other = json.loads(p.read_text(encoding="utf-8"))
        notes = other.get("resolved_notes") or []
        if p.parts[-3] not in (*OLD_VIEWS, VIEWS) and any(n.startswith(old) for n in notes):
            other["resolved_notes"] = [f"{VIEWS} v1 " + n.removeprefix(old) if n.startswith(old) else n for n in notes]
            write_atomic(p, json.dumps(other, ensure_ascii=False, indent=1))
    return d


def migrate(a):
    """D44.3 `P migrate <id>` (references/setup.md, Nâng cấp từ v0.7.1). The old folders stay on disk. (a) status.json
    names no old view step: nothing. (b) both old steps approved, or both kept as `prior`: the pair becomes `views` v1,
    approved (or prior) as the pair was. (c) otherwise: the view work restarts as `views` at todo. The history keeps its
    rows under `views`; decisions keep their old keys. rubric.md and the project rubrics get one `## views` section."""
    from . import findings, hashes
    from .loop import fresh, next_action, reopened_of
    aid, cfg = a.id, load_cfg()
    st = read_st(aid)
    rubrics = [ASSETS / aid / "rubric.md", *sorted((ROOT / "rubrics").glob("*.md"))]
    changed = [r for r in rubrics if r.is_file() and (t := r.read_text(encoding="utf-8")) != views_rubric(t)[0]]
    for r in changed:
        text, moved = views_rubric(r.read_text(encoding="utf-8"))
        r.write_text(text, encoding="utf-8")
        if moved:
            print(f"{rel(r)}: ## {VIEWS} nhận key chỉ có ở ## {OLD_VIEWS[0]}: {', '.join(moved)}")
    tail = f"; rubric.md có mục ## {VIEWS}" if rubrics[0] in changed else ""
    if not legacy(st):
        if changed:
            ledger(f"{aid} · migrate · rubric: {', '.join(rel(r) for r in changed)}")
        print(f"{aid}: không có bước view cũ, không đổi gì{tail}")
        return
    pair = next((k for k in ("approved", "prior") if all(s in (st.get(k) or {}) for s in OLD_VIEWS)), None)
    old_stage, old_state = st.get("stage"), st.get("state")
    if pair:
        fv, rv = (st[pair][s] for s in OLD_VIEWS)
        d = merge_pair(aid, fv, rv)
        built = (st.get("inputs") or {}).get(OLD_VIEWS[0], {}).get(f"v{fv}")
        at = (st.get("approved_at") or {}).get(OLD_VIEWS[1])
    for k in STEP_MAPS:
        if isinstance(st.get(k), dict):
            st[k] = {s: v for s, v in st[k].items() if s not in OLD_VIEWS}
    st["stale"] = {k: v for k, v in (st.get("stale") or {}).items() if k.split()[0] not in OLD_VIEWS}
    st["reopened"] = {k: v for k, v in reopened_of(st).items() if k in findings.REOPEN}
    for k in ("dispatches", "offer_log", "stalls"):
        for x in st.get(k) or []:
            if x.get("step") in OLD_VIEWS:
                x["step"] = VIEWS
                if k == "dispatches" and "ingested" not in x and "ended" not in x:
                    x["ended"] = stamp()
    if pair:
        st.setdefault("versions", {})[VIEWS] = 1
        st.setdefault(pair, {})[VIEWS] = 1
        if pair == "approved":
            st.setdefault("approved_hash", {})[VIEWS] = hashes.tree_hash(d / "final")
            st.setdefault("rejected", {})[VIEWS] = []
            st.setdefault("approved_at", {})[VIEWS] = at or now()
            if built:
                st.setdefault("inputs", {})[VIEWS] = {"v1": built}
        what = (f"{OLD_VIEWS[0]} v{fv} + {OLD_VIEWS[1]} v{rv} → {VIEWS} v1 "
                f"({'đã duyệt' if pair == 'approved' else 'bản đã duyệt trước'}), thư mục cũ giữ nguyên{tail}")
    else:
        what = f"bỏ bước view cũ khỏi status.json, thư mục cũ giữ nguyên{tail}"
    if old_stage in OLD_VIEWS and pair == "approved":
        st["stage"] = VIEWS
    elif old_stage in OLD_VIEWS:
        st |= fresh() | {"stage": VIEWS, "state": "todo", "worker_agent_id": None, "review_scope": None,
                         "dispatch_out": None}
        for k in ("ask", "stalled_from", "blocked_from", "accepted"):
            st.pop(k, None)
        what = (f"{old_stage} {old_state} của v0.7.1 làm lại thành bước {VIEWS}, thư mục cũ giữ nguyên{tail} → "
                f"{VIEWS}/todo")
    hashes.refresh_stale(cfg, st)
    save_st(st)
    ledger(f"{aid} · migrate · {what}")
    print(f"{aid}: {what}. Tiếp: {next_action(st)}")
