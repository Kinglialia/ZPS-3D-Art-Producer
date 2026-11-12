"""Shared `custom` part functions: generic and parametrized, usable for many kinds of object (D32).
A function that only one asset needs goes into that project's production/assets/<id>/custom_parts.py instead.
Each function is plain Python (math only) and returns (verts, faces), like an asset function, so a graph that calls one
builds with no Blender. FUNCTIONS is the set of shared names a `custom` part may use."""
import math

_BOX_EDGES = [("-X", "-Y"), ("-X", "+Y"), ("+X", "-Y"), ("+X", "+Y"), ("-X", "-Z"), ("-X", "+Z"),
              ("+X", "-Z"), ("+X", "+Z"), ("-Y", "-Z"), ("-Y", "+Z"), ("+Y", "-Z"), ("+Y", "+Z")]
_NORMAL = {"-X": (-1.0, 0.0, 0.0), "+X": (1.0, 0.0, 0.0), "-Y": (0.0, -1.0, 0.0), "+Y": (0.0, 1.0, 0.0),
           "-Z": (0.0, 0.0, -1.0), "+Z": (0.0, 0.0, 1.0)}
_EPS = 1e-9


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return (v[0] / n, v[1] / n, v[2] / n)


def _planes(w, d, h, r, seg, mask):
    """(normal, offset) of every half-space of the rounded box: x is inside when normal . x <= offset. The six faces,
    plus `seg` chord planes along each selected edge: the chords of the quarter circle of radius r that joins the two
    faces, so the corners of the section sit on the circle."""
    half = {"X": w / 2.0, "Y": d / 2.0, "Z": h / 2.0}
    out = [(_NORMAL[s], half[s[1]]) for s in _NORMAL]
    step = math.pi / 2.0 / seg
    for k, (a, b) in enumerate(_BOX_EDGES):
        if not int(mask) >> k & 1:
            continue
        na, nb = _NORMAL[a], _NORMAL[b]
        centre = tuple(na[i] * (half[a[1]] - r) + nb[i] * (half[b[1]] - r) for i in range(3))
        for j in range(seg):
            mid = (j + 0.5) * step
            n = tuple(math.cos(mid) * na[i] + math.sin(mid) * nb[i] for i in range(3))
            out.append((n, _dot(centre, n) + r * math.cos(step / 2.0)))
    return out


def _facet(n, off, planes, big):
    """The polygon of the plane (n, off) inside every other half-space, wound counter-clockwise seen from outside."""
    up = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _unit(_cross(up, n))
    v = _cross(n, u)
    c = (n[0] * off, n[1] * off, n[2] * off)
    poly = [tuple(c[i] + big * (su * u[i] + sv * v[i]) for i in range(3)) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for m, mo in planes:
        if m is n:
            continue
        side = [_dot(m, p) - mo for p in poly]
        clipped = []
        for i, p in enumerate(poly):
            q, sp, sq = poly[i - 1], side[i], side[i - 1]
            if (sp > _EPS) != (sq > _EPS):
                t = sq / (sq - sp)
                clipped.append(tuple(q[j] + t * (p[j] - q[j]) for j in range(3)))
            if sp <= _EPS:
                clipped.append(p)
        poly = clipped
        if len(poly) < 3:
            return []
    return poly


def bevel_box(w, d, h, r, seg, mask):
    """Box with rounded edges. mask: bit k rounds the edge between the two faces _BOX_EDGES[k], with `seg` segments of
    radius r (r is cut down to half the shortest side). Edges against another part stay sharp, so the joint has no notch.
    The box keeps its bbox w x d x h and the mesh is closed. r <= 0 or mask 0 gives the plain box (8 vertices, 6 faces)."""
    seg = max(1, int(seg))
    r = min(float(r), min(w, d, h) / 2.0)
    planes = _planes(w, d, h, r, seg, mask if r > 0 else 0)
    big = 4.0 * (w + d + h)
    tol = 1e-7 * max(w, d, h)
    verts, faces = [], []
    for n, off in planes:
        ring = []
        for p in _facet(n, off, planes, big):
            i = next((k for k, q in enumerate(verts) if max(abs(p[j] - q[j]) for j in range(3)) <= tol), None)
            if i is None:
                verts.append(p)
                i = len(verts) - 1
            if not ring or ring[-1] != i:
                ring.append(i)
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) >= 3 and len(set(ring)) == len(ring):
            faces.append(tuple(ring))
    return verts, faces


FUNCTIONS = {f.__name__: f for f in (bevel_box,)}
