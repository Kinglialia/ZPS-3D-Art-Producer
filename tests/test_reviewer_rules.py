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
