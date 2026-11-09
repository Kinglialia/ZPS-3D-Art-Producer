"""Source tracking (docs/producer.md §10, §11): profile hash, per-version `inputs`, stale versions, warnings, `ack`."""
from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import re
from pathlib import Path

from .state import ROOT, die, ledger, load_st, save_st, vdir

AD_LINE = re.compile(r"^\s*-\s*`?([^`\s]+\.md)`?.*?steps:\s*([a-z0-9_,\s-]+)\s*$", re.I)
DATED_LINE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s*·\s*(.+)$")
CARD = "asset-card.yaml"
SOURCES = ("concept", "card", "profile")
WARN = {"concept": "concept đổi sau khi bắt đầu", "card": "thẻ đổi sau khi bắt đầu", "profile": "profile đổi sau khi bắt đầu"}


def ad_readme(cfg: dict) -> Path | None:
    d = cfg["paths"]["art_direction"]
    return d / "README.md" if d and (d / "README.md").exists() else None


def ad_docs(cfg: dict, tags: set[str]) -> list[Path]:
    """Tài liệu art direction có tag `steps:` khớp một trong các tags."""
    rd = ad_readme(cfg)
    if not rd:
        return []
    out = []
    for line in rd.read_text(encoding="utf-8").split("## Thay đổi", 1)[0].splitlines():
        m = AD_LINE.match(line)
        if m:
            steps = {t.strip().lower() for t in m.group(2).split(",")}
            if steps & tags:
                out.append(rd.parent / m.group(1))
    return out


def ad_changes(cfg: dict) -> list[tuple[str, str]]:
    rd = ad_readme(cfg)
    if not rd:
        return []
    body = rd.read_text(encoding="utf-8").split("## Thay đổi", 1)
    if len(body) < 2:
        return []
    return [(m.group(1), m.group(2).strip()) for m in map(DATED_LINE.match, body[1].splitlines()) if m]


def ad_text(cfg: dict, tags: set[str]) -> str:
    """Một câu cho brief: tài liệu art direction cần đọc ở bước này."""
    rd = ad_readme(cfg)
    if not rd:
        return "Art direction: chưa có. Làm theo brief và rubric; ghi \"chưa có art direction\" vào báo cáo."
    docs = ad_docs(cfg, tags)
    if not docs:
        return f"Art direction: không có tài liệu gắn cho bước này. Cần chuẩn khác thì xem `{rd}`."
    return f"Art direction cho bước này: {', '.join(f'`{d}`' for d in docs)}. Cần chuẩn khác thì xem `{rd}`."


def schedule_soon(days: int = 14) -> list[tuple[str, str]]:
    p = ROOT / "schedule.md"
    if not p.exists():
        return []
    today, until = dt.date.today().isoformat(), (dt.date.today() + dt.timedelta(days=days)).isoformat()
    return [(m.group(1), m.group(2).strip()) for m in map(DATED_LINE.match, p.read_text(encoding="utf-8").splitlines())
            if m and today <= m.group(1) <= until]


def tree_hash(d: Path, skip: str = "") -> str | None:
    if not d.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file() and x.name != skip
                    and not any(s.startswith(".") for s in x.relative_to(d).parts)):
        h.update(p.relative_to(d).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if not str(k).startswith("_")}
    return [_strip(i) for i in x] if isinstance(x, list) else x


def digest(profile: dict) -> str:
    """D21.3: hash of the normalized profile without `paths` and `_` keys, so notes and paths never warn."""
    body = _strip({k: v for k, v in profile.items() if k != "paths"})
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     default=str).encode()).hexdigest()[:12]


@functools.lru_cache(maxsize=4)
def _profile_digest(path: str, _mtime: int, _size: int) -> str | None:
    import yaml
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return digest(data) if isinstance(data, dict) else None


def profile_hash() -> str | None:
    p = ROOT / "PROJECT-PROFILE.yaml"
    if not p.exists():
        return None
    s = p.stat()
    return _profile_digest(str(p.resolve()), s.st_mtime_ns, s.st_size)


def sources(st: dict, profile: str | None = None) -> dict:
    cd = Path(st["concept_dir"]) if st.get("concept_dir") else None
    card = cd / CARD if cd else None
    return {"concept": tree_hash(cd, skip=CARD) if cd else None,
            "card": hashlib.sha256(card.read_bytes()).hexdigest() if card and card.is_file() else None,
            "profile": profile or profile_hash()}


def check_inputs(st: dict, inp: dict):
    """Checklist 71: an approved final/ edited after approval stops the brief or ingest that would build on it."""
    for prev, rec in inp.items():
        if isinstance(rec, dict) and tree_hash(vdir(st["id"], prev, rec["v"]) / "final") != rec["hash"]:
            die(f"{prev} v{rec['v']}: final/ đã duyệt bị sửa sau khi duyệt (hash lệch)")


def record_inputs(cfg: dict, st: dict, i: int, n: int, ph: str) -> dict:
    prev = {s["id"]: {"v": st["approved"][s["id"]], "hash": st.get("approved_hash", {}).get(s["id"])}
            for s in cfg["steps"][:i] if s["id"] in st["approved"]}
    check_inputs(st, prev)
    inp = prev | sources(st, ph) | {"art_direction": max((d for d, _ in ad_changes(cfg)), default="")}
    st.setdefault("inputs", {}).setdefault(cfg["steps"][i]["id"], {})[f"v{n}"] = inp
    st.setdefault("sources", {k: inp[k] for k in SOURCES})
    refresh_stale(cfg, st)
    return inp


def refresh_stale(cfg: dict, st: dict):
    """§11: `stale["<step> vN"] = "<prev> vM"` when vN was built from a prev-step final that is no longer approved."""
    ids = [s["id"] for s in cfg["steps"]]
    ah = st.get("approved_hash", {})
    out = {}
    for sid, vers in (st.get("inputs") or {}).items():
        i = ids.index(sid) if sid in ids else 0
        if i == 0:
            continue
        prev = ids[i - 1]
        for v, inp in vers.items():
            if (rec := inp.get(prev)) and rec["hash"] != ah.get(prev):
                out[f"{sid} {v}"] = f"{prev} v{rec['v']}"
    st["stale"] = out


def warnings_for(cfg: dict, st: dict) -> list[str]:
    """Cảnh báo concept, thẻ, profile (theo nội dung, D23.1) hoặc art direction đổi sau khi asset bắt đầu."""
    w = []
    if base := st.get("sources"):
        cur = sources(st)
        w = [WARN[k] for k in SOURCES if cur[k] != base.get(k)]
    since = max(st.get("started", ""), st.get("ad_ack") or "")
    changed = [d for d, _ in ad_changes(cfg) if d > since]
    if changed:
        w.append(f"art direction đổi ({', '.join(changed)})")
    return w


def ack(a):
    st = load_st(a.id)
    st["sources"] = sources(st)
    st["ad_ack"] = dt.date.today().isoformat()
    save_st(st)
    ledger(f"{a.id} · ack thay đổi concept/thẻ/profile/art direction · {a.note}")
    print(f"{a.id}: đã ghi nhận thay đổi")
