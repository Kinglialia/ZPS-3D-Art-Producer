"""The approved builder of an asset part (D32.2): one JSON mesh that custom_mesh.py wrote -> a bmesh.
build_parts.py calls it inside Blender. It reads numbers only; it never imports or runs custom_parts.py.

JSON: {"tool", "part", "fn", "args": [float], "source_sha256", "verts": [[x, y, z]], "faces": [[i, j, k, ...]]}.
errors() is the one validation of a mesh: custom_mesh.py runs it before it writes, and read() again before Blender
builds, so a hand-edited file stops the build too. Plain Python except to_bmesh().
"""
import json
import math

TOOL = "blockout/custom_mesh"


def errors(verts, faces):
    """Reasons the (verts, faces) pair is not a mesh, one line each (empty: valid)."""
    if not isinstance(verts, (list, tuple)) or not verts:
        return ["verts must be a non-empty list of [x, y, z]"]
    if not isinstance(faces, (list, tuple)) or not faces:
        return ["faces must be a non-empty list of vertex index lists"]
    errs = [f"verts[{i}] must be 3 finite numbers" for i, v in enumerate(verts)
            if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(
                isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in v))]
    n = len(verts)
    for i, f in enumerate(faces):
        if not (isinstance(f, (list, tuple)) and len(f) >= 3 and all(
                isinstance(k, int) and not isinstance(k, bool) and 0 <= k < n for k in f)):
            errs.append(f"faces[{i}] must hold >= 3 vertex indexes in 0..{n - 1}")
        elif len(set(f)) != len(f):
            errs.append(f"faces[{i}] repeats a vertex")
    return errs


def read(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or doc.get("tool") != TOOL:
        raise ValueError(f"{path}: not a mesh of {TOOL}")
    errs = errors(doc.get("verts"), doc.get("faces"))
    if errs:
        raise ValueError(f"{path}: {'; '.join(errs[:3])}")
    return doc


def to_bmesh(doc):
    import bmesh
    bm = bmesh.new()
    vs = [bm.verts.new([float(c) for c in v]) for v in doc["verts"]]
    for f in doc["faces"]:
        bm.faces.new([vs[k] for k in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm
