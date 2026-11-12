import json
import os
import re
import subprocess
from argparse import Namespace

import pytest

from shared import write_profile
from core import briefs, intake, limits
from core.state import all_status, load_cfg, load_st, save_st


def dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


@pytest.fixture
def proj(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    write_profile(tmp_path)
    p = tmp_path / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("blender = 2", "blender = 1"), encoding="utf-8")
    for aid, prio in (("a-hut", 1), ("b-barn", 2)):
        intake.new(Namespace(id=aid, title=aid, type="asset", priority=prio, deadline=None), load_cfg())
        intake.ready(Namespace(ids=[aid]))
    capsys.readouterr()
    return tmp_path


def pid_file(root, name, pid):
    d = root / "production/pids/blender"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.pid").write_text(f"{pid}\n", encoding="utf-8")


def next_lines(capsys):
    limits.show_next(Namespace(session=False))
    return [l for l in capsys.readouterr().out.splitlines() if l.startswith("[")]


def test_a_slot_is_held_by_an_open_worker_dispatch_or_a_live_process_and_one_asset_counts_once_c17(proj):
    """C17: a pid file lives only while a tool runs, so a count of live pid files alone, read when the Producer
    dispatched, let a second worker out while the first one thought. A slot is now held from a worker's dispatch to its
    ingest, and also by a live process of a script step or another tool. A worker inside Blender is one asset, not two.
    A dead or broken pid file, a reviewer and an ingested worker hold none."""
    def n(r="blender"):
        return limits.used(load_cfg(), r, all_status())
    pid_file(proj, "y-dead", dead_pid())
    (proj / "production/pids/blender/z-junk.pid").write_text("not a pid", encoding="utf-8")
    assert (n(), n("meshy")) == (0, 0)
    briefs.run(Namespace(id="a-hut"))
    assert n() == 1
    pid_file(proj, f"a-hut-{os.getpid()}", os.getpid())
    assert n() == 1
    pid_file(proj, "x-live", os.getpid())
    assert n() == 2
    st = load_st("a-hut")
    st["dispatches"][-1]["ingested"] = st["dispatches"][-1]["at"]
    st["state"] = "review"
    save_st(st)
    (proj / f"production/pids/blender/a-hut-{os.getpid()}.pid").unlink()
    assert n() == 1


def test_the_threads_of_one_codex_image_run_are_one_asset_holding_one_slot(proj):
    """gen_image_codex.py writes one pid file per thread, `<id>-<pid>-<k>.pid`; each counted as another owner, so one
    asset with two threads filled both codex_image slots."""
    d = proj / "production/pids/codex_image"
    d.mkdir(parents=True)
    for name in (f"a-hut-{os.getpid()}", f"a-hut-{os.getpid()}-1", f"a-hut-{os.getpid()}-2"):
        (d / f"{name}.pid").write_text(str(os.getpid()), encoding="utf-8")
    assert limits.used(load_cfg(), "codex_image", all_status()) == 1
    (d / f"b-barn-{os.getpid()}-1.pid").write_text(str(os.getpid()), encoding="utf-8")
    assert limits.used(load_cfg(), "codex_image", all_status()) == 2


def test_next_offers_dispatch_only_while_a_slot_is_free_and_counts_its_own_offers(proj, capsys):
    assert next_lines(capsys) == ["[a-hut] blockout/todo → giao worker → `brief a-hut`",
                                  "[b-barn] blockout/todo → chờ slot blender"]
    pid_file(proj, "x-live", os.getpid())
    assert next_lines(capsys)[0] == "[a-hut] blockout/todo → chờ slot blender"


def test_a_running_worker_holds_its_slot_while_it_thinks_without_a_blender_process_c17(proj, capsys):
    briefs.run(Namespace(id="a-hut"))
    pid_file(proj, "a-hut", dead_pid())
    assert next_lines(capsys) == ["[a-hut] blockout/running → đang chờ subagent (mất kết nối thì `brief a-hut` để giao lại)",
                                  "[b-barn] blockout/todo → chờ slot blender"]


def test_an_ingest_holds_back_the_next_worker_while_another_asset_holds_the_slot_c17(proj, capsys, monkeypatch):
    """dispatch_next and `P next` read one rule, so the ingest never prints a dispatch `P next` would refuse."""
    from core import loop
    briefs.run(Namespace(id="a-hut"))
    st = load_st("b-barn")
    st["state"] = "fix"
    capsys.readouterr()
    loop.dispatch_next(load_cfg(), st)
    assert capsys.readouterr().out == "b-barn: chờ slot blender, chưa giao\n"
    st = load_st("a-hut")
    st["dispatches"][-1]["ingested"] = st["dispatches"][-1]["at"]
    st["state"] = "review"
    save_st(st)
    sent = []
    monkeypatch.setattr(briefs, "run", lambda a: sent.append(a.id))
    loop.dispatch_next(load_cfg(), load_st("b-barn") | {"state": "fix"})
    assert sent == ["b-barn"]


def test_wait_wakes_when_an_asset_can_go_out_now_and_names_it_c17(proj):
    """P wait woke only on a report, a stall or no running job: an asset in review sat still while another ran."""
    from core import watch
    briefs.run(Namespace(id="a-hut"))
    w = {"stall_min": 10, "deadline_factor": 2, "max_nudges": 1}
    assert watch.wake(w) == []
    st = load_st("b-barn")
    st["state"] = "review"
    save_st(st)
    assert watch.wake(w) == ["b-barn: giao được ngay (blockout/review) → `brief b-barn`"]
    st["state"] = "fix"
    save_st(st)
    assert watch.wake(w) == []
    st = load_st("a-hut")
    st["dispatches"][-1]["ingested"] = st["dispatches"][-1]["at"]
    st["state"] = "waiting_human"
    save_st(st)
    assert watch.wake(w) == ["không có việc nào đang chạy → `next`", "b-barn: giao được ngay (blockout/fix) → `brief b-barn`"]


def test_worker_brief_has_no_pid_wrapper_because_run_tool_writes_the_blender_pid(proj, capsys):
    briefs.run(Namespace(id="a-hut"))
    text = (proj / "production/assets/a-hut/blockout/v1/brief-worker.md").read_text(encoding="utf-8")
    assert [l for l in text.splitlines() if l.startswith("RUN: ")]
    assert not re.search(r"echo \$!|wait \$!|PID", text)
    assert (proj / "production/pids/blender").is_dir()


def test_done_enabled_counts_as_finished_in_next(proj, capsys):
    for aid in ("a-hut", "b-barn"):
        st = load_st(aid)
        st["state"] = "done_enabled"
        save_st(st)
    limits.show_next(Namespace(session=False))
    assert capsys.readouterr().out.splitlines()[0].startswith("0 asset đang chạy · 2 done · ")


def views_none_parked_at_blockout(root, model_on):
    """A `views: none` card skips the views step (D35), so the step after blockout is model."""
    card = root / "concepts/a-hut"
    card.mkdir(parents=True)
    (card / "asset-card.yaml").write_text("views: none\n", encoding="utf-8")
    st = load_st("a-hut")
    st |= {"concept_dir": str(card), "stage": "blockout", "state": "done_enabled"}
    save_st(st)
    if not model_on:
        p = root / "production/pipeline.toml"
        p.write_text(p.read_text(encoding="utf-8").replace('id = "model"\n', 'id = "model"\nenabled = false\n', 1),
                     encoding="utf-8")


def test_next_tells_a_views_none_asset_to_retry_once_model_is_enabled(proj, capsys):
    views_none_parked_at_blockout(proj, model_on=True)
    assert "[a-hut] blockout/done_enabled → bước model đã bật → `retry a-hut`" in next_lines(capsys)


def test_next_does_not_offer_a_retry_for_a_skipped_views_step_while_model_is_still_off(proj, capsys):
    """views is enabled, but this asset never runs it: `retry` would only park it again."""
    views_none_parked_at_blockout(proj, model_on=False)
    assert not [l for l in next_lines(capsys) if "đã bật" in l]


def test_next_reads_no_card_of_an_asset_that_is_not_parked_at_done_enabled(proj, capsys):
    """Only the retry hint needs the card; a finished asset with a broken card must not stop `P next`."""
    card = proj / "concepts/a-hut"
    card.mkdir(parents=True)
    (card / "asset-card.yaml").write_text("views: [unclosed\n", encoding="utf-8")
    st = load_st("a-hut")
    st |= {"concept_dir": str(card), "state": "done"}
    save_st(st)
    assert next_lines(capsys) == ["[b-barn] blockout/todo → giao worker → `brief b-barn`"]


def test_a_retry_out_of_a_stall_goes_out_although_another_asset_took_the_slot_c17(proj, capsys):
    """While b-barn waited on the user after a stall, a-hut took the one blender slot. `retry` moves b-barn to running:
    held back there, it had no dispatch, `P next` showed no "chờ slot" for it, and `P wait` never named it."""
    from core import loop
    briefs.run(Namespace(id="b-barn"))
    st = load_st("b-barn")
    st["dispatches"][-1]["ended"] = {"at": st["dispatches"][-1]["at"], "why": "x"}
    st |= {"state": "waiting_human", "stalled_from": "running"}
    save_st(st)
    briefs.run(Namespace(id="a-hut"))
    capsys.readouterr()
    loop.retry(Namespace(id="b-barn"))
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "b-barn: → running. Tiếp: đang chờ subagent (mất kết nối thì `brief b-barn` để giao lại)"
    assert json.loads(out[-1])["brief"] == "production/assets/b-barn/blockout/v1/brief-worker.md"
