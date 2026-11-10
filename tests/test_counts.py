"""D30.6: each card `counts` key names a fixed param of the part graph, and the gate compares the two numbers.
A count written as a literal in a part's args, or kept in a param the fix round may change, is how a wrong number of
rows reached the reviewer, so only a fixed param of the same name passes."""
import json
import subprocess
import sys
from argparse import Namespace

import pytest
import yaml

from shared import SCRIPTS, brief_hash
from test_intake import dump, make_asset, mutated
from test_loop import AID, OUTPUTS, flow  # noqa: F401  (flow is the blockout-only fixture)

import check_counts
from core import loop
from core.state import load_st, save_st

CARD = {"type": "building", "counts": {"body_board_rows": 3, "doors": 1}}


def graph(rows=3, fixed=("base_w", "body_board_rows", "doors"), **params):
    """A synthetic shed: a grooved wall box whose row count is the param body_board_rows, and one door."""
    return {"params": {"base_w": 2.0, "body_board_rows": rows, "doors": 1, **params}, "fixed_params": list(fixed),
            "parts": [{"name": "walls", "primitive": "custom", "fn": "grooved_box",
                       "args": ["base_w", "base_w", "base_w", 0.02, 0.01, "body_board_rows"]},
                      {"name": "door", "primitive": "box", "dims": ["base_w", "base_w", "base_w"]}]}


def counts_of(tmp_path, card, g):
    final = tmp_path / "final"
    final.mkdir(parents=True, exist_ok=True)
    (final / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    (tmp_path / "card.yaml").write_text(yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
    r = check_counts.write(final, tmp_path / "card.yaml")
    assert r == json.loads((final / "review/checks/counts.json").read_text(encoding="utf-8"))
    return r["overall"], {c["check"]: (c["status"], c["value"]) for c in r["checks"]}


def test_every_count_passes_when_a_fixed_param_of_the_same_name_holds_the_card_number(tmp_path):
    assert counts_of(tmp_path, CARD, graph()) == ("pass", {"counts.body_board_rows": ("pass", []),
                                                           "counts.doors": ("pass", [])})


@pytest.mark.parametrize("g, why", [
    (graph(rows=2), "param body_board_rows = 2, thẻ body_board_rows = 3"),
    (graph(fixed=("base_w", "doors")), "param body_board_rows không có trong fixed_params"),
])
def test_a_count_fails_when_its_param_differs_or_a_fix_round_may_change_it(tmp_path, g, why):
    assert counts_of(tmp_path, CARD, g)[1]["counts.body_board_rows"] == ("fail", [why])


def test_a_card_key_with_no_param_of_that_name_fails_and_says_what_to_add(tmp_path):
    """A row count written as the literal 3 in the args leaves nothing for the gate to compare: that is a fail, not a
    skip, so the count cannot slip through."""
    g = graph()
    del g["params"]["body_board_rows"]
    g["fixed_params"].remove("body_board_rows")
    g["parts"][0]["args"][-1] = 3
    assert counts_of(tmp_path, CARD, g) == ("fail", {
        "counts.body_board_rows": ("fail", ["part graph không có param body_board_rows: đặt param body_board_rows = 3 "
                                            "vào params và fixed_params, rồi truyền tên body_board_rows vào hàm dựng "
                                            "số đó"]),
        "counts.doors": ("pass", [])})


def test_a_card_without_counts_writes_no_counts_json(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (tmp_path / "card.yaml").write_text("type: prop\n", encoding="utf-8")
    assert (check_counts.write(final, tmp_path / "card.yaml"), (final / "review/checks/counts.json").exists()) == (
        None, False)


def test_the_brief_line_names_each_count_the_part_graph_must_carry():
    assert check_counts.lines(CARD) == ["COUNTS: body_board_rows = 3; doors = 1", ""]


def card_cli(d):
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d)], capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


def test_a_card_with_the_six_keys_passes_check_card_without_a_warning(tmp_path):
    counts = dict.fromkeys(check_counts.KEYS, 2)
    assert card_cli(make_asset(tmp_path, card=mutated(counts=counts))) == (0, [])


@pytest.mark.parametrize("value", [{"doors": -1}, {"doors": "2"}, [2], {"doors": True}, {"chimneys": 2}])
def test_a_counts_entry_outside_the_six_keys_or_not_a_whole_number_fails_check_card(tmp_path, value):
    """The gate compares only the six keys; any other key would pass unchecked, so check_card refuses it."""
    from test_intake import messages
    assert messages(make_asset(tmp_path, card=mutated(counts=value))) == [
        "thẻ: counts sai: cần map {khóa: số nguyên ≥ 0}, khóa là body_board_rows | lid_board_rows | doors | windows | "
        "pillars | steps"]


def counted_asset(flow, root):  # noqa: F811
    """The blockout-only flow, with a synthetic card that has counts as the asset's concept card."""
    d = root / "concepts/_approved/shed"
    d.mkdir(parents=True)
    (d / "asset-card.yaml").write_text(dump(mutated(asset="shed", views="none", counts=CARD["counts"])),
                                       encoding="utf-8")
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
    counted_asset(flow, flow.root)
    out, said = worker_round(flow, graph(rows=2))
    assert "COUNTS: body_board_rows = 3; doors = 1" in flow.text(out).splitlines()
    assert said.splitlines()[0] == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    r = json.loads((flow.v(1) / "final/review/checks/counts.json").read_text(encoding="utf-8"))
    assert (r["overall"], r["checks"][0]["value"]) == ("fail", ["param body_board_rows = 2, thẻ body_board_rows = 3"])
    assert "house-a · blockout v1 · worker DONE (check fail) ·  · vòng sửa 1/3: check fail counts.json" in flow.ledger()


def test_accepted_fail_for_counts_json_is_refused_because_it_is_a_hard_gate(flow):  # noqa: F811
    from core.state import HARD_GATES
    assert "counts.json" in HARD_GATES


def test_a_graph_with_every_count_as_a_fixed_param_goes_to_the_reviewer(flow):  # noqa: F811
    counted_asset(flow, flow.root)
    _, said = worker_round(flow, graph())
    assert json.loads(said.splitlines()[-1])["role"] == "reviewer"


def test_an_unreadable_part_graph_is_an_error_result_so_ingest_sends_it_back_instead_of_crashing(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (final / "part_graph.json").write_text("x", encoding="utf-8")
    (tmp_path / "card.yaml").write_text("type: prop\ncounts: {doors: 1}\n", encoding="utf-8")
    assert check_counts.write(final, tmp_path / "card.yaml")["overall"] == "error"
