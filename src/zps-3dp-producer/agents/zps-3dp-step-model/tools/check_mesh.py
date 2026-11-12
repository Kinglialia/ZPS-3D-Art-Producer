"""The joined mesh (docs/agents/3d-artist.md §5): one node, one mesh, one material, no z-fighting faces. Plain Python.

Usage: python3 tools/check_mesh.py --final F [--before-join]
  mesh.part_winding     every closed part of F/assembly.json (F/parts/<part>.glb, each edge on exactly 2 triangles)
                        has a positive signed volume. A part built inside out vanishes in join_mesh.py, because every
                        ray from its faces runs into the part, and kit mesh_check sees only the open joined mesh.
                        Open parts (cards) are listed in data.open_parts, not checked
  mesh.structure        F/<id>-untextured.glb has 1 node with a mesh, 1 mesh, 1 material
  mesh.coplanar_overlap pairs of triangles in the same plane (normals within 0.8 deg, offset under the 1 mm of
                        model.md), facing the same way, whose areas overlap: a join without boolean leaves them where
                        a part sits flush in another. > 0 fails; data.pairs lists up to 10 centroids
Hidden faces and flipped faces: kit mesh_check (hidden_face_ratio, flipped_faces) on the same GLB.
--before-join: right after a build: only mesh.part_winding, to F/review/checks/mesh_build.json.
Writes F/review/checks/mesh.json. Exit 0 pass, 1 fail, 2 error.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import cli  # noqa: E402
import common  # noqa: E402
import glbread  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/check_mesh"
COS_MAX = np.cos(np.radians(0.8))
PLANE_TOL_M = 1e-3
FLOAT32_SLACK_M = 1e-5
SEP_EPS_M = 1e-6
CHUNK = 512
WELD_M = 1e-6


def overlap_2d(a, b):
    """True when two triangles in one plane share area: no edge normal separates them by more than SEP_EPS_M."""
    for tri in (a, b):
        for k in range(3):
            e = tri[(k + 1) % 3] - tri[k]
            ax = np.array([-e[1], e[0]])
            ax /= np.linalg.norm(ax) or 1.0
            pa, pb = a @ ax, b @ ax
            if pa.max() <= pb.min() + SEP_EPS_M or pb.max() <= pa.min() + SEP_EPS_M:
                return False
    return True


def coplanar_pairs(v, f):
    t = v[f]
    cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(cr, axis=1)
    keep = np.flatnonzero(ln > 1e-12)
    n = cr[keep] / ln[keep, None]
    d = np.einsum("ij,ij->i", n, t[keep, 0])
    out = []
    for s in range(0, len(keep), CHUNK):
        cos = n[s:s + CHUNK] @ n.T
        near = np.abs(d[s:s + CHUNK, None] - d[None, :]) < PLANE_TOL_M - FLOAT32_SLACK_M
        for i, j in zip(*np.nonzero((cos > COS_MAX) & near)):
            i += s
            if j <= i:
                continue
            u = np.cross(n[i], [1.0, 0, 0] if abs(n[i][0]) < 0.9 else [0, 1.0, 0])
            u /= np.linalg.norm(u)
            w = np.cross(n[i], u)
            ti, tj = t[keep[i]], t[keep[j]]
            if overlap_2d(np.c_[ti @ u, ti @ w], np.c_[tj @ u, tj @ w]):
                out.append((int(keep[i]), int(keep[j]), ti.mean(0)))
    return out


def winding(final):
    """(inside-out part names, open part names, part count) of the part build."""
    rows = common.read_json(os.path.join(final, "assembly.json"))["data"]["parts"]
    inverted, open_ = [], []
    for r in rows:
        g = glbread.load(os.path.join(final, "parts", f"{r['name']}.glb"))
        v, inv = np.unique(np.round(g["v"] / WELD_M).astype(np.int64), axis=0, return_inverse=True)
        f = inv.reshape(-1)[g["f"]]
        e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
        if (np.unique(e, axis=0, return_counts=True)[1] != 2).any():
            open_.append(r["name"])
            continue
        t = (v * WELD_M)[f]
        if np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() <= 0:
            inverted.append(r["name"])
    return inverted, open_, len(rows)


def args(p):
    p.add_argument("--before-join", action="store_true")


def check(a):
    inverted, open_, n = winding(a.final)
    status = "fail" if inverted else "pass" if len(open_) < n else "not_checked"
    checks = [common.check("mesh.part_winding", status, inverted, note={
        "fail": "part kín có thể tích có dấu ≤ 0: mặt quay vào trong", "not_checked": "không part nào kín"}.get(status))]
    data = {"open_parts": open_}
    if a.before_join:
        return checks, data
    spec = common.read_json(os.path.join(a.final, "spec.json"))
    g = glbread.load(os.path.join(a.final, f"{spec['asset']}-untextured.glb"))
    shape = {k: g[k] for k in ("nodes", "meshes", "materials")}
    pairs = coplanar_pairs(g["v"], g["f"])
    checks += [common.check("mesh.structure", "pass" if shape == {"nodes": 1, "meshes": 1, "materials": 1} else "fail",
                            shape, {"nodes": 1, "meshes": 1, "materials": 1}),
               common.check("mesh.coplanar_overlap", "fail" if pairs else "pass", len(pairs), 0,
                            note="mặt đồng phẳng chồng nhau, cùng hướng: z-fighting")]
    return checks, data | {"tris": len(g["f"]), "pairs": [{"faces": [i, j], "at": [common.r(x, 3) for x in c]}
                                                          for i, j, c in pairs[:10]]}


if __name__ == "__main__":
    require_root()
    cli.run(TOOL, "mesh", __doc__, args, check, glb=True)
