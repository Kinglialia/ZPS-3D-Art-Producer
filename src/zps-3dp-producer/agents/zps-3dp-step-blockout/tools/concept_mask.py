"""Concept on a key-colour background -> mask the kit's raster.concept_mask reads as a mask file.

Usage: python3 tools/concept_mask.py --image <concept.png> --out <mask.png> [--key "#RRGGBB"] [--tol 40] [--border 4]
Background = every pixel within --tol (RGB distance) of the key colour, over the whole image, so
gaps between columns are background even when the image edge does not reach them. Transparent
pixels are background too. --key defaults to the most common colour on the image border.
Output: 8-bit grey PNG, object 255 on 0, with a black border of --border px (raster.concept_mask
treats a binary image with a dark border as white = object). Prints one line. Exit 0, 2 on error.
Replaces the kit's validate_concept.py, which needs optimize/optlib.py.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402


def key_colour(rgb):
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    cols, counts = np.unique(edge, axis=0, return_counts=True)
    return cols[counts.argmax()]


def mask(path, key=None, tol=40.0, border=4):
    im = Image.open(path)
    rgba = np.asarray(im.convert("RGBA"), np.int32)
    rgb = rgba[:, :, :3]
    k = np.array(key, np.int32) if key is not None else key_colour(rgb)
    bg = np.sqrt(((rgb - k) ** 2).sum(axis=2)) <= tol
    bg |= rgba[:, :, 3] < 128
    m = np.where(bg, 0, 255).astype(np.uint8)
    if border:
        m[:border], m[-border:], m[:, :border], m[:, -border:] = 0, 0, 0, 0
    return m, k


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--key")
    p.add_argument("--tol", type=float, default=40.0)
    p.add_argument("--border", type=int, default=4)
    a = p.parse_args()
    try:
        key = tuple(int(a.key.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if a.key else None
        m, k = mask(a.image, key, a.tol, a.border)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        Image.fromarray(m, "L").save(a.out)
    except Exception as e:  # noqa: BLE001
        print(f"[blockout/concept_mask] error {e!r}")
        sys.exit(2)
    hexk = "#" + "".join(f"{int(c):02X}" for c in k)
    print(f"[blockout/concept_mask] key={hexk} object={(m > 0).mean():.1%} -> {os.path.abspath(a.out)}")


if __name__ == "__main__":
    require_root()
    main()
