"""The files the texture brief names exist (D22.12: the script checks hashes, this tool only existence).

Usage: python3 T/check_inputs.py --final F --blockout B [--views-front VF --views-rest VR] --model M --concept C
Card `views: none` (D32): no view set, so VF/concept_colors.json and VR/README.md are not wanted; C/<id>.material.md is.
Writes F/review/checks/inputs.json. Prints one line. Exit 0, 1 when a file is missing.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
import tex  # noqa: E402
from root_guard import require_root  # noqa: E402


def wanted(a):
    from check_card import card_views
    aid = json.load(open(os.path.join(a.model, "spec.json"), encoding="utf-8"))["asset"] \
        if os.path.isfile(os.path.join(a.model, "spec.json")) else "?"
    card = os.path.join(a.concept, "asset-card.yaml")
    views = ([os.path.join(a.concept, f"{os.path.basename(os.path.normpath(a.concept))}.material.md")]
             if os.path.isfile(card) and card_views(a.concept) == "none" else
             [os.path.join(a.views_front or "<views_front>", "concept_colors.json"),
              os.path.join(a.views_rest or "<views_rest>", "README.md")])
    return [os.path.join(a.blockout, "sources.json"), *views, os.path.join(a.model, f"{aid}-untextured.glb"),
            os.path.join(a.model, "spec.json"), os.path.join(a.model, "part_graph.json"),
            os.path.join(a.model, "parts"), os.path.join(a.model, "review", "join.json"),
            os.path.join(a.concept, "concept_albedo.png"), os.path.join(a.concept, "concept_shadow.png"),
            os.path.join(a.concept, "asset-card.yaml")]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("--final", "--blockout", "--model", "--concept"):
        p.add_argument(k, required=True)
    for k in ("--views-front", "--views-rest"):
        p.add_argument(k)
    a = p.parse_args()
    miss = [w for w in wanted(a) if not os.path.exists(w)]
    out = os.path.join(a.final, "review", "checks", "inputs.json")
    tex.write_result(out, "check_inputs", [tex.check("inputs.missing", "fail" if miss else "pass", miss, [])])
    print(f"[check_inputs] {'thiếu ' + ', '.join(miss) if miss else 'đủ file'}")
    sys.exit(1 if miss else 0)


if __name__ == "__main__":
    require_root()
    main()
