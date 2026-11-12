"""make_prompt.py writes the image prompt of one view from the files of the step, so the model writes only the
description of the hidden side. The expected texts below are literal: a change of the fixed words must change a test."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/agents/zps-3dp-step-views/tools/make_prompt.py"

MATERIAL_MD = """# Material Handoff — crate

Nền ảnh concept: #EEEDEA (off-white)

| Mã | Tên | Màu chính (hex) | Chất liệu, bề mặt | Áp cho vùng nào trên asset này |
|---|---|---|---|---|
| STONE | cream plastered stone | #8F8A80 | Đá xếp | Bệ |
| TIMBER | dark oak planks | #5A4030 | Gỗ thô | Thân |
| ROOF_TILE | red clay tile | #7A3B2E | Ngói | Mái |
"""

FRONT = """Repaint image 2 (a flat-coloured 3D guide render) as a finished game-asset illustration
in the exact art style, materials, colours and level of detail of the concept art in image 1.
Image 1: take the shapes and paint colours only; ignore its lighting and shadows.

STRICT RULES
- Orthographic FRONT view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 2.
  Do not add, remove, move, resize or rotate any part.
- Keep the top edge, base and ground contact at exactly the heights of image 2.
- Each flat colour in image 2 marks one material: #E6194B red = STONE, cream plastered stone; #3CB44B green = TIMBER, dark oak planks; #FFE119 yellow = ROOF_TILE, red clay tile.
  Paint each region with that material as it looks in the concept.
- 3 separate props, each where image 2 shows it.
- Plain, flat, solid background #E8E8E8. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light. Keep material detail (grain, weave, finish) as painted colour variation.
- The whole object fully visible and centred. Do not crop. Do not stretch.
"""

BACK = """Image 2 is the approved FRONT view of an object. Image 3 is a flat-coloured 3D guide render
of the BACK view of the SAME object.
Repaint image 3 so it looks like the same object as image 2, from the BACK side,
in the art style of the concept in image 1.

STRICT RULES
- Orthographic BACK view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 3.
  Do not add, remove, move, resize or rotate any part.
- Keep the top edge, base and ground contact at exactly the heights of image 3.
- Each flat colour in image 3 marks one material: #E6194B red = STONE, cream plastered stone; #3CB44B green = TIMBER, dark oak planks; #FFE119 yellow = ROOF_TILE, red clay tile.
  Every material must have the SAME colour, texture and wear as in image 2.
- What this side looks like: plain wall, one small window high on the left.
- 3 separate props, each where image 3 shows it.
- Plain, flat, solid background #E8E8E8. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light.
- The whole object fully visible and centred. Do not crop. Do not stretch.
"""


def guide(path, shapes):
    """A guide mask: one main object and `shapes - 1` separate props beside it (400x400, transparent background)."""
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    im.paste((230, 25, 75, 255), (50, 50, 250, 350))
    for k in range(shapes - 1):
        im.paste((60, 180, 75, 255), (270, 100 + 70 * k, 330, 150 + 70 * k))
    im.save(path)


@pytest.fixture
def step(tmp_path):
    ref, concept = tmp_path / "ref", tmp_path / "_approved/crate"
    (ref / "guides").mkdir(parents=True)
    for view, shapes in (("front", 4), ("back", 4), ("left", 1)):
        guide(ref / "guides" / f"{view}_id.png", shapes)
    (ref / "guides/views.json").write_text(json.dumps({"materials": {
        "STONE": "#E6194B", "TIMBER": "#3CB44B", "ROOF_TILE": "#FFE119"}}), encoding="utf-8")
    (ref / "bg_color.json").write_text(json.dumps({"hex": "#E8E8E8", "source": "pick"}), encoding="utf-8")
    concept.mkdir(parents=True)
    (concept / "crate.material.md").write_text(MATERIAL_MD, encoding="utf-8")
    sizes = tmp_path / "work/sizes.json"
    sizes.parent.mkdir()
    sizes.write_text(json.dumps({"front": "1536x1024", "back": "1536x1024", "left": "1024x1536"}), encoding="utf-8")

    def run(view, *extra, out="work/prompts/x-1.md"):
        p = subprocess.run([sys.executable, str(TOOL), "--view", view, "--ref", str(ref), "--concept", str(concept),
                            "--sizes", str(sizes), "--out", str(tmp_path / out), *extra],
                           capture_output=True, text=True)
        return p, tmp_path / out
    run.dirs = {"ref": ref, "concept": concept, "sizes": sizes}
    return run


def test_the_front_prompt_is_the_template_with_the_materials_the_background_and_the_prop_count_filled(step):
    p, out = step("front")
    assert p.returncode == 0, p.stdout + p.stderr
    assert out.read_text(encoding="utf-8") == FRONT
    assert p.stdout == f"[views/make_prompt] {out} 1536x1024\n"


def test_a_side_view_prompt_holds_the_hidden_side_text_and_the_fix_line_of_a_regen(step):
    p, out = step("back", "--hidden", "plain wall, one small window high on the left.", out="work/prompts/back-1.md")
    assert p.returncode == 0, p.stdout + p.stderr
    assert out.read_text(encoding="utf-8") == BACK
    p, out = step("back", "--hidden", "plain wall, one small window high on the left",
                  "--fix", "leave a margin of background on all four sides", out="work/prompts/back-2.md")
    assert out.read_text(encoding="utf-8") == BACK + "- leave a margin of background on all four sides\n"


def test_the_size_line_is_the_size_of_that_view_from_sizes_json_so_a_tall_view_gets_a_portrait_size(step):
    p, out = step("left", "--hidden", "a door", out="work/prompts/left-1.md")
    assert p.stdout == f"[views/make_prompt] {out} 1024x1536\n"


def test_the_prop_count_is_the_separate_shapes_of_that_views_guide_minus_the_main_object(step):
    """The same number the components check compares with the image, so the prompt asks for what the gate will count.
    A view whose guide is one shape gets no prop line."""
    guide(step.dirs["ref"] / "guides/front_id.png", 2)
    p, out = step("front")
    assert "- 1 separate props, each where image 2 shows it.\n" in out.read_text(encoding="utf-8")
    p, out = step("left", "--hidden", "a door", out="work/prompts/left-1.md")
    text = out.read_text(encoding="utf-8")
    assert p.returncode == 0 and "separate props" not in text and "- Plain, flat, solid background" in text


def test_a_material_code_without_a_row_in_the_handoff_stops_the_tool_with_the_code_and_the_file_named(step):
    (step.dirs["concept"] / "crate.material.md").write_text(MATERIAL_MD.replace("| TIMBER |", "| OAK |"), encoding="utf-8")
    p, out = step("front")
    assert p.returncode == 2 and not out.exists()
    assert "TIMBER" in p.stdout and "crate.material.md" in p.stdout


def test_a_handoff_without_the_code_and_name_columns_stops_the_tool_with_a_clear_message(step):
    (step.dirs["concept"] / "crate.material.md").write_text("# Material Handoff\n\n- STONE: grey\n", encoding="utf-8")
    p, out = step("front")
    assert p.returncode == 2 and not out.exists() and "bảng" in p.stdout


@pytest.mark.parametrize("view,extra", [("back", []), ("front", ["--hidden", "a door"])])
def test_the_hidden_side_belongs_to_the_side_views_only_so_a_wrong_call_is_refused(step, view, extra):
    p, out = step(view, *extra)
    assert p.returncode == 2 and not out.exists()


def test_a_colour_that_is_not_in_the_palette_gets_the_nearest_colour_word(step):
    (step.dirs["ref"] / "guides/views.json").write_text(json.dumps({"materials": {"STONE": "#E81A4E"}}), encoding="utf-8")
    p, out = step("front")
    assert "#E81A4E red = STONE, cream plastered stone" in out.read_text(encoding="utf-8")
