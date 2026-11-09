import json

import pytest
from PIL import Image

from core import briefs, findings, loop
from core.state import ROOT, ProducerError, load_cfg, load_st, save_st, step_of, vdir
from test_board import AID, post_raw, project, server  # noqa: F401

KEY = "blockout-v2-1"
CAM = "review/game_cam.png"
FOLDER = "production/assets/house-a/feedback/blockout-v2-1"
RECT = {"n": 1, "image": CAM, "shape": "rect", "coords": [0.1, 0.2, 0.3, 0.6], "note": "mái thấp"}
FREE = {"n": 2, "image": CAM, "shape": "free", "coords": [[0.5, 0.5], [0.7, 0.5], [0.7, 0.8]], "note": ""}


@pytest.fixture
def real(project):
    Image.new("RGB", (200, 100), "white").save(vdir(AID, "blockout", 2) / "final" / CAM)
    st = load_st(AID)
    st["offer_key"] = KEY
    save_st(st)
    return project


def h(n, repair, png=f"{FOLDER}/review_game_cam.png"):
    return {"priority": "major", "kind": "structure", "status": "open", "first_v": 2, "last_v": 2,
            "region": f"vùng {n} trên {CAM}", "viewing_condition": "ảnh người dùng khoanh",
            "evidence": f"feedback/blockout-v2-1/review_game_cam.png vùng {n}", "consequence": "người dùng chưa duyệt",
            "confidence": "high", "repair": repair, "preserve": "những gì feedback không nhắc",
            "acceptance": f"vùng {n} đạt yêu cầu của người dùng: {repair}", "mark": {"png": png, "n": n}}


def test_each_region_becomes_a_major_h_finding_on_the_version_sent_back_d23_1(real):
    msg = loop.human_action(AID, "redo", "", "blockout", regions=[RECT, FREE], offer=KEY)
    assert msg == "house-a: làm lại blockout từ v2; khoanh 2 vùng → H1, H2. Tiếp: giao worker → `brief house-a`"
    doc = findings.load(AID, "blockout", 2)
    assert ({i: doc["findings"][i] for i in doc["findings"] if i.startswith("H")}, doc["next_id"]) == (
        {"H1": h(1, "mái thấp"), "H2": h(2, "xem vùng khoanh")}, 5)


def test_the_region_json_and_the_annotated_png_land_in_the_feedback_folder_in_original_image_pixels(real):
    loop.human_action(AID, "redo", "", "blockout", regions=[RECT, FREE], offer=KEY)
    d = real / FOLDER
    assert sorted(p.name for p in d.iterdir()) == ["regions.json", "review_game_cam.png"]
    assert json.loads((d / "regions.json").read_text(encoding="utf-8")) == [RECT | {"id": "H1"}, FREE | {"id": "H2"}]
    im = Image.open(d / "review_game_cam.png").convert("RGB")
    assert (im.size, im.getpixel((20, 40)), im.getpixel((40, 40)), im.getpixel((120, 50))) == (
        (200, 100), (230, 30, 30), (255, 255, 255), (230, 30, 30))


def test_the_next_annotation_of_the_same_version_gets_the_next_folder(real):
    loop.human_action(AID, "note", "xem lại", None, regions=[RECT], offer=KEY)
    loop.human_action(AID, "note", "", None, regions=[RECT], offer=KEY)
    assert sorted(p.name for p in (ROOT / "assets/house-a/feedback").iterdir()) == ["blockout-v2-1", "blockout-v2-2"]
    assert [i for i in findings.load(AID, "blockout", 2)["findings"] if i.startswith("H")] == ["H1", "H2"]
    assert load_st(AID)["state"] == "waiting_human"


def test_redo_text_and_regions_both_reach_the_findings(real):
    loop.human_action(AID, "redo", "mái phẳng quá", "blockout", regions=[RECT], offer=KEY)
    fs = findings.load(AID, "blockout", 2)["findings"]
    assert (fs["H1"]["repair"], fs["H1"]["region"], fs["H2"]["region"]) == (
        "mái phẳng quá", "theo feedback người dùng", f"vùng 1 trên {CAM}")


@pytest.mark.parametrize("regions, err", [
    ([RECT | {"image": "../../secret.txt"}], "vùng 1: ảnh '../../secret.txt' không có trên thẻ house-a blockout v2"),
    ([RECT | {"image": "/p/assets/house-a/blockout/v2/final/review/game_cam.png"}],
     "vùng 1: ảnh '/p/assets/house-a/blockout/v2/final/review/game_cam.png' không có trên thẻ house-a blockout v2"),
    ([RECT | {"coords": [0.1, 0.2, 1.3, 0.6]}], "vùng 1: coords của rect phải là [x0, y0, x1, y1] trong 0–1, x0 < x1, y0 < y1"),
    ([RECT | {"coords": [0.3, 0.2, 0.1, 0.6]}], "vùng 1: coords của rect phải là [x0, y0, x1, y1] trong 0–1, x0 < x1, y0 < y1"),
    ([RECT | {"shape": "star"}], "vùng 1: shape phải là circle|rect|free"),
    ([RECT | {"n": 2}], "vùng 1: n phải là 1"),
    ([FREE | {"n": 1, "coords": [[0.5, 0.5]]}], "vùng 1: free cần 2–500 điểm [x, y] trong 0–1"),
    ([RECT | {"note": "x" * 501}], "vùng 1: note phải là chuỗi tối đa 500 ký tự"),
    ([], "regions phải là danh sách 1–50 vùng"),
    ({"n": 1}, "regions phải là danh sách 1–50 vùng"),
])
def test_bad_regions_are_refused_before_anything_is_written(real, regions, err):
    with pytest.raises(ProducerError) as ex:
        loop.human_action(AID, "redo", "", "blockout", regions=regions, offer=KEY)
    assert str(ex.value) == err
    assert (load_st(AID)["state"], (ROOT / "assets/house-a/feedback").exists()) == ("waiting_human", False)


def test_a_click_on_an_old_offer_is_skipped_so_a_stale_tab_or_phone_row_never_decides_the_new_offer(real):
    msg = loop.human_action(AID, "approve", "", None, offer="blockout-v2-0")
    assert msg == "house-a: bỏ qua approve: lần đưa duyệt blockout-v2-0 đã qua (hiện tại: blockout-v2-1)"
    assert load_st(AID)["state"] == "waiting_human"
    assert loop.human_action(AID, "note", "nhớ mái", None, offer="blockout-v2-0").startswith("house-a: đã ghi feedback")


def test_regions_on_an_old_offer_are_skipped_because_they_point_at_images_of_that_offer(real):
    msg = loop.human_action(AID, "note", "", None, regions=[RECT], offer="blockout-v2-0")
    assert msg == "house-a: bỏ qua note: lần đưa duyệt blockout-v2-0 đã qua (hiện tại: blockout-v2-1)"


def test_one_decision_per_offer_across_sources_a_later_redo_on_the_same_offer_is_skipped_d22_8(real):
    first = loop.human_action(AID, "approve", "ok", None, offer=KEY)
    at = load_st(AID)["decisions"]["blockout v2"]["at"]
    again = loop.human_action(AID, "redo", "sửa mái", "blockout", offer=KEY)
    assert (first.split(" → ")[0], again) == (
        "house-a: đã duyệt blockout v2", f"house-a: bỏ qua redo blockout v2: đã có quyết định lúc {at}")
    assert load_st(AID)["decisions"]["blockout v2"] == {"action": "approve", "at": at, "offer": KEY}


def test_a_chat_redo_after_approval_still_opens_a_new_round_because_it_names_no_offer(real):
    loop.human_action(AID, "approve", "ok", None, offer=KEY)
    assert loop.human_action(AID, "redo", "sửa mái", "blockout").startswith("house-a: làm lại blockout từ v2")


def assemble_offer(project):
    final = vdir(AID, "assemble", 1) / "final"
    for name in ("model/house-a.glb", "README.md"):
        (final / name).parent.mkdir(parents=True, exist_ok=True)
        (final / name).write_bytes(b"x")
    (final / "review").mkdir()
    Image.new("RGB", (64, 64), "white").save(final / "review/final_lit_vs_concept.png")
    st = load_st(AID)
    st |= {"stage": "assemble", "versions": {"blockout": 2, "assemble": 1}, "offer": 1, "offer_key": "assemble-v1-1",
           "label": "", "note": "duyệt"}
    save_st(st)


def test_at_a_step_without_reviewer_the_user_closes_own_h_findings_by_approving(project):
    assemble_offer(project)
    mark = {"n": 1, "image": "review/final_lit_vs_concept.png", "shape": "circle", "coords": [0.2, 0.2, 0.6, 0.6],
            "note": "viền tối"}
    loop.human_action(AID, "note", "", None, regions=[mark], offer="assemble-v1-1")
    assert findings.load(AID, "assemble", 1)["findings"]["H1"]["status"] == "open"
    loop.human_action(AID, "approve", "", None, offer="assemble-v1-1")
    assert (findings.load(AID, "assemble", 1)["findings"]["H1"]["status"], load_st(AID)["state"]) == ("resolved", "done")


def test_needs_fix_at_assemble_puts_the_regions_on_the_step_the_user_picks(project):
    assemble_offer(project)
    st = load_st(AID)
    st["approved"] = {"texture": 2}
    st["versions"]["texture"] = 2
    save_st(st)
    mark = {"n": 1, "image": "review/final_lit_vs_concept.png", "shape": "rect", "coords": [0.2, 0.2, 0.6, 0.6], "note": "lem"}
    loop.human_action(AID, "redo", "", "texture", regions=[mark], offer="assemble-v1-1")
    h1 = findings.load(AID, "texture", 2)["findings"]["H1"]
    assert (h1["kind"], h1["mark"]) == (
        "repaint", {"png": "production/assets/house-a/feedback/assemble-v1-1/review_final_lit_vs_concept.png", "n": 1})


def test_fix_and_review_briefs_list_each_region_with_the_annotated_image(real):
    loop.human_action(AID, "redo", "mái phẳng", "blockout", regions=[RECT, FREE], offer=KEY)
    want = (f"`{FOLDER}/review_game_cam.png`: 1 (H2) mái thấp; 2 (H3) xem vùng khoanh")
    doc = findings.load(AID, "blockout", 2)
    assert findings.mark_lines(doc) == [want]
    cfg = load_cfg()
    st, step = load_st(AID), step_of(cfg, "blockout")[1]
    assert f"   - Vùng người dùng khoanh: {want}" in briefs.worker_brief(cfg, st, step, 3, True, "h", None, ROOT / "p.yaml", {})
    assert f"- Vùng người dùng khoanh, kiểm từng vùng: {want}" in briefs.review_brief(cfg, st, step, 3)


def test_the_meshy_question_answers_with_its_own_buttons_so_approve_never_hides_a_credit_spend(project):
    st = load_st(AID)
    st |= {"stage": "texture", "versions": {"blockout": 2, "texture": 1}, "offer": 1, "offer_key": "texture-v1-1",
           "label": "chưa đạt", "note": "Meshy?", "meshy_price": 10,
           "ask": {"kind": "meshy_regen", "budget": "budget-abc123def456.json", "next": "fix", "base": 1, "new_round": True}}
    save_st(st)
    from core import board
    assert board.asset_view(load_cfg(), load_st(AID))["ask"] == {"kind": "meshy_regen", "price": 10}
    msg = loop.human_action(AID, "paint", "", None, offer="texture-v1-1")
    assert msg.startswith("house-a: meshy_regen: VẼ MỚI, không gọi Meshy cho mesh abc123def456")
    assert (load_st(AID)["paint_for"], load_st(AID)["state"]) == ("abc123def456", "fix")


def test_paint_without_a_meshy_question_is_refused(real):
    with pytest.raises(ProducerError) as ex:
        loop.human_action(AID, "paint", "", None, offer=KEY)
    assert str(ex.value) == "house-a: không có câu hỏi Meshy đang chờ"


def post_json(srv, body):
    code, raw = post_raw(srv, body)
    return code, json.loads(raw)["message"]


def test_the_board_posts_regions_and_the_offer_key_and_a_path_in_a_region_gets_400(real, server):
    code, msg = post_json(server, {"id": AID, "action": "redo", "text": "", "step": "blockout", "offer": KEY,
                                   "regions": [RECT | {"image": "../../secret.txt"}]})
    assert (code, msg) == (400, "Lỗi: vùng 1: ảnh '../../secret.txt' không có trên thẻ house-a blockout v2")
    code, msg = post_json(server, {"id": AID, "action": "redo", "text": "", "step": "blockout", "offer": KEY,
                                   "regions": [RECT]})
    assert (code, msg.split(". Tiếp")[0]) == (200, "house-a: làm lại blockout từ v2; khoanh 1 vùng → H1")


@pytest.mark.parametrize("body, err", [
    ({"id": AID, "action": "note", "regions": "x"}, "Lỗi: regions phải là danh sách 1–50 vùng"),
    ({"id": AID, "action": "note", "offer": 5}, "Lỗi: offer phải là chuỗi"),
])
def test_the_board_refuses_fields_of_the_wrong_type(real, server, body, err):
    assert post_json(server, body) == (400, err)
