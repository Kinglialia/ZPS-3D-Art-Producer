"""Texture self-check, four groups (docs/agents/texture-artist.md §6; checklist 19, 58). Regions come from the ID map
(id_map.face_codes), never from fixed labels.

Usage: python3 T/tex_measure.py --final F --glb <locked GLB> --model M --albedo F/albedo_<res>.png
       --concept-colors <CONCEPT_COLORS path of the brief> --profile <profile> --pilot <PILOT line of the brief, or none>
       [--card C/asset-card.yaml]
Per material code (CIE L*; the colour check is dE2000, the seam check dE76):
  1 light     light.side_spread_L.<c>: max - min of the four side means <= side_spread_L. A side mean leaves out groove
                texels; a side under 2 % of the code's texels or under 200 texels has none (side_means)
              light.top_vs_side_L.<c>: |top - side - style.top_vs_side_L| <= top_tol_L
              light.shaded_share.<c>: share of texels whose L* and low-pass L* are both shade_L below the side mean
                <= shaded_share (a bright texel beside a dark island of the atlas is not shaded). Texels and side
                mean leave out groove faces, where the concept draws line art: tex.occluded >= groove_occluded within
                M/spec.json model.alpha_min_px / model.px_per_m metres (data codes.<c>.groove_share).
              light.highlight_share.<c> (info): the same, brighter than the side mean by highlight_L, against
                highlight_share
  2 material  material.dE_concept.<c>: median colour of the code against concept_colors.json <= dE_concept. Both are the
                per-channel RGB median of the code's texels (groove texels left out) and of the concept box
                (views/concept_colors.py), so the same patch compared with itself gives dE 0 (D36.5).
              material.dE_pilot: not_checked without a pilot (D21.7); with one too, since the pilot package has no ID map
  3 read      read.adjacent_dL (info): smallest L* gap between codes that share a mesh edge
              read.hf_noise (info): std of the Laplacian of F/review/thumb.png; not_checked while it does not exist
                (measure runs before render, D36.11)
              read.sharpness.<c> (info): std of the Laplacian of the atlas inside the code; the note names a code under
                sharp_ratio of the median of the other codes
              uv.mirrored_faces (info): faces whose UV triangle runs against the surface (negative determinant). When
                such a face lies in a code of the card's `text_codes` (--card), the note says "chữ có thể bị lật gương
                ở mã …" with the face count, for the reviewer to judge on the renders (it is a UV fault of the model
                step, which the texture worker cannot fix). Never a failure.
  4 seams     seam.p90_dE <= seam_p90 (tex.seam_groups: groups of one material code only, so a border between two
                codes is no seam); seam.unpainted_share (texels darker than RGB 8, codes whose concept colour is that
                dark left out) <= unpainted;
              seam.padding_empty_share: texels in the 2 px ring around islands that are pure black <= padding_empty
Thresholds below; profile `overrides.texture` replaces any of them.
Writes F/review/checks/tex_measure.json. Prints one line. Exit 0, 1 fail, 2 error.
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
import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

LIMITS = {"side_spread_L": 3.0, "top_tol_L": 3.0, "shade_L": 8.0, "shaded_share": 0.02,
          "highlight_L": 8.0, "highlight_share": 0.02, "sharp_ratio": 0.25,  # no run measured these three yet
          "dE_concept": 3.0,  # dE2000 now; the number comes from dE76 and is provisional until the pilot
          "seam_p90": 4.0, "unpainted": 0.001, "padding_empty": 0.01, "groove_occluded": 0.55}
SIDES = ("+X", "-X", "+Y", "-Y")
UNPAINTED_BELOW = 8
SIDE_MIN_SHARE, SIDE_MIN_TEXELS = 0.02, 200  # provisional until the pilot


def side_means(L, mc, side, groove):
    """Mean L* of each of the four sides of the code mc, groove texels left out. A side under SIDE_MIN_SHARE of the
    code's texels or under SIDE_MIN_TEXELS has no mean: the end faces of a trim hold edge bleed, not a side tone."""
    least = max(SIDE_MIN_SHARE * mc.sum(), SIDE_MIN_TEXELS)
    out = {}
    for s in SIDES:
        m = mc & ~groove & (side == s)
        if m.sum() >= least:
            out[s] = float(L[m].mean())
    return out


def limits(prof):
    return LIMITS | ((prof.get("overrides") or {}).get("texture") or {})


def adjacency(f, codes):
    edges = {}
    for k, tri in enumerate(f):
        for i in range(3):
            e = tuple(sorted((int(tri[i]), int(tri[(i + 1) % 3]))))
            edges.setdefault(e, set()).add(codes[k])
    return {tuple(sorted(s)) for s in edges.values() if len(s) == 2}


def welded_faces(g):
    key = np.round(g["v"] / 1e-5).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.reshape(-1)[g["f"]]


def uv_mirrored(g):
    uv = g["uv"]
    a, b, c = (uv[g["f"][:, i]] for i in range(3))
    det = (b[:, 0] - a[:, 0]) * (a[:, 1] - c[:, 1]) - (c[:, 0] - a[:, 0]) * (a[:, 1] - b[:, 1])
    return np.flatnonzero(det < 0)


def text_codes(card):
    """`text_codes` of the card, [] without a card."""
    import yaml
    return ((yaml.safe_load(open(card, encoding="utf-8")) or {}).get("text_codes") or []) if card else []


def laplacian(gray):
    return 4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]


def interior(m):
    """Texels of m (res, res) whose four neighbours are in m, as the (res - 2, res - 2) window laplacian() returns."""
    return m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]


def measure(a, lim, top_l):
    codes, g = id_map.face_codes(a.model, a.glb)
    img = tex.load_rgb(a.albedo)
    res = img.shape[0]
    tm = tex.TexelMap(g["v"], g["f"], g["uv"], res)
    lab = tex.lab(img)
    code = np.asarray(codes, object)[np.where(tm.inside, tm.face, 0)]
    side = tex.side_of(tm.nrm.reshape(-1, 3)).reshape(tm.face.shape)
    model = json.load(open(os.path.join(a.model, "spec.json"), encoding="utf-8")).get("model") or {}
    groove = tex.groove_texels(tm, g["v"], g["f"], model, lim["groove_occluded"])
    concept = json.load(open(a.concept_colors, encoding="utf-8"))
    checks, data = [], {"codes": {}}
    r = max(1, res // 64)
    for c in sorted(set(codes) - {id_map.UNKNOWN}):
        mc = tm.inside & (code == c)
        sides = side_means(lab[..., 0], mc, side, groove)
        row = data["codes"][c] = {"side_L": {s: round(v, 2) for s, v in sides.items()}}
        if sides:
            row["groove_share"] = round(float(groove[mc & np.isin(side, SIDES)].mean()), 4)
            spread = max(sides.values()) - min(sides.values())
            checks.append(tex.check(f"light.side_spread_L.{c}", "pass" if spread <= lim["side_spread_L"] else "fail",
                                    round(spread, 2), lim["side_spread_L"]))
            mean_side = float(np.mean(list(sides.values())))
            top = mc & (side == "top")
            if top.any():
                d = float(lab[top, 0].mean()) - mean_side
                checks.append(tex.check(f"light.top_vs_side_L.{c}", "pass" if abs(d - top_l) <= lim["top_tol_L"] else
                                        "fail", round(d, 2), top_l))
            m = mc & ~groove & np.isin(side, SIDES)
            low = tex.blur(lab[..., 0], m, r)
            ref = list(sides.values())
            dark = float(np.mean(ref)) - lim["shade_L"] if ref else 0.0
            share = float(((low[m] < dark) & (lab[m, 0] < dark)).mean()) if ref else 0.0
            checks.append(tex.check(f"light.shaded_share.{c}", "pass" if share <= lim["shaded_share"] else "fail",
                                    round(share, 4), lim["shaded_share"]))
            bright = float(np.mean(ref)) + lim["highlight_L"] if ref else 0.0
            hi = float(((low[m] > bright) & (lab[m, 0] > bright)).mean()) if ref else 0.0
            checks.append(tex.check(f"light.highlight_share.{c}", "info", round(hi, 4), lim["highlight_share"],
                                    note="vượt ngưỡng" if hi > lim["highlight_share"] else None))
        if c in concept:
            body = mc & ~groove if (mc & ~groove).any() else mc
            med = np.round(np.median(img[body], 0))
            de = float(tex.de2000(tex.lab(med), tex.lab(tex.hex_rgb(concept[c]))))
            row["median"] = "#%02X%02X%02X" % tuple(int(x) for x in med)
            row["dE_concept"] = round(de, 2)
            checks.append(tex.check(f"material.dE_concept.{c}", "pass" if de <= lim["dE_concept"] else "fail",
                                    round(de, 2), lim["dE_concept"]))
        else:
            checks.append(tex.check(f"material.dE_concept.{c}", "not_checked", note="mã không có trong concept_colors"))
    checks.append(tex.check("material.dE_pilot", "not_checked",
                            note="chưa có pilot" if a.pilot in ("", "none") else "gói pilot không có ID map theo mã"))
    means = {c: float(lab[tm.inside & (code == c), 0].mean()) for c in set(codes) if (tm.inside & (code == c)).any()}
    pairs = [abs(means[x] - means[y]) for x, y in adjacency(welded_faces(g), codes) if x in means and y in means]
    checks.append(tex.check("read.adjacent_dL", "info", round(min(pairs), 2) if pairs else None))
    thumb = os.path.join(a.final, "review", "thumb.png")
    if os.path.isfile(thumb):
        checks.append(tex.check("read.hf_noise", "info", round(float(laplacian(tex.load_rgb(thumb).mean(-1)).std()), 2)))
    else:
        checks.append(tex.check("read.hf_noise", "not_checked", note="chưa có review/thumb.png"))
    lap = laplacian(img.mean(-1))
    sharp = {}
    for c in data["codes"]:
        m = interior(tm.inside & (code == c))
        if m.sum() > 1:
            sharp[c] = float(lap[m].std())
    for c, v in sharp.items():
        others = [x for k, x in sharp.items() if k != c]
        weak = bool(others) and np.median(others) > 0 and v < lim["sharp_ratio"] * np.median(others)
        data["codes"][c]["sharpness"] = round(v, 2)
        checks.append(tex.check(f"read.sharpness.{c}", "info", round(v, 2),
                                note="thấp so với trung vị mã khác" if weak else None))
    mirrored = uv_mirrored(g)
    data["uv_mirrored"] = {"count": len(mirrored), "faces": mirrored[:200].tolist(),
                           "by_code": {c: int((np.asarray(codes, object)[mirrored] == c).sum()) for c in sorted(set(codes))}}
    text_hit = {c: n for c, n in data["uv_mirrored"]["by_code"].items() if n and c in text_codes(a.card)}
    checks.append(tex.check("uv.mirrored_faces", "info", len(mirrored), note="chữ có thể bị lật gương ở mã " + ", ".join(
        f"{c} ({n} mặt lật UV)" for c, n in text_hit.items()) if text_hit else None))
    idx, gid = tex.seam_groups(tm, tex.mesh_area(g["v"], g["f"]), codes)
    p90 = tex.seam_spread(img, idx, gid)
    checks.append(tex.check("seam.p90_dE", "pass" if p90 <= lim["seam_p90"] else "fail", round(p90, 2), lim["seam_p90"]))
    near_black = [c for c in concept if tex.hex_rgb(concept[c]).max() < 2 * UNPAINTED_BELOW]
    live = tm.inside & ~np.isin(code, near_black)
    dark = float((img[live].max(-1) < UNPAINTED_BELOW).mean()) if live.any() else 0.0
    checks.append(tex.check("seam.unpainted_share", "pass" if dark <= lim["unpainted"] else "fail", round(dark, 4),
                            lim["unpainted"]))
    ring = tex.border(~tm.inside) & ~tm.inside
    ring |= tex.border(~(tm.inside | ring)) & ~(tm.inside | ring)
    empty = float((img[ring].max(-1) == 0).mean()) if ring.any() else 0.0
    checks.append(tex.check("seam.padding_empty_share", "pass" if empty <= lim["padding_empty"] else "fail",
                            round(empty, 4), lim["padding_empty"]))
    return checks, data


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--final", "--glb", "--model", "--albedo", "--concept-colors", "--profile"):
        p.add_argument(k, required=True)
    p.add_argument("--pilot", default="none")
    p.add_argument("--card")
    a = p.parse_args()
    out = os.path.join(a.final, "review", "checks", "tex_measure.json")
    try:
        import yaml
        prof = yaml.safe_load(open(a.profile, encoding="utf-8")) or {}
        lim = limits(prof)
        checks, data = measure(a, lim, float((prof.get("style") or {}).get("top_vs_side_L") or 0))
    except Exception as e:  # noqa: BLE001
        tex.write_error(out, "tex_measure", e)
        print(f"[tex_measure] error: {e!r}")
        sys.exit(2)
    r = tex.write_result(out, "tex_measure", checks, data=data | {"limits": lim})
    bad = [c["check"] for c in checks if c["status"] == "fail"]
    print(f"[tex_measure] {r['overall']}" + (f": {', '.join(bad)}" if bad else "") + f" -> {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    require_root()
    main()
