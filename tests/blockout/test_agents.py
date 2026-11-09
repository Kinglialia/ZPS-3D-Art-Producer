"""Agent files: routing guard (producer.md §3) and the common reviewer rules (D1, D25.B, D22.6)."""
import re

import pytest

from conftest import AGENT

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
                 "chỉ dòng `VERDICT` và dòng `COUNTS`", "Chỉ chấm trong phạm vi bước"):
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
    assert ("chạy gate, mọi `check_*` và `check_fix.py` với `--work V/variants/<b|c>/`, render cùng bộ góc vào "
            "`V/variants/<b|c>/review/`") in body


def test_worker_reads_blockout_md_sections_from_a_shipped_reference_with_the_summary_first():
    _, body = front(WORKER)
    assert "docs/" not in body and "`R/part-graph.md` mục `blockout.md`" in body
    pg = (AGENT / "references/part-graph.md").read_text(encoding="utf-8").split("## `blockout.md`", 1)[1]
    items = re.findall(r"^(\d+)\. (.+)$", pg.split("\n## ", 1)[0], re.M)
    assert [int(n) for n, _ in items] == list(range(1, 11))
    assert "Dòng đầu: `# Blockout <id> v<N>`" in pg
    assert items[2][1].startswith("Version, hash của `part_graph.json` + `parts_lib.py`")


def test_every_blender_command_uses_the_brief_blender_path_not_a_bare_blender():
    _, body = front(WORKER)
    assert "`BLENDER` = dòng `BLENDER:` của brief" in body
    assert re.findall(r"(?<![A-Z_])blender -b", body) == [] and body.count("BLENDER -b") == 3


def test_dispatch_prompt_asks_for_the_lines_the_brief_names():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Ghi báo cáo đầy đủ vào `<report>`. Chỉ trả về các dòng brief yêu cầu." in text


def test_worker_points_only_at_files_that_exist():
    _, body = front(WORKER)
    for ref in re.findall(r"`references/([\w.-]+)`", body):
        assert (AGENT / "references" / ref).is_file(), ref
    for tool in set(re.findall(r"T/((?:self_build/)?[\w.]+\.(?:py|sh))", body)):
        assert (AGENT / "tools" / tool).is_file(), tool


def test_reviewer_writes_acceptance_a_fix_can_reach_not_an_overlay_percentage():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "Không dùng % red/blue hay IoU của overlay làm ngưỡng" in text


def test_reviewer_checks_aligned_edges_and_parts_across_a_seam_which_the_pilot_reviewers_missed():
    text = (AGENT.parent / "zps-3dp-check-blockout.md").read_text(encoding="utf-8")
    assert "chi tiết vắt qua khe ghép (khóa, đai, bản lề)" in text
    assert "bậc lồi hay lệch mép không có trên concept là fail" in text
