"""Views tools on synthetic images (concept-views.md §3, §6, §9; checklist 10, 13, 14). No Blender, no Codex."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageOps

TOOLS = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/agents/zps-3dp-step-views/tools"
VIEWS = ("front", "back", "left", "right", "top")
POINTER = ("Thông số, mốc chiều cao, phần khuất, Blockout tự quyết, ghi chú real/texture_only: xem `blockout.md` "
           "của blockout đã duyệt. Không chiếu hay bake màu từ ảnh view lên model; màu lấy từ albedo.")


def tool(name, *args):
    p = subprocess.run([sys.executable, str(TOOLS / f"{name}.py"), *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def png(path, size, bg, rects=(), mode="RGB"):
    im = Image.new(mode, size, bg)
    for box, colour in rects:
        im.paste(colour, box)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def checks(p):
    return {c["check"]: (c["status"], c.get("value")) for c in read(p)["checks"]}


CREAM, WOOD = "#EDE3C8", "#4A3020"


@pytest.fixture
def stone_and_wood(tmp_path):
    return png(tmp_path / "concept_albedo.png", (200, 200), "#FFFFFF",
               [((20, 20, 100, 180), CREAM), ((100, 20, 180, 180), WOOD)])


def profile(tmp_path, view_bg=None):
    p = tmp_path / "PROJECT-PROFILE.yaml"
    p.write_text(f"style: {{light_convention: unlit_flat, view_bg: {json.dumps(view_bg)}}}\n", encoding="utf-8")
    return p


def test_pick_bg_skips_both_greys_for_cream_stone_and_dark_wood_so_no_material_is_keyed_out(tmp_path, stone_and_wood):
    rc, out, _ = tool("pick_bg", "--final", tmp_path / "final", "--concept", stone_and_wood, "--profile", profile(tmp_path))
    assert rc == 0
    assert read(tmp_path / "final/bg_color.json") == {"hex": "#3A5FCD", "source": "pick", "min_dist": 180.0,
                                                      "nearest": "#4A3020"}
    assert out == f"[views/pick_bg] #3A5FCD (pick, gần nhất #4A3020 cách 180.0) -> {tmp_path / 'final/bg_color.json'}\n"


def test_pick_bg_keeps_the_kit_light_grey_when_only_the_concept_background_is_near_it(tmp_path):
    concept = png(tmp_path / "c.png", (200, 200), "#E6E6E6", [((40, 40, 160, 160), "#C0392B")])
    tool("pick_bg", "--final", tmp_path, "--concept", concept, "--profile", profile(tmp_path))
    assert read(tmp_path / "bg_color.json")["hex"] == "#E8E8E8"


def test_profile_view_bg_wins_over_the_pick(tmp_path, stone_and_wood):
    tool("pick_bg", "--final", tmp_path, "--concept", stone_and_wood, "--profile", profile(tmp_path, "#123456"))
    assert {k: read(tmp_path / "bg_color.json")[k] for k in ("hex", "source")} == {"hex": "#123456", "source": "profile"}


def test_concept_colors_takes_the_paint_colour_inside_each_material_box(tmp_path, stone_and_wood):
    rc, out, _ = tool("concept_colors", "--final", tmp_path, "--concept", stone_and_wood,
                      "--box", "STONE=30,30,90,170", "--box", "TIMBER=110,30,170,170")
    assert rc == 0 and read(tmp_path / "concept_colors.json") == {"STONE": CREAM, "TIMBER": WOOD}


ID_STONE, ID_TIMBER = "#E6194B", "#3CB44B"


def frame_guides(d):
    """A stone frame with a closed hole: the gap between columns that G1 is about."""
    (d / "views.json").parent.mkdir(parents=True, exist_ok=True)
    (d / "views.json").write_text(json.dumps({"materials": {"STONE": ID_STONE}}), encoding="utf-8")
    for v in ("front", "back"):
        png(d / f"{v}_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 350), ID_STONE), ((110, 110, 290, 290), (0, 0, 0, 0))],
            mode="RGBA")
    return d


def frame_gen(path):
    return png(path, (600, 600), "#E8E8E8", [((75, 75, 525, 525), "#8B5A2B"), ((165, 165, 435, 435), "#E8E8E8")])


def test_measure_keys_the_background_over_the_whole_image_so_a_closed_gap_is_not_object(tmp_path):
    g, f = frame_guides(tmp_path / "guides"), tmp_path / "final"
    frame_gen(f / "front.png")
    cc = tmp_path / "cc.json"
    cc.write_text(json.dumps({"STONE": "#8B5A2B"}), encoding="utf-8")
    rc, out, _ = tool("measure", "--final", f, "--guides", g, "--views", "front", "--concept-colors", cc)
    ours = read(f / "report/report.json")
    kit = tmp_path / "kit"
    subprocess.run([sys.executable, str(TOOLS / "measure_views.py"), "--blockout", str(g), "--gen", str(f), "--out",
                    str(kit), "--views", "front"], capture_output=True, check=True)
    assert (round(ours["views"]["front"]["iou"], 2), ours["regen"]) == (1.0, [])
    assert (round(read(kit / "report.json")["views"]["front"]["iou"], 2), read(kit / "report.json")["regen"]) == (0.64, ["front"])
    assert (rc, out.split(" overall=")[1].split(" ")[0]) == (0, "pass")
    assert checks(f / "review/checks/measure.json")["views.front"][0] == "pass"
    with Image.open(f / "report/overlay_front.png") as im:
        assert im.size == (320, 320)


def test_measure_reads_front_from_views_front_and_fails_a_missing_view_so_the_fix_brief_lists_it(tmp_path):
    g, f = frame_guides(tmp_path / "guides"), tmp_path / "final"
    front = frame_gen(tmp_path / "views_front/front.png")
    rc, _, _ = tool("measure", "--final", f, "--guides", g, "--views", "front,back", "--front", front)
    assert rc == 1
    assert {k: v[0] for k, v in checks(f / "review/checks/measure.json").items()} == {"views.front": "pass",
                                                                                     "views.back": "fail"}
    frame_gen(f / "back.png")
    assert tool("measure", "--final", f, "--guides", g, "--views", "front,back", "--front", front)[0] == 0
    assert sorted(read(f / "report/report.json")["views"]) == ["back", "front"]


def test_check_inputs_names_every_missing_file_the_brief_points_to(tmp_path):
    b, c, fr = tmp_path / "blockout", tmp_path / "_approved/hut", tmp_path / "views_front"
    b.mkdir()
    (b / "part_graph.json").write_text(json.dumps({"parts": [{"name": "base"}, {"name": "roof"}]}), encoding="utf-8")
    for n in ("sources.json", "blockout.md", "parts/base.glb", "../_approved/hut/concept_albedo.png",
              "../_approved/hut/asset-card.yaml", "../_approved/hut/hut.material.md", "../views_front/front.png"):
        (b / n).parent.mkdir(parents=True, exist_ok=True)
        (b / n).write_text("x", encoding="utf-8")
    rc, _, _ = tool("check_inputs", "--final", tmp_path / "final", "--blockout", b, "--concept", c, "--front", fr)
    got = checks(tmp_path / "final/review/checks/inputs.json")
    assert rc == 1
    assert got["inputs.blockout"] == ("fail", ["parts/roof.glb"]) and got["inputs.concept"] == ("pass", [])
    assert got["inputs.front"][1] == sorted(["bg_color.json", "concept_colors.json", "guides/views.json",
                                             *[f"guides/{v}_{k}.png" for v in VIEWS for k in ("guide", "id")]])


def view_set(tmp_path, flip_line="right = left lật ngang"):
    f, front = tmp_path / "final", png(tmp_path / "views_front/front.png", (300, 200), "#E8E8E8", [((50, 50, 250, 190), "#8B5A2B")])
    for v, colour in (("back", "#556B2F"), ("left", "#8B0000"), ("top", "#2F4F4F")):
        png(f / f"{v}.png", (300, 200), "#E8E8E8", [((40, 30, 200, 190), colour)])
    ImageOps.mirror(Image.open(f / "left.png")).save(f / "right.png")
    (f / "report").mkdir()
    rep = {"views": {v: {"score": 90, "iou": 0.97, "max_delta_e": 3.2} for v in VIEWS}}
    (f / "report/report.json").write_text(json.dumps(rep), encoding="utf-8")
    for v in VIEWS:
        png(f / f"report/overlay_{v}.png", (320, 320), "#FFFFFF")
    (f / "README.md").write_text("\n".join([POINTER, "", "## 1. NGOẠI LỆ", "không có", "## 2. TEXTURE NOTE", "không có",
                                            "## 3. Lật ảnh", flip_line, "## 4. Trạng thái duyệt",
                                            "chờ duyệt, 2026-11-09", ""]), encoding="utf-8")
    card = tmp_path / "asset-card.yaml"
    card.write_text("symmetric: {left_right: true, front_back: false}\n", encoding="utf-8")
    concept = png(tmp_path / "concept_albedo.png", (200, 200), "#FFFFFF")
    return f, front, card, concept


def package(f, front, card):
    rc, _, _ = tool("check_package", "--final", f, "--front", front, "--card", card)
    return rc, checks(f / "review/checks/package.json")


def test_views_sheet_puts_concept_and_5_views_over_their_overlays_and_records_what_it_was_built_from(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    rc, out, _ = tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front)
    assert rc == 0 and out == f"[views/views_sheet] 2 hàng 2004x720 -> {f / 'report/VIEWS_sheet.png'}\n"
    assert sorted(read(f / "report/VIEWS_sheet.json")["inputs"]) == sorted(VIEWS)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--crop", "back:40,30,140,130")
    with Image.open(f / "report/VIEWS_sheet.png") as im:
        assert im.size == (2004, 1074)
    assert package(f, front, card) == (0, {"package.views": ("pass", []), "package.sheet": ("pass", []),
                                           "package.readme": ("pass", []), "package.flip": ("pass", [])})


def test_views_sheet_marks_kept_views_in_the_label_strip_only_so_the_user_sees_which_views_are_new(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    shots = []
    for kept in ((), ("--kept", "back,left")):
        tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, *kept)
        shots.append(Image.open(f / "report/VIEWS_sheet.png").convert("RGB"))
    strip, cells = (0, 0, 2004, 12 + 22), (0, 12 + 22, 2004, 720)
    assert (shots[0].crop(strip).tobytes() != shots[1].crop(strip).tobytes(),
            shots[0].crop(cells).tobytes() == shots[1].crop(cells).tobytes()) == (True, True)


def test_check_package_fails_a_view_changed_after_the_sheet_because_the_user_approves_the_sheet(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front)
    png(f / "back.png", (300, 200), "#000000")
    assert package(f, front, card)[1]["package.sheet"] == ("fail", ["back"])


def test_check_package_wants_the_pointer_line_and_all_four_readme_sections(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front)
    text = (f / "README.md").read_text(encoding="utf-8")
    (f / "README.md").write_text(text.replace(POINTER, "# Bộ view").replace("## 2. TEXTURE NOTE\nkhông có\n", ""),
                                 encoding="utf-8")
    assert package(f, front, card)[1]["package.readme"] == ("fail", [
        "dòng đầu phải là dòng trỏ sang blockout.md", "cần đủ 4 mục theo thứ tự: NGOẠI LỆ, TEXTURE NOTE, Lật ảnh, Trạng thái duyệt"])


def test_a_symmetric_card_needs_the_flip_line_and_right_must_be_left_mirrored_pixel_for_pixel(tmp_path):
    f, front, card, concept = view_set(tmp_path, flip_line="không có")
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front)
    assert package(f, front, card)[1]["package.flip"] == (
        "fail", ["thẻ có symmetric.left_right: true, mục Lật ảnh cần `right = left lật ngang`"])
    f, front, card, concept = view_set(tmp_path / "b")
    png(f / "right.png", (300, 200), "#E8E8E8", [((40, 30, 200, 190), "#8B0000")])
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front)
    assert package(f, front, card)[1]["package.flip"] == ("fail", ["right.png không phải left.png lật ngang"])


def test_views_sheet_flip_and_crop_are_exact_pixel_operations(tmp_path):
    src = png(tmp_path / "left.png", (300, 200), "#E8E8E8", [((10, 10, 60, 90), "#8B0000")])
    tool("views_sheet", "flip", "--src", src, "--out", tmp_path / "right.png")
    assert Image.open(tmp_path / "right.png").getpixel((289, 10)) == (139, 0, 0)
    tool("views_sheet", "crop", "--image", src, "--box", "0,0,50,40", "--out", tmp_path / "ev/crop.png")
    assert Image.open(tmp_path / "ev/crop.png").size == (100, 80)


WALL, WIN = "#E6194B", "#3CB44B"


def house_guides(d, window_x=60, top_h=200, colours=(WALL, WIN)):
    d.mkdir(parents=True)
    (d / "views.json").write_text(json.dumps({"materials": {"WALL": colours[0], "WIN": colours[1]}}), encoding="utf-8")
    for v in VIEWS:
        h = top_h if v == "top" else 200
        rects = [((0, 0, 300, h), colours[0])] + ([((window_x, 80, window_x + 40, 120), colours[1])] if v == "back" else [])
        png(d / f"{v}_id.png", (400, 400), (0, 0, 0, 0), [((50 + x0, 50 + y0, 50 + x1, 50 + y1), c)
                                                         for (x0, y0, x1, y1), c in rects], mode="RGBA")
    return d


def test_diff_guides_names_only_the_views_whose_guide_changed_so_kept_views_cost_no_codex_call(tmp_path):
    old = house_guides(tmp_path / "old")
    new = house_guides(tmp_path / "new", window_x=200, top_h=220)
    out = tmp_path / "diff.json"
    rc, line, _ = tool("diff_guides", "--old", old, "--new", new, "--out", out)
    assert (rc, line) == (0, f"[views/diff_guides] đổi: back, top -> {out}\n")
    assert read(out)["data"]["changed"] == ["back", "top"]
    assert {c["check"]: c["value"]["changed"] for c in read(out)["checks"]} == {
        "diff.front": False, "diff.back": True, "diff.left": False, "diff.right": False, "diff.top": True}


def test_diff_guides_ignores_a_reshuffle_of_id_colours_because_it_compares_material_names(tmp_path):
    old = house_guides(tmp_path / "old")
    new = house_guides(tmp_path / "new", colours=(WIN, WALL))
    tool("diff_guides", "--old", old, "--new", new, "--out", tmp_path / "diff.json")
    assert read(tmp_path / "diff.json")["data"]["changed"] == []
