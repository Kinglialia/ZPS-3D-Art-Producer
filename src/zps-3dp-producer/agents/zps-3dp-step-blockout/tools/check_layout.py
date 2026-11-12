"""Total bbox vs sources.json layout (MAP-LAYOUT or size_m), within ±2%. Plain Python.

Usage: python3 tools/check_layout.py --work <dir> [--out <json>]
Reads <dir>/part_graph.json, sources.json, assembly.json (per-part bbox rows; no rebuild).
layout.includes_base false: parts tagged base are left out of the bbox.
Fails when assembly.json came from `assembly.py --upto n` and holds fewer parts than the graph.
Writes <dir>/review/checks/layout.json. Exit 0 pass, 1 fail, 2 error.
Also holds the loader and CLI that check_base, check_support, check_markers, check_fix share.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_layout"
TOL = 0.02


def load_build(work):
    """(graph, assembly rows, sources, assembly.fresh check). Fresh = assembly.json built from this part_graph.json."""
    graph = common.read_json(os.path.join(work, "part_graph.json"))
    asm = common.read_json(os.path.join(work, "assembly.json"))
    sources = common.read_json(os.path.join(work, "sources.json"))
    ok = asm.get("overall") != "error" and asm.get("source_sha256") == common.file_sha256(
        os.path.join(work, "part_graph.json"))
    fresh = common.check("assembly.fresh", "pass" if ok else "fail",
                         note=None if ok else "assembly.json is not built from this part_graph.json; run assembly.py")
    return graph, asm["data"]["parts"], sources, fresh


def tags(graph, key="tag"):
    return {p["name"]: p.get(key) for p in graph.get("parts", [])}


def cli(tool, name, fn, extra=()):
    """Shared CLI: fn(args, graph, rows, sources) -> (checks, data, overall or None)."""
    p = argparse.ArgumentParser(description=sys.modules["__main__"].__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--out")
    for flag in extra:
        p.add_argument(flag, required=True)
    a = p.parse_args()
    out = a.out or os.path.join(a.work, "review", "checks", name(a) if callable(name) else f"{name}.json")
    src = os.path.join(a.work, "assembly.json")
    try:
        graph, rows, sources, fresh = load_build(a.work)
        checks, data, overall = fn(a, graph, rows, sources)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, tool, e, source=src)
        sys.exit(2)
    r = common.write_result(out, tool, [fresh] + checks, data=data,
                            overall=overall if fresh["status"] == "pass" else None, source=src)
    sys.exit(1 if r["overall"] == "fail" else 0)


def bbox_check(graph, rows, sources):
    lay = sources["layout"]
    tag = tags(graph)
    sel = [r for r in rows if lay.get("includes_base", True) or tag.get(r["name"]) != "base"] or rows
    built = [round(max(r["bbox_max"][a] for r in sel) - min(r["bbox_min"][a] for r in sel), 5) for a in range(3)]
    want = [float(lay[k]) for k in ("w", "d", "h")]
    dev = [round(abs(b - w) / w, 4) for b, w in zip(built, want)]
    c = common.check("layout.bbox", "pass" if max(dev) <= TOL else "fail", value=max(dev), threshold=TOL,
                     note=f"built {built} vs layout {want} (w, d, h)")
    return c, {"built": built, "want": want, "deviation": dev, "includes_base": lay.get("includes_base", True),
               "parts": len(sel), "partial": len(rows) < len(graph.get("parts", []))}


def completeness(work):
    data = common.read_json(os.path.join(work, "assembly.json"))["data"]
    upto, total = data.get("upto"), data.get("parts_total")
    done = upto is None or total is None or upto >= total
    return common.check("layout.complete", "pass" if done else "fail", value={"upto": upto, "parts_total": total},
                        note=None if done else f"assembly.json holds {upto} of {total} parts: build without --upto")


def run(a, graph, rows, sources):
    c, data = bbox_check(graph, rows, sources)
    return [c, completeness(a.work)], data, None


if __name__ == "__main__":
    require_root()
    cli(TOOL, "layout", run)
