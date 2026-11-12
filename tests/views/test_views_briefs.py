"""Views briefs built in-process on the pilot project: what each role may read and do (D22.6, D25)."""
import sys
from pathlib import Path

import pytest

from shared import SCRIPTS, pilot_project, run

sys.path.insert(0, str(SCRIPTS))
from core import briefs, findings, hashes, intake  # noqa: E402
from core.state import load_cfg, load_st, step_of  # noqa: E402
from test_hashes import flow  # noqa: E402,F401  (the in-process blockout flow)

AID = "pilot-house"
SKILL = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer"
EVIDENCE = Path(f"production/assets/{AID}/views/v1/review/evidence-1")


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


def test_a_views_review_brief_names_no_single_id_kind_and_no_tie_because_the_views_step_has_none(ctx):
    """D44.3: a wrong front is a `regen` like any view, so every views fix is one batch."""
    text = briefs.review_brief(*ctx("views")[:3], 1)
    assert ("- TOP_FIX chỉ khi FIX: loại của finding nặng nhất; loại lô chỉ ghi loại, script điền mọi finding "
            "blocker/major/minor đang mở của loại đó; need_evidence chỉ ghi loại, script điền mọi finding unclear đang "
            "mở. PASS hoặc ESCALATE: `TOP_FIX: none`.") in text.splitlines()


def test_a_blockout_review_brief_keeps_structure_as_its_single_id_kind(ctx):
    text = briefs.review_brief(*ctx("blockout")[:3], 1)
    assert "; structure 1 id mỗi part, region `<part>: …`; loại lô chỉ ghi loại, script điền mọi finding" in text


def test_a_views_evidence_brief_carries_the_tools_dir_but_no_gen_command_so_a_crop_round_cannot_spend_a_codex_call(ctx):
    cfg, st, step, preset, ph = ctx("views")
    save_top_fix("views", "need_evidence")
    text = briefs.evidence_brief(st, step, 1, EVIDENCE, ph, None, preset).splitlines()
    assert f"TOOLS: {SKILL / 'agents/zps-3dp-step-views/tools'}" in text
    assert [l for l in text if l.startswith(("GEN_IMAGE", "GEN_ARGS"))] == []


def test_a_blockout_evidence_brief_keeps_the_blender_path_because_that_round_renders(ctx):
    cfg, st, step, preset, ph = ctx("blockout")
    save_top_fix("blockout", "need_evidence")
    text = briefs.evidence_brief(st, step, 1, EVIDENCE, ph, {"blender": {"path": "/opt/blender"}}, preset).splitlines()
    assert "BLENDER: /opt/blender" in text


def gen_args(cfg, st, step, preset):
    return [l for l in briefs.tools_line(st, step, None, preset, cfg=cfg) if l.startswith("GEN_ARGS")][0]


def test_the_gen_timeout_per_call_comes_from_pipeline_toml_and_a_project_without_the_section_gets_900_s(ctx):
    """D30.20: one Codex image takes minutes; the brief gives the per-call timeout so a slow call is not cut short."""
    cfg, st, step, preset, _ = ctx("views")
    assert cfg["codex"] == {"timeout_s": 900}
    assert gen_args(cfg | {"codex": {"timeout_s": 600}}, st, step, preset).endswith(" --timeout 600")
    assert gen_args({k: v for k, v in cfg.items() if k != "codex"}, st, step, preset).endswith(" --timeout 900")


def test_a_gen_timeout_under_5_minutes_stops_the_brief_because_a_cut_off_call_still_spends_codex_usage(ctx):
    from core.state import ProducerError
    cfg, st, step, preset, _ = ctx("views")
    with pytest.raises(ProducerError, match=r"^pipeline.toml \[codex\] timeout_s = 299: cần số nguyên ≥ 300 giây \(D30.20\)$"):
        gen_args(cfg | {"codex": {"timeout_s": 299}}, st, step, preset)


def test_the_brief_never_hands_the_worker_a_flag_that_approves_for_the_user_d30_21(ctx):
    """GEN_ARGS goes into every gen the worker runs; --approve-for-me there would lift the approval of all of them."""
    for stage in ("views", "texture"):
        cfg, st, step, preset, _ = ctx(stage)
        assert [f for f in ("--approve-for-me", "--full-auto", "--dangerously-bypass-approvals-and-sandbox")
                if f in gen_args(cfg, st, step, preset)] == [], stage


def test_batching_is_off_in_a_new_project_and_on_only_for_the_step_that_sets_codex_batch_d30_22(ctx):
    """One call for several images may mix the references of the views; it stays off until V6 shows the repaint
    findings are no worse, and then only for the texture paint views."""
    cfg, st, step, preset, _ = ctx("texture")
    assert step["codex_batch"] is False and not gen_args(cfg, st, step, preset).endswith("--batch")
    assert gen_args(cfg, st, step | {"codex_batch": True}, preset).endswith(" --timeout 900 --batch")
    assert [s["id"] for s in cfg["steps"] if "codex_batch" in s] == ["texture"]


def gen_lines(cfg, st, step, preset):
    return [l for l in briefs.tools_line(st, step, None, preset, cfg=cfg) if l.startswith("GEN_")]


@pytest.mark.parametrize("edition", [{}, {"image_gen": "codex_exec"}])
def test_the_claude_edition_brief_keeps_the_nested_codex_call_with_model_reasoning_pid_file_and_timeout(ctx, monkeypatch,
                                                                                                         edition):
    monkeypatch.setattr(briefs, "EDITION", edition)
    cfg, st, step, preset, _ = ctx("views")
    assert gen_lines(cfg, st, step, preset) == [
        f"GEN_IMAGE: {SKILL / 'scripts/gen_image_codex.py'}",
        f"GEN_ARGS: --model gpt-6-astra --reasoning medium --pid-file production/pids/codex_image/{AID}.pid --timeout 900"]


@pytest.mark.parametrize("stage", ["views", "texture"])
def test_the_codex_edition_brief_makes_the_worker_draw_with_its_own_image_tool_and_the_script_only_check(ctx, monkeypatch,
                                                                                                        stage):
    """A sub-agent of a Codex session has the image tool itself; a nested `codex exec` would start a second session."""
    monkeypatch.setattr(briefs, "EDITION", {"image_gen": "direct"})
    cfg, st, step, preset, _ = ctx(stage)
    lines = gen_lines(cfg, st, step | {"codex_batch": True}, preset)
    assert lines[:2] == [f"GEN_IMAGE: {SKILL / 'scripts/gen_image_codex.py'}", "GEN_ARGS: --direct"]
    assert len(lines) == 3 and lines[2].startswith("GEN_MODE: lệnh GEN_IMAGE không vẽ, chỉ kiểm ảnh.")
    for part in ("`image_gen`", "`referenced_image_paths`", "\"Output: <W>x<H> pixels, <landscape|portrait|square>.\"",
                 "chạy lệnh chỉ với cặp đó", "Thoát 3:", "Thoát 1:", "--tool-error"):
        assert part in lines[2], part
    assert "view_image" not in lines[2]


def test_a_codex_edition_views_worker_is_spawned_on_the_preset_image_model_and_the_ledger_names_it(flow, monkeypatch):
    """The owner rule: the agent that makes images runs on Astra. Reviewers and other steps keep the session model."""
    from test_hashes import approve_blockout
    monkeypatch.setattr(briefs, "EDITION", {"image_gen": "direct"})
    approve_blockout(flow)
    assert {(d["role"], d["model"]) for d in flow.st["dispatches"]} == {("worker", "opus"), ("reviewer", "opus")}
    out = flow.brief()
    assert (out["role"], out["model"], out["reasoning_effort"]) == ("worker", "gpt-6-astra", "medium")
    assert flow.st["dispatches"][-1]["model"] == "gpt-6-astra"
    led = (flow.root / "production/ledger.md").read_text(encoding="utf-8").splitlines()
    assert " · house-a · views v1 · giao worker (zps-3dp-step-views, gpt-6-astra) · hạn chót " in led[-1]


def test_a_claude_edition_views_worker_keeps_the_step_model(flow):
    from test_hashes import approve_blockout
    approve_blockout(flow)
    out = flow.brief()
    assert (out["model"], "reasoning_effort" in out) == ("opus", False)
