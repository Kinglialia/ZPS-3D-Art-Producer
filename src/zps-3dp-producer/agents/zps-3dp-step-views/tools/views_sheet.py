"""Review sheet of the view set, crops, and the mirrored side view (concept-views.md §7, §3).

  python3 tools/views_sheet.py make --final <V/final> --concept <concept_albedo.png> --front <front.png>
          [--kept back,left] [--crop <view>:x0,y0,x1,y1 ...]
      Row 1: concept, front, back, left, right, top; --kept views (copied from the prior approved set) are labelled
      "(giữ)". Row 2: report/overlay_<view>.png with score, IoU, dE from
      report/report.json. Row 3: the crops, in pixels of the view image. Writes <final>/report/VIEWS_sheet.png and
      VIEWS_sheet.json (sha256 of the 5 view files, which check_package.py compares).
  python3 tools/views_sheet.py crop --image <png> --box x0,y0,x1,y1 --out <png> [--scale 2]
  python3 tools/views_sheet.py flip --src <left.png> --out <right.png>    right = left mirrored (symmetric left_right)
Prints one line. Exit 0, 2 on error.
"""
import argparse
import hashlib
import json
import os
import sys

from PIL import Image, ImageDraw, ImageOps

VIEWS = ("front", "back", "left", "right", "top")
CELL, PAD, HEAD = 320, 12, 22


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def box(s):
    b = tuple(int(x) for x in s.split(","))
    if len(b) != 4 or b[0] >= b[2] or b[1] >= b[3]:
        raise ValueError(f"box {s}: cần x0,y0,x1,y1 với x0<x1, y0<y1")
    return b


def cell(im):
    im = im.convert("RGBA")
    im.thumbnail((CELL, CELL))
    c = Image.new("RGB", (CELL, CELL), "white")
    c.paste(im, ((CELL - im.width) // 2, (CELL - im.height) // 2), im)
    return c


def label(r):
    if not r or "score" not in r:
        return "không đo"
    de = f" dE {r['max_delta_e']:.1f}" if r.get("max_delta_e") is not None else ""
    return f"{r['score']}/100 IoU {r['iou']:.2f}{de}"


def make(a):
    paths = {v: a.front if v == "front" else os.path.join(a.final, f"{v}.png") for v in VIEWS}
    rdir = os.path.join(a.final, "report")
    rep = json.load(open(os.path.join(rdir, "report.json"), encoding="utf-8"))
    kept = set((a.kept or "").split(","))
    rows = [[("concept", Image.open(a.concept))] + [(v + " (giữ)" * (v in kept), Image.open(paths[v])) for v in VIEWS],
            [(f"{v} {label(rep['views'].get(v))}", Image.open(os.path.join(rdir, f"overlay_{v}.png")))
             for v in VIEWS if os.path.isfile(os.path.join(rdir, f"overlay_{v}.png"))]]
    crops = [c.split(":", 1) for c in a.crop or []]
    if crops:
        rows.append([(f"{v} {b}", Image.open(paths[v]).crop(box(b))) for v, b in crops])
    w = PAD + max(len(r) for r in rows) * (CELL + PAD)
    sheet = Image.new("RGB", (w, PAD + len(rows) * (HEAD + CELL + PAD)), "white")
    d = ImageDraw.Draw(sheet)
    for i, row in enumerate(rows):
        y = PAD + i * (HEAD + CELL + PAD)
        for j, (text, im) in enumerate(row):
            x = PAD + j * (CELL + PAD)
            d.text((x, y), text, fill="black")
            sheet.paste(cell(im), (x, y + HEAD))
    out = os.path.join(rdir, "VIEWS_sheet.png")
    sheet.save(out)
    with open(os.path.join(rdir, "VIEWS_sheet.json"), "w", encoding="utf-8") as f:
        json.dump({"inputs": {v: sha(p) for v, p in paths.items()}}, f, indent=1)
    return f"{len(rows)} hàng {sheet.width}x{sheet.height} -> {out}"


def crop(a):
    im = Image.open(a.image).crop(box(a.box))
    im = im.resize((im.width * a.scale, im.height * a.scale), Image.NEAREST)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    im.save(a.out)
    return f"crop {im.width}x{im.height} -> {a.out}"


def flip(a):
    ImageOps.mirror(Image.open(a.src)).save(a.out)
    return f"flip {a.src} -> {a.out}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--final", required=True)
    m.add_argument("--concept", required=True)
    m.add_argument("--front", required=True)
    m.add_argument("--crop", action="append")
    m.add_argument("--kept")
    c = sub.add_parser("crop")
    c.add_argument("--image", required=True)
    c.add_argument("--box", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--scale", type=int, default=2)
    f = sub.add_parser("flip")
    f.add_argument("--src", required=True)
    f.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        msg = {"make": make, "crop": crop, "flip": flip}[a.cmd](a)
    except Exception as e:  # noqa: BLE001
        print(f"[views/views_sheet] error {e!r}")
        sys.exit(2)
    print(f"[views/views_sheet] {msg}")


if __name__ == "__main__":
    main()
