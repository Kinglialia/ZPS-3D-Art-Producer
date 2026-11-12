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


def test_param_variants_run_their_own_checks_so_a_picked_variant_carries_its_own_json():
    _, body = front(WORKER)
    assert ("gate từng part, mọi `check_*` và `check_fix.py` với `--work V/variants/<b|c>/`, render cùng bộ góc vào "
            "`V/variants/<b|c>/review/`") in body


def test_a_variant_clears_the_gate_json_it_copied_from_variant_a_before_it_gates_its_own_parts():
    """B3: the copy of F brings the gates of variant a. They describe other values, so they must not count."""
    _, body = front(WORKER)
    line = next(l for l in body.splitlines() if l.startswith("- `param`"))
    assert line.index("clear_gates.py --work V/variants/<b|c>/") < line.index("gate từng part")


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
    assert body.count("RUN bl ") == 5 and "`&`" not in body


def test_the_rule_to_run_every_command_in_the_foreground_stays_after_the_pid_text_went():
    _, body = front(WORKER)
    assert "Không chạy lệnh nền: mọi lệnh Bash chạy và chờ xong trong lượt" in body
    assert "không tự viết vòng lặp canh file" in body and "với `timeout: 3600000` cho Bash" in body


@pytest.mark.parametrize("command", [
    "RUN bl build_parts.py assembly --work F", "RUN bl build_parts.py param_fit --work F --spec V/work/spec.json",
    "RUN bl render_critic.py --work F --mode critic", "RUN bl render_review.py --work F",
    "RUN custom_mesh.py --work F", "RUN clear_gates.py --work F", "RUN check_layout.py --work F"])
def test_worker_writes_the_command_in_run_form(command):
    _, body = front(WORKER)
    assert command in body


def test_a_graph_with_a_custom_part_fits_its_params_in_blender_because_python_has_no_bmesh():
    """B1: param_fit builds the graph. A custom part is a bmesh, which exists only in Blender."""
    _, body = front(WORKER)
    assert ("Graph có part `custom`: `RUN bl build_parts.py param_fit --work F --spec V/work/spec.json`") in body


def test_the_final_gate_pass_starts_from_an_empty_gates_folder_and_gates_every_part():
    """B3: a gate JSON of an old build counts as a result, so step 7 clears them and gates every part again."""
    _, body = front(WORKER)
    step7 = next(l for l in body.splitlines() if l.startswith("7. "))
    assert step7.index("clear_gates.py") < step7.index("gate từng part") < step7.index("mọi `check_*`")


def test_a_build_with_upto_cannot_pass_check_layout_and_the_worker_is_told_to_read_the_bbox_check():
    """B2: layout.complete fails on --upto, so step 5 must not promise a pass before the full build."""
    _, body = front(WORKER)
    step5 = next(l for l in body.splitlines() if l.startswith("5. "))
    assert "`layout.complete` luôn fail" in step5 and "đọc `layout.bbox`" in step5
    assert "Cả `layout.bbox` và `layout.complete` phải pass ở lần tự kiểm cuối" in step5


def test_the_spec_json_the_worker_writes_has_no_blender_path_since_no_tool_reads_it():
    _, body = front(WORKER)
    assert '"paths"' not in body and "config.paths" not in body
    assert '`{"concept": {"views": {"<view>": "masks/<view>.png"}}}`' in body


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
    assert {"build_parts.py", "self_build/gates.py", "render_critic.py", "clear_gates.py", "custom_mesh.py"} <= tools
    for tool in tools:
        assert (AGENT / "tools" / tool).is_file(), tool


def test_reviewer_writes_acceptance_a_fix_can_reach_not_an_overlay_percentage():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "Không dùng % red/blue hay IoU của overlay làm ngưỡng" in text


def test_reviewer_checks_aligned_edges_and_parts_across_a_seam_which_the_pilot_reviewers_missed():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "chi tiết vắt qua khe ghép (khung cửa, dầm, ống máng)" in text
    assert "bậc lồi hay lệch mép không có trên concept là fail" in text
