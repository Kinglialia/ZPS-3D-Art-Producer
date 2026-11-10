"""Every `tag: roof` part has another part touching its bottom, within 1 cm. Plain Python, bbox only.

Usage: python3 tools/check_support.py --work <dir> [--out <json>]
A part touches the roof bottom when it rises from below to the roof's bottom plane (top within 1 cm
of it or above, bottom more than 1 cm below it) and its footprint overlaps the roof's. A part level
with the roof, such as a second roof beside it, does not hold it up. Bbox only: can miss a small gap,
never reports a false one.
No roof tag: overall not_checked.
Writes <dir>/review/checks/support.json. Exit 0 pass/not_checked, 1 fail, 2 error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import cli, tags  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_support"
TOUCH = 0.01


def touches(o, roof):
    z = roof["bbox_min"][2]
    span = o["bbox_min"][2] < z - TOUCH <= o["bbox_max"][2]
    overlap = all(min(o["bbox_max"][a], roof["bbox_max"][a]) > max(o["bbox_min"][a], roof["bbox_min"][a]) for a in (0, 1))
    return span and overlap


def run(a, graph, rows, sources):
    tag = tags(graph)
    roofs = [r for r in rows if tag.get(r["name"]) == "roof"]
    if not roofs:
        return [common.check("support.roof", "not_checked", note="no part has tag: roof")], {}, "not_checked"
    support = {r["name"]: [o["name"] for o in rows if o is not r and touches(o, r)] for r in roofs}
    bad = sorted(n for n, s in support.items() if not s)
    c = common.check("support.roof", "fail" if bad else "pass", value=bad, threshold=TOUCH,
                     note=f"{len(roofs)} roof parts")
    return [c], {"support": support}, None


if __name__ == "__main__":
    require_root()
    cli(TOOL, "support", run)
