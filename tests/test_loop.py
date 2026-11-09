import json
import re
from argparse import Namespace
from pathlib import Path

import pytest

from shared import SCRIPTS, blockout_only, brief_hash, finding, report, write_profile
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

    def work(self, status="DONE", out=None):
        out = out or self.brief()
        rep = self.root / out["report"]
        if rep.parent.name.startswith("v"):
            for o in OUTPUTS:
                (rep.parent / "final" / o).write_text("x", encoding="utf-8")
        rep.write_text(f"STATUS: {status}\nPROFILE_HASH: {brief_hash(self.text(out))}\n", encoding="utf-8")
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
    assert fix_v1(flow, 4) == "house-a: review FIX (major=4) → blockout/fix. Tiếp: giao worker → `brief house-a`\n"
    assert pick(flow.st) | {"note": None} == {"state": "fix", "fix_round": 1, "fix_base": 1, "offer": None,
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
    assert pick(flow.st)["state"] == "fix"
    assert flow.st["fix_base"] == 1
    out = flow.brief()
    assert f"Bản gốc: `production/assets/{AID}/blockout/v1/`" in flow.text(out)
    flow.work(out=out)
    rb = flow.text(flow.brief())
    assert ("COMPARE: F1=?\n" in rb, f"Bản gốc v1: ảnh cùng góc `production/assets/{AID}/blockout/v1/final/`" in rb) == (
        True, True)
    assert flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same",
                       prior=["- F1: open", "- F2: open"]).endswith(
        "chờ người dùng: không tiến bộ ở vòng 2; còn mở: F1, F2 (review page)\n")
    assert pick(flow.st) == {"state": "waiting_human", "fix_round": 2, "fix_base": 1, "offer": 1, "label": "chưa đạt",
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
    assert (flow.st["offer"], flow.st["offer_key"]) == (1, "house-a-blockout-v1-2")


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
        "worker", "w1", f"{ev}/brief-worker.md", f"{ev}/report-worker.md")
    assert "Không sửa `production/assets/house-a/blockout/v1/final/`" in flow.text(out)
    assert flow.work(out=out) == "house-a: evidence-1 DONE → blockout/review. Tiếp: giao reviewer → `brief house-a`\n"
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
    fix_v1(flow, 2)
    for _ in range(2):
        flow.work()
        flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same", prior=["- F1: open", "- F2: open"])
    assert flow.st["state"] == "waiting_human"
    flow.human("redo", "mái cao hơn")
    st = flow.st
    assert {k: st[k] for k in ("state", "fix_round", "fix_base", "round_versions", "offer", "label")} == {
        "state": "fix", "fix_round": 1, "fix_base": 1, "round_versions": [1], "offer": None, "label": ""}
    out = flow.brief()
    assert out["report"] == f"production/assets/{AID}/blockout/v4/report-worker.md"
    assert f"Bản gốc: `production/assets/{AID}/blockout/v1/`" in flow.text(out)
    flow.work(out=out)
    rb = flow.text(flow.brief())
    assert [l for l in rb.splitlines() if l.startswith("- F") and ": ? |" in l] == [
        "- F1: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front",
        "- F2: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front"]


def pass_v2(f):
    fix_v1(f, 1)
    f.work()
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
    assert flow.call(loop.retry, Namespace(id=AID)) == "house-a: → todo. Tiếp: giao worker → `brief house-a`\n"
    assert {k: flow.st[k] for k in ("stage", "state", "approved")} == {"stage": "views_front", "state": "todo",
                                                                     "approved": {"blockout": 2}}


def test_approving_the_offered_best_version_rejects_the_newer_versions(flow):
    fix_v1(flow, 2)
    for _ in range(2):
        flow.work()
        flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same", prior=["- F1: open", "- F2: open"])
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
    assert flow.brief()["report"] == f"production/assets/{AID}/blockout/v3/report-worker.md"


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
    flow.work()
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
    flow.work()
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


def test_redo_of_an_unreviewed_version_files_the_user_text_as_H1_so_the_next_review_has_a_base(flow):
    flow.work()
    assert flow.st["state"] == "review"
    assert flow.human("redo", "mái cao hơn") == "house-a: làm lại blockout từ v1. Tiếp: giao worker → `brief house-a`"
    assert findings.load(AID, "blockout", 1)["findings"] == {"H1": H1}
    assert (flow.st["fix_base"], flow.st["round_versions"]) == (1, [1])
    flow.work()
    rb = flow.text(flow.brief())
    assert "- H1: ? | evidence: ? | acceptance: đạt yêu cầu của người dùng: mái cao hơn" in rb
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
        flow.review(counts=counts(major=1), top_fix="structure: H1", rubric="mass=fail", compare="H1=same",
                    prior=["- H1: open"])
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
    fix_v1(flow, 2)
    for _ in range(2):
        flow.work()
        flow.review(counts=counts(major=2), top_fix="structure: F1", compare="F1=same", prior=["- F1: open", "- F2: open"])
    assert (flow.st["offer"], flow.st["versions"]) == (1, {"blockout": 3})
    flow.human("note", "mái chìa thêm")
    log = (flow.root / f"production/assets/{AID}/feedback.md").read_text(encoding="utf-8")
    assert log.splitlines()[-1].endswith(" · blockout v1 · note · mái chìa thêm")


def test_retry_sets_the_old_report_aside_so_ingest_waits_for_the_new_one(flow):
    flow.work(status="NEEDS_CONTEXT")
    assert flow.call(loop.retry, Namespace(id=AID)) == (
        "house-a: → running. Tiếp: đang chờ subagent (mất kết nối thì `brief house-a` để giao lại)\n")
    assert (flow.v(1) / "report-worker-1.md").read_text(encoding="utf-8").startswith("STATUS: NEEDS_CONTEXT")
    with pytest.raises(ProducerError) as e:
        loop.ingest(Namespace(id=AID, agent_id=None))
    assert str(e.value) == f"chưa có báo cáo production/assets/{AID}/blockout/v1/report-worker.md"


def test_a_redispatch_sets_the_old_review_aside_so_the_evidence_rereview_is_not_read_from_the_first(flow):
    need_evidence_v1(flow)
    flow.work()
    flow.brief()
    assert loop.next_action(flow.st) == "đang chờ subagent (mất kết nối thì `brief house-a` để giao lại)"
    assert (flow.v(1) / "report-review-1.md").read_text(encoding="utf-8").startswith("VERDICT: FIX")


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


def test_a_redo_stays_in_the_current_section_the_worker_reads_until_the_step_is_approved_by_its_reviewer(flow):
    """Run 4: redo text went only to the Log, so the texture worker and reviewers read an empty "Hiện hành"."""
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="để reviewer duyệt", confirm_spend=False))
    flow.cap.readouterr()
    fb = flow.root / f"production/assets/{AID}/feedback.md"
    fb.write_text(fb.read_text(encoding="utf-8").replace("## Log", "- giữ mái ngói đỏ (Producer gộp)\n\n## Log"),
                  encoding="utf-8")
    fix_v1(flow, 1)
    flow.human("redo", "mái cao hơn\nmái đỏ")
    flow.human("note", "chỉ là ghi chú")
    assert current(flow) == ["- giữ mái ngói đỏ (Producer gộp)", "- blockout v1 · redo · mái cao hơn mái đỏ"]
    flow.work()
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="F1=better; H1=better",
                prior=["- F1: resolved | evidence: clay_front", "- H1: resolved | evidence: clay_front"])
    assert (flow.st["approved"], current(flow)) == ({"blockout": 2}, ["- giữ mái ngói đỏ (Producer gộp)"])


def test_a_reviewer_reply_saved_whole_with_its_report_markers_ingests_like_the_bare_report(flow):
    """Run 4: every reviewer returned its report as text, and the Producer saved the reply as report-review.md."""
    flow.work()
    out = flow.brief()
    body = report(counts=counts(major=1), findings=[finding("F1", "major")])
    (flow.root / out["report"]).write_text(f"Đã chấm v1.\n--- report ---\n{body}--- end ---\n", encoding="utf-8")
    assert flow.call(loop.ingest, Namespace(id=AID, agent_id=None)).startswith(
        "house-a: review FIX (major=1) → blockout/fix.")


def test_the_review_brief_asks_for_a_report_file_with_text_only_as_fallback_and_states_the_label_rule(flow):
    """D27.5: a report saved by the Producer passes through its context, so the reviewer writes the file and replies
    with two lines (D22.6). Run 4: ingest refused a PRIOR whose evidence named `unlit_close_front (lock crop)` for the
    label `v2 unlit_close_front`."""
    flow.work()
    text = flow.text(flow.brief())
    assert [l for l in text.splitlines() if "report-review" in l or "--- report" in l or "nguyên văn" in l or "Tin nhắn" in l] == [
        f"Ghi report vào `production/assets/{AID}/blockout/v1/report-review.md`. Report mở đầu đúng format, mỗi khóa "
        "một dòng:",
        "- EVIDENCE_OPENED: các nhãn cách nhau bằng dấu phẩy; nhãn không chứa dấu phẩy hay chấm phẩy. `evidence` của "
        "finding mới và của PRIOR resolved chép nguyên văn ít nhất một nhãn đó.",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT và dòng COUNTS. Lệnh ghi file bị chặn: trả cả report giữa "
        "dòng `--- report ---` và dòng `--- end ---`."]
    assert "mức `minor`" not in text


def test_a_report_the_producer_saved_from_a_reply_is_ingested_and_logged_as_a_fallback_by_role_d27_5(flow):
    """The fallback must stay rare, so every one is counted: in the ledger and on the dispatch (`P stats`)."""
    flow.work()
    out = flow.brief()
    body = report(counts=counts(major=1), findings=[finding("F1", "major")])
    (flow.root / out["report"]).write_text(f"--- report ---\n{body}--- end ---\n", encoding="utf-8")
    flow.call(loop.ingest, Namespace(id=AID, agent_id=None, fallback=True))
    assert [x.get("fallback", False) for x in flow.st["dispatches"]] == [False, True]
    assert [l.split(" · ", 2)[2] for l in flow.ledger().splitlines() if "report_fallback" in l] == [
        "house-a · blockout v1 · report_fallback · reviewer"]
