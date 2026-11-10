"""Join every part into one mesh, one object, one material (docs/agents/3d-artist.md §5). Runs in Blender.

Usage: BLENDER -b --python tools/join_mesh.py -- --final F
Reads F/spec.json (asset id), F/assembly.json (part order) and F/parts/<part>.glb of kit assembly.py.
- Join without weld or boolean: each part keeps its own vertices (exact duplicates are merged inside a part only).
- Delete the faces no ray from outside reaches (the half of 64 directions on the side the face looks to, from every
  sample point): the faces a part hides in or against another. Sample points: a grid of pitch <= 5 cm on the face, each
  point moved 1.5 cm towards the incentre, edge points first. Sampling only near the corners deleted the 10 cm base-top
  rim around 3.8 m walls on a 4 m base, because every corner sat under the walls. Coplanar faces of two flush parts
  facing the same way stay; check_mesh.py reports them.
- join.removed_faces_seen fails when a deleted face is the first hit of a 200 x 200 orthographic ray grid along the
  6 axes or from 45 deg above on the 4 diagonals.
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
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/join_mesh"
SHARP_DEG = 20.0
WELD_M = 1e-6
N_DIRS = 64
EDGE_M = 0.015
GRID_M = 0.05
SEEN_RES = 200


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


def samples(t):
    """Grid points of pitch <= GRID_M on triangle t, each moved EDGE_M towards the incentre, edge points first."""
    e = np.linalg.norm(t[[1, 2, 0]] - t[[2, 0, 1]], axis=1)
    if not e.sum():
        return t[:1]
    n = max(1, int(np.ceil(e.max() / GRID_M)))
    i, j = np.mgrid[:n + 1, :n + 1].reshape(2, -1)
    w = np.stack([i, j, n - i - j], 1)[i + j <= n]
    p = w[np.argsort(w.min(1) > 0, kind="stable")] / n @ t
    d = e @ t / e.sum() - p
    return p + d * np.minimum(1, EDGE_M / np.maximum(np.linalg.norm(d, axis=1), 1e-12))[:, None]


def hidden(v, f, tree):
    """Faces from whose samples() no ray towards the side they face escapes the mesh."""
    import raster
    from mathutils import Vector
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    dirs = -np.asarray(raster.sphere_dirs(N_DIRS), float)
    rays = [(Vector(d), Vector(d * 1e-5 * diag)) for d in dirs]
    t = v[f]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    out = np.zeros(len(f), bool)
    for i in range(len(f)):
        dn = dirs @ n[i]
        out_rays = [rays[j] for j in np.argsort(-dn) if dn[j] > 0]
        out[i] = not any(tree.ray_cast(p + o, r, 4 * diag)[0] is None
                         for p in map(Vector, samples(t[i]).tolist()) for r, o in out_rays)
    return out


def seen(v, f, gone, tree):
    """Ids of gone faces that an orthographic ray grid hits first, front side, along the 6 axes and from 45 deg above
    on the 4 diagonals."""
    import raster
    lo, hi = v.min(0), v.max(0)
    c, diag = (lo + hi) / 2, float(np.linalg.norm(hi - lo)) or 1.0
    t = v[f]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    views = [raster.VIEW_DIRS[k] for k in ("front", "back", "left", "right", "top", "bottom")]
    out = set()
    for d in np.asarray(views + [raster.camera_dir(az, 45) for az in (45, 135, 225, 315)], float):
        u = np.cross(d, (0, 0, 1) if abs(d[2]) < 0.9 else (0, 1, 0))
        u /= np.linalg.norm(u)
        w = np.cross(d, u)
        k = (np.arange(SEEN_RES) + np.sqrt(2) - 1) / SEEN_RES  # off the cm grid: no ray runs along a part edge
        pu, pw = (v - c) @ u, (v - c) @ w
        gu, gw = np.meshgrid(pu.min() + k * np.ptp(pu), pw.min() + k * np.ptp(pw))
        rays = c - d * diag + np.outer(gu.ravel(), u) + np.outer(gw.ravel(), w)
        hits = {tree.ray_cast(o, d.tolist(), 2 * diag)[2] for o in rays.tolist()}
        out |= {h for h in hits if h is not None and gone[h] and n[h] @ d < 0}
    return sorted(out)


def run(final):
    import bmesh
    import bpy
    import optbpy
    from mathutils.bvhtree import BVHTree
    aid = common.read_json(os.path.join(final, "spec.json"))["asset"]
    names, v, f = part_arrays(final)
    optbpy.reset_scene()
    tree = BVHTree.FromPolygons(v.tolist(), f.tolist(), all_triangles=True)
    interior = hidden(v, f, tree)
    shown = seen(v, f, interior, tree)
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
    fp = bpy.context.preferences.filepaths
    keep, fp.save_version = fp.save_version, 0
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    fp.save_version = keep
    checks = [common.check("join.parts", "info", len(names)),
              common.check("join.hidden_faces_removed", "info", int(interior.sum())),
              common.check("join.removed_faces_seen", "fail" if shown else "pass", len(shown), 0),
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
    require_root()
    main()
