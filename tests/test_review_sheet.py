"""D31.1 (R1): the reviewer gets one sheet of the step's renders, and an image on disk without a worker round.
Pilot run: reviewers spent over a million tokens, much of it opening one render at a time."""
import json

import pytest
from PIL import Image

from shared import finding
from test_loop import AID, counts, flow  # noqa: F401  (flow is the blockout-only fixture)

import review_sheet
from core.state import TEMPLATES, save_st

RENDERS = ["review/game_cam.png", "review/renders/clay_front.png", "review/renders/parts_34.png"]
FULL = ["review/game_cam.png", "review/lineup.png", "review/foot_front_left.png", "review/foot_front_right.png",
        *[f"review/renders/{k}_{v}.png" for k in ("clay", "normal") for v in ("front", "back", "left", "right", "34")],
        *[f"review/renders/overlay_{v}.png" for v in ("front", "back", "left", "right")],
        "review/renders/parts_front.png", "review/renders/parts_34.png", "review/renders/prev_34.png",
        "review/mat_left.png", "review/mat_right.png", "review/mat_back.png"]


def png(p, size=(400, 300), colour=(90, 60, 30)):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(p)


def tile_at(page, box):
    """The colour at the middle of a tile box on a page image."""
    x0, y0, x1, y1 = box
    return page.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))


def test_more_than_eight_images_go_to_further_pages_and_sheet_json_maps_each_label_to_its_page_and_box(tmp_path):
    """Pilot run: 20 tiles shared one 2048 px image, about 300 px a tile after the vision input shrank it, so a wire
    line or a seam could not be seen. Each page holds at most 8 tiles; a label still names one image."""
    for i in range(20):
        png(tmp_path / f"final/review/r{i:02d}.png", (400, 300), (10 * i, 255 - 10 * i, 40))
    tiles = review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/*.png"])
    placed = json.loads((tmp_path / "review/sheet.json").read_text(encoding="utf-8"))
    assert sorted(tiles) == sorted(placed) == [f"r{i:02d}" for i in range(20)]
    assert sorted(p.name for p in (tmp_path / "review").glob("*.png")) == ["sheet-2.png", "sheet-3.png", "sheet.png"]
    per_page = {}
    for label, t in placed.items():
        per_page.setdefault(t["page"], []).append(label)
        assert t["src"] == tiles[label] == f"final/review/{label}.png"
        with Image.open(tmp_path / t["page"]) as page:
            n = int(label[1:])
            assert tile_at(page.convert("RGB"), t["box"]) == (10 * n, 255 - 10 * n, 40), label
            assert max(page.size) <= review_sheet.LONG_EDGE
    assert {k: len(v) for k, v in per_page.items()} == {"review/sheet.png": 7, "review/sheet-2.png": 7, "review/sheet-3.png": 6}
    assert review_sheet.pages(tmp_path / "review/sheet.png") == [tmp_path / "review" / n for n in (
        "sheet.png", "sheet-2.png", "sheet-3.png")]


def test_a_full_page_gives_each_tile_a_cell_over_480_px_where_twenty_tiles_gave_300(tmp_path):
    for i in range(8):
        png(tmp_path / f"final/review/r{i}.png", (1024, 1024))
    review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/*.png"])
    placed = json.loads((tmp_path / "review/sheet.json").read_text(encoding="utf-8"))
    cells = {(t["box"][2] - t["box"][0], t["box"][3] - t["box"][1]) for t in placed.values()}
    assert len(cells) == 1 and min(cells.pop()) >= 480
    with Image.open(tmp_path / "review/sheet.png") as im:
        assert max(im.size) <= 1568


def test_a_rebuild_with_fewer_images_leaves_no_page_of_the_old_sheet(tmp_path):
    for i in range(10):
        png(tmp_path / f"final/review/r{i}.png")
    review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/*.png"])
    (tmp_path / "final/review/r9.png").unlink()
    (tmp_path / "final/review/r8.png").unlink()
    review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/*.png"])
    assert sorted(p.name for p in (tmp_path / "review").glob("*.png")) == ["sheet.png"]


def test_a_native_tile_keeps_every_pixel_of_a_small_image_and_cuts_a_big_one_instead_of_scaling_it(tmp_path):
    """The thumbnail rubric judges legibility at game size: a scaled thumb would judge another size."""
    thumb = Image.new("RGB", (97, 61), "white")
    for x in range(97):
        thumb.putpixel((x, x % 61), (200, 10, 10))
    (tmp_path / "final/review").mkdir(parents=True)
    thumb.save(tmp_path / "final/review/thumb.png")
    png(tmp_path / "final/review/big.png", (2000, 2000), (0, 0, 255))
    review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["native:final/review/thumb.png", "native:final/review/big.png"])
    placed = json.loads((tmp_path / "review/sheet.json").read_text(encoding="utf-8"))
    with Image.open(tmp_path / "review/sheet.png") as page:
        page = page.convert("RGB")
        x0, y0, x1, y1 = placed["thumb"]["box"]
        left, top = x0 + (x1 - x0 - 97) // 2, y0 + (y1 - y0 - 61) // 2
        assert page.crop((left, top, left + 97, top + 61)).tobytes() == thumb.tobytes()
        bx0, by0, bx1, by1 = placed["big"]["box"]
        assert {page.getpixel((bx0 + 1, by0 + 1)), page.getpixel((bx1 - 2, by1 - 2))} == {(0, 0, 255)}


def test_a_crop_tile_is_the_one_to_one_window_around_the_middle_of_the_drawing_not_of_the_empty_margin(tmp_path):
    """wire_34.png is 1024 px of grey with the wire in one corner of it: a crop of the image middle would show nothing."""
    im = Image.new("RGB", (1024, 1024), (235, 235, 235))
    for x in range(700, 900):
        for y in range(100, 300):
            im.putpixel((x, y), (30, 30, 30) if (x + y) % 7 == 0 else (235, 235, 235))
    (tmp_path / "final/review").mkdir(parents=True)
    im.save(tmp_path / "final/review/wire_34.png")
    tiles = review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/wire_34.png", "crop:final/review/wire_34.png"])
    assert tiles == {"wire_34": "final/review/wire_34.png", "wire_34_crop": "review/sheet-crops/wire_34_crop.png"}
    with Image.open(tmp_path / tiles["wire_34_crop"]) as crop:
        assert crop.size == (480, 480)
        assert crop.tobytes() == im.crop((544, 0, 1024, 480)).tobytes()


def test_two_files_with_one_stem_get_their_folder_in_the_label_so_a_label_names_one_file(tmp_path):
    png(tmp_path / "final/review/lineup.png")
    png(tmp_path / "final/review/renders/lineup.png")
    assert list(review_sheet.make(tmp_path, tmp_path / "s.png", ["final/review/*.png", "final/review/renders/*.png"])) == [
        "review/lineup", "renders/lineup"]


def renders(flow):  # noqa: F811
    for r in RENDERS:
        png(flow.v(1) / "final" / r)


def test_the_blockout_reviewer_brief_points_at_the_sheet_and_lists_no_single_image(flow):  # noqa: F811
    out = flow.brief()
    renders(flow)
    rb = json.loads(flow.work(out=out).splitlines()[-1])
    text = flow.text(rb)
    sheet = f"production/assets/{AID}/blockout/v1/review/sheet.png"
    assert (f"- Sheet: `{sheet}` (nhãn ô = tên ảnh; ảnh lẻ qua need_evidence). Số liệu: JSON trong `final/`, `work/` "
            "của v1.") in text.splitlines()
    assert ("- Output:" in text, ".png`" in text.replace(f"`{sheet}`", "")) == (False, False)
    assert (flow.root / sheet).is_file()
    assert len(text.replace(str(flow.root.resolve()), "").encode()) < 4096


def ask(flow, condition):  # noqa: F811
    """The v1 reviewer asks for evidence on F1 (unclear) with this viewing_condition."""
    out = flow.brief()
    renders(flow)
    flow.work(out=out)
    return flow.review(counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F1",
                       evidence="game_cam", findings=[finding("F1", "unclear", "param", evidence="game_cam: mờ",
                                                              viewing_condition=condition)])


def test_an_image_on_disk_is_served_by_the_script_without_a_worker_and_does_not_use_the_evidence_round(flow):  # noqa: F811
    head, line = ask(flow, "xin ảnh game_cam box 0,0,0.5,0.5").splitlines()
    assert head.endswith("→ blockout/review. Tiếp: giao reviewer → `brief house-a`")
    ev = flow.v(1) / "review/evidence-1"
    with Image.open(ev / "game_cam-crop1.png") as im:
        assert im.size == (200, 150)
    out = json.loads(line)
    assert (out["role"], flow.st.get("evidence_used", 0), flow.st["evidence_served"], flow.st["versions"]) == (
        "reviewer", 0, 1, {"blockout": 1})
    assert f"- Chấm lại v1 với ảnh thêm `production/assets/{AID}/blockout/v1/review/evidence-1/`; " in flow.text(out)


def test_the_original_image_is_served_whole_when_the_reviewer_asks_no_box(flow):  # noqa: F811
    ask(flow, "xin ảnh clay_front.png, góc trước")
    with Image.open(flow.v(1) / "review/evidence-1/clay_front.png") as a, Image.open(
            flow.v(1) / "final/review/renders/clay_front.png") as b:
        assert a.tobytes() == b.tobytes()


def test_a_tile_on_a_later_page_is_served_by_its_label_like_a_tile_of_the_first_page(flow):  # noqa: F811
    """The reviewer sees page 2 as a separate image; asking for a tile of it must not need another worker round."""
    out = flow.brief()
    for r in FULL:
        png(flow.v(1) / "final" / r, (400, 300))
    flow.work(out=out)
    placed = json.loads((flow.v(1) / "review/sheet.json").read_text(encoding="utf-8"))
    assert placed["mat_left"]["page"] != placed["game_cam"]["page"]
    head, line = flow.review(counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F1", evidence="mat_left",
                             findings=[finding("F1", "unclear", "param", evidence="mat_left: mờ",
                                               viewing_condition="xin ảnh mat_left box 0,0,0.5,0.5")]).splitlines()
    assert head.endswith("→ blockout/review. Tiếp: giao reviewer → `brief house-a`")
    with Image.open(flow.v(1) / "review/evidence-1/mat_left-crop1.png") as im:
        assert im.size == (200, 150)


def test_the_crop_tile_of_a_sheet_is_served_at_its_own_resolution_d38_5(tmp_path):
    from core import loop
    png(tmp_path / "final/review/wire_34.png", (1024, 1024), (235, 235, 235))
    review_sheet.make(tmp_path, tmp_path / "review/sheet.png", ["final/review/wire_34.png", "crop:final/review/wire_34.png"])
    doc = {"findings": {"F1": {"viewing_condition": "xin ảnh wire_34_crop"}}}
    assert loop.evidence_on_disk(tmp_path, doc, ["F1"]) == [("wire_34_crop", "review/sheet-crops/wire_34_crop.png", None)]


def test_a_sheet_json_of_the_old_form_still_serves_its_tiles(tmp_path):
    """A version made before pages has {label: file}; its reviewer may still be waiting for a crop."""
    from core import loop
    (tmp_path / "review").mkdir()
    (tmp_path / "review/sheet.json").write_text(json.dumps({"game_cam": "final/review/game_cam.png"}), encoding="utf-8")
    doc = {"findings": {"F1": {"viewing_condition": "xin ảnh game_cam box 0,0,0.5,0.5"}}}
    assert loop.evidence_on_disk(tmp_path, doc, ["F1"]) == [("game_cam", "final/review/game_cam.png", (0.0, 0.0, 0.5, 0.5))]


@pytest.mark.parametrize("condition", ["xin ảnh close_up_door", "cận cảnh cửa, 512 px", "ảnh game_cam, 512 px",
                                       "xin ảnh game_cam box 100,200,400,500", "xin ảnh game_cam box 0.5,0,0.2,1"])
def test_an_image_not_on_disk_a_view_note_or_a_pixel_box_still_goes_to_the_worker_render_round(flow, condition):  # noqa: F811
    assert ask(flow, condition).splitlines()[0].endswith("→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`")


def test_served_rounds_stop_at_served_evidence_and_the_next_ask_goes_to_the_worker(flow):  # noqa: F811
    st = flow.st
    st["evidence_served"] = 2
    save_st(st)
    assert ask(flow, "xin ảnh game_cam").splitlines()[0].endswith(
        "→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`")
