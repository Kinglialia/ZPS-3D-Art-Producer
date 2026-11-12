"""Write F/spec.json, the kit task spec every model tool and kit QA check reads (docs/agents/3d-artist.md §2, §6).

Usage: python3 tools/make_spec.py --final F --blockout B --card C/asset-card.yaml --profile <profile> --preset <preset>
       [--light "from=<left|right|front> elevation=<deg>"]
Geometry comes only from B/sources.json (D22.13): W x D x H, character_h, door_h, camera azimuth, elevation, fov.
includes_base: false takes W x D x H from B/assembly.json instead, because layout then leaves the base out.
Other numbers follow D13, later wins: skill default < preset < profile `overrides` < asset card.
  tris cap: card tris_max, else tiers[card tier]; texture_res: card, else 2048; texel minimum;
  uv padding: stated at 2048, scaled by texture_res / 2048 (8 px at 1024, as the kit table);
  detail.relief_min_px 3, detail.alpha_min_px 16 (profile overrides.detail changes them);
  model.uv_stretch {max_ratio 2.0, max_share 0.05} for check_uv_edge.py uv.stretch (provisional);
  model.bevel: card `bevel`, else profile `style.bevel`, else none (D27.10). none = false; toon = the preset's
  bevel.toon numbers (radius_m, segments). Nothing else turns bevel on, notes and overrides included.
Game camera (sources.json camera): fixed, so screen_tris_check can block with screen_tris.max_small_ratio
(docs/agents/3d-artist.md §10). distance_m puts the asset model.target_px_height px tall on a 1080 px screen.
The asset's height on screen is H cos(el) + (|W sin(az)| + |D cos(az)|) sin(el) metres, the bbox seen from the camera;
model.px_per_m = target_px_height / that height, the scale of thumb.png. Without a camera: target_px_height / H.
spec.concept: the concept masks and cameras of the blockout, so render_views.py --spec F/spec.json draws overlay_*.
The views of B/../work/spec.json (the blockout's own spec) are copied to F/concept/<view>.png; the cameras are its
concept.cameras, then data.cameras of B/camera_fit.json when that file exists. No blockout masks: no concept key.
spec["sources"] names the layer of every number ("mặc định" = skill default).
Keeps `sun` and `concept_cam` of an existing F/spec.json: the worker sets them at A7.
--light (the value of the brief's LIGHT: line) writes `sun` instead, and replaces a kept one. `from` is the side of the
image of concept_shadow.png that the light comes from (left: the lit side is at the left edge, the shadow falls to the
right). azimuth_deg = azimuth of the concept camera + (left -45, right +45, front 0), wrapped to -180..180; elevation_deg
as given. The concept camera is the `concept_cam` of an existing spec, else concepts.cameras["34"] when the card says
view: '34' (concept_shadow.png is then the 3/4 image), else the front view (azimuth 0).
`bottom_visible` of the card (a bool) goes to the spec; a card without it keeps the value of an existing spec.
Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/make_spec"
# uv_stretch: provisional, not yet measured on a real asset; preset or profile overrides replace it.
DEFAULTS = {"texture_res": 2048, "detail": {"relief_min_px": 3, "alpha_min_px": 16},
            "uv_stretch": {"max_ratio": 2.0, "max_share": 0.05}}
KEPT = ("sun", "concept_cam", "bottom_visible")
LIGHT = re.compile(r"from=(left|right|front) elevation=(-?\d+(?:\.\d+)?)")
LIGHT_OFFSET_DEG = {"left": -45.0, "right": 45.0, "front": 0.0}
USED = ("tris_cap", "texture_res", "uv.padding_px", "uv.texel_min_px_per_m", "detail.relief_min_px", "detail.alpha_min_px",
        "bevel", "camera.target_px_height", "screen_tris_max_small_ratio", "uv_stretch.max_ratio", "uv_stretch.max_share",
        "dimensions", "px_per_m")
DIM_TOLERANCE = 0.02
PADDING_AT = 2048
SCREEN = [1920, 1080]


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


def screen_height_m(dims, cam):
    """Metres of the bbox along the screen's up axis, seen from the camera (orthographic estimate)."""
    w, d, h = dims
    az, el = math.radians(cam.get("azimuth_deg", 0)), math.radians(cam.get("elevation_deg", 35))
    return h * math.cos(el) + (abs(w * math.sin(az)) + abs(d * math.cos(az))) * math.sin(el)


def concept(blockout, final):
    """spec.concept for F: the blockout's masks copied into F/concept/ and its fitted cameras; None without masks."""
    src = os.path.join(blockout, "..", "work", "spec.json")
    c = (common.read_json(src).get("concept") or {}) if os.path.isfile(src) else {}
    views = {}
    for label, rel in (c.get("views") or {}).items():
        dst = os.path.join("concept", f"{label}.png")
        os.makedirs(os.path.join(final, "concept"), exist_ok=True)
        shutil.copyfile(common.spec_rel(src, rel), os.path.join(final, dst))
        views[label] = dst
    cams = dict(c.get("cameras") or {})
    fit = os.path.join(blockout, "camera_fit.json")
    if os.path.isfile(fit):
        cams |= common.read_json(fit)["data"].get("cameras") or {}
    if not views:
        return None
    return {"views": views, "cameras": cams} | ({"background": c["background"]} if c.get("background") else {})


def sun_of(light, card, spec, old):
    """(sun, concept camera azimuth) for a `--light` value; see the docstring."""
    m = LIGHT.fullmatch(light.strip())
    if not m:
        raise ValueError(f"--light {light!r}: want 'from=<left|right|front> elevation=<deg>'")
    cam = (old.get("concept_cam") or {}).get("azimuth_deg")
    if cam is None and str(card.get("view")) == "34":
        cam = ((spec.get("concept") or {}).get("cameras") or {}).get("34", {}).get("azimuth_deg")
    cam = float(cam or 0)
    az = (cam + LIGHT_OFFSET_DEG[m[1]] + 180) % 360 - 180
    return {"azimuth_deg": round(az, 2), "elevation_deg": float(m[2])}, cam


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
    tpx = p["camera"]["target_px_height"]
    seen_h = screen_height_m(dims, cam) if cam else dims[2]
    src["px_per_m"] = ("camera.target_px_height / chiều cao bbox trên màn hình ở camera game" if cam
                       else "camera.target_px_height / chiều cao (sources.json không có camera)")
    spec = {
        "asset": aid, "objects": [aid],
        "budget": {"max_tris_total": cap, "max_materials_total": 1},
        "dimensions_m": {aid: dims}, "dimensions_tolerance": DIM_TOLERANCE, "height_m": dims[2],
        "pivot": "bottom_center",
        "uv": {"resolution": res, "min_padding_px": pad, "allow_overlap": False,
               "allow_out_of_bounds": False},
        "export": {"path": f"{aid}-untextured.glb", "skip_export": True},
        "model": {"texel_min_px_per_m": float(p["uv"]["texel_min_px_per_m"]), **p["detail"], "bevel": bev,
                  "uv_stretch": p["uv_stretch"],
                  "target_px_height": tpx, "px_per_m": round(tpx / seen_h, 2),
                  "character_h": s["character_h"], "door_h": s.get("door_h")},
        "sources": {k: src[k] for k in USED if k in src} | {"camera": "sources.json camera",
                                                              "character_h": "sources.json", "door_h": "sources.json"},
    }
    if cam:
        fov = math.radians(cam.get("fov_v_deg", 40))
        spec["camera"] = {"type": "persp", **{k: cam[k] for k in ("azimuth_deg", "elevation_deg", "fov_v_deg") if k in cam},
                          "target_px_height": tpx, "screen": SCREEN,
                          "distance_m": round(seen_h * SCREEN[1] / (2 * math.tan(fov / 2) * tpx), 3)}
    if cc := concept(a.blockout, a.final):
        spec["concept"] = cc
        spec["sources"]["concept"] = "blockout work/spec.json" + (", camera_fit.json" if os.path.isfile(
            os.path.join(a.blockout, "camera_fit.json")) else "")
    if p.get("screen_tris_max_small_ratio") is not None:
        spec["screen_tris"] = {"max_small_ratio": p["screen_tris_max_small_ratio"]}
    out = os.path.join(a.final, "spec.json")
    old = common.read_json(out) if os.path.isfile(out) else {}
    spec |= {k: old[k] for k in KEPT if k in old}
    if a.light:
        spec["sun"], cam = sun_of(a.light, card, spec, old)
        spec["sources"]["sun"] = f"thẻ light ({a.light}), camera concept az {cam:g}"
    if isinstance(card.get("bottom_visible"), bool):
        spec["bottom_visible"] = card["bottom_visible"]
        spec["sources"]["bottom_visible"] = "thẻ asset"
    common.write_json(out, spec)
    return out, spec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("final", "blockout", "card", "profile", "preset"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--light")
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
