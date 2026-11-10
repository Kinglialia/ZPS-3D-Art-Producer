"""VẼ MỚI step 1 (docs/agents/texture-artist.md §4): fill every UV region with its material colour and the light rule.

Usage: python3 T/base_fill.py --final F --model M --concept-colors VF/concept_colors.json --profile <profile>
       --res N --out V/work/paint/base_fill.png [--padding 16]
Colour per material code from concept_colors.json (the views step's {code: "#hex"}). style.light_convention:
  unlit_flat         the flat colour
  painted_top_light  faces up get + style.top_vs_side_L in L*, and L* rises GRADIENT_L from the bottom to the top
A code missing from concept_colors.json is filled mid grey and listed. Gutter: --padding px around each island.
Writes <out> and <out>.json. Prints one line. Exit 0, 1 when a code has no colour, 2 on error.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import id_map  # noqa: E402
import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

GRADIENT_L = 6.0
GREY = "#808080"


def fill(model, colors, light, top_l, res, padding):
    codes, g = id_map.face_codes(model)
    tm = tex.TexelMap(g["v"], g["f"], g["uv"], res)
    missing = sorted({c for c in codes if c not in colors})
    face_lab = tex.lab(np.array([tex.hex_rgb(colors.get(c, GREY)) for c in codes]))
    lab = face_lab[np.where(tm.inside, tm.face, 0)]
    if light == "painted_top_light":
        z = tm.pos[..., 2]
        lo, hi = g["v"][:, 2].min(), g["v"][:, 2].max()
        lab[..., 0] += GRADIENT_L * ((z - lo) / max(hi - lo, 1e-9) - 0.5)
        lab[..., 0] += np.where(tm.nrm[..., 2] > 0.7, top_l, 0)
    rgb = tex.lab_to_rgb(lab)
    rgb[~tm.inside] = 0
    return tex.gutter(rgb, tm.inside, padding), missing


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--final", "--model", "--concept-colors", "--profile", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    a = p.parse_args()
    try:
        import yaml
        style = (yaml.safe_load(open(a.profile, encoding="utf-8")) or {}).get("style") or {}
        colors = json.load(open(a.concept_colors, encoding="utf-8"))
        img, missing = fill(a.model, colors, style.get("light_convention", "unlit_flat"),
                            float(style.get("top_vs_side_L") or 0), a.res, a.padding)
        tex.save_rgb(img, a.out)
    except Exception as e:  # noqa: BLE001
        print(f"[base_fill] error: {e!r}")
        sys.exit(2)
    json.dump({"light_convention": style.get("light_convention"), "missing_codes": missing},
              open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=1)
    print(f"[base_fill] {a.res}x{a.res}" + (f", thiếu màu: {', '.join(missing)}" if missing else "") + f" -> {a.out}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    require_root()
    main()
