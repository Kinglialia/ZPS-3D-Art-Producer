"""The files the model brief names exist (docs/agents/3d-artist.md §2, A1). Plain Python.

Usage: python3 tools/check_inputs.py --final F --blockout B [--views-front FF --views-rest VR] --concept C
Existence only: the Producer script checks input hashes (D22.12).
  inputs.blockout     B/part_graph.json, parts_lib.py, sources.json, blockout.md, assembly.json
  inputs.views        FF/front.png and the side views of the card's `views` in VR (D35: full = back, left, right).
                      `views: none`: no view set; FF and VR are not read
  inputs.concept      C/concept_albedo.png, concept_shadow.png, asset-card.yaml
Writes F/review/checks/inputs.json. Exit 0 pass, 1 fail, 2 error.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
import cli  # noqa: E402
import common  # noqa: E402
from root_guard import require_root  # noqa: E402

TOOL = "model/check_inputs"
BLOCKOUT = ("part_graph.json", "parts_lib.py", "sources.json", "blockout.md", "assembly.json")
CONCEPT = ("concept_albedo.png", "concept_shadow.png", "asset-card.yaml")


def args(p):
    for k in ("blockout", "concept"):
        p.add_argument(f"--{k}", required=True)
    for k in ("views-front", "views-rest"):
        p.add_argument(f"--{k}")


def need(a):
    from check_card import VIEW_SETS, card_views
    sides = VIEW_SETS[card_views(a.concept)] if os.path.isfile(os.path.join(a.concept, "asset-card.yaml")) else None
    views = [] if sides == () else [("views_front", ("front.png",)), ("views_rest", tuple(f"{v}.png" for v in sides or ()))]
    return {"inputs.blockout": [("blockout", BLOCKOUT)], "inputs.views": views, "inputs.concept": [("concept", CONCEPT)]}


def check(a):
    checks = []
    for name, dirs in need(a).items():
        gone = [f"{attr}/{n}" for attr, names in dirs for n in names
                if not (getattr(a, attr) and os.path.isfile(os.path.join(getattr(a, attr), n)))]
        checks.append(common.check(name, "fail" if gone else "pass", value=gone))
    return checks, {}


if __name__ == "__main__":
    require_root()
    cli.run(TOOL, "inputs", __doc__, args, check)
