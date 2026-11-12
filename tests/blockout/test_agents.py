"""Agent files: routing guard (producer.md §3) and the common reviewer rules (D1, D25.B, D22.6)."""
import re

import pytest

from conftest import AGENT, TOOLS

FIXED = "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp."
WORKER = AGENT / "zps-3dp-step-blockout.md"
REVIEWER = AGENT.parent / "zps-3dp-check-blockout.md"


def front(path):
    m = re.match(r"---\n(.*?)\n---\n(.*)", path.read_text(encoding="utf-8"), re.S)
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    return meta, m.group(2)


@pytest.mark.parametrize("path,name", [(WORKER, "zps-3dp-step-blockout"), (REVIEWER, "zps-3dp-check-blockout")])
def test_agent_is_named_by_step_and_guarded_against_direct_calls(path, name):
    meta, _ = front(path)
    assert meta["name"] == name
    assert meta["description"].startswith(FIXED)
    assert "model" not in meta


def test_reviewer_is_read_only():
    meta, _ = front(REVIEWER)
    assert meta["tools"] == "Read, Glob, Grep, Write"


def test_reviewer_carries_the_common_rules():
    _, body = front(REVIEWER)
    for rule in ("Bạn có xu hướng duyệt dễ. Ảnh sạch với chỉ số cao vẫn có thể sai khối hoặc sai style; kiểm từng tiêu chí.",
                 "Không tự đo", "EVIDENCE_OPENED", "`PRIOR`", "**mọi** finding đang mở", "`COMPARE`", "`PICK`",
                 "`structure` đúng một id", "`param` mọi finding", "`need_evidence`", "`superseded`", "`preference`",
                 "giữa dòng `--- report ---` và dòng `--- end ---`", "Chỉ chấm trong phạm vi bước"):
        assert rule in body, rule
    for field in ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve",
                  "acceptance"):
        assert f"`{field}`" in body, field


SKILL = AGENT.parents[1]


def sections(path):
    out, cur = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^## (\w+)$", line):
            cur = out.setdefault(m.group(1), [])
        elif cur is not None and (m := re.match(r"^- ([a-z0-9_]+):", line)):
            cur.append(m.group(1))
    return out


@pytest.mark.parametrize("rubric", ["building.md", "default.md"])
def test_rubric_template_has_one_section_per_step_and_blockout_keys_are_the_reviewer_keys(rubric):
    import tomllib
    steps = [s["id"] for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]]
    got = sections(SKILL / "templates/rubrics" / rubric)
    _, body = front(REVIEWER)
    reviewer_keys = re.findall(r"^\d+\. `([a-z_]+)`:", body.split("## Rubric", 1)[1], re.M)
    assert set(got) <= set(steps) and got["blockout"] == reviewer_keys == [
        "mass", "silhouette", "identity", "open_closed", "props", "foot", "own_decisions"]


FIX = AGENT / "references/fix.md"


def test_a_param_variant_comes_from_one_make_variant_command_so_a_picked_variant_carries_its_own_json():
    """L2: the fix round used to list about 60 commands for two variants; the picked folder becomes final/, so each
    variant must have its own gates, checks and renders."""
    text = FIX.read_text(encoding="utf-8")
    assert "RUN make_variant.py --from F --out V/variants/<b|c> --set <param>=<giá trị>" in text
    assert "mỗi phương án giữ JSON của chính nó" in text
    assert "RUN bl render_review.py --work V/variants/<b|c>" in text


def test_nothing_sends_the_worker_to_clear_the_gate_json_because_gate_all_does_it_before_it_gates():
    _, body = front(WORKER)
    assert "clear_gates" not in body + FIX.read_text(encoding="utf-8") and not (AGENT / "tools/clear_gates.py").exists()


def test_worker_reads_blockout_md_sections_from_a_shipped_reference_with_the_summary_first():
    _, body = front(WORKER)
    assert "docs/" not in body and "`R/part-graph.md` mục `blockout.md`" in body
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8").split("## `blockout.md`", 1)[1]
    items = re.findall(r"^(\d+)\. (.+)$", pg.split("\n## ", 1)[0], re.M)
    assert [int(n) for n, _ in items] == list(range(1, 11))
    assert "Dòng đầu: `# Blockout <id> v<N>`" in pg
    assert items[2][1].startswith("Version, hash của `part_graph.json` + `parts_lib.py`")


def test_every_tool_command_goes_through_run_so_one_entry_holds_the_slot_the_log_and_the_exit_code():
    """D36.1: a bare Blender path, a python path or a PID wrapper skips the exit code and the slot count."""
    _, body = front(WORKER)
    assert "`RUN` = dòng `RUN:` của brief" in body
    assert re.findall(r"(?<![A-Z_])blender -b|BLENDER|\bPY\b|echo \$!|\.pid|dòng PID", body) == []
    assert sorted(re.findall(r"RUN bl (\w+\.py)", body)) == ["render_critic.py", "render_review.py"] and "`&`" not in body


def test_the_rule_to_run_every_command_in_the_foreground_stays_after_the_pid_text_went():
    _, body = front(WORKER)
    assert "Không chạy lệnh nền: mọi lệnh Bash chạy và chờ xong trong lượt" in body
    assert "không tự viết vòng lặp canh file" in body and "với `timeout: 3600000` cho Bash" in body


@pytest.mark.parametrize("command", [
    "RUN init_sources.py --work F", "RUN custom_mesh.py --work F", "RUN gate_all.py --work F",
    "RUN prep_overlay.py --work F", "RUN bl render_critic.py --work F --mode critic",
    "RUN bl render_review.py --work F", "RUN blockout_md.py --work F",
    "RUN build_parts.py param_fit --work F --spec V/work/spec.json"])
def test_worker_writes_the_command_in_run_form(command):
    _, body = front(WORKER)
    assert command in body


def test_a_graph_with_a_custom_part_builds_and_fits_in_the_venv_because_bevel_box_and_the_json_meshes_are_plain_arrays():
    """L4, U2: custom parts no longer need bmesh, so no command of the worker runs a build in Blender."""
    _, body = front(WORKER)
    fix = FIX.read_text(encoding="utf-8")
    assert "RUN build_parts.py param_fit --work F --spec V/work/spec.json" in body
    assert "RUN bl build_parts" not in body + fix and "Graph có part `custom`: `RUN bl" not in body


def test_the_worker_builds_once_through_gate_all_with_the_input_check_arguments_and_never_with_upto():
    """L1: the old procedure built with --upto part by part; gate_all builds the graph once and gates every part."""
    _, body = front(WORKER)
    step4 = next(l for l in body.splitlines() if l.startswith("4. "))
    assert "RUN gate_all.py --work F --check-args \"check_inputs=--approved" in step4
    assert "--upto" not in body + FIX.read_text(encoding="utf-8") and "layout.complete" not in body


def test_the_numbered_procedure_is_short_and_goes_sources_graph_gate_overlay_render_document():
    _, body = front(WORKER)
    steps = [l for l in body.split("## Quy trình", 1)[1].split("## Quy tắc", 1)[0].splitlines() if re.match(r"\d+\. ", l)]
    tools = [re.findall(r"RUN (?:bl )?(\w+\.py)", l) for l in steps]
    assert len(steps) == 7
    assert [t[0] for t in tools if t] == ["init_sources.py", "custom_mesh.py", "gate_all.py", "prep_overlay.py",
                                         "render_critic.py", "blockout_md.py"]


def test_the_spec_json_is_written_by_prep_overlay_and_the_worker_text_has_no_blender_path():
    _, body = front(WORKER)
    assert '"paths"' not in body and "config.paths" not in body and '"concept"' not in body
    assert "`V/work/spec.json`" in body and "RUN prep_overlay.py --work F --view <view>=<ảnh concept>" in body


def test_the_worker_renders_with_the_legend_tool_not_the_kit_render_views():
    """B8: the kit legend is white on light grey. render_critic.py runs the kit and redraws it dark."""
    _, body = front(WORKER)
    assert "render_views.py" not in body and "RUN bl render_critic.py" in body


def test_the_reference_names_render_critic_as_the_writer_of_the_critic_renders():
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8")
    assert "| `render_critic.py --outdir` |" in pg and "render_views" not in pg


def test_gate5_text_says_a_dirty_mesh_fails_the_gate_because_gate5_health_requires_a_clean_union():
    """B5: the text said a blockout need not have a clean mesh, while gates.py fails gate5.health on any open edge."""
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8")
    assert "không bắt buộc mesh sạch" not in pg
    assert "Gate `gate5.health` đòi mesh sạch" in pg
    assert 'check("gate5.health", "pass" if bad_h == 0' in (TOOLS / "self_build/gates.py").read_text(encoding="utf-8")


def test_dispatch_prompt_asks_for_the_lines_the_brief_names():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Ghi báo cáo đầy đủ vào `<report>`. Chỉ trả về các dòng brief yêu cầu." in text


def test_worker_points_only_at_files_that_exist():
    _, body = front(WORKER)
    for ref in re.findall(r"`references/([\w.-]+)`", body):
        assert (AGENT / "references" / ref).is_file(), ref
    tools = set(re.findall(r"RUN (?:bl )?((?:self_build/)?\w+\.py)", body)) | set(
        re.findall(r"T/((?:self_build/)?[\w.]+\.(?:py|sh))", body))
    assert {"build_parts.py", "gate_all.py", "init_sources.py", "blockout_md.py", "prep_overlay.py", "render_critic.py",
            "render_review.py", "custom_mesh.py"} <= tools
    for tool in tools:
        assert (AGENT / "tools" / tool).is_file(), tool


def test_reviewer_writes_acceptance_a_fix_can_reach_not_an_overlay_percentage():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "Không dùng % red/blue hay IoU của overlay làm ngưỡng" in text


def test_reviewer_checks_aligned_edges_and_parts_across_a_seam_which_the_pilot_reviewers_missed():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "chi tiết vắt qua khe ghép (khung cửa, dầm, ống máng)" in text
    assert "bậc lồi hay lệch mép không có trên concept là fail" in text


REFERENCES = sorted(p.name for p in (AGENT / "references").iterdir())
TAG = re.compile(r"\bD\d+(?:\.\d+)*\b")


def test_every_reference_is_listed_in_the_agent_file_with_the_moment_to_read_it():
    """Q11: a worker that reads every reference spends its turns on text it does not need now."""
    _, body = front(WORKER)
    assert REFERENCES == ["craft.md", "fix.md", "part-graph.md"]
    for name in REFERENCES:
        assert re.search(rf"^- `R/{re.escape(name)}`: đọc khi ", body, re.M), name
    assert "Không đọc ở lần dựng đầu" in body


def test_the_fix_round_text_is_in_fix_md_and_not_in_the_agent_file_that_every_run_reads():
    _, body = front(WORKER)
    fix = FIX.read_text(encoding="utf-8")
    assert "## Vòng sửa" not in body and "V/variants" not in body and "evidence-" not in body
    assert "## `structure`" in fix and "## `param`" in fix and "## Vòng xin bằng chứng" in fix
    assert "`V/work/edits/<Fid>/`" in fix


def test_craft_md_keeps_only_the_image_evidence_and_the_preflight_the_worker_needs():
    text = (AGENT / "references/craft.md").read_text(encoding="utf-8")
    assert "**Image evidence:**" in text and "**Preflight for script builds:**" in text
    assert "Analyze before you choose" not in text and "Normal map" not in text and "## A. Receive the task" not in text
    source = (AGENT / "SOURCE.md").read_text(encoding="utf-8")
    assert "technique.md" in source and "references/craft.md" in source and source.count("`references/craft.md`") == 1


def test_a_finding_id_is_written_fid_and_f_means_only_the_final_folder():
    """Q13: `<F>` meant both; a worker that read `edits/<F>/` could write the final folder in it."""
    _, body = front(WORKER)
    fix = FIX.read_text(encoding="utf-8")
    assert "<F>" not in body + fix and "<Fid>" in fix and "`F` = `V/final/`" in body


def test_decision_tags_are_gone_from_the_agent_file_and_its_references_except_the_two_other_tests_pin():
    """Q11: tests/test_watch.py pins "D33.2" and "(D33.8)" in every step agent file; no other tag stays."""
    _, body = front(WORKER)
    assert TAG.findall(body) == ["D33.2", "D33.8"]
    for name in REFERENCES:
        assert TAG.findall((AGENT / "references" / name).read_text(encoding="utf-8")) == [], name


BUILDING = ("mái", "tường", "cửa", "footprint", "tầng", "nhà", "công trình")


def test_the_instructions_use_words_that_hold_for_a_table_a_tree_a_rock_and_a_house():
    """Q12 (D34.4): a building word may stand inside an example, where it sits beside the other kinds, and nowhere else."""
    _, body = front(WORKER)
    fix = FIX.read_text(encoding="utf-8")
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8")
    example = re.compile(r"\((?:ví dụ|vd)\b[^)]*\)|(?:ví dụ|vd)[: ]+\"[^\"]+\"", re.I)
    body_text = body.split("---", 1)[-1]
    for text in (body_text, fix, pg):
        left = example.sub("", text).lower()
        assert [w for w in BUILDING if re.search(rf"(?<!\w){w}(?!\w)", left)] == []


def test_the_count_example_names_no_removed_function_and_two_kinds_of_object_with_the_tag_rule():
    """U3: grooved_box and vault left the library; the example is a tag on 4 table legs and a custom_parts.py function."""
    _, body = front(WORKER)
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8")
    assert "grooved_box" not in body + pg and "vault" not in body + pg
    line = next(l for l in body.splitlines() if l.startswith("Brief có dòng `COUNTS:`"))
    assert "`tag: legs`" in line and "`custom_parts.py`" in line and "chân bàn" in line and "lớp đá" in line


def test_the_worker_does_not_start_blockout_md_by_hand_because_blockout_md_py_makes_the_skeleton_after_the_build():
    """blockout_md.py refuses a file that does not start with the title, so the measuring table goes to notes.md first."""
    _, body = front(WORKER)
    assert "V/work/notes.md" in body and "Đừng tạo `blockout.md` bằng tay" in body
    assert "Khi `RUN` in `error`, đọc log" in body and "đủ mục" not in body
