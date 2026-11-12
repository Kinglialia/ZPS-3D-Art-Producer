"""Material code of every face of the locked mesh, and the ID map atlas (docs/agents/texture-artist.md §6).

Usage: python3 T/id_map.py --final F --model M [--res N]
The model join keeps the part triangles as they are, moved by its origin offset (M/review/join.json). Each face of
M/<id>-untextured.glb takes the part whose triangle centroid lies nearest (M/parts/<part>.glb, Y-up GLB of kit
assembly.py), looked up in cells of MATCH_M so memory grows with the mesh, not with faces x part triangles; the part's
code is its `material` in M/part_graph.json, or that of the part named in `mirror_of`.
A face farther than MATCH_M from every part triangle is `?`.
Writes F/review/id_map.png (one flat colour per code) and F/review/id_map.json {codes: {code: hex}, faces: {code: n},
unmatched}. Prints one line. Exit 0, 1 when a face is unmatched, 2 on error.
"""
import argparse
import colorsys
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import numpy as np  # noqa: E402

import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

MATCH_M = 1e-3
UNKNOWN = "?"


def part_codes(model):
    g = json.load(open(os.path.join(model, "part_graph.json"), encoding="utf-8"))
    by = {p["name"]: p for p in g.get("parts", [])}

    def code(name):
        p = by.get(name) or {}
        return p.get("material") or code((p.get("attach") or {}).get("of", "")) if p else UNKNOWN
    return code


def offset(model):
    j = json.load(open(os.path.join(model, "review", "join.json"), encoding="utf-8"))
    return np.asarray(next(c["value"] for c in j["checks"] if c["check"] == "join.origin_offset_m"), float)


def face_codes(model, glb=None):
    """Codes per face of the locked GLB, in its face order."""
    spec = json.load(open(os.path.join(model, "spec.json"), encoding="utf-8"))
    g = tex.read_glb(glb or os.path.join(model, f"{spec['asset']}-untextured.glb"))
    c = g["v"][g["f"]].mean(1)
    code, off = part_codes(model), offset(model)
    cents, names = [], []
    for name in sorted(os.listdir(os.path.join(model, "parts"))):
        if name.endswith(".glb"):
            p = tex.read_glb(os.path.join(model, "parts", name))
            cents.append(p["v"][p["f"]].mean(1) + off)
            names += [name[:-4]] * len(p["f"])
    best = nearest(c, np.concatenate(cents), MATCH_M)
    return [code(names[b]) if b >= 0 else UNKNOWN for b in best], g


def nearest(points, cents, r):
    """Index of the nearest of cents within r of each point (lowest index on a tie), -1 when none. Cells of size r: a
    centroid within r lies in one of the 27 cells round the point's own, so a float32 join near a cell border still
    finds its part."""
    grid = {}
    for j, key in enumerate(map(tuple, np.floor(cents / r).astype(np.int64).tolist())):
        grid.setdefault(key, []).append(j)
    out = np.full(len(points), -1)
    for i, (p, key) in enumerate(zip(points, np.floor(points / r).astype(np.int64).tolist())):
        near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                for j in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ())]
        if near:
            near.sort()
            d = np.linalg.norm(cents[near] - p, axis=1)
            k = int(d.argmin())
            if d[k] <= r:
                out[i] = near[k]
    return out


def palette(codes):
    out = {}
    for i, k in enumerate(sorted(codes)):
        r, gg, b = colorsys.hsv_to_rgb((i * 0.618) % 1, 0.65, 0.95)
        out[k] = "#%02X%02X%02X" % (round(r * 255), round(gg * 255), round(b * 255))
    out[UNKNOWN] = "#000000"
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--res", type=int)
    a = p.parse_args()
    out = os.path.join(a.final, "review", "id_map.json")
    try:
        codes, g = face_codes(a.model)
        spec = json.load(open(os.path.join(a.model, "spec.json"), encoding="utf-8"))
        res = a.res or int(spec["uv"]["resolution"])
        tm = tex.TexelMap(g["v"], g["f"], g["uv"], res)
        pal = palette(set(codes) - {UNKNOWN})
        lut = np.array([tex.hex_rgb(pal[k]) for k in codes] + [[255, 255, 255]])
        tex.save_rgb(lut[np.where(tm.inside, tm.face, len(codes))], os.path.join(a.final, "review", "id_map.png"))
    except Exception as e:  # noqa: BLE001
        tex.write_error(out, "id_map", e)
        print(f"[id_map] error: {e!r}")
        sys.exit(2)
    faces = {k: codes.count(k) for k in sorted(set(codes))}
    bad = faces.pop(UNKNOWN, 0)
    tex.write_result(out, "id_map", [tex.check("id_map.unmatched_faces", "fail" if bad else "pass", bad, 0)],
                     data={"codes": {k: pal[k] for k in faces}, "faces": faces, "unmatched": bad})
    print(f"[id_map] {len(faces)} mã, {sum(faces.values())} mặt" + (f", {bad} mặt không khớp part" if bad else "")
          + f" -> {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    require_root()
    main()
