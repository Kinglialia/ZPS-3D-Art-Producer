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


def test_missing_evidence_opened_is_rejected_but_missing_counts_is_not_because_the_script_counts():
    _, errs = parse_review("VERDICT: PASS\nRUBRIC: massing=pass\n")
    assert errs == ["thiếu EVIDENCE_OPENED"]


def test_counts_a_reviewer_still_writes_are_read_when_whole_and_dropped_when_not_and_never_reject():
    rv, errs = parse_review(report(counts="blocker=0; major=1; minor=0; preference=0; unclear=0"))
    assert (errs, rv["counts"]) == ([], {"blocker": 0, "major": 1, "minor": 0, "preference": 0, "unclear": 0})
    rv, errs = parse_review(report(counts="blocker=0; major=1"))
    assert (errs, rv["counts"], rv["counts_text"]) == ([], None, "blocker=0; major=1")
    rv, errs = parse_review(report(counts=None))
    assert (errs, rv["counts"], rv["counts_text"]) == ([], None, "")


def test_top_fix_with_a_kind_only_parses_to_no_ids_so_the_script_fills_a_batch():
    rv, errs = parse_review(report(top_fix="param"))
    assert (errs, rv["top_fix"]) == ([], {"kind": "param", "ids": []})
    rv, errs = parse_review(report(top_fix="structure: F1 (mái thấp nhất)"))
    assert (errs, rv["top_fix"]) == ([], {"kind": "structure", "ids": ["F1"]})


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
    assert errs == ["RUBRIC base: 'ok' phải là pass|fail|unclear|not_checked"]
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


def test_a_note_in_brackets_after_a_rubric_value_keeps_the_value_so_a_good_review_is_not_sent_back_for_form():
    rv, errs = parse_review(report(rubric="roof=pass (ok); door=Fail (thấp 0.2 m, chưa đủ); base=pass"))
    assert errs == []
    assert rv["rubric"] == {"roof": "pass", "door": "fail", "base": "pass"}


def test_a_note_in_brackets_after_a_compare_value_keeps_the_value():
    rv, errs = parse_review(report(compare="F1=better (door matches now); F3=Same"))
    assert errs == []
    assert rv["compare"] == {"F1": "better", "F3": "same"}


def test_a_finding_field_wrapped_onto_a_second_indented_line_joins_its_value():
    wrapped = "\n".join([
        "- F1 [major] structure",
        "  region: mái | viewing_condition: front ortho, 512 px | evidence: clay_front: mái thấp",
        "    0.4 m so với concept",
        "  consequence: sai silhouette | confidence: high",
        "  repair: nâng mái 0.3 m",
        "  và giữ độ dốc | preserve: chiều cao tường | acceptance: đỉnh mái 3.2 m trên clay_front"])
    rv, errs = parse_review(report(findings=[wrapped]))
    assert errs == []
    assert rv["findings"]["F1"]["evidence"] == "clay_front: mái thấp 0.4 m so với concept"
    assert rv["findings"]["F1"]["repair"] == "nâng mái 0.3 m và giữ độ dốc"
    assert rv["findings"]["F1"]["preserve"] == "chiều cao tường"


def test_a_capitalised_prior_status_is_read_as_the_status():
    rv, errs = parse_review(report(prior=["- F1: Resolved | evidence: clay_front", "- F2: OPEN", "- F3: Regressed."]))
    assert errs == []
    assert rv["prior"] == {"F1": "resolved", "F2": "open", "F3": "regressed"}


@pytest.mark.parametrize("line", ["**VERDICT:** PASS", "**VERDICT**: PASS", "`VERDICT`: PASS", "verdict: pass",
                                  "VERDICT: **PASS** (đủ)", "VERDICT: Pass."])
def test_verdict_is_read_through_bold_backticks_case_and_a_trailing_note(line):
    text = report(verdict="PASS", top_fix=None).replace("VERDICT: PASS", line)
    rv, errs = parse_review(text)
    assert (errs, rv["verdict"]) == ([], "PASS")


def test_a_wrapped_rubric_line_keeps_every_key():
    rv, errs = parse_review(report(rubric="massing=fail;\n  props=pass; base=pass"))
    assert errs == []
    assert rv["rubric"] == {"massing": "fail", "props": "pass", "base": "pass"}


@pytest.mark.parametrize("dash", ["—", "–", "-"])
def test_accepted_fail_takes_a_dash_between_the_file_and_the_reason(dash):
    c, errs = parse_worker(f"STATUS: DONE\nPROFILE_HASH: abc\nACCEPTED_FAIL: final/review/checks/size-fit.json {dash} "
                           f"dài 0.4 m so với 0.3 m; final/review/join.json {dash} lệch 2 mm\n")
    assert errs == []
    assert c["ACCEPTED_FAIL"] == [("final/review/checks/size-fit.json", "dài 0.4 m so với 0.3 m"),
                                  ("final/review/join.json", "lệch 2 mm")]


def test_accepted_fail_without_a_separated_dash_is_still_rejected():
    _, errs = parse_worker("STATUS: DONE\nPROFILE_HASH: abc\nACCEPTED_FAIL: final/review/checks/size-fit.json lệch 2 mm\n")
    assert errs == ["ACCEPTED_FAIL: 'final/review/checks/size-fit.json lệch 2 mm' phải là <file JSON> — <lý do có số>"]


def test_prose_between_findings_that_would_drop_a_later_finding_is_an_error_naming_the_line():
    """Run 4: a reviewer wrote a sentence between F3 and F4; F4 was dropped without a word."""
    text = report(findings=[finding("F3", "minor", "param"), "Còn một lỗi nữa ở mái:", finding("F4", "major")])
    _, errs = parse_review(text)
    assert errs == ["dòng không thụt lề trong FINDINGS: 'Còn một lỗi nữa ở mái:'; mục sau nó '- F4 [major] structure' "
                    "không được đọc"]


def test_prose_before_the_first_finding_is_an_error_because_the_whole_list_would_be_dropped():
    _, errs = parse_review(report(findings=["Các lỗi tôi thấy:", finding("F1")]))
    assert len(errs) == 1 and errs[0].startswith("dòng không thụt lề trong FINDINGS: 'Các lỗi tôi thấy:'")


def test_prose_between_prior_lines_that_would_drop_a_later_line_is_an_error_naming_the_line():
    _, errs = parse_review(report(prior=["- F1: open", "Hai mục dưới chưa đổi:", "- F2: open"]))
    assert errs == ["dòng không thụt lề trong PRIOR: 'Hai mục dưới chưa đổi:'; mục sau nó '- F2: open' không được đọc"]


def test_a_closing_note_after_the_last_item_does_not_reject_the_report_because_nothing_is_lost():
    rv, errs = parse_review(report(findings=[finding()], prior=["- F2: open"],
                                   extra="Xong.\n\n## Ghi chú\n- đã xem đủ ảnh\n"))
    assert errs == []
    assert (list(rv["findings"]), rv["prior"]) == (["F1"], {"F2": "open"})


def test_worker_status_and_unfixable_are_read_from_their_first_word_so_the_loop_branches_on_clean_values():
    c, errs = parse_worker("STATUS: **Done** (xong hết)\nPROFILE_HASH: abc\nUNFIXABLE: Yes (UV chồng)\n")
    assert errs == []
    assert (c["STATUS"], c["UNFIXABLE"]) == ("DONE", "yes")
    c, errs = parse_worker("STATUS: DONE_WITH_CONCERNS.\nPROFILE_HASH: abc\n")
    assert (errs, c["STATUS"], "UNFIXABLE" in c) == ([], "DONE_WITH_CONCERNS", False)
    assert parse_worker("STATUS: DONE\nPROFILE_HASH: abc\nUNFIXABLE: maybe\n")[1] == ["UNFIXABLE phải là yes|no"]
