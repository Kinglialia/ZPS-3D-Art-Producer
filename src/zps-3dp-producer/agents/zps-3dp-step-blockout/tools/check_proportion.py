"""The built model has the width : height ratio of the concept in every orthographic view, within 10 %. Bbox only.

Usage: python3 tools/check_proportion.py --work <dir> [--spec <spec.json>] [--out <json>]
Per view in spec concept.views (front, back, left, right, top; --spec defaults to <dir>/../work/spec.json): the model box
comes from the union bbox in assembly.json, the concept box from the mask file the spec names. The concept has no scale,
so only the ratio of the two box sides is compared: fail when (model / concept - 1) is beyond +-0.10. Other views (the
3/4 view) are not checked. No spec, or no mask file for a view: that view is not_checked.
Writes <dir>/review/checks/proportion.json. Exit 0 pass/not_checked, 1 fail, 2 error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import cli  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_proportion"
TOL = 0.10
AXES = {"front": (0, 2), "back": (0, 2), "left": (1, 2), "right": (1, 2), "top": (0, 1)}


def model_ratio(rows, view):
    u, v = AXES[view]
    lo = [min(r["bbox_min"][a] for r in rows) for a in range(3)]
    hi = [max(r["bbox_max"][a] for r in rows) for a in range(3)]
    return (hi[u] - lo[u]) / (hi[v] - lo[v]) if hi[v] > lo[v] else None


def concept_ratio(path, background):
    import raster
    box = raster.bbox_of(raster.concept_mask(path, background))
    return None if box is None else float(box[1] - box[0] + 1) / float(box[3] - box[2] + 1)


def run(a, graph, rows, sources):
    spec_path = a.spec or os.path.join(a.work, "..", "work", "spec.json")
    if not os.path.isfile(spec_path):
        return [common.check("proportion.spec", "not_checked", note=f"no spec.json with concept masks at {spec_path}")], \
            {}, "not_checked"
    spec = common.read_json(spec_path)
    concept = spec.get("concept") or {}
    checks, ratios = [], {}
    for view, rel in (concept.get("views") or {}).items():
        name = f"proportion.{view}"
        path = common.spec_rel(spec_path, rel)
        if view not in AXES:
            checks.append(common.check(name, "not_checked", note="only orthographic views are compared"))
        elif not os.path.isfile(path):
            checks.append(common.check(name, "not_checked", note=f"no mask file {path}"))
        else:
            m, c = model_ratio(rows, view), concept_ratio(path, concept.get("background"))
            if not m or not c:
                checks.append(common.check(name, "not_checked", note="the model or the concept mask has no extent"))
                continue
            dev = round(m / c - 1, 3)
            ratios[view] = {"model": round(m, 3), "concept": round(c, 3), "deviation": dev}
            checks.append(common.check(name, "pass" if abs(dev) <= TOL else "fail", value=dev, threshold=TOL,
                                       note=f"width : height, model {m:.3f} vs concept {c:.3f}"))
    if not any(c["status"] != "not_checked" for c in checks):
        return checks or [common.check("proportion.spec", "not_checked", note="the spec lists no view")], \
            {"ratios": ratios}, "not_checked"
    return checks, {"ratios": ratios}, None


if __name__ == "__main__":
    require_root()
    cli(TOOL, "proportion", run, optional=("--spec",))
