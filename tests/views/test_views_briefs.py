"""Views briefs built in-process on the pilot project: what each role may read and do (D22.6, D25)."""
import sys
from pathlib import Path

import pytest

from shared import SCRIPTS, pilot_project, run

sys.path.insert(0, str(SCRIPTS))
from core import briefs, findings, hashes, intake  # noqa: E402
from core.state import load_cfg, load_st, step_of  # noqa: E402

AID = "pilot-house"
SKILL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer"
EVIDENCE = Path(f"production/assets/{AID}/views_front/v1/review/evidence-1")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pilot_project(tmp_path)
    run(tmp_path, "intake", AID)
    run(tmp_path, "ready", AID)
    cfg, st = load_cfg(), load_st(AID)
    from check_profile import PRESETS
    prof = intake.load_profile()

    def at(stage):
        st["stage"] = stage
        return cfg, st, step_of(cfg, stage)[1], PRESETS / f"{prof['preset']}.yaml", hashes.digest(prof)
    return at


def save_top_fix(step, kind, **extra):
    findings.save(AID, step, {"version": 1, "base": None, "pick": None, "next_id": 2, "findings": extra,
                              "top_fix": {"kind": kind, "ids": ["F1"]}})


def test_a_human_redo_on_a_set_whose_top_fix_is_regen_front_gets_no_instruction_the_set_worker_cannot_act_on(ctx):
    cfg, st, step, preset, ph = ctx("views_rest")
    save_top_fix("views_rest", "regen_front", F1={
        "priority": "major", "kind": "regen_front", "status": "open", "first_v": 1, "last_v": 1,
        "region": "front: gỗ đỏ", "acceptance": "front.png: gỗ cùng tông concept"})
    findings.add_human(AID, step, 1, "mái cao hơn")
    st |= {"fix_base": 1, "fix_round": 1}
    text = briefs.worker_brief(cfg, st, step, 2, True, ph, None, preset, {})
    assert "TOP_FIX" not in text and "regen_front" not in text
    assert ("Ưu tiên 1, feedback của người dùng: sửa `H1` (nguyên văn trong `acceptance` của "
            f"`production/assets/{AID}/views_rest/v1/findings.json` và feedback.md). Đối chiếu từng ý với concept; "
            "không bỏ ý nào. Front đã duyệt ở `views_front`, sửa ngoài bước này: không sửa front ở đây.") in text


def test_a_set_review_brief_says_regen_front_takes_exactly_one_id(ctx):
    text = briefs.review_brief(*ctx("views_rest")[:3], 1)
    assert ("- TOP_FIX chỉ khi FIX: loại của finding nặng nhất (cùng mức: regen_front trước); regen_front đúng 1 id; loại khác: mọi finding "
            "blocker/major/minor đang mở của loại đó; need_evidence: mọi finding unclear đang mở. "
            "PASS hoặc ESCALATE: `TOP_FIX: none`.") in text.splitlines()


def test_a_front_review_brief_names_no_single_id_kind_because_views_front_has_none(ctx):
    text = briefs.review_brief(*ctx("views_front")[:3], 1)
    assert ("- TOP_FIX chỉ khi FIX: loại của finding nặng nhất; mọi finding blocker/major/minor đang mở của loại đó; "
            "need_evidence: mọi finding unclear đang mở. PASS hoặc ESCALATE: `TOP_FIX: none`.") in text.splitlines()


def test_a_blockout_review_brief_keeps_structure_as_its_single_id_kind(ctx):
    text = briefs.review_brief(*ctx("blockout")[:3], 1)
    assert "; structure đúng 1 id; loại khác: mọi finding blocker/major/minor đang mở của loại đó;" in text


def test_a_views_evidence_brief_carries_the_tools_dir_but_no_gen_command_so_a_crop_round_cannot_spend_a_codex_call(ctx):
    cfg, st, step, preset, ph = ctx("views_front")
    save_top_fix("views_front", "need_evidence")
    text = briefs.evidence_brief(st, step, 1, EVIDENCE, ph, None, preset).splitlines()
    assert f"TOOLS: {SKILL / 'agents/zps-3dp-step-views/tools'}" in text
    assert [l for l in text if l.startswith(("GEN_IMAGE", "GEN_ARGS"))] == []


def test_a_blockout_evidence_brief_keeps_the_blender_path_because_that_round_renders(ctx):
    cfg, st, step, preset, ph = ctx("blockout")
    save_top_fix("blockout", "need_evidence")
    text = briefs.evidence_brief(st, step, 1, EVIDENCE, ph, {"blender": {"path": "/opt/blender"}}, preset).splitlines()
    assert "BLENDER: /opt/blender" in text
