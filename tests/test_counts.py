"""D30.6, D32.5, D34.3: each card `counts` key is carried into the part graph by a fixed param of the same name, or by
that many parts with `tag: <key>`, and the gate compares the numbers. A count written as a literal in a part's args, or
kept in a param the fix round may change, is how a wrong number of parts reached the reviewer, so neither passes.
The skill has no list of keys: the project's profile names them (`counts_keys`), so every key here is one this test
makes up for a synthetic table, and check_card only warns about a key outside the profile's list."""
import json
import subprocess
import sys
from argparse import Namespace

import pytest
import yaml

from shared import SCRIPTS, brief_hash
from test_intake import dump, make_asset, mutated
from test_loop import AID, OUTPUTS, flow, write_results  # noqa: F401  (flow is the blockout-only fixture)

import check_counts
from core import loop
from core.state import load_st, save_st

# A synthetic project vocabulary: slats of a table top, and its legs.
KEYS = {"top_slats": "số thanh mặt bàn", "legs": "số chân bàn"}
CARD = {"type": "prop", "counts": {"top_slats": 3, "legs": 4}}
HOW = "mỗi khóa: param cùng tên trong fixed_params mà part dùng, hoặc đúng N part có tag: <khóa>"


def graph(slats=3, legs=4, fixed=("top_w", "top_slats")):
    """A synthetic table: a top built by an asset function whose slat count is the param top_slats, and `legs` parts
    tagged legs."""
    return {"params": {"top_w": 1.2, "top_slats": slats}, "fixed_params": list(fixed),
            "parts": [{"name": "top", "primitive": "custom", "fn": "slatted_top",
                       "args": ["top_w", "top_w", "top_slats"]},
                      *({"name": f"leg_{i}", "primitive": "box", "dims": ["top_w"] * 3, "tag": "legs"}
                        for i in range(legs))]}


def counts_of(tmp_path, card, g):
    final = tmp_path / "final"
    final.mkdir(parents=True, exist_ok=True)
    (final / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    (tmp_path / "card.yaml").write_text(yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
    r = check_counts.write(final, tmp_path / "card.yaml")
    assert r == json.loads((final / "review/checks/counts.json").read_text(encoding="utf-8"))
    return r["overall"], {c["check"]: (c["status"], c["value"]) for c in r["checks"]}


def test_a_count_passes_through_a_fixed_param_or_through_tagged_parts(tmp_path):
    assert counts_of(tmp_path, CARD, graph()) == ("pass", {"counts.top_slats": ("pass", []),
                                                           "counts.legs": ("pass", [])})


def test_three_tagged_parts_carry_a_count_of_three_and_two_do_not(tmp_path):
    card = {"counts": {"legs": 3}}
    assert counts_of(tmp_path, card, graph(legs=3))[1] == {"counts.legs": ("pass", [])}
    assert counts_of(tmp_path, card, graph(legs=2))[1] == {"counts.legs": ("fail", [
        "2 part có tag: legs, thẻ legs = 3: đặt param legs = 3 vào params và fixed_params, hoặc gắn tag: legs cho đúng "
        "3 part"])}


def test_a_fixed_param_that_differs_from_the_card_fails(tmp_path):
    assert counts_of(tmp_path, CARD, graph(slats=2))[1]["counts.top_slats"] == (
        "fail", ["param top_slats = 2, thẻ top_slats = 3"])


def test_a_param_outside_fixed_params_does_not_carry_the_count_because_a_fix_round_may_change_it(tmp_path):
    assert counts_of(tmp_path, CARD, graph(fixed=("top_w",)))[1]["counts.top_slats"] == ("fail", [
        "0 part có tag: top_slats, thẻ top_slats = 3 (param top_slats có nhưng không nằm trong fixed_params): đặt "
        "param top_slats = 3 vào params và fixed_params, hoặc gắn tag: top_slats cho đúng 3 part"])


def test_a_count_written_as_a_literal_fails_and_says_both_ways_to_carry_it(tmp_path):
    """A slat count written as the literal 3 in the args leaves nothing for the gate to compare: that is a fail, not
    a skip, so the count cannot slip through."""
    g = graph(fixed=("top_w",))
    del g["params"]["top_slats"]
    g["parts"][0]["args"][-1] = 3
    assert counts_of(tmp_path, CARD, g) == ("fail", {
        "counts.top_slats": ("fail", ["0 part có tag: top_slats, thẻ top_slats = 3: đặt param top_slats = 3 vào params "
                                      "và fixed_params, hoặc gắn tag: top_slats cho đúng 3 part"]),
        "counts.legs": ("pass", [])})


def test_a_fixed_param_with_the_right_value_that_no_part_reads_fails_because_the_graph_can_still_build_another_number(tmp_path):
    """Pilot review: `windows: 4` passed through a fixed param of value 4 while the graph built 2 windows, because no part
    read the param. A count that nothing reads says nothing about the mesh."""
    g = graph()
    g["params"]["windows"] = 4
    g["fixed_params"].append("windows")
    g["parts"] += [{"name": f"win_{i}", "primitive": "box", "dims": ["top_w"] * 3} for i in range(2)]
    assert counts_of(tmp_path, {"counts": {"windows": 4}}, g) == ("fail", {"counts.windows": ("fail", [
        "param windows = 4 nhưng không part nào dùng nó (dims, args, segments, attach): hàm hoặc part dựng số đó phải "
        "nhận param windows, hoặc gắn tag: windows cho đúng 4 part"])})


@pytest.mark.parametrize("part", [
    {"primitive": "box", "dims": ["top_w", "top_w", "n"]},
    {"primitive": "custom", "fn": "f", "args": ["top_w", "top_w", "top_w", "n"]},
    {"primitive": "cylinder", "dims": ["top_w", "top_w"], "segments": "n"},
    {"primitive": "box", "dims": ["top_w"] * 3, "attach": {"type": "inset_into", "to": "top", "inset": "n"}},
    {"primitive": "box", "dims": ["top_w"] * 3, "attach": {"type": "inset_into", "to": "top", "depth": "n"}},
    {"primitive": "box", "dims": ["top_w"] * 3, "attach": {"type": "on_top", "to": "top", "offset_uv": ["n", 0.0]}},
])
def test_a_fixed_param_that_a_part_reads_in_any_field_of_the_part_graph_passes(tmp_path, part):
    g = graph(legs=0)
    g["params"]["n"] = 4
    g["fixed_params"].append("n")
    g["parts"].append({"name": "x"} | part)
    assert counts_of(tmp_path, {"counts": {"n": 4}}, g)[1] == {"counts.n": ("pass", [])}


def test_a_count_of_zero_passes_when_no_part_has_the_tag(tmp_path):
    assert counts_of(tmp_path, {"counts": {"drawers": 0}}, graph())[1] == {"counts.drawers": ("pass", [])}


def test_a_card_without_counts_writes_no_counts_json(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (tmp_path / "card.yaml").write_text("type: prop\n", encoding="utf-8")
    assert (check_counts.write(final, tmp_path / "card.yaml"), (final / "review/checks/counts.json").exists()) == (
        None, False)


def test_the_brief_line_names_each_count_and_how_the_part_graph_must_carry_it():
    assert check_counts.lines(CARD) == [f"COUNTS: top_slats = 3; legs = 4 ({HOW})", ""]


def card_cli(d, profile=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d),
                        *(["--profile", str(profile)] if profile else [])], capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


def profile_with(tmp_path, keys):
    from test_intake import PROFILE
    p = tmp_path / "PROJECT-PROFILE.yaml"
    p.write_text(dump(PROFILE | ({"counts_keys": keys} if keys is not None else {})), encoding="utf-8")
    return p


def test_a_card_whose_keys_are_all_in_the_profile_counts_keys_passes_without_a_warning(tmp_path):
    d = make_asset(tmp_path, card=mutated(counts=CARD["counts"]))
    assert card_cli(d, profile_with(tmp_path, KEYS)) == (0, [])


def test_a_card_key_outside_the_profile_counts_keys_is_a_warning_not_an_error(tmp_path):
    """The key still goes to the gate; the warning tells the Concept Artist the project has not agreed on it."""
    d = make_asset(tmp_path, card=mutated(counts={"legs": 4, "drawers": 2}))
    assert card_cli(d, profile_with(tmp_path, KEYS)) == (0, [
        "cảnh báo: thẻ: counts có khóa ngoài counts_keys của profile: drawers"])


def test_a_profile_without_counts_keys_warns_about_every_card_key(tmp_path):
    d = make_asset(tmp_path, card=mutated(counts={"legs": 4}))
    assert card_cli(d, profile_with(tmp_path, None)) == (0, [
        "cảnh báo: thẻ: counts có khóa ngoài counts_keys của profile: legs"])


@pytest.mark.parametrize("value", [{"legs": -1}, {"legs": "2"}, [2], {"legs": True}, {"Legs": 2}, {"2legs": 1}])
def test_a_counts_entry_that_is_not_a_param_name_and_a_whole_number_fails_check_card(tmp_path, value):
    """The key becomes a param name and a tag in the part graph, so it must be a valid name."""
    from test_intake import messages
    assert messages(make_asset(tmp_path, card=mutated(counts=value))) == [
        "thẻ: counts sai: cần map {khóa: số nguyên ≥ 0}, khóa là tên param (chữ thường, số, _; bắt đầu bằng chữ)"]


def counted_asset(flow, root):  # noqa: F811
    """The blockout-only flow, with a synthetic card that has counts as the asset's concept card."""
    d = root / "concepts/_approved/table"
    d.mkdir(parents=True)
    (d / "asset-card.yaml").write_text(dump(mutated(asset="table", views="none", counts=CARD["counts"])),
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
    write_results(vd.parent / "final")
    vd.write_text(f"STATUS: DONE\nPROFILE_HASH: {brief_hash(flow.text(out))}\n", encoding="utf-8")
    return out, flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))


def test_a_worker_that_never_ran_the_counts_check_still_goes_back_because_ingest_runs_it(flow):  # noqa: F811
    counted_asset(flow, flow.root)
    out, said = worker_round(flow, graph(legs=3))
    assert f"COUNTS: top_slats = 3; legs = 4 ({HOW})" in flow.text(out).splitlines()
    assert said.splitlines()[0] == "house-a: worker DONE (check fail) → blockout/fix. Tiếp: giao worker → `brief house-a`"
    r = json.loads((flow.v(1) / "final/review/checks/counts.json").read_text(encoding="utf-8"))
    assert (r["overall"], r["checks"][1]["value"]) == ("fail", [
        "3 part có tag: legs, thẻ legs = 4: đặt param legs = 4 vào params và fixed_params, hoặc gắn tag: legs cho đúng "
        "4 part"])
    assert "house-a · blockout v1 · worker DONE (check fail) ·  · vòng sửa 1/3: check fail counts.json" in flow.ledger()


def test_accepted_fail_for_counts_json_is_refused_because_it_is_a_hard_gate(flow):  # noqa: F811
    from core.state import HARD_GATES
    assert "counts.json" in HARD_GATES


def test_a_graph_that_carries_every_count_goes_to_the_reviewer(flow):  # noqa: F811
    counted_asset(flow, flow.root)
    _, said = worker_round(flow, graph())
    assert json.loads(said.splitlines()[-1])["role"] == "reviewer"


def test_an_unreadable_part_graph_is_an_error_result_so_ingest_sends_it_back_instead_of_crashing(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (final / "part_graph.json").write_text("x", encoding="utf-8")
    (tmp_path / "card.yaml").write_text("type: prop\ncounts: {legs: 1}\n", encoding="utf-8")
    assert check_counts.write(final, tmp_path / "card.yaml")["overall"] == "error"
