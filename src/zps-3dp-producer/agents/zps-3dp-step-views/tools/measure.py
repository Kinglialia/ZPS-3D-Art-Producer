"""Measure generated views against the guides: the kit's measure_views.py, unchanged, with G1 and D36 fixed here.

Usage: python3 tools/measure.py --final <V/final> --guides <views_front final>/guides --views front[,back,left,right,top]
           [--front <views_front final>/front.png] [--concept-colors <views_front final>/concept_colors.json]
G1 (docs/review-kit-v0.10.4-vs-process.md): the kit keeps only background that touches the image border, so a
closed gap between columns counts as object. Here every pixel near the background colour is background.
Images: <final>/<view>.png; --front when front.png lives in views_front (views_rest).
Without --concept-colors, the kit compares each material with the front view (the colour standard).
--views: names are stripped; an unknown name stops the run with exit 2 and measures nothing (V5).
V2: a boundary between two materials whose colours in the image are under dE 10 apart is not checked for `detail`:
no edge can be seen there. It is listed in the check `detail.<view>` (not_checked).
--front given (views_rest, V4): the approved front is never in `regen` and its check is at most `info`; if the front/back
mirror pair fails, back is queued instead. V6: with --concept-colors too, the reference colour of a material is the measured
front, and the concept colour only for a material the front does not show.
V15: per view, the checks border (the object touches the image border: fail), components (the count of separate shapes
differs from the guide: fail), ring (share of the object rim near the background colour: info), light (luminance change
across each material region, a share of its mean: info).
Writes <final>/report/{report.json, report.md, overlay_sheet.png, overlay_<view>.png} and
<final>/review/checks/measure.json (fail: a view in `regen`, or a missing image). Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import common  # noqa: E402
import measure_views as mv  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "views/measure"
BLIND_DE = 10.0
MIN_COMPONENT_PX = round(0.002 * mv.N * mv.N)
RING_FACTOR = 1.5
LIGHT_NOTE_AT = 0.25
mv.flood_background = lambda bgish: bgish
_measure_view, _internal_boundaries = mv.measure_view, mv.internal_boundaries


def pair_edges(label, pairs):
    out = np.zeros(label.shape, bool)
    for dy, dx in ((0, 1), (1, 0)):
        nb = np.roll(label, (-dy, -dx), (0, 1))
        for i, j in pairs:
            out |= ((label == i) & (nb == j)) | ((label == j) & (nb == i))
    out[-1, :] = out[:, -1] = False
    return out


def blind_pairs(blk, gen, mat_names):
    """V2: material pairs that touch in the guide and cannot be told apart in the image: 9 pixels in 10 of their two
    regions together are under dE 10 from the median of both. Judging by the colour of each region alone would call
    a misplaced border 'blind', because a shifted region holds both colours."""
    if gen["bb"] is None:
        return []
    bl = mv._label_frame(blk["label"], blk["bb"])
    gm = mv.to_frame(gen["mask"].astype(np.uint8) * 255, gen["bb"], Image.NEAREST) > 127
    gr = mv.to_frame(gen["rgb"], gen["bb"], Image.BILINEAR)
    core = [mv.erode(bl == k, 3) & mv.erode(gm, 2) for k in range(len(mat_names))]
    pairs = []
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            px = gr[core[i] | core[j]]
            if core[i].sum() >= 40 and core[j].sum() >= 40 and pair_edges(bl, [(i, j)]).any():
                px, med = px[::max(1, len(px) // 1500)], np.median(px, 0)
                if np.percentile([mv.delta_e(p, med) for p in px], 90) < BLIND_DE:
                    pairs.append((i, j))
    return pairs


def measure_view(view, blk, gen, mat_names):
    pairs = blind_pairs(blk, gen, mat_names)
    mv.internal_boundaries = lambda label: _internal_boundaries(label) & ~pair_edges(label, pairs)
    try:
        r, fr = _measure_view(view, blk, gen, mat_names)
    finally:
        mv.internal_boundaries = _internal_boundaries
    r["detail_not_checked"] = {mat_names[a]: [mat_names[b] for x, b in ((i, j), (j, i)) if x == a]
                               for a in sorted({k for p in pairs for k in p}) for i, j in pairs if a in (i, j)}
    return r, fr


mv.measure_view = measure_view


def gen_dir(d, final, views, front):
    for v in views:
        src = front if v == "front" and front else os.path.join(final, f"{v}.png")
        if os.path.isfile(src):
            os.symlink(os.path.abspath(src), os.path.join(d, f"{v}.png"))


def components(mask):
    h, w = mask.shape
    seen, sizes = np.zeros_like(mask), []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, n = [(y, x)], 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            n += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        sizes.append(n)
    return sum(n >= MIN_COMPONENT_PX for n in sizes)


def light_change(fr, k):
    """Luminance change across a material region along its steepest direction, as a share of its mean luminance."""
    region = mv.erode(fr["bl"] == k, 3) & mv.erode(fr["gm"], 2)
    if region.sum() < 40:
        return None
    ys, xs = np.nonzero(region)
    lum = fr["gr"][ys, xs].astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    step = max(1, len(lum) // 4000)
    (a, b, _), *_ = np.linalg.lstsq(np.c_[xs, ys, np.ones(len(xs))][::step].astype(float), lum[::step], rcond=None)
    along = (xs * a + ys * b) / (np.hypot(a, b) or 1)
    return float(np.hypot(a, b) * (along.max() - along.min()) / max(lum.mean(), 1))


def metric_checks(v, gen, fr, mat_names, threshold, may_fail):
    """V15: the cheap measures of one view. Only border and components may fail."""
    bad = "fail" if may_fail else "info"
    mask = gen["mask"]
    touch = int(mask[0].sum() + mask[-1].sum() + mask[1:-1, 0].sum() + mask[1:-1, -1].sum())
    n_guide, n_image = components(fr["bm"]), components(fr["gm"])
    out = [common.check(f"border.{v}", bad if touch else "pass", value=touch,
                        note="vật chạm mép ảnh: bị cắt" if touch else None),
           common.check(f"components.{v}", "pass" if n_guide == n_image else bad, value={"guide": n_guide, "image": n_image},
                        note=None if n_guide == n_image else "số khối rời khác guide: thiếu hoặc thừa prop")]
    if gen["bg"] == "alpha":
        out.append(common.check(f"ring.{v}", "not_checked", note="ảnh có alpha, không có màu nền"))
    else:
        bg = mv.hex_rgb(gen["bg"]).astype(float)
        rim = mask & ~mv.erode(mask, 3)
        near = np.linalg.norm(gen["rgb"].astype(float) - bg, axis=-1) < RING_FACTOR * threshold
        out.append(common.check(f"ring.{v}", "info", value={"halo_share": round(float((rim & near).sum() / max(rim.sum(), 1)), 3)}))
    light = {m: round(c, 3) for k, m in enumerate(mat_names) if (c := light_change(fr, k)) is not None}
    out.append(common.check(f"light.{v}", "info", value=light,
                            note="ánh sáng đổi mạnh trong một vật liệu" if any(c > LIGHT_NOTE_AT for c in light.values()) else None))
    return out


def overlays(guides, gen, report_dir, views, threshold, front_given):
    meta = common.read_json(os.path.join(guides, "views.json"))
    names = list(meta["materials"])
    palette = np.array([mv.hex_rgb(meta["materials"][m]) for m in names])
    extra = []
    for v in views:
        p = mv.find_gen(gen, v)
        if p:
            image = mv.load_gen(p, threshold)
            _, fr = mv.measure_view(v, mv.load_blockout(guides, v, palette), image, names)
            if fr:
                Image.fromarray(mv.overlay(fr, palette)[2]).save(os.path.join(report_dir, f"overlay_{v}.png"))
                extra += metric_checks(v, image, fr, names, threshold, not (front_given and v == "front"))
    return extra


def rest_concept(guides, front, concept_colors, threshold, tmp):
    """V6: the concept colours of the materials the front does not show; the kit takes the others from the front."""
    meta = common.read_json(os.path.join(guides, "views.json"))
    names = list(meta["materials"])
    palette = np.array([mv.hex_rgb(meta["materials"][m]) for m in names])
    r, _ = mv.measure_view("front", mv.load_blockout(guides, "front", palette), mv.load_gen(front, threshold), names)
    kept = {m: c for m, c in common.read_json(concept_colors).items() if m not in r.get("colours", {})}
    path = os.path.join(tmp, "concept_colors.json")
    common.write_json(path, kept)
    return path


def drop_front(report_dir):
    """V4: views_rest cannot make the front again. A failing front/back pair means back is the view to make."""
    path = os.path.join(report_dir, "report.json")
    rep = common.read_json(path)
    regen = [v for v in rep["regen"] if v != "front"]
    for m in rep["mirrors"]:
        a, b = m["pair"].split("/")
        if "front" in (a, b) and m["status"] == "fail" and a not in regen and b not in regen:
            regen.append(b if a == "front" else a)
    rep["regen"] = regen
    common.write_json(path, rep)
    md = os.path.join(report_dir, "report.md")
    with open(md, encoding="utf-8") as f:
        text = f.read()
    with open(md, "w", encoding="utf-8") as f:
        f.write(re.sub(r"^- Views to generate again: .*$", "- Views to generate again: "
                       + (", ".join(mv.VIEW_NAME[v] for v in regen) or "none"), text, count=1, flags=re.M))
    return rep


def checks_of(rep, views, front_given, extra):
    out = []
    for v in views:
        r = rep["views"].get(v)
        if r is None:
            out.append(common.check(f"views.{v}", "fail", note="thiếu ảnh"))
            continue
        val = {k: r.get(k) for k in ("score", "verdict", "iou", "aspect_err", "detail", "detail_worst", "max_delta_e")}
        status = "fail" if v in rep["regen"] else "info" if front_given and v == "front" and r.get("verdict") == "fail" else "pass"
        out.append(common.check(f"views.{v}", status, value=val, note=r.get("error")))
        if r.get("detail_not_checked"):
            out.append(common.check(f"detail.{v}", "not_checked", value=r["detail_not_checked"],
                                    note="hai màu cách nhau dưới dE 10 trong ảnh: không đo ranh này"))
    return out + extra


def view_list(arg):
    names = [v.strip() for v in arg.split(",") if v.strip()]
    unknown = [v for v in names if v not in mv.VIEWS]
    if unknown or not names:
        raise ValueError(f"--views {arg!r}: tên view lạ {unknown or ['(rỗng)']}; dùng: {', '.join(mv.VIEWS)}")
    return [v for v in mv.VIEWS if v in names]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--guides", required=True)
    p.add_argument("--views", required=True)
    p.add_argument("--front")
    p.add_argument("--concept-colors")
    p.add_argument("--bg-threshold", type=float, default=40)
    a = p.parse_args()
    try:
        views = view_list(a.views)
    except ValueError as e:
        print(f"[{TOOL}] error: {e}")
        sys.exit(2)
    report_dir = os.path.join(a.final, "report")
    out = os.path.join(a.final, "review", "checks", "measure.json")
    try:
        os.makedirs(report_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as d:
            gen_dir(d, a.final, views, a.front)
            concept = a.concept_colors
            if a.front and concept and "front" in views:
                concept = rest_concept(a.guides, a.front, concept, a.bg_threshold, d)
            sys.argv = ["measure_views.py", "--blockout", a.guides, "--gen", d, "--out", report_dir,
                        "--views", ",".join(views), "--bg-threshold", str(a.bg_threshold),
                        *(["--concept-colors", concept] if concept else [])]
            with contextlib.redirect_stdout(io.StringIO()):
                mv.main()
            extra = overlays(a.guides, d, report_dir, views, a.bg_threshold, bool(a.front))
        rep = drop_front(report_dir) if a.front else common.read_json(os.path.join(report_dir, "report.json"))
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(2)
    r = common.write_result(out, TOOL, checks_of(rep, views, bool(a.front), extra),
                            data={"regen": rep["regen"], "overall_score": rep["overall_score"],
                                  "report": os.path.join(report_dir, "report.json")})
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
