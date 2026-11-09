"""Read a GLB without Blender: scene counts, triangles in Blender axes (Z up, front -Y), TEXCOORD_0.

load(path) -> {"nodes", "meshes", "materials", "v" (n,3), "f" (m,3) global vertex ids, "uv" (n,2) or None}.
"nodes" counts the default scene's nodes that hold a mesh. Node TRS or matrix is applied.
Vertex ids are the file's own: the exporter splits a vertex at every UV seam and sharp edge.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "optimize"))
import optlib  # noqa: E402

GLTF_TO_ZUP = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])


def node_matrix(n):
    if "matrix" in n:
        return np.asarray(n["matrix"], float).reshape(4, 4).T
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.asarray(n.get("scale", [1, 1, 1]), float)
    m[:3, 3] = n.get("translation", [0, 0, 0])
    return m


def load(path):
    doc, binary = optlib.read_glb(path)
    nodes = doc.get("nodes", [])
    scenes = doc.get("scenes", [])
    stack = [(i, np.eye(4)) for i in (scenes[doc.get("scene", 0)]["nodes"] if scenes else range(len(nodes)))]
    vs, fs, uvs, off, count = [], [], [], 0, 0
    while stack:
        i, parent = stack.pop()
        n = nodes[i]
        m = parent @ node_matrix(n)
        stack.extend((c, m) for c in n.get("children", []))
        if "mesh" not in n:
            continue
        count += 1
        for prim in doc["meshes"][n["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            p = optlib._accessor_array(doc, binary, prim["attributes"]["POSITION"]).astype(float)
            p = (np.c_[p, np.ones(len(p))] @ m.T)[:, :3]
            idx = (optlib._accessor_array(doc, binary, prim["indices"]).reshape(-1, 3).astype(np.int64)
                   if "indices" in prim else np.arange(len(p)).reshape(-1, 3))
            uv = prim["attributes"].get("TEXCOORD_0")
            uvs.append(optlib._accessor_array(doc, binary, uv).astype(float) if uv is not None else None)
            vs.append(p @ GLTF_TO_ZUP)
            fs.append(idx + off)
            off += len(p)
    has_uv = bool(uvs) and all(u is not None for u in uvs)
    return {"nodes": count, "meshes": len(doc.get("meshes", [])), "materials": len(doc.get("materials", [])),
            "v": np.concatenate(vs) if vs else np.zeros((0, 3)), "f": np.concatenate(fs) if fs else np.zeros((0, 3), int),
            "uv": np.concatenate(uvs) if has_uv else None}


def area(v, f):
    t = v[f]
    return float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2)
