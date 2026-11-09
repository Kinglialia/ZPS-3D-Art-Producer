"""Join every part into one mesh, one object, one material (docs/agents/3d-artist.md §5). Runs in Blender.

Usage: BLENDER -b --python tools/join_mesh.py -- --final F
Reads F/spec.json (asset id), F/assembly.json (part order) and F/parts/<part>.glb of kit assembly.py.
- Join without weld or boolean: each part keeps its own vertices (exact duplicates are merged inside a part only).
- Delete the faces no ray from outside reaches (64 directions, from the centre and near every corner and edge
  midpoint): the faces a part hides in or against another. Kit optbpy.visibility samples only the centre and three
  points around it, so it deleted the base top whose middle sits under the walls. Coplanar faces of two flush parts
  facing the same way stay; check_mesh.py reports them.
- Split the vertices of every edge sharper than 20 deg; every face smooth-shaded.
- Origin at the bottom centre of the whole asset.
Saves F/<id>.blend (object, mesh and material named <id>, no UV yet: unwrap.py next).
Writes F/review/join.json. Exit 0, 1 on error.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("lib", "self_build", "optimize"):
    sys.path.insert(0, os.path.join(HERE, sub))
import bootstrap  # noqa: E402,F401
import numpy as np  # noqa: E402

import common  # noqa: E402

TOOL = "model/join_mesh"
SHARP_DEG = 20.0
WELD_M = 1e-6
N_DIRS = 64


def part_arrays(final):
    import graph as G
    rows = common.read_json(os.path.join(final, "assembly.json"))["data"]["parts"]
    vs, fs, off = [], [], 0
    for r in rows:
        v, t, _ = G.load_glb(os.path.join(final, "parts", f"{r['name']}.glb"))
        _, first, inv = np.unique(np.round(v / WELD_M).astype(np.int64), axis=0, return_index=True, return_inverse=True)
        vs.append(v[first])
        fs.append(inv.reshape(-1)[t] + off)
        off += len(first)
    return [r["name"] for r in rows], np.concatenate(vs), np.concatenate(fs)


def hidden(v, f):
    """Faces no ray from outside reaches, as kit optbpy.visibility, but sampled near every corner and edge too: a big
    face partly under another part (the base top under the walls) keeps its uncovered corners visible."""
    import raster
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons(v.tolist(), f.tolist(), all_triangles=True)
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    dirs = np.asarray(raster.sphere_dirs(N_DIRS), float)
    rays = [Vector(tuple(-d)) for d in dirs]
    t = v[f]
    c = t.mean(1)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    pts = np.stack([c] + [0.9 * t[:, k] + 0.1 * c for k in range(3)]
                   + [0.9 * (t[:, k] + t[:, (k + 1) % 3]) / 2 + 0.1 * c for k in range(3)], axis=1)
    out = np.zeros(len(f), bool)
    for i in range(len(f)):
        order = np.argsort(-np.abs(dirs @ n[i]))
        out[i] = not any(tree.ray_cast(Vector(tuple(p)) + rays[j] * 1e-5 * diag, rays[j], 4 * diag)[0] is None
                         for p in pts[i] for j in order)
    return out


def run(final):
    import bmesh
    import bpy
    import optbpy
    aid = common.read_json(os.path.join(final, "spec.json"))["asset"]
    names, v, f = part_arrays(final)
    optbpy.reset_scene()
    interior = hidden(v, f)
    f = f[~interior]
    lo, hi = v[np.unique(f)].min(0), v[np.unique(f)].max(0)
    offset = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    me = bpy.data.meshes.new(aid)
    me.from_pydata((v + offset).tolist(), [], f.tolist())
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[x for x in bm.verts if not x.link_faces], context="VERTS")
    sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(SHARP_DEG)]
    bmesh.ops.split_edges(bm, edges=sharp)
    for fc in bm.faces:
        fc.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials.new(aid))
    ob = bpy.data.objects.new(aid, me)
    bpy.context.scene.collection.objects.link(ob)
    blend = os.path.join(os.path.abspath(final), f"{aid}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    checks = [common.check("join.parts", "info", len(names)),
              common.check("join.hidden_faces_removed", "info", int(interior.sum())),
              common.check("join.sharp_edges_split", "info", len(sharp), SHARP_DEG),
              common.check("join.origin_offset_m", "info", [common.r(x, 4) for x in offset])]
    return checks, {"parts": names, "tris": len(f), "blend": blend}


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    a = p.parse_args(common.script_argv())
    out = os.path.join(a.final, "review", "join.json")
    try:
        checks, data = run(a.final)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(1)
    common.write_result(out, TOOL, checks, data=data)


if __name__ == "__main__":
    main()
