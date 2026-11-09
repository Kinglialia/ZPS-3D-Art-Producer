import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts"))

from core.contract import parse_review  # noqa: E402
from core.findings import apply, best_version, progress  # noqa: E402
from test_contract import finding, report  # noqa: E402
from shared import brief_hash, write_profile  # noqa: E402

P = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts" / "producer.py"
STEP = {"id": "blockout", "top_fix": ["structure", "param"]}
ZERO = {"blocker": 0, "major": 0, "minor": 0, "preference": 0, "unclear": 0}


def counts(**kw):
    return "; ".join(f"{k}={v}" for k, v in (ZERO | kw).items())


def rv(**kw):
    r, errs = parse_review(report(**kw))
    assert errs == []
    return r


def errs_of(base, n=1, step=STEP, **kw):
    return apply(base, rv(**kw), step, n)[1]


def v1():
    doc, errs = apply(None, rv(counts=counts(major=2, minor=1), top_fix="structure: F1", findings=[
        finding("F1", "major", "structure"), finding("F2", "major", "param"), finding("F3", "minor", "param")]), STEP, 1)
    assert errs == []
    return doc


def brief_view(doc):
    return {i: (f["priority"], f["kind"], f["status"], f["first_v"], f["last_v"]) for i, f in doc["findings"].items()}


def test_first_review_numbers_findings_from_f1_and_records_the_version_they_appeared():
    doc = v1()
    assert {k: doc[k] for k in ("version", "base", "top_fix", "pick", "next_id")} == {
        "version": 1, "base": None, "top_fix": {"kind": "structure", "ids": ["F1"]}, "pick": None, "next_id": 4}
    assert brief_view(doc) == {"F1": ("major", "structure", "open", 1, 1), "F2": ("major", "param", "open", 1, 1),
                               "F3": ("minor", "param", "open", 1, 1)}
    assert set(doc["findings"]["F1"]) == {"priority", "kind", "status", "first_v", "last_v", "region",
                                          "viewing_condition", "evidence", "consequence", "confidence", "repair",
                                          "preserve", "acceptance"}


def test_ids_stay_fixed_across_rounds_and_new_findings_take_the_next_free_id():
    doc, errs = apply(v1(), rv(counts=counts(major=1, minor=2), top_fix="param: F2, F3, F4", compare="F1=better",
                               prior=["- F1: resolved | evidence: clay_front", "- F2: open", "- F3: open"],
                               findings=[finding("F4", "minor", "param")]), STEP, 2)
    assert errs == []
    assert (doc["base"], doc["next_id"]) == (1, 5)
    assert brief_view(doc) == {"F1": ("major", "structure", "resolved", 1, 2), "F2": ("major", "param", "open", 1, 2),
                               "F3": ("minor", "param", "open", 1, 2), "F4": ("minor", "param", "open", 2, 2)}


def test_new_finding_reusing_an_old_id_is_rejected_because_ids_must_mean_one_thing():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), compare="F1=same",
                   prior=["- F1: open", "- F2: open", "- F3: open"], findings=[finding("F2", "major", "structure")]) == [
        "F2 đã có; finding cũ ghi ở PRIOR"]


def test_prior_must_cover_every_open_finding_so_no_old_problem_is_silently_dropped():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), compare="F1=same",
                   prior=["- F1: open", "- F2: open"]) == ["PRIOR thiếu F3"]


def test_prior_for_a_closed_or_unknown_finding_is_rejected():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), compare="F1=same",
                   prior=["- F1: open", "- F2: open", "- F3: open", "- F7: open"]) == ["PRIOR có id không đang mở: F7"]


def test_compare_is_required_for_every_finding_of_the_previous_top_fix():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), prior=["- F1: open", "- F2: open", "- F3: open"]) == [
        "COMPARE thiếu F1"]


def test_resolved_needs_compare_better_because_side_by_side_is_the_stable_judgment():
    assert errs_of(v1(), 2, counts=counts(major=1, minor=1), top_fix="param: F2, F3", compare="F1=same",
                   prior=["- F1: resolved | evidence: clay_front", "- F2: open", "- F3: open"]) == [
        "F1: resolved cần COMPARE better"]


def test_compare_worse_means_prior_regressed():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), compare="F1=worse",
                   prior=["- F1: open", "- F2: open", "- F3: open"]) == ["F1: COMPARE worse thì PRIOR phải là regressed"]


def test_structure_top_fix_takes_exactly_one_id_so_each_structural_change_is_isolated():
    assert errs_of(None, counts=counts(major=2), top_fix="structure: F1, F2", findings=[
        finding("F1", "major", "structure"), finding("F2", "major", "structure")]) == [
        "TOP_FIX structure: đúng một id trong F1, F2"]


def test_param_top_fix_lists_every_open_param_finding_so_one_round_fixes_the_batch():
    assert errs_of(None, counts=counts(major=1, minor=1), top_fix="param: F1", findings=[
        finding("F1", "major", "param"), finding("F2", "minor", "param")]) == ["TOP_FIX param: phải đủ F1, F2"]


def test_param_batch_skips_preference_and_unclear_findings():
    assert errs_of(None, counts=counts(major=1, preference=1, unclear=1), rubric="massing=fail; props=unclear",
                   top_fix="param: F1", findings=[finding("F1", "major", "param"), finding("F2", "preference", "param"),
                                                  finding("F3", "unclear", "param")]) == []


def test_top_fix_kind_not_declared_for_the_step_is_rejected():
    assert errs_of(None, top_fix="repaint: F1", findings=[finding("F1", "major", "repaint")]) == [
        "F1: loại 'repaint' không có ở bước blockout (structure|param)",
        "TOP_FIX 'repaint' không dùng ở bước blockout (structure|param|need_evidence)"]


def test_structure_wins_a_tie_with_param_because_a_structural_fix_can_void_the_param_finding():
    assert errs_of(None, counts=counts(major=2), top_fix="param: F2", findings=[
        finding("F1", "major", "structure"), finding("F2", "major", "param")]) == ["TOP_FIX phải là loại structure"]


def test_heavier_param_finding_goes_before_structure():
    assert errs_of(None, counts=counts(blocker=1, major=1), top_fix="param: F2", findings=[
        finding("F1", "major", "structure"), finding("F2", "blocker", "param")]) == []


def test_preference_never_blocks_pass():
    assert errs_of(None, verdict="PASS", top_fix=None, counts=counts(minor=1, preference=1), rubric="massing=pass",
                   findings=[finding("F1", "preference", "param"), finding("F2", "minor", "param")]) == []


def test_pass_with_an_open_major_is_rejected():
    assert errs_of(None, verdict="PASS", top_fix=None, findings=[finding("F1", "major", "param")]) == [
        "PASS nhưng còn major=1 đang mở"]


def test_only_unclear_left_needs_need_evidence_not_a_fix():
    kw = dict(counts=counts(unclear=1), rubric="props=unclear", findings=[finding("F1", "unclear", "param")])
    assert errs_of(None, top_fix="param: F1", **kw) == ["chỉ còn unclear: TOP_FIX phải là need_evidence"]
    assert errs_of(None, top_fix="need_evidence: F1", **kw) == []


def test_need_evidence_is_refused_while_blocker_or_major_is_open():
    assert errs_of(None, counts=counts(major=1, unclear=1), rubric="props=unclear", top_fix="need_evidence: F2",
                   findings=[finding("F1", "major", "param"), finding("F2", "unclear", "param")]) == [
        "need_evidence chỉ dùng khi không còn blocker/major", "TOP_FIX phải là loại param"]


def test_each_unclear_rubric_key_needs_an_unclear_finding():
    assert errs_of(None, rubric="massing=fail; props=unclear", findings=[finding("F1", "major", "structure")]) == [
        "RUBRIC có 1 key unclear nhưng chỉ 0 finding unclear đang mở"]


def test_counts_must_match_open_findings_because_producer_reports_them_unchecked():
    assert errs_of(None, counts=counts(major=2), findings=[finding("F1", "major", "structure")]) == [
        "COUNTS phải là blocker=0; major=1; minor=0; preference=0; unclear=0"]


def test_pick_is_only_valid_after_a_param_round():
    assert errs_of(v1(), 2, counts=counts(major=2, minor=1), compare="F1=same", pick="b",
                   prior=["- F1: open", "- F2: open", "- F3: open"]) == ["PICK chỉ dùng khi TOP_FIX vòng trước là param"]


def doc_of(n, **status_prio):
    return {"version": n, "findings": {i: {"status": s, "priority": p} for i, (s, p) in status_prio.items()}}


def test_progress_needs_an_old_blocker_or_major_resolved_and_fewer_regressed_than_resolved():
    base = doc_of(1, F1=("open", "major"), F2=("open", "minor"), F3=("open", "minor"))
    assert progress(base, doc_of(2, F1=("resolved", "major"), F2=("open", "minor"), F3=("open", "minor"))) is True
    assert progress(base, doc_of(2, F1=("open", "major"), F2=("resolved", "minor"), F3=("open", "minor"))) is False
    assert progress(base, doc_of(2, F1=("resolved", "major"), F2=("regressed", "minor"), F3=("open", "minor"))) is False
    assert progress(base, doc_of(2, F1=("resolved", "major"), F2=("regressed", "minor"),
                                 F3=("resolved", "minor"))) is True


def test_new_findings_do_not_count_as_regression():
    base = doc_of(1, F1=("open", "major"))
    assert progress(base, doc_of(2, F1=("resolved", "major"), F2=("open", "blocker"))) is True


def test_superseded_closes_a_finding_but_is_not_progress():
    base = doc_of(1, F1=("open", "major"))
    assert progress(base, doc_of(2, F1=("superseded", "major"))) is False


def test_best_version_has_fewest_open_blocker_major_and_ties_go_to_the_older_version():
    docs = [doc_of(1, F1=("open", "major"), F2=("open", "major")),
            doc_of(2, F1=("resolved", "major"), F2=("open", "major"), F3=("open", "minor"), F4=("open", "preference")),
            doc_of(3, F1=("resolved", "major"), F2=("regressed", "major"))]
    assert best_version(docs) == 2
    assert best_version([]) is None



def test_best_version_prefers_the_version_that_resolved_a_major_when_open_counts_tie():
    # Run 4: v2 fixed F1 and the reviewer then saw F2; the fix brief must start from v2, not rebuild v1.
    v1 = doc_of(1, F1=("open", "major"))
    v2 = doc_of(2, F1=("resolved", "major"), F2=("open", "major"))
    v3 = doc_of(3, F1=("resolved", "major"), F2=("open", "major"))
    assert best_version([v1, v2]) == 2
    assert best_version([v1, v2, v3]) == 2

def run(cwd, *args, ok=True):
    r = subprocess.run([sys.executable, str(P), *args], cwd=cwd, capture_output=True, text=True)
    assert (r.returncode == 0) is ok, r.stderr
    return r.stdout if ok else r.stderr


OUTPUTS = ["final/part_graph.json", "final/parts_lib.py", "final/assembled.glb", "final/sources.json", "final/blockout.md"]


def worker_round(tmp, n):
    v = tmp / f"production/assets/house-a/blockout/v{n}"
    for o in OUTPUTS:
        (v / o).write_text("x", encoding="utf-8")
    h = brief_hash((v / "brief-worker.md").read_text(encoding="utf-8"))
    (v / "report-worker.md").write_text(f"STATUS: DONE\nPROFILE_HASH: {h}\nFIXED: F1\n", encoding="utf-8")
    head, line = run(tmp, "ingest", "house-a").splitlines()
    assert head == "house-a: worker DONE → blockout/review. Tiếp: giao reviewer → `brief house-a`"
    out = json.loads(line)
    assert (out["role"], json.loads(run(tmp, "brief", "house-a"))) == ("reviewer", out)
    return (tmp / out["brief"]).read_text(encoding="utf-8"), v


def test_ingest_keeps_findings_per_version_and_review_brief_prefills_prior(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    write_profile(tmp_path)
    run(tmp_path, "new", "house-a", "--title", "House A")
    run(tmp_path, "ready", "house-a")
    run(tmp_path, "brief", "house-a")
    brief, v = worker_round(tmp_path, 1)
    assert "- F1 [blocker|major|minor|preference|unclear] <structure|param>" in brief
    assert "PRIOR:" not in brief
    (v / "report-review.md").write_text(report(counts=counts(major=2), top_fix="structure: F1", findings=[
        finding("F1", "major", "structure"), finding("F2", "major", "param", acceptance="mái chìa 0.3 m")]),
        encoding="utf-8")
    head, line = run(tmp_path, "ingest", "house-a").splitlines()
    assert head == "house-a: review FIX (major=2) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    assert "house-a · blockout v1 · review FIX (major=2) · massing=fail" in (
        tmp_path / "production/ledger.md").read_text(encoding="utf-8")

    out = json.loads(run(tmp_path, "brief", "house-a"))
    assert out == json.loads(line)
    wb = (tmp_path / out["brief"]).read_text(encoding="utf-8")
    assert "Sửa đúng `TOP_FIX: structure: F1`" in wb
    assert "production/assets/house-a/blockout/v1/findings.json" in wb
    assert "PROFILE_HASH: " in wb and "FIXED: F<n>, ..." in wb

    brief, v2 = worker_round(tmp_path, 2)
    assert "COMPARE: F1=?\n" in brief
    assert "- F1: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front\n" in brief
    assert "- F2: ? | evidence: ? | acceptance: mái chìa 0.3 m\n" in brief
    assert "- F3 [blocker|major|minor|preference|unclear] <structure|param>" in brief
    assert "production/assets/house-a/blockout/v1/final/" in brief

    bad = report(counts=counts(major=1), top_fix="param: F2", compare="F1=better",
                 prior=["- F1: resolved | evidence: clay_front"])
    (v2 / "report-review.md").write_text(bad, encoding="utf-8")
    assert run(tmp_path, "ingest", "house-a", ok=False) == (
        "LỖI: production/assets/house-a/blockout/v2/report-review.md sai contract: PRIOR thiếu F2\n")
    assert not (v2 / "findings.json").exists()
    assert json.loads((tmp_path / "production/assets/house-a/status.json").read_text())["state"] == "reviewing"

    (v2 / "report-review.md").write_text(report(
        counts=counts(major=1, minor=1), top_fix="param: F2, F3", compare="F1=better",
        prior=["- F1: resolved | evidence: clay_front", "- F2: open | evidence: ?"],
        findings=[finding("F3", "minor", "param")]), encoding="utf-8")
    assert run(tmp_path, "ingest", "house-a").splitlines()[0] == (
        "house-a: review FIX (major=1 minor=1) → blockout/fix. Tiếp: giao worker → `brief house-a`")
    doc = json.loads((v2 / "findings.json").read_text(encoding="utf-8"))
    assert (doc["version"], doc["base"], doc["next_id"], doc["top_fix"]) == (2, 1, 4, {"kind": "param", "ids": ["F2", "F3"]})
    assert brief_view(doc) == {"F1": ("major", "structure", "resolved", 1, 2), "F2": ("major", "param", "open", 1, 2),
                               "F3": ("minor", "param", "open", 2, 2)}


def test_worker_report_missing_profile_hash_keeps_the_asset_running(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    write_profile(tmp_path)
    run(tmp_path, "new", "house-a", "--title", "House A")
    run(tmp_path, "ready", "house-a")
    run(tmp_path, "brief", "house-a")
    v = tmp_path / "production/assets/house-a/blockout/v1"
    (v / "report-worker.md").write_text("STATUS: DONE\nOUTPUT: final/\n", encoding="utf-8")
    assert run(tmp_path, "ingest", "house-a", ok=False) == (
        "LỖI: production/assets/house-a/blockout/v1/report-worker.md sai contract: thiếu PROFILE_HASH\n")
    assert json.loads((tmp_path / "production/assets/house-a/status.json").read_text())["state"] == "running"


REST = {"id": "views_rest", "top_fix": ["regen", "regen_front", "note_exception", "note_texture"],
        "regions": ["back", "left", "right", "top"]}


def test_regen_front_takes_one_id_and_wins_a_tie_with_regen_because_a_new_front_voids_every_other_view():
    fs = [finding("F1", "major", "regen", region="back: bóng đổ dưới mái"),
          finding("F2", "major", "regen_front", region="front: gỗ đỏ hơn cả bộ")]
    assert errs_of(None, step=REST, counts=counts(major=2), top_fix="regen: F1", findings=fs) == [
        "TOP_FIX phải là loại regen_front"]
    assert errs_of(None, step=REST, counts=counts(major=2), top_fix="regen_front: F2", findings=fs) == []


def test_a_note_finding_must_be_minor_because_a_note_never_causes_a_fix():
    note = {"region": "back: đầu dầm"}
    assert errs_of(None, step=REST, verdict="PASS", top_fix=None, counts=counts(minor=1),
                   findings=[finding("F1", "minor", "note_texture", **note)]) == []
    assert errs_of(None, step=REST, verdict="PASS", top_fix=None, counts=counts(major=1),
                   findings=[finding("F1", "major", "note_texture", **note)]) == [
        "F1: note_texture chỉ ghi chú, mức phải là minor", "PASS nhưng còn major=1 đang mở"]


def test_a_views_rest_finding_opens_with_its_view_so_front_is_judged_only_through_regen_front():
    fs = [finding("F1", "major", "regen", region="mép mái"), finding("F2", "major", "regen", region="front: màu gỗ"),
          finding("F3", "major", "regen", region="back, left: bóng đổ"),
          finding("F4", "major", "regen_front", region="front: gỗ đỏ")]
    assert errs_of(None, step=REST, counts=counts(major=4), top_fix="regen_front: F4", findings=fs) == [
        "F1: region phải mở đầu bằng back|left|right|top, vd `back: …`",
        "F2: region phải mở đầu bằng back|left|right|top, vd `back: …`"]


def test_a_confirmed_note_carries_into_the_next_round_so_the_approved_fix_version_still_drops_it_d27_8():
    base, _ = apply(None, rv(counts=counts(major=1), findings=[finding("F1", "major", "structure")],
                             extra="RESOLVED_CONFIRMED: views_rest v2 F2\n"), STEP, 1)
    doc, errs = apply(base, rv(verdict="PASS", top_fix=None, counts=counts(), compare="F1=better",
                               prior=["- F1: resolved | evidence: clay_front"],
                               extra="RESOLVED_CONFIRMED: views_rest v2 F3\n"), STEP, 2)
    assert (base["resolved_notes"], doc["resolved_notes"], errs) == (
        ["views_rest v2 F2"], ["views_rest v2 F2", "views_rest v2 F3"], [])
