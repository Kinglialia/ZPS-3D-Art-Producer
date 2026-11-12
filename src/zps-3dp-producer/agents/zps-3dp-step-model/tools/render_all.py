"""The critic renders, the normal renders of the joined GLB and the review set in one Blender session (D37.4). Runs in
Blender.

Usage: BLENDER -b --python tools/render_all.py -- --final F [--concept C/concept_shadow.png] [--size 1024]
In this order, each as the tool runs alone:
  1. self_build/render_views.py --work F --spec F/spec.json --mode critic --outdir F/review/renders
  2. self_build/render_views.py --input F/<id>-untextured.glb --mode normal --outdir F/review/renders
       --out F/review/renders/normal.json: normal_* drawn again from the joined GLB
  3. render_review.py --final F [--concept ...] [--size ...]
The first step removes the PNG files in F/review/renders, so it comes first. A failed stage does not stop the next one.
Result files: F/review/renders/renders.json, F/review/renders/normal.json, F/review/review.json.
Exit 0 when no stage is fail or error, 1 otherwise.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("lib", "self_build"):
    sys.path.insert(0, os.path.join(HERE, sub))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402


def main():
    import common
    import render_review
    import render_views
    import session
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    p.add_argument("--concept")
    p.add_argument("--size", type=int)
    a = p.parse_args(common.script_argv())
    final, renders = a.final, os.path.join(a.final, "review", "renders")
    spec = common.read_json(os.path.join(final, "spec.json"))
    glb = os.path.join(final, f"{spec['asset']}-untextured.glb")
    review = ["--final", final] + (["--concept", a.concept] if a.concept else []) + (["--size", a.size] if a.size else [])
    passed = [
        session.stage(render_views.main, os.path.join(renders, "renders.json"), "--work", final,
                      "--spec", os.path.join(final, "spec.json"), "--mode", "critic", "--outdir", renders),
        session.stage(render_views.main, os.path.join(renders, "normal.json"), "--input", glb, "--mode", "normal",
                      "--outdir", renders, "--out", os.path.join(renders, "normal.json")),
        session.stage(render_review.main, os.path.join(final, "review", "review.json"), *review)]
    sys.exit(0 if all(passed) else 1)


if __name__ == "__main__":
    require_root()
    main()
