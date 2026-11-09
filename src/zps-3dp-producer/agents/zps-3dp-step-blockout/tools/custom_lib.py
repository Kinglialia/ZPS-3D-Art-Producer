"""`custom` part functions the user approved (D27.13). Source: run 4 wooden-chest, model v2 parts_lib.py, without arch_band.
Profiles lie in the Y-Z plane and extrude along X. FUNCTIONS is the only set of names a `custom` part may use.
bmesh loads inside Blender or with the bpy module; without it this file still imports, so check_schema.py can read FUNCTIONS."""
import math

try:
    import bmesh
except ImportError:
    bmesh = None


def _profile(d, h, arch_h, seg):
    """Lid end profile from front-bottom to back-bottom: vertical sides, then a half ellipse on top."""
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


def vault(w, d, h, arch_h, seg):
    """Solid lid: closed prism of the lid profile, w along X."""
    pts, _, h = _profile(d, h, arch_h, seg)
    bm = bmesh.new()
    x0, x1 = -w / 2.0, w / 2.0
    left = [bm.verts.new((x0, y, z)) for y, z in pts]
    right = [bm.verts.new((x1, y, z)) for y, z in pts]
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((left[i], left[j], right[j], right[i]))
    bm.faces.new(list(reversed(left)))
    bm.faces.new(right)
    return _centre(bm, h)


def arch_cap(w, d, h, arch_h, band, panel, side, seg, gap=0.0, depth=0.0, planks=0.0, r=0.0, bseg=2):
    """Lid end cap: arch rim of width `band` and depth w, with a recessed end panel `panel` thick on the lid side.
    side +1: the lid is toward +X; side -1: toward -X. Open at the bottom like arch_band.
    gap, depth, planks: the lid's plank grooves (plank_vault). The cap profile then has the same lips, and the
    lid-side face closes each groove end with its own face, so the join keeps it while the rest is hidden.
    r > 0: round the outer and inner arch edges of the outer face (x_out)."""
    if gap > 0 and planks >= 2:
        pts, norms, h, lips = _plank_profile(d, h, arch_h, seg, gap, planks)
    else:
        (pts, norms, h), lips = _profile(d, h, arch_h, seg), []
    inner = [(y - band * ny, z - band * nz) for (y, z), (ny, nz) in zip(pts, norms)]
    inner[0] = (pts[0][0] + band, 0.0)
    inner[-1] = (pts[-1][0] - band, 0.0)
    s = 1.0 if side > 0 else -1.0
    x_in, x_out = s * w / 2.0, -s * w / 2.0
    x_mid = x_in - s * panel
    bm = bmesh.new()
    oi = [bm.verts.new((x_in, y, z)) for y, z in pts]
    oo = [bm.verts.new((x_out, y, z)) for y, z in pts]
    io = [bm.verts.new((x_out, y, z)) for y, z in inner]
    im = [bm.verts.new((x_mid, y, z)) for y, z in inner]
    n = len(pts)
    ring = []
    for k, v in enumerate(oi):
        ring.append(v)
        if k in lips:
            nk = norms[k]
            ia = bm.verts.new((x_in, pts[k][0] - depth * nk[0], pts[k][1] - depth * nk[1]))
            ib = bm.verts.new((x_in, pts[k + 1][0] - depth * nk[0], pts[k + 1][1] - depth * nk[1]))
            ring += [ia, ib]
            bm.faces.new((oi[k], oi[k + 1], ib, ia))
    bm.faces.new(ring)
    bm.faces.new(im)
    for k in range(n - 1):
        bm.faces.new((oo[k], oo[k + 1], io[k + 1], io[k]))
        bm.faces.new((oo[k], oi[k], oi[k + 1], oo[k + 1]))
        bm.faces.new((io[k], io[k + 1], im[k + 1], im[k]))
    # Bottom as three quads (front leg, panel, back leg): the join then keeps a leg bottom that shows
    # past a rounded post corner instead of deleting one big mostly hidden face.
    bm.faces.new((oo[0], io[0], im[0], oi[0]))
    bm.faces.new((oi[0], im[0], im[-1], oi[-1]))
    bm.faces.new((im[-1], io[-1], oo[-1], oi[-1]))
    _bevel(bm, [bm.edges.get((a[k], a[k + 1])) for a in (oo, io) for k in range(n - 1)], r, bseg)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    return _centre(bm, h)


def grooved_box(w, d, h, gap, depth, z1, z2):
    """Body box with two horizontal plank grooves around all four sides. Groove centres at z1, z2 from the bottom."""
    g = gap / 2.0
    levels = [(0.0, 0.0), (z1 - g, 0.0), (z1 - g, depth), (z1 + g, depth), (z1 + g, 0.0),
              (z2 - g, 0.0), (z2 - g, depth), (z2 + g, depth), (z2 + g, 0.0), (h, 0.0)]
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


def _toward(p, o, dist):
    dy, dz = o[0] - p[0], o[1] - p[1]
    L = math.hypot(dy, dz)
    return (p[0] + dy / L * dist, p[1] + dz / L * dist)


def _plank_profile(d, h, arch_h, seg, gap, planks):
    """_profile with each plank-seam vertex (arc split into `planks` equal parts) replaced by two lips `gap` apart.
    Returns pts, norms, h and the index of the first lip of each pair."""
    pts, norms, h = _profile(d, h, arch_h, seg)
    seg, planks = int(seg), int(planks)
    cut = {seg * j // planks + 1 for j in range(1, planks)}
    out, outn, lips = [], [], []
    for k, (p, n) in enumerate(zip(pts, norms)):
        if k not in cut:
            out.append(p)
            outn.append(n)
            continue
        if abs(n[0]) < 1e-9:
            # Apex: lips at apex height, so the lid top (bbox h) stays.
            a, b = (p[0] - gap / 2.0, p[1]), (p[0] + gap / 2.0, p[1])
        else:
            a, b = _toward(p, pts[k - 1], gap / 2.0), _toward(p, pts[k + 1], gap / 2.0)
        lips.append(len(out))
        out += [a, b]
        outn += [n, n]
    return out, outn, h, lips


def plank_vault(w, d, h, arch_h, seg, gap, depth, planks, r=0.0, bseg=2):
    """Lid like vault, with grooves along X between the lip pairs of _plank_profile, `depth` deep.
    r > 0: round the two long bottom edges (front and back lower lid edges); groove edges stay sharp."""
    pts, norms, h, lips = _plank_profile(d, h, arch_h, seg, gap, planks)
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


def strap_band(w, d, h, arch_h, seg, t, embed, r=0.0, bseg=2):
    """Lid strap as a band `t` thick lying on the lid: d, h, arch_h are the outer sizes (lid + 2t, lid + t,
    lid arch + t). The inner face is the lid profile moved `embed` into the lid (a face exactly on the lid
    surface breaks the union used by the gates); over a lid groove it bridges the groove opening.
    Open at the bottom. The strap sides are only the visible strips, so the join keeps them;
    r > 0 rounds their outer edges."""
    pts, norms, _ = _profile(d - 2.0 * t, h - t, arch_h - t, seg)
    outer = [(y + t * ny, z + t * nz) for (y, z), (ny, nz) in zip(pts, norms)]
    pts = [(y - embed * ny, z - embed * nz) for (y, z), (ny, nz) in zip(pts, norms)]
    bm = bmesh.new()
    x0, x1 = -w / 2.0, w / 2.0
    o0 = [bm.verts.new((x0, y, z)) for y, z in outer]
    o1 = [bm.verts.new((x1, y, z)) for y, z in outer]
    i0 = [bm.verts.new((x0, y, z)) for y, z in pts]
    i1 = [bm.verts.new((x1, y, z)) for y, z in pts]
    n = len(pts)
    for k in range(n - 1):
        bm.faces.new((o0[k], o1[k], o1[k + 1], o0[k + 1]))
        bm.faces.new((i0[k], i0[k + 1], i1[k + 1], i1[k]))
        bm.faces.new((o0[k], o0[k + 1], i0[k + 1], i0[k]))
        bm.faces.new((o1[k], i1[k], i1[k + 1], o1[k + 1]))
    for k in (0, n - 1):
        bm.faces.new((o0[k], i0[k], i1[k], o1[k]))
    _bevel(bm, [bm.edges.get((a[k], a[k + 1])) for a in (o0, o1) for k in range(n - 1)], r, bseg)
    return _centre(bm, h)


def _quad_tris(bm, a, b, c, d, uv):
    """Two triangles for a planar quad; picks the diagonal that keeps both the same winding (concave quads)."""
    def area(p, q, r):
        return (uv[q][0] - uv[p][0]) * (uv[r][1] - uv[p][1]) - (uv[q][1] - uv[p][1]) * (uv[r][0] - uv[p][0])
    s1, s2 = area(a, b, c), area(a, c, d)
    if s1 * s2 > 0:
        bm.faces.new((a, b, c))
        bm.faces.new((a, c, d))
    else:
        bm.faces.new((a, b, d))
        bm.faces.new((b, c, d))


def lock_plate(w, d, h, chamfer, key_r, key_z, key_drop, key_tail, key_depth, r=0.0, bseg=2):
    """Lock plate: w x h octagon (corners cut by `chamfer`), d thick along Y, front at -Y.
    Keyhole recess `key_depth` deep: round head radius key_r centred key_z above the plate centre,
    tail widening to half-width key_tail at key_drop below the head centre."""
    W, H, c = w / 2.0, h / 2.0, chamfer
    oct2 = [(W, -H + c), (W, H - c), (W - c, H), (-W + c, H), (-W, H - c), (-W, -H + c), (-W + c, -H), (W - c, -H)]
    key2 = [(key_r * math.cos(math.radians(t)), key_z + key_r * math.sin(math.radians(t)))
            for t in (300, 0, 60, 120, 180, 240)]
    key2 += [(-key_tail, key_z - key_drop), (key_tail, key_z - key_drop)]
    yf, yb, yk = -d / 2.0, d / 2.0, -d / 2.0 + key_depth
    bm = bmesh.new()
    of = [bm.verts.new((x, yf, z)) for x, z in oct2]
    ob = [bm.verts.new((x, yb, z)) for x, z in oct2]
    kf = [bm.verts.new((x, yf, z)) for x, z in key2]
    kb = [bm.verts.new((x, yk, z)) for x, z in key2]
    uv = {v: (v.co.x, v.co.z) for v in of + kf}
    for i in range(8):
        j = (i + 1) % 8
        _quad_tris(bm, of[i], of[j], kf[j], kf[i], uv)
        bm.faces.new((of[i], ob[i], ob[j], of[j]))
        bm.faces.new((kf[i], kf[j], kb[j], kb[i]))
    back = bm.faces.new(list(reversed(ob)))
    floor = bm.faces.new(kb)
    bmesh.ops.triangulate(bm, faces=[back, floor], quad_method="BEAUTY", ngon_method="BEAUTY")
    _bevel(bm, [bm.edges.get((of[i], of[(i + 1) % 8])) for i in range(8)], r, bseg)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


FUNCTIONS = {f.__name__: f for f in (vault, arch_cap, grooved_box, plank_vault, bevel_box, strap_band, lock_plate)}
