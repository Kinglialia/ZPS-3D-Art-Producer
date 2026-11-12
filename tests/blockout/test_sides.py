"""N1: render_sides.py draws the side views with one flat colour per material code, so the owner can judge at the blockout
gate which material sits where without a drawn image (D44.1)."""
import json
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image

from conftest import HUT_SOURCES, TOOLS, hut

VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
needs_blender = pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                   reason="needs Blender and tools/setup_deps.sh")
BG = (235, 235, 235)


def colours_in(codes, seed="0"):
    code = ("import sys; sys.path[:0] = [sys.argv[1] + '/lib', sys.argv[1] + '/self_build', sys.argv[1]]; "
            "import json, render_sides as RS; print(json.dumps({c: RS.hex_of(v) for c, v in RS.colours(sys.argv[2:]).items()}))")
    r = subprocess.run([str(VPY), "-c", code, str(TOOLS), *codes], capture_output=True, text=True, check=True,
                       env={**os.environ, "PYTHONHASHSEED": seed})
    return json.loads(r.stdout)


@needs_venv
def test_a_code_gets_the_same_colour_in_every_process_because_the_hue_is_a_sha256_and_not_hash(tmp_path):
    assert colours_in(["BARK", "LEAF"], "1") == colours_in(["BARK", "LEAF"], "2")
    assert colours_in(["BARK", "LEAF"]) == {"BARK": "#50B0E6", "LEAF": "#E6C650"}


@needs_venv
def test_two_codes_whose_hash_hues_nearly_agree_are_moved_apart_so_the_owner_can_tell_them_apart():
    """STONE and TIMBER hash to hues 0.82 and 0.79: the same purple. The later code in sorted order moves on."""
    got = colours_in(["STONE", "TIMBER", "TEAL"])
    assert got["STONE"] == "#DA50E6" and got["TEAL"] == "#E6505F" and got["TIMBER"] != "#BA50E6"
    import colorsys
    hues = sorted(colorsys.rgb_to_hsv(*(int(v[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] for v in got.values())
    gaps = [b - a for a, b in zip(hues, hues[1:] + [hues[0] + 1])]
    assert min(gaps) >= 0.1


def sides(tmp_path, *extra, size=400):
    f = tmp_path / "final"
    f.mkdir()
    (f / "part_graph.json").write_text(json.dumps(hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True, check=True)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(TOOLS / "render_sides.py"), "--", "--work",
                        str(f), "--size", str(size), *extra], capture_output=True, text=True)
    return f, r


def flat_colours(path, model_w):
    """Distinct colours of the model area that are not the background, with their pixel counts."""
    import numpy as np
    px = np.asarray(Image.open(path).convert("RGB"))[:, :model_w].reshape(-1, 3)
    px = px[(px != BG).any(1)]
    cols, counts = np.unique(px, axis=0, return_counts=True)
    return {tuple(int(x) for x in c): int(n) for c, n in zip(cols, counts)}


@pytest.mark.blender
@needs_blender
def test_a_graph_with_3_material_codes_gives_images_with_exactly_3_flat_colours(tmp_path):
    """No outline and no anti-aliasing, so an edge pixel is one of the three colours too: the model area holds those
    three colours and nothing else, each one the colour the legend gives its code."""
    f, r = sides(tmp_path)
    doc = json.loads((f / "review/sides.json").read_text(encoding="utf-8"))
    assert sorted(doc["artifacts"]) == ["mat_back", "mat_left", "mat_right"], r.stdout[-400:]
    want = colours_in(["STONE", "TIMBER", "TEAL"])
    for label, info in doc["data"]["sides"].items():
        got = flat_colours(f / f"review/{label}.png", info["model_px"][0])
        expect = {tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in want.values()}
        assert info["codes"] == want
        assert len(got) == 3 and all(any(max(abs(a - b) for a, b in zip(c, e)) <= 2 for e in expect) for c in got), (label, got)
        assert min(got.values()) > 100, got


@pytest.mark.blender
@needs_blender
def test_the_legend_names_every_code_in_black_beside_its_swatch_and_leaves_the_model_area_alone(tmp_path):
    import numpy as np
    f, _ = sides(tmp_path)
    info = json.loads((f / "review/sides.json").read_text(encoding="utf-8"))["data"]["sides"]["mat_left"]
    img = np.asarray(Image.open(f / "review/mat_left.png").convert("RGB")).astype(int)
    margin = img[:, info["model_px"][0]:]
    assert img.shape[1] > info["model_px"][0] and int(margin.min()) < 40
    swatches = {tuple(c) for c in margin.reshape(-1, 3) if tuple(c) != (235, 235, 235)}
    assert {tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in info["codes"].values()} <= swatches


@pytest.mark.blender
@needs_blender
def test_top_adds_the_fourth_view_only_when_asked(tmp_path):
    f, _ = sides(tmp_path, "--top")
    assert sorted(p.stem for p in (f / "review").glob("mat_*.png")) == ["mat_back", "mat_left", "mat_right", "mat_top"]
    assert len(flat_colours(f / "review/mat_top.png", 400)) >= 3


@pytest.mark.blender
@needs_blender
def test_the_review_render_makes_the_side_views_in_the_same_blender_session(tmp_path):
    f, _ = sides(tmp_path)
    shutil.rmtree(f / "review")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(TOOLS / "render_review.py"), "--", "--work",
                        str(f), "--size", "256"], capture_output=True, text=True)
    doc = json.loads((f / "review/review.json").read_text(encoding="utf-8"))
    assert {"mat_left", "mat_right", "mat_back"} <= set(doc["artifacts"]), r.stdout[-400:]
    assert "mat_top" not in doc["artifacts"] and sorted(doc["data"]["sides"]) == ["mat_back", "mat_left", "mat_right"]
