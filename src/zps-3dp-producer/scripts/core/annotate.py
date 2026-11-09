"""Regions the user marks on review images (docs/review-board.md §4): check them, draw them on the original image,
save the PNG and `regions.json` under `assets/<id>/feedback/<step>-v<N>-<k>/`."""
from __future__ import annotations

import json
from pathlib import Path

from .state import ASSETS, die, rel, write_atomic

SHAPES = ("circle", "rect", "free")
MAX_REGIONS, MAX_POINTS, MAX_NOTE = 50, 500, 500
RED, WHITE, GREY = (230, 30, 30), (255, 255, 255), (136, 136, 136, 255)


def unit(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


def check(regions, files: dict, card: str) -> list[dict]:
    """The regions as sent, or die. `image` is the name of an image on the card, never a path."""
    if not isinstance(regions, list) or not 1 <= len(regions) <= MAX_REGIONS:
        die(f"regions phải là danh sách 1–{MAX_REGIONS} vùng")
    out = []
    for k, r in enumerate(regions, 1):
        def bad(msg):
            die(f"vùng {k}: {msg}")
        if not isinstance(r, dict):
            bad("phải là {n, image, shape, coords, note}")
        if r.get("n") != k:
            bad(f"n phải là {k}")
        if not isinstance(r.get("image"), str) or r["image"] not in files:
            bad(f"ảnh '{str(r.get('image'))[:80]}' không có trên thẻ {card}")
        shape, c = r.get("shape"), r.get("coords")
        if shape not in SHAPES:
            bad("shape phải là " + "|".join(SHAPES))
        if shape == "free":
            if not (isinstance(c, list) and 2 <= len(c) <= MAX_POINTS
                    and all(isinstance(p, list) and len(p) == 2 and all(map(unit, p)) for p in c)):
                bad(f"free cần 2–{MAX_POINTS} điểm [x, y] trong 0–1")
        elif not (isinstance(c, list) and len(c) == 4 and all(map(unit, c)) and c[0] < c[2] and c[1] < c[3]):
            bad(f"coords của {shape} phải là [x0, y0, x1, y1] trong 0–1, x0 < x1, y0 < y1")
        note = r.get("note", "")
        if not isinstance(note, str) or len(note) > MAX_NOTE:
            bad(f"note phải là chuỗi tối đa {MAX_NOTE} ký tự")
        out.append({"n": k, "image": r["image"], "shape": shape, "coords": c, "note": note.strip()})
    return out


def draw(src: Path, marks: list[dict], out: Path):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        im = Image.alpha_composite(Image.new("RGBA", im.size, GREY), im.convert("RGBA"))
    im = im.convert("RGB")
    W, H = im.size
    w, r = max(3, round(max(W, H) / 250)), max(9, round(max(W, H) / 60))
    font = ImageFont.load_default(size=round(r * 1.3))
    d = ImageDraw.Draw(im)
    for m in marks:
        c = m["coords"]
        if m["shape"] == "free":
            pts = [(x * W, y * H) for x, y in c]
            d.line(pts, fill=RED, width=w, joint="curve")
            ax, ay = pts[0]
        else:
            box = (c[0] * W, c[1] * H, c[2] * W, c[3] * H)
            (d.ellipse if m["shape"] == "circle" else d.rectangle)(box, outline=RED, width=w)
            ax, ay = box[:2]
        d.ellipse((ax - r, ay - r, ax + r, ay + r), fill=RED)
        d.text((ax, ay), str(m["n"]), fill=WHITE, font=font, anchor="mm")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)


def save(aid: str, tag: str, marks: list[dict], files: dict) -> Path:
    """One folder per send: `<tag>-<k>`; one annotated PNG per marked image. Sets `png` on each mark."""
    base = ASSETS / aid / "feedback"
    d = base / f"{tag}-{1 + sum(p.is_dir() for p in base.glob(f'{tag}-*'))}"
    for name in dict.fromkeys(m["image"] for m in marks):
        png = d / (name.replace("/", "_").rsplit(".", 1)[0] + ".png")
        mine = [m for m in marks if m["image"] == name]
        draw(files[name], mine, png)
        for m in mine:
            m["png"] = rel(png)
    return d


def record(d: Path, marks: list[dict], ids: list[str]):
    """`regions.json` of the send; `id` is null when the regions did not become findings."""
    ids = ids or [None] * len(marks)
    write_atomic(d / "regions.json", json.dumps([{k: v for k, v in m.items() if k != "png"} | {"id": i}
                                                 for m, i in zip(marks, ids)], ensure_ascii=False, indent=1))
