"""Blender helpers for tools/optimize (audit, cleanup, decimate, bake).

Import, join to one world-space mesh, triangulate, export GLB, plus numpy mesh analysis that
needs no scipy (Blender's bundled Python has numpy only): edge topology, connected components,
ray visibility (interior faces), UV statistics.

Headless notes: bpy.context.window is None; only operators that work without a UI are used
(import/export, object.join with selection set on the view layer, object.bake).
"""
import os
import sys

import bpy  # noqa: F401  (bpy first: the pip module provides bmesh only after bpy)
import bmesh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "..", "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)
import raster  # noqa: E402  (numpy only)


# --------------------------------------------------------------------------- scene I/O
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(path, merge_vertices=False):
    """Import GLB/glTF/FBX/OBJ/PLY/STL into the current scene; returns the new objects."""
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    path = os.path.abspath(path)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path, merge_vertices=merge_vertices)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError(f"unsupported model format: {ext}")
    return [o for o in bpy.data.objects if o not in before]


def rig_findings():
    """Reasons the scene is a rigged/animated asset (out of scope). Basis-only shape keys and
    plain vertex groups do not count."""
    out = []
    for o in bpy.data.objects:
        if o.type == "ARMATURE":
            out.append(f"armature object '{o.name}'")
        if o.type == "MESH":
            keys = o.data.shape_keys
            if keys and len(keys.key_blocks) > 1:
                out.append(f"mesh '{o.name}' has {len(keys.key_blocks) - 1} shape key(s)")
            for m in o.modifiers:
                if m.type == "ARMATURE":
                    out.append(f"mesh '{o.name}' has an armature modifier")
        if o.animation_data and o.animation_data.action:
            out.append(f"object '{o.name}' has animation '{o.animation_data.action.name}'")
    return out


def mesh_object_names(objs=None):
    """Names of the mesh objects with faces (what join_world joins)."""
    objs = list(bpy.data.objects) if objs is None else list(objs)
    return [o.name for o in objs if o.type == "MESH" and len(o.data.polygons)]


def join_world(name=None, objs=None):
    """Bake each mesh object's world transform into its data and join them into one object.
    objs: the objects to use (default: every object in the file); all of them are deleted and
    replaced by the joined mesh. Negative-scale transforms get their winding flipped back.
    name: object and mesh name; None keeps the name of a single input mesh (else "model"), so
    the asset name audit gave the joined object survives every later import/export."""
    objs = list(bpy.data.objects) if objs is None else list(objs)
    meshes = [o for o in objs if o.type == "MESH" and len(o.data.polygons)]
    if not meshes:
        raise ValueError("no mesh with faces in the input")
    if name is None:
        name = meshes[0].name if len(meshes) == 1 else "model"
    flat = []
    for o in meshes:
        mw = o.matrix_world.copy()
        me = o.data.copy()  # instanced data must not be transformed twice
        me.transform(mw)
        if mw.to_3x3().determinant() < 0:
            me.flip_normals()
        new = bpy.data.objects.new(o.name, me)
        bpy.context.scene.collection.objects.link(new)
        flat.append(new)
    old_meshes = {o.data for o in meshes}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for me in old_meshes:   # orphaned: free the name for the joined mesh
        if me.users == 0:
            bpy.data.meshes.remove(me)
    vl = bpy.context.view_layer
    for o in bpy.data.objects:
        o.select_set(o in flat)
    vl.objects.active = flat[0]
    if len(flat) > 1:
        bpy.ops.object.join()
    obj = vl.objects.active
    obj.name = name
    obj.data.name = name
    return obj


def triangulate(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3],
                          quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def mesh_arrays(obj):
    """(V float64 (n,3), F int64 (m,3)) of a triangulated mesh object, object space."""
    me = obj.data
    v = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", v)
    if any(len(p.vertices) != 3 for p in me.polygons):
        raise ValueError("mesh is not triangulated")
    f = np.empty(len(me.polygons) * 3, np.int64)
    me.polygons.foreach_get("vertices", f)
    return v.reshape(-1, 3), f.reshape(-1, 3)


def bbox(v):
    lo, hi = v.min(axis=0), v.max(axis=0)
    return lo, hi, float(np.linalg.norm(hi - lo))


def transform_mesh(obj, scale=1.0, offset=(0.0, 0.0, 0.0)):
    from mathutils import Matrix, Vector
    m = Matrix.Translation(Vector(offset)) @ Matrix.Scale(scale, 4)
    obj.data.transform(m)
    obj.data.update()


def bottom_center_offset(v):
    lo, hi, _ = bbox(v)
    return (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])


def export_glb(path, objs):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    for o in bpy.data.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(path), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True,
                              export_animations=False, export_skins=False, export_morph=False,
                              export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False)


def materials_and_textures(obj):
    mats, tex = [], []
    for slot in obj.material_slots:
        m = slot.material
        if not m:
            continue
        mats.append(m.name)
        if m.use_nodes and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    tex.append({"material": m.name, "image": n.image.name,
                                "size": list(n.image.size)})
    return mats, tex


# --------------------------------------------------------------------------- topology
def weld_map(v, dist):
    """Vertex index map that merges vertices on the same dist-sized grid cell (exact duplicates,
    such as glTF seam splits, always merge). Face order is untouched: F_welded = map[F]."""
    key = np.round(v / max(dist, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return inv.reshape(-1), len(first)


from optlib import edge_stats  # noqa: E402,F401  (numpy only; shared with measure.py)


def connected_labels(n, edges):
    """Component label per node for an undirected edge list (hook-and-shortcut, numpy only)."""
    lab = np.arange(n)
    if len(edges) == 0:
        return lab
    a0, b0 = edges[:, 0], edges[:, 1]
    while True:
        a, b = lab[a0], lab[b0]
        m = np.minimum(a, b)
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        while True:
            nxt = new[new]
            if (nxt == new).all():
                break
            new = nxt
        if (new == lab).all():
            return lab
        lab = new


def shells(v, f, diag):
    """Connected components of a (welded) triangle mesh.
    Returns (list of {faces, face_share, bbox_share, label} sorted by faces, face label array)."""
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]]])
    lab = connected_labels(len(v), edges)
    _, face_lab, counts = np.unique(lab[f[:, 0]], return_inverse=True, return_counts=True)
    face_lab = face_lab.reshape(-1)
    k = len(counts)
    t = v[f]
    lo = np.full((k, 3), np.inf)
    hi = np.full((k, 3), -np.inf)
    np.minimum.at(lo, face_lab, t.min(axis=1))
    np.maximum.at(hi, face_lab, t.max(axis=1))
    d = np.linalg.norm(hi - lo, axis=1)
    out = [{"faces": int(counts[i]), "face_share": float(counts[i] / len(f)),
            "bbox_share": float(d[i] / diag) if diag > 0 else 0.0, "label": int(i)}
           for i in np.argsort(-counts, kind="stable")]
    return out, face_lab


def face_areas_normals(v, f):
    t = v[f]
    cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.linalg.norm(cr, axis=1)
    n = cr / np.maximum(a, 1e-30)[:, None]
    return a / 2, n


def visibility(v, f, n_dirs=64, samples_per_face=4, max_faces=200000, seed=0):
    """Ray visibility from n_dirs exterior directions (Fibonacci sphere, above and below).

    A face is visible when a ray from one of its sample points toward a camera direction
    escapes the mesh. Faces never visible are interior. Samples: the centroid, then points
    halfway from the centroid to each corner. Directions are tried most-aligned-with-the-face
    first, so exterior faces exit after 1-2 rays.

    Flipped-normal estimate (visible faces only): the ray along +normal is blocked while the
    ray along -normal escapes.

    Returns dict: interior (bool per face; untested faces False), tested (index array),
    flipped (bool per face)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons(v.tolist(), f.tolist(), all_triangles=True)
    _, _, diag = bbox(v)
    eps, far = 1e-5 * diag, 4.0 * diag
    dirs = np.asarray(raster.sphere_dirs(n_dirs), float)
    rays = [Vector(tuple(-d)) for d in dirs]               # toward each camera
    _, nrm = face_areas_normals(v, f)
    t = v[f]
    cent = t.mean(axis=1)
    pts = [cent] + [(cent + t[:, k]) / 2 for k in range(3)]
    pts = np.stack(pts[:max(1, samples_per_face)], axis=1)  # (m, s, 3)
    m = len(f)
    tested = np.arange(m)
    if m > max_faces:
        tested = np.sort(np.random.default_rng(seed).choice(m, max_faces, replace=False))
    interior = np.zeros(m, bool)
    flipped = np.zeros(m, bool)
    for fi in tested:
        order = np.argsort(-np.abs(dirs @ nrm[fi]))
        seen = False
        for p in pts[fi]:
            for j in order:
                r = rays[j]
                if tree.ray_cast(Vector(tuple(p)) + r * eps, r, far)[0] is None:
                    seen = True
                    break
            if seen:
                break
        if not seen:
            interior[fi] = True
            continue
        nv = Vector(tuple(nrm[fi]))
        c = Vector(tuple(cent[fi]))
        front = tree.ray_cast(c + nv * eps, nv, far)[0]
        back = tree.ray_cast(c - nv * eps, -nv, far)[0]
        flipped[fi] = front is not None and back is None
    return {"interior": interior, "tested": tested, "flipped": flipped}


# --------------------------------------------------------------------------- UV
def loop_uvs(obj, layer=None):
    """(m,3,2) UV per triangle corner, or None when the mesh has no UV layer."""
    me = obj.data
    if not me.uv_layers:
        return None
    uvl = me.uv_layers[layer] if layer else (me.uv_layers.active or me.uv_layers[0])
    uv = np.empty(len(me.loops) * 2, np.float64)
    uvl.data.foreach_get("uv", uv)
    start = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", start)
    uv = uv.reshape(-1, 2)
    return np.stack([uv[start], uv[start + 1], uv[start + 2]], axis=1)


def uv_coverage(uvt, res=512):
    """Pixel coverage count of UV triangles at res x res (pixel centre strictly inside, so
    triangles sharing an edge do not count as overlapping). Returns int32 count image."""
    cnt = np.zeros((res, res), np.int32)
    p = uvt * res - 0.5
    for tri in p:
        x0, y0 = np.floor(tri.min(0)).astype(int)
        x1, y1 = np.ceil(tri.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        (ax, ay), (bx, by), (cx, cy) = tri
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        w1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        inside = (w0 > 1e-9) & (w1 > 1e-9) & (1 - w0 - w1 > 1e-9)
        cnt[y0:y1 + 1, x0:x1 + 1] += inside
    return cnt


def uv_islands(f_welded, uvt, tol=1e-5):
    """Number of UV islands: faces joined across a welded edge whose UVs match on both sides."""
    m = len(f_welded)
    he_v = np.concatenate([f_welded[:, [0, 1]], f_welded[:, [1, 2]], f_welded[:, [2, 0]]])
    he_uv = np.concatenate([uvt[:, [0, 1]], uvt[:, [1, 2]], uvt[:, [2, 0]]])
    he_f = np.tile(np.arange(m), 3)
    key = np.sort(he_v, axis=1)
    _, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    two = np.nonzero(counts[inv] == 2)[0]
    two = two[np.argsort(inv[two], kind="stable")].reshape(-1, 2)
    h1, h2 = two[:, 0], two[:, 1]
    same = he_v[h1, 0] == he_v[h2, 0]
    uv2_s = np.where(same[:, None], he_uv[h2, 0], he_uv[h2, 1])
    uv2_e = np.where(same[:, None], he_uv[h2, 1], he_uv[h2, 0])
    match = (np.abs(he_uv[h1, 0] - uv2_s).max(1) < tol) & (np.abs(he_uv[h1, 1] - uv2_e).max(1) < tol)
    edges = np.stack([he_f[h1[match]], he_f[h2[match]]], axis=1)
    lab = connected_labels(m, edges)
    return int(len(np.unique(lab)))


def uv_stats(obj, f_welded, res=512):
    """UV layer present, share of UV area inside 0-1, overlap ratio, islands per 1k faces."""
    uvt = loop_uvs(obj)
    if uvt is None:
        return {"present": False}
    e1, e2 = uvt[:, 1] - uvt[:, 0], uvt[:, 2] - uvt[:, 0]
    area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    total = float(area.sum())
    inside = ((uvt >= -1e-4) & (uvt <= 1 + 1e-4)).all(axis=(1, 2))
    cnt = uv_coverage(np.clip(uvt, -0.01, 1.01), res)
    covered = int((cnt > 0).sum())
    over = int((cnt > 1).sum())
    islands = uv_islands(f_welded, uvt)
    return {
        "present": True,
        "layers": len(obj.data.uv_layers),
        "uv_area_total": total,
        "inside_01_share": float(area[inside].sum() / total) if total > 0 else 0.0,
        "zero_area_uv_faces": int((area <= 1e-12).sum()),
        "overlap_ratio": float(over / covered) if covered else 0.0,
        "coverage_01": float(covered / (res * res)),
        "islands": islands,
        "islands_per_1k_faces": float(islands * 1000.0 / max(1, len(f_welded))),
        "raster_res": res,
    }
