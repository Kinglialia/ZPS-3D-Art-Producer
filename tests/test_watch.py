"""D33: no dead time between the Producer and its agents. Nobody waits on a notification; done or not is read from disk.
D33.18b: every test here uses synthetic jobs (a long command, a hung command), never an object."""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer"
ROLES = sorted([*SKILL.glob("agents/zps-3dp-*.md"), *SKILL.glob("agents/*/zps-3dp-*.md")])


def test_no_role_file_tool_or_brief_template_ever_asks_for_a_background_command_d33_2():
    """A subagent that starts a background command and ends its turn is never woken (anthropics/claude-code #108836):
    the pipeline stands still until the user types. Nothing a worker or reviewer reads may offer that flag."""
    shipped = [p for p in [*SKILL.glob("agents/**/*.md"), *SKILL.glob("agents/**/*.py"), SKILL / "scripts/core/briefs.py",
                           SKILL / "scripts/core/texture.py"] if ".deps" not in p.parts]
    assert len(shipped) > 40
    assert [p.name for p in shipped if "run_in_background" in p.read_text(encoding="utf-8")] == []


def test_every_worker_and_reviewer_role_file_forbids_background_commands_and_writes_its_report_last_d33_2_d33_8():
    """The report file is the done signal (D33.8): written last, so a report on disk means the agent finished."""
    assert len(ROLES) == 9
    for f in ROLES:
        text = f.read_text(encoding="utf-8")
        assert "Không chạy lệnh nền" in text and "D33.2" in text, f.name
        assert "Ghi `<report>` là việc cuối cùng trước khi trả kết quả" in text and "(D33.8)" in text, f.name


def test_every_agent_file_caps_its_turns_so_a_looping_agent_stops_instead_of_running_on_d33_6():
    """`maxTurns` is an agent frontmatter key of Claude Code 2.1.318 ("Maximum number of agentic turns (API
    round-trips) before stopping"). Run 5 used 45 turns for a blockout worker and 12 for its reviewer, so the caps are
    about 8x those: a cap a normal run hits would stop good work. An agent cut by the cap writes no report; P on-stop
    records that and the stall rule takes over (D33.9, D33.11)."""
    import build
    caps = {f.stem: build.frontmatter(f.read_text(encoding="utf-8")).get("maxTurns") for f in ROLES}
    assert caps == {n: ("400" if n.startswith("zps-3dp-step") else "100") for n in caps}


def test_the_settings_snippet_raises_the_bash_timeouts_and_the_brief_asks_for_the_same_cap_d33_4():
    """Claude Code 2.1.318 reads BASH_DEFAULT_TIMEOUT_MS (default 120000) and BASH_MAX_TIMEOUT_MS (default 600000) from
    the environment; settings `env` sets them. A worker or the Producer asking Bash for more than the max gets less, so
    every role file and SKILL.md ask for exactly the max (the brief has no room: 4096-byte budget)."""
    import json
    env = json.loads((SKILL / "templates/settings.snippet.json").read_text(encoding="utf-8"))["env"]
    assert env == {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"}
    asks = [f"timeout: {env['BASH_MAX_TIMEOUT_MS']}` cho Bash" in f.read_text(encoding="utf-8")
            for f in ROLES if f.name.startswith("zps-3dp-step")]
    assert asks == [True] * 4 and f"`timeout` {env['BASH_MAX_TIMEOUT_MS']}" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_the_merge_adds_a_missing_timeout_and_never_changes_one_the_user_set_d33_4():
    import settings_merge as M
    want = {"env": {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"}, "permissions": {"allow": []},
            "hooks": {}}
    mine = {"env": {"BASH_DEFAULT_TIMEOUT_MS": "900000", "OTHER": "1"}}
    assert M.missing(mine, want)["env"] == {"BASH_MAX_TIMEOUT_MS": "3600000"}
    assert M.merge(mine, want)["env"] == {"BASH_DEFAULT_TIMEOUT_MS": "900000", "OTHER": "1",
                                          "BASH_MAX_TIMEOUT_MS": "3600000"}
    assert M.missing(M.merge(mine, want), want)["env"] == {}


def beats(tmp_path):
    vd = tmp_path / "production/assets/a1/stepx/v1"
    vd.mkdir(parents=True)
    return vd, lambda: [r.split(" · ")[1:3] for r in (vd / "heartbeat.log").read_text(encoding="utf-8").splitlines()]


def test_a_hung_child_writes_no_heartbeat_between_start_and_end_so_its_silence_shows_d33_7(tmp_path):
    """A heartbeat by the clock alone would let a hung process look alive (D33.7). `sleep` uses no CPU and prints
    nothing: only the start and the end lines."""
    import heartbeat
    vd, rows = beats(tmp_path)
    r = heartbeat.run(["sleep", "2.5"], tool="hung", vd=vd, every=0.5)
    assert r.returncode == 0 and rows() == [["hung", "start"], ["hung", "done"]]


def test_a_busy_child_keeps_beating_on_cpu_alone_so_a_long_silent_render_is_not_taken_for_stuck_d33_7(tmp_path):
    import heartbeat
    vd, rows = beats(tmp_path)
    busy = "import time\nt = time.time()\nwhile time.time() - t < 3:\n    pass\n"
    heartbeat.run([sys.executable, "-c", busy], tool="busy", vd=vd, every=0.7)
    got = rows()
    assert got[0] == ["busy", "start"] and got[-1] == ["busy", "done"]
    assert got[1:-1].count(["busy", "running"]) >= 2 and len(got) == got.count(["busy", "running"]) + 2


def test_a_child_that_only_prints_keeps_beating_on_output_growth_and_its_output_is_returned_d33_7(tmp_path):
    import heartbeat
    vd, rows = beats(tmp_path)
    r = heartbeat.run(["sh", "-c", "for i in 1 2 3 4 5 6; do echo line$i; sleep 0.4; done"], tool="talk", vd=vd,
                      every=0.6)
    assert r.stdout.split() == [f"line{i}" for i in range(1, 7)]
    assert rows().count(["talk", "running"]) >= 2


def test_a_timeout_kills_the_child_raises_as_subprocess_does_and_logs_it_d33_7(tmp_path):
    import heartbeat
    import pytest
    import subprocess
    vd, rows = beats(tmp_path)
    with pytest.raises(subprocess.TimeoutExpired):
        heartbeat.run(["sleep", "30"], tool="hang", vd=vd, timeout=1, every=0.5)
    assert rows() == [["hang", "start"], ["hang", "timeout"]]
    assert heartbeat.vdir_of(vd / "work/meshy/call-1") == vd and heartbeat.vdir_of(tmp_path / "x/v1") is None


# ---- D33.9–18: on-stop, deadline, stall rule, P next, P wait, stats, board (synthetic jobs only) ----

def project(tmp_path):
    import json as _j
    from flowkit import AID, Flow
    from shared import pilot_project
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    out = f.brief("b1 brief")
    return f, out, _j


def edit_job(f, **kw):
    import json as _j
    from flowkit import A
    p = f.root / A / "status.json"
    st = _j.loads(p.read_text(encoding="utf-8"))
    st["dispatches"][-1] |= kw
    p.write_text(_j.dumps(st), encoding="utf-8")


def ago(minutes):
    import datetime as dt
    return (dt.datetime.now() - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def hook(root, payload):
    import json as _j
    import subprocess
    from shared import P
    r = subprocess.run([sys.executable, str(P), "on-stop"], cwd=root, input=_j.dumps(payload), capture_output=True,
                       text=True)
    return r


def test_a_dispatch_gets_a_deadline_from_the_step_default_and_later_from_the_median_of_earlier_runs_d33_10(tmp_path):
    """No run yet: pipeline.toml usual_min (blockout worker 40) × deadline_factor 2 = 80 minutes, in the ledger too."""
    import datetime as dt
    f, out, _ = project(tmp_path)
    rec = f.st()["dispatches"][0]
    span = dt.datetime.fromisoformat(rec["deadline"]) - dt.datetime.fromisoformat(rec["at"])
    assert span == dt.timedelta(minutes=80)
    assert f"giao worker (zps-3dp-step-blockout, opus) · hạn chót {rec['deadline']}" in f.p("ledger", "--tail", "1")
    from core import watch
    cfg = {"steps": [{"id": "blockout", "usual_min": {"worker": 40}}]}
    runs = [{"dispatches": [{"step": "blockout", "role": "worker", "at": "2026-11-10 09:00:00",
                             "ingested": "2026-11-10 09:10:00", "duration_ms": ms} for ms in (60000, 120000, 600000)]}]
    assert watch.usual_s(cfg, "blockout", "worker", runs) == 120


def test_subagent_stop_records_the_stop_on_disk_when_the_producer_never_hears_of_it_d33_9(tmp_path):
    """The notification to the Producer can be lost (anthropics/claude-code #89505). The hook matches the dispatch by
    the brief the subagent's prompt names and writes whether the report exists; the asset then shows as stalled."""
    f, out, j = project(tmp_path)
    tr = tmp_path / "agent-a5.jsonl"
    tr.write_text(j.dumps({"type": "user", "message": {"content": f"Đọc `{out['brief']}` trước tiên."}}) + "\n",
                  encoding="utf-8")
    other = hook(tmp_path, {"agent_type": "general-purpose", "agent_id": "x", "agent_transcript_path": str(tr)})
    assert (other.returncode, other.stdout, "stopped" in f.st()["dispatches"][0]) == (0, "", False)
    r = hook(tmp_path, {"agent_type": "zps-3dp-step-blockout", "agent_id": "a5", "agent_transcript_path": str(tr)})
    assert r.returncode == 0, r.stderr
    rec = f.st()["dispatches"][0]
    assert (rec["stopped"], rec["agent_id"], rec["transcript"]) == ("no_report", "a5", str(tr))
    assert "on-stop worker · không có report" in f.p("ledger", "--tail", "1")
    nxt = f.p("next")
    assert "blockout v1 · worker" in nxt and "KẸT" in nxt and "→ `stall pilot-house`" in nxt
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    assert hook(empty, {"agent_type": "zps-3dp-step-blockout"}).returncode == 0
    assert hook(tmp_path, "not json").returncode == 0


def test_a_stalled_job_climbs_nudge_then_one_new_agent_then_the_user_and_the_ledger_logs_each_rung_d33_11(tmp_path):
    """One rule for every stall, decided by the script: max_nudges nudges (1), then the same brief to a new agent
    (never a resume of the stuck one), then waiting_human. Each rung waits stall_min before the next."""
    f, out, j = project(tmp_path)
    edit_job(f, deadline=ago(5), agent_id="a1")
    assert "OK" not in f.p("next").split("↳")[1]
    r = f.p("stall", "pilot-house")
    assert "nudge 1/1: gửi tới agent a1 đúng câu \"Tiếp tục, báo trạng thái\"" in r
    assert "không kẹt" in f.p("stall", "pilot-house", ok=False)
    edit_job(f, nudged_at=ago(11))
    r = f.p("stall", "pilot-house")
    new = j.loads(r.strip().splitlines()[-1])
    assert (new["role"], new["resume"], new["brief"]) == ("worker", None, out["brief"])
    d = f.st()["dispatches"]
    assert len(d) == 2 and "ended" in d[0] and d[1]["redispatch_of"] == d[0]["at"] and "ended" not in d[1]
    edit_job(f, deadline=ago(1))
    r = f.p("stall", "pilot-house")
    assert "waiting_human" in r and f.st()["state"] == "waiting_human"
    assert [x["rung"] for x in f.st()["stalls"]] == ["nudge", "redispatch", "human"]
    led = f.p("ledger", "--tail", "6")
    assert "kẹt · worker · quá hạn chót" in led and "nudge 1/1" in led and "giao lại cho agent mới" in led
    stats = f.p("stats", "pilot-house")
    assert "| Bước | Kẹt | Nudge | Giao lại | Hỏi anh |" in stats and "| blockout | 3 | 1 | 1 | 1 |" in stats
    r = f.p("retry", "pilot-house")
    assert f.st()["state"] == "running" and j.loads(r.strip().splitlines()[-1])["resume"] is None


def test_silence_counts_only_while_a_tool_runs_so_a_thinking_worker_is_not_stuck_but_a_hung_tool_is_d33_11(tmp_path):
    f, out, _ = project(tmp_path)
    edit_job(f, at=ago(20))
    vd = (tmp_path / out["report"]).parent
    (vd / "heartbeat.log").write_text(f"{ago(15)} · blender render · done · exit 0\n", encoding="utf-8")
    assert "· OK" in f.p("next")
    (vd / "heartbeat.log").write_text(f"{ago(15)} · blender render · running · cpu +3.0 s\n", encoding="utf-8")
    nxt = f.p("next")
    assert "KẸT 15m · nudge 0/1" in nxt and "không có nhịp tim mới" in f.p("stall", "pilot-house")


def test_the_board_labels_a_stalled_asset_kẹt_d33_17(tmp_path):
    from core import board, state
    f, out, _ = project(tmp_path)
    edit_job(f, deadline=ago(1))
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cfg = state.load_cfg()
        assert board.asset_view(cfg, state.load_st("pilot-house"))["label"] == "kẹt"
    finally:
        os.chdir(cwd)


def test_a_second_p_wait_is_refused_while_one_runs_and_the_first_wakes_on_the_report_d33_13(tmp_path):
    """Waiting loops must not pile up (D33.13): the lock holds the pid of the one `P wait`."""
    import subprocess
    import time
    from shared import P
    f, out, _ = project(tmp_path)
    first = subprocess.Popen([sys.executable, str(P), "wait", "--every", "0.2", "--max-min", "1"], cwd=tmp_path,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lock = tmp_path / "production/wait.lock"
    for _ in range(100):
        if lock.exists():
            break
        time.sleep(0.05)
    second = subprocess.run([sys.executable, str(P), "wait", "--every", "0.2", "--max-min", "1"], cwd=tmp_path,
                            capture_output=True, text=True)
    assert second.returncode == 1 and "đã có một `P wait` đang chạy" in second.stderr
    (tmp_path / out["report"]).write_text("STATUS: DONE\n", encoding="utf-8")
    so, _ = first.communicate(timeout=30)
    assert first.returncode == 0 and "có báo cáo" in so and "→ `ingest pilot-house`" in so
    assert not lock.exists()


def test_policy_takes_only_known_dispatch_modes_and_watch_numbers_and_falls_back_to_the_template_d33_14_18():
    from core import policy
    assert policy.check({"dispatch": "fast"}) == ["dispatch: phải là foreground|background"]
    assert policy.check({"watch": {"stall_min": 0, "nap": 1}}) == [
        "watch.stall_min: phải là số > 0", "watch.nap: khóa không hợp lệ (stall_min|deadline_factor|max_nudges)"]
    assert policy.watch({}) == {"stall_min": 10, "deadline_factor": 2, "max_nudges": 1}
    assert policy.watch({"watch": {"max_nudges": 0}})["max_nudges"] == 0 and policy.dispatch({}) == "foreground"


def test_a_subagent_cut_by_max_turns_is_nudged_with_the_id_its_stop_hook_gave_without_editing_any_file_d33_6_d33_11(
        tmp_path):
    """maxTurns stops an agent before it can write BLOCKED; SubagentStop records no_report and the agent id, so the
    first rung resumes that agent. The Producer can also pass the id it got at launch."""
    f, out, j = project(tmp_path)
    tr = tmp_path / "agent-m4.jsonl"
    tr.write_text(j.dumps({"type": "user", "message": {"content": f"Đọc `{out['brief']}` trước tiên."}}) + "\n",
                  encoding="utf-8")
    assert hook(tmp_path, {"agent_type": "zps-3dp-step-blockout", "agent_id": "m4",
                           "agent_transcript_path": str(tr)}).returncode == 0
    assert "nudge 1/1: gửi tới agent m4" in f.p("stall", "pilot-house")
    assert "stopped" not in f.st()["dispatches"][0]


def test_stall_takes_the_agent_id_from_the_producer_and_dispatch_mode_has_one_writer_d33_11_d33_14(tmp_path):
    f, out, _ = project(tmp_path)
    edit_job(f, deadline=ago(1))
    assert "nudge 1/1: gửi tới agent z9" in f.p("stall", "pilot-house", "--agent-id", "z9")
    f.p("approvals", "set", "dispatch", "background", "--by", "chạy lô")
    assert "dispatch: background" in (tmp_path / "production/policy.yaml").read_text(encoding="utf-8")
    assert "dispatch phải là foreground|background" in f.p("approvals", "set", "dispatch", "fast", "--by", "x", ok=False)
