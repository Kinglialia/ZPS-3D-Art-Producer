"""Texture render set, and the same cameras again from any GLB (docs/agents/texture-artist.md §9). Runs in Blender.

Usage:
  BLENDER -b --python T/render_texture.py -- --glb <locked GLB> --albedo F/albedo_<res>.png --spec <model final>/spec.json
          --concept C/concept_shadow.png --final F [--size 768]
  BLENDER -b --python T/render_texture.py -- --glb <GLB> --cameras F/review/renders.json --views unlit_34_front,unlit_game
          --outdir D
Set mode (texture worker): the albedo on the locked mesh, Workbench, view transform Standard.
  lit_<view>    studio light, texture colour, shadows from spec `sun` (default az 45, el 50)
  unlit_<view>  flat light, texture colour, transparent film: each pixel is the albedo value
  views: 34_front (az 45, el 30), close_front (az 0, el 10, the front half), 34_back (az 225, el 30), game (spec camera)
  thumb.png     the unlit game view, model.target_px_height px tall
  final_lit_vs_concept.png  concept_shadow | lit from spec `concept_cam` under `sun`
  Writes F/review/renders.json: label -> {file, camera {matrix, type, ortho_scale|angle_y, clip, w, h}}, and the sha256
  of the albedo file it rendered as `albedo_sha256`: a render of an older albedo is told by it (D36.11).
Camera mode (assemble.py): imports the GLB with its own material and image, as an engine reads it, and renders the
labels in --views with the recorded cameras and the same shading. Exit 0, 1 on error.
"""
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import bootstrap  # noqa: E402,F401
import numpy as np  # noqa: E402

import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

SUN = {"azimuth_deg": 45.0, "elevation_deg": 50.0}
VIEWS = {"34_front": (45, 30), "close_front": (0, 10), "34_back": (225, 30)}
BG = 0.82


def argv():
    import argparse
    p = argparse.ArgumentParser()
    for k in ("--glb", "--albedo", "--spec", "--concept", "--final", "--cameras", "--views", "--outdir"):
        p.add_argument(k)
    p.add_argument("--size", type=int, default=768)
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def camera_dir(az, el):
    az, el = math.radians(az), math.radians(el)
    return np.array([-math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), -math.sin(el)])


def basis(d):
    up0 = np.array([0.0, 0.0, 1.0])
    right = np.cross(d, up0)
    right /= np.linalg.norm(right)
    return right, np.cross(right, d)


def scene_setup(bpy):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.world = bpy.data.worlds.new("bg")
    sc.world.color = (BG, BG, BG)
    sh = sc.display.shading
    sh.color_type = "TEXTURE"
    sh.show_cavity = sh.show_specular_highlight = sh.show_object_outline = False
    sc.render.image_settings.file_format = "PNG"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def shading(sc, lit, sun=None):
    sh = sc.display.shading
    sh.light = "STUDIO" if lit else "FLAT"
    sh.show_shadows = bool(lit)
    if lit:
        az, el = math.radians(sun["azimuth_deg"]), math.radians(sun["elevation_deg"])
        sc.display.light_direction = (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))
        sh.shadow_intensity = 0.5
    sc.render.film_transparent = not lit
    sc.render.image_settings.color_mode = "RGB" if lit else "RGBA"


def ortho(v, d, half=None, w=1, h=1):
    """Blender's ortho_scale spans the longer image side; the shorter side sees span * short / long."""
    right, up = basis(d)
    if half == "front":
        v = v[v[:, 1] <= (v[:, 1].min() + v[:, 1].max()) / 2]
    pu, pv = v @ right, v @ up
    span = 1.1 * max((pu.max() - pu.min()) * max(w, h) / w, (pv.max() - pv.min()) * max(w, h) / h)
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    c = right * (pu.max() + pu.min()) / 2 + up * (pv.max() + pv.min()) / 2 + d * float(((v.min(0) + v.max(0)) / 2) @ d)
    m = np.eye(4)
    m[:3, :3] = np.stack([right, up, -d], axis=1)
    m[:3, 3] = c - d * 5 * diag
    return {"type": "ORTHO", "ortho_scale": span, "clip": [0.01 * diag, 20 * diag], "matrix": m.tolist(), "w": w, "h": h}


def perspective(v, gc):
    fov = math.radians(float(gc.get("fov_v_deg", 40)))
    d = camera_dir(float(gc.get("azimuth_deg", 0)), float(gc.get("elevation_deg", 35)))
    right, up = basis(d)
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    m = np.eye(4)
    m[:3, :3] = np.stack([right, up, -d], axis=1)
    m[:3, 3] = (v.min(0) + v.max(0)) / 2 - d * 0.55 * diag / math.sin(fov / 2)
    return {"type": "PERSP", "angle_y": fov, "clip": [0.01 * diag, 40 * diag], "matrix": m.tolist()}


def shoot(bpy, sc, cam, rec, path):
    from mathutils import Matrix
    cam.data.type = rec["type"]
    if rec["type"] == "ORTHO":
        cam.data.ortho_scale = rec["ortho_scale"]
    else:
        cam.data.sensor_fit, cam.data.angle_y = "VERTICAL", rec["angle_y"]
    cam.data.clip_start, cam.data.clip_end = rec["clip"]
    cam.matrix_world = Matrix(rec["matrix"])
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rec["w"], rec["h"], 100
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def import_glb(bpy, path):
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
    obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in obs:
        for slot in o.material_slots:
            nt = slot.material.node_tree if slot.material and slot.material.use_nodes else None
            img = [n for n in nt.nodes if n.type == "TEX_IMAGE"] if nt else []
            if img:
                nt.nodes.active = img[0]
    return obs, np.array([o.matrix_world @ x.co for o in obs for x in o.data.vertices], float)


def attach(bpy, obs, albedo):
    img = bpy.data.images.load(os.path.abspath(albedo))
    img.colorspace_settings.name = "sRGB"
    mat = bpy.data.materials.new("albedo")
    mat.use_nodes = True
    nt = mat.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.links.new(node.outputs["Color"], next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"])
    nt.nodes.active = node
    for o in obs:
        o.data.materials.clear()
        o.data.materials.append(mat)


def thumb(src, dst, px):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    crop = im.crop(im.getchannel("A").getbbox() or (0, 0, *im.size))
    out = Image.new("RGBA", crop.size, (int(BG * 255),) * 3 + (255,))
    out.alpha_composite(crop)
    out.convert("RGB").resize((max(1, round(crop.width * px / crop.height)), px), Image.LANCZOS).save(dst)


def side_by_side(left, right, dst):
    from PIL import Image
    b = Image.open(right).convert("RGB")
    a = Image.open(left).convert("RGB") if left and os.path.isfile(left) else None
    if a is None:
        return b.save(dst)
    a = a.resize((max(1, round(a.width * b.height / a.height)), b.height), Image.LANCZOS)
    out = Image.new("RGB", (a.width + b.width, b.height), (255, 255, 255))
    out.paste(a, (0, 0))
    out.paste(b, (a.width, 0))
    out.save(dst)


def render_set(bpy, a):
    spec = json.load(open(a.spec, encoding="utf-8"))
    out = os.path.join(a.final, "review")
    os.makedirs(out, exist_ok=True)
    sc, cam = scene_setup(bpy)
    obs, v = import_glb(bpy, a.glb)
    attach(bpy, obs, a.albedo)
    sun = spec.get("sun") or SUN
    cams = {k: ortho(v, camera_dir(az, el), "front" if k == "close_front" else None, a.size, a.size)
            for k, (az, el) in VIEWS.items()}
    if spec.get("camera"):
        cams["game"] = perspective(v, spec["camera"]) | {"w": a.size, "h": a.size * 3 // 4}
    cc = spec.get("concept_cam") or {"azimuth_deg": 45, "elevation_deg": 30}
    cams["concept"] = ortho(v, camera_dir(float(cc["azimuth_deg"]), float(cc["elevation_deg"])), None, a.size, a.size)
    files = {}
    for lit in (True, False):
        shading(sc, lit, sun)
        for k, rec in cams.items():
            if k == "concept" and not lit:
                continue
            label = f"{'lit' if lit else 'unlit'}_{k}"
            files[label] = {"file": os.path.join(out, f"{label}.png"), "camera": rec}
            shoot(bpy, sc, cam, rec, files[label]["file"])
    side_by_side(a.concept, files.pop("lit_concept")["file"], os.path.join(a.final, "final_lit_vs_concept.png"))
    os.remove(os.path.join(out, "lit_concept.png"))
    if "unlit_game" in files:
        thumb(files["unlit_game"]["file"], os.path.join(out, "thumb.png"), int(spec["model"]["target_px_height"]))
        files["thumb"] = {"file": os.path.join(out, "thumb.png"), "camera": None}
    rel = {k: dict(r, file=os.path.relpath(r["file"], a.final)) for k, r in files.items()}
    write_renders(os.path.join(out, "renders.json"), a.albedo, sun, rel)
    return [tex.check("render.files", "info", len(rel))], rel


def write_renders(path, albedo, sun, rel):
    with open(albedo, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"albedo": os.path.basename(albedo), "albedo_sha256": sha, "sun": sun, "renders": rel}, fh, indent=1)


def render_cameras(bpy, a):
    doc = json.load(open(a.cameras, encoding="utf-8"))
    rec = doc["renders"]
    os.makedirs(a.outdir, exist_ok=True)
    sc, cam = scene_setup(bpy)
    import_glb(bpy, a.glb)
    files = {}
    for label in a.views.split(","):
        shading(sc, label.startswith("lit_"), doc.get("sun") or SUN)
        files[label] = os.path.join(a.outdir, f"{label}.png")
        shoot(bpy, sc, cam, rec[label]["camera"], files[label])
    return [tex.check("render.files", "info", len(files))], files


def main():
    import bpy
    a = argv()
    out = os.path.join(a.final, "review", "render_texture.json") if a.final else os.path.join(a.outdir, "render.json")
    try:
        checks, files = render_cameras(bpy, a) if a.cameras else render_set(bpy, a)
    except Exception as e:  # noqa: BLE001
        tex.write_error(out, "render_texture", e)
        print(f"[render_texture] error: {e!r}")
        sys.exit(1)
    tex.write_result(out, "render_texture", checks, data={"files": files})
    print(f"[render_texture] {len(files)} ảnh -> {os.path.dirname(out)}")


if __name__ == "__main__":
    require_root()
    main()
