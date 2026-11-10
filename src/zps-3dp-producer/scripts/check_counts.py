#!/usr/bin/env python3
"""Card `counts` against the part graph (D30.6): `check_counts.py <final/> <asset-card.yaml> [--map counts.yaml]`.
Writes <final>/review/checks/counts.json; `P ingest` runs it for every step with `counts_gate` in pipeline.toml.
  counts.<key>  every part whose `fn` is the mapped function passes, for the mapped argument, the name of a param in
                `fixed_params`, and that param equals the card's number. No such part: fail.
                A card key with no map entry for the card's type: not_checked (check_card.py warns).
Prints one line. Exit 0 pass or not_checked, 1 fail."""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

from root_guard import require_root

SKILL = Path(__file__).resolve().parents[1]
MAP = SKILL / "templates" / "counts.yaml"
CUSTOM_LIB = next(SKILL.glob("agents/zps-3dp-step-blockout*/tools/custom_lib.py"), SKILL / "agents/x/tools/x").parent  # Codex: -codex
KEYS = ("body_board_rows", "lid_board_rows", "doors", "windows", "pillars", "steps")
TOOL = "producer/check_counts"


def load_map(path: Path = MAP) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def arg_names(fn: str) -> list[str] | None:
    """Parameter names of a custom_lib function, so a positional `args` list can be read by name."""
    if str(CUSTOM_LIB) not in sys.path:
        sys.path.append(str(CUSTOM_LIB))
    import custom_lib
    f = custom_lib.FUNCTIONS.get(fn)
    return list(inspect.signature(f).parameters) if f else None


def arg_of(part: dict, name: str, names: list[str]):
    args = part.get("args")
    if isinstance(args, dict):
        return args.get(name)
    i = names.index(name)
    return args[i] if isinstance(args, list) and i < len(args) else None


def check_key(graph: dict, key: str, want, target: str) -> dict:
    fn, _, arg = target.partition(".")
    names = arg_names(fn)
    if not names or arg not in names:
        return {"check": f"counts.{key}", "status": "fail", "value": [f"bảng ánh xạ sai: {fn} không có tham số {arg}"],
                "threshold": want, "note": target}
    parts = [p for p in graph.get("parts", []) if p.get("primitive") == "custom" and p.get("fn") == fn]
    params, fixed = graph.get("params") or {}, set(graph.get("fixed_params") or [])
    bad = []
    for p in parts:
        v = arg_of(p, arg, names)
        if not isinstance(v, str) or v not in params:
            bad.append(f"{p['name']}: {arg} = {v!r}, cần tên một param")
        elif v not in fixed:
            bad.append(f"{p['name']}: {arg} = {v}, param {v} không có trong fixed_params")
        elif params[v] != want:
            bad.append(f"{p['name']}: {arg} = {v} = {params[v]}, thẻ {key} = {want}")
    if not parts:
        bad.append(f"không part nào dùng {fn}")
    return {"check": f"counts.{key}", "status": "fail" if bad else "pass", "value": bad, "threshold": want,
            "note": target}


def run(final: Path, card: dict, cmap: dict) -> dict:
    counts = card.get("counts") or {}
    table = cmap.get(card.get("type")) or {}
    try:
        graph = json.loads((final / "part_graph.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return {"tool": TOOL, "overall": "error", "checks": [
            {"check": "counts.part_graph", "status": "error", "value": [f"không đọc được part_graph.json: {ex}"]}]}
    checks = [check_key(graph, k, v, table[k]) if k in table else
              {"check": f"counts.{k}", "status": "not_checked", "value": v,
               "note": f"chưa có ánh xạ cho type {card.get('type')}"} for k, v in counts.items() if k in KEYS]
    status = [c["status"] for c in checks]
    overall = "fail" if "fail" in status else "pass" if "pass" in status else "not_checked"
    return {"tool": TOOL, "overall": overall, "checks": checks}


def write(final: Path, card_path: Path, cmap: dict | None = None) -> dict | None:
    """None, and no file, for a card without `counts`: there is nothing to compare."""
    import yaml
    card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
    if not card.get("counts"):
        return None
    r = run(final, card, load_map() if cmap is None else cmap)
    out = final / "review" / "checks" / "counts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def lines(card: dict, cmap: dict | None = None) -> list[str]:
    """The brief line for a counts_gate step: what each mapped card count must be in the part graph."""
    table = ((load_map() if cmap is None else cmap).get(card.get("type")) or {})
    rows = [f"{k} = {v} → {table[k]}" for k, v in (card.get("counts") or {}).items() if k in table]
    return [f"COUNTS: {'; '.join(rows)}", ""] if rows else []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("final", type=Path)
    ap.add_argument("card", type=Path)
    ap.add_argument("--map", type=Path, default=MAP)
    a = ap.parse_args()
    r = write(a.final, a.card, load_map(a.map)) or {"overall": "not_checked", "checks": []}
    bad = [x for c in r["checks"] if c["status"] in ("fail", "error") for x in c["value"]]
    print(f"[check_counts] {r['overall']}" + (f": {'; '.join(bad)}" if bad else ""))
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
