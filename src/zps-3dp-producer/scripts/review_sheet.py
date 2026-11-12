#!/usr/bin/env python3
"""Review sheet of one version (D31.1, D38.5): `review_sheet.py <vN> <out.png> <glob> [<glob> ...]`.
The globs (pipeline.toml `sheet`, relative to the version folder) pick the step's renders, in that order, each file once.
A glob may start with a mode: `native:` shows the image at its true size (a larger one is cut to the cell, never scaled);
`crop:` adds a tile with the 1:1 window of CROP_PX px around the middle of what the image draws, saved to
<out stem>-crops/<stem>_crop.png.
At most MAX_TILES tiles go on one page. More tiles give further pages <out stem>-<n>.png (n from 2), of equal size
and in glob order. Each page is a grid with the largest cell that keeps the long edge at LONG_EDGE px, and each tile
is labelled with the file stem. <out>.json lists {label: {src, page, box}}: the file relative to vN, the page file
relative to vN and the tile box [x0, y0, x1, y1] on that page. `P ingest` reads it to serve a reviewer's need_evidence
from disk by label. Prints one line. Exit 0, 2 when no file matches."""
from __future__ import annotations

import json
import math
import sys
import unicodedata
from pathlib import Path

from root_guard import require_root

LONG_EDGE = 1568
MAX_TILES = 8
CELL_MAX = 768
CROP_PX = 480
PAD, HEAD = 8, 22
FONT = Path(__file__).resolve().parents[1] / "fonts" / "NotoSans-Regular.ttf"
FONT_SIZE = 15
MODES = ("native", "crop")
BACKGROUND_DELTA = 12


def split_mode(glob: str) -> tuple[str, str]:
    mode, sep, rest = glob.partition(":")
    return (mode, rest) if sep and mode in MODES else ("", glob)


def labels(vd: Path, paths: list[Path]) -> dict[str, str]:
    """File stem; a stem seen twice gets its parent folder in front, so every label names one file."""
    stems = [p.stem for p in paths]
    return {(p.stem if stems.count(p.stem) == 1 else f"{p.parent.name}/{p.stem}"): str(p.relative_to(vd)) for p in paths}


def font():
    from PIL import ImageFont
    return ImageFont.truetype(str(FONT), FONT_SIZE) if FONT.is_file() else ImageFont.load_default()


def text(s: str) -> str:
    return s if FONT.is_file() else unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def center_crop(im, size: int):
    """The size x size window (or the whole image when it is smaller) around the middle of what differs from the corner
    colour: the wire of an asset, not the empty margin."""
    from PIL import Image, ImageChops
    rgb = im.convert("RGB")
    mask = ImageChops.difference(rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))).convert("L").point(
        lambda v: 255 if v > BACKGROUND_DELTA else 0)
    x0, y0, x1, y1 = mask.getbbox() or (0, 0, *rgb.size)
    w, h = min(size, rgb.width), min(size, rgb.height)
    left = min(max((x0 + x1) // 2 - w // 2, 0), rgb.width - w)
    top = min(max((y0 + y1) // 2 - h // 2, 0), rgb.height - h)
    return rgb.crop((left, top, left + w, top + h))


def tiles_of(vd: Path, out: Path, globs: list[str]) -> list[tuple[str, str, str]]:
    """(label, file relative to vN, mode) in glob order. A crop is written to disk here, so the label serves like any tile."""
    from PIL import Image
    seen, order = set(), []
    for g in globs:
        mode, pat = split_mode(g)
        for p in sorted(vd.glob(pat)):
            if p.is_file() and p.suffix.lower() == ".png" and (mode, p) not in seen:
                seen.add((mode, p))
                order.append((mode, p))
    names = labels(vd, list(dict.fromkeys(p for _, p in order)))
    by_path = {vd / rel: label for label, rel in names.items()}
    crops = out.parent / f"{out.stem}-crops"
    result = []
    for mode, p in order:
        label = by_path[p]
        if mode != "crop":
            result.append((label, str(p.relative_to(vd)), mode))
            continue
        dst = crops / (label.replace("/", "_") + "_crop.png")
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(p) as im:
            center_crop(im, CROP_PX).save(dst)
        result.append((label + "_crop", str(dst.relative_to(vd)), "native"))
    return result


def pages_of(n: int) -> list[int]:
    """Tiles per page: as few pages as MAX_TILES allows, sizes within one of each other."""
    k = math.ceil(n / MAX_TILES)
    return [n // k + (i < n % k) for i in range(k)]


def grid(n: int) -> tuple[int, int, int]:
    """(columns, rows, cell) with the largest cell whose page stays inside LONG_EDGE both ways."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        cell = min(CELL_MAX, (LONG_EDGE - PAD) // cols - PAD, (LONG_EDGE - PAD) // rows - HEAD - PAD)
        if best is None or cell > best[2]:
            best = (cols, rows, cell)
    return best


def page_path(out: Path, k: int) -> Path:
    return out if k == 1 else out.with_name(f"{out.stem}-{k}{out.suffix}")


def tile_image(im, cell: int, mode: str):
    from PIL import Image
    im = im.convert("RGBA")
    if mode == "native":
        left, top = max((im.width - cell) // 2, 0), max((im.height - cell) // 2, 0)
        im = im.crop((left, top, left + min(cell, im.width), top + min(cell, im.height)))
    else:
        im.thumbnail((cell, cell))
    tile = Image.new("RGB", (cell, cell), "white")
    tile.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2), im)
    return tile


def make(vd: Path, out: Path, globs: list[str]) -> dict[str, str]:
    from PIL import Image, ImageDraw
    for old in out.parent.glob(f"{out.stem}-[0-9]*{out.suffix}"):
        old.unlink()
    tiles = tiles_of(vd, out, globs)
    if not tiles:
        raise ValueError(f"không có ảnh nào khớp {', '.join(globs)} trong {vd}")
    f = font()
    placed, start = {}, 0
    out.parent.mkdir(parents=True, exist_ok=True)
    for k, count in enumerate(pages_of(len(tiles)), 1):
        cols, rows, cell = grid(count)
        page = Image.new("RGB", (PAD + cols * (cell + PAD), PAD + rows * (HEAD + cell + PAD)), "white")
        d, dst = ImageDraw.Draw(page), page_path(out, k)
        for i, (label, rel, mode) in enumerate(tiles[start:start + count]):
            x, y = PAD + (i % cols) * (cell + PAD), PAD + (i // cols) * (HEAD + cell + PAD)
            with Image.open(vd / rel) as im:
                tile = tile_image(im, cell, mode)
            d.text((x, y), text(label), fill="black", font=f)
            page.paste(tile, (x, y + HEAD))
            placed[label] = {"src": rel, "page": str(dst.relative_to(vd)), "box": [x, y + HEAD, x + cell, y + HEAD + cell]}
        page.save(dst)
        start += count
    out.with_suffix(".json").write_text(json.dumps(placed, ensure_ascii=False, indent=1), encoding="utf-8")
    return {label: t["src"] for label, t in placed.items()}


def pages(out: Path) -> list[Path]:
    """The page files of a sheet that `make` wrote, first page first."""
    try:
        placed = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [out]
    names = list(dict.fromkeys(t["page"] for t in placed.values()))
    return [out.with_name(Path(n).name) for n in names] or [out]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    vd, out, globs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    try:
        tiles = make(vd, out, globs)
    except (OSError, ValueError) as e:
        print(f"[review_sheet] error {e}")
        sys.exit(2)
    print(f"[review_sheet] {len(tiles)} ô, {len(pages(out))} trang -> {out}")


if __name__ == "__main__":
    require_root()
    main()
