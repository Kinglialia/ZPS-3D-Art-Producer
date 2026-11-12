"""D30.12: every tool that writes files refuses to run outside the project root and creates no file.

Pilot run: a texture check started from the repo root wrote production/assets/.../review/checks/inputs.json there."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer"
MESSAGE = "LỖI: không thấy production/pipeline.toml: chạy lệnh từ gốc project"

GUARDED = [
    "scripts/assemble.py", "scripts/assemble_glb.py", "scripts/assemble_qa.py", "scripts/check_counts.py", "scripts/gen_image_codex.py",
    "scripts/meshy_call.py", "scripts/producer.py", "scripts/review_sheet.py", "scripts/run_tool.py",
    *(f"agents/zps-3dp-step-blockout/tools/{n}.py" for n in (
        "build_parts", "check_base", "check_fix", "check_inputs", "check_layout", "check_markers", "check_materials",
        "check_proportion", "check_schema", "check_support", "clear_gates", "concept_mask", "custom_mesh", "fit_view",
        "render_critic", "render_review")),
    *(f"agents/zps-3dp-step-model/tools/{n}.py" for n in (
        "check_detail", "check_inputs", "check_mesh", "check_uv_edge", "join_mesh", "make_spec", "render_review",
        "unwrap")),
    *(f"agents/zps-3dp-step-texture/tools/{n}.py" for n in (
        "base_fill", "check_inputs", "check_meshy", "crop_edit", "id_map", "project_views", "render_paint_views",
        "render_texture", "seam_fix", "tex_measure", "texture_complexity", "tone_fix")),
    *(f"agents/zps-3dp-step-views/tools/{n}.py" for n in (
        "check_inputs", "check_package", "concept_colors", "diff_guides", "measure", "pick_bg", "pick_size", "views_sheet")),
]
READ_ONLY = {"scripts/check_card.py", "scripts/check_profile.py"}
# Imported, not run: the guard belongs to the tool that imports them. settings_merge runs from install.py before
# `producer.py init` makes the marker.
LIBRARIES = {"scripts/root_guard.py", "scripts/settings_merge.py", "scripts/heartbeat.py", "agents/zps-3dp-step-blockout/tools/custom_lib.py",
             "agents/zps-3dp-step-blockout/tools/project_parts.py", "agents/zps-3dp-step-blockout/tools/mesh_from_json.py",
             "agents/zps-3dp-step-model/tools/lib/cli.py", "agents/zps-3dp-step-model/tools/lib/glbread.py",
             "agents/zps-3dp-step-texture/tools/lib/tex.py"}


def pinned() -> set[str]:
    """Kit copies that tests/*/test_*_source.py keep byte-identical (D2): no guard can go into them."""
    rows = set()
    for src in SKILL.glob("agents/*/SOURCE.md"):
        text = src.read_text(encoding="utf-8")
        rows |= {f"agents/{src.parent.name}/{d}" for d in re.findall(r"^\| `([^`]+\.py)` \| `[^`]+` \| `[0-9a-f]{64}` \|$",
                                                                     text, re.M)}
    return rows


def python_files() -> set[str]:
    files = [*SKILL.glob("scripts/*.py"), *SKILL.glob("agents/*/tools/**/*.py")]
    return {p.relative_to(SKILL).as_posix() for p in files if ".deps" not in p.parts}


def test_every_python_file_of_the_tools_is_guarded_or_named_as_not_writing():
    """A new tool fails here until someone adds require_root() to it or says why it needs none."""
    assert python_files() - pinned() - READ_ONLY - LIBRARIES == set(GUARDED)


@pytest.mark.parametrize("tool", GUARDED)
def test_a_tool_run_outside_the_project_root_exits_2_and_creates_no_file(tool, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PRODUCER_ROOT"} | {"PYTHONDONTWRITEBYTECODE": "1"}
    args = ["next"] if tool == "scripts/producer.py" else []
    r = subprocess.run([sys.executable, str(SKILL / tool), *args], cwd=tmp_path, env=env, capture_output=True,
                       text=True)
    assert (r.returncode, r.stderr.splitlines()[-1:]) == (2, [MESSAGE])
    assert list(tmp_path.iterdir()) == []


def test_producer_init_still_makes_the_project_root(tmp_path):
    r = subprocess.run([sys.executable, str(SKILL / "scripts/producer.py"), "init", "--project", "Pilot", "--concepts",
                        "concepts"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "production/pipeline.toml").is_file()


def test_the_guard_reads_the_root_of_the_runtime_session(tmp_path):
    """A/B (§16): a session with PRODUCER_ROOT=production-codex has no production/ folder."""
    (tmp_path / "production-codex").mkdir()
    (tmp_path / "production-codex/pipeline.toml").touch()
    env = os.environ | {"PRODUCER_ROOT": "production-codex", "PYTHONDONTWRITEBYTECODE": "1"}
    tool = SKILL / "agents/zps-3dp-step-texture/tools/check_inputs.py"
    r = subprocess.run([sys.executable, str(tool)], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 2 and "the following arguments are required" in r.stderr
