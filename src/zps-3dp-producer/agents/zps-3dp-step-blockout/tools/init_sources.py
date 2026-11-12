"""Fill the computable fields of <w>/sources.json from the asset card, the profile and its preset. Plain Python + PyYAML.

Usage: PY T/init_sources.py --work <w> --approved <_approved/<id>> --profile <PROJECT-PROFILE.yaml> [--out <json>]
Writes (has_map false):
  files.layout, files.layout_sha256     asset-card.yaml
  files.material, files.material_sha256 <id>.material.md of the approved folder
  layout.{w, d, h, includes_base, source}  size_m of the card; includes_base true (size_m is the size of the whole object)
  character_h                           the one scale_refs entry of the profile, or the one named "nhân vật"
  door_h, door_h_source                 the one scale_overrides entry of the card
  camera                                camera of the preset the profile names, or null
  marks                                 one entry per `marks` name of the card: "<part>.top" or "<part>.bottom", the
                                        part edge the worker builds that mark with (check_proportion.py checks it);
                                        no key when the card has no marks
Every field it cannot compute is the string "TODO ..." for the worker: materials (the codes the worker reads on the
concept), door_h and door_h_source when the card has no single scale_overrides entry (measure it on the concept with
character_h as the ruler, or write null and say why), and, when has_map is true, layout, character_h and door_h (read from
<id>.layout.md), and each marks entry. check_inputs.py fails while a value starts with TODO.
An existing sources.json keeps what the worker wrote where this tool computes nothing: materials, door_h, the marks
entries of names the card still has, and the fields of a has_map layout. What it computes is written again, so a changed card gives new numbers and new hashes.
Prints one line: the path, then the fields still TODO. Exit 0, 2 on error.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "[blockout/init_sources]"
PRESETS = os.environ.get("PRODUCER_PRESETS") or os.path.join(HERE, "..", "..", "..", "presets")
CAMERA_KEYS = ("azimuth_deg", "elevation_deg", "fov_v_deg")
CHARACTER = "nhân vật"
TODO = {"materials": "TODO: the material codes of the concept, as a list",
        "layout": "TODO: w, d, h, includes_base and source of the layout",
        "character_h": "TODO: the height of the character in metres",
        "door_h": "TODO: measure on the concept with character_h as the ruler, or null and say why",
        "door_h_source": "TODO: how door_h was measured, or why there is none"}
MARK_TODO = "TODO: <part>.top or <part>.bottom, the part edge that makes this mark"


def yaml_load(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def material_file(approved, aid):
    own = os.path.join(approved, f"{aid}.material.md")
    if os.path.isfile(own):
        return own
    found = glob.glob(os.path.join(approved, "*material*.md"))
    return found[0] if len(found) == 1 else None


def character_h(profile):
    refs = [r for r in profile.get("scale_refs") or [] if isinstance(r, dict) and "height_m" in r]
    pick = refs if len(refs) == 1 else [r for r in refs if r.get("name") == CHARACTER]
    return float(pick[0]["height_m"]) if len(pick) == 1 else None


def camera(profile):
    path = os.path.join(PRESETS, f"{profile.get('preset')}.yaml")
    cam = (yaml_load(path).get("camera") if os.path.isfile(path) else None) or {}
    return {k: cam[k] for k in CAMERA_KEYS} if all(k in cam for k in CAMERA_KEYS) else None


def computed(approved, profile_path):
    """The fields the card, the profile and the preset give. A field they cannot give is left out."""
    aid = os.path.basename(os.path.normpath(approved))
    profile = yaml_load(profile_path)
    has_map = bool(profile.get("has_map"))
    layout_path = os.path.join(approved, f"{aid}.layout.md" if has_map else "asset-card.yaml")
    mat = material_file(approved, aid)
    out = {"files": {"layout": os.path.abspath(layout_path) if os.path.isfile(layout_path)
                     else f"TODO: no {os.path.basename(layout_path)} in {approved}",
                     "layout_sha256": common.file_sha256(layout_path),
                     "material": os.path.abspath(mat) if mat else f"TODO: no {aid}.material.md in {approved}",
                     "material_sha256": common.file_sha256(mat)},
           "camera": camera(profile)}
    if has_map:
        return out
    card_path = os.path.join(approved, "asset-card.yaml")
    card = yaml_load(card_path) if os.path.isfile(card_path) else {}
    size = card.get("size_m") or {}
    if all(isinstance(size.get(k), (int, float)) for k in "wdh"):
        out["layout"] = {**{k: size[k] for k in "wdh"}, "includes_base": True, "source": "asset-card.yaml size_m"}
    height = character_h(profile)
    if height is not None:
        out["character_h"] = height
    over = [o for o in card.get("scale_overrides") or [] if isinstance(o, dict) and "height_m" in o]
    if len(over) == 1:
        out["door_h"] = float(over[0]["height_m"])
        out["door_h_source"] = f"asset-card.yaml scale_overrides {over[0].get('name')} height_m"
    return out


def marks(approved, old):
    """{mark name: part edge} for every `marks` entry of the card: the worker's edge, else a TODO. None without marks."""
    card_path = os.path.join(approved, "asset-card.yaml")
    names = [m["name"] for m in (yaml_load(card_path).get("marks") or []) if isinstance(m, dict) and "name" in m] \
        if os.path.isfile(card_path) else []
    return {n: old[n] if isinstance(old.get(n), str) and old[n] and not old[n].startswith("TODO") else MARK_TODO
            for n in names} or None


def with_todo(doc):
    """doc with a TODO string for every required field it still lacks."""
    for key, text in TODO.items():
        if key not in doc:
            doc[key] = text
    if not (isinstance(doc.get("materials"), list) and doc["materials"]):
        doc["materials"] = TODO["materials"]
    return doc


def todo_fields(doc):
    def bad(v):
        return isinstance(v, str) and v.startswith("TODO") or isinstance(v, dict) and any(bad(x) for x in v.values())
    return sorted(k for k, v in doc.items() if bad(v))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True)
    p.add_argument("--approved", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--out")
    a = p.parse_args()
    out = a.out or os.path.join(a.work, "sources.json")
    try:
        doc = common.read_json(out) if os.path.isfile(out) else {}
        new = computed(a.approved, a.profile)
        doc = with_todo({**doc, **{k: v for k, v in new.items() if k != "files"}, "files": {**doc.get("files", {}), **new["files"]}})
        doc["marks"] = marks(a.approved, doc.get("marks") or {})
        if doc["marks"] is None:
            del doc["marks"]
        common.write_json(out, doc)
    except Exception as e:  # noqa: BLE001
        print(f"{NAME} error {e!r}")
        sys.exit(2)
    left = todo_fields(doc)
    print(f"{NAME} {out}" + (f"; TODO: {', '.join(left)}" if left else "; nothing left to fill"))


if __name__ == "__main__":
    require_root()
    main()
