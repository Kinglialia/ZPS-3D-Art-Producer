"""VẼ MỚI projection (row T5). The 8 paintings are made one by one, so their strokes never line up: a face that two views
see must take one view, not a blend that ghosts and blurs. A painting the generator moved off its guide would put
background or a neighbour material on the model, and a missing painting would leave flat fill; both stop the tool
and name the view to make again."""
import json
import sys

import numpy as np
import pytest

import glbkit
from paintkit import EIGHT, paint_dir
from texkit import AID, TOOLS, face_name, model_final, tool

sys.path.insert(0, str(TOOLS / "lib"))
import tex  # noqa: E402

RES = 128
RED, BLUE, GREEN = (200, 30, 30), (30, 30, 200), (30, 160, 40)
TWO = [(0, 0, 30), (1, 45, -30)]
FRONT_THREE = [(7, 315, -30), (0, 0, 30), (1, 45, -30)]


@pytest.fixture
def m(tmp_path):
    return model_final(tmp_path / "model", RES)


def project(m, paint):
    rc, out = tool("project_views.py", "--glb", m / f"{AID}-untextured.glb", "--model", m, "--views", paint, "--base",
                   paint / "base_fill.png", "--res", RES, "--out", paint / "projected.png", "--padding", "2")
    return rc, out, json.loads((paint / "projected.json").read_text())


def face_texels(m, paint, name):
    g, tm = tex.load_map(m / f"{AID}-untextured.glb", RES)
    sel = tm.inside & (np.vectorize(face_name)(np.where(tm.inside, tm.face, 0)) == name)
    return tex.load_rgb(paint / "projected.png")[sel]


def mixed_share(px, colours, tol=6):
    near = np.stack([np.abs(px - c).max(-1) <= tol for c in colours]).any(0)
    return float((~near).mean())


def test_a_face_three_views_see_takes_one_view_not_a_blend_of_them(m, tmp_path):
    """The front face is seen by its own view (cos 0.87) and by both neighbours (0.61). Its edge texels, which the
    front view's shrunk silhouette leaves out, take one neighbour each; no texel is a blend."""
    paint = paint_dir(tmp_path / "paint", FRONT_THREE, {7: GREEN, 0: RED, 1: BLUE})
    rc, out, r = project(m, paint)
    assert rc == 0, out
    front = face_texels(m, paint, "-Y")
    assert mixed_share(front, (RED, BLUE, GREEN)) < 0.02
    assert (np.abs(front - RED).max(-1) <= 6).mean() > 0.9


def test_a_painting_moved_off_its_guide_is_not_projected_and_is_named_for_a_new_gen(m, tmp_path):
    paint = paint_dir(tmp_path / "paint", TWO, {0: RED, 1: BLUE}, shift={0: (8, 0)})
    rc, out, r = project(m, paint)
    assert (rc, r["redo"]) == (1, ["paint_0.png"])
    assert r["registration"]["paint_0.png"]["offset_px"] == [8, 0]
    assert r["registration"]["paint_1.png"]["offset_px"] == [0, 0] and r["registration"]["paint_1.png"]["iou"] > 0.99
    assert "gen lại paint_0.png" in out
    assert np.abs(face_texels(m, paint, "-Y") - BLUE).max(-1).max() <= 2


def test_a_missing_painting_stops_the_tool_and_is_named(m, tmp_path):
    paint = paint_dir(tmp_path / "paint", TWO, {0: RED, 1: BLUE}, missing=(1,))
    rc, out, r = project(m, paint)
    assert (rc, r["redo"], r["skipped"]) == (1, ["paint_1.png"], {"paint_1.png": "thiếu file"})
    assert "gen lại paint_1.png" in out


def test_a_painting_of_another_aspect_is_named_so_only_that_view_is_painted_again(m, tmp_path):
    from PIL import Image
    paint = paint_dir(tmp_path / "paint", TWO, {0: RED, 1: BLUE})
    Image.new("RGB", (100, 100), BLUE).save(paint / "paint_1.png")
    rc, out, r = project(m, paint)
    assert (rc, r["redo"], r["skipped"]) == (1, ["paint_1.png"], {"paint_1.png": "100x100 khác tỉ lệ guide 768x512"})


def test_eight_good_paintings_paint_every_texel_of_the_box_and_exit_0(m, tmp_path):
    """No texel keeps the flat base fill. A texel at a box corner that every shrunk silhouette leaves out takes the
    mean of its face."""
    colours = {k: (40 + 20 * k, 180 - 15 * k, 60 + 10 * k) for k in range(8)}
    paint = paint_dir(tmp_path / "paint", EIGHT, colours)
    rc, out, r = project(m, paint)
    assert (rc, r["redo"], r["share"]["base"], r["share"]["code_side"]) == (0, [], 0.0, 0.0), out
    assert r["share"]["projected"] >= 0.999, r["share"]
    for name in ("-Y", "+Y", "-X", "+X", "+Z", "-Z"):
        assert mixed_share(face_texels(m, paint, name), list(colours.values())) < 0.02, name


def bent_strip(d):
    """A front wall and a wall turned 40 degrees from it, ONE UV island joined along their shared edge at u = 0.45. The
    front view wins the front wall and the 45 degree view the turned one; both see the edge."""
    v = np.array([[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, -0.5, 1], [-0.5, -0.5, 1], [1.266, 0.143, 0], [1.266, 0.143, 1]])
    uv = np.array([[0.1, 0.1], [0.45, 0.1], [0.45, 0.9], [0.1, 0.9], [0.8, 0.1], [0.8, 0.9]])
    f = np.array([[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2]])
    (d / "parts").mkdir(parents=True)
    (d / "review").mkdir()
    glbkit.write(d / f"{AID}-untextured.glb", v, uv, f)
    glbkit.write(d / "parts/body.glb", v, np.zeros((len(v), 2)), f)
    (d / "part_graph.json").write_text(json.dumps({"parts": [{"name": "body", "material": "TIMBER"}]}))
    (d / "review/join.json").write_text(json.dumps({"checks": [{"check": "join.origin_offset_m", "value": [0, 0, 0]}]}))
    (d / "spec.json").write_text(json.dumps({"asset": AID, "uv": {"resolution": RES}}))
    return d, (v, f)


def test_two_winners_in_one_island_blend_only_in_a_narrow_band_along_their_border(tmp_path):
    m, mesh = bent_strip(tmp_path / "model")
    paint = paint_dir(tmp_path / "paint", [(0, 0, 30), (1, 45, 30)], {0: RED, 1: BLUE}, mesh=mesh)
    rc, out, r = project(m, paint)
    assert rc == 0, out
    g, tm = tex.load_map(m / f"{AID}-untextured.glb", RES)
    img = tex.load_rgb(paint / "projected.png")
    near = (np.abs(img - RED).max(-1) <= 6) | (np.abs(img - BLUE).max(-1) <= 6)
    cols = np.nonzero(tm.inside & ~near)[1]
    edge = 0.45 * RES - 0.5
    assert len(cols) > 0 and np.abs(cols - edge).max() <= 3, sorted(set(cols.tolist()))
