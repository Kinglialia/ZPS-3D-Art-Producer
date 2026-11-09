"""Extra review renders for check-blockout, in one Blender run (docs/agents/blockout.md §6).

Usage: blender -b --python tools/render_review.py -- --work <dir> [--outdir <dir>/review] [--size 1024]
Reads <dir>/assembled.glb, part_graph.json, assembly.json, sources.json. Clay shading as render_views.py.
  game_cam.png          perspective camera from sources.json camera (azimuth, elevation, fov_v);
                        no camera: not_checked
  lineup.png            front ortho, the building beside a figure (cylinder + sphere) character_h tall
  foot_front_left.png,  ortho close-ups of the base-ground-wall corner at the front, from the bbox of
  foot_front_right.png  the tag: base parts, or else the parts resting on the ground (props have no
                        base); left = the object's own left (+X), as the kit's views.
Writes <outdir>/review.json (result JSON, artifacts = label -> path). Exit 0, 1 on error.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "self_build"))
sys.path.insert(0, os.path.join(HERE, "lib"))
import bootstrap  # noqa: E402,F401
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402
import raster  # noqa: E402
import render_views as RV  # noqa: E402

TOOL = "blockout/render_review"
FOOT_EL = 20.0


def look(cam, d, target, dist):
    from mathutils import Matrix, Vector
    d = np.asarray(d, float) / np.linalg.norm(d)
    right, up = raster._basis(d)
    rot = Matrix([list(right), list(up), list(-d)]).transposed()
    cam.matrix_world = Matrix.Translation(Vector(np.asarray(target) - d * dist)) @ rot.to_4x4()


def shoot(bpy, scene, path, w, h):
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def figure(height, x, y):
    import trimesh
    r = 0.12 * height
    body = trimesh.creation.cylinder(radius=r, height=height - 2 * r, sections=16)
    body.apply_translation((x, y, (height - 2 * r) / 2))
    head = trimesh.creation.icosphere(subdivisions=2, radius=r)
    head.apply_translation((x, y, height - r))
    m = trimesh.util.concatenate([body, head])
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def run(work, outdir, size):
    import bpy
    sources = common.read_json(os.path.join(work, "sources.json"))
    graph = common.read_json(os.path.join(work, "part_graph.json"))
    rows = common.read_json(os.path.join(work, "assembly.json"))["data"]["parts"]
    v, t, _ = G.load_glb(os.path.join(work, "assembled.glb"))
    os.makedirs(outdir, exist_ok=True)
    scene = RV.reset_scene(bpy)
    RV.set_shading(scene, "clay")
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    RV.add_mesh(bpy, scene, "model", v, t)
    lo, hi = v.min(0), v.max(0)
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    cam.data.clip_start, cam.data.clip_end = 0.01 * diag, 40 * diag
    files, checks = {}, []

    ch = float(sources["character_h"])
    fv, ft = figure(ch, hi[0] + 0.5 * ch, (lo[1] + hi[1]) / 2)
    fig = RV.add_mesh(bpy, scene, "figure", fv, ft)
    cam.data.type = "ORTHO"
    files["lineup"] = os.path.join(outdir, "lineup.png")
    RV.render_view(bpy, scene, cam, np.concatenate([v, fv]), "front", size, files["lineup"])
    bpy.data.objects.remove(fig)

    ground = RV.add_mesh(bpy, scene, "ground", [[lo[0] - diag, lo[1] - diag, 0], [hi[0] + diag, lo[1] - diag, 0],
                                                [hi[0] + diag, hi[1] + diag, 0], [lo[0] - diag, hi[1] + diag, 0]],
                         [[0, 1, 2], [0, 2, 3]])
    gc = sources.get("camera")
    if gc:
        fov = math.radians(float(gc.get("fov_v_deg", 40)))
        cam.data.type, cam.data.sensor_fit, cam.data.angle_y = "PERSP", "VERTICAL", fov
        look(cam, raster.camera_dir(float(gc.get("azimuth_deg", 0)), float(gc.get("elevation_deg", 35))),
             (lo + hi) / 2, 0.55 * diag / math.sin(fov / 2))
        files["game_cam"] = os.path.join(outdir, "game_cam.png")
        shoot(bpy, scene, files["game_cam"], size, size * 3 // 4)
    else:
        checks.append(common.check("render.game_cam", "not_checked", note="sources.json has no camera"))

    base = [r for r in rows if any(p["name"] == r["name"] and p.get("tag") == "base" for p in graph["parts"])]
    if not base and rows:
        floor = min(r["bbox_min"][2] for r in rows)
        base = [r for r in rows if r["bbox_min"][2] <= floor + 0.01]
    if base:
        blo = np.min([r["bbox_min"] for r in base], axis=0)
        bhi = np.max([r["bbox_max"] for r in base], axis=0)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(1.0, 4 * float(bhi[2] - blo[2]))
        for label, x, az in (("foot_front_left", bhi[0], 45.0), ("foot_front_right", blo[0], -45.0)):
            look(cam, raster.camera_dir(az, FOOT_EL), (x, blo[1], bhi[2]), 10 * diag)
            files[label] = os.path.join(outdir, f"{label}.png")
            shoot(bpy, scene, files[label], size // 2, size // 2)
    else:
        checks.append(common.check("render.foot", "not_checked", note="no part rests on the ground"))
    bpy.data.objects.remove(ground)
    checks.insert(0, common.check("render.files", "info", value=len(files)))
    return checks, files


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--outdir")
    p.add_argument("--size", type=int, default=1024)
    a = p.parse_args(common.script_argv())
    outdir = a.outdir or os.path.join(a.work, "review")
    out = os.path.join(outdir, "review.json")
    src = os.path.join(a.work, "assembled.glb")
    try:
        checks, files = run(a.work, outdir, a.size)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=src)
        sys.exit(1)
    common.write_result(out, TOOL, checks, artifacts=files, source=src)


if __name__ == "__main__":
    main()
