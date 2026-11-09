"""VẼ MỚI step 6 and SỬA (docs/agents/texture-artist.md §4, §3): even out UV seams in 3D, then pad the islands.

Usage: python3 T/seam_fix.py --glb <locked GLB> --albedo A --res N --out A2 [--padding 16]
Seam texels are island border texels that meet a texel of another face at the same 3D point (tex.seam_groups); each
group takes its mean colour, so both sides of a seam match. Then --padding px of gutter around every island.
Writes <out> and <out>.json {seam_p90_before, seam_p90_after, groups}. Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import numpy as np  # noqa: E402

import tex  # noqa: E402


def fix(img, tm, area, padding):
    idx, gid = tex.seam_groups(tm, area)
    before = tex.seam_spread(img, idx, gid)
    out = img.reshape(-1, 3).copy()
    if len(idx):
        n = np.bincount(gid)
        mean = np.stack([np.bincount(gid, out[idx, k]) for k in range(3)], 1) / n[:, None]
        out[idx] = mean[gid]
    out = out.reshape(img.shape)
    return tex.gutter(out, tm.inside, padding), {"seam_p90_before": round(before, 2),
                                                  "seam_p90_after": round(tex.seam_spread(out, idx, gid), 2),
                                                  "groups": int(len(np.unique(gid))) if len(idx) else 0}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--glb", "--albedo", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    a = p.parse_args()
    try:
        g, tm = tex.load_map(a.glb, a.res)
        img, rec = fix(tex.load_rgb(a.albedo, a.res), tm, tex.mesh_area(g["v"], g["f"]), a.padding)
        tex.save_rgb(img, a.out)
    except Exception as e:  # noqa: BLE001
        print(f"[seam_fix] error: {e!r}")
        sys.exit(2)
    json.dump(rec, open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"[seam_fix] seam p90 {rec['seam_p90_before']} → {rec['seam_p90_after']} ({rec['groups']} nhóm) -> {a.out}")


if __name__ == "__main__":
    main()
