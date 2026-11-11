"""D27.11: rules every step reviewer carries in its agent file. Pilot run: `back.png` had 2 board rows for 3 and passed as a
`note_texture`; a texture fix of F6 erased the lid-gap ink line that `preserve` did not name."""
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer/agents"
PRESERVE = ('- `preserve` nêu tên các chi tiết nằm cạnh vùng sửa có thể bị đụng tới (ví dụ "nét mực mép mái", '
            '"chân bàn trái", "gốc cây"), không ghi chung chung "giữ phần còn lại".')
COUNT = {
    "blockout": "- Sai số lượng thành phần so với concept (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là `structure`, "
                "không bao giờ là ghi chú.",
    "clay": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là "
            "`structure`, không bao giờ là ghi chú.",
    "texture": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là "
               "`repaint` (vẽ sai) hoặc `fix_uv_mesh` (mesh sai), không bao giờ là `note`.",
    "views": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số cửa sổ, số chân bàn, số cành, số tảng đá): luôn là "
             "`regen`, không bao giờ là `note_texture`.",
}


@pytest.mark.parametrize("step", sorted(COUNT))
def test_each_step_reviewer_files_a_wrong_part_count_as_a_fix_and_names_what_preserve_keeps(step):
    rows = (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8").splitlines()
    assert (COUNT[step] in rows, PRESERVE in rows) == (True, True)


FALLBACK = "Lệnh ghi file bị chặn: trả cả report giữa dòng `--- report ---` và dòng `--- end ---`."


@pytest.mark.parametrize("step", sorted(COUNT))
def test_each_step_reviewer_writes_its_report_file_and_replies_two_lines_with_text_only_as_fallback_d27_5(step):
    """D22.6 stays: a report saved by the Producer passes through its context, so text is the exception."""
    body = (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8")
    assert ("- Chỉ đọc. Không sửa file nào ngoài report brief chỉ định. Không chạy lại script." in body.splitlines(),
            "- Ghi report vào file brief chỉ định. Tin nhắn trả về cho Producer: chỉ dòng `VERDICT` và dòng `COUNTS`. "
            + FALLBACK in body.splitlines()) == (True, True)


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


@pytest.mark.parametrize("step", ["blockout", "model", "views", "texture"])
def test_each_worker_knows_a_failed_check_comes_back_to_it_and_how_to_accept_one_d31_3(step):
    rows = (AGENTS / f"zps-3dp-step-{step}" / f"zps-3dp-step-{step}.md").read_text(encoding="utf-8").splitlines()
    assert ACCEPTED in rows


SCOPE = ("- `REVIEW_SCOPE` ở đầu brief. `full`: chấm đủ mọi key rubric, không dùng `not_checked`. `fix`: chỉ chấm id trong "
         "`COMPARE` và `TOP_FIX`, vùng `preserve` của chúng, rồi nhìn nhanh toàn bộ ảnh để bắt lỗi mới; key rubric không "
         "chấm ghi `not_checked`. PASS ở vòng `fix` chưa cho bước qua: script giao thêm một lượt `full`.")


@pytest.mark.parametrize("step", sorted(COUNT))
def test_each_step_reviewer_knows_what_a_fix_round_judges_and_that_only_a_full_round_passes_d31_2(step):
    """The brief carries only the REVIEW_SCOPE line, so the role file holds what each scope judges."""
    assert SCOPE in (AGENTS / f"zps-3dp-check-{step}.md").read_text(encoding="utf-8").splitlines()
