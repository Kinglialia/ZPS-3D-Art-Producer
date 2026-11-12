"""DUYỆT 1 renders for check-clay and the user, in one Blender run (docs/agents/3d-artist.md §7).

Usage: BLENDER -b --python tools/render_review.py -- --final F --concept C/concept_shadow.png [--size 1024]
Reads F/<id>-untextured.glb (its own normals), F/spec.json (camera, sun, concept_cam, model.character_h,
model.target_px_height). Workbench clay with studio light and shadows from `sun` (azimuth_deg, elevation_deg; default
az 45, el 50): the sun and sky of the spec, the same light in every round.
  lit_34_front.png, lit_front.png, lit_34_back.png   lit clay, orthographic: 3/4 front, front, 3/4 back
  lit_game.png        lit clay from spec camera (azimuth, elevation, fov); no camera: not_checked
  clay_lit_concept.png  concept_shadow | lit clay from `concept_cam` (default: the spec camera) under `sun`
  wire_34.png         clay with every edge drawn, 3/4 front
  thumb.png           the game view cropped and scaled so the asset is model.target_px_height px tall
  lineup.png          front, beside a figure model.character_h tall
  uv_checker.png      3/4 front with a colour grid through the UV (texture view): squeezed or skewed cells show
                      stretch, cells of different sizes show uneven texel density
  model_sheet.png     the board's first image: the renders above (not uv_checker) and renders/parts_34.png when it
                      exists
Writes F/review/review.json (artifacts = label -> path). Exit 0, 1 on error.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("lib", "self_build"):
    sys.path.insert(0, os.path.join(HERE, sub))
import bootstrap  # noqa: E402,F401
import numpy as np  # noqa: E402

import common  # noqa: E402
import raster  # noqa: E402
import render_views as RV  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/render_review"
SUN = {"azimuth_deg": 45.0, "elevation_deg": 50.0}
CELL = 512


def shoot(bpy, scene, cam, v, d, size, path):
    from mathutils import Matrix, Vector
    d = np.asarray(d, float) / np.linalg.norm(d)
    right, up = raster._basis(d)
    pu, pv = v @ right, v @ up
    span = 1.12 * max(pu.max() - pu.min(), pv.max() - pv.min())
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    c = right * (pu.max() + pu.min()) / 2 + up * (pv.max() + pv.min()) / 2 + d * float(((v.min(0) + v.max(0)) / 2) @ d)
    cam.data.type, cam.data.ortho_scale = "ORTHO", span
    cam.data.clip_start, cam.data.clip_end = 0.01 * diag, 20 * diag
    cam.matrix_world = Matrix.Translation(Vector(c - d * 5 * diag)) @ Matrix([list(right), list(up), list(-d)]).transposed().to_4x4()
    render(bpy, scene, path, size, size)


def render(bpy, scene, path, w, h):
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = w, h, 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def game_view(bpy, scene, cam, v, gc, path, w, h):
    from mathutils import Matrix, Vector
    fov = math.radians(float(gc.get("fov_v_deg", 40)))
    d = np.asarray(raster.camera_dir(float(gc.get("azimuth_deg", 0)), float(gc.get("elevation_deg", 35))), float)
    right, up = raster._basis(d)
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    cam.data.type, cam.data.sensor_fit, cam.data.angle_y = "PERSP", "VERTICAL", fov
    cam.data.clip_start, cam.data.clip_end = 0.01 * diag, 40 * diag
    loc = (v.min(0) + v.max(0)) / 2 - d * 0.55 * diag / math.sin(fov / 2)
    cam.matrix_world = Matrix.Translation(Vector(loc)) @ Matrix([list(right), list(up), list(-d)]).transposed().to_4x4()
    render(bpy, scene, path, w, h)


def figure(height, x, y):
    import trimesh
    r = 0.12 * height
    body = trimesh.creation.cylinder(radius=r, height=height - 2 * r, sections=16)
    body.apply_translation((x, y, (height - 2 * r) / 2))
    head = trimesh.creation.icosphere(subdivisions=2, radius=r)
    head.apply_translation((x, y, height - r))
    mesh = trimesh.util.concatenate([body, head])
    return np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int64)


def light(scene, sun):
    az, el = math.radians(sun["azimuth_deg"]), math.radians(sun["elevation_deg"])
    scene.display.light_direction = (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))
    sh = scene.display.shading
    sh.show_shadows, sh.shadow_intensity = True, 0.6


def thumb(src, dst, px):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    box = im.getchannel("A").getbbox() or (0, 0, *im.size)
    crop = im.crop(box)
    s = px / crop.height
    out = Image.new("RGBA", crop.size, (RV.BG_SRGB,) * 3 + (255,))
    out.alpha_composite(crop)
    out.convert("RGB").resize((max(1, round(crop.width * s)), px), Image.LANCZOS).save(dst)


def side_by_side(left, right, dst):
    from PIL import Image
    a = Image.open(left).convert("RGB") if left and os.path.isfile(left) else None
    b = Image.open(right).convert("RGB")
    if a is None:
        b.save(dst)
        return
    a = a.resize((max(1, round(a.width * b.height / a.height)), b.height), Image.LANCZOS)
    out = Image.new("RGB", (a.width + b.width, b.height), (RV.BG_SRGB,) * 3)
    out.paste(a, (0, 0))
    out.paste(b, (a.width, 0))
    out.save(dst)


def sheet(files, dst):
    from PIL import Image, ImageDraw
    cells = [(k, Image.open(p).convert("RGB")) for k, p in files if os.path.isfile(p)]
    cols = 3
    rows = math.ceil(len(cells) / cols)
    out = Image.new("RGB", (cols * CELL, rows * (CELL + 28)), (RV.BG_SRGB,) * 3)
    dr = ImageDraw.Draw(out)
    for i, (k, im) in enumerate(cells):
        im = RV.fit_long_edge(im, CELL)
        x, y = (i % cols) * CELL, (i // cols) * (CELL + 28)
        out.paste(im, (x + (CELL - im.width) // 2, y + 28 + (CELL - im.height) // 2))
        dr.text((x + 8, y + 6), k, fill=(20, 20, 20), font=RV.font(18))
    out.save(dst)


def checker(bpy, scene, obs):
    img = bpy.data.images.new("uv_checker", 1024, 1024)
    img.generated_type = "COLOR_GRID"
    mat = bpy.data.materials.new("uv_checker")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.nodes.active = tex
    for o in obs:
        o.data.materials.clear()
        o.data.materials.append(mat)
    scene.display.shading.color_type = "TEXTURE"


def run(final, concept, size):
    import bpy
    spec = common.read_json(os.path.join(final, "spec.json"))
    aid, m = spec["asset"], spec["model"]
    out = os.path.join(final, "review")
    os.makedirs(out, exist_ok=True)
    scene = RV.reset_scene(bpy)
    RV.set_shading(scene, "clay")
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(os.path.join(final, f"{aid}-untextured.glb")))
    obs = [o for o in scene.objects if o.type == "MESH"]
    v = np.array([o.matrix_world @ x.co for o in obs for x in o.data.vertices], float)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    light(scene, spec.get("sun") or SUN)
    files, checks = {}, []

    def path(label):
        files[label] = os.path.join(out, f"{label}.png")
        return files[label]
    for label, az, el in (("lit_34_front", 45, 30), ("lit_front", 0, 10), ("lit_34_back", 225, 30)):
        shoot(bpy, scene, cam, v, raster.camera_dir(az, el), size, path(label))
    gc = spec.get("camera")
    if gc:
        game_view(bpy, scene, cam, v, gc, path("lit_game"), size, size * 3 // 4)
        scene.render.film_transparent, scene.render.image_settings.color_mode = True, "RGBA"
        game_view(bpy, scene, cam, v, gc, os.path.join(out, "thumb_src.png"), size, size * 3 // 4)
        scene.render.film_transparent, scene.render.image_settings.color_mode = False, "RGB"
        thumb(os.path.join(out, "thumb_src.png"), path("thumb"), int(m["target_px_height"]))
        os.remove(os.path.join(out, "thumb_src.png"))
    else:
        checks.append(common.check("render.game", "not_checked", note="spec.json has no camera"))
    cc = spec.get("concept_cam") or gc or {"azimuth_deg": 45, "elevation_deg": 30}
    shoot(bpy, scene, cam, v, raster.camera_dir(float(cc.get("azimuth_deg", 45)), float(cc.get("elevation_deg", 30))),
          size, os.path.join(out, "lit_concept_src.png"))
    side_by_side(concept, os.path.join(out, "lit_concept_src.png"), path("clay_lit_concept"))
    os.remove(os.path.join(out, "lit_concept_src.png"))
    scene.display.shading.show_shadows = False
    for o in obs:
        w = o.copy()
        w.data = o.data.copy()
        scene.collection.objects.link(w)
        mod = w.modifiers.new("wire", "WIREFRAME")
        mod.thickness, mod.use_replace = 0.004 * float(np.linalg.norm(v.max(0) - v.min(0))), True
        w.color = (0.02, 0.02, 0.02, 1)
        o.color = (*RV.srgb_to_linear([RV.CLAY_SRGB] * 3), 1)
    scene.display.shading.color_type = "OBJECT"
    shoot(bpy, scene, cam, v, raster.camera_dir(45, 30), size, path("wire_34"))
    for o in [o for o in scene.objects if o.modifiers.get("wire")]:
        bpy.data.objects.remove(o)
    RV.set_shading(scene, "clay")
    fv, ft = figure(float(m["character_h"]), v[:, 0].max() + 0.5 * float(m["character_h"]), float(v[:, 1].mean()))
    f_ob = RV.add_mesh(bpy, scene, "figure", fv, ft)
    shoot(bpy, scene, cam, np.concatenate([v, fv]), raster.VIEW_DIRS["front"], size, path("lineup"))
    bpy.data.objects.remove(f_ob)
    checker(bpy, scene, obs)
    shoot(bpy, scene, cam, v, raster.camera_dir(45, 30), size, path("uv_checker"))
    order = ("lit_34_front", "clay_lit_concept", "wire_34", "lit_34_back", "lit_game", "lineup", "thumb")
    sheet([(k, files[k]) for k in order if k in files] + [("parts_34", os.path.join(out, "renders", "parts_34.png"))],
          path("model_sheet"))
    checks.insert(0, common.check("render.files", "info", len(files)))
    return checks, files


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    p.add_argument("--concept")
    p.add_argument("--size", type=int, default=1024)
    a = p.parse_args(common.script_argv())
    out = os.path.join(a.final, "review", "review.json")
    try:
        checks, files = run(a.final, a.concept, a.size)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(1)
    common.write_result(out, TOOL, checks, artifacts=files)


if __name__ == "__main__":
    require_root()
    main()
