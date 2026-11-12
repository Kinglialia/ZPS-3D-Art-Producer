"""D31.1 (R1): the reviewer gets one sheet of the step's renders, and an image on disk without a worker round.
Pilot run: reviewers spent over a million tokens, much of it opening one render at a time."""
import json

import pytest
from PIL import Image

from shared import finding
from test_loop import AID, counts, flow, held  # noqa: F401  (flow is the blockout-only fixture)

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


import subprocess

from core import briefs
from core.state import load_cfg, step_of
from flowkit import blockout_files
from shared import SCRIPTS

TOOLS = SCRIPTS.parent / "agents/zps-3dp-step-blockout/tools"
VPY = TOOLS / ".deps/venv/bin/python"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")


def gated_pilot(flow, n=1):  # noqa: F811
    """The pilot graph of tests/fixtures with the gate and check results gate_all.py writes for it (a real run)."""
    fd = flow.v(n) / "final"
    blockout_files(fd, "x", files=False)
    run = subprocess.run([str(VPY), str(TOOLS / "gate_all.py"), "--work", str(fd), "--skip", "check_inputs"],
                         capture_output=True, text=True, cwd=flow.root)
    assert run.returncode == 0, run.stdout + run.stderr
    return fd


def blockout_step():
    return step_of(load_cfg(), "blockout")[1]


@needs_venv
def test_the_summary_names_each_part_with_its_primitive_material_size_and_gate_verdict_in_the_render_order(flow, held):  # noqa: F811
    """A reviewer read assembly.json (8.7 KB) and one gate JSON per part (2-3 KB each), all `pass` by construction."""
    flow.work(out=flow.brief())
    gated_pilot(flow)
    out = briefs.write_summary(flow.st, blockout_step(), 1)
    assert flow.root / out == flow.v(1) / "review/summary.json"
    doc = json.loads((flow.root / out).read_text(encoding="utf-8"))
    assert doc["parts"] == [
        {"n": 1, "name": "base", "prim": "box", "mat": "STONE", "tag": "base", "size": [4.0, 4.0, 0.3]},
        {"n": 2, "name": "walls", "prim": "box", "mat": "TIMBER", "size": [3.0, 3.0, 2.4]},
        {"n": 3, "name": "roof_f", "prim": "wedge", "mat": "TEAL", "tag": "roof", "size": [3.0, 1.5, 1.0]},
        {"n": 4, "name": "roof_b", "prim": "wedge", "mat": "TEAL", "tag": "roof", "size": [3.0, 1.5, 1.0]},
        {"n": 5, "name": "door", "prim": "box", "mat": "TIMBER", "size": [0.9, 0.05, 1.8]}]
    assert doc["gate"] == "pass unless a part says otherwise"
    assert doc["numbers"] == {"relief_m": {"door": 0.05}, "size_m": [4.0, 4.0, 3.7]}
    assert len((flow.root / out).read_bytes()) < 85 * 5 + 300


@needs_venv
def test_a_part_whose_gate_did_not_pass_or_has_no_result_says_so_in_the_summary(flow, held):  # noqa: F811
    flow.work(out=flow.brief())
    fd = gated_pilot(flow)
    (fd / "review/gates/door.json").write_text(json.dumps({"overall": "fail"}), encoding="utf-8")
    (fd / "review/gates/roof_f.json").unlink()
    got = {p["name"]: p.get("gate") for p in json.loads(
        (flow.root / briefs.write_summary(flow.st | {"accepted": {"v": 1, "items": ["door.json — x"]}}, blockout_step(), 1)
         ).read_text(encoding="utf-8"))["parts"]}
    assert got == {"base": None, "walls": None, "roof_f": "none", "roof_b": None, "door": "fail (accepted)"}


@needs_venv
def test_the_blockout_review_brief_names_the_summary_the_pages_and_the_part_legend_in_one_bullet(flow, held):  # noqa: F811
    """B8: the part numbers on parts_* are small on a sheet; the reviewer needs "number = name" to write `region: <part>`."""
    out = flow.brief()
    flow.work(out=out)
    gated_pilot(flow)
    for r in FULL:
        png(flow.v(1) / "final" / r, (400, 300))
    text = flow.text(flow.brief())
    sheet = f"production/assets/{AID}/blockout/v1/review/sheet.png"
    assert (f"- Sheet: `{sheet}`, `sheet-2.png`, `sheet-3.png`. Số liệu: `summary.json` cùng thư mục. "
            "Số = tên part: 1 base, 2 walls, 3 roof_f, 4 roof_b, 5 door.") in text.splitlines()
    assert "Số liệu: JSON trong" not in text and "final/review/gates" not in text
    assert (flow.v(1) / "review/sheet-3.png").is_file()
    assert len(text.replace(str(flow.root.resolve()), "").encode()) < 4096


@needs_venv
def test_a_part_legend_that_would_take_the_brief_over_its_budget_stays_in_the_summary_and_the_brief_says_so(flow, held, monkeypatch):  # noqa: F811
    """B8: with the pilot parts the legend fits; the real blockout brief of a fix round is within 20 bytes of its 4096, so
    a longer legend or a third sheet page must not push it over."""
    out = flow.brief()
    flow.work(out=out)
    gated_pilot(flow)
    for r in FULL:
        png(flow.v(1) / "final" / r, (400, 300))
    inline = flow.text(flow.brief())
    monkeypatch.setattr(briefs, "BRIEF_BYTES", len(inline.replace(str(flow.root.resolve()), "").encode()) - 1)
    short = briefs.review_brief(load_cfg(), flow.st, blockout_step(), 1)
    assert "Số = tên part: 1 base" in inline and "roof_f" not in short
    sheet = f"production/assets/{AID}/blockout/v1/review/sheet.png"
    assert (f"- Sheet: `{sheet}`, `sheet-2.png`, `sheet-3.png`. Số liệu và số = tên part (`n`): `summary.json` cùng thư mục."
            in short.splitlines())
    assert "roof_f" in (flow.v(1) / "review/summary.json").read_text(encoding="utf-8")


def test_a_sheet_without_a_parts_render_has_no_legend_line(tmp_path):
    (tmp_path / "summary.json").write_text(json.dumps({"parts": [{"n": 1, "name": "base"}]}), encoding="utf-8")
    (tmp_path / "sheet.json").write_text(json.dumps({"clay_34": {"page": "sheet.png"}}), encoding="utf-8")
    line, short = briefs.sheet_line(tmp_path / "sheet.png", tmp_path / "summary.json", 1)
    assert "Số = tên part" not in line and short is None


def model_final(flow, **checks):  # noqa: F811
    """final/review/checks/ of a model version: {file: {check name: (status, value)}}."""
    fr = flow.v(1, "model") / "final/review/checks"
    fr.mkdir(parents=True, exist_ok=True)
    for name, rows in checks.items():
        (fr / f"{name}.json").write_text(json.dumps({"overall": "pass", "checks": [
            {"check": c, "status": s, "value": v} for c, (s, v) in rows.items()]}), encoding="utf-8")


DETAIL = {"detail.bbox": ("pass", [4.0, 4.0, 3.7]), "detail.fixed_params": ("pass", []), "detail.vs_pilot": ("info", 0.93)}
QA_MESH = {"pilot.dimensions": ("pass", [4, 4, 3.7]), "pilot.pivot_bottom_center": ("pass", [0, 0, 0])}


def model_prefill(flow, **checks):  # noqa: F811
    model_final(flow, **checks)
    step = step_of(load_cfg(), "model")[1]
    return briefs.prefilled(flow.st, step, 1)


def test_density_and_blockout_match_are_filled_from_the_detail_and_mesh_json_that_say_pass(flow):  # noqa: F811
    got = model_prefill(flow, detail=DETAIL, qa_mesh_check=QA_MESH)
    assert got == {"density": ("pass", "detail.json"), "blockout_match": ("pass", "detail.json, qa_mesh_check.json")}


@pytest.mark.parametrize("name, detail, qa_mesh, left", [
    ("a ratio outside 0.5-2 needs the reason of model.md", DETAIL | {"detail.vs_pilot": ("info", 2.4)}, QA_MESH, "density"),
    ("no pilot: the reviewer writes pass with its note", DETAIL | {"detail.vs_pilot": ("not_checked", None)}, QA_MESH, "density"),
    ("a size the spec does not give is only info", DETAIL, {"pilot.dimensions": ("info", [4, 4, 3.7])}, "blockout_match"),
    ("no mesh result", DETAIL, None, "blockout_match"),
    ("fixed_params that moved fail the check", DETAIL | {"detail.fixed_params": ("fail", ["door_h: 1.8 → 2"])}, QA_MESH,
     "blockout_match"),
])
def test_a_key_stays_with_the_reviewer_when_its_json_does_not_say_pass_alone(flow, name, detail, qa_mesh, left):  # noqa: F811
    """Conservative: only a missing or unclear result leaves a key to the reviewer; a fail that no one accepted never
    reaches the review, so it is not a case to fill either."""
    got = model_prefill(flow, detail=detail, **({"qa_mesh_check": qa_mesh} if qa_mesh else {}))
    assert left not in got and len(got) == 1, name


def test_a_missing_detail_json_fills_no_key(flow):  # noqa: F811
    assert model_prefill(flow, qa_mesh_check=QA_MESH) == {}


def test_a_failed_json_the_worker_accepted_fills_the_key_with_fail(flow):  # noqa: F811
    """K08 rule: fail with a valid ACCEPTED_FAIL is `fail`. No model key reads an acceptable JSON today, so the
    mechanism is shown with a mesh result the pipeline would list as acceptable."""
    st = flow.st | {"accepted": {"v": 1, "items": ["qa_mesh_check.json — kích thước lệch 3% do diềm 0.2 m"]}}
    model_final(flow, detail=DETAIL, qa_mesh_check={"pilot.dimensions": ("fail", [4.2, 4, 3.7])})
    step = step_of(load_cfg(), "model")[1]
    assert briefs.prefilled(st, step, 1)["blockout_match"][0] == "fail"
    assert "blockout_match" not in briefs.prefilled(flow.st, step, 1)


def test_the_script_fills_nothing_for_a_key_the_asset_rubric_does_not_have(flow):  # noqa: F811
    rubric = flow.root / f"production/assets/{AID}/rubric.md"
    rubric.write_text(rubric.read_text(encoding="utf-8").replace("- density:", "- tris_budget:"), encoding="utf-8")
    assert "density" not in model_prefill(flow, detail=DETAIL, qa_mesh_check=QA_MESH)


@needs_venv
def test_the_review_brief_lists_the_filled_keys_with_their_source(flow, held, monkeypatch):  # noqa: F811
    monkeypatch.setitem(briefs.PREFILL, "blockout", {"props": lambda fr, acc: ("pass", "counts.json")})
    flow.work(out=flow.brief())
    text = flow.text(flow.brief())
    assert ("- Key script đã điền từ JSON, chép nguyên vào RUBRIC, không chấm lại (report đổi giá trị bị từ chối): "
            "props=pass (counts.json).") in text.splitlines()


def test_the_filled_key_bullet_fits_in_what_the_heaviest_model_review_brief_leaves():
    """`m3 review brief` of tests/test_e2e_model.py (variants, base version, open PRIOR) measured 3981 bytes before the
    bullet, paths left out; the new sheet line is shorter than the old one, so 60 bytes cover its pages."""
    bullet = briefs.prefill_line({"density": ("pass", "detail.json"), "blockout_match": ("pass", "detail.json, qa_mesh_check.json")})
    assert len(bullet.encode()) <= 220
    assert 3981 + len(bullet.encode()) + 1 + 60 < 4416


def prefilled_review(flow, monkeypatch):  # noqa: F811
    monkeypatch.setitem(briefs.PREFILL, "blockout", {"props": lambda fr, acc: ("pass", "counts.json: window 2")})
    out = flow.brief()
    flow.work(out=out)
    return out


def test_ingest_refuses_a_report_that_changes_a_filled_key_and_keeps_it_when_the_reviewer_leaves_it_out(flow, held, monkeypatch):  # noqa: F811
    prefilled_review(flow, monkeypatch)
    out = flow.brief()
    with pytest.raises(Exception) as e:
        flow.review(out=out, verdict="PASS", counts=counts(), top_fix=None, rubric="mass=pass; props=fail")
    assert "RUBRIC đổi key script đã điền từ JSON: props=fail (script điền pass)" in str(e.value)
    assert (flow.root / out["report"].replace("review-out.md", "review-out.rejected-1.md")).is_file()
    out = flow.brief()
    flow.review(out=out, verdict="PASS", counts=counts(), top_fix=None, rubric="mass=pass")
    assert flow.st["last_rubric"] == "mass=pass; props=pass"


def results(fr, **files):
    """Result JSON as the tools write them: {file: {"checks": {name: (status, value, note)}, "data": {...}}}."""
    for name, doc in files.items():
        (fr / "checks").mkdir(parents=True, exist_ok=True)
        (fr / "checks" / f"{name}.json").write_text(json.dumps({"overall": "pass", "data": doc.get("data", {}), "checks": [
            {"check": c, "status": s, "value": v, "threshold": t, "note": note}
            for c, (s, v, t, note) in doc.get("checks", {}).items()]}), encoding="utf-8")


def test_the_blockout_numbers_hold_the_counts_the_proportion_ratios_the_marks_and_the_size(tmp_path):
    results(tmp_path, counts={"checks": {"counts.window": ("pass", [], 2, None), "counts.leg": ("pass", [], 4, None)}},
            proportion={"data": {"ratios": {"front": {"model": 1.1, "concept": 1.08, "deviation": 0.019}}},
                        "checks": {"proportion.front": ("pass", 0.019, 0.1, None), "proportion.mark.eave": ("pass", 0.02, 0.2, None)}},
            markers={"data": {"relief": {"door": 0.05}}}, layout={"data": {"built": [4.0, 4.0, 3.7]}})
    assert briefs.drop_empty(briefs.blockout_numbers(tmp_path)) == {
        "counts": {"window": 2, "leg": 4}, "proportion": {"front": 0.019}, "marks_off_m": {"eave": 0.02},
        "relief_m": {"door": 0.05}, "size_m": [4.0, 4.0, 3.7]}


def test_the_model_numbers_hold_the_budget_the_density_the_uv_stretch_and_the_screen_ratio(tmp_path):
    results(tmp_path, detail={"data": {"tris": 412, "cap": 600, "tris_per_m2": 31.5, "pilot": {"ratio": 0.93}, "bbox_ratio": [1, 1, 1]},
                              "checks": {"detail.fixed_params": ("pass", [], None, None)}},
            uv_edge={"checks": {"uv.texel_px_per_m": ("pass", 410.0, 256, None), "uv.stretch": ("pass", 0.012, 0.05, None)}},
            qa_screen_tris_check={"checks": {"screen.small_tri_ratio": ("pass", 0.04, 0.1, None), "screen.thin_tris": ("pass", 0, 5, None)}})
    assert briefs.drop_empty(briefs.model_numbers(tmp_path)) == {
        "density": {"tris": 412, "cap": 600, "tris_m2": 31.5, "vs_pilot": 0.93},
        "blockout_match": {"bbox_ratio": [1, 1, 1], "fixed_params_diff": "none"},
        "uv": {"texel_px_m": 410.0, "stretch_share": 0.012}, "screen_tris": {"small_tri_ratio": 0.04, "thin": 0}}
    assert len(json.dumps(briefs.drop_empty(briefs.model_numbers(tmp_path)), separators=(",", ":"))) < 400


def test_the_texture_numbers_group_the_measured_part_under_the_rubric_key_the_reviewer_still_judges(tmp_path):
    """light, material and seams also ask for a look at the renders, so the script fills none of them."""
    results(tmp_path, tex_measure={"checks": {
        "light.side_spread_L.STONE": ("pass", 1.2, 3, None), "light.shaded_share.STONE": ("pass", 0.004, 0.02, None),
        "light.highlight_share.STONE": ("info", 0.03, 0.02, "vượt ngưỡng"), "material.dE_concept.STONE": ("pass", 1.8, 3, None),
        "seam.p90_dE": ("pass", 2.4, 4, None), "uv.mirrored_faces": ("info", 12, None, "chữ có thể bị lật gương ở mã SIGN (12 mặt lật UV)")}})
    assert briefs.drop_empty(briefs.texture_numbers(tmp_path)) == {
        "light": {"side_spread_L": {"STONE": 1.2}, "shaded_share": {"STONE": 0.004}, "highlight_share": {"STONE": 0.03}},
        "material": {"dE_concept": {"STONE": 1.8}}, "seams": {"p90_dE": 2.4},
        "mirrored_uv": {"faces": 12, "note": "chữ có thể bị lật gương ở mã SIGN (12 mặt lật UV)"}}
    assert len(json.dumps(briefs.drop_empty(briefs.texture_numbers(tmp_path)), ensure_ascii=False, separators=(",", ":")).encode()) < 600
    assert set(briefs.PREFILL["model"]) == {"density", "blockout_match"} and "texture" not in briefs.PREFILL


def test_a_fix_round_report_may_write_not_checked_for_a_filled_key_and_the_script_keeps_its_value(flow, held, monkeypatch):  # noqa: F811
    """The role files tell the reviewer to write not_checked for a key a fix round does not judge. A filled key is a fact of
    a JSON, so that line is not a change of the value: refusing it would reject every fix-round report."""
    from test_loop import fix_v1
    monkeypatch.setitem(briefs.PREFILL, "blockout", {"props": lambda fr, acc: ("pass", "counts.json")})
    fix_v1(flow)
    flow.work()
    rb = flow.brief()
    assert flow.st["review_scope"] == "fix"
    flow.review(out=rb, verdict="PASS", counts=counts(), top_fix=None, rubric="mass=not_checked; props=not_checked",
                prior=["- F1: resolved | evidence: clay_front.png", "- F2: resolved | evidence: clay_front.png"], compare="F1=better; F2=better")
    assert flow.st["last_rubric"] == "mass=not_checked; props=pass"
