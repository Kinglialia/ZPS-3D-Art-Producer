"""Measure the colors of an image, or the steps of a color ramp, in OKLab/OKLCH.

  python3 palette_report.py <image> [--colors 8] [--palette <#hex ...|palette.json>] [--max-delta 8]
  python3 palette_report.py --ramp <#hex #hex #hex ...>   (or --ramp ramp.json)

Image mode: dominant colors of the opaque pixels, each with its OKLCH value and share. Every
cluster gives two colors: `mean` (what the eye blends) and `vivid` (the mean of its most chromatic
quarter, the color the artist painted). A separate accent pass keeps small, strongly chromatic areas
that clustering merges away (a red gem on a dark body). With --palette, each color gets the nearest
palette color and its delta E OK (OKLab distance x 100).
Ramp mode: delta E OK and lightness step between consecutive stops; uneven steps are flagged.
Diagnostic only: a palette match is not style approval. Requires Pillow and numpy."""
import argparse
import json
from pathlib import Path
import sys

# delta E OK x 100: about 2 is just noticeable; 8 is a clearly different color side by side.
# The default threshold is a starting point, not a standard [guess].
DEFAULT_MAX_DELTA = 8.0
ALPHA_MIN = 128         # below this alpha, a pixel is background or antialias fringe
VIVID_QUANTILE = 0.75   # vivid color = mean of the cluster pixels above this chroma quantile
ACCENT_CHROMA = 0.10    # OKLCH chroma of a clearly colored pixel (greys are below about 0.03)
ACCENT_DIST = 15.0      # delta E OK x 100 from its cluster's vivid color: the clustering lost it
ACCENT_MIN_SHARE = 0.003
RAMP_UNEVEN = 0.35      # a step more than 35% away from the mean step is uneven [guess]


def hex_to_rgb(h):
    h = h.strip().lstrip('#')
    if len(h) != 6:
        raise ValueError(f'invalid hex color {h!r}')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb):
    return '#%02x%02x%02x' % tuple(int(round(min(max(c, 0), 255))) for c in rgb)


def srgb_to_linear(rgb):
    import numpy as np
    c = np.asarray(rgb, dtype=np.float64) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(lin):
    import numpy as np
    c = np.clip(lin, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255


def oklab(rgb):
    """sRGB 0-255 (..., 3) -> OKLab (..., 3) (Björn Ottosson, 2020)."""
    import numpy as np
    lin = srgb_to_linear(rgb)
    m1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                   [0.2119034982, 0.6806995451, 0.1073969566],
                   [0.0883024619, 0.2817188376, 0.6299787005]])
    m2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                   [1.9779984951, -2.4285922050, 0.4505937099],
                   [0.0259040371, 0.7827717662, -0.8086757660]])
    return np.cbrt(lin @ m1.T) @ m2.T


def oklch(lab):
    import numpy as np
    lab = np.asarray(lab, dtype=np.float64)
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
    return lab[..., 0], c, h


def describe(rgb):
    import numpy as np
    lab = oklab(np.asarray(rgb, dtype=np.float64))
    L, C, H = oklch(lab)
    return {'hex': to_hex(rgb), 'oklch': [round(float(L), 3), round(float(C), 3), round(float(H), 1) if C > 0.02 else None]}


def delta_e_ok(a, b):
    import numpy as np
    return float(np.linalg.norm(oklab(np.asarray(a, float)) - oklab(np.asarray(b, float))) * 100)


def load_colors(values):
    colors = []
    for v in values:
        p = Path(v)
        if p.suffix == '.json' and p.is_file():
            data = json.loads(p.read_text())
            items = data.get('colors', data) if isinstance(data, dict) else data
            colors += [i['hex'] if isinstance(i, dict) else i for i in items]
        else:
            colors.append(v)
    return [hex_to_rgb(c) for c in colors]


load_palette = load_colors  # name used by score_variants.py


def mean_rgb(pixels):
    """Average in linear light, then encode: an sRGB average of red and green is too dark."""
    return linear_to_srgb(srgb_to_linear(pixels).mean(axis=0))


def report(path, n_colors=8, palette=None, max_delta=DEFAULT_MAX_DELTA):
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        arr = np.asarray(im.convert('RGBA'))
    px = arr[..., :3][arr[..., 3] >= ALPHA_MIN].astype(np.float64)
    if not len(px):
        raise ValueError('no opaque pixels to analyse')
    strip = Image.fromarray(px.astype(np.uint8).reshape(1, -1, 3), 'RGB')
    labels = np.asarray(strip.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)).reshape(-1)
    lab = oklab(px)
    _, chroma, _ = oklch(lab)
    dominant, vivid_lab = [], np.zeros((labels.max() + 1, 3))
    for idx in np.unique(labels):
        sel = labels == idx
        members, ch = px[sel], chroma[sel]
        vivid = mean_rgb(members[ch >= np.quantile(ch, VIVID_QUANTILE)])
        vivid_lab[idx] = oklab(vivid)
        dominant.append({'share': round(float(sel.mean()), 4), 'mean': describe(mean_rgb(members)),
                         'vivid': describe(vivid)})
    dominant.sort(key=lambda e: -e['share'])
    # Accent pass: colored pixels far from their own cluster's vivid color, grouped by 30-degree hue bins.
    _, _, hue = oklch(lab)
    far = (chroma >= ACCENT_CHROMA) & (np.linalg.norm(lab - vivid_lab[labels], axis=1) * 100 > ACCENT_DIST)
    accents = []
    for b in range(12):
        sel = far & ((hue // 30) == b)
        if sel.mean() >= ACCENT_MIN_SHARE:
            accents.append({'share': round(float(sel.mean()), 4), 'vivid': describe(mean_rgb(px[sel]))})
    accents.sort(key=lambda e: -e['share'])
    if palette:
        for e in dominant + accents:
            rgb = hex_to_rgb(e['vivid']['hex'])
            nearest = min(palette, key=lambda c: delta_e_ok(rgb, c))
            d = delta_e_ok(rgb, nearest)
            e.update(nearest=to_hex(nearest), delta_e_ok=round(d, 2), status='pass' if d <= max_delta else 'off_palette')
    result = {'tool': 'art_palette_report', 'schema_version': 2, 'image': str(Path(path).resolve()),
              'opaque_pixels': int(len(px)), 'color_space': 'OKLab / OKLCH [L 0-1, C, h degrees]',
              'dominant': dominant, 'accents': accents,
              'scope': 'Median-cut clusters of opaque pixels. Antialias and lighting create in-between colors '
                       'that may be valid. Palette checks use the vivid color of each cluster.'}
    if palette:
        result.update(max_delta_e_ok=max_delta,
                      off_palette_share=round(sum(e['share'] for e in dominant if e['status'] == 'off_palette'), 4),
                      off_palette_accents=[e['vivid']['hex'] for e in accents if e['status'] == 'off_palette'])
    return result


def ramp(colors):
    import numpy as np
    if len(colors) < 3:
        raise ValueError('a ramp needs 3 or more stops')
    lab = oklab(np.asarray(colors, dtype=np.float64))
    steps = np.linalg.norm(np.diff(lab, axis=0), axis=1) * 100
    l_steps = np.diff(lab[:, 0]) * 100
    out = {'tool': 'art_palette_ramp', 'stops': [describe(c) for c in colors],
           'delta_e_ok_steps': [round(float(s), 2) for s in steps],
           'lightness_steps': [round(float(s), 2) for s in l_steps]}
    flags = []
    for name, vals in (('color', steps), ('lightness', np.abs(l_steps))):
        mean = vals.mean()
        for i, v in enumerate(vals):
            if mean > 0 and abs(v - mean) > RAMP_UNEVEN * mean:
                flags.append({'between': [i, i + 1], 'kind': name, 'step': round(float(v), 2), 'mean': round(float(mean), 2)})
    if np.any(np.sign(l_steps) != np.sign(l_steps[0])):
        flags.append({'kind': 'lightness_direction', 'note': 'lightness does not change in one direction'})
    out.update(uneven=flags, status='pass' if not flags else 'uneven',
               scope='Even steps look like an even change; a bump exaggerates one transition.')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('image', type=Path, nargs='?')
    p.add_argument('--ramp', nargs='+', help='ramp stops as #RRGGBB values or a JSON file')
    p.add_argument('--colors', type=int, default=8)
    p.add_argument('--palette', nargs='+', help='#RRGGBB values or a JSON file with a colors list')
    p.add_argument('--max-delta', type=float, default=DEFAULT_MAX_DELTA, help='delta E OK x 100')
    p.add_argument('--fail-share', type=float, help='exit 1 when off-palette share exceeds this fraction')
    a = p.parse_args()
    if bool(a.image) == bool(a.ramp):
        p.error('give an image or --ramp, not both')
    try:
        if a.ramp:
            r = ramp(load_colors(a.ramp))
            print(json.dumps(r, indent=2))
            return 0
        r = report(a.image, a.colors, load_colors(a.palette) if a.palette else None, a.max_delta)
        print(json.dumps(r, indent=2))
        if a.fail_share is not None and r.get('off_palette_share', 0) > a.fail_share:
            return 1
        return 0
    except (ImportError, OSError, ValueError) as e:
        print(json.dumps({'error': str(e)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
