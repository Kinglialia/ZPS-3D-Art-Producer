"""Mask, spec, camera fit and proportion check, in one command, after the full build. Plain Python.

Usage: PY T/prep_overlay.py --work <F> --view <view>=<concept image> [--view ...] [--side left|right] [--card <asset-card.yaml>] [--spec <spec.json>]
  view   front, back, left, right, top (orthographic) or 34 (the 3/4 view).
  --side the image side of a 3/4 concept that shows the object's side face, the card's view_side. Required with a 34 view.
  --card the asset card; check_proportion.py compares its `marks` with the blockout (the rerun in step 4 must keep them).
  --spec default <vN>/work/spec.json of the version folder.
Steps:
  1. concept_mask.py's mask() of each image -> <spec folder>/masks/<view>.png.
  2. <spec> gets concept.views.<view> = masks/<view>.png. Every other key of an existing spec stays.
  3. A 34 view: fit_view.py --spec <spec> --side <side> --write-spec, which stores concept.cameras.34.
  4. check_proportion.py again, because gate_all.py ran it before the spec existed (it was not_checked then).
After it, render with `--spec <spec>`: render_critic.py then draws overlay_<view>.png.
Prints one line, or the failing lines and `prep_overlay fail`. Exit 0 pass, 1 fail, 2 refused.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import common  # noqa: E402
import gate_all  # noqa: E402
from check_proportion import AXES, default_spec  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "prep_overlay"
THREE_QUARTER = "34"


def refuse(text):
    print(f"{NAME} refused: {text}")
    sys.exit(2)


def parse_views(items):
    views = {}
    for item in items:
        view, sep, image = item.partition("=")
        if not sep or view not in (*AXES, THREE_QUARTER):
            refuse(f"--view {item}: want <{'|'.join((*AXES, THREE_QUARTER))}>=<image>")
        if not os.path.isfile(image):
            refuse(f"--view {item}: no such image")
        views[view] = image
    return views


def write_masks(views, spec_path, spec):
    import concept_mask
    from PIL import Image
    folder = os.path.join(os.path.dirname(os.path.abspath(spec_path)), "masks")
    os.makedirs(folder, exist_ok=True)
    for view, image in views.items():
        mask, _ = concept_mask.mask(image)
        Image.fromarray(mask, "L").save(os.path.join(folder, f"{view}.png"))
        spec.setdefault("concept", {}).setdefault("views", {})[view] = f"masks/{view}.png"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--view", action="append", default=[], metavar="VIEW=IMAGE")
    ap.add_argument("--side", choices=("left", "right"))
    ap.add_argument("--card")
    ap.add_argument("--spec")
    a = ap.parse_args()
    views = parse_views(a.view)
    if not views:
        refuse("give at least one --view")
    if THREE_QUARTER in views and not a.side:
        refuse("a 34 view needs --side left|right, the card's view_side (brief line VIEW_SIDE:). The brief has none: the card needs view_side")
    work = os.path.abspath(a.work)
    spec_path = os.path.abspath(a.spec or default_spec(work))
    spec = common.read_json(spec_path) if os.path.isfile(spec_path) else {}
    lines = []
    write_masks(views, spec_path, spec)
    common.write_json(spec_path, spec)
    if THREE_QUARTER in views:
        p = subprocess.run([sys.executable, os.path.join(HERE, "fit_view.py"), "--work", work, "--spec", spec_path,
                            "--side", a.side, "--write-spec"], capture_output=True, text=True)
        fit = os.path.join(work, "camera_fit.json")
        lines += [x for x in [gate_all.failing(fit, "camera_fit.json")] if x]
        if p.returncode and not lines:
            lines.append(f"fit_view: exit {p.returncode}: {(p.stdout or p.stderr).strip()[-140:]}")
    lines += gate_all.run_check("check_proportion", work, "--work", ["--spec", spec_path, *(["--card", a.card] if a.card else [])])
    if lines:
        print("\n".join(l[:gate_all.LINE_MAX] for l in lines))
        print(f"{NAME} fail: {len(lines)} failing")
        sys.exit(1)
    cam = (common.read_json(spec_path).get("concept") or {}).get("cameras", {}).get(THREE_QUARTER)
    seen = ", ".join(views) + (f"; camera 34 az {cam['azimuth_deg']:g} el {cam['elevation_deg']:g}" if cam and THREE_QUARTER in views else "")
    print(f"{NAME} pass: {os.path.relpath(spec_path)}: {seen}")


if __name__ == "__main__":
    require_root()
    main()
