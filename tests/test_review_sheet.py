"""D31.1 (R1): the reviewer gets one sheet of the step's renders, and an image on disk without a worker round.
Run 5: reviewers spent 1.33M tokens, much of it opening one render at a time."""
import json

import pytest
from PIL import Image

from shared import finding
from test_loop import AID, counts, flow  # noqa: F401  (flow is the blockout-only fixture)

import review_sheet
from core.state import TEMPLATES, save_st

RENDERS = ["review/game_cam.png", "review/lineup.png", "review/renders/clay_front.png", "review/renders/normal_front.png",
           "review/renders/parts_34.png"]


def png(p, size=(400, 300), colour=(90, 60, 30)):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(p)


def test_the_sheet_has_one_labelled_tile_per_render_of_the_step_and_a_long_edge_of_2048(tmp_path):
    for r in RENDERS:
        png(tmp_path / "final" / r)
    (tmp_path / "final/review/renders/renders.json").write_text("{}", encoding="utf-8")
    import tomllib
    globs = tomllib.loads((TEMPLATES / "pipeline.toml").read_text(encoding="utf-8"))["steps"][0]["sheet"]
    tiles = review_sheet.make(tmp_path, tmp_path / "review/sheet.png", globs)
    assert tiles == {"game_cam": "final/review/game_cam.png", "lineup": "final/review/lineup.png",
                     "clay_front": "final/review/renders/clay_front.png",
                     "normal_front": "final/review/renders/normal_front.png", "parts_34": "final/review/renders/parts_34.png"}
    assert json.loads((tmp_path / "review/sheet.json").read_text(encoding="utf-8")) == tiles
    with Image.open(tmp_path / "review/sheet.png") as im:
        assert im.size == (2048, 8 + 2 * (22 + 672 + 8))


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
    ask(flow, "xin ảnh lineup.png, góc trước")
    with Image.open(flow.v(1) / "review/evidence-1/lineup.png") as a, Image.open(flow.v(1) / "final/review/lineup.png") as b:
        assert a.tobytes() == b.tobytes()


@pytest.mark.parametrize("condition", ["xin ảnh close_up_lock", "cận cảnh khóa, 512 px", "ảnh game_cam, 512 px",
                                       "xin ảnh game_cam box 100,200,400,500", "xin ảnh game_cam box 0.5,0,0.2,1"])
def test_an_image_not_on_disk_a_view_note_or_a_pixel_box_still_goes_to_the_worker_render_round(flow, condition):  # noqa: F811
    assert ask(flow, condition).endswith("→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`\n")


def test_served_rounds_stop_at_served_evidence_and_the_next_ask_goes_to_the_worker(flow):  # noqa: F811
    st = flow.st
    st["evidence_served"] = 2
    save_st(st)
    assert ask(flow, "xin ảnh game_cam").endswith("→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`\n")
