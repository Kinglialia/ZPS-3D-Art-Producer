"""measure.py --pick-best: after one regen, the view keeps the image with the better measure, and a view that still
fails gets the exact ACCEPTED_FAIL line. Pure rules on literal measure results first, then the tool on images."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_tools import TOOLS, checks, read, tool, wall_trim_gen, wall_trim_guides

spec = importlib.util.spec_from_file_location("views_measure", TOOLS / "measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def view_checks(view, iou, *failing, border=0, components=(2, 2)):
    """The checks measure.json holds for one view; `failing` names which of them fail."""
    c = [{"check": f"views.{view}", "status": "fail" if "views" in failing else "pass",
          "value": {"score": 70, "verdict": "fail", "iou": iou, "aspect_err": 0.04, "detail": 0.12, "detail_worst": None,
                    "max_delta_e": 9.4}},
         {"check": f"border.{view}", "status": "fail" if "border" in failing else "pass", "value": border},
         {"check": f"components.{view}", "status": "fail" if "components" in failing else "pass",
          "value": {"guide": components[0], "image": components[1]}},
         {"check": f"ring.{view}", "status": "info", "value": {"halo_share": 0.0}}]
    return c


def test_fewer_failing_checks_win_even_when_the_iou_is_lower():
    first = view_checks("back", 0.70, "views")
    now = view_checks("back", 0.90, "views", "components", components=(2, 3))
    assert measure.keep_first(first, now, "back") is True


def test_with_the_same_number_of_fails_the_higher_iou_wins():
    assert measure.keep_first(view_checks("back", 0.83, "views"), view_checks("back", 0.78, "views"), "back") is True
    assert measure.keep_first(view_checks("back", 0.78, "views"), view_checks("back", 0.83, "views"), "back") is False


def test_a_tie_keeps_the_regen_because_it_answers_the_fault_the_worker_named():
    assert measure.keep_first(view_checks("back", 0.8, "views"), view_checks("back", 0.8, "views"), "back") is False


def test_info_and_not_checked_do_not_count_as_fails_and_only_the_view_asked_for_is_scored():
    first = view_checks("back", 0.7, "views") + view_checks("left", 0.1, "views", "border", border=9)
    now = view_checks("back", 0.7, "views") + view_checks("left", 0.9)
    assert (measure.keep_first(first, now, "back"), measure.keep_first(first, now, "left")) == (False, False)


def test_a_view_without_an_iou_scores_below_any_measured_view():
    broken = [{"check": "views.back", "status": "fail", "value": None, "note": "thiếu ảnh"}]
    assert measure.keep_first(broken, view_checks("back", 0.2, "views"), "back") is False
    assert measure.keep_first(view_checks("back", 0.2, "views"), broken, "back") is True


def test_the_accepted_fail_line_has_the_file_name_the_numbers_and_no_semicolon():
    now = view_checks("back", 0.78, "views", "components", components=(2, 3))
    accepted, note = measure.accepted_lines(now, {"back": "regen"})
    assert note == ("measure.json — back (ảnh lần 2): iou 0.78, aspect_err 0.04, detail 0.12, max_delta_e 9.4, "
                    "số khối rời 3, guide 2")
    assert accepted == "ACCEPTED_FAIL: " + note and ";" not in note


def test_no_line_is_made_for_a_view_that_passes_or_was_not_compared():
    now = view_checks("back", 0.9) + view_checks("left", 0.4, "views")
    assert measure.accepted_lines(now, {"back": "first"}) is None
    assert measure.accepted_lines(now, {}) is None


GOOD = dict(trim="#2F4F4F")
MISPLACED = dict(trim="#2F4F4F", trim_x=150)


def pick(tmp_path, first, regen, *extra):
    """final/front.png holds the regen; work/gen holds both tries, as the worker keeps them."""
    gen = tmp_path / "work/gen"
    wall_trim_gen(gen / "front-1.png", **first)
    wall_trim_gen(gen / "front-2.png", **regen)
    f = tmp_path / "final"
    f.mkdir()
    shutil.copyfile(gen / "front-2.png", f / "front.png")
    g = wall_trim_guides(tmp_path / "guides")
    p = subprocess.run([sys.executable, str(TOOLS / "measure.py"), "--final", str(f), "--guides", str(g), "--views", "front",
                        "--pick-best", str(gen), *extra], capture_output=True, text=True)
    return p, f, gen


def test_a_regen_worse_than_the_first_image_is_replaced_by_the_first_and_the_set_is_measured_again(tmp_path):
    """The regen put the trim in the wrong place; the first image was right. Keeping the regen would ship a wrong view
    and pay Codex for it. The report and measure.json must describe the image that is kept."""
    p, f, gen = pick(tmp_path, GOOD, MISPLACED)
    assert p.returncode == 0, p.stdout
    assert (f / "front.png").read_bytes() == (gen / "front-1.png").read_bytes()
    data = read(f / "review/checks/measure.json")
    assert (data["overall"], data["data"]["picked"], data["data"]["regen"]) == ("pass", {"front": "first"}, [])
    assert "accepted_fail" not in data["data"]


def test_a_regen_better_than_the_first_image_stays_and_a_view_that_still_fails_gets_the_exact_lines(tmp_path):
    p, f, gen = pick(tmp_path, dict(MISPLACED, prop=True), MISPLACED)
    assert p.returncode == 1
    assert (f / "front.png").read_bytes() == (gen / "front-2.png").read_bytes()
    data = read(f / "review/checks/measure.json")["data"]
    assert data["picked"] == {"front": "regen"}
    lines = p.stdout.splitlines()
    assert lines[-2:] == [data["accepted_fail"], data["ngoai_le"]]
    assert data["accepted_fail"] == "ACCEPTED_FAIL: " + data["ngoai_le"]
    assert data["ngoai_le"].startswith("measure.json — front (ảnh lần 2): iou ") and "max_delta_e" in data["ngoai_le"]


def test_without_pick_best_the_tool_does_not_look_at_the_first_image(tmp_path):
    p, f, gen = pick(tmp_path, GOOD, MISPLACED)
    shutil.copyfile(gen / "front-2.png", f / "front.png")
    g = tmp_path / "guides"
    p = subprocess.run([sys.executable, str(TOOLS / "measure.py"), "--final", str(f), "--guides", str(g), "--views", "front"],
                       capture_output=True, text=True)
    assert p.returncode == 1 and "picked" not in read(f / "review/checks/measure.json")["data"]


def test_pick_best_with_no_other_first_image_changes_nothing_and_writes_no_line(tmp_path):
    p, f, gen = pick(tmp_path, MISPLACED, MISPLACED)
    (gen / "front-1.png").unlink()
    g = tmp_path / "guides"
    p = subprocess.run([sys.executable, str(TOOLS / "measure.py"), "--final", str(f), "--guides", str(g), "--views", "front",
                        "--pick-best", str(gen)], capture_output=True, text=True)
    data = read(f / "review/checks/measure.json")["data"]
    assert (p.returncode, "picked" in data, "accepted_fail" in data) == (1, False, False)


def test_a_regen_that_only_touches_the_image_border_is_compared_too_because_border_is_not_in_regen(tmp_path):
    """`border` and `components` fail measure.json without putting the view in the kit's `regen` list. The first image
    is clean; the regen is cut by the image edge. Keeping the regen would hand a failing view on."""
    g = wall_trim_guides(tmp_path / "guides")
    gen, f = tmp_path / "work/gen", tmp_path / "final"
    wall_trim_gen(gen / "front-1.png", **GOOD)
    touching = png_edge(gen / "front-2.png")
    f.mkdir()
    shutil.copyfile(touching, f / "front.png")
    p = subprocess.run([sys.executable, str(TOOLS / "measure.py"), "--final", str(f), "--guides", str(g), "--views", "front",
                        "--pick-best", str(gen)], capture_output=True, text=True)
    data = read(f / "review/checks/measure.json")
    assert (p.returncode, data["data"]["picked"]) == (0, {"front": "first"})
    assert (f / "front.png").read_bytes() == (gen / "front-1.png").read_bytes()


def png_edge(path):
    """The wall and trim of wall_trim_gen at the same proportions, pushed against the top and left edge."""
    from PIL import Image
    im = Image.new("RGB", (600, 600), "#E8E8E8")
    im.paste("#8B5A2B", (0, 0, 300, 450))
    im.paste("#2F4F4F", (300, 0, 450, 450))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path
