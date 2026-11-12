"""VẼ MỚI steps 4 and 5 (docs/agents/texture-artist.md §4; checklist 17): project the painted views onto the UV.

Usage: python3 T/project_views.py --glb <locked GLB> --model M --views V/work/paint --base V/work/paint/base_fill.png
       --res N --out V/work/paint/projected.png [--padding 16]
Drawn from kit project_concept.py (orthographic projection, occlusion), with the cameras of render_paint_views.py instead
of a bbox fit to a concept, so 8 views of any angle work. The paintings are made one by one, so a texel takes one view:
  registration: each painting's object mask (its alpha, else the pixels away from its border colour) is compared with
    its guide's alpha. IoU under LIMITS["min_iou"] (a pixel within LIMITS["band_px"] of the other mask counts as
    matched, so thin parts and outlines are not penalised) or an offset (the shift of most overlap of the two masks)
    over LIMITS["max_shift_px"] rejects the view, so no background or neighbour material lands on the model.
  seen: a view sees a texel when the face looks at the camera (cos = n . back > MIN_COS), the point is the nearest
    surface there (the view's z-buffer, tolerance DEPTH_EPS of the asset size), every pixel within EDGE_PX shows that
    surface too (so no bilinear tap reads a nearer or farther one) and it lies inside the guide alpha shrunk by ERODE_PX.
  winner: per face the view of best cos; a face takes the view that wins its UV island (area x cos) when that view is
    within HYST of its best, so coplanar faces agree. A texel its winner does not see takes the best other view that
    sees it. Sampling is bilinear.
  feather: only texels within FEATHER_PX of another face's winner in the same UV island blend, by the share of each
    winner in that window. A texel taken by another view than its winner keeps that one view.
  texels no view sees take, in order: the mean of the seen texels of the same face; of the same material code and side
  (+X -X +Y -Y top bottom: the same normal direction); else the base fill.
A painting missing, of another aspect than its guide, or rejected is named in `redo`: paint only those views again.
Writes <out> and <out>.json (share of island texels per source, feather share, registration per view, skipped, redo).
Prints one line. Exit 0, 1 when a view is in `redo`, 2 on error.
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
import texture_complexity  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

MIN_COS = 0.2
DEPTH_EPS = 0.004
EDGE_PX = 1
ERODE_PX = 3
FEATHER_PX = 2
HYST = 0.05
LIMITS = {"min_iou": 0.9, "max_shift_px": 3, "band_px": 2}  # provisional until the pilot: the share of good paintings they reject


class Aspect(ValueError):
    pass


def project(cam, pts):
    m = np.asarray(cam["matrix"], float)
    right, up, back, t = m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3]
    rel = pts - t
    k = max(cam["w"], cam["h"]) / cam["ortho_scale"]
    px = cam["w"] / 2 + (rel @ right) * k
    py = cam["h"] / 2 - (rel @ up) * k
    return px, py, -(rel @ back), back


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


def rgba(path, size=None):
    """RGBA array; a paint view of the guide's aspect but another size is resized to the guide (Codex picks its size)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    if size and im.size != size:
        if abs(im.width / im.height - size[0] / size[1]) > 0.01:
            raise Aspect(f"{im.width}x{im.height} khác tỉ lệ guide {size[0]}x{size[1]}")
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, float)


def window(a, px, fn, fill):
    """fn (min or and) over the (2 px + 1)^2 window of each pixel; outside the image counts as fill."""
    out = a
    for axis in (0, 1):
        p = np.pad(out, [(px, px) if k == axis else (0, 0) for k in range(2)], constant_values=fill)
        n = out.shape[axis]
        out = fn.reduce([np.take(p, range(s, s + n), axis=axis) for s in range(2 * px + 1)])
    return out


def registration(paint, guide_alpha):
    """IoU of the painting's object mask with the guide alpha, a pixel within LIMITS["band_px"] of the other mask
    counting as matched, and the painting's offset [dx, dy] in px: the shift of most overlap, the mean of ties (a mask
    a pixel tighter than its guide overlaps it fully at -1, 0 and +1)."""
    pm, gm = texture_complexity.object_mask(paint), guide_alpha >= 128
    band = LIMITS["band_px"]
    miss = (pm & ~window(gm, band, np.logical_or, False)).sum() + (gm & ~window(pm, band, np.logical_or, False)).sum()
    iou = float(1 - miss / max((pm | gm).sum(), 1))
    h, w = pm.shape
    r = np.fft.rfft2(pm.astype(float), (2 * h, 2 * w)) * np.conj(np.fft.rfft2(gm.astype(float), (2 * h, 2 * w)))
    c = np.round(np.fft.irfft2(r, (2 * h, 2 * w)))
    dy, dx = np.nonzero(c == c.max())
    dy, dx = np.where(dy >= h, dy - 2 * h, dy), np.where(dx >= w, dx - 2 * w, dx)
    return iou, [int(np.round(dx.mean())), int(np.round(dy.mean()))]


def accepted(iou, off):
    return iou >= LIMITS["min_iou"] and max(map(abs, off)) <= LIMITS["max_shift_px"]


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x, y = np.clip(x - 0.5, 0, w - 1), np.clip(y - 0.5, 0, h - 1)
    x0, y0 = np.minimum(x.astype(int), w - 2), np.minimum(y.astype(int), h - 2)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx) * (1 - fy)
            + (img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx) * fy)


def islands(uv, f):
    """UV island of every face: faces joined through a shared UV point."""
    _, vid = np.unique(np.round(uv * 65536).astype(np.int64), axis=0, return_inverse=True)
    fv = vid.reshape(-1)[f]
    lab = np.arange(fv.max() + 1)
    while True:
        new = lab.copy()
        np.minimum.at(new, fv.reshape(-1), np.repeat(lab[fv].min(1), 3))
        new = new[new]
        if np.array_equal(new, lab):
            return lab[fv[:, 0]]
        lab = new


def winners(cos, area, isl):
    """Winner view per face (-1 when no view looks at it), cos (V, F)."""
    vis = cos > MIN_COS
    best = np.where(vis, cos, -np.inf).argmax(0)
    score = np.stack([np.bincount(isl, area * np.where(vis[k], cos[k], 0), isl.max() + 1) for k in range(len(cos))])
    dom = score.argmax(0)[isl]
    at = np.arange(cos.shape[1])
    take = vis[dom, at] & (cos[dom, at] >= cos[best, at] - HYST)
    return np.where(vis.any(0), np.where(take, dom, best), -1)


def shifted(a, dy, dx):
    """a[y + dy, x + dx], -1 outside."""
    out = np.full_like(a, -1)
    h, w = a.shape
    out[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)] = a[max(dy, 0):h - max(-dy, 0), max(dx, 0):w - max(-dx, 0)]
    return out


def feather(tm, src, win, isl, seen):
    """Texels that blend and their weights (n, V); every other texel takes src alone. A texel of a face's winner within
    FEATHER_PX of another face's winner in the same island blends the winners there."""
    ins = tm.inside
    srcmap, islmap = np.full(ins.shape, -1), np.full(ins.shape, -1)
    srcmap[ins], islmap[ins] = np.where(src == win, src, -1), isl[tm.face[ins]]
    offs = [(dy, dx) for dy in range(-FEATHER_PX, FEATHER_PX + 1) for dx in range(-FEATHER_PX, FEATHER_PX + 1)]
    band = np.zeros(ins.shape, bool)
    for dy, dx in offs:
        ns = shifted(srcmap, dy, dx)
        band |= (srcmap >= 0) & (ns >= 0) & (ns != srcmap) & (shifted(islmap, dy, dx) == islmap)
    idx = np.full(ins.shape, -1)
    idx[ins] = np.arange(len(src))
    by, bx = np.nonzero(band)
    cnt = np.zeros((len(by), len(seen)))
    for dy, dx in offs:
        ns, ni = shifted(srcmap, dy, dx)[by, bx], shifted(islmap, dy, dx)[by, bx]
        ok = (ns >= 0) & (ni == islmap[by, bx])
        np.add.at(cnt, (np.flatnonzero(ok), ns[ok]), 1)
    t = idx[by, bx]
    cnt *= np.stack([s[t] for s in seen], 1)
    keep = cnt.sum(1) > 0
    return t[keep], cnt[keep] / cnt[keep].sum(1, keepdims=True)


def run(a):
    codes, g = id_map.face_codes(a.model, a.glb)
    tm = tex.TexelMap(g["v"], g["f"], g["uv"], a.res)
    ins = tm.inside
    pos, face = tm.pos[ins], tm.face[ins]
    fn = tex.face_normals(g["v"], g["f"])
    area = np.linalg.norm(np.cross(g["v"][g["f"][:, 1]] - g["v"][g["f"][:, 0]], g["v"][g["f"][:, 2]] - g["v"][g["f"][:, 0]]),
                          axis=1) / 2
    diag = float(np.linalg.norm(g["v"].max(0) - g["v"].min(0)))
    views = json.load(open(os.path.join(a.views, "cameras.json"), encoding="utf-8"))["views"]
    used, skipped, reg = [], {}, {}
    for vw in views:
        name, cam = vw["paint"], vw["camera"]
        path = os.path.join(a.views, name)
        if not os.path.isfile(path):
            skipped[name] = "thiếu file"
            continue
        try:
            img = rgba(path, (cam["w"], cam["h"]))
        except Aspect as e:
            skipped[name] = str(e)
            continue
        alpha = rgba(os.path.join(a.views, vw["guide"]))[..., 3]
        iou, off = registration(img, alpha)
        reg[name] = {"iou": round(iou, 4), "offset_px": off}
        if not accepted(iou, off):
            skipped[name] = f"lệch guide: IoU {iou:.2f}, dời {off[0]},{off[1]} px"
            continue
        mask = window(alpha >= 128, ERODE_PX, np.logical_and, False)
        if (img[..., 3] < 250).any():
            mask &= img[..., 3] >= 128
        px, py, depth, back = project(cam, pos)
        xi, yi = np.clip(px.astype(int), 0, cam["w"] - 1), np.clip(py.astype(int), 0, cam["h"] - 1)
        cosf = fn @ back
        c = np.clip(cosf[face], MIN_COS, 1)
        tol = DEPTH_EPS * diag + 2 * EDGE_PX * cam["ortho_scale"] / max(cam["w"], cam["h"]) * np.sqrt(1 - c ** 2) / c
        z = zbuffer(cam, g["v"], g["f"])
        near, far = window(z, EDGE_PX, np.minimum, np.inf)[yi, xi], window(z, EDGE_PX, np.maximum, -np.inf)[yi, xi]
        seen = (cosf[face] > MIN_COS) & (depth <= near + tol) & (far <= depth + tol) & mask[yi, xi]
        used.append((vw, cosf, seen, img[..., :3].astype(np.uint8)))
    src, band, bw = np.full(len(pos), -1), np.zeros(0, int), np.zeros((0, 0))
    if used:
        isl = islands(g["uv"], g["f"])
        win = winners(np.stack([u[1] for u in used]), area, isl)[face]
        best = np.full(len(pos), -np.inf)
        for k, (_, cosf, seen, _) in enumerate(used):
            sc = np.where(seen, cosf[face] + 2.0 * (win == k), -np.inf)
            src, best = np.where(sc > best, k, src), np.maximum(sc, best)
        band, bw = feather(tm, src, win, isl, [u[2] for u in used])
    acc = np.zeros((len(pos), 3))
    for k, (vw, _, _, img) in enumerate(used):
        wk = (src == k).astype(np.float32)
        wk[band] = bw[:, k]
        t = np.flatnonzero(wk > 0)
        px, py, _, _ = project(vw["camera"], pos[t])
        acc[t] += wk[t, None] * bilinear(img, px, py)
    side = tex.side_of(tm.nrm[ins])
    cs = np.array([f"{codes[fc]}|{s}" for fc, s in zip(face, side)])
    out = np.where((src >= 0)[:, None], acc, np.nan)
    source = np.where(src >= 0, "projected", "")
    seen = src >= 0
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
    return {"views": len(used), "of": len(views), "share": share,
            "feather_share": round(float(((bw > 0).sum(1) > 1).sum() / len(pos)), 4), "registration": reg, "skipped": skipped,
            "redo": [v["paint"] for v in views if v["paint"] in skipped]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--glb", "--model", "--views", "--base", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--res", type=int, required=True)
    p.add_argument("--padding", type=int, default=16)
    a = p.parse_args()
    try:
        r = run(a)
    except Exception as e:  # noqa: BLE001
        print(f"[project_views] error: {e!r}")
        sys.exit(2)
    json.dump(r, open(os.path.splitext(a.out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    share = r["share"]
    skip = "".join(f"; bỏ {k} ({v})" for k, v in r["skipped"].items())
    redo = f"; gen lại {', '.join(r['redo'])} rồi chạy lại" if r["redo"] else ""
    print(f"[project_views] {r['views']}/{r['of']} view; chiếu {share['projected']:.0%}, mặt {share['face']:.0%}, "
          f"mã+hướng {share['code_side']:.0%}, nền {share['base']:.0%}{skip}{redo} -> {a.out}")
    sys.exit(1 if r["redo"] else 0)


if __name__ == "__main__":
    require_root()
    main()
