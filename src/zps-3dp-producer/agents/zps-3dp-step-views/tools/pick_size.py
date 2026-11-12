"""Image size for each view -> a JSON {"<view>": "WxH"}, from bbox_size_m of guides/views.json (D36 V9).

Usage: python3 tools/pick_size.py --guides <V/final/guides> --out <V/work/sizes.json>
The size is the --size of gen_image_codex.py. A view that shows an object wider than tall gets 1536x1024; a taller one
gets 1024x1536; equal gets 1536x1024. front and back show width x height, left and right depth x height, top and bottom
width x depth. The long side stays over 1040 px. Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

SHOWS = {"front": ("width_x", "height_z"), "back": ("width_x", "height_z"), "left": ("depth_y", "height_z"),
         "right": ("depth_y", "height_z"), "top": ("width_x", "depth_y"), "bottom": ("width_x", "depth_y")}
WIDE, TALL = "1536x1024", "1024x1536"


def sizes(box):
    return {v: WIDE if box[w] >= box[h] else TALL for v, (w, h) in SHOWS.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--guides", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        with open(os.path.join(a.guides, "views.json"), encoding="utf-8") as f:
            r = sizes(json.load(f)["bbox_size_m"])
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1)
    except Exception as e:  # noqa: BLE001
        print(f"[views/pick_size] error {e!r}")
        sys.exit(2)
    print(f"[views/pick_size] {' '.join(f'{v}={s}' for v, s in r.items())} -> {a.out}")


if __name__ == "__main__":
    require_root()
    main()
