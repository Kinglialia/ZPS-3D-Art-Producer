"""Script fix before any Codex call (D17; docs/agents/texture-artist.md §3.5; checklist 31): side tones, shaded areas.

Usage: python3 T/tone_fix.py --glb <locked GLB> --model M --albedo A --profile <profile> --res N --out A2
       [--padding 16] [--no-seams]
Per material code, in CIE L* only (a*, b* and the grain stay):
  sides   the four side groups (+X -X +Y -Y by normal) move by one offset each to their area-weighted mean L*,
          when they differ from it by more than SIDE_TOL; top faces move to that mean + style.top_vs_side_L.
  shade   where the low-pass L* (window LOWPASS_FRAC of the atlas) sits more than SHADE_TOL below the group's target,
          it is lifted to target - SHADE_TOL: baked AO under an eave goes, the texel's difference to its low-pass
          (grain, wear) is kept.
Then seam_fix.fix (unless --no-seams). Writes <out> and <out>.json. Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import id_map  # noqa: E402
import seam_fix  # noqa: E402
import tex  # noqa: E402

SIDE_TOL = 1.0
SHADE_TOL = 4.0
LOWPASS_FRAC = 1 / 64
SIDES = ("+X", "-X", "+Y", "-Y")


def groups(tm, codes):
    face = np.where(tm.inside, tm.face, 0)
    code = np.asarray(codes, object)[face]
    side = tex.side_of(tm.nrm.reshape(-1, 3)).reshape(tm.face.shape)
    return code, side


def fix(img, tm, codes, top_l, r):
    lab = tex.lab(img)
    L = lab[..., 0].copy()
    code, side = groups(tm, codes)
    log = {}
    for c in sorted(set(codes)):
        mc = tm.inside & (code == c)
        means = {s: float(L[mc & (side == s)].mean()) for s in SIDES if (mc & (side == s)).any()}
        if not means:
            continue
        sizes = {s: int((mc & (side == s)).sum()) for s in means}
        target = sum(means[s] * sizes[s] for s in means) / sum(sizes.values())
        log[c] = {"target_L": round(target, 2), "moved": {}}
        for s, m in means.items():
            if abs(target - m) > SIDE_TOL:
                L[mc & (side == s)] += target - m
                log[c]["moved"][s] = round(target - m, 2)
        top = mc & (side == "top")
        if top.any() and abs((t := target + top_l) - L[top].mean()) > SIDE_TOL:
            log[c]["moved"]["top"] = round(t - float(L[top].mean()), 2)
            L[top] += t - L[top].mean()
        for s in (*means, "top"):
            m = mc & (side == s)
            if not m.any():
                continue
            low = tex.blur(L, m, r)
            goal = target + (top_l if s == "top" else 0) - SHADE_TOL
            lift = np.where(m & (low < goal), goal - low, 0)
            L += lift
            if lift.any():
                log[c].setdefault("lifted_texels", 0)
                log[c]["lifted_texels"] += int((lift > 0).sum())
    lab[..., 0] = L
    out = np.where(tm.inside[..., None], tex.lab_to_rgb(lab), img)
    return out, log


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--glb", "--model", "--albedo", "--profile", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    p.add_argument("--no-seams", action="store_true")
    a = p.parse_args()
    try:
        import yaml
        style = (yaml.safe_load(open(a.profile, encoding="utf-8")) or {}).get("style") or {}
        codes, g = id_map.face_codes(a.model, a.glb)
        tm = tex.TexelMap(g["v"], g["f"], g["uv"], a.res)
        img, log = fix(tex.load_rgb(a.albedo, a.res), tm, codes, float(style.get("top_vs_side_L") or 0),
                       max(1, round(a.res * LOWPASS_FRAC)))
        rec = {"codes": log}
        if not a.no_seams:
            img, rec["seams"] = seam_fix.fix(img, tm, tex.mesh_area(g["v"], g["f"]), a.padding)
        tex.save_rgb(img, a.out)
    except Exception as e:  # noqa: BLE001
        print(f"[tone_fix] error: {e!r}")
        sys.exit(2)
    json.dump(rec, open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=1)
    moved = sum(len(v["moved"]) for v in log.values())
    print(f"[tone_fix] {moved} nhóm mặt dời tông, {sum(v.get('lifted_texels', 0) for v in log.values())} texel nâng "
          f"-> {a.out}")


if __name__ == "__main__":
    main()
