"""L6: prep_overlay.py is the step between the full build and the review render: mask, spec, camera of a 3/4 concept and the
proportion check that gate_all.py could not run before the spec existed."""
import json
import subprocess

import pytest
from PIL import Image, ImageDraw

from conftest import HUT_SOURCES, TOOLS, hut

VPY = TOOLS / ".deps/venv/bin/python"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
KEY, INK = (0, 177, 64), (180, 120, 60)
SILHOUETTE = """import sys
sys.path[:0] = [sys.argv[1] + "/lib", sys.argv[1] + "/self_build"]
import numpy as np, graph as G, raster
from PIL import Image
v, t, _ = G.load_glb(sys.argv[2])
m = raster.silhouette(v, t, raster.camera_dir(float(sys.argv[3]), float(sys.argv[4])), size=400)[0]
img = np.zeros(m.shape + (3,), np.uint8); img[:] = (0, 177, 64); img[m > 0] = (180, 120, 60)
Image.fromarray(img).save(sys.argv[5])
"""


def final(tmp_path):
    f = tmp_path / "production/assets/hut/blockout/v1/final"
    f.mkdir(parents=True)
    (f / "part_graph.json").write_text(json.dumps(hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True, check=True)
    return f


def concept(path, w, h):
    im = Image.new("RGB", (w + 80, h + 80), KEY)
    ImageDraw.Draw(im).rectangle((40, 40, 39 + w, 39 + h), fill=INK)
    im.save(path)
    return path


def prep(f, *args):
    r = subprocess.run([str(VPY), str(TOOLS / "prep_overlay.py"), "--work", str(f), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip().splitlines()


@needs_venv
def test_a_front_concept_gets_a_mask_a_spec_and_a_proportion_check_that_passes_in_one_line(tmp_path):
    f = final(tmp_path)
    img = concept(tmp_path / "front.png", 400, 370)
    rc, lines = prep(f, "--view", f"front={img}")
    spec = f.parent / "work/spec.json"
    assert (rc, len(lines)) == (0, 1), lines
    assert json.loads(spec.read_text(encoding="utf-8")) == {"concept": {"views": {"front": "masks/front.png"}}}
    assert Image.open(f.parent / "work/masks/front.png").getbbox() == (40, 40, 440, 410)
    prop = json.loads((f / "review/checks/proportion.json").read_text(encoding="utf-8"))
    assert [c["status"] for c in prop["checks"] if c["check"] == "proportion.front"] == ["pass"]


@needs_venv
def test_gate_all_before_the_spec_cannot_check_the_proportion_and_prep_overlay_after_it_does(tmp_path):
    """The reason prep_overlay runs check_proportion itself: the first gate_all pass has no mask to compare with."""
    f = final(tmp_path)
    gate = subprocess.run([str(VPY), str(TOOLS / "gate_all.py"), "--work", str(f), "--skip", "check_inputs"],
                          capture_output=True, text=True)
    before = json.loads((f / "review/checks/proportion.json").read_text(encoding="utf-8"))["overall"]
    prep(f, "--view", f"front={concept(tmp_path / 'front.png', 400, 370)}")
    after = json.loads((f / "review/checks/proportion.json").read_text(encoding="utf-8"))["overall"]
    assert (gate.returncode, before, after) == (0, "not_checked", "pass")


@needs_venv
def test_a_concept_of_the_wrong_proportion_prints_the_failing_check_and_exits_1(tmp_path):
    f = final(tmp_path)
    rc, lines = prep(f, "--view", f"front={concept(tmp_path / 'front.png', 450, 370)}")
    assert rc == 1 and lines[0].startswith("review/checks/proportion.json: proportion.front -0.111")
    assert lines[-1] == "prep_overlay fail: 1 failing"


@needs_venv
def test_the_other_keys_of_an_existing_spec_stay(tmp_path):
    f = final(tmp_path)
    spec = f.parent / "work/spec.json"
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps({"config": {"self_build": {"render_size": 256}}, "concept": {"background": "#00B140"}}),
                    encoding="utf-8")
    prep(f, "--view", f"front={concept(tmp_path / 'front.png', 400, 370)}")
    assert json.loads(spec.read_text(encoding="utf-8")) == {
        "config": {"self_build": {"render_size": 256}},
        "concept": {"background": "#00B140", "views": {"front": "masks/front.png"}}}


@needs_venv
def test_a_34_concept_gets_its_camera_from_fit_view_on_the_side_given_and_needs_that_side(tmp_path):
    f = final(tmp_path)
    img = tmp_path / "34.png"
    subprocess.run([str(VPY), "-c", SILHOUETTE, str(TOOLS), str(f / "assembled.glb"), "-35", "20", str(img)], check=True)
    rc, lines = prep(f, "--view", f"34={img}")
    assert (rc, lines) == (2, ["prep_overlay refused: a 34 view needs --side left|right, the card's view_side (brief line "
                               "VIEW_SIDE:). The brief has none: the card needs view_side"])
    assert not (f.parent / "work/spec.json").exists()
    rc, lines = prep(f, "--view", f"34={img}", "--side", "left")
    cam = json.loads((f.parent / "work/spec.json").read_text(encoding="utf-8"))["concept"]["cameras"]["34"]
    assert rc == 0 and -40 <= cam["azimuth_deg"] <= -30 and 15 <= cam["elevation_deg"] <= 25, (lines, cam)
    assert "camera 34 az " in lines[0]


@needs_venv
@pytest.mark.parametrize("args, why", [
    ([], "give at least one --view"),
    (["--view", "front"], "--view front: want <front|back|left|right|top|34>=<image>"),
    (["--view", "bottom=x.png"], "--view bottom=x.png: want <front|back|left|right|top|34>=<image>"),
    (["--view", "front=/nowhere.png"], "--view front=/nowhere.png: no such image")])
def test_a_missing_view_a_wrong_view_name_and_a_missing_image_are_refused_before_anything_is_written(tmp_path, args, why):
    f = final(tmp_path)
    rc, lines = prep(f, *args)
    assert (rc, lines, (f.parent / "work").exists()) == (2, [f"prep_overlay refused: {why}"], False)


@needs_venv
def test_the_card_goes_on_to_the_proportion_check_so_the_rerun_keeps_the_marks_g5(tmp_path):
    """gate_all.py runs check_proportion with the card; prep_overlay reruns it and writes the same file, so a rerun without
    the card would erase a failed mark."""
    f = final(tmp_path)
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES | {"marks": {"gờ giữa": "walls.top", "mép mái": "walls.top"}}),
                                    encoding="utf-8")
    card = tmp_path / "asset-card.yaml"
    card.write_text("marks:\n- {name: gờ giữa, z_m: 1.5}\n- {name: mép mái, z_m: 2.7}\n", encoding="utf-8")
    rc, lines = prep(f, "--view", f"front={concept(tmp_path / 'front.png', 400, 370)}", "--card", str(card))
    assert rc == 1 and lines[0].startswith("review/checks/proportion.json: proportion.mark.gờ giữa 1.2 (limit 0.074)")
    assert lines[-1] == "prep_overlay fail: 1 failing"
    rc, lines = prep(f, "--view", f"front={concept(tmp_path / 'front.png', 400, 370)}")
    assert (rc, len(lines)) == (0, 1)
