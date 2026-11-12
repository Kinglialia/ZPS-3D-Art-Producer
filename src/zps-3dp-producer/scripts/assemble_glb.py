"""Blender side of assemble.py (docs/producer.md §6.4 point 2): the locked mesh with the albedo, one unlit material.

Usage: BLENDER -b --python scripts/assemble_glb.py -- --glb <locked GLB> --albedo <png> --name <id> --out <final/model>
Imports the locked GLB as it is (its UV kept), joins its meshes into one object <id>, gives it one material <id> whose
base colour is the albedo (sRGB) and turns it unlit with the kit bake.make_unlit (exported as KHR_materials_unlit).
Exports <out>/<id>.glb and saves <out>/<id>.blend without a .blend1. Prints one JSON line. Exit 0, 1 on error.
assemble_qa.py calls build() inside its own session; this command line stays for a single export.
"""
import json
import os
import sys

MODEL_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents", "zps-3dp-step-model", "tools")
for sub in ("optimize", "lib"):
    sys.path.insert(0, os.path.abspath(os.path.join(MODEL_TOOLS, sub)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from root_guard import require_root  # noqa: E402


def build(glb, albedo, name, out) -> dict:
    import bpy
    import bake
    import optbpy
    bpy.context.preferences.filepaths.save_version = 0
    optbpy.reset_scene()
    ob = optbpy.join_world(name, optbpy.import_model(glb))
    ob.data.name = name
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(os.path.abspath(albedo))
    node.image.colorspace_settings.name = "sRGB"
    bake.make_unlit(mat, node)
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(os.path.abspath(out), f"{name}.glb")
    optbpy.export_glb(path, [ob])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(out), f"{name}.blend"))
    return {"glb": path, "objects": len([o for o in bpy.data.objects if o.type == "MESH"]),
            "tris": sum(len(f.vertices) - 2 for f in ob.data.polygons), "image": list(node.image.size)}


def main():
    import argparse
    p = argparse.ArgumentParser()
    for k in ("--glb", "--albedo", "--name", "--out"):
        p.add_argument(k, required=True)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    print(json.dumps(build(a.glb, a.albedo, a.name, a.out)))


if __name__ == "__main__":
    require_root()
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": repr(e)}))
        sys.exit(1)
