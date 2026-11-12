"""Repair by crop (row T11). An image generator returns 1536x1024 or 1024x1536, and it may move or redraw the whole image.
So cut pads the crop to one of those shapes with the atlas round it, paste takes any size of that shape, and an edit
that changed the pad round the box is refused before it puts a shifted patch on the model. After a paste the gutter
round the islands is grown again from the new colours, so mip levels do not bleed the old ones."""
import json
import sys

import numpy as np
import pytest
from PIL import Image

from texkit import AID, TOOLS, face_name, model_final, tool

sys.path.insert(0, str(TOOLS / "lib"))
import tex  # noqa: E402

RES = 128
BOX = (20, 30, 60, 50)


@pytest.fixture
def m(tmp_path):
    return model_final(tmp_path / "model", RES)


def stripes(n=RES):
    """Vertical stripes 16 px apart, so a moved image differs from the one sent."""
    x = np.arange(n)
    row = 128 + 100 * np.sin(2 * np.pi * x / 16)
    return np.repeat(np.stack([row, 255 - row, np.full(n, 90.0)], -1)[None], n, 0).round().astype(np.uint8)


def cut(tmp, img, box=BOX, margin=8):
    Image.fromarray(img).save(tmp / "a.png")
    rc, out = tool("crop_edit.py", "cut", "--albedo", tmp / "a.png", "--box", ",".join(map(str, box)), "--margin",
                   margin, "--out", tmp / "c")
    return rc, out, json.loads((tmp / "c/crop.json").read_text()) if rc == 0 else None


def edit(tmp, meta, size, colour=(255, 0, 0), roll=0):
    """send.png scaled to size, the box painted one colour, the whole image moved `roll` px to the right."""
    send = Image.open(tmp / "c/send.png").resize(size, Image.LANCZOS)
    a = np.asarray(send).copy()
    (x0, y0, x1, y1), (px0, py0, px1, py1) = meta["box"], meta["pad"]
    k = size[0] / (px1 - px0)
    a[round((y0 - py0) * k):round((y1 - py0) * k), round((x0 - px0) * k):round((x1 - px0) * k)] = colour
    Image.fromarray(np.roll(a, roll, 1)).save(tmp / "edited.png")
    return tmp / "edited.png"


def paste(tmp, m, edited, *extra):
    rc, out = tool("crop_edit.py", "paste", "--albedo", tmp / "a.png", "--crop", tmp / "c", "--edited", edited,
                   "--glb", m / f"{AID}-untextured.glb", "--out", tmp / "b.png", *extra)
    return rc, out


def test_cut_pads_the_crop_to_3_2_with_the_atlas_round_it_and_sends_1536x1024(tmp_path):
    img = stripes()
    rc, out, meta = cut(tmp_path, img)
    assert (rc, out) == (0, f"[crop_edit] crop 56x36, đệm 57x38 (3:2), gửi 1536x1024 -> {tmp_path}/c/send.png\n")
    assert (meta["crop"], meta["pad"], meta["send"]) == ([12, 22, 68, 58], [12, 21, 69, 59], [1536, 1024])
    assert np.array_equal(np.asarray(Image.open(tmp_path / "c/crop.png")), img[21:59, 12:69])


def test_a_tall_crop_is_padded_to_2_3(tmp_path):
    rc, out, meta = cut(tmp_path, stripes(), box=(40, 10, 50, 100), margin=4)
    assert (meta["crop"], meta["pad"], meta["send"]) == ([36, 6, 54, 104], [12, 6, 78, 105], [1024, 1536])


def test_a_pad_past_the_atlas_edge_is_moved_inside_it(tmp_path):
    rc, out, meta = cut(tmp_path, stripes(), box=(0, 0, 30, 10), margin=0)
    assert (meta["crop"], meta["pad"]) == ([0, 0, 30, 10], [0, 0, 30, 20])


def test_an_edit_of_the_same_shape_but_another_size_is_pasted_inside_the_box_only(m, tmp_path):
    img = stripes()
    _, _, meta = cut(tmp_path, img)
    rc, out = paste(tmp_path, m, edit(tmp_path, meta, (2304, 1536)), "--feather", "4", "--padding", "4")
    assert rc == 0, out
    got = np.asarray(Image.open(tmp_path / "b.png"))
    tm = tex.load_map(m / f"{AID}-untextured.glb", RES)[1]
    outside = np.ones((RES, RES), bool)
    outside[30:50, 20:60] = False
    assert tuple(got[40, 40]) == (255, 0, 0)
    assert np.array_equal(got[outside & tm.inside], img[outside & tm.inside])
    rec = json.loads((tmp_path / "b.json").read_text())
    assert (rec["status"], rec["changed_outside"]) == ("ok", 0) and rec["ring_diff"] < 2


def test_an_edit_that_moved_the_image_is_refused_and_writes_nothing(m, tmp_path):
    _, _, meta = cut(tmp_path, stripes())
    rc, out = paste(tmp_path, m, edit(tmp_path, meta, (1536, 1024), roll=77))
    assert rc == 1 and not (tmp_path / "b.png").exists()
    assert out.startswith("[crop_edit] vùng quanh chỗ sửa bị dời hoặc đổi (lệch ") and out.endswith(
        "): bỏ kết quả, gen lại\n")


def test_an_edit_of_another_shape_is_refused_and_writes_nothing(m, tmp_path):
    cut(tmp_path, stripes())
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "edited.png")
    rc, out = paste(tmp_path, m, tmp_path / "edited.png")
    assert (rc, out, (tmp_path / "b.png").exists()) == (
        1, "[crop_edit] ảnh sửa 64x64 khác tỉ lệ ảnh gửi 1536x1024: bỏ kết quả\n", False)


def test_the_gutter_next_to_a_pasted_island_edge_takes_the_new_colour(m, tmp_path):
    tm = tex.load_map(m / f"{AID}-untextured.glb", RES)[1]
    flat = tex.gutter(np.where(tm.inside[..., None], np.full(3, 90.0), 0.0), tm.inside, 8).round().astype(np.uint8)
    rows, cols = np.nonzero(tm.inside & (np.vectorize(face_name)(np.where(tm.inside, tm.face, 0)) == "-Y"))
    y, x = int(np.median(rows)), int(cols.min())
    _, _, meta = cut(tmp_path, flat, box=(x, y - 8, x + 12, y + 8), margin=4)
    rc, out = paste(tmp_path, m, edit(tmp_path, meta, tuple(meta["send"])), "--feather", "1", "--padding", "4")
    assert rc == 0, out
    got = np.asarray(Image.open(tmp_path / "b.png")).astype(int)
    assert tuple(got[y, x]) != (90, 90, 90) and tuple(got[y, x - 2]) == tuple(got[y, x])
    assert tuple(got[y, x - 6]) == (90, 90, 90)
