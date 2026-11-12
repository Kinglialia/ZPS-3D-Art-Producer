import json
import re
from argparse import Namespace
from pathlib import Path

import pytest

from shared import SCRIPTS, SUBAGENT_WRITE_BLOCKED, blockout_only, brief_hash, finding, report, write_profile
from core import briefs, findings, intake, loop, policy
from core.state import ProducerError, load_cfg, load_st, save_st

AID = "house-a"
OUTPUTS = ["part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"]
ZERO = {"blocker": 0, "major": 0, "minor": 0, "preference": 0, "unclear": 0}


def counts(**kw):
    return "; ".join(f"{k}={v}" for k, v in (ZERO | kw).items())


class Flow:
    def __init__(self, root, cap):
        self.root, self.cap = root, cap

    def v(self, n, step="blockout"):
        return self.root / f"production/assets/{AID}/{step}/v{n}"

    def call(self, fn, *a):
        fn(*a)
        return self.cap.readouterr().out

    def brief(self):
        return json.loads(self.call(briefs.run, Namespace(id=AID)))

    def text(self, out):
        return (self.root / out["brief"]).read_text(encoding="utf-8")

    def work(self, status="DONE", out=None, extra="", checks=None, fixed=""):
        """checks: {name: overall} of result JSON the worker leaves in final/review/checks/. fixed: the FIXED line; a DONE
        that names every open finding gets a `full` review (D31.2)."""
        out = out or self.brief()
        rep = self.root / out["report"]
        if rep.parent.name.startswith("v"):
            for o in OUTPUTS:
                (rep.parent / "final" / o).write_text("x", encoding="utf-8")
            for name, overall in (checks or {}).items():
                write_json(rep.parent / "final/review/checks" / name, {"overall": overall})
        rep.write_text(f"STATUS: {status}\nPROFILE_HASH: {brief_hash(self.text(out))}\n"
                       + (f"FIXED: {fixed}\n" if fixed else "") + extra, encoding="utf-8")
        return self.call(loop.ingest, Namespace(id=AID, agent_id="w1"))

    def review(self, out=None, **kw):
        out = out or self.brief()
        (self.root / out["report"]).write_text(report(**kw), encoding="utf-8")
        return self.call(loop.ingest, Namespace(id=AID, agent_id=None))

    def human(self, action, text="", step=None):
        return loop.human_action(AID, action, text, step)

    @property
    def st(self):
        return load_st(AID)

    def ledger(self):
        return (self.root / "production/ledger.md").read_text(encoding="utf-8")


@pytest.fixture
def flow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    blockout_only(tmp_path)
    write_profile(tmp_path)
    intake.new(Namespace(id=AID, title="House A", type="asset", priority=2, deadline=None), load_cfg())
    intake.ready(Namespace(ids=[AID]))
    capsys.readouterr()
    return Flow(tmp_path, capsys)


def fix_v1(f, n=2, kind="structure"):
    f.work()
    return f.review(counts=counts(major=n), top_fix=f"{kind}: F1" if kind == "structure" else
                    f"{kind}: " + ", ".join(f"F{i}" for i in range(1, n + 1)),
                    findings=[finding(f"F{i}", "major", kind) for i in range(1, n + 1)])


@pytest.fixture
def held(monkeypatch):
    """The Producer has not dispatched yet (no free slot, preflight off), so the asset waits in review or fix."""
    monkeypatch.setattr(loop, "dispatch_next", lambda cfg, st: None)


def pick(st):
    return {k: st.get(k) for k in ("state", "fix_round", "fix_base", "offer", "label", "note")}


@pytest.mark.parametrize("args, expected", [
    (("ESCALATE", None, False, 0, 3, False, 0), ("ask_human", "reviewer ESCALATE")),
    (("PASS", None, False, 2, 3, False, 0), ("await_approval", None)),
    (("PASS", None, True, 2, 3, False, 0), ("approve", None)),
    (("FIX", "need_evidence", False, 1, 3, False, 0), ("need_evidence", None)),
    (("FIX", "need_evidence", False, 3, 3, False, 1), ("ask_human", "xin bằng chứng lần 2")),
    (("FIX", "structure", False, 0, 3, False, 0), ("fix", None)),
    (("FIX", "structure", False, 1, 3, False, 0), ("fix", None)),
    (("FIX", "param", False, 2, 3, False, 0), ("ask_human", "không tiến bộ ở vòng 2")),
    (("FIX", "param", False, 2, 3, True, 0), ("fix", None)),
    (("FIX", "structure", False, 3, 3, True, 0), ("ask_human", "hết 3 vòng sửa")),
    (("FIX", "regen_front", False, 1, 3, False, 0, 0), ("reopen", None)),
    (("FIX", "regen_front", False, 3, 3, False, 0, 0), ("reopen", None)),
    (("FIX", "regen_front", False, 0, 3, False, 0, 1), ("ask_human", "regen_front lần 2")),
    (("FIX", "fix_uv_mesh", False, 2, 3, False, 0, 0), ("reopen", None)),
    (("FIX", "fix_uv_mesh", False, 0, 3, False, 0, 1), ("ask_human", "fix_uv_mesh lần 2")),
])
def test_review_outcome_table_encodes_round_cap_early_stop_escalate_one_evidence_round_and_one_reopen(args, expected):
    assert loop.review_event(*args) == expected


def test_three_fix_rounds_then_still_fix_sends_the_best_version_to_the_human_labelled_not_passed(flow):
    head, line = fix_v1(flow, 4).splitlines()
    assert head == "house-a: review FIX (major=4) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert (json.loads(line)["brief"], json.loads(line)["resume"]) == (
        f"production/assets/{AID}/blockout/v2/brief-worker.md", "w1")
    assert pick(flow.st) | {"note": None} == {"state": "running", "fix_round": 1, "fix_base": 1, "offer": None,
                                              "label": None, "note": None}
    flow.work()
    flow.review(counts=counts(major=3), top_fix="structure: F2", compare="F1=better",
                prior=["- F1: resolved | evidence: clay_front", "- F2: open", "- F3: open", "- F4: open"])
    assert (flow.st["fix_round"], flow.st["fix_base"]) == (2, 2)
    flow.work()
    flow.review(counts=counts(major=2), top_fix="structure: F3", compare="F2=better",
                prior=["- F2: resolved | evidence: clay_front", "- F3: open", "- F4: open"])
    out = flow.brief()
    assert "Đây là vòng sửa 3." in flow.text(out)
    flow.work(out=out)
    assert flow.review(counts=counts(major=2), top_fix="structure: F3", compare="F3=worse",
                       prior=["- F3: regressed", "- F4: open"]) == (
        "house-a: review FIX (major=2) → blockout/waiting_human. Tiếp: chờ người dùng: hết 3 vòng sửa; "
        "còn mở: F3, F4 (review page)\n")
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 3, "fix_base": 3, "offer": 3, "label": "chưa đạt",
                             "note": "hết 3 vòng sửa; còn mở: F3, F4"}
    assert flow.st["versions"] == {"blockout": 4}
    assert "house-a · blockout v4 · review FIX (major=2) · massing=fail · hết 3 vòng sửa" in flow.ledger()


def test_round_1_without_progress_continues_but_round_2_without_progress_stops_and_fix_starts_from_the_best(flow):
    fix_v1(flow, 2)
    flow.work()
    flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same", prior=["- F1: open", "- F2: open"])
    assert pick(flow.st)["state"] == "running"
    # D30.2: v2 ties v1 on every count, so the newer v2 is the best and the base of round 2.
    assert flow.st["fix_base"] == 2
    out = flow.brief()
    assert f"Bản gốc: `production/assets/{AID}/blockout/v2/`" in flow.text(out)
    flow.work(out=out)
    rb = flow.text(flow.brief())
    assert ("COMPARE: F1=?\n" in rb, f"Bản gốc v2: ảnh cùng góc `production/assets/{AID}/blockout/v2/final/`" in rb) == (
        True, True)
    assert flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same",
                       prior=["- F1: open", "- F2: open"]).endswith(
        "chờ người dùng: không tiến bộ ở vòng 2; còn mở: F1, F2 (review page)\n")
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 2, "fix_base": 2, "offer": 3, "label": "chưa đạt",
                             "note": "không tiến bộ ở vòng 2; còn mở: F1, F2"}


def write_json(p: Path, d: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def test_fix_brief_lists_only_the_failing_gate_and_check_json_of_the_base_so_the_worker_reads_script_errors_first(flow):
    fix_v1(flow, 1)
    rv = flow.v(1) / "final/review"
    write_json(rv / "gates/roof.json", {"overall": "fail"})
    write_json(rv / "gates/base.json", {"overall": "pass"})
    write_json(rv / "checks/check_layout.json", {"overall": "error"})
    write_json(rv / "checks/check_markers.json", {"pass": False})
    write_json(rv / "checks/check_support.json", {"overall": "not_checked"})
    write_json(rv / "renders/renders.json", {"overall": "fail"})
    write_json(flow.v(1) / "work/check_schema.json", {"overall": "fail"})
    text = flow.text(flow.brief())
    base = f"production/assets/{AID}/blockout/v1/final/review"
    assert (f"Đọc trước nguyên văn lỗi script của bản gốc: `{base}/checks/check_layout.json`, "
            f"`{base}/checks/check_markers.json`, `{base}/gates/roof.json`.") in text
    tools = SCRIPTS.parent / "agents/zps-3dp-step-blockout/tools"
    assert f"TOOLS: {tools}" in text.splitlines()
    assert "handoff" not in text


def test_escalate_goes_to_the_human_at_once_without_another_round(flow):
    flow.work()
    flow.review(verdict="ESCALATE", top_fix=None, findings=[finding("F1", "major", "param")])
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 0, "fix_base": None, "offer": 1,
                             "label": "chưa đạt", "note": "reviewer ESCALATE; còn mở: F1"}


def test_each_offer_has_its_own_key_so_a_board_click_names_the_offer_it_answers(flow):
    flow.work()
    flow.review(verdict="ESCALATE", top_fix=None, findings=[finding("F1", "major", "param")])
    assert flow.st["offer_key"] == "house-a-blockout-v1-1"
    flow.human("redo", "mái cao hơn")
    assert flow.st["offer_key"] is None
    flow.work()
    flow.review(verdict="ESCALATE", top_fix=None, findings=[], counts=counts(major=2), prior=["- F1: open", "- H1: open"],
                compare="H1=same")
    # D30.2: v2 ties v1 (F1 and H1 open on both), so the newer v2 is offered.
    assert (flow.st["offer"], flow.st["offer_key"]) == (2, "house-a-blockout-v2-2")


def test_two_assets_offered_the_same_step_and_version_never_share_an_offer_key_so_one_approval_cannot_block_the_other(flow):
    intake.new(Namespace(id="house-b", title="House B", type="asset", priority=2, deadline=None), load_cfg())
    intake.ready(Namespace(ids=["house-b"]))
    a, b = flow.st, load_st("house-b")
    loop.offer(a, "blockout", 2)
    loop.offer(b, "blockout", 2)
    assert (a["offer_key"], b["offer_key"]) == ("house-a-blockout-v2-1", "house-b-blockout-v2-1")


def need_evidence_v1(f):
    f.work()
    return f.review(counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F1",
                    findings=[finding("F1", "unclear", "param")])


def test_need_evidence_renders_into_the_version_review_folder_and_the_reviewer_rejudges_the_same_version(flow):
    assert need_evidence_v1(flow).endswith("→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`\n")
    st = flow.st
    st["fix_round"] = 3
    save_st(st)
    out = flow.brief()
    ev = f"production/assets/{AID}/blockout/v1/review/evidence-1"
    assert (out["role"], out["resume"], out["brief"], out["report"]) == (
        "worker", "w1", f"{ev}/brief-worker.md", f"{ev}/worker-out.md")
    assert "Không sửa `production/assets/house-a/blockout/v1/final/`" in flow.text(out)
    head, line = flow.work(out=out).splitlines()
    assert (head, json.loads(line)["brief"]) == ("house-a: evidence-1 DONE → blockout/review. Tiếp: giao reviewer → "
                                                 "`brief house-a`", f"production/assets/{AID}/blockout/v1/brief-review.md")
    rb = flow.brief()
    assert f"- Chấm lại v1 với ảnh thêm `{ev}/`" in flow.text(rb)
    assert "- F1: ? | evidence: ? |" in flow.text(rb)
    flow.review(out=rb, verdict="PASS", top_fix=None, counts=counts(), rubric="props=pass",
                prior=["- F1: resolved | evidence: clay_front"])
    assert pick(flow.st) | {"evidence": flow.st["evidence"], "evidence_used": flow.st["evidence_used"]} == {
        "state": "waiting_human", "fix_round": 3, "fix_base": None, "offer": 1, "label": "", "note": "duyệt blockout v1",
        "evidence": None, "evidence_used": 1}
    assert flow.st["versions"] == {"blockout": 1}


def test_evidence_round_that_changes_final_is_discarded_because_the_reviewer_judged_the_old_final(flow):
    need_evidence_v1(flow)
    out = flow.brief()
    (flow.v(1) / "final/blockout.md").write_text("edited", encoding="utf-8")
    flow.work(out=out)
    assert pick(flow.st) | {"evidence": flow.st["evidence"]} == {
        "state": "blocked", "fix_round": 0, "fix_base": None, "offer": None, "label": None,
        "note": "evidence-1: final/ đổi trong vòng bằng chứng, bỏ kết quả", "evidence": None}
    assert flow.call(loop.retry, Namespace(id=AID)).startswith("house-a: → running.")


def test_second_need_evidence_in_one_feedback_round_goes_to_the_human_and_redo_resets_the_counter(flow):
    need_evidence_v1(flow)
    flow.work()
    flow.review(counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F1", prior=["- F1: open"])
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 0, "fix_base": None, "offer": 1,
                             "label": "chưa đạt", "note": "xin bằng chứng lần 2; còn mở: F1"}
    assert flow.human("redo", "chụp gần cửa") == "house-a: làm lại blockout từ v1. Tiếp: giao worker → `brief house-a`"
    assert (flow.st["evidence_used"], flow.st["fix_round"], flow.st["fix_base"]) == (0, 1, 1)


def test_redo_opens_a_new_feedback_round_from_the_best_version_and_carries_its_open_findings(flow):
    stall(flow)
    assert flow.st["state"] == "waiting_human"
    flow.human("redo", "mái cao hơn")
    st = flow.st
    assert {k: st[k] for k in ("state", "fix_round", "fix_base", "round_versions", "offer", "label")} == {
        "state": "fix", "fix_round": 1, "fix_base": 1, "round_versions": [1], "offer": None, "label": ""}
    out = flow.brief()
    assert out["report"] == f"production/assets/{AID}/blockout/v4/worker-out.md"
    assert f"Bản gốc: `production/assets/{AID}/blockout/v1/`" in flow.text(out)
    flow.work(out=out)
    rb = flow.text(flow.brief())
    assert [l for l in rb.splitlines() if l.startswith("- F") and ": ? |" in l] == [
        "- F1: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front",
        "- F2: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front"]


def stall(f):
    """Two rounds without progress whose versions regress F2, so v1 stays the best version (D30.2) and is offered."""
    fix_v1(f, 2)
    for _ in range(2):
        f.work()
        f.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same", prior=["- F1: open", "- F2: regressed"])


def pass_v2(f):
    fix_v1(f, 1)
    f.work(fixed="F1")
    return f.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="F1=better",
                    prior=["- F1: resolved | evidence: clay_front"])


def test_human_approve_rejects_the_other_versions_moves_no_folder_and_parks_before_a_disabled_step(flow):
    assert pass_v2(flow).endswith("→ blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")
    assert flow.human("approve", "ok") == "house-a: đã duyệt blockout v2 → blockout/done_enabled. Tiếp: xong các bước đang bật"
    st = flow.st
    assert {k: st[k] for k in ("stage", "state", "approved", "rejected", "note")} == {
        "stage": "blockout", "state": "done_enabled", "approved": {"blockout": 2}, "rejected": {"blockout": [1]},
        "note": "bước views_front chưa bật"}
    assert flow.v(1).is_dir() and not (flow.root / "deliver").exists()
    assert "house-a · blockout v2 · duyệt bởi người dùng" in flow.ledger()
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert str(e.value) == "house-a: state=done_enabled, không có việc để giao (xong các bước đang bật)"


def test_a_gd1_asset_parked_at_done_enabled_moves_on_with_retry_once_its_next_step_is_enabled(flow):
    pass_v2(flow)
    flow.human("approve", "ok")
    assert flow.call(loop.retry, Namespace(id=AID)) == "house-a: → done_enabled. Tiếp: xong các bước đang bật\n"
    assert flow.st["note"] == "bước views_front chưa bật"
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views_front"\nenabled = false\n', 'id = "views_front"\n'),
                 encoding="utf-8")
    from core import limits
    assert "[house-a] blockout/done_enabled → bước views_front đã bật → `retry house-a`\n" in flow.call(
        limits.show_next, Namespace(session=False))
    head, line = flow.call(loop.retry, Namespace(id=AID)).splitlines()
    assert head == "house-a: → todo. Tiếp: giao worker → `brief house-a`"
    assert json.loads(line)["brief"] == f"production/assets/{AID}/views_front/v1/brief-worker.md"
    assert {k: flow.st[k] for k in ("stage", "state", "approved")} == {"stage": "views_front", "state": "running",
                                                                     "approved": {"blockout": 2}}


def test_approving_the_offered_best_version_rejects_the_newer_versions(flow):
    stall(flow)
    flow.human("approve")
    assert (flow.st["approved"], flow.st["rejected"]) == ({"blockout": 1}, {"blockout": [2, 3]})


def test_brief_never_dispatches_a_disabled_step(flow):
    st = flow.st
    st["stage"] = "views_front"
    save_st(st)
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert str(e.value) == "house-a: bước views_front chưa bật (enabled = false), không giao"


def test_approving_the_last_step_ends_at_done_without_the_old_final_human_gate(flow):
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").split("[[steps]]\nid = \"views_front\"")[0], encoding="utf-8")
    pass_v2(flow)
    flow.human("approve")
    assert (flow.st["state"], "final_pending" in flow.st) == ("done", False)


def test_policy_reviewer_approves_a_pass_itself_and_the_ledger_names_the_policy(flow):
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    pass_v2(flow)
    assert (flow.st["state"], flow.st["approved"]) == ("done_enabled", {"blockout": 2})
    assert "house-a · blockout v2 · duyệt bởi reviewer theo chính sách dự án" in flow.ledger()


def test_delegation_overrides_a_human_policy(flow):
    policy.delegate(Namespace(step="blockout", ids=[AID], by="", confirm_spend=False))
    flow.cap.readouterr()
    pass_v2(flow)
    assert flow.st["state"] == "done_enabled"
    assert "house-a · blockout v2 · duyệt bởi reviewer theo ủy quyền" in flow.ledger()


def test_one_approve_or_needs_fix_per_version_and_notes_are_kept_every_time(flow):
    pass_v2(flow)
    flow.human("approve")
    again = flow.human("approve", "duyệt lần nữa")
    assert re.fullmatch(r"house-a: bỏ qua approve blockout v2: đã có quyết định lúc \d{4}-\d\d-\d\d \d\d:\d\d", again)
    assert flow.st["state"] == "done_enabled"
    flow.human("note", "ghi chú 1")
    flow.human("note", "ghi chú 2")
    log = (flow.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")
    assert (log.count("· note · ghi chú"), log.count("· approve ·"), "duyệt lần nữa" in log) == (2, 1, False)


def test_needs_fix_after_approval_sends_the_approved_version_back_and_opens_a_new_version(flow):
    pass_v2(flow)
    flow.human("approve")
    assert flow.human("redo", "mái thấp quá", "blockout") == (
        "house-a: làm lại blockout từ v2. Tiếp: giao worker → `brief house-a`")
    st = flow.st
    assert {k: st[k] for k in ("stage", "state", "fix_round", "fix_base", "approved", "rejected", "approved_hash")} == {
        "stage": "blockout", "state": "fix", "fix_round": 1, "fix_base": 2, "approved": {}, "rejected": {},
        "approved_hash": {}}
    assert flow.brief()["report"] == f"production/assets/{AID}/blockout/v3/worker-out.md"


def test_a_second_needs_fix_click_on_the_same_waiting_version_is_ignored(flow):
    pass_v2(flow)
    flow.human("redo", "mái thấp quá")
    assert flow.human("redo", "bấm lần nữa").startswith("house-a: bỏ qua redo blockout v2: đã có quyết định lúc ")
    assert flow.human("approve").startswith("house-a: bỏ qua approve blockout v2: đã có quyết định lúc ")
    assert (flow.st["state"], flow.st["fix_round"]) == ("fix", 1)


PICKED = dict(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="F1=better",
              prior=["- F1: resolved | evidence: clay_front"])


def test_a_picked_variant_missing_a_required_output_blocks_the_review_and_copies_nothing(flow):
    """Copied as is, the incomplete variant reached waiting_human and the approval then died on the missing lock file."""
    fix_v1(flow, 1, "param")
    flow.work(fixed="F1")
    b = flow.v(2) / "variants/b"
    b.mkdir(parents=True)
    (b / "blockout.md").write_text("b", encoding="utf-8")
    flow.review(pick="b", **PICKED)
    assert (pick(flow.st)["state"], pick(flow.st)["note"]) == ("blocked", (
        f"PICK b: production/assets/{AID}/blockout/v2/variants/b/ thiếu output bắt buộc: "
        "part_graph.json, parts_lib.py, assembled.glb, sources.json"))
    assert {p.name: p.read_text(encoding="utf-8") for p in (flow.v(2) / "final").iterdir()} == {o: "x" for o in OUTPUTS}
    assert not (flow.v(2) / "variants/a").exists() and not (flow.v(2) / "findings.json").exists()
    flow.call(loop.retry, Namespace(id=AID))
    assert (flow.st["state"], flow.st["versions"]["blockout"]) == ("running", 2)


def test_pick_copies_the_chosen_variant_into_final_before_ingest_and_keeps_variant_a(flow):
    fix_v1(flow, 1, "param")
    flow.work(fixed="F1")
    b = flow.v(2) / "variants/b"
    b.mkdir(parents=True)
    for o in OUTPUTS:
        (b / o).write_text("b", encoding="utf-8")
    out = flow.brief()
    with pytest.raises(ProducerError) as e:
        flow.review(out=out, pick="c", **PICKED)
    assert str(e.value) == f"PICK c: không có production/assets/{AID}/blockout/v2/variants/c/"
    assert flow.st["state"] == "reviewing"
    flow.review(out=out, pick="b", **PICKED)
    final = flow.v(2) / "final"
    assert {p.name: p.read_text(encoding="utf-8") for p in final.iterdir()} == {o: "b" for o in OUTPUTS}
    assert (flow.v(2) / "variants/a/part_graph.json").read_text(encoding="utf-8") == "x"
    assert flow.st["state"] == "waiting_human"


def test_assemble_approval_copies_final_to_deliver_and_a_later_redo_marks_the_delivered_readme(flow):
    st = flow.st
    st |= {"stage": "assemble", "state": "waiting_human", "versions": {"blockout": 1, "assemble": 1},
           "approved": {"blockout": 1}, "offer": 1}
    save_st(st)
    (flow.v(1, "assemble") / "final").mkdir(parents=True)
    (flow.v(1, "assemble") / "final/README.md").write_text("Trạng thái: chờ DUYỆT 2\n# House A\n", encoding="utf-8")
    flow.human("approve")
    readme = flow.root / "deliver/house-a/README.md"
    head, body = readme.read_text(encoding="utf-8").split("\n", 1)
    assert (flow.st["state"], body) == ("done", "# House A\n")
    assert re.fullmatch(r"Trạng thái: đã duyệt DUYỆT 2 bởi người dùng · \d{4}-\d\d-\d\d \d\d:\d\d", head)
    assert (flow.v(1, "assemble") / "final/README.md").read_text(encoding="utf-8") == "Trạng thái: chờ DUYỆT 2\n# House A\n"
    flow.human("redo", "mái thấp", "blockout")
    assert readme.read_text(encoding="utf-8") == f"**đang làm lại**\n\n{head}\n# House A\n"
    assert (flow.st["stage"], flow.st["state"], flow.st["approved"]) == ("blockout", "fix", {})


H1 = {"priority": "major", "kind": "structure", "status": "open", "first_v": 1, "last_v": 1,
      "region": "theo feedback người dùng", "viewing_condition": "review page", "evidence": "feedback.md: blockout v1",
      "consequence": "người dùng chưa duyệt", "confidence": "high", "repair": "mái cao hơn",
      "preserve": "những gì feedback không nhắc", "acceptance": "đạt yêu cầu của người dùng: mái cao hơn"}


def test_redo_of_an_unreviewed_version_files_the_user_text_as_H1_so_the_next_review_has_a_base(flow, held):
    flow.work()
    assert flow.st["state"] == "review"
    assert flow.human("redo", "mái cao hơn") == "house-a: làm lại blockout từ v1. Tiếp: giao worker → `brief house-a`"
    assert findings.load(AID, "blockout", 1)["findings"] == {"H1": H1}
    assert (flow.st["fix_base"], flow.st["round_versions"]) == (1, [1])
    flow.work()
    rb = flow.text(flow.brief())
    assert "- H1: ? | evidence: ? | acceptance: đạt yêu cầu của người dùng: mái cao hơn" in rb
    assert "REVIEW_SCOPE: fix" in rb.splitlines()  # the worker did not name H1 in FIXED
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="mass=pass", compare="H1=better",
                prior=["- H1: resolved | evidence: clay_front"])
    assert pick(flow.st)["state"] == "review"  # D31.2: a PASS at a fix round is judged once more in full
    flow.review(out=flow.brief(), verdict="PASS", top_fix=None, counts=counts(), rubric="mass=pass")
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 1, "fix_base": 1, "offer": 2, "label": "",
                             "note": "duyệt blockout v2"}


def test_best_version_skips_a_version_without_findings_so_a_round_never_crashes():
    assert findings.best_version([None, {"version": 2, "findings": {}}]) == 2


def test_send_back_is_a_major_finding_and_a_reoffer_of_the_same_version_takes_a_new_decision(flow):
    pass_v2(flow)
    flow.human("approve")
    flow.human("redo", "mái thấp quá")
    assert findings.open_of(findings.load(AID, "blockout", 2)) == {
        "H1": H1 | {"first_v": 2, "last_v": 2, "evidence": "feedback.md: blockout v2", "repair": "mái thấp quá",
                    "acceptance": "đạt yêu cầu của người dùng: mái thấp quá"}}
    for _ in range(2):
        flow.work()
        flow.review(counts=counts(major=1), top_fix="structure: H1", rubric="mass=fail", compare="H1=worse",
                    prior=["- H1: regressed"])
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 2, "fix_base": 2, "offer": 2, "label": "chưa đạt",
                             "note": "không tiến bộ ở vòng 2; còn mở: H1"}
    assert flow.human("approve", "giữ v2") == (
        "house-a: đã duyệt blockout v2 → blockout/done_enabled. Tiếp: xong các bước đang bật")


def test_redo_of_a_later_step_is_refused_so_the_asset_never_skips_a_step(flow):
    with pytest.raises(ProducerError) as e:
        flow.human("redo", "x", "views_rest")
    assert str(e.value) == "house-a: không làm lại views_rest được: asset đang ở bước blockout"
    assert (flow.st["stage"], flow.st["state"]) == ("blockout", "todo")
    assert "· redo ·" not in (flow.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")


def test_feedback_is_tagged_with_the_version_the_user_sees_not_the_newest(flow):
    stall(flow)
    assert (flow.st["offer"], flow.st["versions"]) == (1, {"blockout": 3})
    flow.human("note", "mái chìa thêm")
    log = (flow.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")
    assert log.splitlines()[-1].endswith(" · blockout v1 · note · mái chìa thêm")


def test_retry_sets_the_old_report_aside_so_ingest_waits_for_the_new_one(flow):
    flow.work(status="NEEDS_CONTEXT")
    head, line = flow.call(loop.retry, Namespace(id=AID)).splitlines()
    assert head == "house-a: → running. Tiếp: đang chờ subagent (mất kết nối thì `brief house-a` để giao lại)"
    assert json.loads(line)["report"] == f"production/assets/{AID}/blockout/v1/worker-out.md"
    assert (flow.v(1) / "worker-out-1.md").read_text(encoding="utf-8").startswith("STATUS: NEEDS_CONTEXT")
    with pytest.raises(ProducerError) as e:
        loop.ingest(Namespace(id=AID, agent_id=None))
    assert str(e.value) == f"chưa có báo cáo production/assets/{AID}/blockout/v1/worker-out.md"


def test_a_redispatch_sets_the_old_review_aside_so_the_evidence_rereview_is_not_read_from_the_first(flow):
    need_evidence_v1(flow)
    flow.work()
    flow.brief()
    assert loop.next_action(flow.st) == "đang chờ subagent (mất kết nối thì `brief house-a` để giao lại)"
    assert (flow.v(1) / "review-out-1.md").read_text(encoding="utf-8").startswith("VERDICT: FIX")


def test_worker_brief_names_the_rubric_section_profile_preset_and_blender_path(flow):
    (flow.root / "production/preflight.json").write_text(json.dumps(
        {"features": {"blender": True}, "blender": {"path": "/opt/blender/blender", "version": "4.2"}}), encoding="utf-8")
    text = flow.text(flow.brief())
    assert "BLENDER: /opt/blender/blender" in text.splitlines()
    assert f"2. `production/assets/{AID}/rubric.md` mục `## blockout` — tiêu chí chấm; tự check trước khi báo cáo." in text
    assert (f"4. `production/PROJECT-PROFILE.yaml` — profile dự án; "
            f"`{SCRIPTS.parent / 'presets/topdown-mobile-lowpoly.yaml'}` — preset của profile.") in text
    pid = [l for l in text.splitlines() if l.startswith("- Mỗi lệnh Blender")]
    assert pid == ["- Mỗi lệnh Blender: `<lệnh> & echo $! > production/pids/blender/house-a.pid; wait $!; "
                   "rm -f production/pids/blender/house-a.pid`."]


def test_review_brief_names_the_rubric_section_of_the_step(flow):
    flow.work()
    assert f"- Theo: `production/assets/{AID}/rubric.md` mục `## blockout`, " in flow.text(flow.brief())


def current(f) -> list[str]:
    text = (f.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")
    rows = text.split("## Hiện hành", 1)[1].split("## Log", 1)[0].splitlines()
    return [re.sub(r"^- \d{4}-\d\d-\d\d \d\d:\d\d · ", "- ", r) for r in rows if r.strip() and not r.startswith("<!--")]


def test_a_redo_stays_in_the_current_section_the_worker_reads_until_the_step_is_approved_by_its_reviewer(flow, held):
    """Pilot run: redo text went only to the Log, so the texture worker and reviewers read an empty "Hiện hành"."""
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    fb = flow.root / f"production/assets/{AID}/feedback.md"
    fb.write_text(fb.read_text(encoding="utf-8").replace("## Log", "- giữ mái ngói đỏ (Producer gộp)\n\n## Log"),
                  encoding="utf-8")
    fix_v1(flow, 1)
    flow.human("redo", "mái cao hơn\nmái đỏ")
    flow.human("note", "chỉ là ghi chú")
    assert current(flow) == ["- giữ mái ngói đỏ (Producer gộp)", "- blockout v1 · redo · mái cao hơn mái đỏ"]
    flow.work(fixed="F1, H1")
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="F1=better; H1=better",
                prior=["- F1: resolved | evidence: clay_front", "- H1: resolved | evidence: clay_front"])
    assert (flow.st["approved"], current(flow)) == ({"blockout": 2}, ["- giữ mái ngói đỏ (Producer gộp)"])


def test_a_reviewer_reply_saved_whole_with_its_report_markers_ingests_like_the_bare_report(flow):
    """Pilot run: every reviewer returned its report as text, and the Producer saved the reply as review-out.md."""
    flow.work()
    out = flow.brief()
    body = report(counts=counts(major=1), findings=[finding("F1", "major")])
    (flow.root / out["report"]).write_text(f"Đã chấm v1.\n--- report ---\n{body}--- end ---\n", encoding="utf-8")
    assert flow.call(loop.ingest, Namespace(id=AID, agent_id=None)).startswith(
        "house-a: review FIX (major=1) → blockout/fix.")


def test_the_review_brief_asks_for_a_report_file_with_text_only_as_fallback_and_states_the_label_rule(flow):
    """D27.5: a report saved by the Producer passes through its context, so the reviewer writes the file and replies
    with two lines (D22.6). Pilot run: ingest refused a PRIOR whose evidence named `unlit_close_front (lock crop)` for the
    label `v2 unlit_close_front`."""
    flow.work()
    text = flow.text(flow.brief())
    assert [l for l in text.splitlines() if "review-out" in l or "--- report" in l or "nguyên văn" in l or "Tin nhắn" in l] == [
        f"Ghi report vào `production/assets/{AID}/blockout/v1/review-out.md`. Report mở đầu đúng format, mỗi khóa "
        "một dòng:",
        "- EVIDENCE_OPENED: các nhãn cách nhau bằng dấu phẩy; nhãn không chứa dấu phẩy hay chấm phẩy. `evidence` của "
        "finding mới và của PRIOR resolved chép nguyên văn ít nhất một nhãn đó.",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT. Lệnh ghi file bị chặn: trả cả report giữa "
        "dòng `--- report ---` và dòng `--- end ---`."]
    assert "Bạn chấm độc lập. Không sửa file nào ngoài report." in text.splitlines()
    assert "mức `minor`" not in text


def test_a_reviewer_report_that_fails_the_contract_is_set_aside_so_the_rewrite_has_a_free_path(flow):
    """Run 4: the rejected report stayed at the report path, so `P wait` and `next` read it as a finished report."""
    flow.work()
    out = flow.brief()
    rep = flow.root / out["report"]
    for k in (1, 2):
        with pytest.raises(ProducerError) as e:
            flow.review(out=out, evidence="", rubric=f"massing=fail; try{k}=fail")
        assert str(e.value) == f"production/assets/{AID}/blockout/v1/review-out.md sai contract: thiếu EVIDENCE_OPENED"
        assert not rep.exists()
        assert f"try{k}=fail" in rep.with_name(f"review-out.rejected-{k}.md").read_text(encoding="utf-8")
    assert flow.st["state"] == "reviewing"
    assert loop.next_action(flow.st).startswith("đang chờ subagent")
    flow.review(out=out, top_fix="structure: F1", findings=[finding("F1", "major", "structure")])
    assert sorted(p.name for p in rep.parent.glob("review-out*")) == [
        "review-out.md", "review-out.rejected-1.md", "review-out.rejected-2.md"]


def test_a_worker_report_without_the_profile_hash_is_set_aside_the_same_way(flow):
    out = flow.brief()
    rep = flow.root / out["report"]
    rep.write_text("STATUS: DONE\nOUTPUT: final/\n", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))
    assert str(e.value) == f"production/assets/{AID}/blockout/v1/worker-out.md sai contract: thiếu PROFILE_HASH"
    assert not rep.exists() and rep.with_name("worker-out.rejected-1.md").read_text(encoding="utf-8").startswith("STATUS: DONE")
    assert flow.st["state"] == "running"


def test_a_worker_report_with_another_profile_hash_is_set_aside_with_its_own_message(flow):
    out = flow.brief()
    rep = flow.root / out["report"]
    rep.write_text("STATUS: DONE\nPROFILE_HASH: 000000000000\n", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))
    assert str(e.value).startswith(f"production/assets/{AID}/blockout/v1/worker-out.md: PROFILE_HASH 000000000000 khác brief")
    assert not rep.exists() and rep.with_name("worker-out.rejected-1.md").exists()


def test_the_checks_that_run_after_parsing_also_set_the_report_aside(flow):
    flow.work()
    out = flow.brief()
    rep = flow.root / out["report"]
    with pytest.raises(ProducerError):
        flow.review(out=out, verdict="PASS", top_fix=None, rubric="massing=pass; props=not_checked")
    assert not rep.exists() and rep.with_name("review-out.rejected-1.md").exists()


def test_a_reviewer_that_omits_counts_and_the_batch_ids_is_ingested_and_the_script_fills_both(flow):
    """The script counts and lists the batch ids, so a reviewer is never sent back for what it cannot get wrong."""
    flow.work()
    out = flow.review(top_fix="param", counts=None, findings=[finding("F1", "major", "param"), finding("F2", "minor", "param")])
    assert out.splitlines()[0] == "house-a: review FIX (major=1 minor=1) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    doc = json.loads((flow.v(1) / "findings.json").read_text(encoding="utf-8"))
    assert doc["top_fix"] == {"kind": "param", "ids": ["F1", "F2"]}
    assert "cảnh báo report reviewer" not in flow.ledger()
    assert "Sửa đúng `TOP_FIX: param: F1, F2`" in flow.text(flow.brief())


def test_a_reviewer_that_writes_wrong_counts_and_wrong_batch_ids_is_warned_in_the_ledger_not_rejected(flow):
    flow.work()
    flow.review(top_fix="param: F1", counts=counts(major=3), findings=[
        finding("F1", "major", "param"), finding("F2", "minor", "param")])
    doc = json.loads((flow.v(1) / "findings.json").read_text(encoding="utf-8"))
    assert (flow.st["state"] != "reviewing", doc["top_fix"]) == (True, {"kind": "param", "ids": ["F1", "F2"]})
    assert [l.rsplit(" · ", 1)[1] for l in flow.ledger().splitlines() if "cảnh báo report reviewer" in l] == [
        "COUNTS 'blocker=0; major=3; minor=0; preference=0; unclear=0' khác số script tính (major=1 minor=1): "
        "dùng số của script",
        "TOP_FIX param: ghi F1, script dùng F1, F2"]


def test_a_report_the_producer_saved_from_a_reply_is_ingested_and_logged_as_a_fallback_by_role_d27_5(flow):
    """The fallback must stay rare, so every one is counted: in the ledger and on the dispatch (`P stats`)."""
    flow.work()
    out = flow.brief()
    body = report(counts=counts(major=1), findings=[finding("F1", "major")])
    (flow.root / out["report"]).write_text(f"--- report ---\n{body}--- end ---\n", encoding="utf-8")
    flow.call(loop.ingest, Namespace(id=AID, agent_id=None, fallback=True))
    assert [x.get("fallback", False) for x in flow.st["dispatches"]] == [False, True, False]
    assert [l.split(" · ", 2)[2] for l in flow.ledger().splitlines() if "report_fallback" in l] == [
        "house-a · blockout v1 · report_fallback · reviewer"]


def test_the_old_report_names_are_the_ones_claude_code_refused_so_the_name_rule_can_catch_a_regression_d27_5():
    assert [n for n in ("report-worker.md", "Report-Review.md", "report.md", "summary.md", "findings-v1.md",
                        "worker-out.md", "review-out.md", "judge-out.md") if SUBAGENT_WRITE_BLOCKED.match(n)] == [
        "report-worker.md", "Report-Review.md", "report.md", "summary.md", "findings-v1.md"]


def test_no_brief_tells_a_subagent_to_write_a_file_that_claude_code_refuses_by_name_d27_5(flow):
    """Pilot run: Claude Code refused every worker and reviewer Write because the file was named `report-*.md`, so each
    report came back as text through the Producer's context. Covers the worker, the reviewer, the fix worker and the
    evidence worker. `role: script` is left out: a script writes its own report, and the rule binds only subagents."""
    outs = [flow.brief()]
    flow.work(out=outs[-1])
    outs.append(flow.brief())
    flow.review(out=outs[-1], counts=counts(major=1), top_fix="structure: F1", findings=[finding("F1", "major")])
    outs.append(flow.brief())
    flow.work(out=outs[-1])
    outs.append(flow.brief())
    flow.review(out=outs[-1], counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F2",
                findings=[finding("F2", "unclear", "param")], prior=["- F1: resolved | evidence: clay_front"],
                compare="F1=better")
    outs.append(flow.brief())
    assert [(o["role"], Path(o["report"]).name) for o in outs] == [
        ("worker", "worker-out.md"), ("reviewer", "review-out.md"), ("worker", "worker-out.md"),
        ("reviewer", "review-out.md"), ("worker", "worker-out.md")]
    assert outs[-1]["report"].endswith("/review/evidence-1/worker-out.md")
    assert [o["report"] for o in outs if SUBAGENT_WRITE_BLOCKED.match(Path(o["report"]).name)] == []
    assert [o["report"] for o in outs if f"`{o['report']}`" not in flow.text(o)] == []


def waive(f, fid, why="anh chấp nhận", by="user", step=None):
    return f.call(loop.waive, Namespace(id=AID, fid=fid, why=why, by=by, step=step))


def held_fix(f, monkeypatch, n=1, kind="structure"):
    """FIX on v1 with the dispatch held, so the asset waits in `fix` as before the Producer sends the worker."""
    with monkeypatch.context() as m:
        m.setattr(loop, "dispatch_next", lambda cfg, st: None)
        fix_v1(f, n, kind)
    assert f.st["state"] == "fix"


def test_waiving_the_only_major_during_fix_sends_the_same_version_to_a_reviewer_and_no_worker_d30_1(flow, monkeypatch):
    """Pilot run: F2 of the model cost 4 versions because the user could not accept it as an exception while in FIX."""
    held_fix(flow, monkeypatch)
    head, line = waive(flow, "F1", "mái thấp là chủ ý").splitlines()
    assert head == ("house-a: waive blockout F1 (người dùng): đã đóng; v1 hết lỗi chặn → reviewer chấm lại v1, không gọi "
                    "worker → blockout/review. Tiếp: giao reviewer → `brief house-a`")
    assert json.loads(line) | {"model": None} == {
        "role": "reviewer", "agent": "zps-3dp-check-blockout", "model": None, "resume": None,
        "brief": f"production/assets/{AID}/blockout/v1/brief-review.md",
        "report": f"production/assets/{AID}/blockout/v1/review-out.md"}
    assert (flow.st["state"], flow.st["versions"], flow.st["fix_round"]) == ("reviewing", {"blockout": 1}, 1)
    f1 = findings.load(AID, "blockout", 1)["findings"]["F1"]
    assert (f1["status"], f1["waived"]["by"], f1["waived"]["why"]) == ("waived", "user", "mái thấp là chủ ý")
    assert "house-a · blockout F1 · waive bởi người dùng · mái thấp là chủ ý" in flow.ledger()
    rb = flow.text(json.loads(line))
    assert (f"- Chấm lại toàn bộ v1, không có bản mới; finding đủ trường `production/assets/{AID}/blockout/v1/findings.json`."
            in rb.splitlines(), "COMPARE:" in rb, "PRIOR:" in rb) == (True, False, False)
    assert ("- Đã waive (người dùng chấp nhận là ngoại lệ): F1. Không mở lại, không ghi PRIOR, không ghi lại thành finding "
            "mới.") in rb.splitlines()
    out = flow.review(out=json.loads(line), verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass")
    assert out == "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v1 (review page)\n"
    assert findings.load(AID, "blockout", 1)["findings"]["F1"]["status"] == "waived"


def test_waive_by_producer_is_refused_outside_test_mode_and_changes_nothing_d30_1(flow, monkeypatch):
    """A real project never lets the Producer accept a finding for the user; only test runs may."""
    held_fix(flow, monkeypatch)
    before, ledger = flow.st, flow.ledger()
    with pytest.raises(ProducerError) as e:
        waive(flow, "F1", "thử", by="producer")
    assert str(e.value) == (f"{AID}: --by producer chỉ chạy khi production/policy.yaml có test_mode: true; dự án thật do "
                            "người dùng waive")
    assert (flow.st, flow.ledger(), findings.load(AID, "blockout", 1)["findings"]["F1"]["status"]) == (
        before, ledger, "open")
    policy.set_approval(Namespace(step="test_mode", who="true", by="chạy thử", confirm_spend=False))
    waive(flow, "F1", "chạy thử", by="producer")
    assert findings.load(AID, "blockout", 1)["findings"]["F1"]["waived"]["by"] == "producer"
    assert "house-a · blockout F1 · waive bởi Producer · chạy thử" in flow.ledger()


def test_waiving_one_of_two_keeps_the_fix_round_and_the_next_briefs_skip_the_waived_finding_d30_1(flow, monkeypatch):
    held_fix(flow, monkeypatch, 2, "param")
    head, line = waive(flow, "F2").splitlines()
    assert head == "house-a: waive blockout F2 (người dùng): đã đóng → blockout/fix. Tiếp: giao worker → `brief house-a`"
    wb = flow.text(json.loads(line))
    assert "`TOP_FIX: param: F1`" in wb and "F2" not in wb
    rb = flow.text(json.loads(flow.work(out=json.loads(line)).splitlines()[-1]))
    assert ("COMPARE: F1=?" in rb.splitlines(), "- F2: ?" in rb, "F2" in rb.split("## Báo cáo")[1]) == (True, False, False)


def test_a_waive_while_the_reviewer_judges_applies_at_its_ingest_and_the_last_major_gone_passes_d30_1(flow):
    fix_v1(flow, 1)
    flow.work()
    out = flow.brief()
    assert waive(flow, "F1").startswith(
        "house-a: waive blockout F1 (người dùng): reviewer đang chấm, áp dụng ở lần ingest tới → blockout/reviewing.")
    assert findings.load(AID, "blockout", 1)["findings"]["F1"]["status"] == "open"
    head, line = flow.review(out=out, counts=counts(major=1), top_fix="structure: F1", compare="F1=same",
                             prior=["- F1: open"]).splitlines()
    assert head == ("house-a: review PASS (0 mở) → blockout/review. Tiếp: giao reviewer → `brief house-a`")
    assert flow.text(json.loads(line)).splitlines()[2] == "REVIEW_SCOPE: full"
    assert flow.review(out=json.loads(line), verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass") == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")
    assert [findings.load(AID, "blockout", v)["findings"]["F1"]["status"] for v in (1, 2)] == ["waived", "waived"]
    assert "waive_pending" not in flow.st or flow.st["waive_pending"] == {}


def test_waive_of_an_id_that_is_not_open_is_refused(flow, monkeypatch):
    held_fix(flow, monkeypatch)
    with pytest.raises(ProducerError) as e:
        waive(flow, "F9")
    assert str(e.value) == f"{AID}: blockout không có F9 đang mở"


def test_the_duyet_2_readme_lists_producer_waives_apart_and_user_waives_as_exceptions_d30_1(flow, monkeypatch):
    import assemble
    held_fix(flow, monkeypatch, 2, "param")
    waive(flow, "F1", "mái thấp là chủ ý")
    policy.set_approval(Namespace(step="test_mode", who="true", by="chạy thử", confirm_spend=False))
    waive(flow, "F2", "chạy thử 0.1 m", by="producer")
    st = flow.st | {"approved": {"blockout": 1}}
    assert (assemble.waived(st, "user", "người dùng waive: "), assemble.waived(st, "producer")) == (
        ["- blockout v1 F1 [major] mái: người dùng waive: mái thấp là chủ ý"],
        ["- blockout v1 F2 [major] mái: chạy thử 0.1 m"])


def cli(f, *argv):
    import producer
    producer.main(list(argv))
    return f.cap.readouterr().out


def test_each_state_change_command_ends_with_the_one_dispatch_line_that_brief_prints_d30_5(flow):
    """Pilot run: after a redo or a retry the Producer ran `P brief` in a separate turn; the dispatch now comes with it."""
    pass_v2(flow)
    out = cli(flow, "feedback", AID, "mái thấp quá", "--action", "redo").splitlines()
    assert (len(out), out[0]) == (2, "house-a: làm lại blockout từ v2. Tiếp: giao worker → `brief house-a`")
    assert json.loads(out[-1]) == flow.brief()
    flow.work(status="NEEDS_CONTEXT", out=json.loads(out[-1]))
    out = cli(flow, "retry", AID).splitlines()
    assert len(out) == 2 and json.loads(out[-1]) == flow.brief()
    note = cli(flow, "feedback", AID, "ghi chú thôi").splitlines()
    assert len(note) == 1 and not note[0].startswith("{")


def test_a_feedback_that_changes_no_state_prints_no_dispatch_d30_5(flow):
    flow.work()
    out = cli(flow, "feedback", AID, "mái đẹp", "--action", "approve").splitlines()
    assert out == ["house-a: đã ghi feedback; house-a không chờ duyệt blockout (state=reviewing). Tiếp: đang chờ subagent "
                   "(mất kết nối thì `brief house-a` để giao lại)"]


def test_compare_for_ids_outside_top_fix_is_ignored_with_a_ledger_warning_and_prior_sets_their_status_d30_4(flow):
    """Pilot run, model v2: the reviewer compared F2 and F3 too; ingest refused the whole report and the Producer edited it."""
    flow.work()
    flow.review(counts=counts(major=2, minor=1), top_fix="structure: F1",
                findings=[finding("F1", "major", "structure"), finding("F2", "major", "param"),
                          finding("F3", "minor", "param")])
    flow.work()
    out = flow.review(counts=counts(major=1), top_fix="param: F2", compare="F1=better; F2=same; F3=better",
                      prior=["- F1: resolved | evidence: clay_front", "- F2: open", "- F3: resolved | evidence: clay_front"])
    assert out.splitlines()[0] == "house-a: review FIX (major=1) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    doc = findings.load(AID, "blockout", 2)
    assert {i: f["status"] for i, f in doc["findings"].items()} == {"F1": "resolved", "F2": "open", "F3": "resolved"}
    warn = [l.split(" · ", 2)[2] for l in flow.ledger().splitlines() if "cảnh báo report reviewer" in l]
    assert warn == [f"{AID} · blockout v2 · cảnh báo report reviewer · COMPARE {i}={c} bỏ qua: không có trong TOP_FIX vòng "
                    "trước hay feedback của người dùng" for i, c in (("F2", "same"), ("F3", "better"))]


def test_no_worker_or_reviewer_brief_tells_the_agent_to_write_its_report_through_the_shell_d30_8(flow):
    shell = re.compile(r"heredoc|cat\s*>|\btee\b|<<\s*['\"]?[A-Z]+|python3?\s+-c", re.I)
    texts = [flow.text(flow.brief())]
    flow.work()
    out = flow.brief()
    texts.append(flow.text(out))
    flow.review(out=out, counts=counts(major=1), findings=[finding("F1", "major", "structure")])
    texts.append(flow.text(flow.brief()))
    assert [t.splitlines()[0][:16] for t in texts] == ["# Brief — House ", "# Review brief —", "# Brief — House "]
    assert [l for t in texts for l in t.splitlines() if shell.search(l)] == []



def acceptable(root, *names):
    p = root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('top_fix = ["structure", "param"]\n',
                                                       f'top_fix = ["structure", "param"]\nacceptable = {list(names)!r}\n'.replace(
                                                           "'", '"'), 1), encoding="utf-8")


def test_a_failed_check_goes_straight_back_to_the_worker_without_a_reviewer_and_counts_as_a_round_d31_3(flow):
    """Pilot run: reviewers spent tokens judging versions a script had already failed; the fix needs the script's words."""
    head, line = flow.work(checks={"join.json": "fail", "layout.json": "pass"}).splitlines()
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    out = json.loads(line)
    assert (out["role"], out["brief"], out["resume"]) == ("worker", f"production/assets/{AID}/blockout/v2/brief-worker.md",
                                                          "w1")
    assert (flow.st["fix_round"], flow.st.get("fix_base"), flow.st["direct"]) == (1, None, 1)
    assert not (flow.v(1) / "brief-review.md").exists()
    text = flow.text(out)
    assert (f"Bản gốc: `production/assets/{AID}/blockout/v1/` (bản vừa dựng, check fail; final/ + work/)" in text,
            f"Đọc trước nguyên văn lỗi script của bản gốc: `production/assets/{AID}/blockout/v1/final/review/checks/join.json`."
            in text, "Đây là vòng sửa 1." in text) == (True, True, True)
    assert "house-a · blockout v1 · worker DONE (check fail) ·  · vòng sửa 1/3: check fail join.json" in flow.ledger()


@pytest.mark.parametrize("name", ["join.json", "unwrap.json"])
def test_a_failed_join_or_unwrap_json_in_final_review_goes_straight_back_to_the_worker_d31_3(flow, name):
    """join_mesh.py and unwrap.py write to final/review/, not checks/; a pilot model v1 had join.json fail
    (removed_faces_seen = 9) and a scan of {gates,checks}/ alone sent it to the reviewer."""
    out = flow.brief()
    write_json(flow.v(1) / "final/review" / name, {"overall": "fail"})
    head = flow.work(out=out).splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert (flow.st["direct"], (flow.v(1) / "brief-review.md").exists()) == (1, False)
    assert f"house-a · blockout v1 · worker DONE (check fail) ·  · vòng sửa 1/3: check fail {name}" in flow.ledger()


def test_an_info_unwrap_json_in_final_review_does_not_stop_the_review_d31_3(flow):
    out = flow.brief()
    write_json(flow.v(1) / "final/review/unwrap.json", {"overall": "info"})
    assert json.loads(flow.work(out=out).splitlines()[-1])["role"] == "reviewer"


def test_accepted_fail_for_a_hard_gate_is_refused_and_the_round_stays_a_fix_d31_3(flow):
    acceptable(flow.root, "layout.json")
    (flow.v(1) / "final").mkdir(parents=True, exist_ok=True)
    head = flow.work(checks={"schema.json": "fail"}, extra="ACCEPTED_FAIL: schema.json — 2 part thiếu attach\n"
                     ).splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert ("house-a · blockout v1 · ACCEPTED_FAIL từ chối · schema.json: gate cứng, không bao giờ được ACCEPTED_FAIL"
            in flow.ledger(), flow.st.get("accepted_fail")) == (True, None)


def test_accepted_fail_for_an_acceptable_check_with_its_readme_exception_goes_to_the_reviewer_and_is_counted_d31_3(flow):
    acceptable(flow.root, "layout.json")
    out = flow.brief()
    assert "ACCEPTED_FAIL: <file JSON> — <lý do có số>; ... | none   (chỉ layout.json)" in flow.text(out).splitlines()
    (flow.v(1) / "final/README.md").write_text("## NGOẠI LỆ\n- layout.json — bbox lệch 6% do diềm 0.2 m\n", encoding="utf-8")
    line = flow.work(out=out, checks={"layout.json": "fail"},
                     extra="ACCEPTED_FAIL: final/review/checks/layout.json — bbox lệch 6% do diềm 0.2 m\n").splitlines()[-1]
    assert (json.loads(line)["role"], flow.st["accepted_fail"]) == ("reviewer", {"blockout": {"layout.json": 1}})
    assert "house-a · blockout v1 · ACCEPTED_FAIL layout.json · lần 1 · bbox lệch 6% do diềm 0.2 m" in flow.ledger()
    assert ("- Worker khai ACCEPTED_FAIL (check fail không sửa được): layout.json — bbox lệch 6% do diềm 0.2 m. Chấm lý do: "
            "lý do không đứng được thì ghi finding.") in flow.text(json.loads(line)).splitlines()


@pytest.mark.parametrize("readme, why, refusal", [
    (None, "bbox lệch 6% do diềm 0.2 m", "layout.json: chưa ghi vào mục NGOẠI LỆ của final/README.md"),
    ("## NGOẠI LỆ\n- layout.json — lệch\n", "bbox lệch do diềm", "layout.json: lý do phải có số"),
])
def test_accepted_fail_without_the_readme_entry_or_a_number_is_refused_d31_3(flow, readme, why, refusal):
    acceptable(flow.root, "layout.json")
    out = flow.brief()
    if readme:
        (flow.v(1) / "final/README.md").write_text(readme, encoding="utf-8")
    flow.work(out=out, checks={"layout.json": "fail"}, extra=f"ACCEPTED_FAIL: layout.json — {why}\n")
    assert (flow.st["state"], f"house-a · blockout v1 · ACCEPTED_FAIL từ chối · {refusal}" in flow.ledger()) == (
        "running", True)


def test_a_failed_check_after_the_last_fix_round_goes_to_the_human_d31_3(flow):
    out = flow.brief()
    st = flow.st
    st["fix_round"] = 3
    save_st(st)
    assert flow.work(out=out, checks={"join.json": "fail"}) == (
        "house-a: worker DONE (check fail) → blockout/waiting_human. Tiếp: chờ người dùng: hết 3 vòng sửa; check fail ở "
        "v1: join.json (review page)\n")
    assert (flow.st["offer"], flow.st["label"]) == (1, "chưa đạt")


def test_the_first_review_after_two_direct_returns_is_not_stopped_for_no_progress_because_it_has_no_base_d31_3(flow):
    for _ in range(2):
        flow.work(checks={"join.json": "fail"})
    flow.work()
    assert flow.st["fix_round"] == 2
    assert flow.review(counts=counts(major=1), findings=[finding("F1", "major", "structure")]).splitlines()[0] == (
        "house-a: review FIX (major=1) → blockout/fix. Tiếp: giao worker → `brief house-a`")


def test_a_hard_gate_in_the_acceptable_list_of_pipeline_toml_is_refused_at_load_d31_3(flow):
    acceptable(flow.root, "qa_export_check.json")
    with pytest.raises(ProducerError) as e:
        load_cfg()
    assert str(e.value) == ("step blockout: acceptable có gate cứng qa_export_check.json (D31.3: không bao giờ được "
                            "ACCEPTED_FAIL)")


def test_an_accepted_fail_in_a_step_readme_reaches_the_exceptions_of_the_duyet_2_readme_d31_3(flow):
    import assemble
    (flow.v(1) / "final").mkdir(parents=True, exist_ok=True)
    (flow.v(1) / "final/README.md").write_text("# Blockout\n## NGOẠI LỆ\n- layout.json — bbox lệch 6% do diềm 0.2 m\n## Khác\n- x\n",
                                               encoding="utf-8")
    assert assemble.exceptions(flow.st | {"approved": {"blockout": 1}}) == [
        "- blockout: layout.json — bbox lệch 6% do diềm 0.2 m"]


def scope_of(f, out):
    return f.text(out).splitlines()[2]


def test_the_first_review_is_full_a_fix_with_findings_left_is_fix_and_a_fix_naming_every_open_finding_is_full_d31_2(flow):
    """D31.2: a fix round judges only what it fixed; the version about to pass gets every rubric key judged again."""
    flow.work()
    assert scope_of(flow, flow.brief()) == "REVIEW_SCOPE: full"
    assert flow.st["dispatches"][-1]["scope"] == "full"
    flow.review(counts=counts(major=2), top_fix="param: F1, F2",
                findings=[finding("F1", "major", "param"), finding("F2", "major", "param")])
    flow.work(fixed="F1")
    out = flow.brief()
    assert (scope_of(flow, out), flow.st["dispatches"][-1]["scope"]) == ("REVIEW_SCOPE: fix", "fix")
    assert "RUBRIC: <key trong mục ## blockout>=pass|fail|unclear|not_checked; ..." in flow.text(out).splitlines()
    flow.review(out=out, counts=counts(major=1), top_fix="param: F2", compare="F1=better; F2=same",
                rubric="massing=fail; props=not_checked", prior=["- F1: resolved | evidence: clay_front", "- F2: open"])
    flow.work(fixed="F2")
    assert scope_of(flow, flow.brief()) == "REVIEW_SCOPE: full"


def test_not_checked_is_refused_in_a_full_review_d31_2(flow):
    flow.work()
    out = flow.brief()
    with pytest.raises(ProducerError) as e:
        flow.review(out=out, verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass; props=not_checked")
    assert str(e.value) == (f"production/assets/{AID}/blockout/v1/review-out.md sai contract: RUBRIC props=not_checked chỉ "
                            "dùng khi REVIEW_SCOPE: fix")
    assert flow.st["state"] == "reviewing"


def test_a_pass_in_a_fix_round_sends_the_same_version_to_a_full_review_without_a_worker_and_no_extra_round_d31_2(flow):
    fix_v1(flow, 1)
    flow.work()
    head, line = flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass; props=not_checked",
                             compare="F1=better", prior=["- F1: resolved | evidence: clay_front"]).splitlines()
    assert head == "house-a: review PASS (0 mở) → blockout/review. Tiếp: giao reviewer → `brief house-a`"
    out = json.loads(line)
    assert (out["role"], out["brief"], flow.st["versions"], flow.st["fix_round"]) == (
        "reviewer", f"production/assets/{AID}/blockout/v2/brief-review.md", {"blockout": 2}, 1)
    rb = flow.text(out)
    assert (scope_of(flow, out), "COMPARE:" in rb, "PRIOR:" in rb) == ("REVIEW_SCOPE: full", False, False)
    assert flow.review(out=out, verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass; props=pass") == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")
    assert findings.load(AID, "blockout", 2)["base"] == 1


def test_a_waive_while_the_worker_runs_prints_no_second_dispatch_and_the_next_review_skips_the_id_d30_1(flow):
    """The Producer sends an agent for every dispatch line; a second line for a running worker would double the work."""
    fix_v1(flow, 2, "param")
    assert flow.st["state"] == "running"
    brief = (flow.v(2) / "brief-worker.md").read_bytes()
    sent = len(flow.st["dispatches"])
    assert waive(flow, "F1").splitlines() == [
        "house-a: waive blockout F1 (người dùng): đã đóng → blockout/running. Tiếp: đang chờ subagent (mất kết nối thì "
        "`brief house-a` để giao lại)"]
    assert (len(flow.st["dispatches"]), (flow.v(2) / "brief-worker.md").read_bytes()) == (sent, brief)
    rb = flow.text(json.loads(flow.work(out={"report": f"production/assets/{AID}/blockout/v2/worker-out.md",
                                             "brief": f"production/assets/{AID}/blockout/v2/brief-worker.md"}
                                        ).splitlines()[-1]))
    assert ("- F1: ?" in rb, "- F2: ? | evidence: ? |" in rb, "COMPARE: F2=?" in rb.splitlines()) == (False, True, True)


def test_waiving_the_last_findings_of_an_offered_older_version_rereviews_that_version_and_approval_keeps_it_d30_1(flow):
    stall(flow)
    assert (flow.st["offer"], flow.st["versions"]) == (1, {"blockout": 3})
    waive(flow, "F1")
    head, line = waive(flow, "F2").splitlines()
    assert head.endswith("v1 hết lỗi chặn → reviewer chấm lại v1, không gọi worker → blockout/review. Tiếp: giao reviewer "
                         "→ `brief house-a`")
    out = json.loads(line)
    assert (out["brief"], out["report"]) == (f"production/assets/{AID}/blockout/v1/brief-review.md",
                                             f"production/assets/{AID}/blockout/v1/review-out.md")
    assert flow.review(out=out, verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass") == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v1 (review page)\n")
    flow.human("approve", "giữ v1")
    assert (flow.st["approved"], flow.st["rejected"]) == ({"blockout": 1}, {"blockout": [2, 3]})


def test_a_redo_of_a_held_fix_round_prints_the_dispatch_of_the_new_round_d30_5(flow, monkeypatch):
    held_fix(flow, monkeypatch)
    out = cli(flow, "feedback", AID, "mái cao hơn", "--action", "redo").splitlines()
    assert (len(out), json.loads(out[-1])["brief"]) == (2, f"production/assets/{AID}/blockout/v2/brief-worker.md")


def stall_to_human(f):
    """The three rungs of `P stall` on the open dispatch: nudge, a new agent, then the user. Each rung starts from a
    SubagentStop without a report, the one stall that needs no clock. The new agent has no id yet, so it is not nudged."""
    import datetime as dt
    from core import watch
    old = (dt.datetime.now() - dt.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    for agent in ("a1", "a1", None):
        st = f.st
        st["dispatches"][-1] |= {"stopped": "no_report", "agent_id": agent} | (
            {"nudged_at": old} if "nudged_at" in st["dispatches"][-1] else {})
        save_st(st)
        out = f.call(watch.stall, Namespace(id=AID, agent_id=None))
    return out


def test_a_review_that_stalled_three_times_is_offered_as_not_reviewed_and_cannot_be_approved_d36_2_c1_c2(flow):
    """The reproduction: the reviewer of v1 stalled, the asset reached waiting_human with no offer, and the board's approve
    sent offer=null, which act() accepted: v1 was approved although no reviewer passed it."""
    flow.work()
    assert flow.st["state"] == "reviewing"
    stall_to_human(flow)
    st = flow.st
    assert pick(st) | {"offer_key": st["offer_key"], "stalled_from": st["stalled_from"]} == {
        "state": "waiting_human", "fix_round": 0, "fix_base": None, "offer": 1, "label": "chưa chấm",
        "note": "kẹt: subagent dừng, không có report; đã nudge và giao lại → hỏi người dùng; giao lại: `retry house-a`",
        "offer_key": "house-a-blockout-v1-1", "stalled_from": "reviewing"}
    assert [w["key"] for w in st["offer_log"]] == ["house-a-blockout-v1-1"]
    with pytest.raises(ProducerError, match=r"house-a: không duyệt được blockout v1: bản chưa chấm \(kẹt ở reviewing\)"):
        loop.human_action(AID, "approve", "ok", None, None, "house-a-blockout-v1-1")
    assert (flow.st["state"], flow.st["approved"], flow.st.get("decisions")) == ("waiting_human", {}, {})
    assert flow.human("note", "xem lại").startswith("house-a: đã ghi feedback")


def test_a_redo_out_of_a_stall_clears_the_stall_so_the_next_reviewed_version_can_be_approved_d36_2_c1(flow):
    flow.work()
    stall_to_human(flow)
    flow.human("redo", "mái cao hơn")
    assert (flow.st["state"], "stalled_from" in flow.st) == ("fix", False)
    flow.work(fixed="H1")
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="H1=better",
                prior=["- H1: resolved | evidence: clay_front"])
    assert flow.human("approve", "ok").startswith("house-a: đã duyệt blockout v2 → blockout/done")


def test_retry_after_a_reviewer_stall_keeps_the_worker_agent_and_drops_the_unreviewed_offer_c11(flow):
    """The worker that built v1 is still the one to resume in a fix round: only a stalled worker loses its agent id."""
    flow.work()
    assert flow.st["worker_agent_id"] == "w1"
    stall_to_human(flow)
    out = flow.call(loop.retry, Namespace(id=AID))
    st = flow.st
    assert (st["state"], st["worker_agent_id"], st["offer"], st["offer_key"], st["label"], "stalled_from" in st) == (
        "reviewing", "w1", None, None, "", False)
    assert json.loads(out.splitlines()[-1])["role"] == "reviewer"


def test_retry_after_a_worker_stall_drops_the_worker_agent_so_the_new_build_never_resumes_it_c11(flow):
    flow.brief()
    st = flow.st
    st["worker_agent_id"] = "w0"
    save_st(st)
    stall_to_human(flow)
    out = flow.call(loop.retry, Namespace(id=AID))
    assert (flow.st["state"], flow.st["worker_agent_id"], json.loads(out.splitlines()[-1])["resume"]) == (
        "running", None, None)
