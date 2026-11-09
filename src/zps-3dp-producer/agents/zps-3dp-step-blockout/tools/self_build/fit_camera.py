"""Find the orthographic camera a painted concept view was drawn from.

A painted 3/4 concept rarely sits at exactly azimuth 45° / elevation 30° (VIEW_DIRS["34"]).
This grid-searches azimuth and elevation per concept view so the model's bbox-normalised
silhouette best matches the concept mask, using the current assembled model.

Usage (pure Python):
  python3 tools/self_build/fit_camera.py --work <w> --spec task/spec.json [--rollout k]
         [--views 34] [--write-spec] [--out <w>/camera_fit.json]

--write-spec stores the result in spec.concept.cameras. That block records where the concept
camera was; it is not a pass/fail threshold. Fit the camera once on a reasonable blockout, then
fit params with the camera fixed. Re-fitting both in a loop lets them chase each other.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import graph as G  # noqa: E402
import raster  # noqa: E402

TOOL = "self_build/fit_camera"


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--rollout")
    p.add_argument("--views", help="comma list; default every non-orthographic concept view")
    p.add_argument("--write-spec", action="store_true")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    out = a.out or os.path.join(a.work, "camera_fit.json")
    try:
        settings, spec = common.load_settings(a.spec)
        gdir = os.path.join(a.work, "rollouts", a.rollout) if a.rollout else a.work
        glb = os.path.join(gdir, "assembled.glb")
        if not os.path.isfile(glb):
            raise SystemExit(f"no assembled.glb in {gdir}; run assembly.py first")
        v, t, _ = G.load_glb(glb)
        size = settings["optimize"]["raster_size"]
        concept = spec.get("concept") or {}
        labels = a.views.split(",") if a.views else [
            k for k in (concept.get("views") or {}) if k not in G.ORTHO_VIEWS]
        spec_no_cam = dict(spec, concept=dict(concept, cameras={}))
        cms = G.concept_masks(spec_no_cam, a.spec, size)
        checks, fits = [], {}
        for label in labels:
            if label not in cms:
                checks.append(common.check(f"camera.{label}", "not_checked",
                                           note="no concept mask for this view"))
                continue
            before = raster.iou(cms[label], G.model_mask(v, t, label, size)) \
                if label in raster.VIEW_DIRS else None
            az, el, best = G.fit_camera(v, t, cms[label], size)
            fits[label] = {"azimuth_deg": az, "elevation_deg": el}
            checks.append(common.check(f"camera.{label}", "info", value=fits[label],
                                       note=f"IoU {before if before is None else round(before, 4)}"
                                            f" at the default camera -> {best} fitted"))
        if a.write_spec and fits:
            spec.setdefault("concept", {}).setdefault("cameras", {}).update(fits)
            common.write_json(a.spec, spec)
        common.write_result(out, TOOL, checks=checks, source=glb, spec_path=a.spec,
                            data={"cameras": fits, "written_to_spec": bool(a.write_spec and fits)})
    except Exception as exc:  # noqa: BLE001
        common.write_error(out, TOOL, exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
