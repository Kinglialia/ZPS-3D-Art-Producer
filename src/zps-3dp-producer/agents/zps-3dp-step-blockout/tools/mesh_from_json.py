"""The approved builder of a `custom` part (D32.2): (verts, faces) -> numpy arrays for the kit's assembly, and the
reader of the JSON mesh that custom_mesh.py wrote. build_parts.py calls both, in plain Python or in Blender: no bmesh.
It reads numbers only; it never imports or runs custom_parts.py.

JSON: {"tool", "part", "fn", "args": [float], "source_sha256", "verts": [[x, y, z]], "faces": [[i, j, k, ...]]}.
errors() is the one validation of a closed mesh (every edge shared by exactly 2 faces): custom_mesh.py runs it before it writes, and read() again before Blender
builds, so a hand-edited file stops the build too. arrays() needs numpy and imports it only when it runs.
"""
import json
import math

TOOL = "blockout/custom_mesh"


def open_edges(faces):
    """Edges, by vertex index, that the faces do not use exactly twice: {(a, b): times used}, sorted."""
    used = {}
    for f in faces:
        for a, b in zip(f, [*f[1:], f[0]]):
            key = (min(a, b), max(a, b))
            used[key] = used.get(key, 0) + 1
    return {k: n for k, n in sorted(used.items()) if n != 2}


def errors(verts, faces):
    """Reasons the (verts, faces) pair is not a closed mesh, one line each (empty: valid)."""
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
    loose = None if errs else open_edges(faces)
    if loose:
        (a, b), n = next(iter(loose.items()))
        return [f"not closed: {len(loose)} edges are not shared by exactly 2 faces (first: vertices {a}-{b} "
                f"used {n} time{'s' if n != 1 else ''}); faces must share vertex indexes, not copies of a vertex"]
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


def _vector_area(verts, face):
    ax = ay = az = 0.0
    for a, b in zip(face, [*face[1:], face[0]]):
        (x1, y1, z1), (x2, y2, z2) = verts[a], verts[b]
        ax += y1 * z2 - z1 * y2
        ay += z1 * x2 - x1 * z2
        az += x1 * y2 - y1 * x2
    return ax / 2.0, ay / 2.0, az / 2.0


def orient(verts, faces):
    """The faces with one winding per shell, counter-clockwise seen from outside (a shell with negative volume is
    reversed). Faces must pass errors(): every edge used by exactly 2 faces."""
    faces = [list(f) for f in faces]
    owner = {}
    for i, f in enumerate(faces):
        for a, b in zip(f, [*f[1:], f[0]]):
            owner.setdefault((min(a, b), max(a, b)), []).append(i)
    shell = [None] * len(faces)
    for start in range(len(faces)):
        if shell[start] is not None:
            continue
        shell[start], todo, members = start, [start], [start]
        while todo:
            i = todo.pop()
            for a, b in zip(faces[i], [*faces[i][1:], faces[i][0]]):
                for j in owner[(min(a, b), max(a, b))]:
                    if shell[j] is not None:
                        continue
                    if any((a, b) == (c, e) for c, e in zip(faces[j], [*faces[j][1:], faces[j][0]])):
                        faces[j].reverse()
                    shell[j] = start
                    todo.append(j)
                    members.append(j)
        volume = sum(sum(p * q for p, q in zip(verts[faces[i][0]], _vector_area(verts, faces[i]))) for i in members)
        if volume < 0:
            for i in members:
                faces[i].reverse()
    return faces


def _ear_clip(verts, face):
    """Triangles of one planar polygon, by ear clipping on the plane of its largest projected area."""
    normal = _vector_area(verts, face)
    axis = max(range(3), key=lambda k: abs(normal[k]))
    keep = [k for k in range(3) if k != axis]
    flip = normal[axis] < 0
    pts = {i: (verts[i][keep[0]], verts[i][keep[1]]) for i in face}
    ring, tris = list(face), []

    def cross(o, a, b):
        c = (pts[a][0] - pts[o][0]) * (pts[b][1] - pts[o][1]) - (pts[a][1] - pts[o][1]) * (pts[b][0] - pts[o][0])
        return -c if flip else c

    while len(ring) > 3:
        for k in range(len(ring)):
            a, b, c = ring[k - 1], ring[k], ring[(k + 1) % len(ring)]
            if cross(a, b, c) <= 0:
                continue
            if any(p not in (a, b, c) and cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0
                   for p in ring):
                continue
            tris.append((a, b, c))
            del ring[k]
            break
        else:
            tris += [(ring[0], ring[k], ring[k + 1]) for k in range(1, len(ring) - 1)]
            return tris
    return [*tris, tuple(ring)]


def arrays(verts, faces):
    """(vertices, triangles) as numpy arrays for the kit's assembly: faces oriented outward, then triangulated (a face
    of 4 or more vertices is ear-clipped, so a concave face works if it is planar)."""
    import numpy as np
    out = []
    for f in orient(verts, faces):
        out += [tuple(f)] if len(f) == 3 else _ear_clip(verts, f)
    return np.array(verts, float), np.array(out, np.int64).reshape(-1, 3)
