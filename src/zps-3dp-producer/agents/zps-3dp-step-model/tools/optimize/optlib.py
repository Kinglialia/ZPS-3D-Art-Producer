"""Shared pure-Python helpers for tools/optimize. No bpy here, and nothing heavy at import time
(numpy + stdlib only), so Blender scripts can import it too.

- settings(): config.yaml + task spec, with the few optimize defaults config.yaml lacks.
- GLB helpers: triangle count, mesh loading (Blender Z-up axes), root-transform rewrite.
- closest_points(): exact point-to-triangle-mesh distance, KD-tree pruned (no rtree needed).
- blender_cmd(): how to run a Blender script on this machine (binary or bpy module).

Axes: glTF is Y-up; every array returned here is in Blender axes (Z up, front faces -Y), the
convention of tools/lib/raster.py. Blender (x, y, z) = glTF (x, -z, y).
"""
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)
import common  # noqa: E402

# Keys config.yaml does not define yet. They sit under the same sections; config.yaml and the
# spec's "config" block override them. Report them when proposing config changes.
EXTRA_DEFAULTS = {
    "audit": {
        "ray_directions": 64,            # optimize.md §1
        "samples_per_face": 4,           # centroid + 3 points halfway to the corners
        "max_faces_for_rays": 200000,    # above: a deterministic random subset is tested
        "nonmanifold_edge_max_ratio": 0.001,   # above: dirty [guess]
        "max_significant_shells": 64,    # shells above loose_part_min_ratio; above: dirty [guess]
        "uv_inside_min": 0.95,           # share of UV area inside 0-1 for keep_uv [guess]
        "uv_overlap_max": 0.05,          # overlapping UV area share when overlap is not allowed [guess]
        "uv_islands_per_1k_faces_max": 30,     # seam-heavy above this: simplification stalls [guess]
        "uv_islands_rule_min_faces": 2000,     # islands-per-1k rule only from this many tris; a low-poly
                                               # mesh has few faces per island by nature [guess]
    },
    "cleanup": {
        "voxel_remesh": {
            "open_boundary_min_ratio": 0.01,   # boundary-edge share that makes a shell an open sheet [guess]
        },
    },
    "concept": {
        "bg_std_max": 10.0,              # std of background RGB (0-255) for "plain background" [guess]
        "rembg_model": "u2net",
    },
    "gate1": {
        "tie_tolerance": 0.005,          # front IoUs this close are tied; mean IoU over views decides
    },
    "measure": {
        "samples": 20000,                # surface samples per direction for Hausdorff
        "max_vertex_samples": 20000,     # vertices added to the samples (simplification error peaks there)
    },
    "sweep": {
        "texture_error_tie": 0.02,       # keep_uv cross-check: texture error p95 closer than this ties [guess]
        "texture_error_warn": 0.05,      # keep_uv: warn when a selected level's texture error p95 is above [guess]
        "refine_steps": 2,               # bisection steps between the last failing and first passing ratio
        "min_tris": 12,                  # extending below the ratio list never goes under this
        "timeout_s": 900,
    },
    "bake": {
        "ssim_views": ["front", "back", "left", "right", "top", "34"],
        "ssim_render_px": 384,
        "render_samples": 16,
        "bake_samples": 4,
    },
}


def settings(spec_path=None):
    """(settings, spec): EXTRA_DEFAULTS < config.yaml < spec["config"]."""
    try:
        cfg, spec = common.load_settings(spec_path)
    except ImportError:  # Blender's bundled Python has no PyYAML: let a system python parse it
        cfg = _yaml_via_system_python(os.path.join(common.SKILL_ROOT, "config.yaml"))
        spec = {}
        if spec_path:
            spec = common.read_json(spec_path)
            cfg = common.deep_merge(cfg, spec.get("config", {}))
    return common.deep_merge(EXTRA_DEFAULTS, cfg), spec


def _yaml_via_system_python(path):
    py = shutil.which("python3") or shutil.which("python")
    code = "import json,sys,yaml;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))"
    out = subprocess.run([py, "-c", code, path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def asset_name(spec, input_path):
    """Name of the joined object audit writes: spec.asset, else the input file stem."""
    name = (spec or {}).get("asset")
    return str(name) if name else os.path.splitext(os.path.basename(input_path))[0]


def output_object(work):
    """data.output_object from <work>/audit.json (the joined object's name), or None."""
    p = os.path.join(work, "audit.json")
    try:
        return common.read_json(p)["data"].get("output_object")
    except (OSError, ValueError, KeyError):
        return None


def name_single_mesh(path, name):
    """Give the GLB's single mesh (and its node) this name, in place. gltfpack drops both names;
    Blender then calls the object Mesh_0. No-op with several meshes."""
    doc, binary = read_glb(path)
    meshes = doc.get("meshes", [])
    if len(meshes) != 1 or not name:
        return False
    meshes[0]["name"] = name
    for n in doc.get("nodes", []):
        if n.get("mesh") == 0:
            n["name"] = name
    write_glb(path, doc, binary)
    return True


def spec_height(spec):
    h = spec.get("height_m") if spec else None
    return float(h) if isinstance(h, (int, float)) and h > 0 else None


# --------------------------------------------------------------------------- GLB
def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"not a GLB file: {path}")
    off, doc, binary = 12, None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    return doc, binary


def write_glb(path, doc, binary):
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binary = binary + b"\0" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(js) + (8 + len(binary) if binary else 0)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        if binary:
            f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def _scene_mesh_instances(doc):
    """Mesh indices instanced by the default scene's node tree (one entry per instance)."""
    nodes = doc.get("nodes", [])
    scenes = doc.get("scenes", [])
    roots = scenes[doc.get("scene", 0)]["nodes"] if scenes else list(range(len(nodes)))
    out, stack = [], list(roots)
    while stack:
        n = nodes[stack.pop()]
        if "mesh" in n:
            out.append(n["mesh"])
        stack.extend(n.get("children", []))
    return out


def glb_tri_count(path):
    """Triangles drawn by the default scene, read from accessor counts (no decoding)."""
    doc, _ = read_glb(path)
    acc = doc.get("accessors", [])
    total = 0
    for mi in _scene_mesh_instances(doc):
        for prim in doc["meshes"][mi]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                total += acc[prim["indices"]]["count"] // 3
            else:
                total += acc[prim["attributes"]["POSITION"]]["count"] // 3
    return int(total)


def glb_summary(path):
    doc, binary = read_glb(path)
    return {"tris": glb_tri_count(path), "materials": len(doc.get("materials", [])),
            "images": len(doc.get("images", [])), "meshes": len(doc.get("meshes", [])),
            "bytes": os.path.getsize(path)}


# Blender Z-up <-> glTF Y-up. gltf = C @ zup ; zup = C.T @ gltf
C_ZUP_TO_GLTF = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])


def load_mesh(path):
    """(verts float64 (n,3) in Blender axes, faces int64 (m,3)) for every triangle mesh in the
    default scene, node transforms applied. Uses trimesh; materials are ignored."""
    import trimesh
    scene = trimesh.load(path, force="scene", process=False)
    vs, fs, off = [], [], 0
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        g = scene.geometry[geom_name]
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        v = trimesh.transform_points(np.asarray(g.vertices, float), transform)
        vs.append(v)
        fs.append(np.asarray(g.faces, np.int64) + off)
        off += len(v)
    if not vs:
        raise ValueError(f"no triangle mesh in {path}")
    v = np.concatenate(vs) @ C_ZUP_TO_GLTF  # row vectors: zup = gltf @ C (C.T applied on the left)
    return v, np.concatenate(fs)


def load_textured(path):
    """Like load_mesh, plus base colour per triangle corner for texture comparisons.
    Returns dict: v, f, uv (m,3,2) or None per primitive mix, img (m,) index into images,
    images (list of float RGB arrays, row 0 = top), textured (bool: every primitive has a UV'd
    base-colour texture). Untextured primitives get a 1x1 image of their base colour factor."""
    import trimesh
    scene = trimesh.load(path, force="scene", process=False)
    vs, fs, uvs, imgs, images, off, textured = [], [], [], [], [], 0, True
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        g = scene.geometry[geom_name]
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        vis = g.visual
        mat = getattr(vis, "material", None)
        tex = getattr(mat, "baseColorTexture", None) if mat is not None else None
        uv = getattr(vis, "uv", None)
        factor = getattr(mat, "baseColorFactor", None) if mat is not None else None
        factor = np.asarray([255, 255, 255, 255] if factor is None else factor, float)
        factor = factor / 255.0 if factor.max() > 1 else factor
        if tex is not None and uv is not None and len(uv) == len(g.vertices):
            arr = np.asarray(tex.convert("RGB"), float) / 255.0 * factor[:3]
            corner = np.asarray(uv, float)[g.faces]
        else:
            textured = False
            arr = factor[:3].reshape(1, 1, 3)
            corner = np.zeros((len(g.faces), 3, 2))
        images.append(arr)
        v = trimesh.transform_points(np.asarray(g.vertices, float), transform)
        vs.append(v)
        fs.append(np.asarray(g.faces, np.int64) + off)
        uvs.append(corner)
        imgs.append(np.full(len(g.faces), len(images) - 1))
        off += len(v)
    if not vs:
        raise ValueError(f"no triangle mesh in {path}")
    return {"v": np.concatenate(vs) @ C_ZUP_TO_GLTF, "f": np.concatenate(fs), "uv": np.concatenate(uvs),
            "img": np.concatenate(imgs), "images": images, "textured": textured}


def barycentric(p, a, b, c):
    """Barycentric weights (n,3) of points p on triangles (a,b,c)."""
    v0, v1, v2 = b - a, c - a, p - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)
    den = d00 * d11 - d01 * d01
    with np.errstate(divide="ignore", invalid="ignore"):
        w1 = np.where(den != 0, (d11 * d20 - d01 * d21) / den, 1 / 3)
        w2 = np.where(den != 0, (d00 * d21 - d01 * d20) / den, 1 / 3)
    return np.stack([1 - w1 - w2, w1, w2], axis=1)


def texture_colour(tm, tri, points):
    """Base colour (n,3) of a load_textured mesh at points lying on triangles tri (nearest texel,
    UV wrapped; trimesh UVs have v up, image row 0 is the top)."""
    t = tm["v"][tm["f"][tri]]
    w = barycentric(points, t[:, 0], t[:, 1], t[:, 2])
    uv = np.einsum("ij,ijk->ik", w, tm["uv"][tri])
    out = np.zeros((len(points), 3))
    for k, img in enumerate(tm["images"]):
        sel = tm["img"][tri] == k
        if not sel.any():
            continue
        h, wdt = img.shape[:2]
        u = np.mod(uv[sel, 0], 1.0)
        v = np.mod(uv[sel, 1], 1.0)
        x = np.clip((u * wdt).astype(int), 0, wdt - 1)
        y = np.clip(((1 - v) * h).astype(int), 0, h - 1)
        out[sel] = img[y, x]
    return out


def wrap_root_transform(src, dst, m_zup):
    """Copy a GLB, parenting the scene roots under one node with matrix m_zup (4x4, Blender
    axes). Lossless: geometry, UVs, materials and textures are untouched."""
    doc, binary = read_glb(src)
    c4 = np.eye(4)
    c4[:3, :3] = C_ZUP_TO_GLTF
    m = c4 @ np.asarray(m_zup, float) @ c4.T
    scenes = doc.setdefault("scenes", [{"nodes": list(range(len(doc.get("nodes", []))))}])
    si = doc.get("scene", 0)
    roots = scenes[si].get("nodes", [])
    doc.setdefault("nodes", []).append({"name": "optimize_orient", "children": roots,
                                        "matrix": [float(x) for x in m.T.reshape(-1)]})
    scenes[si]["nodes"] = [len(doc["nodes"]) - 1]
    write_glb(dst, doc, binary)


# --------------------------------------------------------------------------- validity
DEGENERATE_AREA_M2 = 1e-8   # asset_checks/mesh_check counts faces below this area as degenerate
REPAIR_AREA_M2 = 1e-7       # repair_glb fixes faces below this: a margin over mesh_check's float32 areas
WELD_M = 1e-6               # asset_checks load_input welds glTF seam splits at this distance


def weld_ids(v, tol=WELD_M):
    """Welded vertex id per vertex (positions on the same tol grid cell merge)."""
    key = np.round(np.asarray(v, float) / tol).astype(np.int64)
    return np.unique(key, axis=0, return_inverse=True)[1].reshape(-1)


def edge_stats(f):
    """Undirected edge use counts and winding consistency of a triangle list."""
    he = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    key = np.sort(he, axis=1)
    uniq, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    # winding: for a manifold edge the two half-edges must run in opposite directions
    two = counts[inv] == 2
    order = np.argsort(inv[two], kind="stable")
    pairs = he[two][order].reshape(-1, 2, 2)
    same_dir = (pairs[:, 0, 0] == pairs[:, 1, 0])
    return {
        "edges": int(len(uniq)),
        "manifold": int((counts == 2).sum()),
        "boundary": int((counts == 1).sum()),
        "nonmanifold": int((counts > 2).sum()),
        "winding_inconsistent": int(same_dir.sum()),
    }


def _areas(v, f, dtype=np.float64):
    t = np.asarray(v, dtype)[f]
    return np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2


def topology_stats(v, f):
    """Validity counts on the position-welded mesh, with mesh_check's degenerate rule:
    degenerate_faces (float32 area, as Blender computes it, < DEGENERATE_AREA_M2, or two corners
    welded together),
    nonmanifold_edges, winding_inconsistent_edges, boundary_edges."""
    fw = weld_ids(v)[f]
    dup = (fw[:, 0] == fw[:, 1]) | (fw[:, 1] == fw[:, 2]) | (fw[:, 2] == fw[:, 0])
    deg = dup | (_areas(v, f, np.float32) < DEGENERATE_AREA_M2)
    es = edge_stats(fw[~dup]) if (~dup).any() else edge_stats(np.zeros((0, 3), np.int64))
    return {"degenerate_faces": int(deg.sum()), "nonmanifold_edges": es["nonmanifold"],
            "winding_inconsistent_edges": es["winding_inconsistent"], "boundary_edges": es["boundary"]}


_COMP = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}


def _accessor_array(doc, binary, ai):
    acc = doc["accessors"][ai]
    bv = doc["bufferViews"][acc["bufferView"]]
    dt = np.dtype(_COMP[acc["componentType"]])
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or dt.itemsize * ncomp
    raw = np.frombuffer(binary, np.uint8, count=stride * (acc["count"] - 1) + dt.itemsize * ncomp, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, (acc["count"], dt.itemsize * ncomp), (stride, 1))
    return np.ascontiguousarray(rows).view(dt).reshape(acc["count"], ncomp)


def repair_glb(path, max_passes=8):
    """Light in-place repair of a simplified level (sweep runs it after every simplify).
    Only index buffers change: vertices, UVs, normals, materials and textures stay as they are.
    Per mesh, on the position-welded triangles of all its primitives:
      1. needles (two corners welded together): dropped; their edges coincide after the weld.
      2. caps (area < REPAIR_AREA_M2, three distinct near-collinear corners): the neighbour across
         the long edge is split at the middle corner (edge flip), so the surface stays closed.
         A cap whose neighbour was changed in this pass waits for the next one. When no pass can
         split it (neighbour missing, non-manifold, in another primitive, or itself a cap), the
         cap is dropped (leaves a zero-width T-junction, counted in caps_dropped).
      3. winding: trimesh.repair.fix_winding on the welded mesh; within each connected body the
         minority orientation is the one flipped (two corners swapped).
    Returns counts; {"skipped": reason} when the file cannot be repaired this way."""
    import trimesh
    doc, binary = read_glb(path)
    if any("meshopt" in e or "draco" in e for e in doc.get("extensionsUsed", [])):
        return {"skipped": "compressed buffers"}
    out = {"needles_dropped": 0, "caps_split": 0, "caps_dropped": 0, "faces_flipped": 0}
    new_index = {}                                # accessor index -> new uint32 index array
    for mesh in doc.get("meshes", []):
        prims = [p for p in mesh["primitives"] if p.get("mode", 4) == 4 and "indices" in p]
        if not prims:
            continue
        vs, fs, pid, off = [], [], [], 0
        for k, p in enumerate(prims):
            v = _accessor_array(doc, binary, p["attributes"]["POSITION"]).astype(float)
            f = _accessor_array(doc, binary, p["indices"]).reshape(-1, 3).astype(np.int64)
            vs.append(v)
            fs.append(f + off)
            pid.append(np.full(len(f), k))
            off += len(v)
        v, f, pid = np.concatenate(vs), np.concatenate(fs), np.concatenate(pid)
        w = weld_ids(v)
        fw = w[f]
        needle = (fw[:, 0] == fw[:, 1]) | (fw[:, 1] == fw[:, 2]) | (fw[:, 2] == fw[:, 0])
        out["needles_dropped"] += int(needle.sum())
        f, pid = f[~needle], pid[~needle]
        force = False                                    # a pass without progress: drop the rest
        for pass_no in range(max_passes):
            fw = w[f]
            area = _areas(v, f)
            caps = np.nonzero(area < REPAIR_AREA_M2)[0]
            if caps.size == 0:
                break
            last = force or pass_no == max_passes - 1
            edge_faces = {}
            for fi, tri in enumerate(fw):
                for i in range(3):
                    edge_faces.setdefault(frozenset((tri[i], tri[(i + 1) % 3])), []).append(fi)
            touched, drop, add = set(), [], []
            for ci in caps:
                if ci in touched:
                    continue
                t = v[f[ci]]
                lens = [np.linalg.norm(t[(i + 1) % 3] - t[i]) for i in range(3)]
                i = int(np.argmax(lens))                     # long edge: corners i, i+1; b = i+2
                b = f[ci][(i + 2) % 3]
                nb = [x for x in edge_faces[frozenset((fw[ci][i], fw[ci][(i + 1) % 3]))] if x != ci]
                splittable = len(nb) == 1 and pid[nb[0]] == pid[ci]
                if splittable and not last and (nb[0] in touched or area[nb[0]] < REPAIR_AREA_M2):
                    continue                             # neighbour changed or is a cap: next pass
                ok = splittable and nb[0] not in touched and area[nb[0]] >= REPAIR_AREA_M2
                if ok:
                    n = nb[0]
                    ends = {fw[ci][i], fw[ci][(i + 1) % 3]}
                    j = next(j for j in range(3) if fw[n][j] in ends and fw[n][(j + 1) % 3] in ends)
                    x, y, d = f[n][j], f[n][(j + 1) % 3], f[n][(j + 2) % 3]
                    t1, t2 = np.array([[x, b, d]]), np.array([[b, y, d]])
                    ok = min(_areas(v, t1)[0], _areas(v, t2)[0]) >= REPAIR_AREA_M2
                if ok:
                    f[n] = t1[0]
                    add.append((t2[0], pid[n]))
                    touched.update((n, ci))
                    out["caps_split"] += 1
                else:
                    touched.add(ci)
                    out["caps_dropped"] += 1
                drop.append(ci)
            if not drop:
                force = True
                continue
            keep = np.ones(len(f), bool)
            keep[drop] = False
            f, pid = f[keep], pid[keep]
            if add:
                f = np.concatenate([f, np.array([a for a, _ in add])])
                pid = np.concatenate([pid, np.array([p for _, p in add])])
        # winding consistency, minority orientation per body flipped
        fw = w[f]
        vw = np.zeros((w.max() + 1, 3))
        vw[w] = v
        tm = trimesh.Trimesh(vw, fw, process=False)
        before = tm.face_normals.copy()
        trimesh.repair.fix_winding(tm)
        flip = (np.einsum("ij,ij->i", before, tm.face_normals) < 0)
        if flip.any():
            body = trimesh.graph.connected_component_labels(tm.face_adjacency, len(fw))
            for lab in np.unique(body[flip]):
                sel = body == lab
                if flip[sel].mean() > 0.5:
                    flip[sel] = ~flip[sel]
            f[flip] = f[flip][:, [0, 2, 1]]
            out["faces_flipped"] += int(flip.sum())
        offs = np.cumsum([0] + [len(x) for x in vs])
        for k, p in enumerate(prims):
            new_index[p["indices"]] = (f[pid == k] - offs[k]).astype(np.uint32).reshape(-1)
    if not any(out.values()):
        return out
    blob = bytearray(binary)
    for ai, idx in new_index.items():
        acc = doc["accessors"][ai]
        blob += b"\0" * ((4 - len(blob) % 4) % 4)
        bv = {"buffer": 0, "byteOffset": len(blob), "byteLength": idx.nbytes, "target": 34963}
        blob += idx.tobytes()
        doc["bufferViews"].append(bv)
        acc.update({"bufferView": len(doc["bufferViews"]) - 1, "byteOffset": 0, "componentType": 5125,
                    "count": int(idx.size)})
        acc.pop("min", None)
        acc.pop("max", None)
    _drop_unused_buffer_views(doc)
    doc["buffers"][0]["byteLength"] = len(blob) + (4 - len(blob) % 4) % 4
    write_glb(path, doc, bytes(blob))
    return out


def _drop_unused_buffer_views(doc):
    """Remove bufferViews nothing references (the replaced index views) and renumber."""
    used = {a["bufferView"] for a in doc.get("accessors", []) if "bufferView" in a}
    used |= {im["bufferView"] for im in doc.get("images", []) if "bufferView" in im}
    keep = [i for i in range(len(doc["bufferViews"])) if i in used]
    remap = {old: new for new, old in enumerate(keep)}
    doc["bufferViews"] = [doc["bufferViews"][i] for i in keep]
    for a in doc.get("accessors", []):
        if "bufferView" in a:
            a["bufferView"] = remap[a["bufferView"]]
    for im in doc.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = remap[im["bufferView"]]


# --------------------------------------------------------------------------- distances
def closest_on_triangles(p, a, b, c):
    """Closest point on triangle (a,b,c) to p, row-wise (Ericson, Real-Time Collision
    Detection §5.1.5). All inputs (n,3)."""
    ab, ac, ap = b - a, c - a, p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = va + vb + vc
        v = np.where(denom != 0, vb / denom, 0.0)
        w = np.where(denom != 0, vc / denom, 0.0)
        out = a + ab * v[:, None] + ac * w[:, None]          # interior
        done = np.zeros(len(p), bool)

        def put(mask, value):
            nonlocal done
            m = mask & ~done
            out[m] = value[m]
            done |= m

        put((d1 <= 0) & (d2 <= 0), a)
        put((d3 >= 0) & (d4 <= d3), b)
        t = np.where(d1 - d3 != 0, d1 / (d1 - d3), 0.0)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * t[:, None])
        put((d6 >= 0) & (d5 <= d6), c)
        t = np.where(d2 - d6 != 0, d2 / (d2 - d6), 0.0)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * t[:, None])
        e1, e2 = d4 - d3, d5 - d6
        t = np.where(e1 + e2 != 0, e1 / (e1 + e2), 0.0)
        put((va <= 0) & (e1 >= 0) & (e2 >= 0), b + (c - b) * t[:, None])
    # zero-area triangles: the region test above is unreliable; use the nearest of the 3 edges
    area2 = np.linalg.norm(np.cross(ab, ac), axis=1)
    scale = np.maximum(np.einsum("ij,ij->i", ab, ab), np.einsum("ij,ij->i", ac, ac))
    bad = (area2 <= 1e-12 * np.maximum(scale, 1e-300)) | ~np.isfinite(out).all(axis=1)
    if bad.any():
        pb = p[bad]
        segs = [_closest_on_segments(pb, a[bad], b[bad]), _closest_on_segments(pb, b[bad], c[bad]),
                _closest_on_segments(pb, c[bad], a[bad])]
        dists = np.stack([np.linalg.norm(pb - q, axis=1) for q in segs], axis=1)
        pick = dists.argmin(axis=1)
        out[bad] = np.stack(segs, axis=1)[np.arange(len(pb)), pick]
    return out


def _closest_on_segments(p, a, b):
    ab = b - a
    ll = np.einsum("ij,ij->i", ab, ab)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(ll > 0, np.einsum("ij,ij->i", p - a, ab) / ll, 0.0)
    return a + ab * np.clip(t, 0, 1)[:, None]


class TriangleIndex:
    """Exact closest-point queries on a triangle mesh (build once, query many times).

    Each triangle is represented by points in a KD-tree: its centroid, or for a large triangle
    a barycentric grid fine enough that every point of the triangle lies within cover[t] of one
    of its representatives. For a query point p:
    1. the k nearest representatives give candidate triangles and an upper bound d;
    2. any triangle closer than d has a representative within d + cover[t] of p, so a ball query
       of radius d + max(cover), filtered by |p - rep| - cover[t] < d, holds every possible winner."""

    def __init__(self, verts, faces, k=16, max_reps=3_000_000):
        from scipy.spatial import cKDTree
        self.tris = np.asarray(verts, float)[np.asarray(faces)]
        t = self.tris
        cent = t.mean(axis=1)
        rad = np.linalg.norm(t - cent[:, None, :], axis=2).max(axis=1)
        edge = np.stack([np.linalg.norm(t[:, i] - t[:, (i + 1) % 3], axis=1) for i in range(3)], 1).max(1)
        r0 = max(float(np.percentile(rad, 90)), 1e-12)
        n = np.maximum(1, np.ceil(rad / r0).astype(int))
        while ((n + 1) * (n + 2) // 2 * (n > 1) + (n == 1)).sum() > max_reps:   # bound memory
            r0 *= 1.5
            n = np.maximum(1, np.ceil(rad / r0).astype(int))
        reps, owner, cover = [cent[n == 1]], [np.nonzero(n == 1)[0]], [rad[n == 1]]
        for nn in np.unique(n[n > 1]):
            ids = np.nonzero(n == nn)[0]
            ij = np.array([(i, j) for i in range(nn + 1) for j in range(nn + 1 - i)], float) / nn
            w = np.stack([1 - ij.sum(1), ij[:, 0], ij[:, 1]], axis=1)          # (g, 3)
            pts = np.einsum("gk,tkd->tgd", w, t[ids])                            # (len(ids), g, 3)
            reps.append(pts.reshape(-1, 3))
            owner.append(np.repeat(ids, len(w)))
            cover.append(np.repeat(edge[ids] / nn, len(w)))
        self.rep = np.concatenate(reps)
        self.owner = np.concatenate(owner)
        self.cover = np.concatenate(cover)
        self.cmax = float(self.cover.max())
        self.tree = cKDTree(self.rep)
        self.k = min(k, len(self.rep))

    def _exact(self, points, pi, ti):
        t = self.tris[ti]
        cp = closest_on_triangles(points[pi], t[:, 0], t[:, 1], t[:, 2])
        return np.linalg.norm(points[pi] - cp, axis=1)

    @staticmethod
    def _best_per_point(pi, ti, dd, best_d, best_t):
        order = np.lexsort((dd, pi))                    # per point, smallest distance first
        first = np.ones(order.size, bool)
        first[1:] = pi[order][1:] != pi[order][:-1]
        sel = order[first]
        better = dd[sel] < best_d[pi[sel]]
        best_d[pi[sel][better]] = dd[sel][better]
        best_t[pi[sel][better]] = ti[sel][better]

    def query(self, points, chunk=1024):
        """Returns (closest (n,3), distance (n,), triangle index (n,))."""
        points = np.asarray(points, float)
        n = len(points)
        _, idx = self.tree.query(points, self.k)
        idx = idx.reshape(n, self.k)
        best_d = np.full(n, np.inf)
        best_t = np.zeros(n, int)
        pi = np.repeat(np.arange(n), self.k)
        ti = self.owner[idx.reshape(-1)]
        self._best_per_point(pi, ti, self._exact(points, pi, ti), best_d, best_t)
        for s in range(0, n, chunk):
            sl = slice(s, min(n, s + chunk))
            lists = self.tree.query_ball_point(points[sl], best_d[sl] + self.cmax)
            lens = np.fromiter((len(x) for x in lists), int, len(lists))
            if lens.sum() == 0:
                continue
            reps = np.concatenate([np.asarray(x, int) for x in lists])
            cp = np.repeat(np.arange(s, sl.stop), lens)
            keep = np.linalg.norm(points[cp] - self.rep[reps], axis=1) - self.cover[reps] < best_d[cp]
            cp, ct = cp[keep], self.owner[reps[keep]]
            if cp.size == 0:
                continue
            pair = np.unique(cp.astype(np.int64) * len(self.tris) + ct)
            cp, ct = pair // len(self.tris), pair % len(self.tris)
            self._best_per_point(cp, ct, self._exact(points, cp, ct), best_d, best_t)
        t = self.tris[best_t]
        closest = closest_on_triangles(points, t[:, 0], t[:, 1], t[:, 2])
        return closest, np.linalg.norm(points - closest, axis=1), best_t


def closest_points(points, verts, faces):
    """Exact closest point on a triangle mesh for each point: (closest, distance, triangle)."""
    return TriangleIndex(verts, faces).query(points)


# --------------------------------------------------------------------------- processes
def blender_cmd(settings_, script, args):
    """Command list to run a Blender script, or None when no Blender is available.
    Order: paths.blender if it exists, `blender` on PATH, then the bpy module in this Python."""
    exe = (settings_.get("paths") or {}).get("blender")
    if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
        return [exe, "-b", "--python-exit-code", "1", "--python", script, "--", *args]
    which = shutil.which("blender")
    if which:
        return [which, "-b", "--python-exit-code", "1", "--python", script, "--", *args]
    if importlib.util.find_spec("bpy") is not None:
        return [sys.executable, script, *args]
    return None


def run(cmd, timeout=900):
    """subprocess.run with captured text output; never raises on a non-zero exit."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", repr(exc))


def tail(text, n=15):
    lines = [x for x in (text or "").splitlines() if "EGL" not in x]
    return "\n".join(lines[-n:])
