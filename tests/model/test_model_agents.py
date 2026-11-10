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


def test_worker_points_only_at_references_and_tools_that_exist():
    _, body = front(WORKER)
    refs = re.findall(r"`R/([\w.-]+)`", body)
    assert refs and all((AGENT / "references" / r).is_file() for r in refs), refs
    assert (AGENT / "tools" / "../../zps-3dp-step-blockout/references/part-graph.md").resolve().is_file()
    tools = set(re.findall(r"T/([\w/]+\.(?:py|sh))", body))
    assert len(tools) == 12 and all((AGENT / "tools" / t).is_file() for t in tools), tools
    assert all((AGENT / f"tools/asset_checks/{q}.py").is_file() for q in re.findall(r"`(\w+_check)`", body)), body


def test_every_flag_the_worker_passes_is_one_its_tool_accepts():
    _, body = front(WORKER)
    calls = re.findall(r"`(?:PY|BL) T/([\w/<>.-]+\.py)([^`]*)`", body)
    assert len(calls) == 12
    vpy = AGENT / "tools/.deps/venv/bin/python"
    for script, args in calls:
        flags = set(re.findall(r"(--[a-z][a-z-]*)", args))
        if script.startswith("asset_checks/"):
            text = (AGENT / "tools/asset_checks/ac_common.py").read_text(encoding="utf-8")
            assert all(f'"{f}"' in text for f in flags), (script, flags)
            continue
        py = str(vpy) if vpy.is_file() else sys.executable
        target = args.split()[:1] if script.endswith("build_parts.py") else []
        if (script.startswith("self_build/") or target) and not vpy.is_file():
            continue
        out = subprocess.run([py, str(AGENT / "tools" / script), *target, "--help"], capture_output=True, text=True).stdout
        assert all(f in out for f in flags), (script, flags, out[-300:])


def test_every_blender_command_goes_through_the_brief_blender_path():
    _, body = front(WORKER)
    assert re.findall(r"(?<![A-Z_])blender -b", body) == []
    assert "`BL` = `BLENDER -b --python-exit-code 1 --python`" in body
