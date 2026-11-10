"""Simple or not: the five numbers of docs/agents/texture-artist.md §2.1 (D10), and the proposed mode (D30.11).

Usage: python3 T/texture_complexity.py --final F --blockout B --concept C --views-rest VR --profile <profile> \
         --mode meshy|paint
  1 materials       codes in B/sources.json `materials`
  2 colour clusters palette_report (kit) clusters with share >= CLUSTER_SHARE on the concept albedo object pixels
                    (alpha when the image has one, else pixels away from the border colour by > BG_DIST)
  3 detail density  mean gradient of the object pixels, 0..1 (shown only, never decides)
  4 motif           card real_texture_only_notes and the TEXTURE NOTE section of VR/README.md name a motif, text, sign (whole words)
  5 tier            card tier
Simple when materials <= texture_simple.max_materials, clusters <= texture_simple.max_color_clusters, no motif, tier not
hero. `simple` is information only (D30.11): the proposed mode is --mode, the mode the Producer script chose from the
Meshy key and budget (brief line `MODE: Meshy SỬA` = meshy, `MODE: VẼ MỚI` = paint).
Writes F/texture_spec.json {scores, thresholds, simple, proposed, used: null, reason: null}; the worker fills `used` and
`reason`. Prints one line. Exit 0, 2 on error.
"""
import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

CLUSTER_SHARE = 0.03
BG_DIST = 40.0
MOTIF = re.compile(r"\b(hoa văn|chữ|biển|motif|logo|họa tiết|pattern|text|sign)\b", re.I)


def object_pixels(path):
    from PIL import Image
    im = np.asarray(Image.open(path).convert("RGBA"), float)
    if (im[..., 3] < 250).any():
        return im, im[..., 3] >= 128
    rgb = im[..., :3]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    return im, np.linalg.norm(rgb - np.median(border, 0), axis=-1) > BG_DIST


def clusters(path):
    import palette_report
    from PIL import Image
    im, mask = object_pixels(path)
    im[..., 3] = np.where(mask, 255, 0)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "object.png")
        Image.fromarray(im.astype(np.uint8)).save(p)
        r = palette_report.report(p, n_colors=12)
    gray = im[..., :3].mean(-1)
    grad = np.hypot(*np.gradient(gray))[mask]
    return sum(e["share"] >= CLUSTER_SHARE for e in r["dominant"]), round(float(np.clip(grad.mean() / 64, 0, 1)), 3)


def section(path, key):
    if not os.path.isfile(path):
        return []
    out, on = [], False
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.lstrip().startswith("#"):
            on = key.lower() in line.lower()
        elif on and line.strip():
            out.append(line.strip().lstrip("-* ").strip())
    return out


def score(a, mode):
    import yaml
    card = yaml.safe_load(open(os.path.join(a.concept, "asset-card.yaml"), encoding="utf-8")) or {}
    prof = yaml.safe_load(open(a.profile, encoding="utf-8")) or {}
    th = prof.get("texture_simple") or {}
    mats = json.load(open(os.path.join(a.blockout, "sources.json"), encoding="utf-8")).get("materials") or []
    n_clusters, density = clusters(os.path.join(a.concept, "concept_albedo.png"))
    notes = [str(x) for x in card.get("real_texture_only_notes") or []] + section(
        os.path.join(a.views_rest, "README.md"), "TEXTURE NOTE")
    motif = [n for n in notes if MOTIF.search(n)]
    tier = card.get("tier") or "standard"
    scores = {"materials": len(mats), "color_clusters": int(n_clusters), "detail_density": density,
              "motif": motif, "tier": tier}
    simple = (len(mats) <= th.get("max_materials", 2) and n_clusters <= th.get("max_color_clusters", 6) and not motif
              and tier != "hero")
    return {"scores": scores, "thresholds": {"max_materials": th.get("max_materials", 2),
                                             "max_color_clusters": th.get("max_color_clusters", 6)},
            "simple": bool(simple), "proposed": mode, "used": None, "reason": None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--final", "--blockout", "--concept", "--views-rest", "--profile"):
        p.add_argument(k, required=True)
    p.add_argument("--mode", required=True, choices=("meshy", "paint"))
    a = p.parse_args()
    try:
        r = score(a, a.mode)
    except Exception as e:  # noqa: BLE001
        print(f"[texture_complexity] error: {e!r}")
        sys.exit(2)
    out = os.path.join(a.final, "texture_spec.json")
    os.makedirs(a.final, exist_ok=True)
    json.dump(r, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    s = r["scores"]
    print(f"[texture_complexity] {'đơn giản' if r['simple'] else 'phức tạp'} → {r['proposed']} (vật liệu "
          f"{s['materials']}, cụm màu {s['color_clusters']}, motif {len(s['motif'])}, hạng {s['tier']}) -> {out}")


if __name__ == "__main__":
    main()
