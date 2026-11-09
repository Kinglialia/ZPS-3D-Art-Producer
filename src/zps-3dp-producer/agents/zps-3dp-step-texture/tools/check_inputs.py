"""The files the texture brief names exist (D22.12: the script checks hashes, this tool only existence).

Usage: python3 T/check_inputs.py --final F --blockout B --views-front VF --views-rest VR --model M --concept C
Writes F/review/checks/inputs.json. Prints one line. Exit 0, 1 when a file is missing.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import tex  # noqa: E402


def wanted(a):
    aid = json.load(open(os.path.join(a.model, "spec.json"), encoding="utf-8"))["asset"] \
        if os.path.isfile(os.path.join(a.model, "spec.json")) else "?"
    return [os.path.join(a.blockout, "sources.json"), os.path.join(a.views_front, "concept_colors.json"),
            os.path.join(a.views_rest, "README.md"), os.path.join(a.model, f"{aid}-untextured.glb"),
            os.path.join(a.model, "spec.json"), os.path.join(a.model, "part_graph.json"),
            os.path.join(a.model, "parts"), os.path.join(a.model, "review", "join.json"),
            os.path.join(a.concept, "concept_albedo.png"), os.path.join(a.concept, "concept_shadow.png"),
            os.path.join(a.concept, "asset-card.yaml")]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("--final", "--blockout", "--views-front", "--views-rest", "--model", "--concept"):
        p.add_argument(k, required=True)
    a = p.parse_args()
    miss = [w for w in wanted(a) if not os.path.exists(w)]
    out = os.path.join(a.final, "review", "checks", "inputs.json")
    tex.write_result(out, "check_inputs", [tex.check("inputs.missing", "fail" if miss else "pass", miss, [])])
    print(f"[check_inputs] {'thiếu ' + ', '.join(miss) if miss else 'đủ file'}")
    sys.exit(1 if miss else 0)


if __name__ == "__main__":
    main()
