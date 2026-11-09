"""Measure generated views against the guides: the kit's measure_views.py, unchanged, with G1 fixed here.

Usage: python3 tools/measure.py --final <V/final> --guides <views_front final>/guides --views front[,back,left,right,top]
           [--front <views_front final>/front.png] [--concept-colors <views_front final>/concept_colors.json]
G1 (docs/review-kit-v0.10.4-vs-process.md): the kit keeps only background that touches the image border, so a
closed gap between columns counts as object. Here every pixel near the background colour is background.
Images: <final>/<view>.png; --front when front.png lives in views_front (views_rest).
Without --concept-colors, the kit compares each material with the front view (the colour standard).
Writes <final>/report/{report.json, report.md, overlay_sheet.png, overlay_<view>.png} and
<final>/review/checks/measure.json (fail: a view in the kit's `regen`, or a missing image). Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import common  # noqa: E402
import measure_views as mv  # noqa: E402

TOOL = "views/measure"
mv.flood_background = lambda bgish: bgish


def gen_dir(d, final, views, front):
    for v in views:
        src = front if v == "front" and front else os.path.join(final, f"{v}.png")
        if os.path.isfile(src):
            os.symlink(os.path.abspath(src), os.path.join(d, f"{v}.png"))


def overlays(guides, gen, report_dir, views, threshold):
    meta = common.read_json(os.path.join(guides, "views.json"))
    names = list(meta["materials"])
    palette = np.array([mv.hex_rgb(meta["materials"][m]) for m in names])
    for v in views:
        p = mv.find_gen(gen, v)
        if p:
            _, fr = mv.measure_view(v, mv.load_blockout(guides, v, palette), mv.load_gen(p, threshold), names)
            if fr:
                Image.fromarray(mv.overlay(fr, palette)[2]).save(os.path.join(report_dir, f"overlay_{v}.png"))


def checks_of(rep, views):
    out = []
    for v in views:
        r = rep["views"].get(v)
        if r is None:
            out.append(common.check(f"views.{v}", "fail", note="thiếu ảnh"))
            continue
        val = {k: r.get(k) for k in ("score", "verdict", "iou", "aspect_err", "detail", "detail_worst", "max_delta_e")}
        out.append(common.check(f"views.{v}", "fail" if v in rep["regen"] else "pass", value=val,
                                note=r.get("error")))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", required=True)
    p.add_argument("--guides", required=True)
    p.add_argument("--views", required=True)
    p.add_argument("--front")
    p.add_argument("--concept-colors")
    p.add_argument("--bg-threshold", type=float, default=40)
    a = p.parse_args()
    views = [v for v in mv.VIEWS if v in a.views.split(",")]
    report_dir = os.path.join(a.final, "report")
    out = os.path.join(a.final, "review", "checks", "measure.json")
    try:
        os.makedirs(report_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as d:
            gen_dir(d, a.final, views, a.front)
            sys.argv = ["measure_views.py", "--blockout", a.guides, "--gen", d, "--out", report_dir,
                        "--views", ",".join(views), "--bg-threshold", str(a.bg_threshold),
                        *(["--concept-colors", a.concept_colors] if a.concept_colors else [])]
            with contextlib.redirect_stdout(io.StringIO()):
                mv.main()
            overlays(a.guides, d, report_dir, views, a.bg_threshold)
        with open(os.path.join(report_dir, "report.json"), encoding="utf-8") as f:
            rep = json.load(f)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(2)
    r = common.write_result(out, TOOL, checks_of(rep, views), data={"regen": rep["regen"],
                            "overall_score": rep["overall_score"], "report": os.path.join(report_dir, "report.json")})
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    main()
