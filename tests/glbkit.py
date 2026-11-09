"""Write small GLB files for tests: a unit box (or any triangles) with TEXCOORD_0 and an optional base colour PNG."""
import json
import struct

import numpy as np

BOX = np.array([[x, y, z] for z in (0, 1) for y in (-0.5, 0.5) for x in (-0.5, 0.5)], float)
FACES = {"-Z": (0, 2, 3, 1), "+Z": (4, 5, 7, 6), "-Y": (0, 1, 5, 4), "+Y": (2, 6, 7, 3), "-X": (0, 4, 6, 2),
         "+X": (1, 3, 7, 5)}


def box(size=(1.0, 1.0, 1.0)):
    """Six quads, each its own UV island in a 3 x 2 grid; Blender axes (Z up)."""
    v, uv, f = [], [], []
    for k, (name, q) in enumerate(FACES.items()):
        c, r = k % 3, k // 3
        base = len(v)
        for j, (du, dv) in zip(q, ((0, 0), (1, 0), (1, 1), (0, 1))):
            v.append(BOX[j] * size)
            uv.append(((c + 0.1 + 0.8 * du) / 3, (r + 0.1 + 0.8 * dv) / 2))
        f += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return np.array(v), np.array(uv), np.array(f)


def write(path, v, uv, f, png: bytes | None = None, unlit=False):
    zup_to_gltf = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
    pos = (np.asarray(v, float) @ zup_to_gltf.T).astype("<f4")
    tex = np.c_[np.asarray(uv)[:, 0], 1 - np.asarray(uv)[:, 1]].astype("<f4")
    idx = np.asarray(f, "<u4").reshape(-1)
    chunks = [pos.tobytes(), tex.tobytes(), idx.tobytes()] + ([png] if png else [])
    views, off, blob = [], 0, b""
    for c in chunks:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(c)})
        pad = (-len(c)) % 4
        blob += c + b"\0" * pad
        off += len(c) + pad
    mat = {"name": "m", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "obj"}],
           "meshes": [{"name": "obj", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2,
                                                       "material": 0}]}],
           "materials": [mat], "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
                          "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
                         {"bufferView": 1, "componentType": 5126, "count": len(tex), "type": "VEC2"},
                         {"bufferView": 2, "componentType": 5125, "count": len(idx), "type": "SCALAR"}]}
    if png:
        doc["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
        mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    if unlit:
        mat["extensions"] = {"KHR_materials_unlit": {}}
        doc["extensionsUsed"] = ["KHR_materials_unlit"]
    js = json.dumps(doc).encode()
    js += b" " * ((-len(js)) % 4)
    data = (struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(data)) + data)
    return path
