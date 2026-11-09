"""Fit part-graph params to the concept silhouettes (references/self_build.md, step 5).

Usage:
  python3 tools/self_build/param_fit.py --work <w> --spec task/spec.json [--part <name>]
          [--rollout k] [--out <json>]
  blender -b --python tools/self_build/param_fit.py -- --work <w> --spec task/spec.json ...

Nelder-Mead (scipy) over every float param in part_graph.json (or only those --part references:
dims, args, inset, depth, offset_uv). Integer params are segment counts and are never fitted.
Each param moves by a factor in [1 - max_param_change, 1 + max_param_change], never below 0.
Objective = mean IoU over the spec's orthographic concept views
            - worst_penalty x (mean - worst)          (bbox-normalised silhouettes, numpy raster)
A small pull toward the starting values (regularization x sum((p/p0 - 1)^2)) keeps params the
silhouettes cannot see (thin straps, insets) where they were.
Settings: self_build.param_fit.{enabled, time_limit_s, max_evals, max_param_change, min_gain,
  raster_size}; optional worst_penalty (default 0.5), regularization (default 0.001).
The search runs at param_fit.raster_size; the keep/reject decision re-scores before and after at
optimize.raster_size (the raster assembly.json reports) and writes the new params to
part_graph.json only when that objective improves by >= min_gain. Both are reported
(metrics *_before/_after = decision raster, search_* = search raster).
Writes fit.json (result JSON; data: before, after, params_before, params_after, evals, seconds,
kept). Exit 0 on pass/fail/skipped, 1 on error.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402

TOOL = "self_build/param_fit"


class _Stop(Exception):
    pass


def score(graph, lib, params, cmasks, size, penalty):
    parts = G.solve(graph, lib, params=params, warnings=[])
    v, t = G.concat(parts)
    per, _ = G.view_ious(v, t, cmasks, size)
    s = G.iou_summary(per)
    s["objective"] = round(s["mean"] - penalty * (s["mean"] - s["worst"]), 5)
    return s


def fit(gdir, spec, spec_path, settings, part=None):
    cfg = settings["self_build"]["param_fit"]
    penalty = cfg.get("worst_penalty", 0.5)
    reg = cfg.get("regularization", 0.001)
    size = cfg["raster_size"]
    warnings = []
    graph = G.load_graph(gdir)
    lib = G.load_parts_lib(gdir)
    params0 = dict(graph["params"])
    names = G.fit_params(graph)
    if part:
        refs = set(G.part_params(graph, part))
        names = [n for n in names if n in refs]
    fixed = set(graph.get("fixed_params") or [])
    if fixed & set(names):
        warnings.append(f"fixed by the brief, not fitted: {sorted(fixed & set(names))}")
        names = [n for n in names if n not in fixed]
    zero = [n for n in names if params0[n] <= 0]
    if zero:
        warnings.append(f"params at 0 cannot be scaled and are not fitted: {zero}")
        names = [n for n in names if n not in zero]
    skipped = sorted(set(graph["params"]) - set(names))
    if not cfg.get("enabled", True):
        return "skipped", [], {}, ["param_fit.enabled is false"], {"params": names}
    cmasks = G.concept_masks(spec, spec_path, size)
    if not cmasks:
        return "skipped", [], {}, ["spec has no orthographic concept.views"], {}
    if not names:
        return "skipped", [], {}, warnings + ["no float params to fit"], {"skipped_params": skipped}

    c = cfg["max_param_change"]
    p0 = np.array([params0[n] for n in names], float)
    lo, hi = max(0.0, 1 - c), 1 + c

    def params_at(x):
        p = dict(params0)
        for n, xi, base in zip(names, x, p0):
            p[n] = float(base * np.clip(xi, lo, hi))
        return p

    start = time.time()
    state = {"evals": 0, "best_x": np.ones(len(names)), "best_f": np.inf}

    def f(x):
        if state["evals"] >= cfg["max_evals"] or time.time() - start > cfg["time_limit_s"]:
            raise _Stop()
        state["evals"] += 1
        try:
            s = score(graph, lib, params_at(x), cmasks, size, penalty)["objective"]
        except G.GraphError:
            return 1.0
        val = -(s - reg * float(((np.clip(x, lo, hi) - 1) ** 2).sum()))
        if val < state["best_f"]:
            state["best_f"], state["best_x"] = val, np.array(x, float)
        return val

    before = score(graph, lib, params0, cmasks, size, penalty)
    from scipy.optimize import minimize
    k = len(names)
    step = c / 2
    simplex = np.vstack([np.ones(k)] + [np.ones(k) + step * np.eye(k)[i] for i in range(k)])
    stop_reason = "converged"
    try:
        res = minimize(f, np.ones(k), method="Nelder-Mead", bounds=[(lo, hi)] * k,
                       options={"initial_simplex": simplex, "maxfev": cfg["max_evals"],
                                "xatol": 1e-3, "fatol": 1e-5})
        if not res.success:
            stop_reason = res.message
    except _Stop:
        stop_reason = "eval or time limit"
    seconds = time.time() - start

    params_new = {n: round(v, 5) for n, v in params_at(state["best_x"]).items()}
    params_new = {n: (params_new[n] if n in names else params0[n]) for n in params0}
    after = score(graph, lib, params_new, cmasks, size, penalty)
    gain_search = after["objective"] - before["objective"]
    # decide at the raster assembly.json reports (optimize.raster_size): a fit that only wins at
    # the coarse search raster is overfitting the pixel grid
    dsize = settings["optimize"]["raster_size"]
    if dsize != size:
        cm_d = G.concept_masks(spec, spec_path, dsize)
        before_d = score(graph, lib, params0, cm_d, dsize, penalty)
        after_d = score(graph, lib, params_new, cm_d, dsize, penalty)
    else:
        before_d, after_d = before, after
    gain = after_d["objective"] - before_d["objective"]
    kept = gain >= cfg["min_gain"]
    if gain_search >= cfg["min_gain"] and not kept:
        warnings.append(f"fit gained {gain_search:+.4f} at the {size} px search raster but {gain:+.4f} at "
                        f"{dsize} px (assembly raster): not kept")
    if kept:
        graph["params"] = params_new
        G.save_graph(gdir, graph)
    changes = {n: {"before": params0[n], "after": params_new[n],
                   "change": round(params_new[n] / params0[n] - 1, 4)}
               for n in names if params_new[n] != params0[n]}
    at_bound = [n for n, ch in changes.items() if abs(abs(ch["change"]) - c) < 1e-3]
    if at_bound:
        warnings.append(f"params at the ±{c} limit (the shape may be wrong, not just the size): {at_bound}")
    checks = [common.check("fit.gain", "pass" if kept else "info", value=round(gain, 5),
                           threshold=cfg["min_gain"],
                           note=(f"objective gain at {dsize} px (assembly raster); search raster {size} px gain "
                                 f"{gain_search:+.5f}; ")
                                + ("params written to part_graph.json" if kept else "kept the old params"))]
    metrics = {"objective_before": before_d["objective"], "objective_after": after_d["objective"],
               "iou_mean_before": before_d["mean"], "iou_mean_after": after_d["mean"],
               "iou_worst_before": before_d["worst"], "iou_worst_after": after_d["worst"],
               "decision_raster_size": dsize,
               "search_objective_before": before["objective"], "search_objective_after": after["objective"],
               "search_iou_mean_before": before["mean"], "search_iou_mean_after": after["mean"],
               "search_raster_size": size,
               "evals": state["evals"], "seconds": round(seconds, 1), "kept": kept}
    data = {"before": before_d, "after": after_d, "search_before": before, "search_after": after,
            "gain_search": round(gain_search, 5), "decision_raster_size": dsize,
            "params_before": params0, "params_after": params_new,
            "fitted_params": names, "not_fitted": skipped, "changes": changes, "part": part,
            "evals": state["evals"], "seconds": round(seconds, 2), "kept": kept, "gain": round(gain, 5),
            "stop_reason": str(stop_reason), "raster_size": size, "worst_penalty": penalty,
            "regularization": reg, "code_hash_after": G.code_hash(gdir)}
    return None, checks, metrics, warnings, data


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--part")
    p.add_argument("--rollout")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    gdir = G.graph_dir(a.work, a.rollout)
    out = a.out or os.path.join(gdir, "fit.json")
    try:
        settings, spec = common.load_settings(a.spec)
        overall, checks, metrics, warnings, data = fit(gdir, spec, a.spec, settings, a.part)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=os.path.join(gdir, "part_graph.json"))
        sys.exit(1)
    common.write_result(out, TOOL, checks, metrics, warnings, data=data, overall=overall,
                        source=os.path.join(gdir, "part_graph.json"), spec_path=a.spec)


if __name__ == "__main__":
    main()
