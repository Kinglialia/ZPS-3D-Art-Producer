"""D27.11: rules every step reviewer carries in its agent file. Run 4: `back.png` had 2 board rows for 3 and passed as a
`note_texture`; a texture fix of F6 erased the lid-gap ink line that `preserve` did not name."""
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer/agents"
PRESERVE = ('- `preserve` nêu tên các chi tiết nằm cạnh vùng sửa có thể bị đụng tới (ví dụ "nét mực khe nắp", '
            '"bản lề trái"), không ghi chung chung "giữ phần còn lại".')
COUNT = {
    "blockout": "- Sai số lượng thành phần so với concept (số hàng ván, số cửa, số trụ): luôn là `structure`, "
                "không bao giờ là ghi chú.",
    "clay": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số hàng ván, số cửa, số trụ): luôn là "
            "`structure`, không bao giờ là ghi chú.",
    "texture": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số hàng ván, số cửa, số trụ): luôn là "
               "`repaint` (vẽ sai) hoặc `fix_uv_mesh` (mesh sai), không bao giờ là `note`.",
    "views": "- Sai số lượng thành phần so với concept hoặc `blockout.md` (số hàng ván, số cửa, số trụ): luôn là "
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
