"""make_paint_prompts.py writes the 8 paint prompts of VẼ MỚI from one template (row L12), so the worker types no prompt
and all views go to one gen call. The texts below are literal: a change of the fixed words must change a test."""
import json

import pytest
import yaml

from texkit import tool

MATERIAL_MD = """# Material Handoff — crate

| Mã | Tên | Màu chính (hex) | Áp cho vùng nào |
|---|---|---|---|
| STONE | cream plastered stone | #8F8A80 | Bệ |
| TIMBER | dark oak planks | #5A4030 | Thân |
"""

FRONT = """Repaint image 2 (a flat-coloured 3D render of a game asset) with the finished surface colours of that asset,
in the exact art style, materials, colours and level of detail of the concept art in image 1.
Image 1: take the paint colours and material detail only; ignore its lighting, shadows and camera.

STRICT RULES
- Orthographic view from azimuth 0 degrees, 30 degrees above: the camera of image 2. No perspective.
- Keep EXACTLY the silhouette, size and position of image 2, pixel for pixel.
  Do not move, scale, rotate or crop the object. Do not add or remove any part.
- Each flat colour in image 2 marks one material: #8F8A80 = STONE, cream plastered stone; #5A4030 = TIMBER, dark oak planks.
  Paint each region with that material as it looks in the concept. Keep every border between materials where image 2 has it.
- Texture note, paint it where image 2 shows its place: biển chữ "TAVERN" trên cửa
- Texture note, paint it where image 2 shows its place: vân gỗ dọc trên cửa
- Unlit base colour only: even light, no shading, no cast or contact shadow, no highlight, no dark ambient-occlusion corners.
  Keep material detail (grain, weave, wear) as painted colour variation.
- Plain, flat, solid background #FF8C00. No ground, no vignette, no text, no labels, no border.
"""


@pytest.fixture
def inputs(tmp_path):
    paint, c, vr = tmp_path / "paint", tmp_path / "crate", tmp_path / "VR"
    for d in (paint, c, vr):
        d.mkdir()
    cam = {"matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "ortho_scale": 2.0, "w": 1536, "h": 1024}
    (paint / "cameras.json").write_text(json.dumps({"views": [
        {"k": k, "azimuth_deg": 45 * k, "elevation_deg": (30, -30)[k % 2], "guide": f"guide_{k}.png",
         "paint": f"paint_{k}.png", "camera": cam} for k in range(8)]}), encoding="utf-8")
    (c / "crate.material.md").write_text(MATERIAL_MD, encoding="utf-8")
    (c / "asset-card.yaml").write_text(yaml.safe_dump({"real_texture_only_notes": ['biển chữ "TAVERN" trên cửa']},
                                                      allow_unicode=True), encoding="utf-8")
    (vr / "README.md").write_text("# README\n## TEXTURE NOTE\n- vân gỗ dọc trên cửa\n## Khác\n- x\n", encoding="utf-8")
    (tmp_path / "cc.json").write_text(json.dumps({"STONE": "#8F8A80", "TIMBER": "#5A4030"}), encoding="utf-8")
    return tmp_path


def run(t, *extra):
    return tool("make_paint_prompts.py", "--views", t / "paint", "--concept", t / "crate", "--concept-colors",
                t / "cc.json", "--view-set", t / "VR", "--out", t / "prompts", *extra)


def test_each_view_gets_the_template_with_its_camera_materials_notes_and_a_keyable_background(inputs):
    rc, out = run(inputs)
    assert (rc, out) == (0, f"[texture/make_paint_prompts] 8 prompt paint_{{0,1,2,3,4,5,6,7}}.md -> {inputs}/prompts, "
                            "--size 1536x1024, nền #FF8C00\n")
    assert (inputs / "prompts/paint_0.md").read_text(encoding="utf-8") == FRONT
    one = (inputs / "prompts/paint_1.md").read_text(encoding="utf-8")
    assert one == FRONT.replace("azimuth 0 degrees, 30 degrees above", "azimuth 45 degrees, 30 degrees below")


def test_in_one_batch_call_each_prompt_names_its_own_guide_after_the_concept(inputs):
    rc, out = run(inputs, "--batch", "--k", "3", "--k", "5", "--fix", "keep the object exactly where its guide is")
    assert rc == 0, out
    assert sorted(p.name for p in (inputs / "prompts").iterdir()) == ["paint_3.md", "paint_5.md"]
    three, five = ((inputs / f"prompts/paint_{k}.md").read_text(encoding="utf-8") for k in (3, 5))
    assert three == FRONT.replace("azimuth 0 degrees, 30 degrees above", "azimuth 135 degrees, 30 degrees below") \
        + "- keep the object exactly where its guide is\n"
    assert five == three.replace("image 2", "image 3").replace("azimuth 135", "azimuth 225")


def test_a_view_that_is_not_in_cameras_json_stops_the_run(inputs):
    rc, out = run(inputs, "--k", "9")
    assert (rc, out) == (2, "[texture/make_paint_prompts] error: cameras.json không có view 9\n")
