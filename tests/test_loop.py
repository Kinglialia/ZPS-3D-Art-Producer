import json
import os
import re
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from shared import SCRIPTS, SUBAGENT_WRITE_BLOCKED, blockout_only, brief_hash, finding, judged_all, report, write_profile
from core import briefs, findings, hashes, intake, loop, policy, texture
from core.state import ProducerError, load_cfg, load_st, save_st

AID = "house-a"
OUTPUTS = ["part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"]
RESULTS = ["inputs", "schema", "materials", "layout", "base", "markers", "support", "proportion"]
ZERO = {"blocker": 0, "major": 0, "minor": 0, "preference": 0, "unclear": 0}
REAL_RECHECK = loop.recheck


def counts(**kw):
    return "; ".join(f"{k}={v}" for k, v in (ZERO | kw).items())


class Flow:
    def __init__(self, root, cap):
        self.root, self.cap = root, cap

    def v(self, n, step="blockout"):
        return self.root / f"production/assets/{AID}/{step}/v{n}"

    def call(self, fn, *a):
        fn(*a)
        got = self.cap.readouterr()
        self.err = got.err
        return got.out

    def brief(self):
        return json.loads(self.call(briefs.run, Namespace(id=AID)))

    def text(self, out):
        return (self.root / out["brief"]).read_text(encoding="utf-8")

    def work(self, status="DONE", out=None, extra="", checks=None, fixed="", raw=None, skip=()):
        """checks: {name: overall} of result JSON the worker leaves in final/review/checks/. raw: {name: text} written as
        is, for a file that does not parse. fixed: the FIXED line; a DONE
        that names every open finding gets a `full` review (D31.2)."""
        out = out or self.brief()
        rep = self.root / out["report"]
        if rep.parent.name.startswith("v"):
            for o in OUTPUTS:
                (rep.parent / "final" / o).write_text("x", encoding="utf-8")
            (rep.parent / "final/review/checks").mkdir(parents=True, exist_ok=True)
            for name, overall in ({f"{k}.json": "pass" for k in RESULTS} | (checks or {})).items():
                write_json(rep.parent / "final/review/checks" / name, {"overall": overall})
            for name, text in (raw or {}).items():
                (rep.parent / "final/review/checks" / name).write_text(text, encoding="utf-8")
            for o in skip:
                (rep.parent / "final" / o).unlink()
        rep.write_text(f"STATUS: {status}\nPROFILE_HASH: {brief_hash(self.text(out))}\n"
                       + (f"FIXED: {fixed}\n" if fixed else "") + extra, encoding="utf-8")
        return self.call(loop.ingest, Namespace(id=AID, agent_id="w1"))

    def review(self, out=None, agent_id=None, **kw):
        out = out or self.brief()
        rep = self.root / out["report"]
        rep.write_text(judged_all(rep, report(**kw)), encoding="utf-8")
        return self.call(loop.ingest, Namespace(id=AID, agent_id=agent_id))

    def human(self, action, text="", step=None):
        return loop.human_action(AID, action, text, step)

    @property
    def st(self):
        return load_st(AID)

    def ledger(self):
        return (self.root / "production/ledger.md").read_text(encoding="utf-8")


@pytest.fixture
def flow(tmp_path, monkeypatch, capsys):
    """The fake worker leaves placeholder files, so the ingest re-run of the step checks (L15) is off here; it runs for
    real in tests/test_e2e_blockout.py and in the tests below that call REAL_RECHECK."""
    monkeypatch.setattr(loop, "recheck", lambda st, step, d: ([], None))
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
    (("FIX", "fix_uv_mesh", False, 2, 3, False, 0, 0), ("reopen", None)),
    (("FIX", "fix_uv_mesh", False, 3, 3, False, 0, 0), ("reopen", None)),
    (("FIX", "regen", False, 0, 3, False, 0, 1), ("fix", None)),
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
    assert ("house-a · blockout v4 · review FIX (major=2) · massing=fail; mass=pass; silhouette=pass; identity=pass; "
            "open_closed=pass; props=pass; foot=pass; own_decisions=pass · hết 3 vòng sửa") in flow.ledger()


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


def write_results(final: Path):
    """The result JSON a correct worker leaves in final/review/checks/ (pipeline.toml outputs, D36.4)."""
    for k in RESULTS:
        write_json(final / f"review/checks/{k}.json", {"overall": "pass"})


def write_json(p: Path, d: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def test_fix_brief_lists_only_the_failing_gate_and_check_json_of_the_base_so_the_worker_reads_script_errors_first(
        flow, held):
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


def test_need_evidence_prints_the_dispatch_of_the_render_worker_c16(flow):
    """The ingest that moves the asset to evidence ends with the dispatch line, as the one that ends in fix does: a
    Producer that reads only the ingest output no longer waits for a turn that never comes."""
    head, line = need_evidence_v1(flow).splitlines()
    assert head == "house-a: review FIX (unclear=1) → blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`"
    out = json.loads(line)
    ev = f"production/assets/{AID}/blockout/v1/review/evidence-1"
    assert (out["role"], out["resume"], out["brief"]) == ("worker", "w1", f"{ev}/brief-worker.md")
    assert flow.st["state"] == "evidence_running"


def test_need_evidence_renders_into_the_version_review_folder_and_the_reviewer_rejudges_the_same_version(flow, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(loop, "dispatch_next", lambda cfg, st: None)
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
        "note": "bước views chưa bật"}
    assert flow.v(1).is_dir() and not (flow.root / "deliver").exists()
    assert "house-a · blockout v2 · duyệt bởi người dùng" in flow.ledger()
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert str(e.value) == "house-a: state=done_enabled, không có việc để giao (xong các bước đang bật)"


def test_a_gd1_asset_parked_at_done_enabled_moves_on_with_retry_once_its_next_step_is_enabled(flow):
    pass_v2(flow)
    flow.human("approve", "ok")
    assert flow.call(loop.retry, Namespace(id=AID)) == "house-a: → done_enabled. Tiếp: xong các bước đang bật\n"
    assert flow.st["note"] == "bước views chưa bật"
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views"\nenabled = false\n', 'id = "views"\n'),
                 encoding="utf-8")
    from core import limits
    assert "[house-a] blockout/done_enabled → bước views đã bật → `retry house-a`\n" in flow.call(
        limits.show_next, Namespace(session=False))
    head, line = flow.call(loop.retry, Namespace(id=AID)).splitlines()
    assert head == "house-a: → todo. Tiếp: giao worker → `brief house-a`"
    assert json.loads(line)["brief"] == f"production/assets/{AID}/views/v1/brief-worker.md"
    assert {k: flow.st[k] for k in ("stage", "state", "approved")} == {"stage": "views", "state": "running",
                                                                     "approved": {"blockout": 2}}


def test_approving_the_offered_best_version_rejects_the_newer_versions(flow):
    stall(flow)
    flow.human("approve")
    assert (flow.st["approved"], flow.st["rejected"]) == ({"blockout": 1}, {"blockout": [2, 3]})


def test_brief_never_dispatches_a_disabled_step(flow):
    st = flow.st
    st["stage"] = "views"
    save_st(st)
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert str(e.value) == "house-a: bước views chưa bật (enabled = false), không giao"


def test_approving_the_last_step_ends_at_done_without_the_old_final_human_gate(flow):
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").split("[[steps]]\nid = \"views\"")[0], encoding="utf-8")
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


def variant_results(b: Path):
    """make_variant.py leaves the result JSON of its chain in the variant, so the variant that is picked carries them."""
    for k in RESULTS:
        write_json(b / f"review/checks/{k}.json", {"overall": "pass"})


def test_a_picked_variant_missing_a_required_output_blocks_the_review_and_copies_nothing(flow):
    """Copied as is, the incomplete variant reached waiting_human and the approval then died on the missing lock file."""
    fix_v1(flow, 1, "param")
    flow.work(fixed="F1")
    b = flow.v(2) / "variants/b"
    b.mkdir(parents=True)
    (b / "blockout.md").write_text("b", encoding="utf-8")
    variant_results(b)
    flow.review(pick="b", **PICKED)
    assert (pick(flow.st)["state"], pick(flow.st)["note"]) == ("blocked", (
        f"PICK b: production/assets/{AID}/blockout/v2/variants/b/ thiếu output bắt buộc: "
        "part_graph.json, parts_lib.py, assembled.glb, sources.json"))
    assert {p.name: p.read_text(encoding="utf-8") for p in (flow.v(2) / "final").iterdir() if p.is_file()} == {
        o: "x" for o in OUTPUTS}
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
    variant_results(b)
    out = flow.brief()
    with pytest.raises(ProducerError) as e:
        flow.review(out=out, pick="c", **PICKED)
    assert str(e.value) == f"PICK c: không có production/assets/{AID}/blockout/v2/variants/c/"
    assert flow.st["state"] == "reviewing"
    flow.review(out=out, pick="b", **PICKED)
    final = flow.v(2) / "final"
    assert {p.name: p.read_text(encoding="utf-8") for p in final.iterdir() if p.is_file()} == {o: "b" for o in OUTPUTS}
    assert (flow.v(2) / "variants/a/part_graph.json").read_text(encoding="utf-8") == "x"
    assert flow.st["state"] == "waiting_human"


def test_a_review_that_dies_on_its_pick_writes_no_waive_so_the_corrected_report_still_ingests(flow):
    """The waive went to disk before PICK named a missing variant. The brief's PRIOR still listed the waived id, so the
    corrected report was refused with "PRIOR có id không đang mở"."""
    fix_v1(flow, 2, "param")
    flow.work(fixed="F1, F2")
    b = flow.v(2) / "variants/b"
    b.mkdir(parents=True)
    for o in OUTPUTS:
        (b / o).write_text("b", encoding="utf-8")
    variant_results(b)
    out = flow.brief()
    waive(flow, "F2")
    review = dict(verdict="FIX", top_fix="param: F2", counts=counts(major=1), rubric="massing=pass",
                  compare="F1=better; F2=same", prior=["- F1: resolved | evidence: clay_front", "- F2: open"])
    with pytest.raises(ProducerError, match="PICK c: không có"):
        flow.review(out=out, pick="c", **review)
    assert (findings.load(AID, "blockout", 1)["findings"]["F2"]["status"], list(flow.st["waive_pending"]["blockout"])) == (
        "open", ["F2"])
    assert flow.review(out=out, pick="b", **review).startswith("house-a: review PASS (0 mở) → blockout/waiting_human")
    assert findings.load(AID, "blockout", 2)["findings"]["F2"]["status"] == "waived"


def test_assemble_approval_copies_final_to_deliver_and_a_later_redo_marks_the_delivered_readme(flow):
    st = flow.st
    st |= {"stage": "assemble", "state": "waiting_human", "versions": {"blockout": 1, "assemble": 1},
           "approved": {"blockout": 1}, "offer": 1}
    save_st(st)
    (flow.v(1, "assemble") / "final").mkdir(parents=True)
    (flow.v(1, "assemble") / "final/README.md").write_text("Trạng thái: chờ DUYỆT 2\n# House A\n", encoding="utf-8")
    (flow.root / "production/policy.yaml").write_text("purge: off\n", encoding="utf-8")
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
        flow.human("redo", "x", "views")
    assert str(e.value) == "house-a: không làm lại views được: asset đang ở bước blockout"
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
    assert [l for l in text.splitlines() if l.startswith("RUN: ")]
    assert not re.search(r"echo \$!|wait \$!|PID", text)


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
    body = judged_all(flow.root / out["report"], report(counts=counts(major=1), findings=[finding("F1", "major")]))
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
    body = judged_all(flow.root / out["report"], report(counts=counts(major=1), findings=[finding("F1", "major")]))
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



TEMPLATE_ACCEPTABLE = 'acceptable = ["proportion.json", "base.json", "gates/*.json#gate5.health"]\n'


def acceptable(root, *names):
    p = root / "production/pipeline.toml"
    text = p.read_text(encoding="utf-8")
    assert TEMPLATE_ACCEPTABLE in text
    p.write_text(text.replace(TEMPLATE_ACCEPTABLE, f"acceptable = {json.dumps(list(names))}\n", 1), encoding="utf-8")


def test_a_failed_check_goes_straight_back_to_the_worker_without_a_reviewer_and_is_not_a_fix_round_d31_3_w7(flow):
    """Pilot run: reviewers spent tokens judging versions a script had already failed; the fix needs the script's words.
    The round has its own counter (W7): a worker that cannot fix a check must not use up the rounds of the reviewer."""
    head, line = flow.work(checks={"join.json": "fail", "layout.json": "pass"}).splitlines()
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    out = json.loads(line)
    assert (out["role"], out["brief"], out["resume"]) == ("worker", f"production/assets/{AID}/blockout/v2/brief-worker.md",
                                                          "w1")
    assert (flow.st["fix_round"], flow.st.get("fix_base"), flow.st["direct"], flow.st["direct_rounds"]) == (0, None, 1, 1)
    assert not (flow.v(1) / "brief-review.md").exists()
    text = flow.text(out)
    assert (f"Bản gốc: `production/assets/{AID}/blockout/v1/` (bản vừa dựng, check fail; final/ + work/)" in text,
            f"Đọc trước nguyên văn lỗi script của bản gốc: `production/assets/{AID}/blockout/v1/final/review/checks/join.json`."
            in text, "Đây là vòng trả thẳng 1." in text) == (True, True, True)
    assert "house-a · blockout v1 · worker DONE (check fail) ·  · vòng trả thẳng 1/2: check fail join.json" in flow.ledger()


@pytest.mark.parametrize("name", ["join.json", "unwrap.json"])
def test_a_failed_join_or_unwrap_json_in_final_review_goes_straight_back_to_the_worker_d31_3(flow, name):
    """join_mesh.py and unwrap.py write to final/review/, not checks/; a pilot model v1 had join.json fail
    (removed_faces_seen = 9) and a scan of {gates,checks}/ alone sent it to the reviewer."""
    out = flow.brief()
    write_json(flow.v(1) / "final/review" / name, {"overall": "fail"})
    head = flow.work(out=out).splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert (flow.st["direct"], (flow.v(1) / "brief-review.md").exists()) == (1, False)
    assert f"house-a · blockout v1 · worker DONE (check fail) ·  · vòng trả thẳng 1/2: check fail {name}" in flow.ledger()


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


def test_a_failed_check_after_the_direct_round_cap_goes_to_the_human_w7(flow):
    out = flow.brief()
    st = flow.st
    st["direct_rounds"] = 2
    save_st(st)
    assert flow.work(out=out, checks={"join.json": "fail"}) == (
        "house-a: worker DONE (check fail) → blockout/waiting_human. Tiếp: chờ người dùng: hết 2 vòng trả thẳng; check fail "
        "ở v1: join.json; bản chưa chấm, không duyệt được → Cần sửa kèm lời, hoặc sửa asset-card/profile rồi `retry house-a` (review page)\n")
    assert (flow.st["offer"], flow.st["label"]) == (1, "chưa chấm")


def test_the_fix_rounds_of_the_reviewer_do_not_stop_a_direct_round_w7(flow):
    """Run 5: a check that the worker could not fix used up max_fix_rounds, and the human got the version with no
    reviewer finding. The caps are separate: three used fix rounds leave the direct rounds whole."""
    out = flow.brief()
    st = flow.st
    st["fix_round"] = 3
    save_st(st)
    head = flow.work(out=out, checks={"join.json": "fail"}).splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert (flow.st["fix_round"], flow.st["direct_rounds"]) == (3, 1)


def test_the_same_failing_names_as_the_round_before_ask_the_human_at_once_and_name_the_checks_w6(flow):
    """Run 5: the same failure went back to the worker until the rounds ran out. Two rounds with the same names mean the
    worker cannot fix it, so the third dispatch is waste."""
    flow.work(checks={"join.json": "fail", "layout.json": "fail"})
    assert flow.st["direct_names"] == ["join.json", "layout.json"]
    assert flow.work(checks={"layout.json": "fail", "join.json": "fail"}) == (
        "house-a: worker DONE (check fail) → blockout/waiting_human. Tiếp: chờ người dùng: check fail y hệt vòng trả thẳng "
        "trước, ở v2: join.json, layout.json; bản chưa chấm, không duyệt được → Cần sửa kèm lời, hoặc sửa asset-card/profile rồi `retry house-a` (review page)\n")
    assert (flow.st["fix_round"], flow.st["direct_rounds"], flow.st["label"]) == (0, 1, "chưa chấm")


def test_a_direct_round_stop_offers_its_version_as_unreviewed_and_approve_is_refused_until_a_retry_rebuilds_it(flow):
    """The stop offered for approval a version that fails a hard gate and that no reviewer judged."""
    flow.work(checks={"counts.json": "fail"})
    assert flow.work(checks={"counts.json": "fail"}).splitlines()[0] == (
        "house-a: worker DONE (check fail) → blockout/waiting_human. Tiếp: chờ người dùng: check fail y hệt vòng trả thẳng "
        "trước, ở v2: counts.json; bản chưa chấm, không duyệt được → Cần sửa kèm lời, hoặc sửa asset-card/profile rồi "
        "`retry house-a`; gate cứng counts.json không nhận ACCEPTED_FAIL (review page)")
    assert (flow.st["offer"], flow.st["label"]) == (2, "chưa chấm")
    with pytest.raises(ProducerError, match="không duyệt được blockout v2: bản chưa chấm"):
        flow.human("approve")
    head, line = flow.call(loop.retry, Namespace(id=AID)).splitlines()
    assert head == "house-a: → fix. Tiếp: giao worker → `brief house-a`"
    sent = json.loads(line)
    assert (sent["brief"], flow.st["direct"], flow.st["direct_rounds"]) == (
        f"production/assets/{AID}/blockout/v3/brief-worker.md", 2, 1)
    assert "Đây là vòng trả thẳng 1." in flow.text(sent)


def test_other_failing_names_than_the_round_before_are_progress_so_the_round_goes_on_w6(flow):
    flow.work(checks={"join.json": "fail"})
    flow.work(checks={"layout.json": "fail"})
    assert (flow.st["state"], flow.st["direct_rounds"], flow.st["direct_names"]) == ("running", 2, ["layout.json"])


def test_a_clean_version_ends_the_run_of_direct_rounds_so_a_later_failure_starts_again_w7(flow):
    flow.work(checks={"join.json": "fail"})
    flow.work()
    assert (flow.st["direct_rounds"], flow.st["direct_names"]) == (0, None)


def test_the_first_review_after_two_direct_returns_is_not_stopped_for_no_progress_because_it_has_no_base_d31_3(flow):
    flow.work(checks={"join.json": "fail"})
    flow.work(checks={"layout.json": "fail"})
    flow.work()
    assert (flow.st["fix_round"], flow.st["direct_rounds"]) == (0, 0)
    assert flow.review(counts=counts(major=1), findings=[finding("F1", "major", "structure")]).splitlines()[0] == (
        "house-a: review FIX (major=1) → blockout/fix. Tiếp: giao worker → `brief house-a`")
    assert flow.st["fix_round"] == 1


def gate_json(flow, part, failing=()):
    """A kit gate result of one part, as gates.py writes it: one entry per gate, the failing ones named."""
    checks = [{"check": c, "status": "fail" if c in failing else "pass"} for c in ("gate2.contact", "gate5.health")]
    write_json(flow.v(1) / f"final/review/gates/{part}.json", {"overall": "fail" if failing else "pass", "checks": checks})


def accept(flow, claim, why="hai part chạm nhau dọc một cạnh, 1 cạnh mở"):
    out = flow.brief()
    (flow.v(1) / "final/README.md").write_text(f"## NGOẠI LỆ\n- {claim} — {why}\n", encoding="utf-8")
    flow.work(out=out, extra=f"ACCEPTED_FAIL: {claim} — {why}\n")
    return flow.st


def test_the_template_lets_a_blockout_worker_accept_a_proportion_check_that_has_no_other_exit_c19(flow):
    """A false proportion fail (a concept mask the camera cannot match) had no exit: the worker looped to the cap."""
    out = flow.brief()
    assert "(chỉ proportion.json, base.json, gates/*.json#gate5.health)" in flow.text(out)
    (flow.v(1) / "final/README.md").write_text("## NGOẠI LỆ\n- proportion.json — front lệch 12% do mái chìa 0.4 m\n", encoding="utf-8")
    flow.work(out=out, checks={"proportion.json": "fail"},
              extra="ACCEPTED_FAIL: proportion.json — front lệch 12% do mái chìa 0.4 m\n")
    assert (flow.st["state"], flow.st["accepted_fail"]) == ("reviewing", {"blockout": {"proportion.json": 1}})


def test_a_gate_json_whose_only_failing_check_is_gate5_health_can_be_accepted_c19(flow):
    gate_json(flow, "roof", failing=["gate5.health"])
    st = accept(flow, "roof.json")
    assert (st["state"], st["accepted_fail"]) == ("reviewing", {"blockout": {"roof.json": 1}})


def test_a_gate_json_with_another_failing_gate_beside_gate5_health_is_still_refused_c19(flow):
    """gate2.contact says a part floats: accepting it hides a real structure fault behind the edge-contact exception."""
    gate_json(flow, "roof", failing=["gate5.health", "gate2.contact"])
    accept(flow, "roof.json")
    assert flow.st["state"] == "running"
    assert f"{AID} · blockout v1 · ACCEPTED_FAIL từ chối · roof.json: không có trong acceptable của bước blockout" in flow.ledger()


def test_a_name_in_the_acceptable_list_does_not_cover_the_gate_json_of_a_part_that_has_the_same_name_c19(flow):
    """A part called `base` is the norm; its gates/base.json is not the base-margin check checks/base.json."""
    gate_json(flow, "base", failing=["gate2.contact"])
    accept(flow, "base.json")
    assert flow.st["state"] == "running"
    assert f"{AID} · blockout v1 · ACCEPTED_FAIL từ chối · base.json: không có trong acceptable của bước blockout" in flow.ledger()


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


def test_a_gate_json_cut_short_counts_as_an_error_and_goes_back_to_the_worker_c5(flow):
    """A tool killed in the middle of its write leaves half a JSON. Skipped, it read as a pass and the reviewer judged a
    version whose check never finished."""
    head = flow.work(raw={"layout.json": '{"tool": "blockout/check_layout", "overall": "pa'}).splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert flow.st["direct"] == 1 and "layout.json" in flow.st["note"]


def test_accepted_fail_cannot_cover_a_json_that_does_not_parse_c5(flow):
    acceptable(flow.root, "layout.json")
    out = flow.brief()
    (flow.v(1) / "final").mkdir(parents=True, exist_ok=True)
    (flow.v(1) / "final/README.md").write_text("## NGOẠI LỆ\n- layout.json — bbox lệch 6% do diềm 0.2 m\n", encoding="utf-8")
    flow.work(out=out, raw={"layout.json": '{"overall": "fa'},
              extra="ACCEPTED_FAIL: final/review/checks/layout.json — bbox lệch 6% do diềm 0.2 m\n")
    assert (flow.st["state"], flow.st["direct"]) == ("running", 1)
    assert f"{AID} · blockout v1 · ACCEPTED_FAIL từ chối · layout.json: JSON không đọc được" in flow.ledger()


def test_not_checked_inside_a_json_whose_overall_is_pass_stays_a_pass_c5(flow):
    """The views measure writes detail.<view> as not_checked on purpose, and a tool writes it when a check does not apply:
    only a missing file, an unreadable file or an overall of fail or error blocks."""
    out = flow.brief()
    write_json(flow.v(1) / "final/review/checks/proportion.json", {"overall": "pass", "checks": [
        {"check": "proportion.front", "status": "not_checked"}, {"check": "proportion.top", "status": "pass"}]})
    flow.work(out=out)
    assert (flow.st["state"], flow.st["direct"]) == ("reviewing", None)


def at_step(f, sid):
    """The blockout flow with the asset moved to `sid`, v1 running: the ingest reads the outputs of that step."""
    ph = brief_hash(f.text(f.brief()))
    st = f.st
    st |= {"stage": sid, "state": "running", "versions": {sid: 1}, "inputs": {sid: {"v1": {"profile": ph}}}}
    save_st(st)
    (f.v(1, sid) / "final").mkdir(parents=True, exist_ok=True)
    return f.v(1, sid), ph


def result_files(sid):
    cfg = load_cfg()
    step = next(s for s in cfg["steps"] if s["id"] == sid)
    return step, [o for o in step["outputs"] if o.startswith("final/review/") and o.endswith(".json")]


@pytest.mark.parametrize("sid", ["blockout", "views", "model", "texture"])
def test_a_worker_that_left_out_one_result_json_of_its_step_is_blocked_with_the_file_named_c5(flow, sid):
    """No output list required the gate and check JSON, so a worker that never ran them went straight to the reviewer."""
    from core.state import outputs_of
    step, results = result_files(sid)
    assert results, f"{sid}: pipeline.toml lists no result JSON in outputs"
    d, ph = at_step(flow, sid)
    for gone in results:
        for o in outputs_of(step, flow.st):
            p = d / o
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{"overall": "pass"}' if o.endswith(".json") else "x", encoding="utf-8")
        (d / gone).unlink()
        (d / "worker-out.md").write_text(f"STATUS: DONE\nPROFILE_HASH: {ph}\n", encoding="utf-8")
        flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))
        assert (flow.st["state"], flow.st["note"]) == ("blocked", f"thiếu output bắt buộc: {gone}")
        st = flow.st
        st |= {"state": "running"}
        save_st(st)


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


ALL_BUT_FOOT = "mass=pass; silhouette=pass; identity=pass; open_closed=pass; props=pass; own_decisions=pass"


def raw_review(flow, out, **kw):
    """A reviewer report written as is: no key of the rubric is added for the test."""
    (flow.root / out["report"]).write_text(report(**kw), encoding="utf-8")
    return flow.call(loop.ingest, Namespace(id=AID, agent_id=None))


def test_a_full_review_that_leaves_rubric_keys_out_is_a_contract_error_that_names_them(flow):
    """A key left out was never judged, yet a PASS without not_checked would let the version through."""
    flow.work()
    out = flow.brief()
    with pytest.raises(ProducerError) as e:
        raw_review(flow, out, verdict="PASS", top_fix=None, counts=counts(), rubric="mass=pass; props=pass")
    assert str(e.value) == (f"production/assets/{AID}/blockout/v1/review-out.md sai contract: RUBRIC thiếu key của mục "
                            "## blockout: silhouette, identity, open_closed, foot, own_decisions")


def test_a_rubric_key_in_another_case_counts_as_the_key_of_the_rubric_section(flow):
    """`Mass=pass` judged the key `mass`; a case-sensitive match refused the report as "RUBRIC thiếu key … mass". A
    capitalised key written in rubric.md is the same key too."""
    rub = flow.root / f"production/assets/{AID}/rubric.md"
    rub.write_text(rub.read_text(encoding="utf-8").replace("\n- foot:", "\n- Foot:", 1), encoding="utf-8")
    assert briefs.rubric_keys(AID, "blockout")[-2:] == ["foot", "own_decisions"]
    flow.work()
    out = flow.brief()
    upper = "; ".join(f"{k.upper()}=pass" for k in ("mass", "silhouette", "identity", "open_closed", "props", "foot",
                                                     "own_decisions"))
    assert raw_review(flow, out, verdict="PASS", top_fix=None, counts=counts(), rubric=upper).startswith(
        "house-a: review PASS (0 mở) → blockout/waiting_human")
    assert flow.st["last_rubric"].startswith("mass=pass; silhouette=pass")


def test_a_pass_in_a_fix_round_that_leaves_a_key_out_is_refused_so_it_cannot_skip_the_full_review(flow):
    fix_v1(flow, 1)
    flow.work()
    out = flow.brief()
    assert scope_of(flow, out) == "REVIEW_SCOPE: fix"
    with pytest.raises(ProducerError) as e:
        raw_review(flow, out, verdict="PASS", top_fix=None, counts=counts(), rubric=ALL_BUT_FOOT, compare="F1=better",
                   prior=["- F1: resolved | evidence: clay_front"])
    assert str(e.value).endswith("sai contract: RUBRIC thiếu key của mục ## blockout: foot")


def test_a_key_the_script_filled_may_be_left_out_of_the_rubric(flow, monkeypatch):
    monkeypatch.setitem(briefs.PREFILL, "blockout", {"foot": lambda fr, acc: ("pass", "base.json")})
    flow.work()
    out = flow.brief()
    assert raw_review(flow, out, verdict="PASS", top_fix=None, counts=counts(), rubric=ALL_BUT_FOOT).startswith(
        "house-a: review PASS (0 mở) → blockout/waiting_human")


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


def rereview_v1_asks_for_evidence(f):
    """v3 is the newest build, v1 the best: the waives make the reviewer judge v1 again, and it asks for more images."""
    stall(f)
    waive(f, "F1")
    waive(f, "F2")
    assert (f.st["rereview"], f.st["versions"]) == (1, {"blockout": 3})
    return f.review(counts=counts(unclear=1), rubric="props=unclear", top_fix="need_evidence: F3",
                    findings=[finding("F3", "unclear", "param")])


def test_the_evidence_round_of_a_rereview_targets_the_version_judged_not_the_newest_c7(flow):
    """The reproduction: the answer need_evidence cleared `rereview`, `current_v()` fell back to v3, so the worker
    rendered pictures for v3 and its report was checked against the hash of v1."""
    assert rereview_v1_asks_for_evidence(flow).splitlines()[0].endswith(
        "→ blockout/evidence. Tiếp: giao worker render bằng chứng → `brief house-a`")
    assert (flow.st["evidence"]["version"], loop.current_v(flow.st, "blockout")) == (1, 1)
    out = flow.brief()
    ev = f"production/assets/{AID}/blockout/v1/review/evidence-1"
    assert (out["brief"], out["report"]) == (f"{ev}/brief-worker.md", f"{ev}/worker-out.md")
    head, line = flow.work(out=out).splitlines()
    assert head == "house-a: evidence-1 DONE → blockout/review. Tiếp: giao reviewer → `brief house-a`"
    assert json.loads(line)["report"] == f"production/assets/{AID}/blockout/v1/review-out.md"


def test_a_pass_after_the_evidence_of_a_rereview_offers_the_judged_version_not_the_newest_c7(flow):
    rereview_v1_asks_for_evidence(flow)
    flow.work()
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="props=pass",
                prior=["- F3: resolved | evidence: clay_front"])
    st = flow.st
    assert (st["state"], st["offer"], st["evidence"], st["versions"]) == ("waiting_human", 1, None, {"blockout": 3})
    flow.human("approve", "giữ v1")
    assert (flow.st["approved"], flow.st["rejected"]) == ({"blockout": 1}, {"blockout": [2, 3]})


CAM_MARK = {"n": 1, "image": "review/game_cam.png", "shape": "rect", "coords": [0.1, 0.2, 0.3, 0.6], "note": "cửa lệch trái"}


def blockout_waiting_with_a_picture(f):
    from PIL import Image
    p = f.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views"\nenabled = false', 'id = "views"'),
                 encoding="utf-8")
    f.work()
    f.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass")
    (f.v(1) / "final/review").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 100), "white").save(f.v(1) / "final/review/game_cam.png")
    assert f.st["state"] == "waiting_human"


def test_marks_sent_with_an_approve_become_a_minor_note_the_next_step_brief_lists_c10(flow):
    """The reproduction: the marks became open `major` H findings on the approved version, and no later brief reads them,
    so the user's marks were lost."""
    blockout_waiting_with_a_picture(flow)
    ok, msg = loop.act(AID, "approve", "đạt, nhớ cửa", None, [CAM_MARK])
    assert (ok, msg.splitlines()[0]) == (True, "house-a: đã duyệt blockout v1 → views/todo; khoanh 1 vùng → H1. "
                                              "Tiếp: giao worker → `brief house-a`")
    h1 = findings.load(AID, "blockout", 1)["findings"]["H1"]
    assert (h1["kind"], h1["priority"], h1["status"], h1["repair"], h1["mark"]["n"]) == (
        "note", "minor", "open", "cửa lệch trái", 1)
    brief = flow.text(flow.brief())
    assert (f"Ghi chú còn mở của reviewer `blockout` v1: H1 trong `production/assets/{AID}/blockout/v1/findings.json`"
            in brief) is True


def test_marks_sent_with_a_redo_stay_major_findings_of_the_step_kind_c10(flow):
    blockout_waiting_with_a_picture(flow)
    loop.act(AID, "redo", "", "blockout", [CAM_MARK])
    h1 = findings.load(AID, "blockout", 1)["findings"]["H1"]
    assert (h1["kind"], h1["priority"]) == ("structure", "major")


def test_a_step_with_note_kinds_stores_the_marks_of_an_approve_as_its_first_note_kind_c10(flow):
    cfg = load_cfg()
    views = next(s for s in cfg["steps"] if s["id"] == "views")
    texture = next(s for s in cfg["steps"] if s["id"] == "texture")
    for step, kind in ((views, "note_exception"), (texture, "note")):
        findings.add_human(AID, step, 1, None, [{"n": 1, "image": "back.png", "png": "p/x.png", "note": "n"}])
        assert loop.marks_as_notes(AID, step, 1, ["H1"]) == ["H1"]
        assert findings.load(AID, step["id"], 1)["findings"]["H1"]["kind"] == kind


def pending_texts(f):
    return {s: [(e["text"], e["offer"], e["marks"]) for e in es] for s, es in f.st.get("pending_redo", {}).items()}


def test_a_redo_sent_while_the_worker_runs_is_stored_and_becomes_a_finding_at_its_ingest_c6(flow):
    """The reproduction: the redo printed "sẽ áp dụng ở vòng sau" and nothing kept it; v1 went to review as if it had
    never been sent."""
    flow.brief()
    assert flow.human("redo", "mái cao hơn") == (
        "house-a: đã ghi feedback; house-a đang running, lưu Cần sửa blockout: áp dụng ở lần ingest kế. "
        "Tiếp: đang chờ subagent (mất kết nối thì `brief house-a` để giao lại)")
    assert pending_texts(flow) == {"blockout": [("mái cao hơn", None, [])]}
    assert findings.load(AID, "blockout", 1) is None
    head = flow.work().splitlines()[0]
    assert head == "house-a: worker DONE → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert findings.load(AID, "blockout", 1)["findings"] == {"H1": H1}
    assert (flow.st["pending_redo"], flow.st["fix_base"], flow.st["round_versions"]) == ({}, 1, [1])
    assert "Cần sửa nhận lúc đang chạy → blockout H1" in flow.ledger()


def test_two_redos_sent_while_the_worker_runs_become_two_findings_in_one_fix_round_c6(flow):
    flow.brief()
    flow.human("redo", "mái cao hơn")
    flow.human("redo", "cửa rộng hơn")
    flow.work()
    doc = findings.load(AID, "blockout", 1)["findings"]
    assert (sorted(doc), doc["H2"]["repair"], flow.st["state"], flow.st["fix_round"]) == (
        ["H1", "H2"], "cửa rộng hơn", "running", 1)


def test_a_redo_sent_while_the_reviewer_judges_turns_a_pass_at_a_human_gate_into_a_fix_round_not_an_offer_c6(flow):
    flow.work()
    flow.brief()
    assert flow.st["state"] == "reviewing"
    flow.human("redo", "mái cao hơn")
    assert pending_texts(flow) == {"blockout": [("mái cao hơn", None, [])]}
    head = flow.review(out={"report": f"production/assets/{AID}/blockout/v1/review-out.md",
                            "brief": f"production/assets/{AID}/blockout/v1/brief-review.md"},
                       verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass").splitlines()[0]
    assert head == "house-a: review PASS (0 mở) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    st = flow.st
    assert (st["offer"], st["approved"], st["pending_redo"], list(findings.load(AID, "blockout", 1)["findings"])) == (
        None, {}, {}, ["H1"])


def test_a_redo_sent_while_the_reviewer_judges_is_not_lost_when_the_reviewer_would_approve_it_c6(flow):
    """The reproduction: the automatic PASS approved v1 and approval deleted the redo line of "Hiện hành"."""
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    flow.work()
    flow.brief()
    flow.human("redo", "mái cao hơn")
    flow.review(out={"report": f"production/assets/{AID}/blockout/v1/review-out.md",
                     "brief": f"production/assets/{AID}/blockout/v1/brief-review.md"},
                verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass")
    st = flow.st
    assert (st["state"], st["approved"], st["pending_redo"], list(findings.load(AID, "blockout", 1)["findings"])) == (
        "running", {}, {}, ["H1"])
    fb = (flow.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")
    assert "- " in fb.split("## Log")[0] and "blockout v1 · redo · mái cao hơn" in fb.split("## Log")[0]


def test_a_redo_sent_during_an_evidence_round_becomes_a_finding_when_the_evidence_is_ingested_c6(flow):
    need_evidence_v1(flow)
    out = flow.brief()
    assert flow.st["state"] == "evidence_running"
    flow.human("redo", "chụp gần cửa")
    assert pending_texts(flow) == {"blockout": [("chụp gần cửa", None, [])]}
    head = flow.work(out=out).splitlines()[0]
    assert head == "house-a: evidence-1 DONE → blockout/fix. Tiếp: giao worker → `brief house-a`"
    st = flow.st
    assert (st["evidence"], st["pending_redo"], "H1" in findings.load(AID, "blockout", 1)["findings"]) == (None, {}, True)


def test_a_redo_with_marks_sent_while_the_worker_runs_keeps_the_marks_for_the_finding_c6(flow):
    from PIL import Image
    flow.brief()
    (flow.v(1) / "final/review").mkdir(parents=True)
    Image.new("RGB", (200, 100), "white").save(flow.v(1) / "final/review/game_cam.png")
    msg = loop.act(AID, "redo", "", None, [CAM_MARK])[1]
    assert msg.startswith("house-a: đã ghi feedback; house-a đang running, lưu Cần sửa blockout")
    assert [(e["text"], len(e["marks"])) for e in flow.st["pending_redo"]["blockout"]] == [(None, 1)]
    flow.work()
    h1 = findings.load(AID, "blockout", 1)["findings"]["H1"]
    assert (h1["kind"], h1["priority"], h1["repair"], h1["mark"]["n"]) == ("structure", "major", "cửa lệch trái", 1)
    folder = flow.root / "production/assets" / AID / "feedback/blockout-v1-1"
    assert json.loads((folder / "regions.json").read_text(encoding="utf-8"))[0]["id"] == "H1"


def test_a_redo_for_a_later_step_than_the_stage_is_still_refused_and_stores_nothing_c6(flow):
    flow.brief()
    with pytest.raises(ProducerError, match="không làm lại views được"):
        flow.human("redo", "x", "views")
    assert flow.st.get("pending_redo", {}) == {}


def stalled_worker_with_pending_redo(f):
    """Worker v2 runs, the user sends "Cần sửa" (stored), then the worker goes silent past the new-agent rung."""
    import datetime as dt
    f.work()
    f.review(top_fix="structure: F1", findings=[finding("F1", "major", "structure")])
    f.brief()
    f.human("redo", "mái cao hơn")
    old = dt.datetime.now() - dt.timedelta(minutes=40)
    st = f.st
    st["dispatches"][-1] |= {"at": old.strftime("%Y-%m-%d %H:%M:%S"), "redispatch_of": "2026-11-12 09:00:00"}
    save_st(st)
    for p in [f.v(2), *f.v(2).rglob("*")]:
        os.utime(p, (old.timestamp(), old.timestamp()))


def h_texts(n):
    return [x["repair"] for i, x in findings.load(AID, "blockout", n)["findings"].items() if i.startswith("H")]


def test_a_redo_takes_in_the_stored_redos_of_its_step_so_none_turns_the_next_version_into_an_unreviewed_fix_k06(flow):
    """The reproduction: the stored "Cần sửa" outlived the user's redo at the stall rung, and the ingest of v3 applied
    it, so v3 went back to a worker as v4 and no reviewer judged it."""
    stalled_worker_with_pending_redo(flow)
    st = flow.st
    st["stalled_from"] = "running"
    loop.move(st, "ask_human")
    loop.offer(st, "blockout", 2, label=loop.UNREVIEWED, note="kẹt")
    st["dispatches"][-1]["ended"] = {"at": "2026-11-12 10:00:00", "why": "kẹt"}
    save_st(st)
    flow.human("redo", "cửa rộng hơn")
    assert (flow.st["pending_redo"], h_texts(2)) == ({}, ["cửa rộng hơn", "mái cao hơn"])
    flow.work()
    assert (flow.st["state"], flow.st["versions"]["blockout"]) == ("reviewing", 3)


def test_a_stored_redo_is_applied_when_the_stall_ladder_reaches_the_human_rung_k06(flow):
    """The stalled job never reaches an ingest, so the stored text would wait for ever."""
    from core import watch
    stalled_worker_with_pending_redo(flow)
    out = flow.call(watch.stall, Namespace(id=AID, agent_id=None))
    assert out.splitlines()[0].startswith(
        "house-a: kẹt lần 3 (không có nhịp tim, không có file đổi từ ") and (
        "→ áp dụng Cần sửa đang chờ: Cần sửa nhận lúc đang chạy → blockout H1 → blockout/fix" in out.splitlines()[0])
    assert (flow.st["state"], flow.st["versions"]["blockout"], flow.st["pending_redo"]) == ("running", 3, {})
    assert h_texts(2) == ["mái cao hơn"]


def test_retry_applies_a_stored_redo_instead_of_giving_the_stalled_brief_again_k06(flow):
    stalled_worker_with_pending_redo(flow)
    st = flow.st
    st["stalled_from"] = "running"
    loop.move(st, "ask_human")
    loop.offer(st, "blockout", 2, label=loop.UNREVIEWED, note="kẹt")
    save_st(st)
    out = flow.call(loop.retry, Namespace(id=AID))
    assert out.splitlines()[0] == (
        "house-a: retry → áp dụng Cần sửa đang chờ: Cần sửa nhận lúc đang chạy → blockout H1 → blockout/fix. "
        "Tiếp: giao worker → `brief house-a`")
    assert (flow.st["state"], flow.st["versions"]["blockout"], flow.st["pending_redo"]) == ("running", 3, {})


def test_brief_again_while_an_agent_is_out_prints_the_stored_dispatch_and_touches_nothing_c13(flow, monkeypatch):
    """`P brief` is also how a Producer re-sends a job after a lost connection. It rehashed the approved finals, rebuilt the
    sheet, ran the texture gate (a Meshy price dry-run) and rewrote the brief file the agent was reading."""
    for who in ("worker", "reviewer"):
        out = flow.brief()
        brief = flow.root / out["brief"]
        os.utime(brief, (1_000_000, 1_000_000))
        status = flow.root / f"production/assets/{AID}/status.json"
        before = status.read_bytes()

        def boom(*a, **k):
            raise AssertionError("work done again")
        with monkeypatch.context() as m:
            for mod, name in ((hashes, "record_inputs"), (briefs, "sheet_of"), (texture, "gate"), (briefs, "worker_brief"),
                              (briefs, "review_brief")):
                m.setattr(mod, name, boom)
            assert flow.call(briefs.run, Namespace(id=AID)) == json.dumps(out, ensure_ascii=False) + "\n", who
        assert (brief.stat().st_mtime, status.read_bytes()) == (1_000_000, before), who
        if who == "worker":
            flow.work(out=out)


def test_brief_again_does_not_run_the_texture_gate_of_a_running_texture_worker_c13(flow, monkeypatch):
    out = flow.brief()
    st = flow.st
    st |= {"stage": "texture", "versions": {"texture": 1}}
    st["dispatches"][0] |= {"step": "texture", "v": 1}
    save_st(st)
    monkeypatch.setattr(texture, "gate", lambda *a: pytest.fail("the texture gate ran again"))
    assert json.loads(flow.call(briefs.run, Namespace(id=AID))) == out


def test_brief_after_a_retry_builds_again_because_no_agent_is_out_c13(flow, monkeypatch):
    flow.work(status="NEEDS_CONTEXT")
    monkeypatch.setattr(loop, "dispatch_next", lambda *a: None)
    flow.call(loop.retry, Namespace(id=AID))
    sent = json.loads(flow.call(briefs.run, Namespace(id=AID)))
    assert (flow.root / sent["brief"]).is_file() and sent["resume"] == "w1"
    assert flow.call(briefs.run, Namespace(id=AID)) == json.dumps(sent, ensure_ascii=False) + "\n"


def test_the_brief_of_a_new_dispatch_waits_for_a_free_slot_but_the_stored_one_does_not_k04(flow):
    """limits.gate holds a worker in `P next`; `P brief` read no slot at all, so a Producer could run past the cap."""
    p = flow.root / "production/pipeline.toml"
    full = p.read_text(encoding="utf-8")
    p.write_text(full.replace("blender = 2", "blender = 0"), encoding="utf-8")
    assert flow.call(briefs.run, Namespace(id=AID)) == f"{AID}: chờ slot blender, chưa giao\n"
    assert (flow.st["state"], flow.st["versions"], flow.st.get("dispatches")) == ("todo", {}, None)
    p.write_text(full, encoding="utf-8")
    out = flow.brief()
    p.write_text(full.replace("blender = 2", "blender = 0"), encoding="utf-8")
    assert json.loads(flow.call(briefs.run, Namespace(id=AID))) == out


def test_an_ingest_whose_next_worker_waits_for_a_slot_says_so_in_the_words_of_p_brief(flow):
    """The ingest printed "Tiếp: giao worker" and nothing else, so the Producer ran `brief` to dispatch a held worker."""
    flow.work()
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("blender = 2", "blender = 0"), encoding="utf-8")
    out = flow.review(counts=counts(major=1), findings=[finding("F1", "major", "structure")])
    assert out.splitlines()[1:] == [f"{AID}: chờ slot blender, chưa giao"]
    assert flow.st["state"] == "fix"


def test_a_fix_dispatch_takes_its_deadline_from_the_median_of_fix_rounds_not_of_every_round_k04(flow, held):
    """The first build took 10 minutes. No fix round has run, so a fix round gets the step's usual 40 minutes, twice for
    the factor. The pooled median would give it 20."""
    import datetime as dt
    flow.work()
    st = flow.st
    st["dispatches"][0]["duration_ms"] = 600_000
    save_st(st)
    flow.review(counts=counts(major=1), findings=[finding("F1", "major", "structure")])
    flow.brief()
    rec = flow.st["dispatches"][-1]
    assert (rec["role"], rec["v"]) == ("worker", 2)
    assert dt.datetime.fromisoformat(rec["deadline"]) - dt.datetime.fromisoformat(rec["at"]) == dt.timedelta(minutes=80)


def test_a_retry_after_a_missing_output_resumes_the_same_worker_and_names_the_file_l16(flow):
    """Run 5: a worker that forgot one file was replaced by a fresh agent that rebuilt the whole step."""
    out = flow.brief()
    flow.work(out=out, skip=["blockout.md"])
    assert (flow.st["state"], flow.st["note"]) == ("blocked", "thiếu output bắt buộc: final/blockout.md")
    head, line = flow.call(loop.retry, Namespace(id=AID)).splitlines()
    sent = json.loads(line)
    assert (sent["resume"], sent["report"], flow.st["versions"]) == ("w1", out["report"], {"blockout": 1})
    text = flow.text(sent)
    assert "## Lần giao trước" in text and "dừng ở: thiếu output: final/blockout.md." in text.replace("\n", " ")
    assert "Bản gốc:" not in text and "Giữ phần đã làm trong thư mục version" in text


def test_a_retry_after_needs_context_resumes_the_same_worker_with_its_note_l16(flow):
    flow.work(status="NEEDS_CONTEXT", extra="ISSUES: thiếu file layout\n")
    sent = json.loads(flow.call(loop.retry, Namespace(id=AID)).splitlines()[-1])
    assert sent["resume"] == "w1"
    assert "dừng ở: NEEDS_CONTEXT: thiếu file layout." in flow.text(sent)


def test_a_new_agent_on_a_retried_version_is_never_told_it_is_the_session_that_stopped(flow):
    """The stall rung gives the same version to a new agent (resume null); "Bạn là phiên đó, làm tiếp" told it to trust
    a session it never was."""
    flow.work(skip=["blockout.md"])
    flow.call(loop.retry, Namespace(id=AID))
    st = flow.st
    st["dispatches"][-1]["ended"] = {"at": "2026-11-12 10:00:00", "why": "kẹt"}
    st["worker_agent_id"] = None
    save_st(st)
    again = flow.brief()
    assert again["resume"] is None and "## Lần giao trước" not in flow.text(again)


def test_the_first_ingest_after_a_retry_drops_the_reason_so_a_later_brief_has_no_stale_section_l16(flow):
    flow.work(status="NEEDS_CONTEXT")
    flow.call(loop.retry, Namespace(id=AID))
    flow.work()
    assert flow.st["retry_why"] is None


def enable_views(f):
    p = f.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views"\nenabled = false', 'id = "views"'),
                 encoding="utf-8")


def test_an_ingest_that_approves_by_policy_prints_the_dispatch_of_the_next_step_c16(flow):
    enable_views(flow)
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    flow.work()
    head, line = flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass").splitlines()
    assert head == "house-a: review PASS (0 mở) → views/todo. Tiếp: giao worker → `brief house-a`"
    sent = json.loads(line)
    assert (sent["role"], sent["agent"]) == ("worker", "zps-3dp-step-views")


def test_an_ingest_that_approves_by_policy_prints_no_dispatch_while_the_next_step_has_no_free_slot_c16(flow):
    enable_views(flow)
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    flow.work()
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("blender = 2", "blender = 0"), encoding="utf-8")
    out = flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass")
    assert "views/todo" in out.splitlines()[0] and out.splitlines()[1:] == [f"{AID}: chờ slot blender, chưa giao"]


def tools_without_venv(tmp_path, venv=False):
    skill = tmp_path / "skill"
    tools = skill / "agents/zps-3dp-step-blockout/tools"
    tools.mkdir(parents=True)
    if venv:
        (tools / ".deps/venv/bin").mkdir(parents=True)
        (tools / ".deps/venv/bin/python").write_text("", encoding="utf-8")
    return skill


def test_ingest_says_in_one_line_that_it_did_not_recheck_when_the_tools_venv_is_missing_and_goes_on_l15(
        flow, monkeypatch, tmp_path):
    """A fresh project where no worker ran setup_deps: run_tool.py would install the venv inside the ingest. The ingest
    names the gap on stderr and in the ledger and ends as before; it never crashes."""
    monkeypatch.setattr(loop, "recheck", REAL_RECHECK)
    monkeypatch.setattr(loop, "SKILL_DIR", tools_without_venv(tmp_path))
    out = flow.work()
    assert json.loads(out.splitlines()[-1])["role"] == "reviewer"
    assert flow.err.count("\n") == 1 and "thiếu venv của tool" in flow.err and "setup_deps.sh" in flow.err
    assert "house-a · blockout v1 · ingest không kiểm lại gate_all.py được: thiếu venv của tool" in flow.ledger()


def test_a_recheck_that_dies_without_a_result_json_sends_the_worker_back_with_its_log_l15(flow, monkeypatch, tmp_path):
    """gate_all.py exits 1 with no failing JSON when the build dies. failed_checks reads JSON only, so without the log
    path of that run the check that did not finish would count as a pass."""
    log = f"production/assets/{AID}/blockout/v1/work/logs/gate_all.log"
    ran = []

    def fake_run(cmd, **kw):
        ran.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout=f"gate_all error {log}\n", stderr="")
    monkeypatch.setattr(loop, "recheck", REAL_RECHECK)
    monkeypatch.setattr(loop, "SKILL_DIR", tools_without_venv(tmp_path, venv=True))
    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    head = flow.work().splitlines()[0]
    assert head == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert flow.st["note"] == "vòng trả thẳng 1/2: check fail gate_all.log"
    assert [Path(x).name for x in ran[0] if x.endswith(".py")] == ["run_tool.py", "gate_all.py"]
    assert ran[0][ran[0].index("--version-dir") + 1] == f"production/assets/{AID}/blockout/v1"
    assert "--skip" in ran[0] and "check_inputs" in ran[0]


def test_a_recheck_the_runner_refuses_is_one_line_and_not_a_failure_l15(flow, monkeypatch, tmp_path):
    monkeypatch.setattr(loop, "recheck", REAL_RECHECK)
    monkeypatch.setattr(loop, "SKILL_DIR", tools_without_venv(tmp_path, venv=True))
    monkeypatch.setattr(loop.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 2, stdout="", stderr="run_tool: refused gate_all.py: not a .py file\n"))
    out = flow.work()
    assert json.loads(out.splitlines()[-1])["role"] == "reviewer"
    assert flow.err.strip() == f"{AID}: ingest không kiểm lại gate_all.py được: run_tool: refused gate_all.py: not a .py file"


def models(f, step: dict, fallback="haiku"):
    """Rewrites pipeline.toml: blockout gets the keys in `step`, `[review] reviewer_model` the fallback, and no step keeps
    another value of those keys, so each value in the test names one source."""
    p = f.root / "production/pipeline.toml"
    text = p.read_text(encoding="utf-8")
    for k in {"reviewer_model", *step}:
        text = re.sub(rf'^{k} = .*\n', "", text, flags=re.M)
    text = text.replace("[review]\n", f'[review]\nreviewer_model = "{fallback}"\n', 1)
    keys = "".join(f'{k} = {json.dumps(v)}\n' for k, v in step.items())
    p.write_text(text.replace('id = "blockout"\n', f'id = "blockout"\n{keys}', 1), encoding="utf-8")


@pytest.mark.parametrize("step, want", [({"reviewer_model": "sonnet"}, "sonnet"), ({}, "haiku")])
def test_the_reviewer_takes_the_model_of_its_step_and_the_review_section_only_as_fallback_q9_a1(flow, step, want):
    """D45: the owner lowers the reviewer of one step after a pilot; one key for all steps would lower every reviewer."""
    models(flow, step)
    out = json.loads(flow.work().splitlines()[-1])
    assert (out["role"], out["model"], flow.st["dispatches"][-1]["model"]) == ("reviewer", want, want)
    assert f"giao reviewer (zps-3dp-check-blockout, {want})" in flow.ledger()


def test_a_worker_after_the_resume_rounds_takes_the_escalate_model_of_its_step_a1(flow):
    models(flow, {"model": "sonnet", "escalate_model": "opus"})
    p = flow.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("resume_rounds = 2", "resume_rounds = 0"), encoding="utf-8")
    first = flow.brief()
    flow.work(out=first)
    line = flow.review(counts=counts(major=1), findings=[finding("F1", "major", "structure")]).splitlines()[-1]
    out = json.loads(line)
    assert (first["model"], out["role"], out["model"], out["resume"]) == ("sonnet", "worker", "opus", None)


@pytest.mark.parametrize("key", ["model", "escalate_model", "reviewer_model"])
def test_a_model_name_outside_opus_sonnet_haiku_is_refused_when_the_pipeline_loads_a1(flow, key):
    """A typo would reach the Agent tool as a model name and fail there, after the brief was built."""
    models(flow, {key: "sonet"})
    with pytest.raises(ProducerError) as e:
        load_cfg()
    assert str(e.value) == f"step blockout: {key} = 'sonet' phải là opus | sonnet | haiku"


def test_a_fallback_reviewer_model_outside_the_names_is_refused_too_a1(flow):
    models(flow, {}, fallback="gpt")
    with pytest.raises(ProducerError) as e:
        load_cfg()
    assert str(e.value) == "pipeline.toml [review] reviewer_model = 'gpt' phải là opus | sonnet | haiku"


def rounds(f):
    return [(x["role"], x["v"], x.get("scope")) for x in f.st["dispatches"]]


def test_a_fix_round_that_leaves_a_minor_finding_open_costs_two_reviewers_not_three_q3(flow):
    """The fix brief names only the TOP_FIX ids, so a real worker leaves the minor finding out of FIXED. Run 5 paid a third
    reviewer for each such round: a `fix` review, then a `full` one on the same version."""
    flow.work()
    flow.review(findings=[finding("F1", "major", "structure"), finding("F2", "minor", "param")])
    flow.work(fixed="F1")
    assert flow.review(verdict="PASS", top_fix=None, rubric="massing=pass", compare="F1=better",
                       prior=["- F1: resolved | evidence: clay_front", "- F2: open | evidence: clay_front"]) == (
        "house-a: review PASS (minor=1) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")
    assert rounds(flow) == [("worker", 1, None), ("reviewer", 1, "full"), ("worker", 2, None), ("reviewer", 2, "full")]


def test_a_pass_in_a_fix_round_that_judged_every_rubric_key_is_final_without_another_reviewer_q3(flow):
    """A `fix` review that wrote no `not_checked` judged every key: a `full` review of the same version adds nothing."""
    fix_v1(flow, 1)
    flow.work()
    assert flow.review(verdict="PASS", top_fix=None, rubric="massing=pass; props=pass", compare="F1=better",
                       prior=["- F1: resolved | evidence: clay_front"]) == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")
    assert rounds(flow) == [("worker", 1, None), ("reviewer", 1, "full"), ("worker", 2, None), ("reviewer", 2, "fix")]


def test_two_structure_findings_on_different_parts_are_fixed_and_judged_in_one_round_w8(flow):
    flow.work()
    out = json.loads(flow.review(top_fix="structure: F1, F2", findings=[
        finding("F1", "major", "structure", region="roof: mái thấp"),
        finding("F2", "major", "structure", region="door: thiếu cửa")]).splitlines()[-1])
    assert "Sửa đúng `TOP_FIX: structure: F1, F2`; repair" in flow.text(out)
    flow.work(out=out, fixed="F1, F2")
    assert flow.review(verdict="PASS", top_fix=None, rubric="massing=pass", compare="F1=better; F2=better",
                       prior=["- F1: resolved | evidence: clay_front", "- F2: resolved | evidence: clay_front"]) == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v2 (review page)\n")


def game_cam(f, n=1):
    from PIL import Image
    p = f.v(n) / "final/review/game_cam.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), (90, 60, 30)).save(p)


def asks_crop(f, agent_id="r1"):
    """The v1 reviewer asks for a crop of a sheet tile; the script serves it from disk."""
    out = f.brief()
    game_cam(f)
    f.work(out=out)
    return f.review(agent_id=agent_id, rubric="props=unclear", top_fix="need_evidence", evidence="game_cam",
                    findings=[finding("F1", "unclear", "param", evidence="game_cam: mờ",
                                      viewing_condition="xin ảnh game_cam box 0,0,0.5,0.5")])


def test_a_crop_served_from_disk_goes_back_to_the_reviewer_that_asked_with_a_short_brief_q4(flow):
    """Run 5: a new reviewer re-read the concept, the sheet, the base and the rubric to judge one crop."""
    from core.contract import FALLBACK
    out = json.loads(asks_crop(flow).splitlines()[-1])
    v1 = f"production/assets/{AID}/blockout/v1"
    assert (out["role"], out["resume"], out["brief"], out["report"]) == (
        "reviewer", "r1", f"{v1}/review/evidence-1/brief-review.md", f"{v1}/review-out.md")
    assert flow.text(out).splitlines() == [
        "# Review brief — House A · bước `blockout` · v1 · tiếp", "", "REVIEW_SCOPE: full", "",
        f"Ảnh bạn xin đã có: `{v1}/review/evidence-1/game_cam-crop1.png`.",
        f"Chấm lại v1 với ảnh này. Report cùng format như lần trước, ghi vào `{v1}/review-out.md`.",
        "- PRIOR: mọi id đang mở F1, kể cả id bạn vừa ghi. Không ghi COMPARE.",
        "- FINDINGS: chỉ finding mới, id từ F2, hoặc `FINDINGS: none`.",
        "- EVIDENCE_OPENED: thêm tên ảnh mới.",
        "", f"Tin nhắn trả về cho Producer: chỉ dòng VERDICT. {FALLBACK}"]
    assert flow.review(out=out, agent_id="r1", verdict="PASS", top_fix=None, rubric="props=pass",
                       evidence="game_cam, game_cam-crop1", prior=["- F1: resolved | evidence: game_cam-crop1"]) == (
        "house-a: review PASS (0 mở) → blockout/waiting_human. Tiếp: chờ người dùng: duyệt blockout v1 (review page)\n")
    assert rounds(flow) == [("worker", 1, None), ("reviewer", 1, "full"), ("reviewer", 1, "full")]
    assert [x.get("evidence") for x in flow.st["dispatches"]] == [None, None, 1]


def test_the_report_of_a_resumed_reviewer_is_seen_by_every_watcher_so_a_finished_review_is_never_redone(flow):
    """The resumed brief sits in review/evidence-k/ while the report goes to vN/review-out.md. A report path derived from
    the brief never exists: `P wait` slept, the Stop hook let the turn end, on-stop said no_report, and the stall
    ladder set the finished report aside for a new reviewer."""
    from core import watch
    out = json.loads(asks_crop(flow).splitlines()[-1])
    rep = flow.root / out["report"]
    rep.write_text(judged_all(rep, report(verdict="PASS", top_fix=None, rubric="props=pass", evidence="game_cam, game_cam-crop1",
                                          prior=["- F1: resolved | evidence: game_cam-crop1"])), encoding="utf-8")
    st = flow.st
    rec = watch.job(st)
    assert str(watch.report_of(rec)) == out["report"]
    assert watch.wake(policy.watch(policy.load()))[0] == f"{AID}: có báo cáo {out['report']} → `ingest {AID}`"
    assert watch.main_stop_reason([st], Path.exists, lambda s, r: True) == (
        f"Còn report chưa ingest: chạy `P ingest {AID} --agent-id <id subagent>`")
    rec["agent_id"] = "r1"
    save_st(st)
    watch.on_stop(json.dumps({"agent_type": "zps-3dp-check-blockout", "agent_id": "r1"}))
    assert watch.job(flow.st)["stopped"] == "report"
    assert watch.check(flow.st, watch.job(flow.st), policy.watch(policy.load()))["stalled"] is False
    old = {"step": "blockout", "v": 1, "role": "worker", "brief": f"production/assets/{AID}/blockout/v1/brief-worker.md"}
    assert str(watch.report_of(old)) == f"production/assets/{AID}/blockout/v1/worker-out.md"


def test_without_the_agent_id_of_the_reviewer_a_served_crop_goes_to_a_new_reviewer_with_the_full_brief_q4(flow):
    out = json.loads(asks_crop(flow, agent_id=None).splitlines()[-1])
    assert (out["resume"], out["brief"]) == (None, f"production/assets/{AID}/blockout/v1/brief-review.md")


def test_a_resumed_reviewer_that_stalls_is_replaced_by_a_new_one_with_the_full_brief_q4(flow):
    """The stall rung gives the same work to a new agent; that agent has no first brief to go back to."""
    sent = json.loads(asks_crop(flow).splitlines()[-1])
    assert sent["resume"] == "r1"
    assert json.loads(flow.call(briefs.run, Namespace(id=AID))) == sent
    st = flow.st
    st["dispatches"][-1]["ended"] = {"at": "2026-11-12 10:00:00", "why": "no_report"}
    save_st(st)
    again = flow.brief()
    assert (again["resume"], again["brief"]) == (None, f"production/assets/{AID}/blockout/v1/brief-review.md")


def test_the_review_of_a_new_version_never_resumes_the_reviewer_that_asked_for_a_crop_of_the_old_one_q4(flow, held):
    """A reviewer anchored on its own findings of v1 would judge v2 against them, not against the concept. The crop is
    served but not yet sent when the user asks for a redo."""
    asks_crop(flow)
    assert flow.st["evidence"]["agent_id"] == "r1"
    flow.human("redo", "mái cao hơn")
    flow.work()
    out = flow.brief()
    assert (out["role"], out["resume"], out["brief"]) == (
        "reviewer", None, f"production/assets/{AID}/blockout/v2/brief-review.md")
