"""Runtime identity (producer.md §16, D22.9, D22.10): every ledger line names its runtime, each runtime writes only its
own production-<runtime>/ and deliver-<runtime>/, and the data P compare needs (dispatch model, tokens, offers and the
user's answer) is in status.json."""
import json
import os
import re
import subprocess
import sys
from argparse import Namespace

import pytest

from shared import P, brief_hash
from core import loop
from test_loop import AID, flow  # noqa: F401


def cli(root, *args, runtime=None, prod=None, ok=True):
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME")}
    env |= ({"PRODUCER_RUNTIME": runtime} if runtime else {}) | ({"PRODUCER_ROOT": prod} if prod else {})
    r = subprocess.run([sys.executable, str(P), *args], cwd=root, env=env, capture_output=True, text=True)
    assert (r.returncode == 0) is ok, r.stderr
    return r.stdout if ok else r.stderr


def ledger_runtimes(path):
    return [re.match(r"^- \d{4}-\d\d-\d\d \d\d:\d\d · (\w+) · ", l)[1] for l in path.read_text(encoding="utf-8").splitlines()
            if l.startswith("- ")]


def test_every_ledger_line_names_the_runtime_that_wrote_it_so_compare_never_mixes_two_ledgers(tmp_path):
    cli(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts", runtime="codex", prod="production-codex")
    cli(tmp_path, "new", AID, "--title", "House A", runtime="codex", prod="production-codex")
    cli(tmp_path, "rule", "giữ mái đỏ", runtime="codex", prod="production-codex")
    assert ledger_runtimes(tmp_path / "production-codex/ledger.md") == ["codex", "codex"]


def test_the_source_tree_writes_src_until_a_build_stamps_the_edition(tmp_path):
    cli(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    cli(tmp_path, "new", AID, "--title", "House A")
    assert ledger_runtimes(tmp_path / "production/ledger.md") == ["src"]


def test_one_edition_cannot_write_into_the_other_runtime_folder_during_an_ab_run(tmp_path):
    cli(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts", runtime="codex", prod="production-codex")
    err = cli(tmp_path, "new", AID, "--title", "House A", runtime="claude", prod="production-codex", ok=False)
    assert err.strip() == ("LỖI: production-codex là thư mục của runtime codex, phiên này là claude: "
                           "đặt PRODUCER_ROOT=production-claude")
    assert not (tmp_path / "production-codex/assets" / AID).exists()


@pytest.mark.parametrize("prod, deliver", [(None, "deliver"), ("production-claude", "deliver-claude"),
                                           ("production-codex", "deliver-codex")])
def test_each_runtime_compares_with_the_pilot_in_its_own_deliver_folder_d22_10(tmp_path, prod, deliver):
    code = "import sys; sys.path.insert(0, sys.argv[1]); from core import briefs; print(briefs.pilot_line({'pilot_asset': 'hut'}))"
    env = {k: v for k, v in os.environ.items() if k != "PRODUCER_ROOT"} | ({"PRODUCER_ROOT": prod} if prod else {})
    out = subprocess.run([sys.executable, "-c", code, str(P.parent)], cwd=tmp_path, env=env, capture_output=True,
                         text=True, check=True).stdout
    assert out == f"PILOT: {deliver}/hut/\n"


def test_a_dispatch_records_its_model_and_the_ingest_records_the_tokens_the_runtime_reported(flow):  # noqa: F811
    out = flow.brief()
    rep = flow.root / out["report"]
    for o in ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"):
        (rep.parent / "final" / o).write_text("x", encoding="utf-8")
    rep.write_text(f"STATUS: DONE\nPROFILE_HASH: {brief_hash(flow.text(out))}\n", encoding="utf-8")
    flow.call(loop.ingest, Namespace(id=AID, agent_id="w1", tokens=48210))
    d = flow.st["dispatches"]
    assert [{k: x[k] for k in ("step", "v", "role", "model", "tokens")} for x in d] == [
        {"step": "blockout", "v": 1, "role": "worker", "model": "opus", "tokens": 48210}]
    lines = flow.ledger().splitlines()
    assert lines[-2].endswith(" · src · house-a · blockout v1 · giao worker (zps-3dp-step-blockout, opus)")
    assert lines[-1].endswith(" · src · house-a · blockout v1 · worker DONE ·  · tokens 48210")


def test_every_offer_is_logged_with_its_reason_and_the_users_answer_so_silence_is_not_an_approval(flow):  # noqa: F811
    flow.work()
    flow.review(verdict="PASS", counts="blocker=0; major=0; minor=0; preference=0; unclear=0", top_fix=None,
                rubric="massing=pass")
    log = flow.st["offer_log"]
    assert [{k: w.get(k) for k in ("key", "step", "v", "why", "verdict", "decision")} for w in log] == [
        {"key": "blockout-v1-1", "step": "blockout", "v": 1, "why": "duyệt", "verdict": "PASS", "decision": None}]
    flow.human("approve", "đạt")
    assert flow.st["offer_log"][0]["decision"] == "approve"
    assert list(flow.st["approved_at"]) == ["blockout"]


def test_a_note_does_not_count_as_an_answer_to_the_offer(flow):  # noqa: F811
    flow.work()
    flow.review(verdict="PASS", counts="blocker=0; major=0; minor=0; preference=0; unclear=0", top_fix=None,
                rubric="massing=pass")
    flow.human("note", "để xem")
    assert "decision" not in flow.st["offer_log"][0]
    assert json.loads((flow.root / f"production/assets/{AID}/status.json").read_text(encoding="utf-8"))["state"] == \
        "waiting_human"
