"""Texture agent files: routing guard (producer.md §3), common reviewer rules (D1, D25.B, D22.6), rubric keys, Meshy
only through the wrapper, and worker commands whose flags the tools accept, so a pilot never stops on a wrong flag."""
import re
import tomllib
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer"
AGENT = SKILL / "agents/zps-3dp-step-texture"
WORKER = AGENT / "zps-3dp-step-texture.md"
REF = AGENT / "references/texture.md"
REVIEWER = SKILL / "agents/zps-3dp-check-texture.md"
FIXED = "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp."
KEYS = ["light", "material", "thumbnail", "seams", "texture_note", "meshy_detail", "geometry_match", "inventory"]


def front(path):
    m = re.match(r"---\n(.*?)\n---\n(.*)", path.read_text(encoding="utf-8"), re.S)
    return dict(line.split(": ", 1) for line in m.group(1).splitlines()), m.group(2)


@pytest.mark.parametrize("path,name", [(WORKER, "zps-3dp-step-texture"), (REVIEWER, "zps-3dp-check-texture")])
def test_agent_is_named_by_step_and_guarded_against_direct_calls(path, name):
    meta, _ = front(path)
    assert (meta["name"], meta["description"].startswith(FIXED), "model" in meta) == (name, True, False)


def test_pipeline_enables_texture_and_assemble_with_agents_and_a_script_that_exist():
    steps = {s["id"]: s for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    t, a = steps["texture"], steps["assemble"]
    assert (t.get("enabled", True), t["gate"], t["top_fix"], a.get("enabled", True), a["gate"], a["script"]) == (
        True, "review", ["repaint", "fix_uv_mesh", "meshy_regen", "note"], True, "checks_human", "assemble.py")
    assert ((AGENT / f"zps-3dp-{t['agent']}.md").is_file(), (SKILL / f"agents/zps-3dp-{t['reviewer']}.md").is_file(),
            (SKILL / "scripts" / a["script"]).is_file()) == (True, True, True)


def test_reviewer_is_read_only_and_carries_the_common_rules():
    meta, body = front(REVIEWER)
    assert meta["tools"] == "Read, Glob, Grep, Write"
    for rule in ("Bạn có xu hướng duyệt dễ. Ảnh sạch với chỉ số cao vẫn có thể sai khối hoặc sai style; kiểm từng tiêu chí.",
                 "Không tự đo", "EVIDENCE_OPENED", "`PRIOR`", "**mọi** finding đang mở", "kể cả `H<n>`", "`COMPARE`",
                 "`repaint` mọi finding `repaint` đang mở", "`need_evidence`", "`superseded`", "`preference`",
                 "chỉ dòng `VERDICT` và dòng `COUNTS`", "Chỉ chấm trong phạm vi bước",
                 "Không dùng % hay IoU chuẩn hóa theo bbox làm ngưỡng",
                 "Cùng mức: `fix_uv_mesh` trước `meshy_regen` trước `repaint`"):
        assert rule in body, rule
    for field in ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve",
                  "acceptance"):
        assert f"`{field}`" in body, field


def test_reviewer_diagnoses_colour_space_and_padding_before_asking_for_a_repaint():
    _, body = front(REVIEWER)
    assert ("Đen, sai màu, quá sáng: kiểm color space, alpha, normal trước khi đề xuất vẽ lại. Seam: kiểm vị trí cắt UV và "
            "padding") in body


def test_reviewer_inventories_painted_elements_and_ai_image_faults_d25_f():
    _, body = front(REVIEWER)
    assert "truy được về concept hoặc TEXTURE NOTE" in body and "hạt sáng không yêu cầu" in body


def reviewer_keys():
    _, body = front(REVIEWER)
    return re.findall(r"^\d+\. `([a-z_]+)`:", body.split("## Rubric", 1)[1], re.M)


@pytest.mark.parametrize("rubric", ["building.md", "default.md"])
def test_rubric_template_texture_keys_are_the_check_texture_keys(rubric):
    part = (SKILL / "templates/rubrics" / rubric).read_text(encoding="utf-8").split("\n## texture\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^- ([a-z0-9_]+):", part, re.M) == reviewer_keys() == KEYS


def commands():
    text = front(WORKER)[1] + REF.read_text(encoding="utf-8")
    return text, re.findall(r"`(?:PY|BL) T/([\w/]+\.py)([^`]*)`", text)


def test_worker_points_only_at_references_and_tools_that_exist():
    text, calls = commands()
    refs = re.findall(r"`references/([\w.-]+)`", front(WORKER)[1])
    assert refs and all((AGENT / "references" / r).is_file() for r in refs), refs
    tools = {s for s, _ in calls}
    assert tools == {"check_inputs.py", "texture_complexity.py", "id_map.py", "render_texture.py", "tex_measure.py",
                     "check_meshy.py", "tone_fix.py", "base_fill.py", "render_paint_views.py", "project_views.py",
                     "seam_fix.py", "crop_edit.py"}
    assert all((AGENT / "tools" / t).is_file() for t in tools)


def test_every_flag_the_worker_passes_is_one_its_tool_accepts():
    _, calls = commands()
    for script, args in calls:
        src = (AGENT / "tools" / script).read_text(encoding="utf-8")
        flags = set(re.findall(r"(--[a-z][a-z-]*)", args))
        assert all(f'"{f}"' in src for f in flags), (script, sorted(f for f in flags if f'"{f}"' not in src))


def test_meshy_runs_only_through_the_wrapper_with_the_brief_lines_and_never_reads_the_env_file():
    _, body = front(WORKER)
    assert "gen_api" not in body and "gen_api" not in REF.read_text(encoding="utf-8")
    assert '`PY "<MESHY>" texture <MESHY_ARGS> --model G --style-image C/concept_albedo.png' in body
    assert "Không đọc, in hay chép file `.env`." in body
    assert "MESHY_CALLS" in body and "Không sửa file budget." in body


def test_every_blender_command_goes_through_the_brief_blender_path():
    text, _ = commands()
    assert re.findall(r"(?<![A-Z_])blender -b", text) == []
    assert "`BL` = `BLENDER -b --python-exit-code 1 --python`" in front(WORKER)[1]


def test_a_fix_round_keeps_the_review_evidence_of_the_version_it_fixes_and_rerenders_only_what_steps_5_and_6_write():
    _, body = front(WORKER)
    assert ("Chép `P/final/` vào `F`, cả `review/` (`id_map.*`, `meshy_albedo.png`, `checks/meshy.json` là bằng chứng "
            "của lớp đang sửa), trừ file bước 5–6 ghi lại: `review/lit_*`, `review/unlit_*`, `review/thumb.png`, "
            "`review/renders.json`, `review/render_texture.json`, `review/checks/tex_measure.json`.") in body
    assert "trừ `review/`" not in body
