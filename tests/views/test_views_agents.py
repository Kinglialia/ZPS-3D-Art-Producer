"""Views agent files: routing guard (producer.md §3), common reviewer rules (D1, D25.B, D22.6), and worker commands
that match the tools they call, so a pilot never stops on a flag or file that does not exist."""
import re
import tomllib
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer"
AGENT = SKILL / "agents/zps-3dp-step-views"
WORKER = AGENT / "zps-3dp-step-views.md"
REVIEWER = SKILL / "agents/zps-3dp-check-views.md"
FIXED = "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp."


def front(path):
    m = re.match(r"---\n(.*?)\n---\n(.*)", path.read_text(encoding="utf-8"), re.S)
    return dict(line.split(": ", 1) for line in m.group(1).splitlines()), m.group(2)


@pytest.mark.parametrize("path,name", [(WORKER, "zps-3dp-step-views"), (REVIEWER, "zps-3dp-check-views")])
def test_agent_is_named_by_step_and_guarded_against_direct_calls(path, name):
    meta, _ = front(path)
    assert (meta["name"], meta["description"].startswith(FIXED), "model" in meta) == (name, True, False)


def test_reviewer_is_read_only_and_carries_the_common_rules():
    meta, body = front(REVIEWER)
    assert meta["tools"] == "Read, Glob, Grep, Write"
    for rule in ("Bạn có xu hướng duyệt dễ. Ảnh sạch với chỉ số cao vẫn có thể sai khối hoặc sai style; kiểm từng tiêu chí.",
                 "Không tự đo", "EVIDENCE_OPENED", "`PRIOR`", "**mọi** finding đang mở", "`COMPARE`",
                 "`regen` liệt kê mọi finding `regen` đang mở (kiểu lô)", "`regen_front` đúng một id", "`need_evidence`",
                 "`superseded`", "`preference`", "giữa dòng `--- report ---` và dòng `--- end ---`", "Chỉ chấm trong phạm vi bước"):
        assert rule in body, rule
    for field in ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve",
                  "acceptance"):
        assert f"`{field}`" in body, field


def test_reviewer_writes_acceptance_a_regen_can_reach_not_a_bbox_normalised_number():
    _, body = front(REVIEWER)
    assert "Không dùng IoU hay % vị trí chi tiết làm ngưỡng: chúng chuẩn hóa theo bbox" in body


def test_the_set_reviewer_never_rejudges_the_approved_front_except_through_regen_front():
    _, body = front(REVIEWER)
    rest = body.split("### views_rest", 1)[1]
    assert "Front đã duyệt ở `views_front`: không chấm lại, không ghi finding về front." in rest
    assert "một finding `regen_front`, `region` mở đầu bằng `front:`" in rest


def test_a_regen_front_finding_is_judged_on_front_png_only_by_the_front_reviewer_so_the_set_reviewer_writes_acceptance_for_it():
    _, body = front(REVIEWER)
    on_front, on_rest = body.split("### views_rest", 1)[0], body.split("### views_rest", 1)[1]
    assert ("Finding `regen_front` mang từ `views_rest` sang đây: chấm nó chỉ trên `front.png`. "
            "Không mở back, left, right, top để chấm nó.") in on_front
    assert ("`acceptance` của nó phải thấy được trên `front.png` một mình, vì reviewer của `views_front` "
            "chấm nó chỉ trên `front.png`.") in on_rest


def reviewer_keys(step):
    _, body = front(REVIEWER)
    part = body.split(f"### {step}\n", 1)[1].split("\n### ", 1)[0]
    return re.findall(r"^\d+\. `([a-z_]+)`:", part, re.M)


def rubric_keys(path, step):
    part = path.read_text(encoding="utf-8").split(f"\n## {step}\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- ([a-z0-9_]+):", part, re.M)


@pytest.mark.parametrize("rubric", ["building.md", "default.md"])
@pytest.mark.parametrize("step,keys", [
    ("views_front", ["style", "shape", "light", "inventory"]),
    ("views_rest", ["style", "shape", "light", "inventory", "sync", "hidden_sides", "props"])])
def test_rubric_template_keys_of_each_views_step_are_the_reviewer_keys(rubric, step, keys):
    assert rubric_keys(SKILL / "templates/rubrics" / rubric, step) == reviewer_keys(step) == keys


def test_worker_points_only_at_references_and_tools_that_exist():
    _, body = front(WORKER)
    for ref in re.findall(r"`R/([\w.-]+)`", body):
        assert (AGENT / "references" / ref).is_file(), ref
    for tool in set(re.findall(r"`RUN (?:bl )?([\w.]+\.py)", body)):
        assert (AGENT / "tools" / tool).is_file(), tool


def test_every_tool_command_of_the_worker_goes_through_run_and_none_through_a_bare_python_or_a_pid_wrapper():
    _, body = front(WORKER)
    assert re.findall(r"PY T/|\bBLENDER\b|PID|\bnohup\b|`PY (?!\"<GEN_IMAGE>\")", body) == []
    assert re.findall(r"`PY ([^ ]+)", body) == ['"<GEN_IMAGE>"']
    assert "Không chạy lệnh nền: mọi lệnh Bash chạy ở foreground và chờ xong trong lượt" in body and "`&`" not in body


def test_every_flag_the_worker_passes_is_one_its_tool_parses():
    _, body = front(WORKER)
    calls = re.findall(r"`(?:RUN (?:bl )?([\w.]+\.py)|PY (\"<GEN_IMAGE>\" <GEN_ARGS>))([^`]*)`", body)
    assert len(calls) == 18
    for script, gen, args in calls:
        src = SKILL / "scripts/gen_image_codex.py" if gen else AGENT / "tools" / script
        text = src.read_text(encoding="utf-8")
        for flag in set(re.findall(r"(--[a-z][a-z-]*)", args)):
            assert f'"{flag}"' in text, (script or gen, flag)


def test_every_blender_command_uses_the_brief_blender_path_and_only_views_front_renders():
    _, body = front(WORKER)
    assert re.findall(r"(?<![A-Z_])blender -b|BLENDER", body) == [] and re.findall(r"`RUN bl ([\w.]+\.py)", body) == ["render_blockout_views.py"]
    steps = {s["id"]: s for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    assert (steps["views_front"]["uses"], steps["views_rest"]["uses"]) == (["blender", "codex_image"], ["codex_image"])


def test_the_readme_template_of_the_reference_passes_check_package_sections():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_package", AGENT / "tools/check_package.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    ref = (AGENT / "references/views.md").read_text(encoding="utf-8").split("## 5. `README.md`", 1)[1]
    blocks = re.findall(r"```text\n(.*?)```", ref, re.S)
    assert blocks[0].strip() == cp.POINTER
    assert re.findall(r"^## \d\. (.+)$", blocks[1], re.M) == list(cp.SECTIONS)


def test_the_worker_writes_no_prompt_by_hand_and_passes_every_view_of_a_step_in_one_gen_call():
    _, body = front(WORKER)
    assert "Không viết prompt bằng tay" in body and "`RUN make_prompt.py --view <view>" in body
    assert "Một lệnh gen cho mọi view của bước" in body and "một lệnh cho mọi view fail" in body
    assert body.count("--pick-best V/work/gen") == 2 and "data.accepted_fail" in body and "data.ngoai_le" in body


def test_the_reference_has_a_read_when_trigger_in_the_worker_and_holds_no_prompt_template_after_the_move_to_the_tool():
    _, body = front(WORKER)
    ref = (AGENT / "references/views.md").read_text(encoding="utf-8")
    assert "`R/views.md`: đọc khi" in body
    assert "STRICT RULES" not in ref and "STRICT RULES" in (AGENT / "tools/make_prompt.py").read_text(encoding="utf-8")


def test_the_worker_and_the_reference_name_no_building_part_so_their_examples_fit_any_object():
    """A barrel, a tree and a hut get the same text. The fixed words of the prompt are pinned in test_make_prompt."""
    for path in (WORKER, AGENT / "references/views.md"):
        text = path.read_text(encoding="utf-8").lower()
        assert [w for w in ("roof", "fascia", "plinth", "mái", "tường", "dầm") if w in text] == [], path.name


def test_the_worker_and_the_reference_carry_no_decision_tag_except_the_two_that_test_watch_pins():
    _, body = front(WORKER)
    tags = lambda t: re.findall(r"\bD\d{2}(?:\.\d+)?\b", t)
    assert tags(body) == ["D33.2", "D33.8"]
    assert tags((AGENT / "references/views.md").read_text(encoding="utf-8")) == []
