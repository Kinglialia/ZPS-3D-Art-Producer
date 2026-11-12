"""Model agent files: routing guard (producer.md §3), common reviewer rules (D1, D25.B, D22.6), rubric keys, and worker
commands that match the tools they call, so a pilot never stops on a flag or file that does not exist."""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer"
AGENT = SKILL / "agents/zps-3dp-step-model"
WORKER = AGENT / "zps-3dp-step-model.md"
REVIEWER = SKILL / "agents/zps-3dp-check-clay.md"
FIXED = "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp."
CHECK_CLAY_KEYS = ["mass", "detail", "shading", "planes", "thumbnail", "density", "blockout_match", "shadow_read"]


def front(path):
    m = re.match(r"---\n(.*?)\n---\n(.*)", path.read_text(encoding="utf-8"), re.S)
    return dict(line.split(": ", 1) for line in m.group(1).splitlines()), m.group(2)


@pytest.mark.parametrize("path,name", [(WORKER, "zps-3dp-step-model"), (REVIEWER, "zps-3dp-check-clay")])
def test_agent_is_named_by_step_and_guarded_against_direct_calls(path, name):
    meta, _ = front(path)
    assert (meta["name"], meta["description"].startswith(FIXED), "model" in meta) == (name, True, False)


def test_pipeline_names_the_agents_whose_files_exist():
    steps = {s["id"]: s for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    m = steps["model"]
    assert (m.get("enabled", True), m["gate"], m["uses"], m["top_fix"]) == (True, "review_human", ["blender"],
                                                                           ["structure", "param"])
    assert ((SKILL / "agents" / f"zps-3dp-{m['agent']}" / f"zps-3dp-{m['agent']}.md").is_file(),
            (SKILL / "agents" / f"zps-3dp-{m['reviewer']}.md").is_file()) == (True, True)


def test_reviewer_is_read_only_and_carries_the_common_rules():
    meta, body = front(REVIEWER)
    assert meta["tools"] == "Read, Glob, Grep, Write"
    for rule in ("Bạn có xu hướng duyệt dễ. Ảnh sạch với chỉ số cao vẫn có thể sai khối hoặc sai style; kiểm từng tiêu chí.",
                 "Không tự đo", "EVIDENCE_OPENED", "`PRIOR`", "**mọi** finding đang mở", "kể cả `H<n>`", "`COMPARE`",
                 "`PICK`", "`structure` đúng một id", "`param` mọi finding `param` đang mở", "`need_evidence`",
                 "`superseded`", "`preference`", "giữa dòng `--- report ---` và dòng `--- end ---`", "Chỉ chấm trong phạm vi bước"):
        assert rule in body, rule
    for field in ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve",
                  "acceptance"):
        assert f"`{field}`" in body, field


def test_reviewer_writes_acceptance_a_fix_can_reach_not_a_bbox_normalised_number():
    _, body = front(REVIEWER)
    assert "Không dùng % hay IoU chuẩn hóa theo bbox làm ngưỡng" in body


def test_without_a_pilot_density_passes_as_not_checked_and_never_unclear_d21_7():
    _, body = front(REVIEWER)
    assert ("`not_checked` (chưa có pilot): ghi `pass` và ghi chú \"not_checked: chưa có pilot\" trong report; "
            "không ghi `unclear`") in body


def test_reviewer_checks_aligned_edges_and_details_across_seams_the_run_2_reviewers_missed():
    _, body = front(REVIEWER)
    assert ("Mép các khối chồng nhau (mái và tường, tầng và tầng) thẳng hàng như concept; chi tiết vắt qua khe ghép "
            "(khung cửa, dầm, ống máng) đúng phía như concept.") in body


def reviewer_keys():
    _, body = front(REVIEWER)
    return re.findall(r"^\d+\. `([a-z_]+)`:", body.split("## Rubric", 1)[1], re.M)


@pytest.mark.parametrize("rubric", ["building.md", "default.md"])
def test_rubric_template_model_keys_are_the_check_clay_keys(rubric):
    part = (SKILL / "templates/rubrics" / rubric).read_text(encoding="utf-8").split("\n## model\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^- ([a-z0-9_]+):", part, re.M) == reviewer_keys() == CHECK_CLAY_KEYS


TOOL = r"`RUN (bl )?((?:BT/)?[\w/<>.-]+\.py)([^`]*)`"
BLENDER_TOOLS = ("build_model.py", "qa_all.py", "render_all.py")
QUOTED = re.compile(r'"[^"]*"')
CHECK_ARGS = re.compile(r'--check-args "(\w+)=([^"]*)"')
DECISION_TAG = re.compile(r"\bD\d+(?:\.\d+)?\b")
PINNED_TAGS = {"D33.2", "D33.8"}


def calls(body):
    """(in Blender, tool path relative to T, arguments) of every RUN command of the worker file."""
    return [(bool(bl), t.replace("BT/", "../../zps-3dp-step-blockout/tools/"), a) for bl, t, a in re.findall(TOOL, body)]


def flags(text):
    return set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", text))


def test_worker_points_only_at_references_and_tools_that_exist():
    _, body = front(WORKER)
    refs = re.findall(r"`R/([\w.-]+)`", body)
    assert sorted(set(refs)) == ["fix.md", "model.md"] and all((AGENT / "references" / r).is_file() for r in refs), refs
    assert (AGENT / "tools" / "../../zps-3dp-step-blockout/references/part-graph.md").resolve().is_file()
    tools = {t for _, t, _ in calls(body)}
    assert len(tools) == 7 and all((AGENT / "tools" / t).is_file() for t in tools), tools
    assert all((AGENT / f"tools/asset_checks/{q}.py").is_file() for q in re.findall(r"`(\w+_check)`", body)), body


def test_every_flag_the_worker_passes_is_one_its_tool_accepts():
    """gate_all.py passes its --check-args to the check tools, so those flags are read against the check tool."""
    _, body = front(WORKER)
    found = calls(body)
    assert len(found) == 8  # check_inputs, make_spec, custom_mesh, gate_all twice, build_model, qa_all, render_all
    vpy = AGENT / "tools/.deps/venv/bin/python"
    py = str(vpy) if vpy.is_file() else sys.executable
    for _, script, args in found:
        for tool, used in [(script, flags(QUOTED.sub("", args)))] + [(f"{n}.py", flags(a)) for n, a in CHECK_ARGS.findall(args)]:
            out = subprocess.run([py, str(AGENT / "tools" / tool), "--help"], capture_output=True, text=True).stdout
            assert used <= flags(out), (tool, used - flags(out), out[-300:])


def test_every_tool_command_goes_through_run_and_every_blender_tool_through_run_bl():
    """run_tool.py holds the Blender slot, returns 1 on a failed result JSON and needs no PID wrapper; a bare python
    or blender command bypasses all three and asks for permission."""
    _, body = front(WORKER)
    assert re.findall(r"`(?:PY|BL|BLENDER|bash) ", body) == [] and "PID" not in body and "&" not in body
    assert {t for bl, t, _ in calls(body) if bl} == set(BLENDER_TOOLS)
    assert all(bl for bl, t, _ in calls(body) if t in BLENDER_TOOLS)


def test_the_worker_opens_blender_in_three_commands_and_builds_a_custom_part_in_the_venv_after_k15():
    """Since K15 the shared custom functions are pure Python, so no build of the model needs Blender. A worker told
    otherwise starts Blender for every build, which is what L10 removes."""
    _, body = front(WORKER)
    assert "RUN bl BT/build_parts" not in body and "graph có part `custom`: `RUN bl" not in body
    assert "Mọi bước dựng chạy trong venv, kể cả graph có part `custom`" in body
    assert len([1 for bl, _, _ in calls(body) if bl]) == 3


def test_the_worker_runs_custom_mesh_before_each_gate_of_a_graph_with_asset_functions_and_never_writes_parts_lib():
    """gate_all.py never runs the asset's custom_parts.py (its docstring), so a graph inherited from the blockout that
    calls such a function fails the first gate in a new version folder unless custom_mesh.py ran first."""
    _, body = front(WORKER)
    step3 = body.split("\n3. ", 1)[1].split("\n4. ", 1)[0]
    assert "Không viết `parts_lib.py`" in step3
    assert step3.index("`RUN BT/custom_mesh.py --work F`") < step3.index("`RUN gate_all.py")
    assert "sau mỗi lần sửa `part_graph.json` hoặc file đó" in step3


def test_the_worker_gates_the_detail_pass_with_one_gate_all_before_the_join_and_again_after_it():
    _, body = front(WORKER)
    pre, post = (c for c in re.findall(r"`RUN gate_all\.py ([^`]+)`", body))
    assert flags(QUOTED.sub("", pre)) == {"--work", "--check-flag", "--skip", "--check-args"} == flags(QUOTED.sub("", post))
    assert "--before-join" in pre and "--skip check_uv_edge" in pre
    assert "--before-join" not in post and "--skip check_uv_edge" not in post
    assert "--check-flag final" in pre and "--check-flag final" in post


def test_the_normal_renders_come_from_the_joined_glb_in_the_one_render_command():
    _, body = front(WORKER)
    assert "`RUN bl render_all.py --final F --concept C/concept_shadow.png`" in body
    assert "ảnh `normal_*` vẽ từ GLB đã join" in body


def test_every_reference_the_worker_names_says_when_to_read_it():
    """Q11: a worker that reads every reference at the start reads the fix round text on a first build. The brief prints
    the ACCEPTED_FAIL line of any step with an acceptable list, first build included, so that line is no reason to
    open fix.md."""
    _, body = front(WORKER)
    docs = body.split("## Tài liệu", 1)[1].split("## Quy trình", 1)[0]
    lines = [l for l in docs.splitlines() if l.startswith("- ")]
    assert len(lines) == 3 and all("đọc khi" in l.lower() for l in lines), lines
    assert "Mỗi part" in lines[1] and "Hàm custom" in lines[1] and "Bỏ qua các mục còn lại" in lines[1]
    assert "Không đọc ở lần dựng đầu" in lines[2] and "dòng `ACCEPTED_FAIL`" not in lines[2]


def test_the_fix_round_text_lives_in_fix_md_and_not_in_the_file_every_first_build_reads():
    _, body = front(WORKER)
    fix = (AGENT / "references/fix.md").read_text(encoding="utf-8")
    for heading in ("## `structure`", "## `param`", "## Bản đã duyệt trước", "## `ACCEPTED_FAIL`", "## Vòng xin bằng chứng"):
        assert heading in fix and heading not in body, heading
    assert "V/work/edits" in fix and "V/work/edits" not in body and "V/variants" not in body
    assert "ACCEPTED_FAIL: <file JSON>" in fix and "ACCEPTED_FAIL: <file JSON>" not in body


def test_a_finding_id_is_fid_and_the_file_name_letter_f_is_the_folder():
    """Q13: `<F>` was a finding id in a file where F is also the final folder."""
    _, body = front(WORKER)
    fix = (AGENT / "references/fix.md").read_text(encoding="utf-8")
    assert "<F>" not in body + fix and "<Fid>" in fix


def test_the_hard_gate_list_in_the_agent_file_has_every_name_of_the_code_list_counts_included():
    """Q13: the brief prints only the acceptable list, so the agent file keeps the hard gates. counts.json was missing."""
    state = (SKILL / "scripts/core/state.py").read_text(encoding="utf-8")
    code = re.search(r"^HARD_GATES = \(([^)]*)\)", state, re.M).group(1)
    stems = [n.removesuffix(".json").removeprefix("qa_") for n in re.findall(r'"([\w.]+)"', code)]
    _, body = front(WORKER)
    listed = re.search(r"Gate cứng \(([^)]*)\)", body).group(1)
    assert "counts" in stems and sorted(stems) == sorted(x.strip() for x in listed.split(","))


def test_no_decision_tag_stays_in_the_agent_text_except_the_two_the_foreground_rule_test_pins():
    _, body = front(WORKER)
    assert set(DECISION_TAG.findall(body)) == PINNED_TAGS
    for name in ("model.md", "fix.md"):
        assert DECISION_TAG.findall((AGENT / "references" / name).read_text(encoding="utf-8")) == [], name


def test_the_counts_example_names_no_removed_function_and_two_kinds_of_object():
    """U3: the example of a count that a function builds named grooved_box once; the agent copies its examples."""
    _, body = front(WORKER)
    text = body + "".join(p.read_text(encoding="utf-8") for p in (AGENT / "references").glob("*.md"))
    assert "grooved_box" not in text and "vault" not in text.lower()
    example = re.search(r"\(ví dụ ([^)]*)\)", body.split("`COUNTS:`", 1)[1]).group(1)
    assert "chân bàn" in example and "tường" in example


def test_model_reference_states_the_bbox_rule_the_bevel_exception_and_the_angle_convention():
    """The worker reads these before the checks fail: a bevel judged by the 3 px rule never gets built (9 mm is under
    1 px), and a sun or camera azimuth with the wrong sign lights the clay from the other side."""
    text = (AGENT / "references/model.md").read_text(encoding="utf-8")
    for rule in ("Model nằm trong bbox của blockout ±2 % trên mỗi trục.",
                 "Không áp ngưỡng pixel của quy tắc 2 cho bevel",
                 "`azimuth_deg` 0 = camera (hoặc nắng) ở phía trước (−Y), nhìn về +Y; số dương đưa camera sang +X",
                 '`"round": true`'):
        assert rule in text, rule


def test_the_light_line_of_the_brief_goes_to_make_spec_so_the_worker_no_longer_guesses_the_sun_g6():
    _, body = front(WORKER)
    step2 = next(l for l in body.split("## Quy trình")[1].splitlines() if l.startswith("2. "))
    step7 = next(l for l in body.split("## Quy trình")[1].splitlines() if l.startswith("7. "))
    assert 'Brief có dòng `LIGHT:`: thêm `--light "<giá trị sau LIGHT:>"`' in step2
    assert "`make_spec.py` đã ghi `sun`, không ước lượng lại" in step7 and "ghi thêm hướng nắng" in step7
    assert "--light" in (AGENT / "tools/make_spec.py").read_text(encoding="utf-8")
    text = (AGENT / "references/model.md").read_text(encoding="utf-8")
    assert "(`left` −45°, `right` +45°, `front` 0°)" in text and "`from` tính theo ảnh `concept_shadow.png`" in text
