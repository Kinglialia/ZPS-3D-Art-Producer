"""The files the model brief names exist (docs/agents/3d-artist.md §2, A1). Plain Python.

Usage: python3 tools/check_inputs.py --final F --blockout B --views-front FF --views-rest VR --concept C
Existence only: the Producer script checks input hashes (D22.12).
  inputs.blockout     B/part_graph.json, parts_lib.py, sources.json, blockout.md, assembly.json
  inputs.views        FF/front.png and VR/back.png, left.png, right.png, top.png
  inputs.concept      C/concept_albedo.png, concept_shadow.png, asset-card.yaml
Writes F/review/checks/inputs.json. Exit 0 pass, 1 fail, 2 error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import cli  # noqa: E402
import common  # noqa: E402

TOOL = "model/check_inputs"
NEED = {
    "inputs.blockout": [("blockout", ("part_graph.json", "parts_lib.py", "sources.json", "blockout.md", "assembly.json"))],
    "inputs.views": [("views_front", ("front.png",)), ("views_rest", ("back.png", "left.png", "right.png", "top.png"))],
    "inputs.concept": [("concept", ("concept_albedo.png", "concept_shadow.png", "asset-card.yaml"))],
}


def args(p):
    for k in ("blockout", "views-front", "views-rest", "concept"):
        p.add_argument(f"--{k}", required=True)


def check(a):
    checks = []
    for name, dirs in NEED.items():
        gone = [f"{attr}/{n}" for attr, names in dirs for n in names
                if not os.path.isfile(os.path.join(getattr(a, attr), n))]
        checks.append(common.check(name, "fail" if gone else "pass", value=gone))
    return checks, {}


if __name__ == "__main__":
    cli.run(TOOL, "inputs", __doc__, args, check)
