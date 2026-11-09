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
                 "`superseded`", "`preference`", "chỉ dòng `VERDICT` và dòng `COUNTS`", "Chỉ chấm trong phạm vi bước"):
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
    for ref in re.findall(r"`references/([\w.-]+)`", body):
        assert (AGENT / "references" / ref).is_file(), ref
    for tool in set(re.findall(r"T/([\w.]+\.(?:py|sh))", body)):
        assert (AGENT / "tools" / tool).is_file(), tool


def test_every_flag_the_worker_passes_is_one_its_tool_parses():
    _, body = front(WORKER)
    calls = re.findall(r"`PY (T/[\w.]+\.py|\"<GEN_IMAGE>\" <GEN_ARGS>)([^`]*)`", body)
    assert len(calls) == 12
    for script, args in calls:
        src = (SKILL / "scripts/gen_image_codex.py" if "GEN_IMAGE" in script else AGENT / "tools" / script[2:])
        text = src.read_text(encoding="utf-8")
        for flag in set(re.findall(r"(--[a-z][a-z-]*)", args)):
            assert f'"{flag}"' in text, (script, flag)


def test_every_blender_command_uses_the_brief_blender_path_and_only_views_front_renders():
    _, body = front(WORKER)
    assert re.findall(r"(?<![A-Z_])blender -b", body) == [] and body.count("BLENDER -b") == 1
    steps = {s["id"]: s for s in tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]}
    assert (steps["views_front"]["uses"], steps["views_rest"]["uses"]) == (["blender", "codex_image"], ["codex_image"])


def test_the_readme_template_of_the_reference_passes_check_package_sections():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_package", AGENT / "tools/check_package.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    ref = (AGENT / "references/views.md").read_text(encoding="utf-8").split("## 6. `README.md`", 1)[1]
    blocks = re.findall(r"```text\n(.*?)```", ref, re.S)
    assert blocks[0].strip() == cp.POINTER
    assert re.findall(r"^## \d\. (.+)$", blocks[1], re.M) == list(cp.SECTIONS)
