"""Input files exist and sources.json has every key (docs/agents/blockout.md §2). Plain Python + PyYAML.

Usage: python3 tools/check_inputs.py --work <dir> --approved <_approved/<id>> --profile <PROJECT-PROFILE.yaml> [--out <json>]
Checks file existence only, not input hashes: the Producer script owns those (D22.12).
  inputs.files          concept image, asset-card.yaml, <id>.layout.md (has_map: true), files.layout, files.material
  inputs.sources_keys   required keys of sources.json
  inputs.layout_source  has_map true: files.layout is <id>.layout.md; has_map false: files.layout is
                        asset-card.yaml and layout w/d/h equal its size_m (D20.12)
  inputs.todo           no value in sources.json starts with TODO (init_sources.py leaves those for the worker to fill)
data.sources_reusable: the recorded layout/material sha256 still match, so a rebuild may keep sources.json.
Writes <dir>/review/checks/inputs.json. Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "blockout/check_inputs"
IMAGES = (".png", ".jpg", ".jpeg", ".webp")
NUM = (int, float)
KEYS = {"files.layout": str, "files.material": str, "files.layout_sha256": str, "files.material_sha256": str,
        "layout.w": NUM, "layout.d": NUM, "layout.h": NUM, "layout.includes_base": bool, "layout.source": str,
        "door_h": NUM, "door_h_source": str, "character_h": NUM, "materials": list}


def get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def todo_keys(node, prefix=""):
    """Dotted names of every value that is a string starting with TODO."""
    if isinstance(node, dict):
        return [k for key, v in node.items() for k in todo_keys(v, f"{prefix}{key}.")]
    if isinstance(node, list):
        return [k for i, v in enumerate(node) for k in todo_keys(v, f"{prefix}{i}.")]
    return [prefix.rstrip(".")] if isinstance(node, str) and node.startswith("TODO") else []


def yaml_load(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run(work, approved, profile):
    aid = os.path.basename(os.path.normpath(approved))
    has_map = bool(yaml_load(profile).get("has_map"))
    s = common.read_json(os.path.join(work, "sources.json"))
    card_path = os.path.join(approved, "asset-card.yaml")
    layout_md = os.path.join(approved, f"{aid}.layout.md")
    missing = [] if any(f.lower().endswith(IMAGES) for f in os.listdir(approved)) else ["concept image"]
    need = [card_path] + ([layout_md] if has_map else [])
    missing += [os.path.basename(p) for p in need if not os.path.isfile(p)]
    missing += [k for k in ("files.layout", "files.material") if not os.path.isfile(str(get(s, k)))]
    no_door = get(s, "door_h") is None and isinstance(get(s, "door_h_source"), str) and get(s, "door_h_source")
    keys = [k for k, t in KEYS.items()
            if not (k == "door_h" and no_door) and (not isinstance(get(s, k), t) or get(s, k) in ("", []))]
    if "camera" not in s:
        keys.append("camera")
    layout = get(s, "files.layout")
    want = layout_md if has_map else card_path
    value = os.path.basename(want)
    src_ok = isinstance(layout, str) and os.path.abspath(layout) == os.path.abspath(want)
    if src_ok and not has_map and os.path.isfile(card_path):
        size = yaml_load(card_path).get("size_m") or {}
        diff = [k for k in ("w", "d", "h") if get(s, f"layout.{k}") != size.get(k)]
        if diff:
            src_ok, value = False, diff
    todo = sorted(todo_keys(s))
    checks = [common.check("inputs.files", "fail" if missing else "pass", value=sorted(missing)),
              common.check("inputs.todo", "fail" if todo else "pass", value=todo,
                           note="fill these values of sources.json" if todo else None),
              common.check("inputs.sources_keys", "fail" if keys else "pass", value=sorted(keys)),
              common.check("inputs.layout_source", "pass" if src_ok else "fail", value=value,
                           note=f"has_map {str(has_map).lower()}; files.layout must be {os.path.basename(want)}")]
    reuse = all(isinstance(get(s, k), str) and common.file_sha256(get(s, k)) == get(s, f"{k}_sha256")
                for k in ("files.layout", "files.material"))
    return checks, {"has_map": has_map, "sources_reusable": reuse}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--approved", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--out")
    a = p.parse_args()
    out = a.out or os.path.join(a.work, "review", "checks", "inputs.json")
    src = os.path.join(a.work, "sources.json")
    try:
        checks, data = run(a.work, a.approved, a.profile)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=src)
        sys.exit(2)
    r = common.write_result(out, TOOL, checks, data=data, source=src)
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
