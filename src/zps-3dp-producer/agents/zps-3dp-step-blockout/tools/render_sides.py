"""Side views of the blockout, each part in one flat colour per material code, for the owner at the blockout gate (D44.1).

Usage: blender -b --python tools/render_sides.py -- --work <dir> [--outdir <dir>/review] [--size 1024] [--top]
Reads <dir>/assembled.glb, part_graph.json (material of each part) and assembly.json (the part files).
  mat_left.png, mat_right.png, mat_back.png   and mat_top.png with --top (the card says views: full_top)
Cameras are the ones of render_views.py (VIEW_DIRS, same framing). Flat light, no outline, no anti-aliasing: a part is one
colour all over, so a code reads as one colour. The colour of a code is a hue taken from the sha256 of the code, at fixed
saturation and value. When two codes of the asset land less than a tenth of the hue circle apart, the later code in sorted
order moves on by the golden ratio until it is clear of the earlier ones: the same asset always gives the same colours, and
two codes of one asset never look alike. A legend in black (a swatch and the code) sits in the right margin.
render_review.py calls render() in its own Blender session, so the review render makes these files too.
Writes <outdir>/sides.json (result JSON; data.sides[label] = {model_px: [w, h], codes: {code: "#rrggbb"}}). Exit 0, 1 on error.
"""
import colorsys
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "self_build"))
sys.path.insert(0, os.path.join(HERE, "lib"))
import bootstrap  # noqa: E402,F401
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402
import render_views as RV  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/render_sides"
SATURATION, VALUE = 0.65, 0.9
GOLDEN = 0.6180339887
SIDES = ("left", "right", "back")


def hue(code):
    return int(hashlib.sha256(code.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def colours(codes):
    """{code: (r, g, b)} in 0..1 sRGB for the codes of one asset. See the module text for the collision rule."""
    codes = sorted(set(codes))
    gap, placed = min(0.1, 0.8 / max(len(codes), 1)), {}
    for code in codes:
        h = hue(code)
        for _ in range(64):
            if all(min(abs(h - x), 1 - abs(h - x)) >= gap for x in placed.values()):
                break
            h = (h + GOLDEN) % 1
        placed[code] = h
    return {c: colorsys.hsv_to_rgb(h, SATURATION, VALUE) for c, h in placed.items()}


def hex_of(rgb):
    return "#" + "".join(f"{round(c * 255):02X}" for c in rgb)


def legend(path, rgbs, long_edge):
    """The image at path with a margin on its right: a swatch and the code, in black."""
    from PIL import Image, ImageDraw
    img = Image.open(path).convert("RGB")
    w, h = img.size
    fs = max(14, w // 40)
    line = fs + 10
    out = Image.new("RGB", (w + max(220, fs * 9), max(h, line * (len(rgbs) + 2))), (RV.BG_SRGB,) * 3)
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((w + 12, 8), "material", fill=(0, 0, 0), font=RV.font(int(fs * 0.8)))
    for k, (code, rgb) in enumerate(rgbs.items()):
        y = 8 + line * (k + 1)
        d.rectangle([w + 12, y, w + 12 + fs, y + fs], fill=tuple(round(c * 255) for c in rgb), outline=(0, 0, 0))
        d.text((w + 20 + fs, y), code, fill=(0, 0, 0), font=RV.font(int(fs * 0.8)))
    out.save(path)
    return [w, h]


def part_meshes(work):
    """[(code, vertices, triangles)] in build order, and the assembled vertices that frame the view."""
    graph = common.read_json(os.path.join(work, "part_graph.json"))
    code = {p["name"]: p["material"] for p in G.expand_parts(graph)}
    rows = common.read_json(os.path.join(work, "assembly.json"))["data"]["parts"]
    out = []
    for r in rows:
        path = r["glb"] if os.path.isfile(r["glb"]) else os.path.join(work, "parts", os.path.basename(r["glb"]))
        v, t, _ = G.load_glb(path)
        out.append((code[r["name"]], v, t))
    return out, G.load_glb(os.path.join(work, "assembled.glb"))[0]


def render(bpy, scene, cam, work, outdir, size, top=False):
    """Render the side views into outdir with the scene and the orthographic camera of the caller. Returns (files, data)."""
    meshes, frame = part_meshes(work)
    rgbs = colours(c for c, _, _ in meshes)
    sh = scene.display.shading
    sh.light, sh.color_type = "FLAT", "OBJECT"
    sh.show_object_outline = sh.show_cavity = sh.show_shadows = sh.show_specular_highlight = False
    scene.display.render_aa = "OFF"
    scene.render.dither_intensity = 0
    cam.data.type = "ORTHO"
    objects = []
    for i, (code, v, t) in enumerate(meshes):
        ob = RV.add_mesh(bpy, scene, f"mat_{i}", v, t)
        ob.color = (*RV.srgb_to_linear(rgbs[code]), 1.0)
        objects.append(ob)
    files, data = {}, {}
    for side in (*SIDES, *(("top",) if top else ())):
        label = f"mat_{side}"
        files[label] = os.path.join(outdir, f"{label}.png")
        RV.render_view(bpy, scene, cam, np.asarray(frame, float), side, size, files[label])
        data[label] = {"model_px": legend(files[label], rgbs, size), "codes": {c: hex_of(rgb) for c, rgb in rgbs.items()}}
    for ob in objects:
        bpy.data.objects.remove(ob)
    return files, data


def run(work, outdir, size, top):
    import bpy
    os.makedirs(outdir, exist_ok=True)
    scene = RV.reset_scene(bpy)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    return render(bpy, scene, cam, work, outdir, size, top)


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--outdir")
    p.add_argument("--size", type=int, default=1024)
    p.add_argument("--top", action="store_true")
    a = p.parse_args(common.script_argv())
    outdir = a.outdir or os.path.join(a.work, "review")
    out = os.path.join(outdir, "sides.json")
    src = os.path.join(a.work, "assembled.glb")
    try:
        files, data = run(a.work, outdir, a.size, a.top)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=src)
        sys.exit(1)
    common.write_result(out, TOOL, [common.check("render.files", "info", value=len(files))], artifacts=files,
                        data={"sides": data}, source=src)


if __name__ == "__main__":
    require_root()
    main()
