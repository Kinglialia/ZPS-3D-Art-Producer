"""D33: the worker of a step that builds a part graph writes the asset's own `custom` functions outside its version
folder, so the brief must name that one file; agents write only the paths their brief names."""
from test_loop import AID, flow  # noqa: F401  (flow is the blockout-only fixture)


def test_the_blockout_worker_brief_names_the_asset_file_for_its_own_custom_functions(flow):  # noqa: F811
    lines = flow.text(flow.brief()).splitlines()
    assert f"CUSTOM_PARTS: production/assets/{AID}/custom_parts.py" in lines
