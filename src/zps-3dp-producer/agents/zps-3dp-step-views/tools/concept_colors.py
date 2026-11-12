"""Colour of each material on the concept albedo -> <final>/concept_colors.json, the kit format {"<material>": "#RRGGBB"}.

Usage: python3 tools/concept_colors.py --final <V/final> --concept <concept_albedo.png> --box <MATERIAL>=x0,y0,x1,y1 [...]
A box is a pixel rectangle inside one material area of the concept, away from edges, lines and painted light.
The colour is the median of the box pixels, per channel: the statistic measure.py takes for a material in a view, so the
same patch compared with itself gives dE 0 (D36.5). `median_hex` is the function other modules import.
MATERIAL is the code in guides/views.json (the `material` labels of the blockout).
Fails (exit 1, <final>/review/checks/concept_colors.json, no concept_colors.json) when
  - the main colour of a box covers under 60% of its pixels (within dE 12 of the median): the box holds two materials
    or a light, and the median is neither;
  - <final>/guides holds a front guide and a material that measure.py will measure on the front has no box.
Prints one line with the image size, so a box can be checked against it. Exit 0, 1 fail, 2 on error.
"""
import argparse
import contextlib
import io
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import common  # noqa: E402
import measure_views as mv  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "views/concept_colors"
ALPHA_MIN = 128
MAIN_SHARE_MIN = 0.6
MAIN_DE = mv.TH["delta_e"][1]
SAMPLE = 4000
MIN_REGION_PX = 40


def box_pixels(im, box):
    w, h = im.size
    if box[0] < 0 or box[1] < 0 or box[2] > w or box[3] > h:
        raise ValueError(f"box {box} ngoài ảnh {w}x{h}")
    a = np.asarray(im.convert("RGBA").crop(box)).reshape(-1, 4)
    px = a[a[:, 3] >= ALPHA_MIN][:, :3]
    if not len(px):
        raise ValueError(f"box {box} không có pixel đặc")
    return px


def median_hex(im, box):
    return mv.hexc(np.median(box_pixels(im, box), 0))


def main_share(im, box):
    px = box_pixels(im, box)
    med = np.median(px, 0)
    sample = px[::max(1, len(px) // SAMPLE)]
    return float(np.mean([mv.delta_e(p, med) <= MAIN_DE for p in sample]))


def missing_codes(final, boxed):
    guides = os.path.join(final, "guides")
    if not (os.path.isfile(os.path.join(guides, "views.json")) and os.path.isfile(os.path.join(guides, "front_id.png"))):
        return None
    names = list(common.read_json(os.path.join(guides, "views.json"))["materials"])
    palette = np.array([mv.hex_rgb(h) for h in common.read_json(os.path.join(guides, "views.json"))["materials"].values()])
    label = mv.load_blockout(guides, "front", palette)["label"]
    shown = [n for k, n in enumerate(names) if mv.erode(label == k, 3).sum() >= MIN_REGION_PX]
    return [n for n in shown if n not in boxed]


def parse_box(s):
    name, _, nums = s.partition("=")
    box = tuple(int(x) for x in nums.split(","))
    if not name or len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"--box {s}: cần MATERIAL=x0,y0,x1,y1 với x0<x1, y0<y1")
    return name, box


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--concept", required=True)
    p.add_argument("--box", action="append", required=True)
    a = p.parse_args()
    out, check_path = os.path.join(a.final, "concept_colors.json"), os.path.join(a.final, "review", "checks", "concept_colors.json")
    try:
        boxes = [parse_box(b) for b in a.box]
        with Image.open(a.concept) as im:
            im.load()
            colours = {name: median_hex(im, box) for name, box in boxes}
            shares = {name: main_share(im, box) for name, box in boxes}
        missing = missing_codes(a.final, {n for n, _ in boxes})
        checks = [common.check(f"colors.{n}", "pass" if shares[n] >= MAIN_SHARE_MIN else "fail",
                               value={"hex": colours[n], "main_share": round(shares[n], 2)}, threshold={"main_share": MAIN_SHARE_MIN},
                               note=None if shares[n] >= MAIN_SHARE_MIN else "box có hai vật liệu hoặc ánh sáng: chọn ô khác")
                  for n, _ in boxes]
        checks.append(common.check("colors.codes", "not_checked" if missing is None else "fail" if missing else "pass",
                                   value=missing, note="không có guides/front_id.png" if missing is None else
                                   "mã có trên guide front mà chưa có --box" if missing else None))
        with contextlib.redirect_stdout(io.StringIO()):
            res = common.write_result(check_path, TOOL, checks)
    except Exception as e:  # noqa: BLE001
        print(f"[views/concept_colors] error {e!r}")
        sys.exit(2)
    if res["overall"] == "fail":
        bad = [c["check"] for c in checks if c["status"] == "fail"]
        print(f"[views/concept_colors] fail: {', '.join(bad)} -> {check_path}")
        sys.exit(1)
    os.makedirs(a.final, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(colours, f, indent=1)
    print(f"[views/concept_colors] {im.width}x{im.height} {', '.join(f'{k}={v}' for k, v in colours.items())} -> {out}")


if __name__ == "__main__":
    require_root()
    main()
