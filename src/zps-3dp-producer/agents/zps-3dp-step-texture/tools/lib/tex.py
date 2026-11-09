"""Shared by the texture tools, numpy and Pillow only (runs in the tools venv and in Blender).

read_glb(path) -> {"v" (n,3) Blender axes, "f" (m,3), "uv" (n,2) glTF convention (v down) or None, "images" [bytes],
                   "nodes", "meshes", "materials"}; node transforms applied.
texel_map(v, f, uv, res) -> TexelMap: for every texel centre inside a UV triangle its face, 3D point and face normal.
Image row 0 is the top of the atlas, which is glTF v = 0.
Result JSON: the kit shape {"tool", "run_at", "overall", "checks", "data"}; overall fail > pass > info.
"""
import datetime
import json
import os
import struct

import numpy as np

GLTF_TO_ZUP = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
SIDES = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0)}


def chunks(path):
    data = open(path, "rb").read()
    if data[:4] != b"glTF" or struct.unpack("<I", data[8:12])[0] != len(data):
        raise ValueError(f"{path}: not a complete GLB")
    out, off = {}, 12
    while off < len(data):
        n, kind = struct.unpack("<II", data[off:off + 8])
        out[kind] = data[off + 8:off + 8 + n]
        off += 8 + n
    return json.loads(out[0x4E4F534A]), out.get(0x004E4942, b"")


def accessor(doc, binary, i):
    a = doc["accessors"][i]
    bv = doc["bufferViews"][a["bufferView"]]
    dt, w = np.dtype(COMP[a["componentType"]]), WIDTH[a["type"]]
    start, stride = bv.get("byteOffset", 0) + a.get("byteOffset", 0), bv.get("byteStride") or dt.itemsize * w
    raw = np.frombuffer(binary, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * w, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * w), (stride, 1))
    return np.ascontiguousarray(rows).view(dt).reshape(a["count"], w).squeeze(-1 if w == 1 else ())


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


def read_glb(path):
    doc, binary = chunks(path)
    nodes = doc.get("nodes", [])
    scenes = doc.get("scenes", [])
    stack = [(i, np.eye(4)) for i in (scenes[doc.get("scene", 0)]["nodes"] if scenes else range(len(nodes)))]
    vs, fs, uvs, off, count = [], [], [], 0, 0
    while stack:
        i, parent = stack.pop()
        m = parent @ node_matrix(nodes[i])
        stack.extend((c, m) for c in nodes[i].get("children", []))
        if "mesh" not in nodes[i]:
            continue
        count += 1
        for prim in doc["meshes"][nodes[i]["mesh"]]["primitives"]:
            p = accessor(doc, binary, prim["attributes"]["POSITION"]).astype(float)
            p = (np.c_[p, np.ones(len(p))] @ m.T)[:, :3] @ GLTF_TO_ZUP
            idx = (accessor(doc, binary, prim["indices"]).reshape(-1, 3).astype(np.int64) if "indices" in prim
                   else np.arange(len(p)).reshape(-1, 3))
            t = prim["attributes"].get("TEXCOORD_0")
            uvs.append(accessor(doc, binary, t).astype(float) if t is not None else None)
            vs.append(p)
            fs.append(idx + off)
            off += len(p)
    images = [binary[(bv := doc["bufferViews"][im["bufferView"]]).get("byteOffset", 0):
                     bv.get("byteOffset", 0) + bv["byteLength"]] for im in doc.get("images", []) if "bufferView" in im]
    return {"v": np.concatenate(vs) if vs else np.zeros((0, 3)), "f": np.concatenate(fs) if fs else np.zeros((0, 3), int),
            "uv": np.concatenate(uvs) if uvs and all(u is not None for u in uvs) else None, "images": images,
            "nodes": count, "meshes": len(doc.get("meshes", [])), "materials": len(doc.get("materials", []))}


def face_normals(v, f):
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


class TexelMap:
    """face (res,res) int, -1 outside every island; pos, nrm (res,res,3) for the texels inside."""

    def __init__(self, v, f, uv, res):
        self.res = res
        self.face = np.full((res, res), -1, np.int32)
        self.pos = np.zeros((res, res, 3))
        self.nrm = np.zeros((res, res, 3))
        fn = face_normals(v, f)
        px = uv[:, 0] * res - 0.5
        py = uv[:, 1] * res - 0.5
        for k, (a, b, c) in enumerate(f):
            xs, ys = px[[a, b, c]], py[[a, b, c]]
            x0, x1 = max(int(np.floor(xs.min())), 0), min(int(np.ceil(xs.max())), res - 1)
            y0, y1 = max(int(np.floor(ys.min())), 0), min(int(np.ceil(ys.max())), res - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(d) < 1e-12:
                continue
            l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
            l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
            l2 = 1 - l0 - l1
            inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
            yy, xx = gy[inside], gx[inside]
            self.face[yy, xx] = k
            self.pos[yy, xx] = (l0[inside, None] * v[a] + l1[inside, None] * v[b] + l2[inside, None] * v[c])
            self.nrm[yy, xx] = fn[k]

    @property
    def inside(self):
        return self.face >= 0


def load_map(glb, res):
    g = read_glb(glb)
    if g["uv"] is None:
        raise ValueError(f"{glb}: no TEXCOORD_0")
    return g, TexelMap(g["v"], g["f"], g["uv"], res)


def side_of(nrm, up_z=0.7, down_z=-0.7):
    """'top', 'bottom' or the nearest of +X -X +Y -Y for each normal (n,3)."""
    out = np.full(len(nrm), "", object)
    out[nrm[:, 2] > up_z] = "top"
    out[nrm[:, 2] < down_z] = "bottom"
    rest = out == ""
    keys = list(SIDES)
    dots = np.stack([nrm[rest] @ np.asarray(SIDES[k], float) for k in keys], axis=1)
    out[rest] = np.asarray(keys, object)[dots.argmax(1)]
    return out


def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def lab(rgb255):
    """CIE Lab (D65) of sRGB colours in 0..255, shape (..., 3)."""
    lin = srgb_to_linear(np.asarray(rgb255, float) / 255)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    e = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * e[..., 1] - 16, 500 * (e[..., 0] - e[..., 1]), 200 * (e[..., 1] - e[..., 2])], -1)


def lab_to_rgb(lab_):
    """Inverse of lab(): sRGB 0..255 (clipped)."""
    L, a, b = (np.asarray(lab_, float)[..., i] for i in range(3))
    fy = (L + 16) / 116
    f = np.stack([fy + a / 500, fy, fy - b / 200], -1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    return linear_to_srgb(xyz @ m.T) * 255


def blur(x, mask, r):
    """Mean of x over the (2r+1)^2 window, counting only texels where mask is true (an island never bleeds into the
    empty atlas)."""
    def box(a):
        c = np.cumsum(np.cumsum(np.pad(a, ((r + 1, r), (r + 1, r))), 0), 1)
        return c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]
    m = mask.astype(float)
    return box(x * m) / np.maximum(box(m), 1e-9)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def load_rgb(path, res=None):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if res and im.size != (res, res):
        im = im.resize((res, res), Image.LANCZOS)
    return np.asarray(im, float)


def save_rgb(arr, path):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(np.clip(np.round(arr), 0, 255).astype(np.uint8)).save(path)


def check(name, status, value=None, threshold=None, note=None):
    return {"check": name, "status": status, "value": value, "threshold": threshold, "note": note}


def write_result(path, tool, checks, data=None):
    st = {c["status"] for c in checks}
    overall = "fail" if "fail" in st else "pass" if "pass" in st else "info"
    r = {"tool": f"texture/{tool}", "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
         "overall": overall, "checks": checks, "data": data or {}}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
    return r


def write_error(path, tool, exc):
    r = {"tool": f"texture/{tool}", "run_at": datetime.datetime.now().isoformat(timespec="seconds"), "overall": "error",
         "checks": [], "data": {"error": repr(exc)}}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
    return r


def gutter(img, inside, px):
    """Fill up to px texels around each island with the nearest island colour (padding against mip bleed)."""
    out, done = img.copy(), inside.copy()
    for _ in range(px):
        grow = np.zeros_like(done)
        acc = np.zeros(out.shape, float)
        cnt = np.zeros(done.shape, float)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(done, (dy, dx), (0, 1))
            col = np.roll(out, (dy, dx), (0, 1))
            add = src & ~done
            acc[add] += col[add]
            cnt[add] += 1
            grow |= add
        out[grow] = acc[grow] / cnt[grow, None]
        done |= grow
    return out


def border(inside):
    """Island texels with a 4-neighbour outside every island."""
    out = np.zeros_like(inside)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        out |= inside & ~np.roll(inside, (dy, dx), (0, 1))
    return out


def seam_groups(tm, area):
    """Border texels that meet texels of another face at the same 3D point (cell = 1.5 texel edges): returns the flat
    texel indices and a group id per index. area: 3D surface area of the mesh, for the texel size in metres."""
    b = border(tm.inside) & tm.inside
    idx = np.flatnonzero(b)
    if not len(idx):
        return idx, idx
    cell = 1.5 * np.sqrt(area / max(tm.inside.sum(), 1))
    key = np.floor(tm.pos.reshape(-1, 3)[idx] / cell).astype(np.int64)
    _, gid = np.unique(key, axis=0, return_inverse=True)
    gid = gid.reshape(-1)
    face = tm.face.reshape(-1)[idx]
    fmin = np.full(gid.max() + 1, np.iinfo(np.int64).max)
    fmax = np.full(gid.max() + 1, -1)
    np.minimum.at(fmin, gid, face)
    np.maximum.at(fmax, gid, face)
    keep = fmin[gid] != fmax[gid]
    return idx[keep], gid[keep]


def seam_spread(img, idx, gid):
    """Per seam group the largest dE76 of a member to the group mean; returns the 90th percentile (0 without seams)."""
    if not len(idx):
        return 0.0
    labs = lab(img.reshape(-1, 3)[idx])
    n = np.bincount(gid)
    mean = np.stack([np.bincount(gid, labs[:, k]) for k in range(3)], 1) / np.maximum(n, 1)[:, None]
    d = np.linalg.norm(labs - mean[gid], axis=1)
    worst = np.zeros(len(n))
    np.maximum.at(worst, gid, d)
    return float(np.percentile(worst[n > 1], 90)) if (n > 1).any() else 0.0


def mesh_area(v, f):
    return float(np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1).sum() / 2)
