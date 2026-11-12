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
    tool("pick_bg", "--final", tmp_path, "--concept", stone_and_wood, "--profile", profile(tmp_path, "#1E90FF"))
    assert {k: read(tmp_path / "bg_color.json")[k] for k in ("hex", "source")} == {"hex": "#1E90FF", "source": "profile"}


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
    assert {k: v[0] for k, v in checks(f / "review/checks/measure.json").items() if k.startswith("views.")} == {
        "views.front": "pass", "views.back": "fail"}
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
    card.write_text("views: full_top\nsymmetric: {left_right: true, front_back: false}\n", encoding="utf-8")
    concept = png(tmp_path / "concept_albedo.png", (200, 200), "#FFFFFF")
    return f, front, card, concept


def package(f, front, card):
    rc, _, _ = tool("check_package", "--final", f, "--front", front, "--card", card)
    return rc, checks(f / "review/checks/package.json")


def test_views_sheet_puts_concept_and_5_views_over_their_overlays_and_records_what_it_was_built_from(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    rc, out, _ = tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)
    assert rc == 0 and out == f"[views/views_sheet] 2 hàng 2004x720 -> {f / 'report/VIEWS_sheet.png'}\n"
    assert sorted(read(f / "report/VIEWS_sheet.json")["inputs"]) == sorted(VIEWS)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card, "--crop", "back:40,30,140,130")
    with Image.open(f / "report/VIEWS_sheet.png") as im:
        assert im.size == (2004, 1074)
    assert package(f, front, card) == (0, {"package.views": ("pass", []), "package.sheet": ("pass", []),
                                           "package.readme": ("pass", []), "package.flip": ("pass", [])})


@pytest.mark.parametrize("mode, shipped, width", [
    ("back", ["back", "front"], 12 + 3 * 332),
    ("full", ["back", "front", "left", "right"], 12 + 5 * 332),
    (None, ["back", "front", "left", "right"], 12 + 5 * 332),
])
def test_views_sheet_and_check_package_take_only_the_views_of_the_card_so_full_ships_no_top_d35(tmp_path, mode,
                                                                                                  shipped, width):
    """D35: no step after views needs top; `back` keeps front because front is the colour reference."""
    f, front, card, concept = view_set(tmp_path)
    for v in {"back", "left", "right", "top"} - set(shipped):
        (f / f"{v}.png").unlink()
    card.write_text(("" if mode is None else f"views: {mode}\n") + "symmetric: {left_right: true, front_back: false}\n",
                    encoding="utf-8")
    assert tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)[0] == 0
    assert sorted(read(f / "report/VIEWS_sheet.json")["inputs"]) == shipped
    with Image.open(f / "report/VIEWS_sheet.png") as im:
        assert im.width == width
    assert package(f, front, card) == (0, {"package.views": ("pass", []), "package.sheet": ("pass", []),
                                           "package.readme": ("pass", []), "package.flip": ("pass", [])})


def test_check_package_fails_a_full_top_set_without_top_png_d35(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    (f / "top.png").unlink()
    assert package(f, front, card)[1]["package.views"] == ("fail", ["top"])


def test_views_sheet_marks_kept_views_in_the_label_strip_only_so_the_user_sees_which_views_are_new(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    shots = []
    for kept in ((), ("--kept", "back,left")):
        tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card, *kept)
        shots.append(Image.open(f / "report/VIEWS_sheet.png").convert("RGB"))
    strip, cells = (0, 0, 2004, 12 + 22), (0, 12 + 22, 2004, 720)
    assert (shots[0].crop(strip).tobytes() != shots[1].crop(strip).tobytes(),
            shots[0].crop(cells).tobytes() == shots[1].crop(cells).tobytes()) == (True, True)


def missing(font, ch):
    m, box = font.getmask(ch), font.getmask("\U000F0000")
    return (m.size, bytes(m)) == (box.size, bytes(box))


VIETNAMESE = "aàáảãạăằắẳẵặâầấẩẫậđeèéẻẽẹêềếểễệiìíỉĩịoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữựyỳýỷỹỵ"


def test_views_sheet_labels_use_the_bundled_noto_sans_on_every_machine_and_it_draws_every_vietnamese_letter_d27_12(
        monkeypatch, tmp_path):
    sys.path.insert(0, str(TOOLS))
    import views_sheet
    font, drawn = views_sheet.fit("back (giữ)")
    letters = VIETNAMESE + VIETNAMESE.upper()
    assert (font.getname(), drawn, [c for c in letters if missing(font, c)]) == (("Noto Sans", "Regular"), "back (giữ)", [])
    monkeypatch.setattr(views_sheet, "FONT", str(tmp_path / "none.ttf"))
    assert [views_sheet.fit(t)[1] for t in ("back (giữ)", "front không đo")] == ["back (giu)", "front khong do"]


def test_check_package_fails_a_view_changed_after_the_sheet_because_the_user_approves_the_sheet(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)
    png(f / "back.png", (300, 200), "#000000")
    assert package(f, front, card)[1]["package.sheet"] == ("fail", ["back"])


def test_check_package_wants_the_pointer_line_and_all_four_readme_sections(tmp_path):
    f, front, card, concept = view_set(tmp_path)
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)
    text = (f / "README.md").read_text(encoding="utf-8")
    (f / "README.md").write_text(text.replace(POINTER, "# Bộ view").replace("## 2. TEXTURE NOTE\nkhông có\n", ""),
                                 encoding="utf-8")
    assert package(f, front, card)[1]["package.readme"] == ("fail", [
        "dòng đầu phải là dòng trỏ sang blockout.md", "cần đủ 4 mục theo thứ tự: NGOẠI LỆ, TEXTURE NOTE, Lật ảnh, Trạng thái duyệt"])


def test_a_symmetric_card_needs_the_flip_line_and_right_must_be_left_mirrored_pixel_for_pixel(tmp_path):
    f, front, card, concept = view_set(tmp_path, flip_line="không có")
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)
    assert package(f, front, card)[1]["package.flip"] == (
        "fail", ["thẻ có symmetric.left_right: true, mục Lật ảnh cần `right = left lật ngang`"])
    f, front, card, concept = view_set(tmp_path / "b")
    png(f / "right.png", (300, 200), "#E8E8E8", [((40, 30, 200, 190), "#8B0000")])
    tool("views_sheet", "make", "--final", f, "--concept", concept, "--front", front, "--card", card)
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


ID_TRIM = "#3CB44B"
BROWN, BROWN_15 = "#8B5A2B", "#9A5A2B"


def wall_trim_guides(d, views=("front",), prop=False, trim_x=250):
    """A wall (left) and a trim band (right) in a 300x300 object, optionally with one separate prop beside it."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "views.json").write_text(json.dumps({"materials": {"WALL": ID_STONE, "TRIM": ID_TRIM}}), encoding="utf-8")
    for v in views:
        rects = [((50, 50, trim_x, 350), ID_STONE), ((trim_x, 50, 350, 350), ID_TRIM)]
        if prop:
            rects.append(((360, 300, 390, 350), ID_STONE))
        png(d / f"{v}_id.png", (400, 400), (0, 0, 0, 0), rects, mode="RGBA")
    return d


def wall_trim_gen(path, wall=BROWN, trim=BROWN_15, trim_x=375, margin=75, prop=False, bg="#E8E8E8"):
    """600x600 repaint of wall_trim_guides: the 300 px object of the guide is 450 px here."""
    rects = [((margin, margin, trim_x, 525), wall), ((trim_x, margin, 525, 525), trim)]
    if prop:
        rects.append(((540, 450, 585, 525), wall))
    return png(path, (600, 600), bg, rects)


def measure(tmp_path, views="front", extra=(), guides=None):
    g, f = guides or wall_trim_guides(tmp_path / "guides"), tmp_path / "final"
    rc, out, err = tool("measure", "--final", f, "--guides", g, "--views", views, *extra)
    rep = f / "report/report.json"
    return rc, out + err, (read(rep) if rep.is_file() else None), f / "review/checks/measure.json"


def test_two_materials_of_almost_one_colour_do_not_fail_detail_because_no_edge_can_be_seen_between_them_v2(tmp_path):
    """A pixel-perfect repaint of a wall and a trim 15 RGB apart (dE 7.3, under the dE 10 an eye needs) has no edge
    for the detail measure to find. Failing it asks the worker to regenerate a correct image."""
    wall_trim_gen(tmp_path / "final/front.png")
    rc, out, rep, check = measure(tmp_path)
    front = rep["views"]["front"]
    assert (rc, front["detail"], front["verdict"], rep["regen"]) == (0, None, "pass", [])
    assert checks(check)["detail.front"][0] == "not_checked"
    assert checks(check)["detail.front"][1] == {"WALL": ["TRIM"], "TRIM": ["WALL"]}


def test_a_boundary_between_two_clearly_different_materials_in_the_wrong_place_still_fails_detail_v2(tmp_path):
    """The V2 exception must not hide a real misplaced detail: the trim starts at a sixth of the width, not at two
    thirds. Region medians would mix the two colours here, so the test is what keeps the rule honest."""
    wall_trim_gen(tmp_path / "final/front.png", trim="#2F4F4F", trim_x=150)
    rc, _, rep, check = measure(tmp_path)
    assert (rc, rep["regen"], rep["views"]["front"]["status"]["detail"]) == (1, ["front"], "fail")
    assert "detail.front" not in checks(check)


def test_two_materials_the_concept_paints_apart_must_show_a_border_even_when_the_image_paints_them_alike_v2(tmp_path):
    """The V2 exception is for colours that are alike in the concept too. Here the concept says the trim is dE 13 from
    the wall: an image with one colour for both has lost the border, and detail must say so."""
    cc = tmp_path / "cc.json"
    cc.write_text(json.dumps({"WALL": BROWN, "TRIM": "#8B7A4B"}), encoding="utf-8")
    wall_trim_gen(tmp_path / "final/front.png", trim=BROWN)
    rc, _, rep, check = measure(tmp_path, extra=("--concept-colors", cc))
    assert (rc, rep["views"]["front"]["status"]["detail"], "detail.front" in checks(check)) == (1, "fail", False)


def test_a_material_beside_two_blind_neighbours_lists_both_of_them_v2(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "views.json").write_text(json.dumps({"materials": {"A": ID_STONE, "B": ID_TRIM, "C": "#4363D8"}}), encoding="utf-8")
    png(g / "front_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 150), ID_STONE), ((50, 150, 350, 250), ID_TRIM),
                                                       ((50, 250, 350, 350), "#4363D8")], mode="RGBA")
    png(tmp_path / "final/front.png", (600, 600), "#E8E8E8", [((75, 75, 525, 225), BROWN), ((75, 225, 525, 375), BROWN_15),
                                                           ((75, 375, 525, 525), "#9A5A3B")])
    rc, _, _, check = measure(tmp_path, guides=g)
    assert checks(check)["detail.front"][1] == {"A": ["B"], "B": ["A", "C"], "C": ["B"]}


def test_a_boundary_in_the_right_place_between_different_materials_passes_detail_v2(tmp_path):
    wall_trim_gen(tmp_path / "final/front.png", trim="#2F4F4F")
    rc, _, rep, _ = measure(tmp_path)
    assert (rc, rep["views"]["front"]["status"]["detail"]) == (0, "pass")


GRAIN_FROM, GRAIN_TO = (125, 95, 55), (155, 80, 30)


def grain(width, height=200):
    """Wood paint that drifts from a muted to a saturated brown across the patch. Its median is the middle colour; the
    `vivid` colour of its biggest cluster sits at the saturated end, dE 5.9 away."""
    import numpy as np
    cols = [np.round(np.add(GRAIN_FROM, np.subtract(GRAIN_TO, GRAIN_FROM) * x / (width - 1))) for x in range(width)]
    return np.tile(np.array(cols, np.uint8)[None], (height, 1, 1))


def test_concept_colors_is_the_median_of_the_box_not_the_vivid_colour_of_its_biggest_cluster_v3(tmp_path):
    Image.fromarray(grain(200)).save(tmp_path / "c.png")
    rc, _, _ = tool("concept_colors", "--final", tmp_path, "--concept", tmp_path / "c.png", "--box", "WALL=0,0,200,200")
    assert (rc, read(tmp_path / "concept_colors.json")) == (0, {"WALL": "#8C582A"})


def test_a_patch_compared_with_itself_gives_a_colour_distance_near_zero_v3(tmp_path):
    """D36.5: the concept colour and the measured colour must be one statistic. With 'vivid' against the median the
    same wood patch scored dE 5.9 (6.8 in the review), over the texture limit of 3."""
    Image.fromarray(grain(200)).save(tmp_path / "c.png")
    tool("concept_colors", "--final", tmp_path, "--concept", tmp_path / "c.png", "--box", "WALL=0,0,200,200")
    g = solid_guides(tmp_path / "guides", ("front",))
    gen = Image.new("RGB", (600, 600), "#E8E8E8")
    gen.paste(Image.fromarray(grain(450, 450)), (75, 75))
    (tmp_path / "final").mkdir()
    gen.save(tmp_path / "final/front.png")
    rc, _, rep, _ = measure(tmp_path, extra=("--concept-colors", tmp_path / "concept_colors.json"), guides=g)
    cell = rep["colours"]["WALL"]["views"]["front"]
    assert (rc, cell["delta_e"] < 1.0) == (0, True), cell


def test_concept_colors_is_importable_so_intake_measures_with_the_same_function_v3(tmp_path):
    sys.path.insert(0, str(TOOLS))
    import concept_colors
    assert concept_colors.median_hex(Image.fromarray(grain(200)), (0, 0, 200, 200)) == "#8C582A"


def test_a_box_over_two_materials_fails_because_its_median_is_neither_of_them_v8(stone_and_wood, tmp_path):
    rc, out, _ = tool("concept_colors", "--final", tmp_path, "--concept", stone_and_wood, "--box", "STONE=60,30,140,170")
    assert (rc, (tmp_path / "concept_colors.json").exists()) == (1, False)
    got = checks(tmp_path / "review/checks/concept_colors.json")
    assert got["colors.STONE"][0] == "fail" and got["colors.STONE"][1]["main_share"] < 0.6


def test_a_noisy_single_material_box_passes_the_main_cluster_limit_v8(tmp_path):
    import random
    rnd = random.Random(3)
    im = Image.new("RGB", (100, 100))
    im.putdata([tuple(max(0, min(255, c + rnd.randint(-12, 12))) for c in (139, 90, 43)) for _ in range(10000)])
    im.save(tmp_path / "c.png")
    rc, out, _ = tool("concept_colors", "--final", tmp_path, "--concept", tmp_path / "c.png", "--box", "WALL=0,0,100,100")
    assert (rc, out.startswith("[views/concept_colors] 100x100 WALL=#")) == (0, True)


def test_a_material_of_the_front_guide_without_a_box_fails_because_measure_would_take_its_colour_from_the_front_v8(
        tmp_path, stone_and_wood):
    f = tmp_path / "final"
    wall_trim_guides(f / "guides")
    rc, _, _ = tool("concept_colors", "--final", f, "--concept", stone_and_wood, "--box", "WALL=30,30,90,170")
    got = checks(f / "review/checks/concept_colors.json")
    assert (rc, got["colors.codes"]) == (1, ("fail", ["TRIM"]))
    assert not (f / "concept_colors.json").exists()
    rc, _, _ = tool("concept_colors", "--final", f, "--concept", stone_and_wood, "--box", "WALL=30,30,90,170",
                    "--box", "TRIM=110,30,170,170")
    assert rc == 0


def front_mismatch_gen(path):
    """A front 30% taller than the guide: its aspect fails, and so does its mirror against back."""
    return png(path, (600, 600), "#E8E8E8", [((75, 30, 525, 570), BROWN)])


def solid_guides(d, views):
    d.mkdir(parents=True, exist_ok=True)
    (d / "views.json").write_text(json.dumps({"materials": {"WALL": ID_STONE}}), encoding="utf-8")
    for v in views:
        png(d / f"{v}_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 350), ID_STONE)], mode="RGBA")
    return d


def test_with_front_given_the_approved_front_is_never_listed_for_regen_but_its_mirror_partner_is_v4(tmp_path):
    """views_rest cannot regenerate the front. A failing front/back pair means the back is the view to redo."""
    g = solid_guides(tmp_path / "guides", ("front", "back"))
    front = front_mismatch_gen(tmp_path / "views_front/front.png")
    png(tmp_path / "final/back.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), BROWN)])
    rc, _, rep, check = measure(tmp_path, "front,back", ("--front", front), guides=g)
    assert rep["views"]["front"]["verdict"] == "fail" and rep["mirrors"][0]["status"] == "fail"
    assert (rep["regen"], rc) == (["back"], 1)
    assert {k: v[0] for k, v in checks(check).items() if k.startswith("views.")} == {"views.front": "info",
                                                                                   "views.back": "fail"}
    assert "Views to generate again: Back\n" in (tmp_path / "final/report/report.md").read_text(encoding="utf-8")


def test_without_front_given_a_failing_front_is_still_regenerated_in_views_front_v4(tmp_path):
    g = solid_guides(tmp_path / "guides", ("front",))
    front_mismatch_gen(tmp_path / "final/front.png")
    rc, _, rep, _ = measure(tmp_path, guides=g)
    assert (rc, rep["regen"]) == (1, ["front"])


def test_view_names_are_stripped_and_an_unknown_name_stops_with_exit_2_and_measures_nothing_v5(tmp_path):
    g = solid_guides(tmp_path / "guides", ("front", "back"))
    for v in ("front", "back"):
        png(tmp_path / f"final/{v}.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), BROWN)])
    rc, _, rep, _ = measure(tmp_path, "front, back", guides=g)
    assert (rc, sorted(rep["views"])) == (0, ["back", "front"])
    rc, out, rep, _ = measure(tmp_path / "x", "front,bakc", guides=g)
    assert rc == 2 and "bakc" in out and "front, back, left, right, top" in out and rep is None


def test_a_named_view_without_an_image_fails_even_when_a_space_follows_the_comma_v5(tmp_path):
    g = solid_guides(tmp_path / "guides", ("front", "back"))
    png(tmp_path / "final/front.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), BROWN)])
    rc, _, _, check = measure(tmp_path, "front, back", guides=g)
    assert (rc, checks(check)["views.back"][0]) == (1, "fail")


def test_views_rest_takes_the_colour_reference_from_the_measured_front_and_the_concept_only_where_front_has_none_v6(
        tmp_path):
    """D36: front is the colour standard of the set. A material the front never shows (the roof) has no front colour, so
    the concept colour is its reference, not the median of the views (which is the view itself, dE 0 always)."""
    g = tmp_path / "guides"
    g.mkdir()
    (g / "views.json").write_text(json.dumps({"materials": {"WALL": ID_STONE, "ROOF": ID_TRIM}}), encoding="utf-8")
    png(g / "front_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 350), ID_STONE)], mode="RGBA")
    png(g / "back_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 200), ID_STONE), ((50, 200, 350, 350), ID_TRIM)], mode="RGBA")
    front = png(tmp_path / "views_front/front.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), "#7A4F26")])
    png(tmp_path / "final/back.png", (600, 600), "#E8E8E8", [((75, 75, 525, 300), "#7A4F26"), ((75, 300, 525, 525), "#556B2F")])
    cc = tmp_path / "views_front/concept_colors.json"
    cc.write_text(json.dumps({"WALL": BROWN, "ROOF": "#8B0000"}), encoding="utf-8")
    rc, _, rep, _ = measure(tmp_path, "front,back", ("--front", front, "--concept-colors", cc), guides=g)
    rows = {m: (r["reference"], r["reference_hex"]) for m, r in rep["colours"].items()}
    assert rows == {"WALL": ("front view", "#7A4F26"), "ROOF": ("concept", "#8B0000")}
    assert (rc, rep["regen"]) == (1, ["back"])


def test_views_front_still_compares_the_front_with_the_concept_colours_v6(tmp_path):
    cc = tmp_path / "cc.json"
    cc.write_text(json.dumps({"WALL": "#8B0000", "TRIM": BROWN}), encoding="utf-8")
    wall_trim_gen(tmp_path / "final/front.png", trim="#2F4F4F")
    rc, _, rep, _ = measure(tmp_path, extra=("--concept-colors", cc))
    assert {m: r["reference"] for m, r in rep["colours"].items()} == {"WALL": "concept", "TRIM": "concept"}
    assert rc == 1


def test_a_profile_background_too_close_to_a_concept_colour_fails_like_a_picked_one_would_be_skipped_v7(
        tmp_path, stone_and_wood):
    """MIN_DIST keeps measure.py from keying a material out as background. The profile value had no such check."""
    rc, out, _ = tool("pick_bg", "--final", tmp_path, "--concept", stone_and_wood, "--profile",
                      profile(tmp_path, "#4B3121"))
    assert (rc, (tmp_path / "bg_color.json").exists()) == (1, False)
    assert out.startswith("[views/pick_bg] fail: nền của profile #4B3121 cách #4A3020 chỉ ")


def test_pick_size_orients_each_view_by_the_box_it_shows_v9(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    box = {"width_x": 2.0, "depth_y": 1.0, "height_z": 3.0}
    (g / "views.json").write_text(json.dumps({"bbox_size_m": box}), encoding="utf-8")
    rc, out, _ = tool("pick_size", "--guides", g, "--out", tmp_path / "work/sizes.json")
    assert rc == 0 and out == f"[views/pick_size] front=1024x1536 back=1024x1536 left=1024x1536 right=1024x1536 top=1536x1024 bottom=1536x1024 -> {tmp_path / 'work/sizes.json'}\n"
    assert read(tmp_path / "work/sizes.json")["top"] == "1536x1024"


def test_pick_size_gives_a_wide_view_and_a_square_view_the_landscape_size_v9(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "views.json").write_text(json.dumps({"bbox_size_m": {"width_x": 4.0, "depth_y": 2.0, "height_z": 2.0}}), encoding="utf-8")
    tool("pick_size", "--guides", g, "--out", tmp_path / "sizes.json")
    assert read(tmp_path / "sizes.json") == {"front": "1536x1024", "back": "1536x1024", "left": "1536x1024",
                                             "right": "1536x1024", "top": "1536x1024",
                                             "bottom": "1536x1024"}


def test_a_gen_that_touches_the_image_border_fails_because_the_object_is_cropped_v15(tmp_path):
    wall_trim_gen(tmp_path / "final/front.png", margin=0)
    rc, _, rep, check = measure(tmp_path)
    assert (rc, checks(check)["border.front"][0]) == (1, "fail")
    wall_trim_gen(tmp_path / "ok/final/front.png")
    rc, _, _, check = measure(tmp_path / "ok")
    assert (rc, checks(check)["border.front"][0]) == (0, "pass")


def test_the_approved_front_that_touches_the_border_is_only_info_in_views_rest_v15(tmp_path):
    front = wall_trim_gen(tmp_path / "views_front/front.png", margin=0)
    g = wall_trim_guides(tmp_path / "guides", ("front", "back"))
    wall_trim_gen(tmp_path / "final/back.png")
    rc, _, rep, check = measure(tmp_path, "front,back", ("--front", front), guides=g)
    got = {k: v[0] for k, v in checks(check).items()}
    assert (got["border.front"], got["border.back"]) == ("info", "pass")


def test_a_missing_prop_fails_the_component_count_against_the_guide_v15(tmp_path):
    g = wall_trim_guides(tmp_path / "guides", prop=True)
    wall_trim_gen(tmp_path / "final/front.png")
    rc, _, _, check = measure(tmp_path, guides=g)
    assert (rc, checks(check)["components.front"]) == (1, ("fail", {"guide": 2, "image": 1}))
    wall_trim_gen(tmp_path / "ok/final/front.png", prop=True)
    rc, _, _, check = measure(tmp_path / "ok", guides=g)
    assert checks(check)["components.front"] == ("pass", {"guide": 2, "image": 2})


def test_a_pale_halo_around_the_object_is_reported_as_info_never_as_fail_v15(tmp_path):
    png(tmp_path / "final/front.png", (600, 600), "#E8E8E8", [((60, 60, 540, 540), "#D0D0D0"), ((75, 75, 525, 525), BROWN)])
    rc, _, _, check = measure(tmp_path, guides=solid_guides(tmp_path / "guides", ("front",)))
    status, value = checks(check)["ring.front"]
    assert (status, value["halo_share"] > 0.5) == ("info", True)
    wall_trim_gen(tmp_path / "ok/final/front.png")
    assert checks(measure(tmp_path / "ok")[3])["ring.front"][1]["halo_share"] == 0.0


def test_a_strong_light_gradient_across_a_material_is_reported_as_info_v15(tmp_path):
    ramp = Image.new("RGB", (450, 450))
    ramp.putdata([(40 + x * 200 // 450,) * 3 for _ in range(450) for x in range(450)])
    flat = png(tmp_path / "flat/final/front.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), "#808080")])
    shaded = tmp_path / "final/front.png"
    png(shaded, (600, 600), "#E8E8E8")
    im = Image.open(shaded)
    im.paste(ramp, (75, 75))
    im.save(shaded)
    g = solid_guides(tmp_path / "guides", ("front",))
    status, shaded_v = checks(measure(tmp_path, guides=g)[3])["light.front"]
    flat_v = checks(measure(tmp_path / "flat", guides=g)[3])["light.front"][1]
    assert (status, shaded_v["WALL"] > 0.5, flat_v["WALL"] < 0.02) == ("info", True, True)


def test_a_left_made_again_leaves_a_stale_right_that_the_colour_match_fails_unless_measure_mirrors_right_v10(tmp_path):
    """Symmetric asset: right is left mirrored. The worker makes left again after a fail; if right is not mirrored again,
    the old right is measured and fails the colour match with the new left, and `regen` asks for a paid gen of a view
    that should be a flip."""
    g = tmp_path / "guides"
    g.mkdir()
    (g / "views.json").write_text(json.dumps({"materials": {"WALL": ID_STONE}}), encoding="utf-8")
    for v in ("left", "right"):
        png(g / f"{v}_id.png", (400, 400), (0, 0, 0, 0), [((50, 50, 350, 350), ID_STONE)], mode="RGBA")
    f = tmp_path / "final"
    png(f / "left.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), BROWN)])
    tool("views_sheet", "flip", "--src", f / "left.png", "--out", f / "right.png")
    png(f / "left.png", (600, 600), "#E8E8E8", [((75, 75, 525, 525), "#556B2F")])
    rc, _, rep, _ = measure(tmp_path, "left,right", guides=g)
    assert (rc, sorted(rep["regen"])) == (1, ["left", "right"])
    rc, _, rep, _ = measure(tmp_path, "left,right", ("--mirror-right",), guides=g)
    assert (rc, rep["regen"]) == (0, [])
    assert ImageOps.mirror(Image.open(f / "left.png")).tobytes() == Image.open(f / "right.png").tobytes()
