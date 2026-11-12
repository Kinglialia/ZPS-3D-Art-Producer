"""Paint views of the texkit box without Blender: the cameras of render_paint_views.py (render_texture.ortho), a guide
whose alpha is the box silhouette by the projection math of project_views.py, and a painting that is one flat colour
inside that silhouette on a white background, as a painter who follows the guide exactly would give it."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import glbkit
from texkit import TOOLS

sys.path.insert(0, str(TOOLS / "lib"))
sys.path.insert(0, str(TOOLS))
import project_views  # noqa: E402
import render_texture  # noqa: E402

W, H = 768, 512
BG = (255, 255, 255)
EIGHT = [(k, 45 * k, (30, -30)[k % 2]) for k in range(8)]


def paint_dir(d: Path, views, colours, shift=None, missing=(), base=(90, 90, 90), res=128, mesh=None):
    """views: [(k, azimuth, elevation)]; colours {k: rgb}; shift {k: (dx, dy)} px of the painting against its guide;
    mesh (v, f), the box by default."""
    v, f = mesh or (lambda b: (b[0], b[2]))(glbkit.box())
    d.mkdir(parents=True, exist_ok=True)
    recs = []
    for k, az, el in views:
        cam = render_texture.ortho(v, render_texture.camera_dir(az, el), None, W, H)
        mask = np.isfinite(project_views.zbuffer(cam, v, f))
        guide = np.zeros((H, W, 4), np.uint8)
        guide[mask] = (128, 128, 128, 255)
        Image.fromarray(guide).save(d / f"guide_{k}.png")
        dx, dy = (shift or {}).get(k, (0, 0))
        moved = np.roll(mask, (dy, dx), (0, 1))
        if k not in missing:
            Image.fromarray(np.where(moved[..., None], colours[k], BG).astype(np.uint8)).save(d / f"paint_{k}.png")
        recs.append({"k": k, "azimuth_deg": az, "elevation_deg": el, "guide": f"guide_{k}.png", "paint": f"paint_{k}.png",
                     "camera": cam})
    (d / "cameras.json").write_text(json.dumps({"views": recs}), encoding="utf-8")
    Image.new("RGB", (res, res), base).save(d / "base_fill.png")
    return d
