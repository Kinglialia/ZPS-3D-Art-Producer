"""Files the views brief names exist (D22.12: existence only; the Producer script checks hashes).

Usage: python3 tools/check_inputs.py --final <V/final> --blockout <blockout final> --concept <_approved/<id>>
  inputs.blockout  part_graph.json, sources.json, blockout.md, parts/<part>.glb of every part in the graph
  inputs.concept   concept_albedo.png, asset-card.yaml, <id>.material.md
Writes <final>/review/checks/inputs.json. Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "views/check_inputs"


def missing(base, names):
    return sorted(n for n in names if not os.path.isfile(os.path.join(base, n)))


def run(a):
    pg = os.path.join(a.blockout, "part_graph.json")
    parts = [f"parts/{p['name']}.glb" for p in common.read_json(pg).get("parts", [])] if os.path.isfile(pg) else []
    aid = os.path.basename(os.path.normpath(a.concept))
    groups = {"inputs.blockout": (a.blockout, ["part_graph.json", "sources.json", "blockout.md", *parts]),
              "inputs.concept": (a.concept, ["concept_albedo.png", "asset-card.yaml", f"{aid}.material.md"])}
    out = []
    for name, (base, names) in groups.items():
        miss = missing(base, names)
        out.append(common.check(name, "fail" if miss else "pass", value=miss, note=base))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--blockout", required=True)
    p.add_argument("--concept", required=True)
    a = p.parse_args()
    out = os.path.join(a.final, "review", "checks", "inputs.json")
    try:
        checks = run(a)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(2)
    sys.exit(1 if common.write_result(out, TOOL, checks)["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
