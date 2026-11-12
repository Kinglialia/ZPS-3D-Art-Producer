"""VẼ MỚI projection (row T5). The 8 paintings are made one by one, so their strokes never line up: a face that two views
see must take one view, not a blend that ghosts and blurs. A painting the generator moved off its guide would put
background or a neighbour material on the model, and a missing painting would leave flat fill; both stop the tool
and name the view to make again."""
import json
import sys

import numpy as np
import pytest

import glbkit
from paintkit import EIGHT, H, W, paint_dir
from texkit import AID, TOOLS, face_name, model_final, tool

sys.path.insert(0, str(TOOLS / "lib"))
import project_views  # noqa: E402
import render_texture  # noqa: E402
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


def silhouette(size, azimuth, elevation=30):
    v, _, f = glbkit.box(size)
    cam = render_texture.ortho(v, render_texture.camera_dir(azimuth, elevation), None, W, H)
    return np.isfinite(project_views.zbuffer(cam, v, f))


def grown(mask, px):
    """mask grown (px > 0) or shrunk (px < 0) by |px| pixels, 4-neighbour steps, as a painter's edge drifts."""
    out = mask.copy()
    for _ in range(abs(px)):
        s = out.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s = (s | np.roll(out, (dy, dx), (0, 1))) if px > 0 else (s & np.roll(out, (dy, dx), (0, 1)))
        out = s
    return out


def painting(mask, outline=None):
    """One flat colour inside mask on a white background; outline: a dark mask drawn under the colour."""
    im = np.full(mask.shape + (4,), 255.0)
    if outline is not None:
        im[outline, :3] = (30, 20, 10)
    im[mask, :3] = (120, 90, 60)
    return im


def bars(rects):
    m = np.zeros((H, W), bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


def verdict(im, guide):
    iou, off = project_views.registration(im, guide.astype(float) * 255)
    return project_views.accepted(iou, off), off


LAMP_POST = [(380, 40, 388, 470), (360, 40, 408, 60)]
PICKETS = [(150 + 80 * k, 200, 156 + 80 * k, 400) for k in range(6)] + [(150, 260, 556, 268)]


@pytest.mark.parametrize("size", [(4.0, 3.0, 3.5), (2.0, 0.6, 1.2)])
@pytest.mark.parametrize("azimuth", [0, 90, 180, 270])
def test_a_painting_one_pixel_inside_a_rectangular_guide_is_kept(size, azimuth):
    """A painter's edge lands a pixel inside the guide. On a flat-sided box view the phase-only peak used to jump to
    hundreds of px ([359, 47] at az 0), so a good painting went to a paid repaint that failed the same way."""
    g = silhouette(size, azimuth)
    assert verdict(painting(grown(g, -1)), g) == (True, [0, 0])


@pytest.mark.parametrize("rects", [LAMP_POST, PICKETS], ids=["lamp post 8 px", "pickets 6 px"])
def test_thin_parts_painted_a_pixel_wider_or_with_a_2_px_outline_are_kept(rects):
    """Plain IoU of an 8 px post painted a pixel wider is 0.82 and of 6 px pickets with a 2 px dark outline 0.62: a
    band of 2 px around each mask is not an error of the painting."""
    g = bars(rects)
    assert verdict(painting(grown(g, 1)), g) == (True, [0, 0])
    assert verdict(painting(g, outline=grown(g, 2)), g)[0] is True


def test_a_painting_moved_8_px_is_rejected_and_the_move_is_reported():
    g = silhouette((4.0, 3.0, 3.5), 0)
    assert verdict(painting(np.roll(grown(g, -1), 8, 1)), g) == (False, [8, 0])


def test_a_blank_painting_or_one_of_another_shape_is_rejected():
    g = bars(LAMP_POST)
    assert verdict(painting(np.zeros_like(g)), g)[0] is False
    assert verdict(painting(silhouette((4.0, 3.0, 3.5), 0)), g)[0] is False
