"""After one top_fix finding: fixed_params unchanged and the layout bbox still within ±2%. Plain Python.

Usage: python3 tools/check_fix.py --work <dir> --old <base version>/final/part_graph.json --finding F<n> [--out <json>]
Run after the edit and assembly.py, once per finding (a param batch runs it after each finding).
fixed_params: the same names, and each value equal to the old graph's. A name dropped from the
list counts as changed.
Writes <dir>/review/checks/fix_<finding>.json. Exit 0 pass, 1 fail, 2 error. On fail the worker
restores the part_graph.json/parts_lib.py it had before this finding.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import bbox_check, cli  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_fix"


def run(a, graph, rows, sources):
    old = common.read_json(a.old)
    op, np_ = old.get("params", {}), graph.get("params", {})
    new_fixed = set(graph.get("fixed_params") or [])
    changed = sorted(n for n in old.get("fixed_params") or [] if n not in new_fixed or np_.get(n) != op.get(n))
    fixed = common.check("fix.fixed_params", "fail" if changed else "pass", value=changed,
                         note="fixed_params changed" if changed else None)
    bbox, layout = bbox_check(graph, rows, sources)
    diff = {k: [op.get(k), np_.get(k)] for k in sorted(set(op) | set(np_)) if op.get(k) != np_.get(k)}
    return [fixed, bbox], {"finding": a.finding, "old": os.path.abspath(a.old), "changed_params": diff,
                           "layout": layout}, None


if __name__ == "__main__":
    require_root()
    cli(TOOL, lambda a: f"fix_{a.finding}.json", run, extra=("--old", "--finding"))
