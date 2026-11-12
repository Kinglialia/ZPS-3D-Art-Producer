"""Script fix before any Codex call (D17; docs/agents/texture-artist.md §3.5; checklist 31): side tones, shaded areas.

Usage: python3 T/tone_fix.py --glb <locked GLB> --model M --albedo A --profile <profile> --res N --out A2
       [--concept-colors concept_colors.json] [--padding 16] [--no-seams]
Per material code:
  sides   in CIE L*: the four side groups (+X -X +Y -Y by normal) move by one offset each to their area-weighted mean
          L*, when they differ from it by more than SIDE_TOL; top faces move to that mean + style.top_vs_side_L. The
          means are tex_measure.side_means: groove texels left out, a side with too few texels neither counts nor moves.
  shade   in CIE L*: where the low-pass L* (window LOWPASS_FRAC of the atlas) sits more than SHADE_TOL below the group's
          target, it is lifted to target - SHADE_TOL: baked AO under an eave goes, the texel's difference to its
          low-pass (grain, wear) is kept. Groove faces (tex.groove_texels, the same mask as tex_measure) are not
          lifted and do not count in the target of the lift: the concept draws line art there.
  hue     with --concept-colors: all texels of the code but the groove ones move by one a*b* offset, from the median
          colour of the code to the concept colour, at most AB_MAX long and only above AB_TOL, and by one L* offset
          the same way, at most L_MAX. This runs after the side and shade steps, so the sides keep their flattening.
          The grain stays.
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
import tex_measure  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

SIDE_TOL = 1.0
SHADE_TOL = 4.0
AB_MAX = 12.0  # a wrong concept box must not repaint a whole material
L_MAX = 12.0
AB_TOL = 1.0
LOWPASS_FRAC = 1 / 64


def groups(tm, codes):
    face = np.where(tm.inside, tm.face, 0)
    code = np.asarray(codes, object)[face]
    side = tex.side_of(tm.nrm.reshape(-1, 3)).reshape(tm.face.shape)
    return code, side


def fix(img, tm, codes, top_l, r, groove, concept=None):
    lab = tex.lab(img)
    L = lab[..., 0].copy()
    code, side = groups(tm, codes)
    log = {}
    for c in sorted(set(codes)):
        mc = tm.inside & (code == c)
        means = tex_measure.side_means(L, mc, side, groove)
        if not means:
            continue
        sizes = {s: int((mc & ~groove & (side == s)).sum()) for s in means}
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
        paint = list(tex_measure.side_means(L, mc, side, groove).values())
        ref = float(np.mean(paint)) if paint else target
        for s in (*means, "top"):
            m = mc & (side == s) & ~groove
            if not m.any():
                continue
            low = tex.blur(L, m, r)
            goal = ref + (top_l if s == "top" else 0) - SHADE_TOL
            lift = np.where(m & (low < goal), goal - low, 0)
            L += lift
            if lift.any():
                log[c].setdefault("lifted_texels", 0)
                log[c]["lifted_texels"] += int((lift > 0).sum())
    lab[..., 0] = L
    cur = tex.lab_to_rgb(lab)
    for c, hexa in (concept or {}).items():
        m = tm.inside & (code == c) & ~groove
        if not m.any():
            continue
        d = tex.lab(tex.hex_rgb(hexa)) - tex.lab(np.round(np.median(cur[m], 0)))
        if abs(d[0]) > AB_TOL:
            dl = float(np.clip(d[0], -L_MAX, L_MAX))
            lab[m, 0] += dl
            log.setdefault(c, {"moved": {}})["L_shift"] = round(dl, 2)
        n = float(np.linalg.norm(d[1:]))
        if n > AB_TOL:
            ab = d[1:] * min(1.0, AB_MAX / n)
            lab[m, 1:] += ab
            log.setdefault(c, {"moved": {}})["ab_shift"] = [round(float(x), 2) for x in ab]
    out = np.where(tm.inside[..., None], tex.lab_to_rgb(lab), img)
    return out, log


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--glb", "--model", "--albedo", "--profile", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--concept-colors")
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    p.add_argument("--no-seams", action="store_true")
    a = p.parse_args()
    try:
        import yaml
        prof = yaml.safe_load(open(a.profile, encoding="utf-8")) or {}
        style = prof.get("style") or {}
        codes, g = id_map.face_codes(a.model, a.glb)
        tm = tex.TexelMap(g["v"], g["f"], g["uv"], a.res)
        model = json.load(open(os.path.join(a.model, "spec.json"), encoding="utf-8")).get("model") or {}
        groove = tex.groove_texels(tm, g["v"], g["f"], model, tex_measure.limits(prof)["groove_occluded"])
        concept = json.load(open(a.concept_colors, encoding="utf-8")) if a.concept_colors else None
        img, log = fix(tex.load_rgb(a.albedo, a.res), tm, codes, float(style.get("top_vs_side_L") or 0),
                       max(1, round(a.res * LOWPASS_FRAC)), groove, concept)
        rec = {"codes": log}
        if not a.no_seams:
            img, rec["seams"] = seam_fix.fix(img, tm, tex.mesh_area(g["v"], g["f"]), codes, a.padding)
        tex.save_rgb(img, a.out)
    except Exception as e:  # noqa: BLE001
        print(f"[tone_fix] error: {e!r}")
        sys.exit(2)
    json.dump(rec, open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=1)
    moved = sum(len(v["moved"]) for v in log.values())
    print(f"[tone_fix] {moved} nhóm mặt dời tông, {sum(v.get('lifted_texels', 0) for v in log.values())} texel nâng "
          f"-> {a.out}")


if __name__ == "__main__":
    require_root()
    main()
