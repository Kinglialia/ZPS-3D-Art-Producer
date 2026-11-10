#!/usr/bin/env python3
"""Card `counts` against the part graph (D30.6): `check_counts.py <final/> <asset-card.yaml>`.
Writes <final>/review/checks/counts.json; `P ingest` runs it for every step with `counts_gate` in pipeline.toml.
  counts.<key>  the part graph has a param named <key>, listed in `fixed_params`, equal to the card's number. A key with
                no such param fails: a count is checked only when a fixed param carries it into the geometry.
Only the 6 keys of KEYS are compared; check_card.py refuses any other key.
Prints one line. Exit 0 pass or not_checked, 1 fail."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from root_guard import require_root

KEYS = ("body_board_rows", "lid_board_rows", "doors", "windows", "pillars", "steps")
TOOL = "producer/check_counts"


def check_key(graph: dict, key: str, want) -> dict:
    params, fixed = graph.get("params") or {}, set(graph.get("fixed_params") or [])
    if key not in params:
        bad = [f"part graph không có param {key}: đặt param {key} = {want} vào params và fixed_params, "
               f"rồi truyền tên {key} vào hàm dựng số đó"]
    elif key not in fixed:
        bad = [f"param {key} không có trong fixed_params"]
    elif params[key] != want:
        bad = [f"param {key} = {params[key]}, thẻ {key} = {want}"]
    else:
        bad = []
    return {"check": f"counts.{key}", "status": "fail" if bad else "pass", "value": bad, "threshold": want}


def run(final: Path, card: dict) -> dict:
    try:
        graph = json.loads((final / "part_graph.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return {"tool": TOOL, "overall": "error", "checks": [
            {"check": "counts.part_graph", "status": "error", "value": [f"không đọc được part_graph.json: {ex}"]}]}
    checks = [check_key(graph, k, v) for k, v in (card.get("counts") or {}).items() if k in KEYS]
    status = [c["status"] for c in checks]
    overall = "fail" if "fail" in status else "pass" if "pass" in status else "not_checked"
    return {"tool": TOOL, "overall": overall, "checks": checks}


def write(final: Path, card_path: Path) -> dict | None:
    """None, and no file, for a card without `counts`: there is nothing to compare."""
    import yaml
    card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
    if not card.get("counts"):
        return None
    r = run(final, card)
    out = final / "review" / "checks" / "counts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def lines(card: dict) -> list[str]:
    """The brief line for a counts_gate step: the fixed param each card count needs in the part graph."""
    rows = [f"{k} = {v}" for k, v in (card.get("counts") or {}).items() if k in KEYS]
    return [f"COUNTS: {'; '.join(rows)}", ""] if rows else []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("final", type=Path)
    ap.add_argument("card", type=Path)
    a = ap.parse_args()
    r = write(a.final, a.card) or {"overall": "not_checked", "checks": []}
    bad = [x for c in r["checks"] if c["status"] in ("fail", "error") for x in c["value"]]
    print(f"[check_counts] {r['overall']}" + (f": {'; '.join(bad)}" if bad else ""))
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
