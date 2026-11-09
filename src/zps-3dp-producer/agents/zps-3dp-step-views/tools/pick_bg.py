"""Flat background colour for every generated view (concept-views.md §3 step 3) -> <final>/bg_color.json.

Usage: python3 tools/pick_bg.py --final <V/final> --concept <concept_albedo.png> --profile <PROJECT-PROFILE.yaml>
style.view_bg of the profile wins. Else the first of CANDIDATES that is MIN_DIST or more (RGB distance) from
every colour palette_report finds on the concept; if none is, the farthest one. The concept's own background
(transparent, or the most common border colour) is left out first.
MIN_DIST = 100 = 2.5 x the 40 RGB key tolerance of measure.py, so no material is keyed out as background.
Writes {"hex", "source": profile|pick, "min_dist", "nearest"}. Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette_report  # noqa: E402

CANDIDATES = ("#E8E8E8", "#2B2B2B", "#3A5FCD", "#2E8B57", "#C71585", "#FF8C00")
MIN_DIST = 100.0
KEY_TOL = 40.0


def rgb(h):
    return np.array(palette_report.hex_to_rgb(h), float)


def concept_colours(path):
    a = np.asarray(Image.open(path).convert("RGBA")).copy()
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    edge = edge[edge[:, 3] >= 128][:, :3]
    if len(edge):
        cols, n = np.unique(edge, axis=0, return_counts=True)
        a[np.linalg.norm(a[..., :3].astype(float) - cols[n.argmax()], axis=-1) <= KEY_TOL, 3] = 0
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "object.png")
        Image.fromarray(a).save(p)
        r = palette_report.report(p)
    hexes = [e[k]["hex"] for e in r["dominant"] for k in ("mean", "vivid")] + [e["vivid"]["hex"] for e in r["accents"]]
    return [rgb(h) for h in hexes]


def distance(cand, colours):
    d = [float(np.linalg.norm(rgb(cand) - c)) for c in colours]
    i = int(np.argmin(d))
    return d[i], palette_report.to_hex(colours[i]).upper()


def pick(concept, view_bg=None):
    colours = concept_colours(concept)
    if view_bg:
        d, near = distance(view_bg, colours)
        return {"hex": view_bg.upper(), "source": "profile", "min_dist": round(d, 1), "nearest": near}
    scored = [(c, *distance(c, colours)) for c in CANDIDATES]
    c, d, near = next((s for s in scored if s[1] >= MIN_DIST), max(scored, key=lambda s: s[1]))
    return {"hex": c, "source": "pick", "min_dist": round(d, 1), "nearest": near}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--concept", required=True)
    p.add_argument("--profile", required=True)
    a = p.parse_args()
    out = os.path.join(a.final, "bg_color.json")
    try:
        import yaml
        with open(a.profile, encoding="utf-8") as f:
            view_bg = ((yaml.safe_load(f) or {}).get("style") or {}).get("view_bg")
        r = pick(a.concept, view_bg)
    except Exception as e:  # noqa: BLE001
        print(f"[views/pick_bg] error {e!r}")
        sys.exit(2)
    os.makedirs(a.final, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    print(f"[views/pick_bg] {r['hex']} ({r['source']}, gần nhất {r['nearest']} cách {r['min_dist']}) -> {out}")


if __name__ == "__main__":
    main()
