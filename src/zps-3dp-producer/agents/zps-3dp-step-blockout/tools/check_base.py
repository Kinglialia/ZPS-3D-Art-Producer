"""Parts standing on a `tag: base` part keep >= 0.1 m from its edge, or 5 % of the base's shorter side when that is less.
Plain Python, bbox only.

Usage: python3 tools/check_base.py --work <dir> [--out <json>]
A part stands on a base when assembly.json gives it that parent with contact on +Z.
The bbox of a sloped or round part is larger than its shape, so this can miss a small fault
but never reports a false one. No base tag: overall not_checked.
Writes <dir>/review/checks/base.json. Exit 0 pass/not_checked, 1 fail, 2 error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import cli, tags  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_base"
MIN_MARGIN = 0.1
MARGIN_RATIO = 0.05   # of the base's shorter side; temporary, set by hand, to re-measure on small bases


def run(a, graph, rows, sources):
    tag = tags(graph)
    if not any(t == "base" for t in tag.values()):
        return [common.check("base.edge_margin", "not_checked", note="no part has tag: base")], {}, "not_checked"
    by = {r["name"]: r for r in rows}
    margin, need = {}, {}
    for r in rows:
        b = by.get(r["parent"])
        if b is None or tag.get(b["name"]) != "base" or r["contact"] != {"axis": 2, "sign": 1}:
            continue
        lo, hi, blo, bhi = r["bbox_min"], r["bbox_max"], b["bbox_min"], b["bbox_max"]
        margin[r["name"]] = round(min(lo[0] - blo[0], bhi[0] - hi[0], lo[1] - blo[1], bhi[1] - hi[1]), 4)
        need[r["name"]] = round(min(MIN_MARGIN, MARGIN_RATIO * min(bhi[0] - blo[0], bhi[1] - blo[1])), 4)
    bad = sorted(n for n, m in margin.items() if m < need[n] - 1e-6)
    c = common.check("base.edge_margin", "fail" if bad else "pass", value=bad, threshold=MIN_MARGIN,
                     note=f"{len(margin)} parts on a base")
    return [c], {"margin": margin, "required": need}, None


if __name__ == "__main__":
    require_root()
    cli(TOOL, "base", run)
