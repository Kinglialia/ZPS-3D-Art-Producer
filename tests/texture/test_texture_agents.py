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
FIX = AGENT / "references/fix.md"
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
                 "giữa dòng `--- report ---` và dòng `--- end ---`", "Chỉ chấm trong phạm vi bước",
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
    text = front(WORKER)[1] + REF.read_text(encoding="utf-8") + FIX.read_text(encoding="utf-8")
    return text, re.findall(r"`RUN (?:bl )?([\w./-]+\.py)([^`]*)`", text)


def test_worker_points_only_at_references_and_tools_that_exist():
    text, calls = commands()
    refs = re.findall(r"`R/([\w.-]+)`", front(WORKER)[1])
    assert refs and all((AGENT / "references" / r).is_file() for r in refs), refs
    tools = {s for s, _ in calls}
    assert tools == {"check_inputs.py", "texture_complexity.py", "id_map.py", "render_texture.py", "tex_measure.py",
                     "check_meshy.py", "tone_fix.py", "base_fill.py", "render_paint_views.py", "project_views.py",
                     "seam_fix.py", "crop_edit.py", "make_paint_prompts.py",
                     "../../zps-3dp-step-views/tools/concept_colors.py"}
    assert all((AGENT / "tools" / t).resolve().is_file() for t in tools)


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


def test_every_tool_command_is_a_run_line_so_the_exit_code_and_the_log_come_from_run_tool_d36_1():
    text, calls = commands()
    body = front(WORKER)[1]
    assert re.findall(r"(?<![A-Z_])blender -b", text) == [] and re.findall(r"`(?:PY|BL) T/", text) == []
    assert "`RUN bl <tool> <args>` chạy tool trong Blender" in body
    assert set(re.findall(r"`RUN bl ([\w./-]+\.py)", text)) == {"render_texture.py", "render_paint_views.py"}
    assert not re.search(r"\bBL\b|dòng PID|nohup|disown|không `&`", text)


def test_a_fix_round_is_prepared_by_p_brief_so_the_fix_text_has_no_copy_list_and_the_toml_has_it_l14():
    """One wrong copy by hand left a stale measure or render in the new version: the list moved to pipeline.toml."""
    fix = FIX.read_text(encoding="utf-8")
    assert "Brief có `P` và `TOP_FIX`: làm theo `R/fix.md`" in front(WORKER)[1]
    assert "`F` đã có bản chép của `P/final/`" in fix and "Không chép tay." in fix
    assert not re.search(r"Chép `P/final/`|review/lit_|review/renders\.json|tex_measure\.json", fix)
    step = {s["id"]: s for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    assert step["texture"]["fix_copy_exclude"] == [
        "review/lit_*", "review/unlit_*", "review/thumb.png", "review/renders.json", "review/render_texture.json",
        "review/checks/tex_measure.json", "review/checks/render_fresh.json", "final_lit_vs_concept.png"]
    assert "id_map" not in " ".join(step["texture"]["fix_copy_exclude"])


def test_every_tool_gets_the_concept_colours_of_the_briefs_concept_colors_line_t14():
    """The colours come from intake (D43.1), also when the asset has no view set: no tool reads a views-step folder."""
    text, calls = commands()
    body = front(WORKER)[1]
    assert "`CC` = file màu concept: đường dẫn ở dòng `CONCEPT_COLORS:` của brief, cả khi `VIEWS: none`." in body
    assert "`F/concept_colors.json` (bước 1)" in body and "Dòng ghi `none`" in body
    assert "VF/concept_colors.json" not in text
    users = [(s, a) for s, a in calls if "--concept-colors" in a]
    assert sorted(s for s, _ in users) == ["base_fill.py", "make_paint_prompts.py", "tex_measure.py", "tone_fix.py"]
    assert all("--concept-colors CC " in a for _, a in users)


def test_tex_measure_gets_the_card_so_the_flipped_uv_check_knows_the_text_codes_g7():
    got = {s: a for s, a in commands()[1]}
    assert "--card C/asset-card.yaml" in got["tex_measure.py"]


def steps():
    return {int(n): line for n, line in re.findall(r"^(\d+)\. (.*)$", front(WORKER)[1].split("## Quy trình")[1].split("## Vòng sửa")[0], re.M)}


def test_the_albedo_is_measured_before_it_is_rendered_so_a_fix_never_leaves_a_stale_render_d36_11():
    s = steps()
    measure = [n for n, line in s.items() if "`RUN tex_measure.py" in line]
    render = [n for n, line in s.items() if "`RUN bl render_texture.py" in line]
    assert (measure, render) == ([5], [6])
    assert "sha256" in s[6] and "chạy lại bước 5 và 6" in s[6]


def test_the_resolution_is_res_and_r_is_only_the_references_folder_t15():
    text, _ = commands()
    assert not re.search(r"<R>|--res R\b|`R` = độ phân giải", text)
    assert "`R` = `T/../references`" in front(WORKER)[1] and "`RES` = độ phân giải" in front(WORKER)[1]
    assert "--res RES" in text and "albedo_<RES>.png" in text


def test_meshy_text_says_one_run_waits_28_minutes_and_has_no_dry_run_step_t16():
    body, ref = front(WORKER)[1], REF.read_text(encoding="utf-8")
    assert "--dry-run" not in body.replace("không chạy `--dry-run`", "") and "--dry-run" not in ref.replace(
        "không chạy `--dry-run`", "")
    assert "khoảng 28 phút (1700 s)" in body and "khoảng 28 phút (1700 s)" in ref and not re.search(r"\b8 phút", body + ref)


def test_tone_fix_and_seam_fix_get_the_inputs_the_new_checks_need():
    text, calls = commands()
    got = {s: a for s, a in calls}
    assert "--concept-colors" in got["tone_fix.py"] and "--model M" in got["seam_fix.py"]


def test_each_reference_says_when_to_read_it_and_the_fix_round_text_lives_only_in_fix_md_q11():
    _, body = front(WORKER)
    for ref in ("texture.md", "fix.md"):
        assert re.search(rf"^- `R/{re.escape(ref)}`: (?:chỉ )?đọc (?:khi|ở) ", body, re.M), ref
    assert "`repaint`:" not in body and "`meshy_regen`:" not in body


def test_the_worker_and_the_references_carry_no_decision_tag_except_the_two_that_test_watch_pins_q11():
    tags = lambda s: re.findall(r"\bD\d{2}(?:\.\d+)?\b", s)
    assert tags(front(WORKER)[1]) == ["D33.2", "D33.8"]
    assert tags(REF.read_text(encoding="utf-8")) == tags(FIX.read_text(encoding="utf-8")) == []


def test_shared_gen_images_stand_before_the_first_prompt_so_every_view_gets_them_l12():
    """gen_image_codex.py gives an --image placed after a --prompt to that job only."""
    _, body = front(WORKER)
    line = next(x for x in body.splitlines() if x.startswith("- Gen ảnh:"))
    assert line.index("--image <ảnh chung>") < line.index("--prompt") < line.index("--image <ảnh riêng>")
    ref = REF.read_text(encoding="utf-8").split("## 3. VẼ MỚI", 1)[1].split("## 4.", 1)[0]
    assert "Gen cả 8 view trong một lệnh" in ref and "`--image C/concept_albedo.png --size <size>` trước `--prompt` đầu tiên" in ref
    assert "Khi `GEN_ARGS` có `--batch`:" in ref and "`GEN_ARGS` có `--batch` (" not in ref


def test_the_reviewer_turns_a_mirrored_text_note_into_fix_uv_mesh_g7():
    """The texture worker cannot fix UV, so tex_measure only names the code and the reviewer judges on the renders."""
    _, body = front(REVIEWER)
    assert ("Check `uv.mirrored_faces` của `tex_measure.json` có note \"chữ có thể bị lật gương ở mã …\"" in body
            and "Chữ đọc ngược trên ảnh thì ghi finding `fix_uv_mesh`" in body)
