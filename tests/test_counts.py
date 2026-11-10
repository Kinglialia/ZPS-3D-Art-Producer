"""D30.6: the card `counts` against the named params of the part graph. Lost twice (Run 4 views, Run 5 blockout)."""
import json
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

from shared import SCRIPTS, brief_hash
from test_intake import make_asset, mutated, png
from test_loop import AID, OUTPUTS, flow  # noqa: F401  (flow is the blockout-only fixture)

import check_counts
from core import loop
from core.state import load_st, save_st

V10 = Path(__file__).parent / "fixtures" / "wooden-chest-v10"


def graph(planks, fixed=("lid_planks",), lid_planks=2):
    """The Run 5 chest lid: plank_vault(w, d, h, arch_h, seg, gap, depth, planks, r, bseg)."""
    return {"params": {"lid_w": 0.87, "lid_planks": lid_planks}, "fixed_params": ["lid_w", *fixed],
            "parts": [{"name": "body", "primitive": "custom", "fn": "grooved_box", "args": ["lid_w"] * 7},
                      {"name": "lid_vault", "primitive": "custom", "fn": "plank_vault",
                       "args": ["lid_w", "lid_w", "lid_w", "lid_w", 12, "lid_w", "lid_w", planks, "lid_w", 2]}]}


def counts_of(tmp_path, card, g, cmap=None):
    final = tmp_path / "final"
    final.mkdir(parents=True, exist_ok=True)
    (final / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    (tmp_path / "card.yaml").write_text(yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
    r = check_counts.write(final, tmp_path / "card.yaml", cmap)
    assert r == json.loads((final / "review/checks/counts.json").read_text(encoding="utf-8"))
    return r["overall"], {c["check"]: (c["status"], c["value"]) for c in r["checks"]}


def test_the_plan_case_body_rows_3_against_planks_2_fails_the_gate(tmp_path):
    """v0.7.0 plan C2, with a map that sends body_board_rows to plank_vault.planks."""
    g = graph("body_planks", fixed=("body_planks",)) | {"params": {"lid_w": 0.87, "body_planks": 2}}
    assert counts_of(tmp_path, {"type": "prop", "counts": {"body_board_rows": 3}}, g,
                     {"prop": {"body_board_rows": "plank_vault.planks"}}) == (
        "fail", {"counts.body_board_rows": ("fail", ["lid_vault: planks = body_planks = 2, thẻ body_board_rows = 3"])})


def v10_card():
    return yaml.safe_load((V10 / "asset-card.yaml").read_text(encoding="utf-8"))


def test_the_v10_card_with_the_shipped_map_passes_a_lid_of_two_named_planks_and_leaves_body_rows_unchecked(tmp_path):
    assert counts_of(tmp_path, v10_card(), graph("lid_planks")) == ("pass", {
        "counts.body_board_rows": ("not_checked", 3), "counts.lid_board_rows": ("pass", [])})


@pytest.mark.parametrize("planks, fixed, lid_planks, why", [
    (4, ("lid_planks",), 2, "lid_vault: planks = 4, cần tên một param"),
    ("lid_planks", (), 2, "lid_vault: planks = lid_planks, param lid_planks không có trong fixed_params"),
    ("lid_planks", ("lid_planks",), 4, "lid_vault: planks = lid_planks = 4, thẻ lid_board_rows = 2"),
    ("nope", ("lid_planks",), 2, "lid_vault: planks = 'nope', cần tên một param"),
])
def test_the_v10_lid_fails_for_the_run5_literal_4_and_for_a_param_outside_fixed_params(tmp_path, planks, fixed,
                                                                                        lid_planks, why):
    """Run 5 passed the literal 4 to plank_vault; the card said 2. The model step may not change a fixed param."""
    assert counts_of(tmp_path, v10_card(), graph(planks, fixed, lid_planks))[1]["counts.lid_board_rows"] == ("fail", [why])


def test_a_mapped_count_with_no_part_of_that_function_fails(tmp_path):
    g = graph("lid_planks")
    g["parts"] = g["parts"][:1]
    assert counts_of(tmp_path, v10_card(), g)[1]["counts.lid_board_rows"] == ("fail", ["không part nào dùng plank_vault"])


def test_a_card_without_counts_writes_no_counts_json(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (tmp_path / "card.yaml").write_text("type: prop\n", encoding="utf-8")
    assert (check_counts.write(final, tmp_path / "card.yaml"), (final / "review/checks/counts.json").exists()) == (
        None, False)


def card_cli(d):
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d)], capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


def test_the_real_v10_card_passes_check_card_with_one_warning_for_the_unmapped_body_rows(tmp_path):
    d = tmp_path / "wooden-chest"
    d.mkdir()
    for n in ("asset-card.yaml", "wooden-chest.material.md"):
        shutil.copy(V10 / n, d / n)
    for n in ("concept_albedo.png", "concept_shadow.png"):
        png(d / n, (1254, 1254))
    assert card_cli(d) == (0, ["cảnh báo: thẻ: counts.body_board_rows chưa có ánh xạ cho type prop trong "
                               "templates/counts.yaml; gate không so khóa này"])


def test_an_unknown_counts_key_warns_and_does_not_fail(tmp_path):
    d = make_asset(tmp_path, card=mutated(counts={"chimneys": 2}))
    assert card_cli(d) == (0, ["cảnh báo: thẻ: counts.chimneys lạ (body_board_rows | lid_board_rows | doors | windows | "
                               "pillars | steps); gate không so khóa này"])


@pytest.mark.parametrize("value", [{"doors": -1}, {"doors": "2"}, [2], {"doors": True}])
def test_a_counts_value_that_is_not_a_whole_number_fails_check_card(tmp_path, value):
    from test_intake import messages
    assert messages(make_asset(tmp_path, card=mutated(counts=value))) == ["thẻ: counts sai: cần map {khóa: số nguyên ≥ 0}"]


def chest_asset(flow, root):  # noqa: F811
    """The blockout-only flow, with the v10 card as the asset's concept card."""
    d = root / "concepts/_approved/wooden-chest"
    d.mkdir(parents=True)
    shutil.copy(V10 / "asset-card.yaml", d / "asset-card.yaml")
    st = load_st(AID)
    st["concept_dir"] = str(d)
    save_st(st)


def worker_round(flow, g):  # noqa: F811
    out = flow.brief()
    vd = flow.root / out["report"]
    for o in OUTPUTS:
        (vd.parent / "final" / o).write_text("x", encoding="utf-8")
    (vd.parent / "final/part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    vd.write_text(f"STATUS: DONE\nPROFILE_HASH: {brief_hash(flow.text(out))}\n", encoding="utf-8")
    return out, flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))


def test_a_worker_that_never_ran_the_counts_check_still_goes_back_because_ingest_runs_it(flow):  # noqa: F811
    chest_asset(flow, flow.root)
    out, said = worker_round(flow, graph(4))
    assert "COUNTS: lid_board_rows = 2 → plank_vault.planks" in flow.text(out).splitlines()
    assert said.splitlines()[0] == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    r = json.loads((flow.v(1) / "final/review/checks/counts.json").read_text(encoding="utf-8"))
    assert (r["overall"], r["checks"][1]["value"]) == ("fail", ["lid_vault: planks = 4, cần tên một param"])
    assert "house-a · blockout v1 · worker DONE (check fail) ·  · vòng sửa 1/3: check fail counts.json" in flow.ledger()


def test_accepted_fail_for_counts_json_is_refused_because_it_is_a_hard_gate(flow):  # noqa: F811
    from core.state import HARD_GATES
    assert "counts.json" in HARD_GATES


def test_a_lid_with_two_named_fixed_planks_goes_to_the_reviewer(flow):  # noqa: F811
    chest_asset(flow, flow.root)
    _, said = worker_round(flow, graph("lid_planks"))
    assert json.loads(said.splitlines()[-1])["role"] == "reviewer"


def test_an_unreadable_part_graph_is_an_error_result_so_ingest_sends_it_back_instead_of_crashing(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (final / "part_graph.json").write_text("x", encoding="utf-8")
    (tmp_path / "card.yaml").write_text("type: prop\ncounts: {lid_board_rows: 2}\n", encoding="utf-8")
    assert check_counts.write(final, tmp_path / "card.yaml")["overall"] == "error"
