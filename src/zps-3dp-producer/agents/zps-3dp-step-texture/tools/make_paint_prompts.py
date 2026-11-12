"""Write the prompt of every VẼ MỚI paint view from one template (row L12), so the model writes only a --fix line.

Usage: python3 T/make_paint_prompts.py --views V/work/paint --concept C --concept-colors CC
           [--view-set VS] [--batch] [--k <k> ...] [--fix "<line>" ...] --out V/work/prompts
Fills, per view of <views>/cameras.json (render_paint_views.py):
  camera     azimuth and elevation of the view.
  materials  concept_colors.json {code: hex}: the base fill paints each code in that colour, so the guide shows it.
             The name is the `Tên` cell of the code's row in the table of C/<id>.material.md whose header has `Mã` and
             `Tên`; a code without a row is named by its code only.
  notes      `real_texture_only_notes` of C/asset-card.yaml and the TEXTURE NOTE section of VS/README.md (the approved
             view set; --views is the folder of the paint views).
  background the first of BACKGROUNDS farthest (RGB) from every concept colour, so project_views.py can key it.
  image      the number of the view's guide in the gen call: 2 when each job gets the concept and its own guide;
             with --batch every image goes to one call (the concept, then the guides in the order written), so the
             i-th prompt names image i + 2.
--k writes only those views (a new gen of the views project_views.py names). Each --fix adds one rule line to every
prompt written: the fault of a view made again. Writes <out>/paint_<k>.md. Prints one line with the --size of the
guides. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import texture_complexity  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "texture/make_paint_prompts"
BACKGROUNDS = ("#E8E8E8", "#2B2B2B", "#3A5FCD", "#2E8B57", "#C71585", "#FF8C00")

PAINT = """Repaint image {image} (a flat-coloured 3D render of a game asset) with the finished surface colours of that asset,
in the exact art style, materials, colours and level of detail of the concept art in image 1.
Image 1: take the paint colours and material detail only; ignore its lighting, shadows and camera.

STRICT RULES
- Orthographic view from azimuth {az} degrees, {el} degrees {side}: the camera of image {image}. No perspective.
- Keep EXACTLY the silhouette, size and position of image {image}, pixel for pixel.
  Do not move, scale, rotate or crop the object. Do not add or remove any part.
- Each flat colour in image {image} marks one material: {materials}.
  Paint each region with that material as it looks in the concept. Keep every border between materials where image {image} has it.
{notes}- Unlit base colour only: even light, no shading, no cast or contact shadow, no highlight, no dark ambient-occlusion corners.
  Keep material detail (grain, weave, wear) as painted colour variation.
- Plain, flat, solid background {bg}. No ground, no vignette, no text, no labels, no border.
"""


def cells(line):
    return [c.strip().strip("`*").strip() for c in line.strip().strip("|").split("|")]


def material_names(path):
    """{code: name} from the table whose header row has `Mã` and `Tên` (same reading as views make_prompt.py)."""
    if not os.path.isfile(path):
        return {}
    rows = [cells(line) for line in open(path, encoding="utf-8").read().splitlines() if line.lstrip().startswith("|")]
    for i, head in enumerate(rows):
        low = [c.lower() for c in head]
        if "mã" in low and "tên" in low:
            code, name = low.index("mã"), low.index("tên")
            return {r[code]: r[name] for r in rows[i + 1:] if len(r) > max(code, name) and not set("".join(r)) <= set("-: ")}
    return {}


def background(colours):
    rgb = lambda h: [int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    far = lambda b: min(sum((x - y) ** 2 for x, y in zip(rgb(b), rgb(c))) for c in colours) if colours else 0
    return max(BACKGROUNDS, key=far)


def notes(concept, view_set):
    import yaml
    card_path = os.path.join(concept, "asset-card.yaml")
    card = (yaml.safe_load(open(card_path, encoding="utf-8")) or {}) if os.path.isfile(card_path) else {}
    lines = [str(x) for x in card.get("real_texture_only_notes") or []]
    if view_set:
        lines += texture_complexity.section(os.path.join(view_set, "README.md"), "TEXTURE NOTE")
    return [n for n in lines if n.lower().strip(" .") not in ("không có", "none")]


def prompts(a):
    views = json.load(open(os.path.join(a.views, "cameras.json"), encoding="utf-8"))["views"]
    pick = [v for v in views if not a.k or v["k"] in a.k]
    missing = sorted(set(a.k or []) - {v["k"] for v in views})
    if missing:
        raise ValueError(f"cameras.json không có view {', '.join(map(str, missing))}")
    colours = json.load(open(a.concept_colors, encoding="utf-8"))
    names = material_names(os.path.join(a.concept, f"{os.path.basename(os.path.normpath(a.concept))}.material.md"))
    materials = "; ".join(f"{h} = {c}, {names[c]}" if c in names else f"{h} = {c}" for c, h in colours.items())
    note = notes(a.concept, a.view_set)
    bg = background(list(colours.values()))
    out = {}
    for i, v in enumerate(pick):
        image = i + 2 if a.batch else 2
        lines = "".join(f"- Texture note, paint it where image {image} shows its place: {n}\n" for n in note)
        out[v["k"]] = PAINT.format(image=image, az=v["azimuth_deg"], el=abs(v["elevation_deg"]),
                                   side="above" if v["elevation_deg"] >= 0 else "below", materials=materials,
                                   notes=lines, bg=bg) + "".join(f"- {f.strip()}\n" for f in a.fix)
    cam = pick[0]["camera"]
    return out, f"{cam['w']}x{cam['h']}", bg


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--views", "--concept", "--concept-colors", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--view-set")
    p.add_argument("--batch", action="store_true")
    p.add_argument("--k", type=int, action="append")
    p.add_argument("--fix", action="append", default=[])
    a = p.parse_args()
    try:
        texts, size, bg = prompts(a)
        os.makedirs(a.out, exist_ok=True)
        for k, text in texts.items():
            with open(os.path.join(a.out, f"paint_{k}.md"), "w", encoding="utf-8") as f:
                f.write(text)
    except Exception as e:  # noqa: BLE001
        print(f"[{TOOL}] error: {e}")
        sys.exit(2)
    print(f"[{TOOL}] {len(texts)} prompt paint_{{{','.join(map(str, texts))}}}.md -> {a.out}, --size {size}, nền {bg}")


if __name__ == "__main__":
    require_root()
    main()
