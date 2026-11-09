"""Every `role: marker` part stands >= 2 cm out of its parent face. Plain Python, bbox only.

Usage: python3 tools/check_markers.py --work <dir> [--out <json>]
Relief = how far the marker's bbox passes the parent's bbox face on the contact side (assembly.json
contact axis and sign). inset_into parts count only the part outside the face. A marker with no
contact (root, through_axis) is listed under not_checked. No marker: overall not_checked.
Writes <dir>/review/checks/markers.json. Exit 0 pass/not_checked, 1 fail, 2 error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
from check_layout import cli, tags  # noqa: E402

TOOL = "blockout/check_markers"
MIN_RELIEF = 0.02


def run(a, graph, rows, sources):
    role = tags(graph, "role")
    by = {r["name"]: r for r in rows}
    markers = [r for r in rows if role.get(r["name"]) == "marker"]
    if not markers:
        return [common.check("markers.relief", "not_checked", note="no part has role: marker")], {}, "not_checked"
    relief, skipped = {}, []
    for r in markers:
        c, p = r["contact"], by.get(r["parent"])
        if not c or p is None:
            skipped.append(r["name"])
            continue
        ax = c["axis"]
        out = r["bbox_max"][ax] - p["bbox_max"][ax] if c["sign"] > 0 else p["bbox_min"][ax] - r["bbox_min"][ax]
        relief[r["name"]] = round(out, 4)
    bad = sorted(n for n, m in relief.items() if m < MIN_RELIEF - 1e-6)
    c = common.check("markers.relief", "fail" if bad else "pass", value=bad, threshold=MIN_RELIEF,
                     note=f"{len(relief)} markers measured")
    return [c], {"relief": relief, "not_checked": skipped}, None


if __name__ == "__main__":
    cli(TOOL, "markers", run)
