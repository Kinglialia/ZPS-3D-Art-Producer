"""Project init, asset creation, `_approved/` intake scan, `ready`."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

from PIL import Image

import check_card
import check_profile

from .estimate import batch_line
from .hashes import warnings_for
from .state import (ARCHIVE, ASSETS, FINISHED, ROOT, SKILL_DIR, TEMPLATES, agent_name, all_status, die, ledger, load_st,
                    now, rel, rubric_approved, save_st)

SCRIPTS = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "PROJECT-PROFILE.yaml"
ERROR_LABELS = {"files": "Thiếu file", "type": "Loại chưa hỗ trợ v1", "card": "Thẻ sai"}

COLORS_FILE = "concept_colors.json"
BOX_HEADER, HEX_HEADER, CODE_HEADER = "ô lấy màu", "hex", "mã"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
BG_LINE = re.compile(r"^[\s>*_-]*BG:\s*(#[0-9A-Fa-f]{6})\b", re.M)
BORDER_PX = 4

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


_colors_mod = None


def colors_tool():
    """concept_colors.py of the views step, loaded by path under a private name: it puts its tools folder on
    sys.path and binds `common` and `measure_views`, names other tool folders use for other modules. The median that
    intake takes is the one the views tool takes (D43.1)."""
    global _colors_mod
    if _colors_mod is None:
        tools = SKILL_DIR / "agents" / agent_name("step-views") / "tools"
        names = ("common", "measure_views")
        saved_path, saved_mods = list(sys.path), {n: sys.modules.pop(n, None) for n in names}
        try:
            spec = importlib.util.spec_from_file_location("_zps_views_concept_colors", tools / "concept_colors.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path[:] = saved_path
            for n in names:
                sys.modules.pop(n, None)
                if saved_mods[n] is not None:
                    sys.modules[n] = saved_mods[n]
        _colors_mod = mod
    return _colors_mod


def handoff_rows(text: str) -> tuple[list[str] | None, list[dict[str, str]]]:
    """The Material Handoff table by its header row: (headers, rows keyed by header), headers lower case; (None, [])
    when no table has a `Mã` column."""
    cells = lambda line: [unicodedata.normalize("NFC", c.strip()) for c in line.strip().strip("|").split("|")]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        head = [c.lower() for c in cells(line)] if line.lstrip().startswith("|") else []
        if CODE_HEADER not in head:
            continue
        rows = []
        for l in lines[i + 1:]:
            if not l.lstrip().startswith("|"):
                break
            row = cells(l)
            if not set("".join(row)) <= set("-: "):
                rows.append(dict(zip(head, row)))
        return head, rows
    return None, []


def measure_handoff(aid: str, d: Path, dest: Path) -> list[str]:
    """D43.1: median colour of the box of each material code in `<id>.material.md`, written to dest in the format of
    the views tool's concept_colors.json. Returns the warning lines."""
    warn = lambda m: f"cảnh báo: {aid}: {m}"
    text = (d / f"{aid}.material.md").read_text(encoding="utf-8", errors="replace")
    head, rows = handoff_rows(text)
    box_col = next((h for h in head or [] if BOX_HEADER in h), None)
    if box_col is None:
        return [warn('Material Handoff không có cột "Ô lấy màu": không ghi concept_colors.json, worker tự chọn ô')]
    hex_col = next((h for h in head if HEX_HEADER in h), None)
    cc = colors_tool()
    out, found = [], {}
    with Image.open(d / "concept_albedo.png") as im:
        im.load()
        w, h = im.size
        for row in rows:
            code, cell = row.get(CODE_HEADER, ""), row.get(box_col, "")
            if not code:
                continue
            if not cell:
                out.append(warn(f"{code}: không có ô lấy màu"))
                continue
            nums = re.findall(r"-?\d+", cell)
            if len(nums) != 4 or int(nums[2]) <= 0 or int(nums[3]) <= 0:
                out.append(warn(f'{code}: ô lấy màu "{cell}" sai, cần x, y, w, h'))
                continue
            x, y, bw, bh = map(int, nums)
            if x < 0 or y < 0 or x + bw > w or y + bh > h:
                out.append(warn(f"{code}: ô {x}, {y}, {bw}, {bh} nằm ngoài ảnh {w}x{h}"))
                continue
            try:
                found[code] = cc.median_hex(im, (x, y, x + bw, y + bh))
            except ValueError:
                out.append(warn(f"{code}: ô {x}, {y}, {bw}, {bh} không có pixel đặc"))
                continue
            written = HEX.search(row.get(hex_col, "")) if hex_col else None
            de = cc.mv.delta_e(cc.mv.hex_rgb(written[0]), cc.mv.hex_rgb(found[code])) if written else 0
            if de > cc.mv.TH["delta_e"][0]:
                out.append(warn(f"{code}: hex {written[0].upper()} lệch màu đo {found[code]} (dE {de:.1f} > 6)"))
        if bg := BG_LINE.search(text):
            try:
                edge = cc.median_hex(im, (0, 0, w, min(h, BORDER_PX)))
            except ValueError:
                edge = None
            de = cc.mv.delta_e(cc.mv.hex_rgb(bg[1]), cc.mv.hex_rgb(edge)) if edge else 0
            if de > cc.mv.TH["delta_e"][0]:
                out.append(warn(f"BG {bg[1].upper()} lệch màu nền đo ở viền ảnh {edge} (dE {de:.1f} > 6)"))
    if found:
        dest.write_text(json.dumps(found, indent=1), encoding="utf-8")
    return out


def empty_counts_warning(aid: str, d: Path, prof: dict) -> list[str]:
    """C18: a card with `counts: {}` in a project that names count keys may have left out a count."""
    keys = prof.get("counts_keys")
    card = check_profile.load_yaml(d / check_card.CARD)
    if keys and isinstance(card, dict) and card.get("counts") == {}:
        return [f"cảnh báo: {aid}: thẻ có counts rỗng mà profile có counts_keys ({', '.join(keys)}): ghi số đếm, "
                "hoặc để {} nếu asset không có thành phần lặp lại"]
    return []


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
    for aid in ids:
        for line in measure_handoff(aid, root / aid, ASSETS / aid / COLORS_FILE) + empty_counts_warning(aid, root / aid, prof):
            print(line)
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
