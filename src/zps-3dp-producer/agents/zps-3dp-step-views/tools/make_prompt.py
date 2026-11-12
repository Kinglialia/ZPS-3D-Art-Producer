"""Write the image prompt of one view: the fixed words of the kit with the data of the step filled in (row L7).

Usage: python3 tools/make_prompt.py --view front|back|left|right|top --ref <final with guides/ and bg_color.json>
           --concept <_approved/<id>> --sizes <V/work/sizes.json>
           [--hidden "<what this side looks like>"] [--fix "<line>" ...] --out <V/work/prompts/<view>-<k>.md>
Fills:
  materials   guides/views.json `materials` (code -> ID colour of the guide). Each entry is `<hex> <colour word> = <code>,
              <name>`; the colour word is the nearest of the 20 guide colours; the name is the `Tên` cell of the row with
              that code in <id>.material.md (the table whose header has `Mã` and `Tên`). A code without a row stops the run.
  background  bg_color.json `hex`.
  props       the separate shapes of the view's guide (guides/<view>_id.png) minus the main object, counted as the
              `components.<view>` check of measure.py counts them. None: no prop line. The component line of
              blockout.md ("4 pillars, 1 door, 3 barrels") does not say which items are separate, so it is not used.
  size        sizes.json (pick_size.py) for the view, printed in the one output line.
--hidden is the description of the hidden side, written in English; it is required for back, left, right and top and
refused for front. Each --fix adds one rule line at the end: the exact fault of a view that is made again.
The fixed words are the kit's, except `roof edge, fascia, base and plinth`, which holds only for a building: here
`top edge, base and ground contact`. Prints `[views/make_prompt] <out> <size>`. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import measure  # noqa: E402
import measure_views as mv  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "views/make_prompt"
VIEWS = ("front", "back", "left", "right", "top")
GUIDE_COLOURS = {
    "#E6194B": "red", "#3CB44B": "green", "#FFE119": "yellow", "#4363D8": "blue", "#F58231": "orange",
    "#911EB4": "purple", "#42D4F4": "cyan", "#BFEF45": "lime", "#FABED4": "pink", "#469990": "teal",
    "#DCBEFF": "lavender", "#9A6324": "brown", "#FFFAC8": "beige", "#800000": "maroon", "#AAFFC3": "mint",
    "#808000": "olive", "#FFD8B1": "apricot", "#000075": "navy", "#A9A9F5": "periwinkle", "#C46210": "rust"}

FRONT = """Repaint image 2 (a flat-coloured 3D guide render) as a finished game-asset illustration
in the exact art style, materials, colours and level of detail of the concept art in image 1.
Image 1: take the shapes and paint colours only; ignore its lighting and shadows.

STRICT RULES
- Orthographic FRONT view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 2.
  Do not add, remove, move, resize or rotate any part.
- Keep the top edge, base and ground contact at exactly the heights of image 2.
- Each flat colour in image 2 marks one material: {materials}.
  Paint each region with that material as it looks in the concept.
{props}- Plain, flat, solid background {bg}. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light. Keep material detail (grain, weave, finish) as painted colour variation.
- The whole object fully visible and centred. Do not crop. Do not stretch.
"""

SIDE = """Image 2 is the approved FRONT view of an object. Image 3 is a flat-coloured 3D guide render
of the {view} view of the SAME object.
Repaint image 3 so it looks like the same object as image 2, from the {view} side,
in the art style of the concept in image 1.

STRICT RULES
- Orthographic {view} view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 3.
  Do not add, remove, move, resize or rotate any part.
- Keep the top edge, base and ground contact at exactly the heights of image 3.
- Each flat colour in image 3 marks one material: {materials}.
  Every material must have the SAME colour, texture and wear as in image 2.
- What this side looks like: {hidden}.
{props}- Plain, flat, solid background {bg}. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light.
- The whole object fully visible and centred. Do not crop. Do not stretch.
"""


def colour_word(hex_):
    """The word of the nearest guide colour (RGB distance); the render palette is the only source of IDs."""
    rgb = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    near = min(GUIDE_COLOURS, key=lambda g: sum((a - b) ** 2 for a, b in zip(rgb(g), rgb(hex_.upper()))))
    return GUIDE_COLOURS[near]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cells(line):
    return [c.strip().strip("`*").strip() for c in line.strip().strip("|").split("|")]


def material_names(path):
    """{code: name} from the table of the Material Handoff whose header row has the columns `Mã` and `Tên`."""
    rows = [cells(l) for l in open(path, encoding="utf-8").read().splitlines() if l.lstrip().startswith("|")]
    for i, head in enumerate(rows):
        low = [c.lower() for c in head]
        if "mã" in low and "tên" in low:
            code, name = low.index("mã"), low.index("tên")
            return {r[code]: r[name] for r in rows[i + 1:] if len(r) > max(code, name) and not set("".join(r)) <= set("-: ")}
    raise ValueError(f"{path}: không thấy bảng có cột `Mã` và `Tên`")


def prop_count(path):
    mask = np.array(Image.open(path).convert("RGBA"))[..., 3] > 127
    frame = mv.to_frame(mask.astype(np.uint8) * 255, mv.bbox(mask), Image.NEAREST) > 127
    return max(0, measure.components(frame) - 1)


def prompt(a):
    materials = read_json(os.path.join(a.ref, "guides", "views.json"))["materials"]
    names = material_names(os.path.join(a.concept, f"{os.path.basename(os.path.normpath(a.concept))}.material.md"))
    missing = [c for c in materials if c not in names]
    if missing:
        raise ValueError(f"mã {', '.join(missing)} của guides/views.json không có dòng trong bảng của "
                         f"{os.path.basename(os.path.normpath(a.concept))}.material.md")
    image = "image 2" if a.view == "front" else "image 3"
    n = prop_count(os.path.join(a.ref, "guides", f"{a.view}_id.png"))
    text = (FRONT if a.view == "front" else SIDE).format(
        view=a.view.upper(), hidden=(a.hidden or "").strip().rstrip("."), bg=read_json(os.path.join(a.ref, "bg_color.json"))["hex"],
        materials="; ".join(f"{h} {colour_word(h)} = {c}, {names[c]}" for c, h in materials.items()),
        props=f"- {n} separate props, each where {image} shows it.\n" if n else "")
    return text + "".join(f"- {f.strip()}\n" for f in a.fix)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--view", required=True, choices=VIEWS)
    for k in ("--ref", "--concept", "--sizes", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--hidden")
    p.add_argument("--fix", action="append", default=[])
    a = p.parse_args()
    try:
        if (a.view == "front") == bool(a.hidden):
            raise ValueError("--hidden describes the hidden side: give it for back, left, right, top, not for front")
        text, size = prompt(a), read_json(a.sizes)[a.view]
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:  # noqa: BLE001
        print(f"[{TOOL}] error: {e}")
        sys.exit(2)
    print(f"[{TOOL}] {a.out} {size}")


if __name__ == "__main__":
    require_root()
    main()
