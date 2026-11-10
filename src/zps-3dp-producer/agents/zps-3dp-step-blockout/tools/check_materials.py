"""Every part (mirror_of parts too) has a material code listed in sources.json materials. Plain Python.

Usage: python3 tools/check_materials.py --work <dir> [--out <json>]
Value lists "<part>: <code>" for unknown or missing codes. data.unused lists codes no part uses.
Writes <dir>/review/checks/materials.json. Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_materials"


def run(graph, sources):
    known = set(sources["materials"])
    parts = graph.get("parts", [])
    bad = sorted(f"{p['name']}: {p.get('material')}" for p in parts if p.get("material") not in known)
    used = {p.get("material") for p in parts}
    c = common.check("materials.known", "fail" if bad else "pass", value=bad, note=f"{len(known)} codes in sources.json")
    return [c], {"unused": sorted(known - used)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--out")
    a = p.parse_args()
    out = a.out or os.path.join(a.work, "review", "checks", "materials.json")
    src = os.path.join(a.work, "part_graph.json")
    try:
        checks, data = run(common.read_json(src), common.read_json(os.path.join(a.work, "sources.json")))
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=src)
        sys.exit(2)
    r = common.write_result(out, TOOL, checks, data=data, source=src)
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
