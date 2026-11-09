"""VẼ MỚI steps 4 and 5 (docs/agents/texture-artist.md §4; checklist 17): project the painted views onto the UV.

Usage: python3 T/project_views.py --glb <locked GLB> --model M --views V/work/paint --base V/work/paint/base_fill.png
       --res N --out V/work/paint/projected.png [--padding 16]
Drawn from kit project_concept.py (orthographic projection, cos weights, occlusion), with the cameras of
render_paint_views.py instead of a bbox fit to a concept, so 8 views of any angle work:
  each texel's 3D point is projected into every view; a view counts when the face looks at the camera
  (cos = n . -d > MIN_COS), the point is the nearest surface there (the view's own z-buffer, tolerance DEPTH_EPS of the
  asset size) and the painted pixel is opaque (paint alpha, else guide alpha); weight cos^2.
  texels no view sees take, in order: the mean of the seen texels of the same face; of the same material code and side
  (+X -X +Y -Y top bottom: the same normal direction); else the base fill.
Writes <out> and <out>.json (share of island texels per source). Prints one line. Exit 0, 2 on error.
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

MIN_COS = 0.2
DEPTH_EPS = 0.004


def project(cam, pts):
    m = np.asarray(cam["matrix"], float)
    right, up, back, t = m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3]
    rel = pts - t
    s = cam["ortho_scale"]
    px = (rel @ right / s + 0.5) * cam["w"]
    py = (0.5 - rel @ up / s) * cam["h"]
    return px, py, -(rel @ back), -back


def zbuffer(cam, v, f):
    px, py, depth, _ = project(cam, v)
    w, h = cam["w"], cam["h"]
    z = np.full((h, w), np.inf)
    for a, b, c in f:
        xs, ys, ds = px[[a, b, c]] - 0.5, py[[a, b, c]] - 0.5, depth[[a, b, c]]
        x0, x1 = max(int(np.floor(xs.min())), 0), min(int(np.ceil(xs.max())), w - 1)
        y0, y1 = max(int(np.floor(ys.min())), 0), min(int(np.ceil(ys.max())), h - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-12:
            continue
        l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        dd = l0 * ds[0] + l1 * ds[1] + l2 * ds[2]
        sub = z[gy[ok], gx[ok]]
        z[gy[ok], gx[ok]] = np.minimum(sub, dd[ok])
    return z


def rgba(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"), float)


def run(a):
    codes, g = id_map.face_codes(a.model, a.glb)
    tm = tex.TexelMap(g["v"], g["f"], g["uv"], a.res)
    ins = tm.inside
    pos, nrm = tm.pos[ins], tm.nrm[ins]
    diag = float(np.linalg.norm(g["v"].max(0) - g["v"].min(0)))
    acc, wsum = np.zeros((len(pos), 3)), np.zeros(len(pos))
    views = json.load(open(os.path.join(a.views, "cameras.json"), encoding="utf-8"))["views"]
    for vw in views:
        paint = os.path.join(a.views, vw["paint"])
        if not os.path.isfile(paint):
            continue
        cam = vw["camera"]
        img, guide = rgba(paint), rgba(os.path.join(a.views, vw["guide"]))
        if img.shape[:2] != (cam["h"], cam["w"]):
            raise ValueError(f"{vw['paint']} {img.shape[1]}x{img.shape[0]} khác guide {cam['w']}x{cam['h']}")
        alpha = img[..., 3] if (img[..., 3] < 250).any() else guide[..., 3]
        px, py, depth, look = project(cam, pos)
        cos = nrm @ -look
        xi, yi = np.clip(px.astype(int), 0, cam["w"] - 1), np.clip(py.astype(int), 0, cam["h"] - 1)
        z = zbuffer(cam, g["v"], g["f"])
        seen = (cos > MIN_COS) & (depth <= z[yi, xi] + DEPTH_EPS * diag) & (alpha[yi, xi] >= 128)
        w = np.where(seen, cos ** 2, 0)
        acc += w[:, None] * img[yi, xi, :3]
        wsum += w
    face = tm.face[ins]
    side = tex.side_of(nrm)
    cs = np.array([f"{codes[fc]}|{s}" for fc, s in zip(face, side)])
    out = np.where(wsum[:, None] > 0, acc / np.maximum(wsum, 1e-9)[:, None], np.nan)
    source = np.where(wsum > 0, "projected", "")
    seen = wsum > 0
    for key, label in ((face, "face"), (cs, "code_side")):
        _, inv = np.unique(key, return_inverse=True)
        cnt = np.bincount(inv, seen)
        mean = np.stack([np.bincount(inv, np.where(seen, out[:, k], 0)) for k in range(3)], 1) / np.maximum(cnt, 1)[:, None]
        take = (source == "") & (cnt[inv] > 0)
        out[take], source[take] = mean[inv[take]], label
        seen = source != ""
    base = tex.load_rgb(a.base, a.res)[ins]
    take = source == ""
    out[take], source[take] = base[take], "base"
    img = np.zeros((a.res, a.res, 3))
    img[ins] = out
    tex.save_rgb(tex.gutter(img, ins, a.padding), a.out)
    share = {k: round(float((source == k).mean()), 4) for k in ("projected", "face", "code_side", "base")}
    return share, len([v for v in views if os.path.isfile(os.path.join(a.views, v["paint"]))])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--glb", "--model", "--views", "--base", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    a = p.parse_args()
    try:
        share, n = run(a)
    except Exception as e:  # noqa: BLE001
        print(f"[project_views] error: {e!r}")
        sys.exit(2)
    json.dump({"views": n, "share": share}, open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"[project_views] {n} view; chiếu {share['projected']:.0%}, mặt {share['face']:.0%}, "
          f"mã+hướng {share['code_side']:.0%}, nền {share['base']:.0%} -> {a.out}")


if __name__ == "__main__":
    main()
