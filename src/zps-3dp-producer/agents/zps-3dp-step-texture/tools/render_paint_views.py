"""VẼ MỚI step 2 (docs/agents/texture-artist.md §4): paint guides of the locked mesh with the base fill. Runs in Blender.

Usage: BLENDER -b --python T/render_paint_views.py -- --glb <locked GLB> --albedo V/work/paint/base_fill.png
       --outdir V/work/paint [--width 1536 --height 1024]
8 orthographic views evenly around the asset (azimuth 0, 45, ... 315), elevation +30 and -30 in turn; unlit, flat
light, transparent film, so each guide shows the base colours exactly. Codex paints paint_<k>.png on top of
guide_<k>.png, 1536 x 1024 by default because gen_image_codex.py needs a long side over 1040 px.
project_views.py reads the cameras back from <outdir>/cameras.json.
Prints one line. Exit 0, 1 on error.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_texture as R  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

ELEVATIONS = (30, -30)


def main():
    import argparse
    import bpy
    p = argparse.ArgumentParser()
    for k in ("--glb", "--albedo", "--outdir"):
        p.add_argument(k, required=True)
    p.add_argument("--width", type=int, default=1536)
    p.add_argument("--height", type=int, default=1024)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    os.makedirs(a.outdir, exist_ok=True)
    sc, cam = R.scene_setup(bpy)
    obs, v = R.import_glb(bpy, a.glb)
    R.attach(bpy, obs, a.albedo)
    R.shading(sc, False)
    views = []
    for k in range(8):
        az, el = 45 * k, ELEVATIONS[k % 2]
        rec = R.ortho(v, R.camera_dir(az, el), None, a.width, a.height)
        f = os.path.join(a.outdir, f"guide_{k}.png")
        R.shoot(bpy, sc, cam, rec, f)
        views.append({"k": k, "azimuth_deg": az, "elevation_deg": el, "guide": f"guide_{k}.png",
                      "paint": f"paint_{k}.png", "camera": rec})
    json.dump({"views": views}, open(os.path.join(a.outdir, "cameras.json"), "w"), indent=1)
    print(f"[render_paint_views] 8 guide -> {a.outdir}")


if __name__ == "__main__":
    require_root()
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"[render_paint_views] error: {e!r}")
        sys.exit(1)
