"""Repair by crop (docs/agents/texture-artist.md §5; checklist 18): cut a region of the atlas, paste Codex's edit back.

Usage:
  python3 T/crop_edit.py cut --albedo A --box x0,y0,x1,y1 [--margin 32] --out V/work/crops/<k>
  python3 T/crop_edit.py paste --albedo A --crop V/work/crops/<k> --edited <png> --glb G --out A2 [--feather 8]
          [--padding 16]
cut: the crop is the box plus the margin, clamped to the atlas; its long side must be <= 1024 px (else split the
region). The crop is padded with the atlas round it to 3:2 or 2:3, whichever adds less, because the image tool returns
1536x1024 or 1024x1536; a pad that would leave the atlas moves inside it, and only an atlas smaller than the pad leaves
a band of the crop's mean colour. 1:1 is not offered: a 1024x1024 image fails the 1040 px long side of
gen_image_codex.py. Writes <out>/crop.png (the padded crop), <out>/send.png (it at 1536x1024 or 1024x1536) and
<out>/crop.json {box, crop, pad, send}. Codex gets send.png.
paste: the edited image may have any size of send.png's shape (1% tolerance); it is scaled to the pad. Outside the
box by more than --feather px nothing should change, so the mean RGB difference to crop.png there (the ring, at atlas
scale, where detail finer than a texel no longer counts) over LIMITS["ring_diff"] refuses the edit: it moved or redrew
the surroundings. Only pixels inside the box change, blended with a weight that rises from 0 at the box edge to 1 at --feather px inside; every
pixel outside the box is compared with A and must be equal, else nothing is written. Last, the gutter (non-island
texels of G's UV within --padding px of the box) is grown again from the new island colours (tex.gutter).
Writes <out>.json next to A2. Prints one line. Exit 0, 1 refused, 2 error.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

MAX_SIDE = 1024
SHAPES = {"3:2": ((3, 2), (1536, 1024)), "2:3": ((2, 3), (1024, 1536))}
LIMITS = {"ring_diff": 8.0}  # provisional until the pilot: mean RGB difference of a faithful Codex edit outside the box


def pad_box(c, size):
    """The padded box round crop c and its shape: the shape that adds less area, centred, moved inside the atlas."""
    w, h = c[2] - c[0], c[3] - c[1]
    fits = {}
    for name, ((a, b), _) in SHAPES.items():
        k = max(math.ceil(w / a), math.ceil(h / b))
        fits[name] = (a * k, b * k)
    name = min(fits, key=lambda n: fits[n][0] * fits[n][1])
    out = []
    for lo, n, full, limit in ((c[0], w, fits[name][0], size[0]), (c[1], h, fits[name][1], size[1])):
        start = lo - (full - n) // 2
        if full <= limit:
            start = min(max(start, 0), limit - full)
        out.append((start, start + full))
    return [out[0][0], out[1][0], out[0][1], out[1][1]], name


def cut(a):
    im = Image.open(a.albedo).convert("RGB")
    x0, y0, x1, y1 = map(int, a.box.split(","))
    c = [max(0, x0 - a.margin), max(0, y0 - a.margin), min(im.width, x1 + a.margin), min(im.height, y1 + a.margin)]
    if max(c[2] - c[0], c[3] - c[1]) > MAX_SIDE:
        return 1, f"vùng {c[2] - c[0]}x{c[3] - c[1]} px > {MAX_SIDE}: chia nhỏ vùng"
    p, shape = pad_box(c, im.size)
    src = np.asarray(im)
    fill = src[c[1]:c[3], c[0]:c[2]].reshape(-1, 3).mean(0).round().astype(np.uint8)
    padded = np.broadcast_to(fill, (p[3] - p[1], p[2] - p[0], 3)).copy()
    sx0, sy0, sx1, sy1 = max(p[0], 0), max(p[1], 0), min(p[2], im.width), min(p[3], im.height)
    padded[sy0 - p[1]:sy1 - p[1], sx0 - p[0]:sx1 - p[0]] = src[sy0:sy1, sx0:sx1]
    os.makedirs(a.out, exist_ok=True)
    Image.fromarray(padded).save(os.path.join(a.out, "crop.png"))
    send = SHAPES[shape][1]
    Image.fromarray(padded).resize(send, Image.LANCZOS).save(os.path.join(a.out, "send.png"))
    json.dump({"albedo": os.path.abspath(a.albedo), "box": [x0, y0, x1, y1], "crop": c, "pad": p, "send": list(send)},
              open(os.path.join(a.out, "crop.json"), "w"), indent=1)
    return 0, (f"crop {c[2] - c[0]}x{c[3] - c[1]}, đệm {p[2] - p[0]}x{p[3] - p[1]} ({shape}), gửi {send[0]}x{send[1]} "
               f"-> {a.out}/send.png")


def ring_diff(ed, crop, meta, feather):
    """Mean RGB difference of the edit to the padded crop outside the box grown by feather px, both at atlas scale."""
    (x0, y0, x1, y1), (px0, py0, _, _) = meta["box"], meta["pad"]
    yy, xx = np.mgrid[py0:py0 + crop.shape[0], px0:px0 + crop.shape[1]]
    ring = (xx < x0 - feather) | (xx >= x1 + feather) | (yy < y0 - feather) | (yy >= y1 + feather)
    return float(np.abs(ed - crop)[ring].mean()) if ring.any() else 0.0


def paste(a):
    meta = json.load(open(os.path.join(a.crop, "crop.json")))
    base = np.asarray(Image.open(a.albedo).convert("RGB"), float)
    ed = Image.open(a.edited).convert("RGB")
    sw, sh = meta["send"]
    (px0, py0, px1, py1), (x0, y0, x1, y1) = meta["pad"], meta["box"]
    if abs(ed.width / ed.height - sw / sh) > 0.01 * sw / sh:
        return 1, f"ảnh sửa {ed.width}x{ed.height} khác tỉ lệ ảnh gửi {sw}x{sh}: bỏ kết quả", None
    ed = np.asarray(ed.resize((px1 - px0, py1 - py0), Image.LANCZOS), float)
    crop = np.asarray(Image.open(os.path.join(a.crop, "crop.png")).convert("RGB"), float)
    ring = ring_diff(ed, crop, meta, a.feather)
    if ring > LIMITS["ring_diff"]:
        return 1, f"vùng quanh chỗ sửa bị dời hoặc đổi (lệch {ring:.0f} > {LIMITS['ring_diff']:.0f}): bỏ kết quả, gen lại", None
    out = base.copy()
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inner = np.minimum.reduce([xx - x0 + 0.5, x1 - xx - 0.5, yy - y0 + 0.5, y1 - yy - 0.5])
    w = np.clip(inner / max(a.feather, 1), 0, 1)[..., None]
    out[y0:y1, x0:x1] = (1 - w) * base[y0:y1, x0:x1] + w * ed[y0 - py0:y1 - py0, x0 - px0:x1 - px0]
    outside = np.ones(base.shape[:2], bool)
    outside[y0:y1, x0:x1] = False
    changed = int((np.round(out) != base).any(-1)[outside].sum())
    if changed:
        return 1, f"{changed} pixel ngoài vùng sửa đổi: bỏ kết quả", None
    inside = tex.load_map(a.glb, base.shape[1])[1].inside
    near = np.zeros(inside.shape, bool)
    near[max(y0 - a.padding, 0):y1 + a.padding, max(x0 - a.padding, 0):x1 + a.padding] = True
    grown = tex.gutter(np.round(out), inside, a.padding)
    gut = near & ~inside & (np.round(grown) != np.round(out)).any(-1)
    out[gut] = grown[gut]
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(a.out)
    rec = {"box": meta["box"], "changed_inside": int((np.round(out) != base).any(-1)[~outside].sum()),
           "changed_outside": 0, "gutter_refreshed": int(gut.sum()), "ring_diff": round(ring, 2)}
    return 0, (f"dán {rec['changed_inside']} pixel trong vùng, 0 ngoài vùng, gutter {rec['gutter_refreshed']} "
               f"-> {a.out}"), rec


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--albedo", required=True); c.add_argument("--box", required=True)
    c.add_argument("--margin", type=int, default=32); c.add_argument("--out", required=True)
    s = sub.add_parser("paste")
    s.add_argument("--albedo", required=True); s.add_argument("--crop", required=True)
    s.add_argument("--edited", required=True); s.add_argument("--glb", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--feather", type=int, default=8); s.add_argument("--padding", type=int, default=16)
    a = p.parse_args()
    try:
        if a.cmd == "cut":
            code, line = cut(a)
        else:
            code, line, rec = paste(a)
            json.dump({"status": "ok" if code == 0 else "refused", "note": line, **(rec or {})},
                      open(os.path.splitext(a.out)[0] + ".json", "w"), ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        print(f"[crop_edit] error: {e!r}")
        sys.exit(2)
    print(f"[crop_edit] {line}")
    sys.exit(code)


if __name__ == "__main__":
    require_root()
    main()
