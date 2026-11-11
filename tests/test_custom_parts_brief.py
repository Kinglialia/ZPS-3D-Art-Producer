"""D32: the worker of a step that builds a part graph writes the asset's own `custom` functions outside its version
folder, so the brief must name that one file; agents write only the paths their brief names. The reviewer reads only
what its brief names too, and that code is evidence of how the shape was built (D32.2), so its brief names the file
once the file exists."""
from test_loop import AID, flow  # noqa: F401  (flow is the blockout-only fixture)

LINE = (f"- Hàm `custom` riêng của asset (code, đọc như bằng chứng; nhãn `custom_parts.py`): "
        f"`production/assets/{AID}/custom_parts.py`.")


def test_the_blockout_worker_brief_names_the_asset_file_for_its_own_custom_functions(flow):  # noqa: F811
    lines = flow.text(flow.brief()).splitlines()
    assert f"CUSTOM_PARTS: production/assets/{AID}/custom_parts.py" in lines


def review_lines(flow):  # noqa: F811
    flow.work()
    return flow.text(flow.brief()).splitlines()


def test_the_reviewer_brief_names_the_asset_file_when_the_worker_wrote_one(flow):  # noqa: F811
    (flow.root / f"production/assets/{AID}/custom_parts.py").write_text("import math\n", encoding="utf-8")
    assert LINE in review_lines(flow)


def test_the_reviewer_brief_has_no_asset_file_line_when_there_is_no_file(flow):  # noqa: F811
    assert not any("custom_parts.py" in line for line in review_lines(flow))
