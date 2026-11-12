"""Part numbers and the legend of parts_<view>.png: the kit draws the legend in white on a light grey margin."""
import json
import subprocess

import pytest

from conftest import TOOLS

VPY = TOOLS / ".deps/venv/bin/python"
pytestmark = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh (numpy, cv2, Pillow)")

MEASURE = """
import json, sys
sys.path[:0] = [sys.argv[1], sys.argv[1] + "/self_build", sys.argv[1] + "/lib"]
import numpy as np
from PIL import Image
import render_views as RV
import render_critic as RC

BLUE, RED = (0.2, 0.3, 0.9), (0.9, 0.2, 0.2)
LEGEND = [(1, "walls", BLUE), (2, "roof", RED), (3, "hidden_back_wall", (0.5, 0.5, 0.5))]


def draw(fn, path, w=640, h=480, legend=LEGEND, max_edge=1568):
    img = np.full((h, w, 3), RV.BG_SRGB, np.uint8)
    img[100:300, 80:300] = [round(c * 255) for c in BLUE]
    img[100:200, 340:560] = [round(c * 255) for c in RED]
    Image.fromarray(img).save(path)
    visible = fn(path, [(1, BLUE), (2, RED)], legend, max_edge)
    return visible, np.asarray(Image.open(path).convert("L")).astype(int)


out = {}
for name, fn in (("kit", RC.KIT_LABEL), ("own", RC.label_parts)):
    visible, g = draw(fn, sys.argv[2] + "/" + name + ".png")
    text = g[:, 640 + 80:]
    out[name] = {"visible": visible, "text_min": int(text.min()), "text_dark": int((text < 120).sum()),
                 "width": g.shape[1], "left": g[:, :640].tolist() if name else None}
out["same_left"] = out["kit"].pop("left") == out["own"].pop("left")
legend = [(i, "part_%d" % i, BLUE) for i in range(1, 15)]
_, g = draw(RC.label_parts, sys.argv[2] + "/long.png", w=320, h=120, legend=legend, max_edge=400)
out["long"] = list(g.shape[::-1])
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    r = subprocess.run([str(VPY), "-c", MEASURE, str(TOOLS), str(tmp_path_factory.mktemp("legend"))],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_kit_legend_is_white_on_light_grey_so_no_pixel_of_a_word_is_darker_than_the_margin(drawn):
    assert drawn["kit"]["text_min"] >= 235


def test_the_legend_words_are_dark_on_the_light_margin_so_a_reviewer_can_read_which_number_is_which_part(drawn):
    assert drawn["own"]["text_min"] < 60 and drawn["own"]["text_dark"] > 300
    assert drawn["own"]["visible"] == [1, 2]


def test_the_numbers_on_the_parts_and_the_image_width_stay_as_the_kit_draws_them(drawn):
    assert drawn["same_left"] is True and drawn["own"]["width"] == drawn["kit"]["width"]


def test_a_long_legend_makes_the_image_taller_and_the_long_edge_cap_still_holds(drawn):
    width, height = drawn["long"]
    assert max(width, height) <= 400 and height > 120 * 400 / width
