"""The built model has the width : height ratio of the concept in every orthographic view, within 10 %. Bbox only.

Usage: python3 tools/check_proportion.py --work <dir> [--spec <spec.json>] [--card <asset-card.yaml>] [--out <json>]
Per view in spec concept.views (front, back, left, right, top): the model box comes from the union bbox in
assembly.json, the concept box from the mask file the spec names. --spec defaults to <vN>/work/spec.json of the version
folder, also for a graph in <vN>/variants/<b|c>/. The concept has no scale,
so only the ratio of the two box sides is compared: fail when (model / concept - 1) is beyond +-0.10. Other views (the
3/4 view) are not checked. No spec, or no mask file for a view: that view is not_checked.
--card: each `marks` entry {name, z_m} of the card (a height above the bottom of the object, in metres) must sit on the
top or the bottom z of some part in assembly.json, within 10 % of the object height or 5 cm, whichever is larger. A mark
that does not fails as proportion.mark.<name> and its note names the nearest part edge. Marks need no spec.
Writes <dir>/review/checks/proportion.json. Exit 0 pass/not_checked, 1 fail, 2 error.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import cli  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_proportion"
TOL = 0.10
MARK_MIN_M = 0.05
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


def default_spec(work):
    """<vN>/work/spec.json for a graph in <vN>/final/ or <vN>/variants/<b|c>/; beside the graph's folder if outside vN."""
    d = os.path.abspath(work)
    while os.path.dirname(d) != d:
        if re.fullmatch(r"v\d+", os.path.basename(d)):
            return os.path.join(d, "work", "spec.json")
        d = os.path.dirname(d)
    return os.path.join(os.path.abspath(work), "..", "work", "spec.json")


def mark_checks(card_path, rows):
    import yaml
    with open(card_path, encoding="utf-8") as f:
        marks = (yaml.safe_load(f) or {}).get("marks") or []
    low = min(r["bbox_min"][2] for r in rows)
    height = max(r["bbox_max"][2] for r in rows) - low
    tol = max(TOL * height, MARK_MIN_M)
    edges = [(r[key][2] - low, f"{r['name']}.{end}") for r in rows for key, end in (("bbox_min", "bottom"), ("bbox_max", "top"))]
    checks = []
    for m in marks:
        z, (at, part) = float(m["z_m"]), min(edges, key=lambda e: abs(e[0] - m["z_m"]))
        off = round(abs(at - z), 3)
        checks.append(common.check(f"proportion.mark.{m['name']}", "pass" if off <= round(tol, 3) else "fail", value=off,
                                   threshold=round(tol, 3),
                                   note=f"mốc {m['name']} z {z:.2f} m; cạnh part gần nhất {part} {at:.2f} m"))
    return checks


def run(a, graph, rows, sources):
    checks, data, overall = compare_views(a, graph, rows, sources)
    marks = mark_checks(a.card, rows) if a.card else []
    return checks + marks, data, None if marks else overall


def compare_views(a, graph, rows, sources):
    spec_path = a.spec or default_spec(a.work)
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
    cli(TOOL, "proportion", run, optional=("--spec", "--card"))
