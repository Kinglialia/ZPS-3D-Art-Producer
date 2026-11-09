"""Source tracking: art direction, concept files, schedule, change warnings and `ack`."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .state import IMAGE_EXT, ROOT, ledger, load_st, save_st

AD_LINE = re.compile(r"^\s*-\s*`?([^`\s]+\.md)`?.*?steps:\s*([a-z0-9_,\s-]+)\s*$", re.I)
DATED_LINE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s*·\s*(.+)$")


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


def concept_images(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT) if d.exists() else []


def latest_mtime(d: Path) -> float:
    return max((p.stat().st_mtime for p in d.rglob("*") if p.is_file()), default=0.0)


def schedule_soon(days: int = 14) -> list[tuple[str, str]]:
    p = ROOT / "schedule.md"
    if not p.exists():
        return []
    today, until = dt.date.today().isoformat(), (dt.date.today() + dt.timedelta(days=days)).isoformat()
    return [(m.group(1), m.group(2).strip()) for m in map(DATED_LINE.match, p.read_text(encoding="utf-8").splitlines())
            if m and today <= m.group(1) <= until]


def warnings_for(cfg: dict, st: dict) -> list[str]:
    """Cảnh báo concept hoặc art direction đổi sau khi asset bắt đầu."""
    w = []
    cd = st.get("concept_dir")
    if cd and Path(cd).exists() and latest_mtime(Path(cd)) > st.get("concept_mtime", 0) + 1:
        w.append("concept đổi sau khi bắt đầu")
    since = max(st.get("started", ""), st.get("ad_ack") or "")
    changed = [d for d, _ in ad_changes(cfg) if d > since]
    if changed:
        w.append(f"art direction đổi ({', '.join(changed)})")
    return w


def ack(a):
    st = load_st(a.id)
    if st.get("concept_dir"):
        st["concept_mtime"] = latest_mtime(Path(st["concept_dir"]))
    st["ad_ack"] = dt.date.today().isoformat()
    save_st(st)
    ledger(f"{a.id} · ack thay đổi concept/art direction · {a.note}")
    print(f"{a.id}: đã ghi nhận thay đổi")
