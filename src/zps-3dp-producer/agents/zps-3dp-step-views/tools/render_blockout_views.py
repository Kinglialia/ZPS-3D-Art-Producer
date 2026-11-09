"""Render 6 orthographic views of a blockout for the 6-view process.

Run with Blender (background), with literal absolute paths:
  <BLENDER> -b --python <SKILL>/scripts/render_blockout_views.py -- --input <abs>/blockout.glb --out <abs>/views_blockout [--res 1024]
  <BLENDER> -b --python <SKILL>/scripts/render_blockout_views.py -- --parts <w>/parts --graph <w>/part_graph.json --out <abs>/views_blockout
--parts/--graph: the 3D self-build output (tools/self_build/assembly.py). Each part becomes one
object, and its material is the part's "material" label (the part name when it has none).

Outputs in --out:
  <view>_id.png     flat colour per material, no anti-aliasing, transparent background
                    (ground truth for silhouette + material regions; used by measure_views.py)
  <view>_guide.png  shaded render with the same material colours + outlines
                    (the image you give the image AI as the shape guide)
  views.json        views, bbox size (m), ortho scale, metres per pixel, material -> hex

Views (kit convention, the same as the 3D Artist): the object faces -Y. front = camera at -Y,
back = camera at +Y, left = the object's OWN left side (camera at +X), right = the object's own
right side (camera at -X), top (+Z, front at the bottom of the image), bottom. All six share ONE ortho scale and resolution so the sizes are comparable.
The script changes material viewport colours only in memory; it never saves the .blend.
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

VIEWS = {
    # name: (camera direction from centre, rotation euler in degrees)
    "front": (Vector((0, -1, 0)), (90, 0, 0)),
    "back": (Vector((0, 1, 0)), (90, 0, 180)),
    "left": (Vector((1, 0, 0)), (90, 0, 90)),     # object's own left = +X
    "right": (Vector((-1, 0, 0)), (90, 0, -90)),  # object's own right = -X
    "top": (Vector((0, 0, 1)), (0, 0, 0)),
    "bottom": (Vector((0, 0, -1)), (180, 0, 0)),
}

# Distinct sRGB colours for material IDs (avoid pure white/black/grey and chroma green/magenta,
# which the image AI may use as its background).
PALETTE = [
    "#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231", "#911EB4", "#42D4F4",
    "#BFEF45", "#FABED4", "#469990", "#DCBEFF", "#9A6324", "#FFFAC8", "#800000",
    "#AAFFC3", "#808000", "#FFD8B1", "#000075", "#A9A9F5", "#C46210",
]


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", help=".glb/.gltf/.obj/.fbx (omit if a .blend was opened)")
    p.add_argument("--parts", help="folder of part GLBs from the 3D self-build (with --graph)")
    p.add_argument("--graph", help="part_graph.json of the self-build; gives the material label per part")
    p.add_argument("--out", required=True)
    p.add_argument("--res", type=int, default=1024)
    p.add_argument("--margin", type=float, default=1.15, help="ortho scale = max bbox dim * margin")
    return p.parse_args(argv)


def import_model(path):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise SystemExit(f"Unsupported input: {path}")


def import_parts(parts_dir, graph_path):
    """One object per self-build part; material = the part's "material" label."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    graph = json.load(open(graph_path))
    labels = {p["name"]: p.get("material") for p in graph["parts"]}
    for p in graph["parts"]:  # a mirror_of part without its own label takes the source label
        if not labels.get(p["name"]) and (p.get("attach") or {}).get("type") == "mirror_of":
            labels[p["name"]] = labels.get(p["attach"]["of"])
    for name in labels:
        path = os.path.join(parts_dir, f"{name}.glb")
        if not os.path.exists(path):
            raise SystemExit(f"Missing part file {path}: run assembly.py first")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        mat_name = labels[name] or name
        mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
        for o in set(bpy.data.objects) - before:
            if o.type == "MESH":
                o.data.materials.clear()
                o.data.materials.append(mat)


def main():
    args = parse_args()
    if bool(args.parts) != bool(args.graph):
        raise SystemExit("--parts and --graph go together")
    if args.parts:
        import_parts(os.path.abspath(args.parts), os.path.abspath(args.graph))
    elif args.input:
        import_model(os.path.abspath(args.input))
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise SystemExit("No visible mesh objects found.")
    for o in scene.objects:
        if o.type not in ("MESH", "CAMERA"):
            o.hide_render = True

    # Material IDs: one colour per material; objects without material get their own.
    materials = {}
    for o in meshes:
        if not o.material_slots or all(s.material is None for s in o.material_slots):
            m = bpy.data.materials.new(name=o.name)
            o.data.materials.clear()
            o.data.materials.append(m)
        for s in o.material_slots:
            if s.material and s.material.name not in materials:
                materials[s.material.name] = s.material
    mat_hex = {}
    for i, (name, m) in enumerate(sorted(materials.items())):
        hx = PALETTE[i % len(PALETTE)]
        if i >= len(PALETTE):
            print(f"WARNING: more than {len(PALETTE)} materials, colours repeat ({name})")
        m.diffuse_color = (*hex_to_linear(hx), 1.0)
        mat_hex[name] = hx

    # World-space bounding box of all meshes.
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(deps)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    size = mx - mn
    center = (mn + mx) / 2
    ortho = max(size) * args.margin
    dist = max(size) * 3 + 10

    cam_data = bpy.data.cameras.new("view_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho
    cam_data.clip_start = 0.01
    cam_data.clip_end = dist * 3
    cam = bpy.data.objects.new("view_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x = r.resolution_y = args.res
    r.resolution_percentage = 100
    r.film_transparent = True
    r.dither_intensity = 0.0
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    sh = scene.display.shading
    sh.color_type = "MATERIAL"

    for view, (d, rot) in VIEWS.items():
        cam.location = center + d * dist
        cam.rotation_euler = [math.radians(a) for a in rot]
        # Pass 1: material ID, flat, no AA, no outline/cavity.
        sh.light = "FLAT"
        sh.show_object_outline = False
        sh.show_cavity = False
        sh.show_shadows = False
        scene.display.render_aa = "OFF"
        r.filepath = os.path.join(out, f"{view}_id.png")
        bpy.ops.render.render(write_still=True)
        # Pass 2: shaded guide for the image AI.
        sh.light = "STUDIO"
        sh.show_object_outline = True
        sh.object_outline_color = (0, 0, 0)
        sh.show_cavity = True
        scene.display.render_aa = "8"
        r.filepath = os.path.join(out, f"{view}_guide.png")
        bpy.ops.render.render(write_still=True)

    meta = {
        "views": list(VIEWS),
        "resolution": args.res,
        "ortho_scale_m": ortho,
        "metres_per_pixel": ortho / args.res,
        "bbox_size_m": {"width_x": size.x, "depth_y": size.y, "height_z": size.z},
        "materials": mat_hex,
        "convention": "object faces -Y; left/right are the object's own sides (left = camera at +X)",
        "image_axes": {
            "front/back": "horizontal = width (X), vertical = height (Z)",
            "left/right": "horizontal = depth (Y), vertical = height (Z)",
            "top/bottom": "horizontal = width (X), vertical = depth (Y)",
        },
    }
    with open(os.path.join(out, "views.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Rendered {len(VIEWS)} views x 2 passes to {out}")


main()
