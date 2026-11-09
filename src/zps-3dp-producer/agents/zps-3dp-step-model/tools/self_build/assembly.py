"""Build a prop from its part graph: primitives, attach solving, manifold3d union, IoU vs concept.

Usage:
  blender -b --python tools/self_build/assembly.py -- --work <w> [--rollout k] [--upto n|name]
          [--coarse] [--spec task/spec.json] [--out <json>]
  python3 tools/self_build/assembly.py --work <w> ...        (bpy pip module, or no custom parts)

Reads <w>/part_graph.json + <w>/parts_lib.py (or <w>/rollouts/<k>/ with --rollout k).
  --upto n|name  build only the first n parts (1-based, build order) or up to that part name
  --coarse       custom parts become boxes of the same bbox
Writes, in the graph folder:
  parts/<name>.glb   each solved part in world position (glTF Y-up)
  assembled.glb      manifold3d union of the built parts (plain join + warning when a part is
                     not a closed manifold)
  assembly.json      result JSON (lib/common.write_result): data has params, per-part solved
                     centre/bbox/declared extents/tris/contact, union stats, code_hash, and
                     per-view IoU vs spec.concept.views (orthographic views only, bbox-normalised,
                     raster size = optimize.raster_size).
Exit 0 on pass/fail, 1 on error (assembly.json then has overall=error and the traceback).
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402

TOOL = "self_build/assembly"


def parse_upto(s, graph):
    if s is None:
        return None
    if s.isdigit():
        n = int(s)
        if n < 1:
            raise G.GraphError("--upto must be >= 1")
        return n
    names = [p.get("name") for p in graph.get("parts", [])]
    if s not in names:
        raise G.GraphError(f"--upto: no part named '{s}'")
    return names.index(s) + 1


def build(gdir, spec, spec_path, settings, upto=None, coarse=False):
    """Solve, export and measure. Returns (checks, metrics, warnings, artifacts, data)."""
    warnings = []
    graph = G.load_graph(gdir)
    lib = G.load_parts_lib(gdir)
    n = parse_upto(upto, graph)
    parts = G.solve(graph, lib, upto=n, coarse=coarse, warnings=warnings)

    pdir = os.path.join(gdir, "parts")
    os.makedirs(pdir, exist_ok=True)
    for old in glob.glob(os.path.join(pdir, "*.glb")):
        os.remove(old)
    artifacts, rows = {}, []
    for p in parts:
        path = os.path.join(pdir, f"{p['name']}.glb")
        G.save_glb(path, p["verts"], p["tris"])
        artifacts[f"part:{p['name']}"] = path
        ext = p["hi"] - p["lo"]
        rows.append({"index": p["index"], "name": p["name"], "primitive": p["primitive"],
                     "parent": p["parent"], "attach": p["attach"], "contact": p["contact"],
                     "depth": p["depth"],
                     "center": ((p["lo"] + p["hi"]) / 2).round(5).tolist(),
                     "bbox_min": p["lo"].round(5).tolist(), "bbox_max": p["hi"].round(5).tolist(),
                     "extents": ext.round(5).tolist(),
                     "declared": None if p["declared"] is None else np.round(p["declared"], 5).tolist(),
                     "tris": int(len(p["tris"])),
                     "manifold": G.is_manifold(p["verts"], p["tris"]),
                     "glb": os.path.abspath(path)})

    v, t, method, bad = G.union([(p["verts"], p["tris"]) for p in parts])
    if bad:
        warnings.append("not a closed manifold, union replaced by a plain join: "
                        + ", ".join(parts[i]["name"] for i in bad))
    out_glb = os.path.join(gdir, "assembled.glb")
    G.save_glb(out_glb, v, t)
    artifacts["assembled"] = out_glb
    lo, hi = v.min(0), v.max(0)
    h = G.health(v, t)
    union_stats = {"method": method, "tris": int(len(t)), "verts": int(len(v)),
                   "volume": round(G.volume(v, t), 6) if method == "manifold3d" else None,
                   "bbox_min": lo.round(5).tolist(), "bbox_max": hi.round(5).tolist(),
                   "extents": (hi - lo).round(5).tolist(), "health": h,
                   "components": len(G.components(v, t)[2])}

    checks = [common.check("build.runs", "pass", value=len(parts)),
              common.check("union.closed_manifold", "pass" if method == "manifold3d" else "fail",
                           value=method, note=None if not bad else "plain join fallback")]
    metrics = {"parts": len(parts), "tris": int(len(t))}

    size = settings["optimize"]["raster_size"]
    iou = None
    cm = G.concept_masks(spec, spec_path, size) if spec_path else {}
    if cm:
        per, _ = G.view_ious(v, t, cm, size)
        iou = G.iou_summary(per)
        partial = coarse or (n is not None and n < len(graph["parts"]))
        min_iou = (spec.get("concept") or {}).get("min_iou")
        for view, x in iou["per_view"].items():
            status = "info" if (partial or min_iou is None) else ("pass" if x >= min_iou else "fail")
            checks.append(common.check(f"iou.{view}", status, value=x, threshold=min_iou))
        metrics.update({"iou_mean": iou["mean"], "iou_worst": iou["worst"],
                        "iou_worst_view": iou["worst_view"]})
    elif spec_path:
        warnings.append("spec has no orthographic concept.views; IoU not measured")

    data = {"graph_dir": os.path.abspath(gdir), "code_hash": G.code_hash(gdir),
            "params": graph.get("params", {}), "coarse": coarse,
            "upto": n, "parts_total": len(graph["parts"]), "parts": rows,
            "union": union_stats, "iou": iou, "iou_raster_size": size if cm else None}
    return checks, metrics, warnings, artifacts, data


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--rollout")
    p.add_argument("--upto")
    p.add_argument("--coarse", action="store_true")
    p.add_argument("--spec")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    gdir = G.graph_dir(a.work, a.rollout)
    out = a.out or os.path.join(gdir, "assembly.json")
    try:
        settings, spec = common.load_settings(a.spec)
        checks, metrics, warnings, artifacts, data = build(gdir, spec, a.spec, settings, a.upto, a.coarse)
    except Exception as e:  # noqa: BLE001 - every failure must land in the result JSON
        common.write_error(out, TOOL, e, source=os.path.join(gdir, "part_graph.json"))
        sys.exit(1)
    for w in warnings:
        print("WARNING:", w)
    common.write_result(out, TOOL, checks, metrics, warnings, artifacts, data,
                        source=os.path.join(gdir, "part_graph.json"), spec_path=a.spec)


if __name__ == "__main__":
    main()
