"""Which views changed between two guide renders (concept-views.md §9): regenerate only those.

Usage: python3 tools/diff_guides.py --old <old guides dir> --new <new guides dir> --out <json>
Compares <view>_id.png as material maps (names from views.json, so a colour reshuffle is no change), each
cropped to the object and resized to 256 px. A view changed when more than 0.5% of the object area has another
material (or none), or the bbox height/width changed more than 1%. A kept view is still measured against the
new guide, so a miss shows up in measure.py. Writes the common result JSON with data.changed. Prints one line.
Exit 0, 2 on error.
"""
import argparse
import contextlib
import io
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "views/diff_guides"
VIEWS = ("front", "back", "left", "right", "top")
N = 256
AREA, ASPECT = 0.005, 0.01


def material_map(d, view, names):
    meta = common.read_json(os.path.join(d, "views.json"))
    mats = list(meta["materials"])
    pal = np.array([[int(meta["materials"][m].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for m in mats])
    a = np.asarray(Image.open(os.path.join(d, f"{view}_id.png")).convert("RGBA")).astype(int)
    cols, inv = np.unique(a[..., :3].reshape(-1, 3), axis=0, return_inverse=True)
    near = ((cols[:, None] - pal[None]) ** 2).sum(-1).argmin(-1)
    codes = np.array([names.index(m) for m in mats])[near][inv.reshape(-1)].reshape(a.shape[:2])
    lab = np.where(a[..., 3] > 127, codes, -1)
    ys, xs = np.where(lab >= 0)
    if not len(ys):
        return None, None
    crop = lab[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    aspect = crop.shape[0] / crop.shape[1]
    ri = (np.arange(N) * crop.shape[0] / N).astype(int)
    ci = (np.arange(N) * crop.shape[1] / N).astype(int)
    return crop[ri][:, ci], aspect


def compare(old, new):
    names = sorted(set(common.read_json(os.path.join(old, "views.json"))["materials"])
                   | set(common.read_json(os.path.join(new, "views.json"))["materials"]))
    out = {}
    for v in VIEWS:
        if not all(os.path.isfile(os.path.join(d, f"{v}_id.png")) for d in (old, new)):
            out[v] = {"changed": True, "diff": None, "aspect_change": None}
            continue
        (mo, ao), (mn, an) = material_map(old, v, names), material_map(new, v, names)
        if mo is None or mn is None:
            out[v] = {"changed": mo is not mn, "diff": None, "aspect_change": None}
            continue
        obj = (mo >= 0) | (mn >= 0)
        diff = float(((mo != mn) & obj).sum() / obj.sum())
        asp = abs(an / ao - 1)
        out[v] = {"changed": diff > AREA or asp > ASPECT, "diff": round(diff, 4), "aspect_change": round(asp, 4)}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        res = compare(a.old, a.new)
    except Exception as e:  # noqa: BLE001
        common.write_error(a.out, TOOL, e)
        print(f"[{TOOL}] error {e!r}")
        sys.exit(2)
    changed = [v for v, r in res.items() if r["changed"]]
    with contextlib.redirect_stdout(io.StringIO()):
        common.write_result(a.out, TOOL, [common.check(f"diff.{v}", "info", value=r) for v, r in res.items()],
                            data={"changed": changed, "old": a.old, "new": a.new})
    print(f"[{TOOL}] đổi: {', '.join(changed) or 'none'} -> {a.out}")


if __name__ == "__main__":
    require_root()
    main()
