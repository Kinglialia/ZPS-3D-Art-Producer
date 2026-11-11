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
from core import briefs, loop
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


@pytest.mark.parametrize("args, out", [(["dashboard"], "dashboard.md"), (["show", AID], "show")])
def test_dashboard_and_show_write_files_so_they_refuse_the_other_runtime_folder_too(tmp_path, args, out):
    cli(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts", runtime="codex", prod="production-codex")
    cli(tmp_path, "new", AID, "--title", "House A", runtime="codex", prod="production-codex")
    (tmp_path / "production-codex/dashboard.md").unlink(missing_ok=True)
    err = cli(tmp_path, *args, runtime="claude", prod="production-codex", ok=False)
    assert err.strip() == ("LỖI: production-codex là thư mục của runtime codex, phiên này là claude: "
                           "đặt PRODUCER_ROOT=production-claude")
    assert not (tmp_path / "production-codex" / out).exists()


@pytest.mark.parametrize("prod, deliver", [(None, "deliver"), ("production-claude", "deliver-claude"),
                                           ("production-codex", "deliver-codex")])
def test_each_runtime_compares_with_the_pilot_in_its_own_deliver_folder_d22_10(tmp_path, prod, deliver):
    code = "import sys; sys.path.insert(0, sys.argv[1]); from core import briefs; print(briefs.pilot_line({'pilot_asset': 'hut'}))"
    env = {k: v for k, v in os.environ.items() if k != "PRODUCER_ROOT"} | ({"PRODUCER_ROOT": prod} if prod else {})
    out = subprocess.run([sys.executable, "-c", code, str(P.parent)], cwd=tmp_path, env=env, capture_output=True,
                         text=True, check=True).stdout
    assert out == f"PILOT: {deliver}/hut/\n"


def clock(monkeypatch, *times):
    t = iter(times)
    monkeypatch.setattr(briefs, "stamp", lambda: next(t))
    monkeypatch.setattr(loop, "stamp", lambda: next(t))


def worker_report(flow, out):
    rep = flow.root / out["report"]
    for o in ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"):
        (rep.parent / "final" / o).write_text("x", encoding="utf-8")
    rep.write_text(f"STATUS: DONE\nPROFILE_HASH: {brief_hash(flow.text(out))}\n", encoding="utf-8")


def test_a_dispatch_records_its_model_and_the_ingest_records_the_role_times_tokens_and_duration_d27_3(
        flow, monkeypatch):  # noqa: F811
    """A pilot run had tokens per step only, so nobody could tell whether the worker, the reviewer or the Producer grew."""
    clock(monkeypatch, "2026-11-10 09:00:00", "2026-11-10 09:12:30", "2026-11-10 09:12:31")
    out = flow.brief()
    worker_report(flow, out)
    flow.call(loop.ingest, Namespace(id=AID, agent_id="w1", tokens=48210, duration_ms=731000))
    assert flow.st["dispatches"] == [
        {"step": "blockout", "v": 1, "role": "worker", "model": "opus", "at": "2026-11-10 09:00:00",
         "brief": out["brief"], "agent_id": "w1", "ingested": "2026-11-10 09:12:30", "tokens": 48210,
         "duration_ms": 731000, "after": "review"},
        {"step": "blockout", "v": 1, "role": "reviewer", "model": "opus", "at": "2026-11-10 09:12:31",
         "brief": out["brief"].replace("brief-worker.md", "brief-review.md"), "scope": "full"}]
    lines = flow.ledger().splitlines()
    assert lines[-3].endswith(" · src · house-a · blockout v1 · giao worker (zps-3dp-step-blockout, opus)")
    assert lines[-2].endswith(" · src · house-a · blockout v1 · worker DONE ·  · worker giao 2026-11-10 09:00:00 · "
                              "ingest 2026-11-10 09:12:30 · token 48210 · thời lượng 731000 ms")


def test_a_runtime_that_reports_no_numbers_is_ledgered_as_having_none_never_as_zero_d27_3(flow, monkeypatch):  # noqa: F811
    clock(monkeypatch, "2026-11-10 09:00:00", "2026-11-10 09:12:30", "2026-11-10 09:12:31")
    worker_report(flow, flow.brief())
    flow.call(loop.ingest, Namespace(id=AID, agent_id="w1"))
    assert flow.ledger().splitlines()[-2].endswith(
        " · token không có số · thời lượng không có số")
    assert (flow.st["dispatches"][0]["tokens"], flow.st["dispatches"][0]["duration_ms"]) == (None, None)


def test_brief_called_again_while_its_subagent_runs_reprints_the_same_dispatch_and_records_it_once_d27_2(flow):  # noqa: F811
    first = flow.call(briefs.run, Namespace(id=AID))
    again = flow.call(briefs.run, Namespace(id=AID))
    assert (again, flow.st["versions"], len(flow.st["dispatches"])) == (first, {"blockout": 1}, 1)
    assert sum(" · giao worker " in l for l in flow.ledger().splitlines()) == 1


def test_every_offer_is_logged_with_its_reason_and_the_users_answer_so_silence_is_not_an_approval(flow):  # noqa: F811
    flow.work()
    flow.review(verdict="PASS", counts="blocker=0; major=0; minor=0; preference=0; unclear=0", top_fix=None,
                rubric="massing=pass")
    log = flow.st["offer_log"]
    assert [{k: w.get(k) for k in ("key", "step", "v", "why", "verdict", "decision")} for w in log] == [
        {"key": "house-a-blockout-v1-1", "step": "blockout", "v": 1, "why": "duyệt", "verdict": "PASS", "decision": None}]
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


def test_redoing_an_approved_step_does_not_answer_the_offer_of_a_later_step(flow):  # noqa: F811
    from core.state import load_st, save_st
    flow.work()
    flow.review(verdict="PASS", counts="blocker=0; major=0; minor=0; preference=0; unclear=0", top_fix=None,
                rubric="massing=pass")
    flow.human("approve", "đạt")
    st = load_st(AID)
    st |= {"stage": "views_front", "state": "waiting_human", "offer_key": "house-a-views_front-v1-2"}
    st["offer_log"].append({"key": "house-a-views_front-v1-2", "step": "views_front", "v": 1, "why": "duyệt",
                            "verdict": "PASS", "at": "2026-11-09 10:00"})
    save_st(st)
    flow.human("redo", "mái thấp", "blockout")
    assert [w.get("decision") for w in flow.st["offer_log"]] == ["approve", None]
