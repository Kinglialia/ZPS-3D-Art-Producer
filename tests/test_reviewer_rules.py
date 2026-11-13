"""D27.11: rules every step reviewer carries in its agent file. Pilot run: `back.png` had 2 board rows for 3 and passed as a
`note_texture`; a texture fix of F6 erased the lid-gap ink line that `preserve` did not name."""
import json
from pathlib import Path

import pytest

from test_loop import flow  # noqa: F401  (the blockout-only fixture)

AGENTS = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer/agents"
PRESERVE = ('- `preserve` nêu tên các chi tiết nằm cạnh vùng sửa có thể bị đụng tới (ví dụ "nét mực mép mái", '
            '"chân bàn trái", "gốc cây"), không ghi chung chung "giữ phần còn lại".')
COUNT = {
    "texture": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là "
               "`repaint` (vẽ sai) hoặc `fix_uv_mesh` (mesh sai), không bao giờ là `note`.",
    "views": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là "
             "`regen`, không bao giờ là `note_texture`.",
}
KEPT = set()  # K08 (Q10) trimmed blockout, clay, texture; P29 trimmed views the same way: the brief states preserve
STEPS = ["blockout", "clay", "texture", "views"]


@pytest.mark.parametrize("step", sorted(COUNT))
def test_each_step_reviewer_files_a_wrong_part_count_as_a_fix_and_names_what_preserve_keeps(step):
    rows = (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8").splitlines()
    assert (COUNT[step] in rows, PRESERVE in rows) == (True, step in KEPT)


FALLBACK = "Lệnh ghi file bị chặn: trả cả report giữa dòng `--- report ---` và dòng `--- end ---`."


@pytest.mark.parametrize("step", STEPS)
def test_each_step_reviewer_writes_its_report_file_and_replies_two_lines_with_text_only_as_fallback_d27_5(step):
    """D22.6 stays: a report saved by the Producer passes through its context, so text is the exception. Every review
    brief, the resumed one too, ends with the reply and fallback rule (P29), so the role file keeps only "read only"."""
    from core import briefs
    body = (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8")
    assert ("- Chỉ đọc. Không sửa file nào ngoài report brief chỉ định. Không chạy lại script." in body.splitlines(),
            FALLBACK in body, briefs.FALLBACK == FALLBACK) == (True, False, True)


def test_the_ab_judge_writes_its_report_file_and_replies_done_with_text_only_as_fallback_d27_5():
    rows = (AGENTS / "zps-3dp-check-ab.md").read_text(encoding="utf-8").splitlines()
    assert ("- Chỉ đọc. Không sửa file nào ngoài report brief chỉ định. Không chạy script." in rows,
            "Chỉ dòng `DONE`. Report nằm trong file. " + FALLBACK in rows) == (True, True)


@pytest.mark.parametrize("step", ["blockout", "model", "views", "texture"])
def test_each_worker_returns_its_report_as_text_only_when_the_write_is_blocked_d27_5(step):
    rows = (AGENTS / f"zps-3dp-step-{step}" / f"zps-3dp-step-{step}.md").read_text(encoding="utf-8").splitlines()
    assert FALLBACK in rows


ACCEPTED = ("JSON fail trong `final/review/{gates,checks}/` trả thẳng về bạn, không qua reviewer: sửa cho pass. Check không "
            "sửa được và có trong danh sách `ACCEPTED_FAIL` của brief: ghi `ACCEPTED_FAIL: <file JSON> — <lý do có số>` "
            "trong report và cùng dòng đó vào mục `## NGOẠI LỆ` của `final/README.md` (tạo mục nếu chưa có). Gate cứng "
            "(inputs, package, schema, export_check, meshy) không bao giờ được khai.")


@pytest.mark.parametrize("step", ["blockout", "views", "texture"])
def test_each_worker_knows_a_failed_check_comes_back_to_it_and_how_to_accept_one_d31_3(step):
    rows = (AGENTS / f"zps-3dp-step-{step}" / f"zps-3dp-step-{step}.md").read_text(encoding="utf-8").splitlines()
    assert ACCEPTED in rows


def test_the_model_worker_knows_a_failed_check_comes_back_to_it_and_reads_how_to_accept_one_in_fix_md_d31_3():
    """K19 (Q11) moved the steps of ACCEPTED_FAIL to references/fix.md, which a first build does not read. The agent
    file keeps the rule that a failed JSON comes back and the hard gates, counts included."""
    agent = AGENTS / "zps-3dp-step-model"
    rows = (agent / "zps-3dp-step-model.md").read_text(encoding="utf-8").splitlines()
    assert ("JSON fail trong `final/review/{gates,checks}/`, `final/review/join.json` và `unwrap.json` trả thẳng về bạn, "
            "không qua reviewer: sửa cho pass. Check không sửa được và có trong danh sách `ACCEPTED_FAIL` của brief: "
            "đọc mục `ACCEPTED_FAIL` của `R/fix.md`. Gate cứng (inputs, package, schema, counts, export_check, meshy) "
            "không bao giờ được khai.") in rows
    fix = (agent / "references/fix.md").read_text(encoding="utf-8")
    assert ("ghi `ACCEPTED_FAIL: <file JSON> — <lý do có số>` trong report. Ghi cùng dòng đó vào mục `## NGOẠI LỆ` của "
            "`final/README.md` (tạo mục nếu chưa có).") in fix


SCOPE = ("- `REVIEW_SCOPE` ở đầu brief. `full`: chấm đủ mọi key rubric, không dùng `not_checked`. `fix`: chỉ chấm id trong "
         "`COMPARE` và `TOP_FIX`, vùng `preserve` của chúng, rồi nhìn nhanh toàn bộ ảnh để bắt lỗi mới; key rubric không "
         "chấm ghi `not_checked`. PASS ở vòng `fix` cho bước qua khi `RUBRIC` không có `not_checked`; có thì script giao "
         "thêm một lượt `full`.")


@pytest.mark.parametrize("step", STEPS)
def test_each_step_reviewer_knows_what_a_fix_round_judges_and_when_its_pass_is_final_d31_2_d38_3(step):
    """The brief carries only the REVIEW_SCOPE line, so the role file holds what each scope judges."""
    assert SCOPE in (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8").splitlines()


TRIMMED = ["blockout", "clay", "texture", "views"]


def reviewer(step):
    return (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("step", TRIMMED)
def test_a_reviewer_file_holds_no_line_that_the_brief_states_or_the_script_decides_q10(step):
    """The brief is the format authority: it carries preserve, COMPARE, COUNTS and the PRIOR words. The script decides
    the approval, so a rule about approval by delegation only gave the reviewer a second thing to get wrong."""
    text = reviewer(step)
    gone = ["Duyệt theo ủy quyền", "ủy quyền", "Không ghi `COUNTS`", "Vòng sửa: so ảnh cùng góc", "`resolved` chỉ khi ảnh mới chứng minh",
            "- `preserve` nêu tên", "- Finding có id `F<n>`, giữ id qua các vòng.", "Mỗi finding đủ 8 trường",
            "`preference` (khẩu vị) không chặn PASS", "- `TOP_FIX` chỉ khi FIX", "Tin nhắn trả về cho Producer"]
    assert [g for g in gone if g in text] == []


def test_the_brief_that_replaces_those_lines_states_them(flow):  # noqa: F811
    from core import findings
    from test_loop import fix_v1
    fix_v1(flow)
    out = flow.work()
    rv = flow.text(json.loads(out.splitlines()[-1]))
    for stated in ("- `preserve`: tên chi tiết", "Không ghi COUNTS", "FINDINGS chỉ ghi finding mới", "PRIOR: thay `?` bằng",
                   "COMPARE: so ảnh cùng góc", "- Sai số thành phần (cửa, chân bàn, đá) so với concept hoặc `blockout.md`: luôn `structure`",
                   "  region: … | viewing_condition: … | evidence: <nhãn trong EVIDENCE_OPENED> …",
                   "  consequence: … | confidence: high|medium|low", "  repair: … | preserve: … | acceptance: …",
                   "preference không chặn PASS", "rubric mâu thuẫn brief → ESCALATE",
                   "- ESCALATE: thêm dòng `ESCALATE: <lý do; các phương án>`. Ghi chú khác: cuối report, dưới dòng "
                   "`## Ghi chú`, không trong FINDINGS hay PRIOR.",
                   # The script fills every open finding of a batch kind with a priority in BATCH_PRIO; the old
                   # reviewer line said every open `param` finding. P29 left the rule in the brief only.
                   f"loại lô chỉ ghi loại, script điền mọi finding {'/'.join(findings.BATCH_PRIO)} đang mở của loại đó",
                   "structure 1 id mỗi part, region `<part>: …`", "Tin nhắn trả về cho Producer: chỉ dòng VERDICT. " + FALLBACK):
        assert stated in rv, stated


@pytest.mark.parametrize("step", ["blockout", "clay", "texture"])
def test_a_reviewer_file_has_one_image_rule_that_covers_sheet_pages_and_crops_q10(step):
    rows = [r for r in reviewer(step).splitlines() if r.startswith("- Ảnh: ")]
    assert len(rows) == 1 and "`sheet-2.png`" in rows[0] and "không mở ảnh lẻ trong `final/`" in rows[0]
    text = reviewer(step)
    assert "Mở từng ảnh bằng tool, theo nhãn." not in text and "Brief có sheet: không mở ảnh lẻ" not in text
    assert "xin ảnh <nhãn ô> box x0,y0,x1,y1" in text and "…_crop" in text




@pytest.mark.parametrize("step", TRIMMED)
def test_a_reviewer_file_carries_no_decision_tag_q10(step):
    import re
    assert re.findall(r"\bD\d+(?:\.\d+)*\b", reviewer(step)) == []


@pytest.mark.parametrize("step, dead", [
    ("clay", ["`detail.json` `detail.more_tris` fail là fail", "`mesh.coplanar_overlap` > 0 là fail", "`join.json` `join.removed_faces_seen` fail là fail",
              "`qa_mesh_check.json` báo mặt ngược là fail"]),
    ("texture", ["`light.*` fail trong `tex_measure.json` là fail", "`material.dE_concept.*` fail là fail", "`seam.*` fail là fail"]),
])
def test_a_rubric_clause_that_fails_a_key_on_a_failed_json_is_gone_because_that_json_never_reaches_the_reviewer_q7(step, dead):
    """A failed check returns to the worker before a review (D31.3), so the reviewer can never see these JSON failed."""
    assert [d for d in dead if d in reviewer(step)] == []


def test_the_clay_reviewer_names_the_two_keys_the_script_fills_and_when_it_does_not_q7():
    text = reviewer("clay")
    assert "6. `density`: script điền `pass` khi `detail.vs_pilot` nằm trong 0,5–2 (brief nêu)." in text
    assert "7. `blockout_match`: script điền `pass` khi bbox, `fixed_params` và kích thước, pivot của mesh đều pass (brief nêu)." in text


def test_the_rubric_templates_say_four_to_eight_criteria_because_two_steps_have_eight():
    import re
    rubrics = AGENTS.parent / "templates/rubrics"
    most = 0
    for f in sorted(rubrics.glob("*.md")):
        for sec in re.split(r"\n## ", f.read_text(encoding="utf-8"))[1:]:
            most = max(most, len(re.findall(r"^- [a-z0-9_]+:", sec, re.M)))
    assert most == 8
    assert "Giữ 4–8 tiêu chí mỗi bước" in (rubrics / "default.md").read_text(encoding="utf-8")
    assert "4–7" not in "".join(f.read_text(encoding="utf-8") for f in rubrics.glob("*.md"))


@pytest.mark.parametrize("step", ["blockout", "clay"])
def test_the_param_rule_tells_the_reviewer_that_a_variant_sheet_can_have_further_pages_q5(step):
    """The model sheet has 12 tiles, so sheet-b.png comes with sheet-b-2.png; the brief names only sheet-<b|c>.png."""
    assert "`sheet-<b|c>-2.png`" in reviewer(step)


@pytest.mark.parametrize("step", ["blockout", "model", "views", "texture"])
def test_each_worker_reads_fix_md_on_the_line_every_fix_type_brief_has_and_fix_md_covers_json_and_user_findings_p2(step):
    """The brief writes "Bản gốc:" in every fix-type brief, but TOP_FIX only after a reviewer FIX. A worker that waited
    for TOP_FIX rebuilt a direct round or a redo with only H findings from nothing."""
    agent = AGENTS / f"zps-3dp-step-{step}"
    line = next(l for l in (agent / f"zps-3dp-step-{step}.md").read_text(encoding="utf-8").splitlines()
                if l.startswith("- `R/fix.md`:"))
    fix = (agent / "references/fix.md").read_text(encoding="utf-8")
    assert "dòng `Bản gốc:`" in line and "`TOP_FIX`" not in line
    assert "JSON fail (vòng trả thẳng)" in fix and "`H<n>`" in fix and "thứ tự brief nêu" in fix
