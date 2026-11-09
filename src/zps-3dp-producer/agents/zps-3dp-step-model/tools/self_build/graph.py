"""Part-graph solver and mesh helpers shared by the self_build tools. Pure Python (numpy,
trimesh, manifold3d); bmesh is imported only to run `custom` part functions from parts_lib.py.

Coordinates follow references/self_build.md: metres, +Z up, front faces -Y. Part numbers shown
to people (renders, --upto) are 1-based in build order.

A solved part is a dict:
  index (1-based), name, primitive, verts (N,3 world), tris (M,3), lo, hi (world AABB),
  declared (extents the dims declare, after rotation, or None), parent (name or None),
  attach (as written), contact {axis, sign} (the child's face on side -sign of axis touches the
  parent's face on side +sign; None for the root and through_axis), depth (inset_into only).
"""
import hashlib
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import raster  # noqa: E402

AXES = {"X": 0, "Y": 1, "Z": 2}
IN_PLANE = {0: (1, 2), 1: (0, 2), 2: (0, 1)}   # offset_uv order for ±X, ±Y, ±Z faces
ORTHO_VIEWS = ("front", "back", "left", "right", "top", "bottom")


class GraphError(Exception):
    """A part graph that cannot be built as written (bad name, bad attach, bad dims)."""


# ------------------------------------------------------------------ files
def graph_dir(work, rollout=None):
    return os.path.join(work, "rollouts", str(rollout)) if rollout is not None else work


def load_graph(gdir):
    import json
    path = os.path.join(gdir, "part_graph.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_graph(gdir, graph):
    import json
    with open(os.path.join(gdir, "part_graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
        f.write("\n")


def code_hash(gdir):
    """sha256 of part_graph.json followed by parts_lib.py (missing file = empty)."""
    h = hashlib.sha256()
    for name in ("part_graph.json", "parts_lib.py"):
        p = os.path.join(gdir, name)
        h.update(name.encode())
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def load_parts_lib(gdir):
    path = os.path.join(gdir, "parts_lib.py")
    if not os.path.isfile(path):
        return None
    try:
        import bpy  # noqa: F401  (with the bpy pip module, bmesh/mathutils load only after bpy)
    except ImportError:
        pass
    name = "parts_lib_" + hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ values
def value(v, params, what):
    """A literal number or a param name."""
    if isinstance(v, str):
        if v not in params:
            raise GraphError(f"{what}: unknown param '{v}'")
        return float(params[v])
    if isinstance(v, (int, float)):
        return float(v)
    raise GraphError(f"{what}: expected a number or param name, got {v!r}")


def dim(v, params, what):
    """Dimensions must be param names (self_build.md: parts never hold raw sizes)."""
    if not isinstance(v, str):
        raise GraphError(f"{what}: dimensions must be param names, got {v!r}")
    return value(v, params, what)


def parse_face(s, what):
    if not (isinstance(s, str) and len(s) == 2 and s[0] in "+-" and s[1] in AXES):
        raise GraphError(f"{what}: expected one of ±X/±Y/±Z, got {s!r}")
    return AXES[s[1]], (1 if s[0] == "+" else -1)


def expand_parts(graph):
    """Parts with mirror_of copies filled in from their source (shape fields only)."""
    by_name, out = {}, []
    for i, p in enumerate(graph.get("parts", [])):
        if "name" not in p:
            raise GraphError(f"part #{i + 1} has no name")
        if p["name"] in by_name:
            raise GraphError(f"duplicate part name '{p['name']}'")
        q = dict(p)
        att = p.get("attach") or {}
        if att.get("type") == "mirror_of":
            src = by_name.get(att.get("of"))
            if src is None:
                raise GraphError(f"{p['name']}: mirror_of '{att.get('of')}' is not listed earlier")
            for k in ("primitive", "dims", "fn", "args", "segments", "axis", "rotation_deg"):
                if k in src and k not in q:
                    q[k] = src[k]
        by_name[p["name"]] = q
        out.append(q)
    return out


def fit_params(graph):
    """Params param_fit may change: floats only. Integers are segment counts and are never fitted."""
    return [k for k, v in graph.get("params", {}).items()
            if isinstance(v, float) and not isinstance(v, bool)]


def part_params(graph, name):
    """Param names one part references (dims, args, inset, depth, offset_uv); mirrors follow their source."""
    parts = {p["name"]: p for p in expand_parts(graph)}
    if name not in parts:
        raise GraphError(f"unknown part '{name}'")
    p = parts[name]
    refs = list(p.get("dims", [])) + list(p.get("args", []))
    att = p.get("attach") or {}
    refs += [att.get("inset"), att.get("depth")] + list(att.get("offset_uv", []) or [])
    return [r for r in refs if isinstance(r, str) and r in graph.get("params", {})]


# ------------------------------------------------------------------ primitives
def box(w, d, h):
    import trimesh
    m = trimesh.creation.box(extents=(w, d, h))
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def cylinder(radius, height, segments, axis):
    import trimesh
    m = trimesh.creation.cylinder(radius=radius, height=height, sections=int(segments))
    v = np.asarray(m.vertices, float)
    if axis == 0:      # Z -> X
        v = v[:, [2, 1, 0]] * [1, 1, -1]
    elif axis == 1:    # Z -> Y
        v = v[:, [0, 2, 1]] * [1, 1, -1]
    t = np.asarray(m.faces, np.int64)
    return v, t


def wedge(w, d, h):
    """Bottom w x d; slope rises toward +Y (full height h at the +Y face, zero at -Y)."""
    x, y, z = w / 2, d / 2, h / 2
    v = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],   # bottom 0-3
                  [-x, y, z], [x, y, z]], float)                           # top ridge at +Y 4-5
    t = np.array([[0, 2, 1], [0, 3, 2],          # bottom (normal -Z)
                  [3, 4, 5], [3, 5, 2],          # back (+Y)
                  [0, 1, 5], [0, 5, 4],          # slope
                  [0, 4, 3],                     # -X side
                  [1, 2, 5]], np.int64)          # +X side
    return v, t


def bmesh_arrays(bm):
    """Vertices and triangles of a BMesh (triangulated by loop triangles), then frees it."""
    bm.verts.index_update()
    tris = bm.calc_loop_triangles()
    v = np.array([tuple(x.co) for x in bm.verts], float)
    t = np.array([[l.vert.index for l in tri] for tri in tris], np.int64).reshape(-1, 3)
    bm.free()
    return v, t


def rotate_z(v, deg):
    k = int(round(deg / 90.0)) % 4
    for _ in range(k):
        v = np.stack([-v[:, 1], v[:, 0], v[:, 2]], axis=1)
    return v


def local_mesh(p, params, lib, coarse, warnings):
    """Mesh of one part centred on its own bbox, rotated, plus its declared extents."""
    name, prim = p["name"], p.get("primitive")
    dims = [dim(x, params, f"{name}.dims") for x in p.get("dims", [])]
    declared = None
    if prim == "box" or prim == "wedge":
        if len(dims) != 3:
            raise GraphError(f"{name}: {prim} needs dims [w, d, h]")
        if min(dims) <= 0:
            raise GraphError(f"{name}: dims must be > 0, got {dims}")
        v, t = box(*dims) if prim == "box" else wedge(*dims)
        declared = list(dims)
    elif prim == "cylinder":
        if len(dims) != 2:
            raise GraphError(f"{name}: cylinder needs dims [radius, height]")
        if min(dims) <= 0:
            raise GraphError(f"{name}: dims must be > 0, got {dims}")
        seg = p.get("segments", 12)
        seg = int(round(value(seg, params, f"{name}.segments")))
        if not 8 <= seg <= 24:
            warnings.append(f"{name}: segments {seg} outside 8-24")
        axis = AXES.get(p.get("axis", "Z"))
        if axis is None:
            raise GraphError(f"{name}: axis must be X, Y or Z")
        v, t = cylinder(dims[0], dims[1], seg, axis)
        declared = [2 * dims[0]] * 3
        declared[axis] = dims[1]
    elif prim == "custom":
        if lib is None:
            raise GraphError(f"{name}: custom part but no parts_lib.py")
        fn = getattr(lib, p.get("fn", ""), None)
        if fn is None:
            raise GraphError(f"{name}: parts_lib.py has no function '{p.get('fn')}'")
        args = [value(a, params, f"{name}.args") if isinstance(a, str) else a for a in p.get("args", [])]
        v, t = bmesh_arrays(fn(*args))
        if len(t) == 0:
            raise GraphError(f"{name}: {p.get('fn')} returned an empty mesh")
        c = (v.min(0) + v.max(0)) / 2
        if np.abs(c).max() > 1e-3:
            warnings.append(f"{name}: {p.get('fn')} is not centred on its bbox (off by "
                            f"{np.round(c, 4).tolist()} m); recentred")
        v = v - c
        if dims:
            declared = list(dims)
        elif len(p.get("args", [])) >= 3:
            declared = [float(x) for x in args[:3]]   # convention: first three args are w, d, h
        if coarse:
            v, t = box(*(v.max(0) - v.min(0)))
    else:
        raise GraphError(f"{name}: unknown primitive {prim!r}")
    rot = p.get("rotation_deg", 0) or 0
    if rot % 90:
        raise GraphError(f"{name}: rotation_deg must be a multiple of 90")
    if rot:
        v = rotate_z(v, rot)
        if declared and int(round(rot / 90)) % 2:
            declared = [declared[1], declared[0], declared[2]]
    return v, t, declared


# ------------------------------------------------------------------ placement
def place(ext, att, lo, hi, params, name):
    """Centre of a child with extents ext attached to a parent AABB (lo, hi).
    Returns (centre, contact, depth)."""
    pc, pe = (lo + hi) / 2, hi - lo
    c = pc.copy()
    t = att.get("type")

    def offsets(axes):
        uv = att.get("offset_uv", [0, 0]) or [0, 0]
        if len(uv) != 2:
            raise GraphError(f"{name}: offset_uv needs two values")
        for k, a in enumerate(axes):
            u = value(uv[k], params, f"{name}.offset_uv")
            c[a] = pc[a] + u * (pe[a] - ext[a]) / 2

    def bound(a, s):
        return hi[a] if s > 0 else lo[a]

    if t == "on_top":
        c[2] = hi[2] + ext[2] / 2
        offsets((0, 1))
        return c, {"axis": 2, "sign": 1}, None
    if t in ("center_on_face", "flush_edge", "inset_into"):
        a, s = parse_face(att.get("face"), f"{name}.face")
        if t == "inset_into":
            depth = value(att.get("depth"), params, f"{name}.depth")
            c[a] = bound(a, s) + s * (ext[a] / 2 - depth)
        else:
            depth = None
            c[a] = bound(a, s) + s * ext[a] / 2
        if t == "flush_edge":
            e, se = parse_face(att.get("edge"), f"{name}.edge")
            if e == a:
                raise GraphError(f"{name}: edge must be perpendicular to face")
            inset = value(att.get("inset", 0), params, f"{name}.inset")
            c[e] = bound(e, se) - se * (inset + ext[e] / 2)
        else:
            offsets(IN_PLANE[a])
        return c, {"axis": a, "sign": s}, depth
    if t == "through_axis":
        a = AXES.get(att.get("axis"))
        if a is None:
            raise GraphError(f"{name}: through_axis needs axis X, Y or Z")
        offsets(IN_PLANE[a])
        return c, None, None
    raise GraphError(f"{name}: unknown attach type {t!r}")


def solve(graph, lib=None, params=None, upto=None, coarse=False, warnings=None):
    """Build and place every part (or the first `upto`). Returns a list of solved parts."""
    params = dict(graph.get("params", {}) if params is None else params)
    warnings = warnings if warnings is not None else []
    parts = expand_parts(graph)
    if not parts:
        raise GraphError("part graph has no parts")
    n = len(parts) if upto is None else upto
    solved, by_name, root = [], {}, None
    for i, p in enumerate(parts[:n]):
        name, att = p["name"], p.get("attach")
        if att and att.get("type") == "mirror_of":
            src = by_name.get(att.get("of"))
            plane = AXES.get(att.get("plane"))
            if plane not in (0, 1):
                raise GraphError(f"{name}: mirror plane must be X or Y")
            v = src["verts"].copy()
            cen = (root["lo"][plane] + root["hi"][plane]) / 2
            v[:, plane] = 2 * cen - v[:, plane]
            t = src["tris"][:, ::-1].copy()
            contact = dict(src["contact"]) if src["contact"] else None
            if contact and contact["axis"] == plane:
                contact["sign"] = -contact["sign"]
            declared, parent, depth = src["declared"], src["parent"], src["depth"]
        else:
            lv, t, declared = local_mesh(p, params, lib, coarse, warnings)
            ext = lv.max(0) - lv.min(0)
            if not att:
                if i != 0:
                    raise GraphError(f"{name}: only the first part may have attach null")
                centre, contact, parent, depth = np.array([0, 0, ext[2] / 2]), None, None, None
            else:
                parent = att.get("to")
                if parent not in by_name:
                    raise GraphError(f"{name}: attach.to '{parent}' is not listed earlier")
                uv = att.get("offset_uv")
                if uv and any(isinstance(u, (int, float)) and abs(u) > 1 for u in uv):
                    warnings.append(f"{name}: offset_uv {uv} outside -1..1 (part overhangs the face)")
                pp = by_name[parent]
                centre, contact, depth = place(ext, att, pp["lo"], pp["hi"], params, name)
            v = lv + centre
        sp = {"index": i + 1, "name": name, "primitive": p.get("primitive"), "verts": v, "tris": t,
              "lo": v.min(0), "hi": v.max(0), "declared": declared, "parent": parent,
              "attach": att, "contact": contact, "depth": depth}
        solved.append(sp)
        by_name[name] = sp
        if root is None:
            root = sp
    return solved


def concat(parts):
    vs, ts, off = [], [], 0
    for p in parts:
        vs.append(p["verts"])
        ts.append(p["tris"] + off)
        off += len(p["verts"])
    return np.concatenate(vs), np.concatenate(ts)


# ------------------------------------------------------------------ manifold
def to_manifold(v, t):
    import manifold3d as m3d
    mesh = m3d.Mesh(vert_properties=np.ascontiguousarray(v, np.float32),
                    tri_verts=np.ascontiguousarray(t, np.uint32))
    mesh.merge()
    return m3d.Manifold(mesh)


def is_manifold(v, t):
    import manifold3d as m3d
    m = to_manifold(v, t)
    return m.status() == m3d.Error.NoError and not m.is_empty()


def from_manifold(m):
    out = m.to_mesh()
    return np.asarray(out.vert_properties[:, :3], float), np.asarray(out.tri_verts, np.int64)


def union(meshes):
    """manifold3d union of [(v, t)]. Falls back to a plain join when any input is not a closed
    manifold. Returns (v, t, method, bad_indices)."""
    import manifold3d as m3d
    mans, bad = [], []
    for i, (v, t) in enumerate(meshes):
        m = to_manifold(v, t)
        if m.status() != m3d.Error.NoError or m.is_empty():
            bad.append(i)
        mans.append(m)
    if bad:
        vs, ts, off = [], [], 0
        for v, t in meshes:
            vs.append(v)
            ts.append(t + off)
            off += len(v)
        return np.concatenate(vs), np.concatenate(ts), "join", bad
    u = mans[0] if len(mans) == 1 else m3d.Manifold.batch_boolean(mans, m3d.OpType.Add)
    v, t = from_manifold(u)
    return v, t, "manifold3d", []


def volume(v, t):
    return float(to_manifold(v, t).volume())


def intersection_volume(a, b):
    import manifold3d as m3d
    ma, mb = to_manifold(*a), to_manifold(*b)
    if ma.status() != m3d.Error.NoError or mb.status() != m3d.Error.NoError:
        return None
    return float((ma ^ mb).volume())


# ------------------------------------------------------------------ mesh measures
def components(v, t):
    """List of (verts_idx, tris_idx) per connected component (shared vertices, after welding)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    v, t = weld(v, t)
    n = len(v)
    if len(t) == 0:
        return v, t, []
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    k, lab = connected_components(g, directed=False)
    tri_lab = lab[t[:, 0]]
    comps = [np.nonzero(tri_lab == c)[0] for c in range(k)]
    return v, t, [c for c in comps if len(c)]


def weld(v, t, tol=1e-6):
    q = np.round(np.asarray(v) / tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return np.asarray(v)[first], inv[np.asarray(t)]


def floaters(v, t, span_ratio):
    """Components besides the largest whose bbox longest edge >= span_ratio x object size."""
    v, t, comps = components(v, t)
    if not comps:
        return 0, []
    size = float((v.max(0) - v.min(0)).max())
    info = []
    for c in comps:
        cv = v[np.unique(t[c])]
        info.append({"tris": int(len(c)), "span": float((cv.max(0) - cv.min(0)).max()),
                     "lo": cv.min(0).round(4).tolist(), "hi": cv.max(0).round(4).tolist()})
    main = max(range(len(info)), key=lambda i: info[i]["tris"])
    rest = [c for i, c in enumerate(info) if i != main and c["span"] >= span_ratio * size]
    return len(rest), rest


def health(v, t, area_eps=1e-12):
    v, t = weld(v, t)
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    area = 0.5 * np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1)
    used = np.zeros(len(v), bool)
    used[t.ravel()] = True
    return {"non_manifold_edges": int((counts != 2).sum()),
            "zero_area_faces": int((area < area_eps).sum()),
            "loose_verts": int((~used).sum()),
            "tris": int(len(t)), "verts": int(len(v))}


def point_mesh_distance(p, v, t, chunk=200000):
    """Unsigned distance from each point to the triangle mesh (numpy, no spatial index)."""
    p = np.asarray(p, float)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    out = np.full(len(p), np.inf)
    step = max(1, chunk // max(1, len(t)))
    for s in range(0, len(p), step):
        q = p[s:s + step, None, :]
        d = _closest_on_tri(q, a[None], b[None], c[None]) - q
        out[s:s + step] = np.sqrt((d * d).sum(-1)).min(1)
    return out


def _closest_on_tri(p, a, b, c):
    """Closest point on triangles abc to p (Ericson, Real-Time Collision Detection 5.1.5), broadcast."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - b
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - c
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
    v_ = vb / denom
    w_ = vc / denom
    res = a + ab * v_[..., None] + ac * w_[..., None]           # inside face

    def put(cond, val):
        nonlocal res
        res = np.where(cond[..., None], val, res)

    # edges (later regions override earlier ones only where their condition holds)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), b + (c - b) * np.nan_to_num(t_bc)[..., None])
        t_ac = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * np.nan_to_num(t_ac)[..., None])
        t_ab = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * np.nan_to_num(t_ab)[..., None])
    put((d6 >= 0) & (d5 <= d6), np.broadcast_to(c, res.shape))
    put((d3 >= 0) & (d4 <= d3), np.broadcast_to(b, res.shape))
    put((d1 <= 0) & (d2 <= 0), np.broadcast_to(a, res.shape))
    return res


def winding_number(p, v, t):
    """Generalised winding number (~1 inside a closed mesh, ~0 outside)."""
    p = np.asarray(p, float)
    out = np.zeros(len(p))
    step = max(1, 200000 // max(1, len(t)))
    for s in range(0, len(p), step):
        q = p[s:s + step, None, :]
        a, b, c = v[t[:, 0]][None] - q, v[t[:, 1]][None] - q, v[t[:, 2]][None] - q
        la, lb, lc = (np.linalg.norm(x, axis=-1) for x in (a, b, c))
        num = (a * np.cross(b, c)).sum(-1)
        den = la * lb * lc + (a * b).sum(-1) * lc + (b * c).sum(-1) * la + (c * a).sum(-1) * lb
        out[s:s + step] = np.arctan2(num, den).sum(1) / (2 * np.pi)
    return out


# ------------------------------------------------------------------ glb io (Z-up <-> glTF Y-up)
def save_glb(path, v, t):
    import trimesh
    v = np.asarray(v, float)
    yup = np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    trimesh.Trimesh(yup, np.asarray(t), process=False).export(path, file_type="glb")


def load_glb(path):
    """All meshes of a glTF/GLB, transforms applied, as one Z-up (v, t) and per-geometry list."""
    import trimesh
    scene = trimesh.load(path, force="scene", process=False)
    pieces = []
    for node in scene.graph.nodes_geometry:
        tf, gname = scene.graph[node]
        g = scene.geometry[gname]
        if not hasattr(g, "faces") or len(g.faces) == 0:
            continue
        vv = trimesh.transform_points(np.asarray(g.vertices, float), tf)
        z = np.stack([vv[:, 0], -vv[:, 2], vv[:, 1]], axis=1)
        pieces.append((gname, z, np.asarray(g.faces, np.int64)))
    if not pieces:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64), []
    vs, ts, off = [], [], 0
    for _, z, f in pieces:
        vs.append(z)
        ts.append(f + off)
        off += len(z)
    return np.concatenate(vs), np.concatenate(ts), pieces


# ------------------------------------------------------------------ silhouettes vs concept
def fit_camera(v, t, cmask, size, az_range=(0, 90, 5), el_range=(5, 60, 5)):
    """Grid-search the orthographic camera (azimuth, elevation) that best matches one concept
    mask (bbox-normalised IoU), coarse then refined at 1°. Returns (az, el, iou)."""
    def score(az, el):
        m, _ = raster.silhouette(v, t, raster.camera_dir(az, el), size=size)
        return raster.iou(cmask, raster.normalize_to_bbox(m, size))
    best = max(((score(a, e), a, e) for a in range(*az_range) for e in range(*el_range)))
    _, a0, e0 = best
    for a in range(a0 - 4, a0 + 5):
        for e in range(max(1, e0 - 4), e0 + 5):
            s = score(a, e)
            if s > best[0]:
                best = (s, a, e)
    return float(best[1]), float(best[2]), round(best[0], 4)

# Camera overrides from spec.concept.cameras, set by concept_masks(); every caller loads the
# concept masks before asking for model silhouettes in the same process.
_CAMERAS = {}


def concept_masks(spec, spec_path, size):
    """{view: bbox-normalised bool mask} for spec.concept.views: the orthographic labels, "34",
    and any label with a camera in spec.concept.cameras."""
    import common
    global _CAMERAS
    concept = spec.get("concept") or {}
    views = concept.get("views") or {}
    bg = concept.get("background")
    _CAMERAS = concept.get("cameras") or {}
    out = {}
    for label, rel in views.items():
        if label not in raster.VIEW_DIRS and label not in _CAMERAS:
            continue
        m = raster.concept_mask(common.spec_rel(spec_path, rel), bg)
        out[label] = raster.normalize_to_bbox(m, size)
    return out


def model_mask(v, t, view, size):
    m, _ = raster.silhouette(v, t, raster.view_dir(view, _CAMERAS), size=size)
    return raster.normalize_to_bbox(m, size)


def view_ious(v, t, cmasks, size):
    """Per-view IoU of the model's bbox-normalised silhouette against each concept mask."""
    per, masks = {}, {}
    for view, cm in cmasks.items():
        mm = model_mask(v, t, view, size)
        masks[view] = mm
        per[view] = raster.iou(cm, mm)
    return per, masks


def iou_summary(per):
    if not per:
        return None
    worst_view = min(per, key=per.get)
    return {"per_view": {k: round(x, 4) for k, x in per.items()},
            "mean": round(float(np.mean(list(per.values()))), 4),
            "worst": round(per[worst_view], 4), "worst_view": worst_view}
