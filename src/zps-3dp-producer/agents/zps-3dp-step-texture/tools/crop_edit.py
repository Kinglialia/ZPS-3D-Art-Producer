"""Repair by crop (docs/agents/texture-artist.md §5; checklist 18): cut a region of the atlas, paste Codex's edit back.

Usage:
  python3 T/crop_edit.py cut --albedo A --box x0,y0,x1,y1 [--margin 32] --out V/work/crops/<k>
  python3 T/crop_edit.py paste --albedo A --crop V/work/crops/<k> --edited <png> --out A2 [--feather 8]
cut: the crop is the box plus the margin, clamped to the atlas; its long side must be <= 1024 px (else split the
region). Writes <out>/crop.png, <out>/send.png (the crop scaled so its long side is SEND_LONG px, because
gen_image_codex.py needs a long side over 1040 px) and <out>/crop.json {box, crop, send}. Codex gets send.png.
paste: the edited image must have send.png's size; it is scaled back to the crop. Only pixels inside the box change,
blended with a weight that
rises from 0 at the box edge to 1 at --feather px inside; then every pixel outside the box is compared with A and must
be equal, else nothing is written. Writes <out>.json next to A2. Prints one line. Exit 0, 1 refused, 2 error.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

MAX_SIDE = 1024
SEND_LONG = 1536


def cut(a):
    im = Image.open(a.albedo).convert("RGB")
    x0, y0, x1, y1 = map(int, a.box.split(","))
    c = [max(0, x0 - a.margin), max(0, y0 - a.margin), min(im.width, x1 + a.margin), min(im.height, y1 + a.margin)]
    if max(c[2] - c[0], c[3] - c[1]) > MAX_SIDE:
        return 1, f"vùng {c[2] - c[0]}x{c[3] - c[1]} px > {MAX_SIDE}: chia nhỏ vùng"
    os.makedirs(a.out, exist_ok=True)
    crop = im.crop(c)
    crop.save(os.path.join(a.out, "crop.png"))
    k = SEND_LONG / max(crop.size)
    send = (round(crop.width * k), round(crop.height * k))
    crop.resize(send, Image.LANCZOS).save(os.path.join(a.out, "send.png"))
    json.dump({"albedo": os.path.abspath(a.albedo), "box": [x0, y0, x1, y1], "crop": c, "send": list(send)},
              open(os.path.join(a.out, "crop.json"), "w"), indent=1)
    return 0, f"crop {c[2] - c[0]}x{c[3] - c[1]}, gửi {send[0]}x{send[1]} -> {a.out}/send.png"


def paste(a):
    meta = json.load(open(os.path.join(a.crop, "crop.json")))
    base = np.asarray(Image.open(a.albedo).convert("RGB"), float)
    ed = Image.open(a.edited).convert("RGB")
    (cx0, cy0, cx1, cy1), (x0, y0, x1, y1) = meta["crop"], meta["box"]
    if list(ed.size) != meta["send"]:
        return 1, f"ảnh sửa {ed.width}x{ed.height} khác ảnh gửi {meta['send'][0]}x{meta['send'][1]}: bỏ kết quả", None
    ed = ed.resize((cx1 - cx0, cy1 - cy0), Image.LANCZOS)
    out = base.copy()
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inner = np.minimum.reduce([xx - x0 + 0.5, x1 - xx - 0.5, yy - y0 + 0.5, y1 - yy - 0.5])
    w = np.clip(inner / max(a.feather, 1), 0, 1)[..., None]
    patch = np.asarray(ed, float)[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0]
    out[y0:y1, x0:x1] = (1 - w) * base[y0:y1, x0:x1] + w * patch
    outside = np.ones(base.shape[:2], bool)
    outside[y0:y1, x0:x1] = False
    changed = int((np.round(out) != base).any(-1)[outside].sum())
    if changed:
        return 1, f"{changed} pixel ngoài vùng sửa đổi: bỏ kết quả", None
    Image.fromarray(np.round(out).astype(np.uint8)).save(a.out)
    rec = {"box": meta["box"], "changed_inside": int((np.round(out) != base).any(-1)[~outside].sum()),
           "changed_outside": 0}
    return 0, f"dán {rec['changed_inside']} pixel trong vùng, 0 ngoài vùng -> {a.out}", rec


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--albedo", required=True); c.add_argument("--box", required=True)
    c.add_argument("--margin", type=int, default=32); c.add_argument("--out", required=True)
    s = sub.add_parser("paste")
    s.add_argument("--albedo", required=True); s.add_argument("--crop", required=True)
    s.add_argument("--edited", required=True); s.add_argument("--out", required=True)
    s.add_argument("--feather", type=int, default=8)
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
    main()
