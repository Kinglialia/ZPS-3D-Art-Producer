"""Shared `custom` part functions: generic and parametrized, usable for many kinds of object (D33).
A function that only one asset needs goes into that project's production/assets/<id>/custom_parts.py instead.
Profiles lie in the Y-Z plane and extrude along X. FUNCTIONS is the set of shared names a `custom` part may use.
bmesh loads inside Blender or with the bpy module; without it this file still imports, so check_schema.py can read FUNCTIONS."""
import math

try:
    import bmesh
except ImportError:
    bmesh = None


def _profile(d, h, arch_h, seg):
    """Arch profile from front-bottom to back-bottom: vertical sides, then a half ellipse on top."""
    seg = int(seg)
    a, side_h = d / 2.0, h - arch_h
    pts = [(-a, 0.0), (-a, side_h)]
    for i in range(1, seg):
        t = math.pi * (1.0 - i / seg)
        pts.append((a * math.cos(t), side_h + arch_h * math.sin(t)))
    pts += [(a, side_h), (a, 0.0)]
    norms = [(-1.0, 0.0), (-1.0, 0.0)]
    for i in range(1, seg):
        t = math.pi * (1.0 - i / seg)
        nx, nz = math.cos(t) / a, math.sin(t) / arch_h
        L = math.hypot(nx, nz)
        norms.append((nx / L, nz / L))
    norms += [(1.0, 0.0), (1.0, 0.0)]
    return pts, norms, h


def _toward(p, o, dist):
    dy, dz = o[0] - p[0], o[1] - p[1]
    L = math.hypot(dy, dz)
    return (p[0] + dy / L * dist, p[1] + dz / L * dist)


def _plank_profile(d, h, arch_h, seg, gap, planks, depth):
    """_profile, and when there are grooves (planks >= 2, gap > 0, depth > 0) each seam vertex replaced by two lips
    gap apart. Seams split the seg arc steps into `planks` equal parts. Returns pts, norms, h and the index of the
    first lip of each pair."""
    pts, norms, h = _profile(d, h, arch_h, seg)
    seg, planks = int(seg), int(planks)
    if planks < 2 or gap <= 0 or depth <= 0:
        return pts, norms, h, []
    cut = {seg * j // planks + 1 for j in range(1, planks)}
    out, outn, lips = [], [], []
    for k, (p, n) in enumerate(zip(pts, norms)):
        if k not in cut:
            out.append(p)
            outn.append(n)
            continue
        if abs(n[0]) < 1e-9:
            # Apex: lips at apex height, so the top (bbox h) stays.
            a, b = (p[0] - gap / 2.0, p[1]), (p[0] + gap / 2.0, p[1])
        else:
            a, b = _toward(p, pts[k - 1], gap / 2.0), _toward(p, pts[k + 1], gap / 2.0)
        lips.append(len(out))
        out += [a, b]
        outn += [n, n]
    return out, outn, h, lips


def _centre(bm, h):
    bmesh.ops.translate(bm, vec=(0.0, 0.0, -h / 2.0), verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _bevel(bm, edges, r, seg):
    """Round toon edges: `seg` segments, radius r. No-op when r <= 0 or no edges."""
    if r <= 0 or not edges:
        return
    bmesh.ops.bevel(bm, geom=list(edges), offset=r, offset_type="OFFSET", segments=int(seg), profile=0.5,
                    affect="EDGES", clamp_overlap=True)


_BOX_EDGES = [("-X", "-Y"), ("-X", "+Y"), ("+X", "-Y"), ("+X", "+Y"), ("-X", "-Z"), ("-X", "+Z"),
              ("+X", "-Z"), ("+X", "+Z"), ("-Y", "-Z"), ("-Y", "+Z"), ("+Y", "-Z"), ("+Y", "+Z")]


def bevel_box(w, d, h, r, seg, mask):
    """Box with rounded edges. mask: bit k rounds the edge between the two faces _BOX_EDGES[k].
    Edges against another part stay sharp, so the joint has no notch."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    bm.normal_update()
    want = {frozenset(pair) for k, pair in enumerate(_BOX_EDGES) if int(mask) >> k & 1}

    def side(f):
        n = f.normal
        a = max(range(3), key=lambda i: abs(n[i]))
        return ("+" if n[a] > 0 else "-") + "XYZ"[a]
    _bevel(bm, [e for e in bm.edges if frozenset(side(f) for f in e.link_faces) in want], r, seg)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def vault(w, d, h, arch_h, seg, planks=1, gap=0.0, depth=0.0, r=0.0, bseg=2):
    """Solid arched prism, w along X: vertical sides h - arch_h high, then a half ellipse arch_h high (roofs, lids,
    tunnel vaults). planks >= 2 with gap > 0 and depth > 0: `planks` equal strips along the arc, split by grooves
    along X, gap wide and depth deep. r > 0: round the two long bottom edges; groove edges stay sharp."""
    pts, norms, h, lips = _plank_profile(d, h, arch_h, seg, gap, planks, depth)
    out = []
    for k, p in enumerate(pts):
        out.append(p)
        if k in lips:
            n = norms[k]
            q = pts[k + 1]
            out += [(p[0] - depth * n[0], p[1] - depth * n[1]), (q[0] - depth * n[0], q[1] - depth * n[1])]
    bm = bmesh.new()
    x0, x1 = -w / 2.0, w / 2.0
    left = [bm.verts.new((x0, y, z)) for y, z in out]
    right = [bm.verts.new((x1, y, z)) for y, z in out]
    n = len(out)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((left[i], left[j], right[j], right[i]))
    bm.faces.new(list(reversed(left)))
    bm.faces.new(right)
    _bevel(bm, [bm.edges.get((left[0], right[0])), bm.edges.get((left[-1], right[-1]))], r, bseg)
    return _centre(bm, h)


def _groove_centres(h, gap, rows, z0=0.0, pitch=0.0):
    """Heights of the rows - 1 groove centres from the bottom. pitch <= 0: rows equal bands over h.
    pitch > 0: the first centre at z0, then one every pitch. Grooves must not touch each other or the ends."""
    rows = int(rows)
    if pitch <= 0:
        zs = [h * j / rows for j in range(1, rows)]
    else:
        zs = [z0 + k * pitch for k in range(rows - 1)]
    edges = [0.0] + [e for z in zs for e in (z - gap / 2.0, z + gap / 2.0)] + [h]
    if any(b <= a for a, b in zip(edges, edges[1:])):
        raise ValueError(f"grooves {zs} of gap {gap} do not fit apart inside h {h}")
    return zs


def grooved_box(w, d, h, gap, depth, rows, z0=0.0, pitch=0.0):
    """Box with rows - 1 horizontal grooves, gap high and depth deep, around all four sides (board walls, stone
    courses, panel lines). Groove heights: _groove_centres. rows <= 1: a plain box."""
    g = gap / 2.0
    levels = [(0.0, 0.0)]
    for z in _groove_centres(h, gap, rows, z0, pitch):
        levels += [(z - g, 0.0), (z - g, depth), (z + g, depth), (z + g, 0.0)]
    levels.append((h, 0.0))
    bm = bmesh.new()
    loops = []
    for z, ins in levels:
        x, y = w / 2.0 - ins, d / 2.0 - ins
        loops.append([bm.verts.new(c) for c in ((-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z))])
    for lo, hi in zip(loops, loops[1:]):
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new((lo[k], lo[j], hi[j], hi[k]))
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    return _centre(bm, h)


FUNCTIONS = {f.__name__: f for f in (vault, grooved_box, bevel_box)}
