"""Measure how well AI-generated views match the blockout and each other; write a report.

  python3 <SKILL>/scripts/measure_views.py --blockout <abs>/views_blockout --gen <abs>/views_gen \
      --out <abs>/report [--views front,back,left,right,top] [--concept-colors concept_colors.json] [--bg-threshold 40]

--blockout  folder from render_blockout_views.py (<view>_id.png + views.json)
--gen       folder with the generated images named front/back/left/right/top/bottom (.png/.jpg/.webp).
            Missing views are skipped. Images should have a flat, plain background (or alpha).
--concept-colors  optional JSON {"material name": "#RRGGBB"} measured on the concept.

Outputs in --out: report.md (English), report.json, overlay_sheet.png.

The AI will not keep the blockout's framing, so every comparison is done after cropping both
images to the subject's bounding box and resizing to a common frame. Absolute size is not judged;
proportions (aspect ratio), silhouette shape, where material borders fall, and colours are.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw

VIEWS = ["front", "back", "left", "right", "top", "bottom"]
VIEW_NAME = {"front": "Front", "back": "Back", "left": "Left", "right": "Right", "top": "Top", "bottom": "Bottom"}
# (pair, flip) — orthographic silhouettes of opposite views are exact mirror images.
MIRROR_PAIRS = [("front", "back", "lr"), ("left", "right", "lr"), ("top", "bottom", "ud")]
N = 320  # common frame size

TH = {  # (pass if >=/<=, warn if >=/<=) — beyond warn is fail
    "iou": (0.93, 0.88),
    "aspect_err": (0.03, 0.06),
    "detail": (0.75, 0.60),
    "delta_e": (6.0, 12.0),
    "mirror": (0.93, 0.88),
    "proportion_err": (0.04, 0.08),
}
ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", None: "—"}


# ---------------------------------------------------------------- helpers
def status(metric, v):
    if v is None:
        return None
    good, warn = TH[metric]
    if metric in ("aspect_err", "delta_e", "proportion_err"):
        v = abs(v)
        return "pass" if v <= good else "warn" if v <= warn else "fail"
    return "pass" if v >= good else "warn" if v >= warn else "fail"


def worst(states):
    states = [s for s in states if s]
    for s in ("fail", "warn", "pass"):
        if s in states:
            return s
    return None


def shift(a, dy, dx):
    out = np.zeros_like(a)
    h, w = a.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx <= r * r:
                out |= shift(m, dy, dx)
    return out


def erode(m, r):
    return ~dilate(~m, r)


def flood_background(bgish):
    """Background = bg-coloured pixels connected to the image border."""
    reach = np.zeros_like(bgish)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = bgish[0, :], bgish[-1, :], bgish[:, 0], bgish[:, -1]
    while True:
        grown = (reach | shift(reach, 1, 0) | shift(reach, -1, 0) | shift(reach, 0, 1) | shift(reach, 0, -1)) & bgish
        if (grown == reach).all():
            return reach
        reach = grown


def bbox(mask, min_count=3):
    rows = np.where(mask.sum(1) >= min_count)[0]
    cols = np.where(mask.sum(0) >= min_count)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return rows[0], rows[-1] + 1, cols[0], cols[-1] + 1  # y0, y1, x0, x1


def to_frame(arr, bb, resample):
    y0, y1, x0, x1 = bb
    im = Image.fromarray(arr[y0:y1, x0:x1])
    return np.array(im.resize((N, N), resample))


def srgb_to_lab(rgb):
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def delta_e(a, b):
    """CIE76 with lightness at half weight: the same material is lit differently on a sloped
    face or from another side, so a brightness shift matters less than a hue/saturation shift."""
    d = srgb_to_lab(a) - srgb_to_lab(b)
    d[0] *= 0.5
    return float(np.linalg.norm(d))


def hexc(rgb):
    return "#%02X%02X%02X" % tuple(int(round(x)) for x in rgb)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])


def find_gen(folder, view):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(folder, view + ext)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------- loading
def load_blockout(folder, view, palette):
    a = np.array(Image.open(os.path.join(folder, f"{view}_id.png")).convert("RGBA"))
    mask = a[..., 3] > 127
    rgb = a[..., :3].astype(int)
    d = ((rgb[..., None, :] - palette[None, None]) ** 2).sum(-1)
    label = np.where(mask, d.argmin(-1), -1)
    bb = bbox(mask)
    return {"mask": mask, "label": label, "bb": bb}


def load_gen(path, bg_threshold):
    im = Image.open(path)
    im = im.convert("RGBA")
    scale = 512 / max(im.size)
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    a = np.array(im)
    rgb = a[..., :3]
    alpha = a[..., 3]
    if alpha.min() < 250:
        mask = alpha > 127
        bg_hex = "alpha"
    else:
        border = np.concatenate([rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                                 rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)])
        bg = np.median(border, 0)
        bgish = np.linalg.norm(rgb.astype(float) - bg, axis=-1) < bg_threshold
        mask = ~flood_background(bgish)
        bg_hex = hexc(bg)
    mask = dilate(erode(mask, 1), 1)  # remove specks
    return {"rgb": rgb, "mask": mask, "bb": bbox(mask), "bg": bg_hex, "size": im.size}


def blur(f, r=2):
    """Box blur (2r+1)^2 — removes fine texture (grain, noise) but keeps material borders."""
    acc = np.zeros_like(f)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            acc += np.roll(f, (dy, dx), (0, 1))
    return acc / (2 * r + 1) ** 2


def edges(rgb, mask):
    f = blur(rgb.astype(float))
    # difference across 4px so a blurred step keeps ~80% of its contrast
    gy = np.abs(np.roll(f, -2, 0) - np.roll(f, 2, 0)).max(-1)
    gx = np.abs(np.roll(f, -2, 1) - np.roll(f, 2, 1)).max(-1)
    g = np.maximum(gx, gy)
    inside = g[mask]
    if inside.size == 0:
        return np.zeros_like(mask)
    t = max(np.percentile(inside, 85), 18.0)
    return (g >= t) & mask


def internal_boundaries(label):
    b = np.zeros(label.shape, bool)
    for dy, dx in ((0, 1), (1, 0)):
        nb = np.roll(label, (-dy, -dx), (0, 1))
        b |= (label != nb) & (label >= 0) & (nb >= 0)
    b[-1, :] = b[:, -1] = False
    return b


# ---------------------------------------------------------------- measuring
def measure_view(view, blk, gen, mat_names):
    r = {"view": view}
    if gen["bb"] is None:
        r["error"] = "Could not separate the object from the background (background not uniform?)"
        return r, None
    bm = to_frame(blk["mask"].astype(np.uint8) * 255, blk["bb"], Image.NEAREST) > 127
    bl = _label_frame(blk["label"], blk["bb"])
    gm = to_frame(gen["mask"].astype(np.uint8) * 255, gen["bb"], Image.NEAREST) > 127
    gr = to_frame(gen["rgb"], gen["bb"], Image.BILINEAR)

    inter, union = (bm & gm).sum(), (bm | gm).sum()
    r["iou"] = float(inter / union) if union else 0.0
    by0, by1, bx0, bx1 = blk["bb"]
    gy0, gy1, gx0, gx1 = gen["bb"]
    blk_aspect = (by1 - by0) / (bx1 - bx0)
    gen_aspect = (gy1 - gy0) / (gx1 - gx0)
    r["aspect_blockout"] = blk_aspect
    r["aspect_gen"] = gen_aspect
    r["aspect_err"] = gen_aspect / blk_aspect - 1

    ib = internal_boundaries(bl)
    r["detail"], r["detail_worst"], r["detail_by_material"] = None, None, {}
    if ib.sum() >= 20:
        ge = dilate(edges(gr, gm), 4)
        # chance correction: on a busy texture, edges are everywhere and any border would "match"
        cov = float(ge[gm].mean()) if gm.any() else 0.0
        r["edge_coverage"] = cov
        # score each material's own border, so a small moved part (window) is not hidden by big ones
        near = dilate(ib, 1)
        for k, name in enumerate(mat_names):
            region = bl == k
            own = near & region & dilate(~region & (bl >= 0), 2)
            if own.sum() >= 20:
                recall = (own & ge).sum() / own.sum()
                r["detail_by_material"][name] = float(max(0.0, (recall - cov) / max(1 - cov, 1e-6)))
        if r["detail_by_material"]:
            r["detail_worst"] = min(r["detail_by_material"], key=r["detail_by_material"].get)
            r["detail"] = r["detail_by_material"][r["detail_worst"]]

    colours = {}
    for k, name in enumerate(mat_names):
        region = erode(bl == k, 3) & erode(gm, 2)
        if region.sum() >= 40:
            colours[name] = hexc(np.median(gr[region], 0))
    r["colours"] = colours
    r["status"] = {
        "iou": status("iou", r["iou"]),
        "aspect_err": status("aspect_err", r["aspect_err"]),
        "detail": status("detail", r["detail"]),
    }
    frames = {"bm": bm, "bl": bl, "gm": gm, "gr": gr, "ib": ib}
    return r, frames


def _label_frame(label, bb):
    y0, y1, x0, x1 = bb
    crop = label[y0:y1, x0:x1]
    ys = (np.arange(N) * (y1 - y0) / N).astype(int)
    xs = (np.arange(N) * (x1 - x0) / N).astype(int)
    return crop[ys][:, xs]


def overlay(fr, palette):
    base = (fr["gr"].astype(float) * 0.55 + 255 * 0.45).astype(np.uint8)
    out = base.copy()
    out[fr["bm"] & ~fr["gm"]] = (230, 30, 30)    # blockout has it, AI image does not
    out[fr["gm"] & ~fr["bm"]] = (0, 170, 230)    # AI image has it, blockout does not
    out[dilate(fr["ib"], 1)] = (255, 200, 0)     # where material borders should be
    idimg = np.full((N, N, 3), 255, np.uint8)
    lab = fr["bl"]
    for k, c in enumerate(palette):
        idimg[lab == k] = c
    gen = fr["gr"].copy()
    gen[~fr["gm"]] = (gen[~fr["gm"]] * 0.3 + 255 * 0.7).astype(np.uint8)
    return idimg, gen, out


def make_sheet(rows, path):
    pad, head = 10, 26
    W = 3 * N + 4 * pad
    H = len(rows) * (N + head + pad) + head + pad
    sheet = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(["Blockout (ID)", "AI gen (cropped to subject)", "Difference"]):
        d.text((pad + i * (N + pad), 6), t, fill="black")
    for r, (view, imgs, verdict) in enumerate(rows):
        y = head + pad + r * (N + head + pad)
        d.text((pad, y), f"{view.upper()}  {verdict}", fill="black")
        for i, im in enumerate(imgs):
            sheet.paste(Image.fromarray(im), (pad + i * (N + pad), y + head - 6))
    d.text((pad, H - 16), "Red = in blockout, missing in AI | Blue = extra in AI | Yellow = where material borders must be", fill="black")
    sheet.save(path)


# ---------------------------------------------------------------- report
def fixes_for(r, colour_rows):
    out = []
    v = VIEW_NAME[r["view"]]
    if r.get("error"):
        return [f"{v}: {r['error']}. Generate again with a plain one-colour background and no cast shadow."]
    if r["status"]["iou"] in ("warn", "fail"):
        out.append(f"Silhouette differs from the blockout, IoU {r['iou']:.2f}: see the red/blue areas on the overlay; generate again and stress 'keep the exact silhouette of the guide render'.")
    if r["status"]["aspect_err"] in ("warn", "fail"):
        word = "taller/narrower than" if r["aspect_err"] > 0 else "shorter/wider than"
        out.append(f"Proportions are stretched: the image is {abs(r['aspect_err'])*100:.1f}% {word} the blockout; ask for no crop and no stretch.")
    if r["status"]["detail"] in ("warn", "fail"):
        out.append(f"Detail '{r['detail_worst']}' is misplaced or missing: only {r['detail']*100:.0f}% of its blockout border has a matching edge in the AI image; see the yellow lines on the overlay.")
    for mat, info in colour_rows.items():
        cell = info["views"].get(r["view"])
        if cell and cell["status"] in ("warn", "fail"):
            out.append(f"Colour '{mat}' is off by dE {cell['delta_e']:.1f}: now {cell['hex']}, needs to be close to {info['reference_hex']} ({info['reference']}).")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--blockout", required=True)
    p.add_argument("--gen", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--concept-colors")
    p.add_argument("--bg-threshold", type=float, default=40)
    p.add_argument("--views", default="front,back,left,right,top",
                   help="views to measure; bottom only when it was requested")
    a = p.parse_args()
    wanted = [v for v in VIEWS if v in a.views.split(",")]
    os.makedirs(a.out, exist_ok=True)

    meta = json.load(open(os.path.join(a.blockout, "views.json")))
    mat_names = list(meta["materials"])
    palette = np.array([hex_rgb(meta["materials"][m]) for m in mat_names])
    concept = json.load(open(a.concept_colors)) if a.concept_colors else {}

    results, frames, missing = {}, {}, []
    for view in wanted:
        gp = find_gen(a.gen, view)
        if not gp:
            missing.append(view)
            continue
        blk = load_blockout(a.blockout, view, palette)
        gen = load_gen(gp, a.bg_threshold)
        r, fr = measure_view(view, blk, gen, mat_names)
        r["file"] = os.path.basename(gp)
        r["background"] = gen["bg"]
        results[view], frames[view] = r, fr

    # colour consistency per material across views
    colour_rows = {}
    for mat in mat_names:
        per_view = {v: r["colours"][mat] for v, r in results.items() if "colours" in r and mat in r["colours"]}
        if not per_view:
            continue
        if mat in concept:
            ref, ref_name = concept[mat], "concept"
        elif "front" in per_view:
            ref, ref_name = per_view["front"], "front view"
        else:
            med = np.median([hex_rgb(h) for h in per_view.values()], 0)
            ref, ref_name = hexc(med), "median of the views"
        cells = {}
        for v, h in per_view.items():
            de = delta_e(hex_rgb(h), hex_rgb(ref))
            cells[v] = {"hex": h, "delta_e": de, "status": status("delta_e", de)}
        colour_rows[mat] = {"reference": ref_name, "reference_hex": ref, "views": cells}
    for v, r in results.items():
        des = [c["views"][v]["delta_e"] for c in colour_rows.values() if v in c["views"]]
        if "status" in r:
            r["max_delta_e"] = max(des) if des else None
            r["status"]["colour"] = status("delta_e", r["max_delta_e"])

    # mirror checks between opposite AI views (independent of the blockout)
    mirrors = []
    for va, vb, flip in MIRROR_PAIRS:
        if va in frames and vb in frames and frames[va] and frames[vb]:
            m2 = frames[vb]["gm"]
            m2 = m2[:, ::-1] if flip == "lr" else m2[::-1]
            m1 = frames[va]["gm"]
            iou = float((m1 & m2).sum() / max((m1 | m2).sum(), 1))
            asp = results[va]["aspect_gen"] / results[vb]["aspect_gen"] - 1
            st = worst([status("mirror", iou), status("proportion_err", asp)])
            mirrors.append({"pair": f"{va}/{vb}", "iou": iou, "aspect_diff": asp, "status": st})

    # cross-view proportion: front(H/W) should equal side(H/D) * top(D/W)
    proportion = None
    side = next((v for v in ("right", "left") if v in results and "aspect_gen" in results[v]), None)
    if "front" in results and "aspect_gen" in results["front"] and side and "top" in results and "aspect_gen" in results["top"]:
        lhs = results["front"]["aspect_gen"]
        rhs = results[side]["aspect_gen"] * results["top"]["aspect_gen"]
        err = lhs / rhs - 1
        proportion = {"views": f"front vs {side} x top", "err": err, "status": status("proportion_err", err)}

    # scores
    def clamp(x):
        return max(0.0, min(1.0, x))

    for v, r in results.items():
        if "status" not in r:
            r["score"], r["verdict"] = 0, "fail"
            continue
        parts = [clamp((r["iou"] - 0.7) / 0.3), clamp(1 - abs(r["aspect_err"]) / 0.1)]
        if r["detail"] is not None:
            parts.append(r["detail"])
        if r.get("max_delta_e") is not None:
            parts.append(clamp(1 - r["max_delta_e"] / 20))
        r["score"] = round(100 * sum(parts) / len(parts))
        r["verdict"] = worst(r["status"].values())
    cross = [clamp((m["iou"] - 0.7) / 0.3) for m in mirrors]
    if proportion:
        cross.append(clamp(1 - abs(proportion["err"]) / 0.1))
    view_scores = [r["score"] for r in results.values()]
    overall = round(0.8 * np.mean(view_scores) + 0.2 * 100 * np.mean(cross)) if cross else round(np.mean(view_scores)) if view_scores else 0
    overall_verdict = worst([r["verdict"] for r in results.values()] + [m["status"] for m in mirrors]
                            + ([proportion["status"]] if proportion else []))
    regen = [v for v, r in results.items() if r["verdict"] == "fail"]
    for m in mirrors:
        if m["status"] == "fail":
            va, vb = m["pair"].split("/")
            if va not in regen and vb not in regen:  # neither already queued: redo the weaker one
                regen.append(vb if results[vb]["score"] <= results[va]["score"] else va)

    # overlay sheet
    rows = []
    for v in VIEWS:
        if v in frames and frames[v]:
            rows.append((v, overlay(frames[v], palette), f"{results[v]['score']}/100 {results[v]['verdict'].upper()}"))
    if rows:
        make_sheet(rows, os.path.join(a.out, "overlay_sheet.png"))

    # write json
    report = {"overall_score": overall, "overall_verdict": overall_verdict, "regen": regen,
              "missing_views": missing, "views": results, "mirrors": mirrors,
              "proportion": proportion, "colours": colour_rows, "thresholds": TH}
    json.dump(report, open(os.path.join(a.out, "report.json"), "w"), indent=2, ensure_ascii=False)

    # write markdown
    L = []
    L.append("# View match report\n")
    L.append(f"**Overall score: {overall}/100 — {ICON[overall_verdict]} {(overall_verdict or 'n/a').upper()}**\n")
    L.append(f"- Views to generate again: {', '.join(VIEW_NAME[v] for v in regen) if regen else 'none'}")
    if missing:
        L.append(f"- Missing images: {', '.join(VIEW_NAME[v] for v in missing)}")
    L.append("- Comparison image: `overlay_sheet.png` (red = AI image lacks it compared with the blockout, blue = AI image has extra, yellow = where material borders must be)\n")

    L.append("## 1. Each view against the blockout\n")
    L.append("| View | Score | Shape (IoU) | H/W ratio error | Detail position | Colour dE max | Verdict |")
    L.append("|---|---|---|---|---|---|---|")
    for v in VIEWS:
        if v not in results:
            continue
        r = results[v]
        if "status" not in r:
            L.append(f"| {VIEW_NAME[v]} | 0 | — | — | — | — | ❌ {r['error']} |")
            continue
        s = r["status"]
        det = f"{r['detail']*100:.0f}% ({r['detail_worst']})" if r["detail"] is not None else "—"
        de = f"{r['max_delta_e']:.1f}" if r.get("max_delta_e") is not None else "—"
        L.append(f"| {VIEW_NAME[v]} | {r['score']} | {ICON[s['iou']]} {r['iou']:.3f} | {ICON[s['aspect_err']]} {r['aspect_err']*100:+.1f}% "
                 f"| {ICON[s['detail']]} {det} | {ICON[s.get('colour')]} {de} | {ICON[r['verdict']]} |")

    L.append("\n## 2. Do the views match each other\n")
    L.append("The orthographic silhouettes of two opposite views must be mirror images of each other. This part does not need the blockout.\n")
    L.append("| Pair | IoU after flip | H/W ratio difference | Verdict |")
    L.append("|---|---|---|---|")
    for m in mirrors:
        a_, b_ = m["pair"].split("/")
        L.append(f"| {VIEW_NAME[a_]} ↔ {VIEW_NAME[b_]} | {m['iou']:.3f} | {m['aspect_diff']*100:+.1f}% | {ICON[m['status']]} |")
    if proportion:
        L.append(f"\nCross-view proportion (Front H/W = Side H/D × Top D/W): error {proportion['err']*100:+.1f}% {ICON[proportion['status']]}")

    if colour_rows:
        L.append("\n## 3. Colour of each material across the views\n")
        L.append("dE (CIE76, lightness at half weight, because one material looks lighter or darker on a sloped or turned face): under 6 is almost invisible, 6–12 is visible side by side, over 12 is clearly different.\n")
        shown = [v for v in VIEWS if v in results]
        L.append("| Material | Reference | " + " | ".join(VIEW_NAME[v] for v in shown) + " |")
        L.append("|---|---|" + "---|" * len(shown))
        for mat, info in colour_rows.items():
            cells = []
            for v in shown:
                c = info["views"].get(v)
                cells.append(f"{ICON[c['status']]} {c['hex']} ({c['delta_e']:.1f})" if c else "—")
            L.append(f"| {mat} | {info['reference_hex']} ({info['reference']}) | " + " | ".join(cells) + " |")

    L.append("\n## 4. What to fix\n")
    any_fix = False
    for v in VIEWS:
        if v in results:
            fx = fixes_for(results[v], colour_rows)
            if fx:
                any_fix = True
                L.append(f"**{VIEW_NAME[v]}**")
                L += [f"- {f}" for f in fx]
                L.append("")
    for m in mirrors:
        if m["status"] in ("warn", "fail"):
            any_fix = True
            a_, b_ = m["pair"].split("/")
            L.append(f"- {VIEW_NAME[a_]} and {VIEW_NAME[b_]} do not match each other (IoU after flip {m['iou']:.2f}, ratio difference {m['aspect_diff']*100:+.1f}%): generate the lower-scoring view again and give the other view as a reference.")
    if not any_fix:
        L.append("No error is over a threshold.")

    L.append("\n## How it is calculated\n")
    L.append("- The AI image and the blockout are both cropped to the object's bounding box and resized to one size, so absolute size and position in the frame are not counted as errors.")
    L.append(f"- Shape: silhouette IoU. Pass at {TH['iou'][0]} or more, warn at {TH['iou'][1]} or more.")
    L.append(f"- Ratio: height/width of the AI image against the blockout. Pass at {TH['aspect_err'][0]*100:.0f}% or less, warn at {TH['aspect_err'][1]*100:.0f}% or less.")
    L.append(f"- Detail position: for each material, the % of its blockout border that has a matching edge in the AI image (tolerance ±4 px on a {N} px frame). Chance matches on a busy texture are subtracted. The table shows the worst material. Pass at {TH['detail'][0]*100:.0f}% or more.")
    L.append(f"- Colour: median colour of each material region, compared with the concept if `--concept-colors` is given, else with the front view. Pass at {TH['delta_e'][0]} or less, warn at {TH['delta_e'][1]} or less.")
    L.append("- View score = average of shape, ratio, detail and colour, scaled to 0–100. Overall score = 80% average of the views + 20% cross-view match (opposite pairs, cross proportion).")
    L.append("- Limit: small detail inside one material region (patterns, number of window panes) is not measured. Check these on the overlay or with vision_check.")
    open(os.path.join(a.out, "report.md"), "w").write("\n".join(L) + "\n")
    print(f"Overall {overall}/100 {overall_verdict}; regen: {regen or 'none'} -> {a.out}/report.md")


if __name__ == "__main__":
    main()
