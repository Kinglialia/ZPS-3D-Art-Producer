"""Project init, asset creation, `_approved/` intake scan, `ready`."""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from pathlib import Path

import check_card
import check_profile

from .estimate import batch_line
from .hashes import warnings_for
from .state import (ARCHIVE, ASSETS, FINISHED, ROOT, TEMPLATES, all_status, die, ledger, load_st, now, rel,
                    rubric_approved, save_st)

SCRIPTS = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "PROJECT-PROFILE.yaml"
ERROR_LABELS = {"files": "Thiếu file", "type": "Loại chưa hỗ trợ v1", "card": "Thẻ sai"}

FEEDBACK_TMPL = """# Feedback — {title}

## Hiện hành
<!-- Producer duy trì: các quyết định còn hiệu lực, gộp từ log. Worker đọc mục này trước. -->

## Log
"""


def init(a):
    for d in (ROOT, ASSETS, ARCHIVE, ROOT / "rubrics"):
        d.mkdir(parents=True, exist_ok=True)
    concepts = Path(os.path.expanduser(a.concepts)).resolve()
    fill = {"{{PROJECT}}": a.project, "{{CONCEPTS}}": str(concepts), "{{DATE}}": dt.date.today().isoformat(),
            "{{CHECK_CARD}}": f"{SCRIPTS / '.deps/venv/bin/python'} {SCRIPTS / 'check_card.py'}",
            "{{PROFILE}}": str(PROFILE.resolve())}

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
    put(TEMPLATES / "policy.yaml", ROOT / "policy.yaml")
    for r in sorted((TEMPLATES / "rubrics").glob("*.md")):
        put(r, ROOT / "rubrics" / r.name)
    (concepts / "_approved").mkdir(parents=True, exist_ok=True)
    put(TEMPLATES / "GUIDELINE.md", concepts / "GUIDELINE.md")
    for name, body in (("ledger.md", "# Ledger\n\n"),
                       ("schedule.md", "# Schedule\n\n<!-- Mỗi milestone một dòng: `- YYYY-MM-DD · việc`. Có thể kèm link tới Sheet/Calendar gốc. -->\n")):
        if not (ROOT / name).exists():
            (ROOT / name).write_text(body, encoding="utf-8")
    ignore_env()
    print("Xong. Duyệt rubric trong production/rubrics/ (đổi `status: draft` thành `status: approved`), "
          "gửi GUIDELINE.md cho Concept Artist và AD.")


def ignore_env():
    g = Path(".gitignore")
    lines = g.read_text(encoding="utf-8").splitlines() if g.exists() else []
    if ".env" not in (l.strip() for l in lines):
        g.write_text("".join(l + "\n" for l in lines) + ".env\n", encoding="utf-8")
        print("thêm .env vào .gitignore")


def create_asset(cfg: dict, aid: str, title: str, typ: str, priority: int, deadline: str | None,
                 concept_dir: Path | None) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", aid):
        die(f"id '{aid}' không hợp lệ: chỉ gồm a-z, 0-9 và '-'")
    d = ASSETS / aid
    if (d / "status.json").exists() or (ARCHIVE / aid).exists():
        die(f"asset {aid} đã tồn tại")
    if d.exists():
        shutil.rmtree(d)
    rub_src = ROOT / "rubrics" / f"{typ}.md"
    if not rub_src.exists():
        rub_src = ROOT / "rubrics" / "default.md"
    d.mkdir(parents=True)
    src_note = (f"\nConcept đã duyệt: `{concept_dir}`\nThẻ asset: `{concept_dir / 'asset-card.yaml'}`\n"
                if concept_dir else "")
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
          "concept_dir": str(concept_dir) if concept_dir else None, "ad_ack": None}
    save_st(st)
    ledger(f"{aid} · tạo mới ({'todo' if ready else 'draft, rubric chưa duyệt'})")
    return st


def new(a, cfg: dict):
    st = create_asset(cfg, a.id, a.title, a.type, a.priority, a.deadline, None)
    print(f"OK {a.id} → {st['state']}. Viết yêu cầu vào {rel(ASSETS / a.id / 'brief.md')}"
          + ("" if st["state"] == "todo" else f"; rubric chưa duyệt, duyệt xong thì `ready {a.id}`"))


def load_profile() -> dict:
    if not PROFILE.exists():
        die(f"chưa có {rel(PROFILE)}: nạp skill zps-3dp-project-setup")
    errs = check_profile.check(PROFILE)
    if errs:
        die("profile sai:\n" + "\n".join(f"  {e}" for e in errs))
    return check_profile.load_yaml(PROFILE)


def group_errors(errs: dict[str, list[tuple[str, str]]]) -> list[str]:
    lines = []
    for group, label in ERROR_LABELS.items():
        items = [f"{aid} ({'; '.join(m for g, m in e if g == group)})" for aid, e in errs.items()
                 if any(g == group for g, _ in e)]
        if items:
            lines.append(f"{label} ({len(items)}): {', '.join(items)}")
    return lines


def scan_approved(cfg: dict, has_map: bool) -> dict:
    root = cfg["paths"]["approved"]
    if not root or not root.exists():
        die("chưa cấu hình [paths].approved trong pipeline.toml hoặc thư mục không tồn tại")
    known = {s["id"]: s for s in all_status()}
    archived = {p.name for p in ARCHIVE.glob("*")} if ARCHIVE.exists() else set()
    g = {"new": [], "bad_name": [], "loose": [], "changed": [], "registered": [], "errors": {}}
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
        elif errs := check_card.check(p, has_map):
            g["errors"][p.name] = errs
        else:
            g["new"].append(p.name)
    return g


def run(a, cfg: dict):
    prof = load_profile()
    root = cfg["paths"]["approved"]
    g = scan_approved(cfg, prof["has_map"])
    no_pilot = prof["pilot_asset"] is None
    if not a.ids and not a.all:
        labels = {"changed": "Concept đổi sau khi bắt đầu", "bad_name": "Tên thư mục sai quy ước",
                  "loose": "File rời", "registered": "Đã đăng ký"}
        lines = [f"Mới, đủ file ({len(g['new'])}): {', '.join(g['new'])}"] if g["new"] else []
        lines += group_errors(g["errors"])
        lines += [f"{lab} ({len(g[k])}): {', '.join(g[k])}" for k, lab in labels.items() if g[k]]
        if est := batch_line(len(g["new"]), bool((prof.get("paths") or {}).get("env_file"))):
            lines.append(est)
        if lines:
            print("\n".join(lines))
        print("Chưa có pilot (pilot_asset: null): đăng ký từng asset, `intake <id>`." if no_pilot else
              "Đăng ký: `intake --all` (nhóm 'Mới, đủ file') hoặc `intake <id> ... [--priority 1]`")
        return
    if no_pilot:
        if a.all or len(a.ids) > 1:
            die("pilot_asset: null, chưa có pilot: chỉ đăng ký từng asset gọi đích danh (`intake <id>`), không dùng --all hay nhiều id")
        busy = [s["id"] for s in all_status() if s["state"] not in FINISHED]
        if busy:
            die(f"pilot_asset: null, chưa có pilot: chưa đăng ký asset mới khi còn asset đang chạy: {', '.join(busy)}")
    if a.all:
        ids = g["new"]
        if g["errors"]:
            print("\n".join(group_errors(g["errors"])))
    else:
        ids = a.ids
        for aid in ids:
            if not (root / aid).is_dir():
                die(f"không có thư mục {root / aid}")
        bad = {aid: e for aid in ids if (e := check_card.check(root / aid, prof["has_map"]))}
        if bad:
            die("không đăng ký:\n" + "\n".join(group_errors(bad)))
    if not ids:
        print("Không có asset mới đủ file.")
        return
    created = [create_asset(cfg, aid, aid.replace("-", " ").title(),
                            check_profile.load_yaml(root / aid / check_card.CARD)["type"], a.priority, a.deadline,
                            root / aid) for aid in ids]
    print(f"Đã đăng ký {len(ids)}: {', '.join(ids)}.")
    print(batch_line(len(ids), bool((prof.get("paths") or {}).get("env_file"))))
    drafts = [st["id"] for st in created if st["state"] == "draft"]
    if drafts:
        print(f"Rubric chưa duyệt: {', '.join(drafts)} nằm ở draft. Người dùng duyệt xong thì `ready {' '.join(drafts)}`.")


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
