"""check_proportion.py: the built model has the proportions of the concept in every orthographic view (D36, B9).

The concept has no scale, so only the width : height ratio of the silhouette box is compared. The model box comes from
assembly.json, the concept box from the mask file the spec names for that view."""
import json
import subprocess

import pytest
import yaml

from conftest import HUT_ROWS, HUT_SOURCES, TOOLS, write_mask, write_build

VPY = TOOLS / ".deps/venv/bin/python"
pytestmark = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh (numpy, cv2)")


def box_rows(w, d, h):
    return [{"name": "base", "parent": None, "contact": None, "depth": None,
             "bbox_min": [-w / 2, -d / 2, 0.0], "bbox_max": [w / 2, d / 2, h]}]


def spec_for(tmp_path, **views):
    """{view: (width px, height px)} -> spec.json with one mask file per view."""
    spec = {"concept": {"views": {}}}
    for view, (w, h) in views.items():
        write_mask(tmp_path / f"{view}.png", w, h)
        spec["concept"]["views"][view] = f"{view}.png"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def run_proportion(tmp_path, work, spec=None, marks=None):
    out = tmp_path / "proportion.result.json"
    cmd = [str(VPY), str(TOOLS / "check_proportion.py"), "--work", str(work), "--out", str(out)]
    if marks is not None:
        card = tmp_path / "asset-card.yaml"
        card.write_text(yaml.safe_dump({"marks": marks}), encoding="utf-8")
        cmd += ["--card", str(card)]
    r = subprocess.run(cmd + (["--spec", str(spec)] if spec else []), capture_output=True, text=True)
    return r, (json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None)


def statuses(res):
    return {c["check"]: c["status"] for c in res["checks"]}


def test_a_concept_with_the_proportions_of_the_model_passes_in_every_view_and_prints_one_line(tmp_path):
    work = write_build(tmp_path / "w", rows=HUT_ROWS)
    spec = spec_for(tmp_path, front=(400, 370), back=(400, 370), left=(400, 370), right=(400, 370), top=(400, 400))
    r, res = run_proportion(tmp_path, work, spec)
    assert (r.returncode, res["overall"], len(r.stdout.strip().splitlines())) == (0, "pass", 1), r.stdout + r.stderr
    assert statuses(res) == {"assembly.fresh": "pass", **{f"proportion.{v}": "pass" for v in
                                                          ("front", "back", "left", "right", "top")}}


def test_a_concept_ten_percent_wider_than_the_model_fails_and_names_the_view_and_both_ratios(tmp_path):
    """The hut box is 4 x 3.7 m: ratio 1.081. A mask 450 x 370 px (1.216) is 11 % wider: a roof or a wall in the
    wrong place. 430 x 370 (1.162) is 7 % off and passes."""
    work = write_build(tmp_path / "w", rows=HUT_ROWS)
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(450, 370), left=(430, 370)))
    assert (r.returncode, res["overall"]) == (1, "fail")
    assert statuses(res)["proportion.front"] == "fail" and statuses(res)["proportion.left"] == "pass"
    front = next(c for c in res["checks"] if c["check"] == "proportion.front")
    assert front["value"] == -0.111 and front["threshold"] == 0.1
    assert "model 1.081" in front["note"] and "concept 1.216" in front["note"]


def test_each_view_reads_the_axes_it_shows_so_a_long_thin_model_fails_a_front_shaped_side_mask(tmp_path):
    """A 4 x 2 x 3.7 m model: front ratio 1.081 (x : z), left ratio 0.541 (y : z), top ratio 2.0 (x : y)."""
    work = write_build(tmp_path / "w", rows=box_rows(4.0, 2.0, 3.7))
    good = spec_for(tmp_path, front=(400, 370), left=(200, 370), top=(400, 200))
    r, res = run_proportion(tmp_path, work, good)
    assert (r.returncode, res["overall"]) == (0, "pass"), res["checks"]
    bad = spec_for(tmp_path, left=(400, 370))
    r, res = run_proportion(tmp_path, work, bad)
    assert (r.returncode, statuses(res)["proportion.left"]) == (1, "fail")


def test_without_a_spec_or_a_mask_file_nothing_is_compared_and_the_result_is_not_checked(tmp_path):
    work = write_build(tmp_path / "w")
    r, res = run_proportion(tmp_path, work)
    assert (r.returncode, res["overall"], len(r.stdout.strip().splitlines())) == (0, "not_checked", 1)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"concept": {"views": {"front": "missing.png"}}}), encoding="utf-8")
    r, res = run_proportion(tmp_path, work, spec)
    assert (r.returncode, res["overall"], statuses(res)["proportion.front"]) == (0, "not_checked", "not_checked")


def test_a_three_quarter_view_is_not_compared_because_its_box_depends_on_the_camera(tmp_path):
    work = write_build(tmp_path / "w")
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(400, 370), **{"34": (300, 300)}))
    assert (r.returncode, statuses(res)["proportion.34"], statuses(res)["proportion.front"]) == (0, "not_checked", "pass")


def test_the_spec_defaults_to_the_one_the_worker_writes_beside_final(tmp_path):
    work = write_build(tmp_path / "v1" / "final")
    (tmp_path / "v1" / "work").mkdir()
    spec_for(tmp_path / "v1" / "work", front=(400, 450))
    r, res = run_proportion(tmp_path, work)
    assert (r.returncode, statuses(res)["proportion.front"]) == (1, "fail")


def test_a_param_variant_reads_the_spec_of_its_version_so_it_is_not_skipped_as_not_checked(tmp_path):
    """A variant lives in vN/variants/b/, a sibling of final/: its spec is still vN/work/spec.json."""
    (tmp_path / "v1" / "work").mkdir(parents=True)
    spec_for(tmp_path / "v1" / "work", front=(400, 450))
    work = write_build(tmp_path / "v1" / "variants" / "b")
    r, res = run_proportion(tmp_path, work)
    assert (r.returncode, statuses(res)["proportion.front"]) == (1, "fail")


def test_a_stale_assembly_fails_instead_of_comparing_an_old_build(tmp_path):
    work = write_build(tmp_path / "w", stale=True)
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(400, 370)))
    assert (r.returncode, res["overall"]) == (1, "fail")


def mark(name, z_m):
    return {"name": name, "z_m": z_m}


def hut_with(edges, rows=None):
    """sources.json of the hut with the worker's `marks` map {mark name: "<part>.top" | "<part>.bottom"}."""
    return {"rows": rows or HUT_ROWS, "sources": {**HUT_SOURCES, "marks": edges}}


def checked(res, name):
    c = next(c for c in res["checks"] if c["check"] == f"proportion.mark.{name}")
    return c["status"], c.get("value"), c.get("threshold"), c["note"]


def test_marks_that_sit_on_the_part_edge_the_worker_named_pass_without_any_concept_image_g5(tmp_path):
    """The hut is 3.7 m high; the walls end at 2.7 m and the base at 0.3 m."""
    work = write_build(tmp_path / "w", **hut_with({"mép mái": "walls.top", "mặt bệ": "base.top"}))
    r, res = run_proportion(tmp_path, work, marks=[mark("mép mái", 2.7), mark("mặt bệ", 0.3)])
    assert (r.returncode, res["overall"], len(r.stdout.strip().splitlines())) == (0, "pass", 1), r.stdout
    assert statuses(res) == {"assembly.fresh": "pass", "proportion.spec": "not_checked", "proportion.mark.mép mái": "pass",
                             "proportion.mark.mặt bệ": "pass"}


def test_a_mark_is_checked_on_its_own_edge_not_on_the_nearest_edge_of_any_part_g5(tmp_path):
    """The eave mark at 2.1 m sits on the door top, but the worker says the walls make it, and they end at 2.7 m. The
    old rule took the nearest edge of any part within 10 % of the height, so on a house every z from 0 to 5 m passed."""
    work = write_build(tmp_path / "w", **hut_with({"mép mái": "walls.top"}))
    r, res = run_proportion(tmp_path, work, marks=[mark("mép mái", 2.1)])
    assert (r.returncode, checked(res, "mép mái")) == (1, ("fail", 0.6, 0.074,
                                                          "mốc mép mái z 2.10 m; cạnh walls.top 2.70 m"))


@pytest.mark.parametrize("z, status", [(2.65, "pass"), (2.6, "fail")])
def test_the_tolerance_is_two_percent_of_the_height_g5(tmp_path, z, status):
    """2 % of the 3.7 m hut is 7.4 cm."""
    work = write_build(tmp_path / "w", **hut_with({"mép mái": "walls.top"}))
    _, res = run_proportion(tmp_path, work, marks=[mark("mép mái", z)])
    assert checked(res, "mép mái")[:3] == (status, round(2.7 - z, 3), 0.074)


@pytest.mark.parametrize("z, status", [(0.185, "pass"), (0.17, "fail")])
def test_the_tolerance_is_never_less_than_two_centimetres_g5(tmp_path, z, status):
    """A 0.2 m prop: 2 % is 4 mm, so the floor of 2 cm decides."""
    work = write_build(tmp_path / "w", rows=box_rows(1.0, 1.0, 0.2), sources={**HUT_SOURCES, "marks": {"a": "base.top"}})
    _, res = run_proportion(tmp_path, work, marks=[mark("a", z)])
    assert checked(res, "a")[:3] == (status, round(0.2 - z, 3), 0.02)


@pytest.mark.parametrize("edges, note", [
    ({}, "mốc mép mái: sources.json marks chưa khai cạnh part nào tạo mốc này"),
    ({"mép mái": "eave.top"}, "mốc mép mái: cạnh eave.top không có part eave"),
    ({"mép mái": "walls.middle"}, "mốc mép mái: cạnh 'walls.middle' phải là <part>.top hoặc <part>.bottom")])
def test_a_mark_without_a_valid_edge_fails_so_the_worker_must_name_the_part_g5(tmp_path, edges, note):
    work = write_build(tmp_path / "w", **hut_with(edges))
    r, res = run_proportion(tmp_path, work, marks=[mark("mép mái", 2.7)])
    assert (r.returncode, checked(res, "mép mái")) == (1, ("fail", None, None, note))


@pytest.mark.parametrize("z", ["2.7", "cao", None])
def test_a_mark_whose_height_is_not_a_number_is_a_card_error_in_one_line_g5(tmp_path, z):
    work = write_build(tmp_path / "w", **hut_with({"mép mái": "walls.top"}))
    r, res = run_proportion(tmp_path, work, marks=[mark("mép mái", z)])
    assert (r.returncode, len(r.stdout.strip().splitlines())) == (1, 1), r.stdout + r.stderr
    assert checked(res, "mép mái") == ("fail", None, None, f"thẻ: z_m của mốc mép mái phải là số mét, không phải {z!r}")


def test_marks_are_checked_beside_the_view_ratios_and_a_failed_mark_is_not_hidden_by_them_g5(tmp_path):
    work = write_build(tmp_path / "w", **hut_with({"gờ giữa": "walls.top"}))
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(400, 370)), marks=[mark("gờ giữa", 1.5)])
    assert (r.returncode, statuses(res)["proportion.front"], statuses(res)["proportion.mark.gờ giữa"]) == (1, "pass", "fail")


@pytest.mark.parametrize("marks", [None, []])
def test_a_card_without_marks_adds_no_check(tmp_path, marks):
    work = write_build(tmp_path / "w", rows=HUT_ROWS)
    r, res = run_proportion(tmp_path, work, marks=marks)
    assert (r.returncode, res["overall"], [c for c in statuses(res) if "mark" in c]) == (0, "not_checked", [])
