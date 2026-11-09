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


def test_worker_points_only_at_files_that_exist():
    _, body = front(WORKER)
    for ref in re.findall(r"`references/([\w.-]+)`", body):
        assert (AGENT / "references" / ref).is_file(), ref
    for tool in set(re.findall(r"T/((?:self_build/)?[\w.]+\.(?:py|sh))", body)):
        assert (AGENT / "tools" / tool).is_file(), tool
