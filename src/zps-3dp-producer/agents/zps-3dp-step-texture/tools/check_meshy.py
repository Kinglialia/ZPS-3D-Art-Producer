"""The Meshy GLB kept the locked mesh: same triangles, same UV at every corner (texture-artist.md §2.2; checklist 75).

Usage: python3 T/check_meshy.py --final F --locked <locked GLB> --meshy <meshy_call glb.glb> --res N --albedo-out <png>
Triangles are matched by their three corner positions (rounded to POS_M); each matched corner compares its UV.
Pass: same triangle count, every triangle matched, max UV shift <= 0.5 texel at --res. Then the base colour image of
the Meshy GLB is written to --albedo-out at N x N (the Meshy layer for SỬA mode). A fail keeps no albedo: drop that GLB.
Writes F/review/checks/meshy.json. Prints one line. Exit 0, 1 fail, 2 error.
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import numpy as np  # noqa: E402

import tex  # noqa: E402

POS_M = 1e-4


def corners(g):
    out = {}
    for tri in g["f"]:
        key = tuple(sorted(tuple(np.round(g["v"][i] / POS_M).astype(int)) for i in tri))
        out[key] = {tuple(np.round(g["v"][i] / POS_M).astype(int)): g["uv"][i] for i in tri}
    return out


def compare(locked, meshy, res):
    a, b = tex.read_glb(locked), tex.read_glb(meshy)
    if b["uv"] is None:
        return [tex.check("meshy.uv", "fail", None, note="Meshy GLB has no TEXCOORD_0")], b
    ca, cb = corners(a), corners(b)
    missing = sum(k not in cb for k in ca)
    shift = max((float(np.abs(ca[k][c] - cb[k][c]).max()) for k in ca if k in cb for c in ca[k]), default=0.0) * res
    return [tex.check("meshy.tris", "pass" if len(a["f"]) == len(b["f"]) else "fail", len(b["f"]), len(a["f"])),
            tex.check("meshy.unmatched_tris", "pass" if missing == 0 else "fail", missing, 0),
            tex.check("meshy.uv_shift_px", "pass" if shift <= 0.5 else "fail", round(shift, 3), 0.5)], b


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--final", "--locked", "--meshy", "--albedo-out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    a = p.parse_args()
    out = os.path.join(a.final, "review", "checks", "meshy.json")
    try:
        checks, g = compare(a.locked, a.meshy, a.res)
        ok = all(c["status"] == "pass" for c in checks)
        if ok and g["images"]:
            from PIL import Image
            im = Image.open(io.BytesIO(g["images"][0])).convert("RGB")
            checks.append(tex.check("meshy.image_px", "info", list(im.size), a.res,
                                    note="scaled to --res" if im.size != (a.res, a.res) else None))
            os.makedirs(os.path.dirname(os.path.abspath(a.albedo_out)), exist_ok=True)
            im.resize((a.res, a.res), Image.LANCZOS).save(a.albedo_out)
        elif ok:
            checks.append(tex.check("meshy.image", "fail", 0, 1, note="Meshy GLB has no base colour image"))
    except Exception as e:  # noqa: BLE001
        tex.write_error(out, "check_meshy", e)
        print(f"[check_meshy] error: {e!r}")
        sys.exit(2)
    r = tex.write_result(out, "check_meshy", checks)
    bad = [c["check"] for c in checks if c["status"] == "fail"]
    print(f"[check_meshy] {'fail ' + ', '.join(bad) + ': bỏ GLB này' if bad else 'giữ UV và tam giác'} -> {out}")
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    main()
