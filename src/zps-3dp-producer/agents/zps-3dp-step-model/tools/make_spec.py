"""Write F/spec.json, the kit task spec every model tool and kit QA check reads (docs/agents/3d-artist.md §2, §6).

Usage: python3 tools/make_spec.py --final F --blockout B --card C/asset-card.yaml --profile <profile> --preset <preset>
Geometry comes only from B/sources.json (D22.13): W x D x H, character_h, door_h, camera azimuth, elevation, fov.
includes_base: false takes W x D x H from B/assembly.json instead, because layout then leaves the base out.
Other numbers follow D13, later wins: skill default < preset < profile `overrides` < asset card.
  tris cap: card tris_max, else tiers[card tier]; texture_res: card, else 2048; texel minimum;
  uv padding: stated at 2048, scaled by texture_res / 2048 (8 px at 1024, as the kit table);
  detail.relief_min_px 3, detail.alpha_min_px 16 (profile overrides.detail changes them);
  model.bevel: card `bevel`, else profile `style.bevel`, else none (D27.10). none = false; toon = the preset's
  bevel.toon numbers (radius_m, segments). Nothing else turns bevel on, notes and overrides included.
spec["sources"] names the layer of every number ("mặc định" = skill default).
Keeps `sun` and `concept_cam` of an existing F/spec.json: the worker sets them at A7.
Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/make_spec"
DEFAULTS = {"texture_res": 2048, "detail": {"relief_min_px": 3, "alpha_min_px": 16}}
KEPT = ("sun", "concept_cam")
USED = ("tris_cap", "texture_res", "uv.padding_px", "uv.texel_min_px_per_m", "detail.relief_min_px", "detail.alpha_min_px",
        "bevel", "camera.target_px_height", "screen_tris_max_small_ratio", "dimensions")
DIM_TOLERANCE = 0.02
PADDING_AT = 2048


def yaml_load(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def layered(layers):
    """Deep merge of (label, dict) layers; returns (merged, {dotted key: label of the layer that set it})."""
    out, src = {}, {}

    def put(d, o, prefix, label):
        for k, v in d.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                put(v, o.setdefault(k, {}), key + ".", label)
            else:
                o[k], src[key] = v, label
    for label, d in layers:
        put(d or {}, out, "", label)
    return out, src


def bevel(card, prof, preset):
    """(spec.model.bevel, source): false for none, else {style, radius_m, segments} from preset bevel.<style>."""
    if card.get("bevel") is not None:
        style, src = card["bevel"], "thẻ asset bevel"
    elif (prof.get("style") or {}).get("bevel") is not None:
        style, src = prof["style"]["bevel"], "profile style.bevel"
    else:
        style, src = "none", "mặc định"
    if style == "none":
        return False, src
    return {"style": style, **preset["bevel"][style]}, f"{src}; số: preset bevel.{style}"


def build(a):
    s = common.read_json(os.path.join(a.blockout, "sources.json"))
    card, prof, preset = yaml_load(a.card), yaml_load(a.profile), yaml_load(a.preset)
    p, src = layered([("mặc định", DEFAULTS), ("preset", preset), ("profile overrides", prof.get("overrides"))])
    p["detail"].pop("bevel", None)
    bev, src["bevel"] = bevel(card, prof, preset)
    aid = str(card.get("asset") or os.path.basename(os.path.dirname(os.path.abspath(a.card))))
    tier = card.get("tier") or "standard"
    if card.get("tris_max"):
        cap, src["tris_cap"] = int(card["tris_max"]), "thẻ asset tris_max"
    else:
        cap, src["tris_cap"] = int(p["tiers"][tier]), f"{src[f'tiers.{tier}']} tiers.{tier}"
    if card.get("texture_res"):
        res, src["texture_res"] = int(card["texture_res"]), "thẻ asset"
    else:
        res = int(p["texture_res"])
    pad = max(1, round(int(p["uv"]["padding_px"]) * res / PADDING_AT))
    if res != PADDING_AT:
        src["uv.padding_px"] += f"; × {res}/{PADDING_AT}"
    lay = s["layout"]
    if lay.get("includes_base", True):
        dims, src["dimensions"] = [float(lay[k]) for k in ("w", "d", "h")], "sources.json layout"
    else:
        dims = [float(x) for x in common.read_json(os.path.join(a.blockout, "assembly.json"))["data"]["union"]["extents"]]
        src["dimensions"] = "assembly.json union (includes_base: false)"
    cam = dict(s.get("camera") or {})
    spec = {
        "asset": aid, "objects": [aid],
        "budget": {"max_tris_total": cap, "max_materials_total": 1},
        "dimensions_m": {aid: dims}, "dimensions_tolerance": DIM_TOLERANCE, "height_m": dims[2],
        "pivot": "bottom_center",
        "uv": {"resolution": res, "min_padding_px": pad, "allow_overlap": False,
               "allow_out_of_bounds": False},
        "export": {"path": f"{aid}-untextured.glb", "skip_export": True},
        "model": {"texel_min_px_per_m": float(p["uv"]["texel_min_px_per_m"]), **p["detail"], "bevel": bev,
                  "target_px_height": p["camera"]["target_px_height"],
                  "px_per_m": round(p["camera"]["target_px_height"] / dims[2], 2),
                  "character_h": s["character_h"], "door_h": s.get("door_h")},
        "sources": {k: src[k] for k in USED if k in src} | {"camera": "sources.json camera",
                                                              "character_h": "sources.json", "door_h": "sources.json"},
    }
    if cam:
        spec["camera"] = {"type": "persp", **{k: cam[k] for k in ("azimuth_deg", "elevation_deg", "fov_v_deg") if k in cam},
                          "target_px_height": p["camera"]["target_px_height"]}
    if p.get("screen_tris_max_small_ratio") is not None:
        spec["screen_tris"] = {"max_small_ratio": p["screen_tris_max_small_ratio"]}
    out = os.path.join(a.final, "spec.json")
    old = common.read_json(out) if os.path.isfile(out) else {}
    spec |= {k: old[k] for k in KEPT if k in old}
    common.write_json(out, spec)
    return out, spec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("final", "blockout", "card", "profile", "preset"):
        p.add_argument(f"--{k}", required=True)
    a = p.parse_args()
    try:
        out, s = build(a)
    except Exception as e:  # noqa: BLE001
        print(f"[{TOOL}] error: {e!r}")
        sys.exit(2)
    w, d, h = s["dimensions_m"][s["asset"]]
    print(f"[{TOOL}] {out}: tris cap {s['budget']['max_tris_total']}, texture {s['uv']['resolution']}, "
          f"padding {s['uv']['min_padding_px']} px, {w}x{d}x{h} m")


if __name__ == "__main__":
    require_root()
    main()
