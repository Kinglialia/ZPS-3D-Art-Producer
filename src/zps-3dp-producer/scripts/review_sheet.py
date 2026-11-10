#!/usr/bin/env python3
"""Review sheet of one version (D31.1): `review_sheet.py <vN> <out.png> <glob> [<glob> ...]`.
The globs (pipeline.toml `sheet`, relative to the version folder) pick the step's renders, in that order, each file once.
One PNG grid, long edge about LONG_EDGE px, each tile labelled with the file stem. <out>.json lists
{label: path relative to vN}, which `P ingest` reads to serve a reviewer's need_evidence from disk.
Prints one line. Exit 0, 2 when no file matches."""
from __future__ import annotations

import json
import math
import sys
import unicodedata
from pathlib import Path

from root_guard import require_root

LONG_EDGE = 2048
PAD, HEAD = 8, 22
FONT = Path(__file__).resolve().parents[1] / "fonts" / "NotoSans-Regular.ttf"
FONT_SIZE = 15


def files(vd: Path, globs: list[str]) -> list[Path]:
    out = []
    for g in globs:
        for p in sorted(vd.glob(g)):
            if p.is_file() and p.suffix.lower() == ".png" and p not in out:
                out.append(p)
    return out


def labels(vd: Path, paths: list[Path]) -> dict[str, str]:
    """File stem; a stem seen twice gets its parent folder in front, so every label names one file."""
    stems = [p.stem for p in paths]
    return {(p.stem if stems.count(p.stem) == 1 else f"{p.parent.name}/{p.stem}"): str(p.relative_to(vd)) for p in paths}


def font():
    from PIL import ImageFont
    return ImageFont.truetype(str(FONT), FONT_SIZE) if FONT.is_file() else ImageFont.load_default()


def text(s: str) -> str:
    return s if FONT.is_file() else unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def make(vd: Path, out: Path, globs: list[str]) -> dict[str, str]:
    from PIL import Image, ImageDraw
    paths = files(vd, globs)
    if not paths:
        raise ValueError(f"không có ảnh nào khớp {', '.join(globs)} trong {vd}")
    tiles = labels(vd, paths)
    n = len(paths)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell = (LONG_EDGE - PAD) // cols - PAD
    w, h = PAD + cols * (cell + PAD), PAD + rows * (HEAD + cell + PAD)
    sheet = Image.new("RGB", (w, h), "white")
    d, f = ImageDraw.Draw(sheet), font()
    for i, (label, rel) in enumerate(tiles.items()):
        x, y = PAD + (i % cols) * (cell + PAD), PAD + (i // cols) * (HEAD + cell + PAD)
        with Image.open(vd / rel) as im:
            im = im.convert("RGBA")
            im.thumbnail((cell, cell))
            tile = Image.new("RGB", (cell, cell), "white")
            tile.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2), im)
        d.text((x, y), text(label), fill="black", font=f)
        sheet.paste(tile, (x, y + HEAD))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    out.with_suffix(".json").write_text(json.dumps(tiles, ensure_ascii=False, indent=1), encoding="utf-8")
    return tiles


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    vd, out, globs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    try:
        tiles = make(vd, out, globs)
    except (OSError, ValueError) as e:
        print(f"[review_sheet] error {e}")
        sys.exit(2)
    print(f"[review_sheet] {len(tiles)} ô -> {out}")


if __name__ == "__main__":
    require_root()
    main()
