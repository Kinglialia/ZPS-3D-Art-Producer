import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts"))

from shared import finding, report  # noqa: E402,F401
from core.contract import FIELDS, parse_review, parse_worker, unwrap  # noqa: E402


def test_finding_block_keeps_every_kit_field_so_ad_and_human_findings_share_one_format():
    rv, errs = parse_review(report(findings=[finding()]))
    assert errs == []
    assert rv["findings"] == {"F1": {
        "priority": "major", "kind": "structure", "region": "mái", "viewing_condition": "front ortho, 512 px",
        "evidence": "clay_front: mái thấp 0.4 m", "consequence": "sai silhouette", "confidence": "high",
        "repair": "nâng mái 0.3 m", "preserve": "chiều cao tường", "acceptance": "đỉnh mái 3.2 m trên clay_front"}}
    assert (rv["verdict"], rv["top_fix"], rv["evidence"]) == (
        "FIX", {"kind": "structure", "ids": ["F1"]}, ["clay_front.png", "clay_side.png"])
    assert rv["counts"] == {"blocker": 0, "major": 1, "minor": 0, "preference": 0, "unclear": 0}


def test_contract_fields_equal_the_kit_issue_fields_minus_header_keys():
    assert FIELDS == ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve",
                      "acceptance")
    for p in Path(__file__).resolve().parents:
        kit = p / "upstream/zps-art-assets-kit-v0.10.4/src/.art-production-support/templates/issue-fields.json"
        if kit.exists():
            fields = json.loads(kit.read_text(encoding="utf-8"))["fields"]
            assert tuple(f for f in fields if f not in ("id", "priority", "status")) == FIELDS
            return
    pytest.skip("kit v0.10.4 not checked out next to the repo")


def test_finding_without_acceptance_is_rejected_because_resolved_must_prove_it_later():
    text = finding().replace(" | acceptance: đỉnh mái 3.2 m trên clay_front", "")
    _, errs = parse_review(report(findings=[text]))
    assert errs == ["F1 thiếu acceptance"]


def test_finding_evidence_must_cite_an_opened_image_so_claims_trace_to_what_was_seen():
    _, errs = parse_review(report(findings=[finding(evidence="nhìn thấy mái thấp")]))
    assert errs == ["F1: evidence phải dẫn nhãn trong EVIDENCE_OPENED"]


def test_field_value_with_a_pipe_stays_in_its_field():
    rv, errs = parse_review(report(findings=[finding(repair="nâng mái | giữ độ dốc")]))
    assert errs == []
    assert rv["findings"]["F1"]["repair"] == "nâng mái | giữ độ dốc"


@pytest.mark.parametrize("empty", ["- none", "none", "-"])
def test_a_pass_with_no_new_finding_written_as_none_is_accepted_so_the_reviewer_is_not_sent_back(empty):
    text = report(verdict="PASS", counts="blocker=0; major=0; minor=0; preference=0; unclear=0", top_fix="none",
                  rubric="massing=pass", findings=[empty])
    _, errs = parse_review(text)
    assert errs == []


def test_confidence_with_a_reason_in_brackets_keeps_the_level_so_a_reviewer_is_not_sent_back_for_a_rewrite():
    rv, errs = parse_review(report(findings=[finding(confidence="low (chưa có ảnh cùng góc, xem F1)")]))
    assert errs == []
    assert rv["findings"]["F1"]["confidence"] == "low"


def test_unknown_priority_and_confidence_are_rejected():
    _, errs = parse_review(report(findings=[finding(prio="critical", confidence="sure")]))
    assert errs == ["F1: mức 'critical' không hợp lệ", "F1: confidence phải là high|medium|low"]


def test_missing_counts_and_evidence_opened_are_rejected_because_producer_reads_only_verdict_and_counts():
    _, errs = parse_review("VERDICT: PASS\nRUBRIC: massing=pass\n")
    assert errs == ["thiếu COUNTS", "thiếu EVIDENCE_OPENED"]


def test_counts_need_all_five_priorities():
    _, errs = parse_review(report(counts="blocker=0; major=1"))
    assert errs == ["COUNTS phải là blocker=N; major=N; minor=N; preference=N; unclear=N"]


def test_prior_resolved_needs_evidence_label_because_resolved_means_acceptance_was_proven():
    rv, errs = parse_review(report(prior=["- F1: resolved | evidence: ? | acceptance: đỉnh mái 3.2 m",
                                          "- F2: open | evidence: ?"]))
    assert errs == ["PRIOR F1: resolved cần evidence dẫn nhãn trong EVIDENCE_OPENED"]
    assert rv["prior"] == {"F1": "resolved", "F2": "open"}


def test_prior_placeholder_left_unfilled_is_rejected():
    _, errs = parse_review(report(prior=["- F1: ? | evidence: ?"]))
    assert errs == ["PRIOR F1: '?' phải là open|resolved|regressed|superseded"]


def test_compare_and_pick_parse_to_literal_values():
    rv, errs = parse_review(report(compare="F1=better; F3=worse", pick="b",
                                   prior=["- F1: resolved | evidence: clay_front", "- F3: regressed | evidence: ?"]))
    assert errs == []
    assert (rv["compare"], rv["pick"], rv["prior"]) == (
        {"F1": "better", "F3": "worse"}, "b", {"F1": "resolved", "F3": "regressed"})


def test_bad_compare_and_pick_values_are_rejected():
    _, errs = parse_review(report(compare="F1=?", pick="d"))
    assert errs == ["COMPARE F1: '?' phải là better|same|worse", "PICK phải là a|b|c"]


def test_rubric_accepts_unclear_and_rejects_other_values():
    rv, errs = parse_review(report(rubric="massing=fail; props=unclear; base=ok"))
    assert errs == ["RUBRIC base: 'ok' phải là pass|fail|unclear"]
    assert rv["rubric"] == {"massing": "fail", "props": "unclear"}


def test_top_fix_none_on_pass_parses_as_absent():
    rv, errs = parse_review(report(verdict="PASS", top_fix="none",
                                   counts="blocker=0; major=0; minor=0; preference=0; unclear=0"))
    assert (errs, rv["top_fix"]) == ([], None)


def test_findings_after_line_40_are_read_because_reports_with_many_findings_are_long():
    many = [finding(f"F{i}") for i in range(1, 12)]
    rv, errs = parse_review(report(findings=many, extra="\n## Ghi chú\n- không phải finding\n"))
    assert errs == []
    assert list(rv["findings"]) == [f"F{i}" for i in range(1, 12)]


def test_worker_report_without_profile_hash_is_rejected_so_stale_profiles_cannot_slip_through():
    c, errs = parse_worker("STATUS: DONE\nOUTPUT: final/\nRUBRIC: a=pass\nISSUES: none\n")
    assert errs == ["thiếu PROFILE_HASH"]
    c, errs = parse_worker("STATUS: DONE\nPROFILE_HASH: 3f2a\nFIXED: F1, F2\n")
    assert (errs, c["PROFILE_HASH"], c["FIXED"]) == ([], "3f2a", "F1, F2")


def test_worker_status_outside_contract_is_rejected():
    _, errs = parse_worker("STATUS: OK\nPROFILE_HASH: 3f2a\n")
    assert errs == ["STATUS phải là BLOCKED|DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT"]


def test_a_saved_reviewer_reply_parses_only_its_report_even_with_trailing_spaces_and_crlf_on_the_markers():
    body = report(findings=[finding()])
    crlf = body.replace("\n", "\r\n")
    reply = f"Xong v2.\r\n--- report --- \r\n{crlf}--- end ---\t\r\nCảm ơn.\r\n"
    assert parse_review(unwrap(reply)) == parse_review(body)


def test_resolved_notes_and_their_confirmation_name_a_note_by_step_version_and_id_d27_8():
    """README "Việc còn mở" matches these ids against `<step> vN F<k>`, so a loose form would keep a done note listed."""
    c, errs = parse_worker("STATUS: DONE\nPROFILE_HASH: abc\nRESOLVED_NOTES: views_rest v2 F2, views_rest v2 F3\n")
    assert (c["RESOLVED_NOTES"], errs) == (["views_rest v2 F2", "views_rest v2 F3"], [])
    assert parse_worker("STATUS: DONE\nPROFILE_HASH: abc\nRESOLVED_NOTES: none\n")[0]["RESOLVED_NOTES"] == []
    assert parse_worker("STATUS: DONE\nPROFILE_HASH: abc\nRESOLVED_NOTES: F2 hàng ván\n")[1] == [
        "RESOLVED_NOTES: 'F2 hàng ván' phải là <bước> vN F<k>"]
    rv, errs = parse_review(report(extra="RESOLVED_CONFIRMED: views_rest v2 F2\n"))
    assert (rv["confirmed"], errs) == (["views_rest v2 F2"], [])
    assert parse_review(report())[0]["confirmed"] == []
