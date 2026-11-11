#!/usr/bin/env python3
"""Card `counts` against the part graph (D30.6, D32.5, D34.3): `check_counts.py <final/> <asset-card.yaml>`.
Writes <final>/review/checks/counts.json; `P ingest` runs it for every step with `counts_gate` in pipeline.toml.
  counts.<key>  when `fixed_params` lists a param named <key>, that param equals the card's number; otherwise the
                number of parts with `tag: <key>` equals it (no such part counts 0). A count written as a literal in a
                part's args, or kept in a param a fix round may change, fails.
Every key of the card is compared. The keys a project uses are its profile's `counts_keys` (D34.3): check_card.py warns
about a key outside that list, and this gate still compares it, so a mistyped key cannot pass unchecked.
Prints one line. Exit 0 pass or not_checked, 1 fail."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from root_guard import require_root

TOOL = "producer/check_counts"
HOW = "mỗi khóa: param cùng tên trong fixed_params, hoặc đúng N part có tag: <khóa>"


def check_key(graph: dict, key: str, want) -> dict:
    params, fixed = graph.get("params") or {}, set(graph.get("fixed_params") or [])
    if key in fixed and key in params:
        bad = [] if params[key] == want else [f"param {key} = {params[key]}, thẻ {key} = {want}"]
    else:
        n = sum(1 for p in graph.get("parts") or [] if isinstance(p, dict) and p.get("tag") == key)
        loose = f" (param {key} có nhưng không nằm trong fixed_params)" if key in params else ""
        bad = [] if n == want else [f"{n} part có tag: {key}, thẻ {key} = {want}{loose}: đặt param {key} = {want} vào "
                                    f"params và fixed_params, hoặc gắn tag: {key} cho đúng {want} part"]
    return {"check": f"counts.{key}", "status": "fail" if bad else "pass", "value": bad, "threshold": want}


def run(final: Path, card: dict) -> dict:
    try:
        graph = json.loads((final / "part_graph.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return {"tool": TOOL, "overall": "error", "checks": [
            {"check": "counts.part_graph", "status": "error", "value": [f"không đọc được part_graph.json: {ex}"]}]}
    checks = [check_key(graph, k, v) for k, v in (card.get("counts") or {}).items()]
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
    """The brief line for a counts_gate step: each card count, and how the part graph must carry it."""
    rows = [f"{k} = {v}" for k, v in (card.get("counts") or {}).items()]
    return [f"COUNTS: {'; '.join(rows)} ({HOW})", ""] if rows else []


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
