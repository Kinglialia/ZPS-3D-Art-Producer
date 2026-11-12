"""Write the routine parts of <w>/blockout.md from the JSON files and keep the rest. Plain Python.

Usage: PY T/blockout_md.py --work <w> [--out <blockout.md>]
Writes line 3 (item 2: the bbox against the layout), section 3 (version and hashes) and section 8 (mesh errors of the
union). Reads part_graph.json, sources.json, assembly.json and parts_lib.py. It stops when assembly.json is not built
from this part_graph.json, because the numbers would belong to another graph.
Every other line stays as it is. A missing file starts from the skeleton of references/part-graph.md (`blockout.md`):
line 1 is `# Blockout <id> v<N>` (from the vN folder), line 2 is item 1, line 3 is item 2, then `## 3.` to `## 10.`.
The sections the worker writes start as `TODO: ...`. Re-run the tool after the worker writes them: while a TODO is left, it
prints the section numbers and exits 1. Re-running it on its own output changes nothing but the three generated places.
Prints one line. Exit 0 done, 1 TODO left, 2 error.
"""
import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import common  # noqa: E402
from check_layout import bbox_check, load_build  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "[blockout/blockout_md]"
TODO = {1: "TODO: thành phần đếm trên concept, một dòng",
        4: "TODO: bảng đo (param, giá trị, nguồn, cách đo)",
        5: "TODO: ghi chú real/texture_only, chép nguyên từ concept",
        6: "TODO: từng chỗ phần khuất hoặc kích thước mà mô tả không có, kèm lý do",
        7: "TODO: mâu thuẫn giữa các nguồn và lựa chọn (hoặc `Không có.`)"}
TITLES = {3: "Version và hash", 4: "Bảng đo", 5: "Ghi chú real/texture_only", 6: "Blockout tự quyết",
          7: "Mâu thuẫn giữa các nguồn", 8: "Lỗi mesh còn lại", 9: "Thay đổi so với version trước",
          10: "Trạng thái duyệt"}
HEADING = re.compile(r"^#{2,}\s*(\d+)[.)]?\s")
TODO_WORD = re.compile(r"\bTODO\b")


def mm(values):
    return " × ".join(f"{x:g}" for x in values)


def version_folder(work):
    """(id, 'vN') of the version folder that holds the graph, or (None, None)."""
    d = os.path.abspath(work)
    while os.path.dirname(d) != d:
        if re.fullmatch(r"v\d+", os.path.basename(d)):
            return os.path.basename(os.path.dirname(os.path.dirname(d))), os.path.basename(d)
        d = os.path.dirname(d)
    return None, None


def item2(graph, rows, sources):
    check, data = bbox_check(graph, rows, sources)
    layout = sources["layout"]
    base = "" if layout.get("includes_base", True) else " (không tính nền)"
    verdict = "đạt" if check["status"] == "pass" else "không đạt"
    return (f"Bbox dựng {mm(data['built'])} m{base} so với {layout.get('source', 'layout')} {mm(data['want'])} m: "
            f"lệch tối đa {max(data['deviation']) * 100:.1f} % (ngưỡng {check['threshold'] * 100:g} %), {verdict}.")


def section3(work, graph, asm):
    lines = [f"- Version: {graph.get('version', '?')}"]
    for name in ("part_graph.json", "parts_lib.py"):
        lines.append(f"- {name}: sha256 {common.file_sha256(os.path.join(work, name)) or 'không có file'}")
    lines.append(f"- Hash gộp part_graph.json + parts_lib.py: {asm['data'].get('code_hash')}")
    return lines


def section8(asm):
    union = asm["data"].get("union") or {}
    h = union.get("health") or {}
    return [f"- non-manifold: {h.get('non_manifold_edges', '?')}. zero-area: {h.get('zero_area_faces', '?')}. "
            f"đỉnh rời: {h.get('loose_verts', '?')}.", f"- Hợp nhất: {union.get('method', '?')}."]


def split(text):
    """(head lines before the first numbered heading, {number: [heading, *body]}, order of the numbers)."""
    head, sections, order, cur = [], {}, [], None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            cur = int(m.group(1))
            sections[cur] = [line]
            order.append(cur)
        elif cur is None:
            head.append(line)
        else:
            sections[cur].append(line)
    return head, sections, order


def skeleton(work, graph):
    aid, vn = version_folder(work)
    title = f"# Blockout {aid} {vn}" if aid else "# Blockout <id> v<N>"
    first = int(vn[1:]) == 1 if vn else False
    body = {n: [f"## {n}. {t}", TODO.get(n) or ""] for n, t in TITLES.items()}
    body[9][1] = "Không có (version đầu)." if first else "TODO: part nào, param nào đổi, vì sao"
    body[10][1] = f"Chờ duyệt, {datetime.date.today().isoformat()}."
    return [title, TODO[1], ""], body


def render(work, text):
    graph, rows, sources, fresh = load_build(work)
    if fresh["status"] != "pass":
        raise ValueError(fresh["note"])
    asm = common.read_json(os.path.join(work, "assembly.json"))
    new_head, new_sections = skeleton(work, graph)
    head, sections, _ = split(text) if text else (new_head, {}, [])
    sections = {**new_sections, **sections}
    lines = [x for x in head if x.strip()] or new_head[:2]
    lines = lines[:1] + (lines[1:2] or [new_head[1]]) + [item2(graph, rows, sources)] + lines[3:]
    sections[3] = [sections[3][0], *section3(work, graph, asm)]
    sections[8] = [sections[8][0], *section8(asm)]
    out = [*lines, ""]
    for n in sorted(sections):
        body = sections[n]
        while body and not body[-1].strip():
            body = body[:-1]
        out += [*body, ""]
    return "\n".join(out).rstrip() + "\n"


def todo_sections(text):
    head, sections, _ = split(text)
    left = [n for n, body in sorted(sections.items()) if any(TODO_WORD.search(x) for x in body)]
    return ([0] if any(TODO_WORD.search(x) for x in head) else []) + left


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or os.path.join(a.work, "blockout.md")
    try:
        old = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
        text = render(a.work, old)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:  # noqa: BLE001
        print(f"{NAME} error {e!r}")
        sys.exit(2)
    left = todo_sections(text)
    if left:
        names = (["dòng 2"] if 0 in left else []) + ([f"mục {', '.join(str(n) for n in left if n)}"] if any(left) else [])
        print(f"{NAME} {out}: còn TODO ở {', '.join(names)}")
        sys.exit(1)
    print(f"{NAME} {out}: đủ mục")


if __name__ == "__main__":
    require_root()
    main()
