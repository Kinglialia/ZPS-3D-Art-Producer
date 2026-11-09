"""Numpy-only orthographic silhouettes and IoU. One implementation shared by gate1, measure,
assembly and param_fit, so every IoU in the pipeline is computed the same way.

Coordinates: Blender convention, Z up, front of the prop faces -Y.
A view direction is the direction the camera LOOKS (from camera to object).
"""
import math

import numpy as np

# Direction each camera LOOKS. The prop faces -Y, so the front camera stands at -Y looking +Y.
# A concept "left view" shows the object's own left side; facing -Y, its left hand is at +X,
# so the left camera stands at +X looking -X.
VIEW_DIRS = {
    "front": (0.0, 1.0, 0.0),
    "back": (0.0, -1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "top": (0.0, 0.0, -1.0),
    "bottom": (0.0, 0.0, 1.0),
    "34": (-0.6124, 0.6124, -0.5),   # front-left, 30° down: camera at (+X,-Y,+Z)
}


def camera_dir(azimuth_deg, elevation_deg):
    """Direction an orthographic camera looks. azimuth 0 = camera in front (-Y) looking +Y;
    positive azimuth moves the camera toward +X (the prop's right); elevation = degrees above
    the horizon. camera_dir(45, 30) == VIEW_DIRS["34"]."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return (-math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), -math.sin(el))


def view_dir(label, cameras=None):
    """View direction for a concept label; spec concept.cameras[label] (azimuth_deg,
    elevation_deg) overrides the built-in VIEW_DIRS. Painted concepts rarely sit at exactly
    45/30, so the 34 view usually needs one (see assembly.py --fit-camera)."""
    c = (cameras or {}).get(label)
    if c:
        return camera_dir(c.get("azimuth_deg", 45.0), c.get("elevation_deg", 30.0))
    return VIEW_DIRS[label]


def _basis(d):
    """Right and up image axes for a camera looking along d (unit)."""
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    world_up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(d, world_up)) > 0.99:
        world_up = np.array([0.0, 1.0, 0.0]) if d[2] < 0 else np.array([0.0, -1.0, 0.0])
    right = np.cross(d, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, d)
    return right, up


def sphere_dirs(n):
    """n view directions roughly uniform on the sphere (Fibonacci), includes above and below."""
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(max(0.0, 1 - z * z))
        th = golden * i
        out.append((rad * math.cos(th), rad * math.sin(th), z))
    return out


def project(verts, d):
    right, up = _basis(d)
    v = np.asarray(verts, float)
    return np.stack([v @ right, v @ up], axis=1)


def silhouette(verts, faces, d, size=512, frame=None, margin=0.02):
    """Boolean mask (size x size, row 0 = top) of the mesh seen orthographically along d.

    frame: (umin, umax, vmin, vmax) in projected units; when None, the mesh's own bbox is
    fitted into the square with `margin`, aspect preserved. To compare two meshes, build the
    frame with union_frame([project(a, d), project(b, d)]) and pass it to both; a frame fitted
    to one mesh clips the other at the border and inflates IoU. Returns (mask, frame).
    """
    p = project(verts, d)
    if frame is None:
        frame = fit_frame(p, margin)
    umin, umax, vmin, vmax = frame
    scale = (size - 1) / max(umax - umin, vmax - vmin)
    px = (p[:, 0] - umin) * scale
    py = (vmax - p[:, 1]) * scale
    mask = np.zeros((size, size), dtype=bool)
    tri = np.asarray(faces, dtype=np.int64)
    _raster_tris(mask, px, py, tri)
    return mask, frame


def fit_frame(p, margin=0.02):
    umin, vmin = p.min(0)
    umax, vmax = p.max(0)
    span = max(umax - umin, vmax - vmin) * (1 + 2 * margin)
    cu, cv = (umin + umax) / 2, (vmin + vmax) / 2
    return (cu - span / 2, cu + span / 2, cv - span / 2, cv + span / 2)


def union_frame(p_list, margin=0.02):
    return fit_frame(np.concatenate(p_list, axis=0), margin)


_BATCH_SIZES = (4, 8, 16, 32)   # triangles whose pixel bbox fits in B x B are rasterised in batches
_BATCH_CELLS = 1 << 20          # pixel tests per batch (bounds memory)


def _raster_tris(mask, px, py, tri):
    """Fill mask with every triangle. A pixel is inside when its centre has all barycentric
    weights >= -1e-6; a triangle that covers no pixel centre marks its centroid pixel.
    Small triangles go through a vectorised path, large ones through a per-triangle loop;
    both use the same test, so the result does not depend on the path."""
    h, w = mask.shape
    x0, y0 = px[tri[:, 0]], py[tri[:, 0]]
    x1, y1 = px[tri[:, 1]], py[tri[:, 1]]
    x2, y2 = px[tri[:, 2]], py[tri[:, 2]]
    minx = np.clip(np.floor(np.minimum(np.minimum(x0, x1), x2)).astype(int), 0, w - 1)
    maxx = np.clip(np.ceil(np.maximum(np.maximum(x0, x1), x2)).astype(int), 0, w - 1)
    miny = np.clip(np.floor(np.minimum(np.minimum(y0, y1), y2)).astype(int), 0, h - 1)
    maxy = np.clip(np.ceil(np.maximum(np.maximum(y0, y1), y2)).astype(int), 0, h - 1)
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    todo = np.abs(area) > 1e-12
    extent = np.maximum(maxx - minx, maxy - miny)
    for bsize in _BATCH_SIZES:
        small = todo & (extent < bsize)
        todo &= ~small
        ids_all = np.nonzero(small)[0]
        step = max(1, _BATCH_CELLS // (bsize * bsize))
        for start in range(0, ids_all.size, step):
            ids = ids_all[start:start + step]
            off = np.arange(bsize)
            gxi = minx[ids, None, None] + off[None, None, :]          # (n, 1, B)
            gyi = miny[ids, None, None] + off[None, :, None]          # (n, B, 1)
            inb = (gxi <= maxx[ids, None, None]) & (gyi <= maxy[ids, None, None])
            gx, gy = gxi + 0.5, gyi + 0.5
            a = area[ids, None, None]
            X0, Y0 = x0[ids, None, None], y0[ids, None, None]
            X1, Y1 = x1[ids, None, None], y1[ids, None, None]
            X2, Y2 = x2[ids, None, None], y2[ids, None, None]
            w0 = ((X1 - gx) * (Y2 - gy) - (X2 - gx) * (Y1 - gy)) / a
            w1 = ((X2 - gx) * (Y0 - gy) - (X0 - gx) * (Y2 - gy)) / a
            w2 = 1 - w0 - w1
            inside = inb & (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            n_i, r_i, c_i = np.nonzero(inside)
            mask[gyi[n_i, r_i, 0], gxi[n_i, 0, c_i]] = True
            empty = ids[~inside.any(axis=(1, 2))]
            if empty.size:
                # sub-pixel triangles: mark the centroid so thin parts do not vanish
                cx = np.clip((x0[empty] + x1[empty] + x2[empty]) / 3, 0, w - 1).astype(int)
                cy = np.clip((y0[empty] + y1[empty] + y2[empty]) / 3, 0, h - 1).astype(int)
                mask[cy, cx] = True

    for i in np.nonzero(todo)[0]:
        xs = np.arange(minx[i], maxx[i] + 1) + 0.5
        ys = np.arange(miny[i], maxy[i] + 1) + 0.5
        if xs.size == 0 or ys.size == 0:
            continue
        gx, gy = np.meshgrid(xs, ys)
        a = area[i]
        w0 = ((x1[i] - gx) * (y2[i] - gy) - (x2[i] - gx) * (y1[i] - gy)) / a
        w1 = ((x2[i] - gx) * (y0[i] - gy) - (x0[i] - gx) * (y2[i] - gy)) / a
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if inside.any():
            mask[miny[i]:maxy[i] + 1, minx[i]:maxx[i] + 1] |= inside
        else:
            # sub-pixel triangle: mark its centroid so thin parts do not vanish
            cx = int(np.clip((x0[i] + x1[i] + x2[i]) / 3, 0, w - 1))
            cy = int(np.clip((y0[i] + y1[i] + y2[i]) / 3, 0, h - 1))
            mask[cy, cx] = True


def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 1.0


def bbox_of(mask):
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return xs.min(), xs.max(), ys.min(), ys.max()


def normalize_to_bbox(mask, size=512, margin=0.02, keep_aspect=True):
    """Crop a mask to its bbox and fit it into a size x size square (aspect kept, centred).
    Used to compare a concept mask with a model silhouette when the concept has no scale."""
    import cv2
    bb = bbox_of(mask)
    out = np.zeros((size, size), dtype=bool)
    if bb is None:
        return out
    x0, x1, y0, y1 = bb
    crop = mask[y0:y1 + 1, x0:x1 + 1].astype(np.uint8) * 255
    ch, cw = crop.shape
    inner = int(size * (1 - 2 * margin))
    s = inner / max(ch, cw)
    nw, nh = max(1, int(round(cw * s))), max(1, int(round(ch * s)))
    res = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA) > 127
    ox, oy = (size - nw) // 2, (size - nh) // 2
    out[oy:oy + nh, ox:ox + nw] = res
    return out


def overlay_image(concept_mask, model_mask):
    """RGB uint8: concept-only red, model-only blue, overlap grey, background white.
    Returns (img, red_pct, blue_pct) where pct is relative to the concept area."""
    h, w = concept_mask.shape
    img = np.full((h, w, 3), 255, np.uint8)
    both = concept_mask & model_mask
    red = concept_mask & ~model_mask
    blue = model_mask & ~concept_mask
    img[both] = (150, 150, 150)
    img[red] = (220, 40, 40)
    img[blue] = (40, 80, 220)
    area = max(1, concept_mask.sum())
    return img, float(red.sum() / area), float(blue.sum() / area)


def concept_mask(path, background=None):
    """Foreground mask (bool, row 0 = top) of a concept image, without bpy.

    A black/white mask file with a dark border (validate_concept's mask_<view>.png) is read as
    white = object. Otherwise the same rule as asset_checks/ac_common.concept_mask: alpha
    channel when present; otherwise a
    pixel is background when it is bright and grey (min channel > background.max_min_channel,
    default 225, and saturation < background.min_saturation, default 0.12). Specks under 0.2 %
    of the image are dropped and holes are filled.
    """
    import cv2
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError(f"cannot read image: {path}")
    if im.dtype != np.uint8:
        im = (im / 257).astype(np.uint8)
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    h, w = im.shape[:2]
    grey = im[:, :, :3].max(axis=2).astype(np.int16) - im[:, :, :3].min(axis=2) < 3
    lum = im[:, :, :3].mean(axis=2)
    binary = grey.mean() > 0.99 and ((lum < 10) | (lum > 245)).mean() > 0.98
    border = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    if im.shape[2] == 4 and im[:, :, 3].min() < 250:
        m = (im[:, :, 3] > 127).astype(np.uint8)
    elif binary and (border < 128).mean() > 0.5:
        # a mask file (validate_concept writes white object on black)
        m = (lum > 127).astype(np.uint8)
    else:
        bg = background or {}
        rgb = im[:, :, :3].astype(np.float32)
        mn, mx = rgb.min(axis=2), rgb.max(axis=2)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        is_bg = (mn > bg.get("max_min_channel", 225)) & (sat < bg.get("min_saturation", 0.12))
        m = (~is_bg).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 0.002 * w * h:
            keep[lab == i] = 1
    cnts, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(keep)
    cv2.drawContours(filled, cnts, -1, 1, thickness=-1)
    return filled.astype(bool)
