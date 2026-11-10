"""Find the orthographic camera a 3/4 concept view was drawn from, on either side of the prop. Plain Python.

Usage: PY tools/fit_view.py --work <F> --spec <spec.json> [--side left|right] [--rollout k] [--views 34]
       [--write-spec] [--out <F>/camera_fit.json]

Kit fit_camera.py scans azimuth 0..90 only and ranks by bbox IoU, which barely separates mirrored or distant
cameras (two mirrored cameras can score almost the same IoU). This tool scans azimuth -90..90 and elevation 5..55,
ranks each camera first by whether the model's bottom silhouette breaks where the concept's does (the near bottom
corner, which splits side face width from front face width), then by IoU, and refines at 1°.
--side: image side where the concept shows the prop's side face (left = camera toward -X, azimuth < 0). Pass it
for a near-square footprint: a square box looks the same from -30° and +60°.
Output as fit_camera.py: camera_fit.json, and --write-spec stores spec.concept.cameras for render_views.py.
A view whose break matches no camera within 0.05 of the bbox width fails and is not written. Exit 1 on fail.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), os.path.join(HERE, "self_build")]
import common  # noqa: E402
import graph as G  # noqa: E402
import raster  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/fit_view"
TOL = 0.05
AZ = {"left": (-90, 0), "right": (0, 90), None: (-90, 90)}


def split(mask):
    """Column where the bottom outline breaks into two straight edges, as a fraction of the bbox width.
    Columns whose bottom lies above the lowest 30 % of the height (overhangs) are left out."""
    cols, rows = np.nonzero(mask.any(0))[0], np.nonzero(mask.any(1))[0]
    bottom = mask.shape[0] - 1 - np.argmax(mask[::-1][:, cols], axis=0)
    keep = bottom >= rows[-1] - 0.3 * (rows[-1] - rows[0])
    x, y = cols[keep].astype(float), bottom[keep].astype(float)
    sums = [np.concatenate([[0.0], np.cumsum(q)]) for q in (np.ones_like(x), x, y, x * x, x * y, y * y)]

    def sse(i, j):
        n, sx, sy, sxx, sxy, syy = (s[j] - s[i] for s in sums)
        cxy = sxy - sx * sy / n
        return syy - sy * sy / n - cxy * cxy / np.maximum(sxx - sx * sx / n, 1e-9)

    k = np.arange(2, len(x) - 2)
    corner = x[k[np.argmin(sse(0, k + 1) + sse(k, len(x)))]]
    return float((corner - cols[0]) / max(cols[-1] - cols[0], 1))


def side_ratio(s, az):
    return round(s / max(1 - s, 1e-6) if az < 0 else (1 - s) / max(s, 1e-6), 3)


def fit(v, t, cm, size, side):
    """Best (matched, iou, az, el, split) over the grid, then at 1° around it; and the concept's split."""
    sc, (lo, hi), memo = split(cm), AZ[side], {}

    def key(a, e):
        if (a, e) not in memo:
            m = raster.normalize_to_bbox(raster.silhouette(v, t, raster.camera_dir(a, e), size=size)[0], size)
            s = split(m)
            memo[a, e] = (abs(s - sc) <= TOL, raster.iou(cm, m), a, e, s)
        return memo[a, e]

    _, _, a0, e0, _ = max(key(a, e) for a in range(lo, hi + 1, 5) for e in range(5, 60, 5))
    return max(key(a, e) for a in range(max(lo, a0 - 4), min(hi, a0 + 4) + 1)
               for e in range(max(1, e0 - 4), e0 + 5)), sc


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--side", choices=("left", "right"))
    p.add_argument("--rollout")
    p.add_argument("--views", help="comma list; default every non-orthographic concept view")
    p.add_argument("--write-spec", action="store_true")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    out = a.out or os.path.join(a.work, "camera_fit.json")
    try:
        settings, spec = common.load_settings(a.spec)
        gdir = os.path.join(a.work, "rollouts", a.rollout) if a.rollout else a.work
        glb = os.path.join(gdir, "assembled.glb")
        if not os.path.isfile(glb):
            raise SystemExit(f"no assembled.glb in {gdir}; run assembly.py first")
        v, t, _ = G.load_glb(glb)
        size = settings["optimize"]["raster_size"]
        concept = spec.get("concept") or {}
        labels = a.views.split(",") if a.views else [k for k in (concept.get("views") or {}) if k not in G.ORTHO_VIEWS]
        cms = G.concept_masks(dict(spec, concept=dict(concept, cameras={})), a.spec, size)
        checks, fits, views = [], {}, {}
        for label in labels:
            if label not in cms:
                checks.append(common.check(f"camera.{label}", "not_checked", note="no concept mask for this view"))
                continue
            (ok, iou, az, el, sm), sc = fit(v, t, cms[label], size, a.side)
            cam = {"azimuth_deg": float(az), "elevation_deg": float(el)}
            views[label] = {"side": "left" if az < 0 else "right", "side_front_ratio": side_ratio(sm, az),
                            "concept_side_front_ratio": side_ratio(sc, az), "iou": round(iou, 4)}
            note = "side face {side}, side/front {side_front_ratio} vs concept {concept_side_front_ratio}, " \
                   "IoU {iou}".format(**views[label])
            if ok:
                fits[label] = cam
            else:
                note += f"; no camera breaks the bottom outline within {TOL} of the concept: compare the model's " \
                        "width and depth with the concept"
            checks.append(common.check(f"camera.{label}", "info" if ok else "fail", value=cam, note=note))
        if a.write_spec and fits:
            spec.setdefault("concept", {}).setdefault("cameras", {}).update(fits)
            common.write_json(a.spec, spec)
        r = common.write_result(out, TOOL, checks=checks, source=glb, spec_path=a.spec,
                                data={"cameras": fits, "written_to_spec": bool(a.write_spec and fits), "views": views})
    except Exception as exc:  # noqa: BLE001
        common.write_error(out, TOOL, exc)
        raise SystemExit(2)
    raise SystemExit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
