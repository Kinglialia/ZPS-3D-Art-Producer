"""Colour of each material on the concept albedo -> <final>/concept_colors.json, the kit format {"<material>": "#RRGGBB"}.

Usage: python3 tools/concept_colors.py --final <V/final> --concept <concept_albedo.png> --box <MATERIAL>=x0,y0,x1,y1 [...]
A box is a pixel rectangle inside one material area of the concept, away from edges, lines and painted light.
The colour is the `vivid` colour of the largest palette_report cluster in the box (the paint the artist used).
MATERIAL is the code in guides/views.json (the `material` labels of the blockout). Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys
import tempfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette_report  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402


def colours(concept, boxes):
    out = {}
    im = Image.open(concept).convert("RGBA")
    with tempfile.TemporaryDirectory() as d:
        for name, box in boxes:
            p = os.path.join(d, "crop.png")
            im.crop(box).save(p)
            out[name] = palette_report.report(p, n_colors=4)["dominant"][0]["vivid"]["hex"].upper()
    return out


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
    out = os.path.join(a.final, "concept_colors.json")
    try:
        r = colours(a.concept, [parse_box(b) for b in a.box])
    except Exception as e:  # noqa: BLE001
        print(f"[views/concept_colors] error {e!r}")
        sys.exit(2)
    os.makedirs(a.final, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    print(f"[views/concept_colors] {', '.join(f'{k}={v}' for k, v in r.items())} -> {out}")


if __name__ == "__main__":
    require_root()
    main()
