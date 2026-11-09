"""Project init, asset creation, `_approved/` intake scan, `ready`."""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from pathlib import Path

from .hashes import concept_images, latest_mtime, warnings_for
from .state import (ARCHIVE, ASSETS, ROOT, TEMPLATES, all_status, die, ledger, load_st, now, rel,
                    rubric_approved, save_st)

FEEDBACK_TMPL = """# Feedback — {title}

## Hiện hành
<!-- Producer duy trì: các quyết định còn hiệu lực, gộp từ log. Worker đọc mục này trước. -->

## Log
"""


def init(a):
    for d in (ROOT, ASSETS, ARCHIVE, ROOT / "rubrics"):
        d.mkdir(parents=True, exist_ok=True)
    concepts = Path(os.path.expanduser(a.concepts)).resolve()
    fill = {"{{PROJECT}}": a.project, "{{CONCEPTS}}": str(concepts), "{{DATE}}": dt.date.today().isoformat()}

    def put(src: Path, dst: Path):
        if dst.exists():
            print(f"giữ nguyên {dst}")
            return
        text = src.read_text(encoding="utf-8")
        for k, v in fill.items():
            text = text.replace(k, v)
        dst.write_text(text, encoding="utf-8")
        print(f"tạo {dst}")

    put(TEMPLATES / "pipeline.toml", ROOT / "pipeline.toml")
    for r in sorted((TEMPLATES / "rubrics").glob("*.md")):
        put(r, ROOT / "rubrics" / r.name)
    (concepts / "_approved").mkdir(parents=True, exist_ok=True)
    put(TEMPLATES / "GUIDELINE.md", concepts / "GUIDELINE.md")
    for name, body in (("ledger.md", "# Ledger\n\n"),
                       ("schedule.md", "# Schedule\n\n<!-- Mỗi milestone một dòng: `- YYYY-MM-DD · việc`. Có thể kèm link tới Sheet/Calendar gốc. -->\n")):
        if not (ROOT / name).exists():
            (ROOT / name).write_text(body, encoding="utf-8")
    print("Xong. Duyệt rubric trong production/rubrics/ (đổi `status: draft` thành `status: approved`), "
          "gửi GUIDELINE.md cho Concept Artist và AD.")


def create_asset(cfg: dict, aid: str, title: str, typ: str, priority: int, deadline: str | None,
                 concept_dir: Path | None) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", aid):
        die(f"id '{aid}' không hợp lệ: chỉ gồm a-z, 0-9 và '-'")
    d = ASSETS / aid
    if d.exists() or (ARCHIVE / aid).exists():
        die(f"asset {aid} đã tồn tại")
    rub_src = ROOT / cfg["intake"]["rubric"] if typ == cfg["intake"]["type"] else ROOT / "rubrics" / f"{typ}.md"
    if not rub_src.exists():
        rub_src = ROOT / "rubrics" / "default.md"
    d.mkdir(parents=True)
    src_note = f"\nConcept đã duyệt: `{concept_dir}`\n" if concept_dir else ""
    (d / "brief.md").write_text(
        f"# Brief — {title}\n{src_note}\n<!-- Yêu cầu gốc, sát lời người dùng. Không sửa sau khi chốt; bổ sung ở mục Làm rõ. -->\n\n## Làm rõ\n",
        encoding="utf-8")
    shutil.copy(rub_src, d / "rubric.md")
    (d / "feedback.md").write_text(FEEDBACK_TMPL.format(title=title), encoding="utf-8")
    ready = rubric_approved(rub_src)
    st = {"id": aid, "title": title, "type": typ, "priority": priority, "deadline": deadline,
          "stage": cfg["steps"][0]["id"], "state": "todo" if ready else "draft",
          "versions": {}, "approved": {}, "fix_round": 0, "worker_agent_id": None, "last_rubric": "",
          "note": "" if ready else "chờ duyệt rubric", "created": now(), "started": dt.date.today().isoformat(),
          "concept_dir": str(concept_dir) if concept_dir else None,
          "concept_mtime": latest_mtime(concept_dir) if concept_dir else 0.0, "ad_ack": None}
    save_st(st)
    ledger(f"{aid} · tạo mới ({'todo' if ready else 'draft, rubric chưa duyệt'})")
    return st


def new(a, cfg: dict):
    st = create_asset(cfg, a.id, a.title, a.type, a.priority, a.deadline, None)
    print(f"OK {a.id} → {st['state']}. Viết yêu cầu vào {rel(ASSETS / a.id / 'brief.md')}"
          + ("" if st["state"] == "todo" else f"; rubric chưa duyệt, duyệt xong thì `ready {a.id}`"))


def scan_approved(cfg: dict) -> dict:
    root = cfg["paths"]["approved"]
    if not root or not root.exists():
        die("chưa cấu hình [paths].approved trong pipeline.toml hoặc thư mục không tồn tại")
    known = {s["id"]: s for s in all_status()}
    archived = {p.name for p in ARCHIVE.glob("*")} if ARCHIVE.exists() else set()
    g = {"new": [], "few": [], "bad_name": [], "loose": [], "changed": [], "registered": []}
    for p in sorted(root.iterdir()):
        if p.name.startswith("."):
            continue
        if p.is_file():
            g["loose"].append(p.name)
        elif not re.fullmatch(r"[a-z0-9][a-z0-9-]*", p.name):
            g["bad_name"].append(p.name)
        elif p.name in known:
            st = known[p.name]
            (g["changed"] if "concept đổi sau khi bắt đầu" in warnings_for(cfg, st) else g["registered"]).append(p.name)
        elif p.name in archived:
            g["registered"].append(p.name)
        else:
            n = len(concept_images(p))
            (g["new"] if n >= cfg["intake"]["min_images"] else g["few"]).append(f"{p.name} ({n} ảnh)" if n < cfg["intake"]["min_images"] else p.name)
    return g


def run(a, cfg: dict):
    g = scan_approved(cfg)
    if not a.ids and not a.all:
        labels = {"new": "Mới, đủ ảnh", "few": "Mới, ít ảnh (có thể thiếu view)", "changed": "Concept đổi sau khi bắt đầu",
                  "bad_name": "Tên thư mục sai quy ước", "loose": "File rời (không thuộc building nào)",
                  "registered": "Đã đăng ký"}
        for k, lab in labels.items():
            if g[k]:
                print(f"{lab} ({len(g[k])}): {', '.join(g[k])}")
        print("Đăng ký: `intake --all` (nhóm 'Mới, đủ ảnh') hoặc `intake <id> ... [--priority 1]`")
        return
    root = cfg["paths"]["approved"]
    ids = [x.split(" ")[0] for x in g["new"]] if a.all else a.ids
    if not ids:
        print("Không có building mới đủ ảnh.")
        return
    done = []
    for aid in ids:
        if not (root / aid).is_dir():
            die(f"không có thư mục {root / aid}")
        create_asset(cfg, aid, aid.replace("-", " ").title(), cfg["intake"]["type"], a.priority, a.deadline, root / aid)
        done.append(aid)
    rub = ROOT / cfg["intake"]["rubric"]
    print(f"Đã đăng ký {len(done)}: {', '.join(done)}.")
    if not rubric_approved(rub):
        print(f"Rubric {rel(rub)} chưa duyệt: asset nằm ở draft. Người dùng duyệt xong thì `ready {' '.join(done)}`.")


def ready(a):
    for aid in a.ids:
        st = load_st(aid)
        if st["state"] != "draft":
            print(f"{aid}: bỏ qua (state={st['state']})")
            continue
        st["state"], st["note"] = "todo", ""
        save_st(st)
        ledger(f"{aid} · ready")
        print(f"{aid}: → todo")
