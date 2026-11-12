"""The critic renders of the kit's render_views.py, with a legend the reviewer can read.

Usage: blender -b --python tools/render_critic.py -- <arguments of self_build/render_views.py>
The kit draws the legend of parts_<view>.png (build number = part name) in white on a light grey margin, so the words
cannot be read. This script lets the kit draw the part numbers, then redraws the margin with dark words. Everything else
is the kit's run: same options, same files, same renders.json.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "self_build"))
sys.path.insert(0, os.path.join(HERE, "lib"))
import bootstrap  # noqa: E402,F401
import render_views as RV  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

KIT_LABEL = RV.label_parts


def label_parts(png, parts_colors, legend, max_edge):
    """Part numbers as the kit draws them; legend (n name, hidden marked) in black on the margin, long edge <= max_edge."""
    from PIL import Image, ImageDraw
    w = Image.open(png).size[0]
    visible = KIT_LABEL(png, parts_colors, [], 10 ** 9)
    img = Image.open(png).convert("RGB")
    fs = max(14, w // 40)
    line = fs + 10
    out = Image.new("RGB", (img.width, max(img.height, line * (len(legend) + 2))), (RV.BG_SRGB,) * 3)
    out.paste(img.crop((0, 0, w, img.height)), (0, 0))
    d = ImageDraw.Draw(out)
    d.text((w + 12, 8), "parts (n = build order)", fill=(0, 0, 0), font=RV.font(int(fs * 0.8)))
    for k, (idx, name, rgb) in enumerate(legend):
        y = 8 + line * (k + 1)
        d.rectangle([w + 12, y, w + 12 + fs, y + fs], fill=tuple(int(c * 255) for c in rgb), outline=(0, 0, 0))
        hidden = "" if idx in visible else "  (hidden)"
        d.text((w + 20 + fs, y), f"{idx} {name}{hidden}", fill=(0, 0, 0), font=RV.font(int(fs * 0.8)))
    RV.fit_long_edge(out, max_edge).save(png)
    return visible


RV.label_parts = label_parts

if __name__ == "__main__":
    require_root()
    RV.main()
