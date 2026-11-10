"""The view set of views_rest is complete (concept-views.md §6). Pure Python + Pillow + PyYAML.

Usage: python3 tools/check_package.py --final <V/final> --front <views_front final>/front.png --card <asset-card.yaml>
  package.views   front (--front) and the side views of the card's `views` exist (D32: back; full: back, left, right;
                  full_top: and top; no field = full)
  package.sheet   report/VIEWS_sheet.json holds the sha256 of exactly these files (the sheet shows what ships)
  package.readme  README.md line 1 is the fixed pointer line; the 4 sections exist in order, none empty
  package.flip    "Lật ảnh" says `right = left lật ngang` when the card has symmetric.left_right: true and the set
                  has left and right, and then right.png is left.png mirrored, pixel for pixel
Writes <final>/review/checks/package.json. Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from views_sheet import card_set  # noqa: E402

TOOL = "views/check_package"
POINTER = ("Thông số, mốc chiều cao, phần khuất, Blockout tự quyết, ghi chú real/texture_only: xem `blockout.md` "
           "của blockout đã duyệt. Không chiếu hay bake màu từ ảnh view lên model; màu lấy từ albedo.")
SECTIONS = ("NGOẠI LỆ", "TEXTURE NOTE", "Lật ảnh", "Trạng thái duyệt")
FLIP = "right = left lật ngang"


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def readme(path):
    if not os.path.isfile(path):
        return ["không có README.md"], {}
    lines = open(path, encoding="utf-8").read().splitlines()
    first = next((l.strip() for l in lines if l.strip()), "")
    errs = [] if first == POINTER else ["dòng đầu phải là dòng trỏ sang blockout.md"]
    body, cur = {}, None
    for l in lines:
        m = re.match(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$", l)
        if m:
            cur = m.group(1)
            body[cur] = []
        elif cur and l.strip():
            body[cur].append(l.strip())
    got = [s for s in body if s in SECTIONS]
    if got != list(SECTIONS):
        errs.append("cần đủ 4 mục theo thứ tự: " + ", ".join(SECTIONS))
    errs += [f"mục {s} trống (ghi 'không có')" for s in SECTIONS if s in body and not body[s]]
    return errs, body


def run(a):
    views = card_set(a.card)
    paths = {v: a.front if v == "front" else os.path.join(a.final, f"{v}.png") for v in views}
    miss = [v for v, p in paths.items() if not os.path.isfile(p)]
    out = [common.check("package.views", "fail" if miss else "pass", value=miss)]
    side = os.path.join(a.final, "report", "VIEWS_sheet.json")
    rec = (common.read_json(side).get("inputs") or {}) if os.path.isfile(side) else {}
    stale = [v for v, p in paths.items() if v not in miss and rec.get(v) != sha(p)]
    out.append(common.check("package.sheet", "fail" if miss or stale or set(rec) != set(views) else "pass",
                            value=stale, note="dựng lại sheet bằng views_sheet.py make" if stale else None))
    errs, body = readme(os.path.join(a.final, "README.md"))
    out.append(common.check("package.readme", "fail" if errs else "pass", value=errs))
    import yaml
    with open(a.card, encoding="utf-8") as f:
        sym = bool(((yaml.safe_load(f) or {}).get("symmetric") or {}).get("left_right"))
    said = any(FLIP in l for l in body.get("Lật ảnh", []))
    pair = {"left", "right"} <= set(views)
    flip_errs = [f"thẻ có symmetric.left_right: true, mục Lật ảnh cần `{FLIP}`"] if sym and pair and not said else []
    if said and pair and not {"left", "right"} & set(miss):
        from PIL import Image, ImageOps
        l, r = (Image.open(paths[v]).convert("RGBA") for v in ("left", "right"))
        if l.size != r.size or ImageOps.mirror(l).tobytes() != r.tobytes():
            flip_errs.append("right.png không phải left.png lật ngang")
    out.append(common.check("package.flip", "fail" if flip_errs else "pass", value=flip_errs))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--front", required=True)
    p.add_argument("--card", required=True)
    a = p.parse_args()
    out = os.path.join(a.final, "review", "checks", "package.json")
    try:
        checks = run(a)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(2)
    sys.exit(1 if common.write_result(out, TOOL, checks)["overall"] == "fail" else 0)


if __name__ == "__main__":
    main()
