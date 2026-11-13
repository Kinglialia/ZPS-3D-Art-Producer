"""D33: no dead time between the Producer and its agents. Nobody waits on a notification; done or not is read from disk.
D33.18b: every test here uses synthetic jobs (a long command, a hung command), never an object."""
import sys
from pathlib import Path

import pytest

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
    """The report file is the done signal (D33.8): written last, so a report on disk means the agent finished. The rule
    says so in its own words: the agent cannot resolve a decision tag."""
    assert len(ROLES) == 9
    for f in ROLES:
        text = f.read_text(encoding="utf-8")
        assert "Không chạy lệnh nền" in text and "không chờ thông báo" in text.lower(), f.name
        assert ("Ghi `<report>` là việc cuối cùng trước khi trả kết quả: file này là tín hiệu xong việc." in text
                and "D33" not in text), f.name


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


def gone(pid, wait_s=5.0):
    """True once pid no longer exists. A killed process stays a zombie until its new parent reaps it, so poll."""
    import os
    import time
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def kill_quietly(*pids):
    import os
    import signal
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_a_timeout_kills_the_whole_process_group_so_no_grandchild_keeps_writing_v14(tmp_path):
    """A tool child often starts its own children (Blender, a shell around codex). A kill of the child alone left the
    grandchild running after the timeout, still writing into vN."""
    import pytest
    import subprocess
    import heartbeat
    vd, _ = beats(tmp_path)
    pid = tmp_path / "gc.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        heartbeat.run(["sh", "-c", f"sleep 60 & echo $! > {pid}; wait"], tool="tree", vd=vd, timeout=1, every=0.3)
    gc = int(pid.read_text(encoding="utf-8"))
    try:
        assert gone(gc)
    finally:
        kill_quietly(gc)


@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP"])
def test_a_tool_stopped_by_a_signal_takes_its_child_and_grandchild_with_it_v14(tmp_path, sig):
    """The child runs in its own session so the group kill reaches every process under it. That session no longer
    hears a signal sent to the tool, so the tool turns SIGTERM and SIGHUP into a group kill before it exits."""
    import signal
    import subprocess
    import time
    vd, rows = beats(tmp_path)
    kid, pid, ready = tmp_path / "kid.pid", tmp_path / "gc.pid", tmp_path / "handlers.ready"
    code = (f"import sys; sys.path.insert(0, {str(SKILL / 'scripts')!r}); import heartbeat, pathlib, signal\n"
            f"set_handler = signal.signal\n"
            f"def spy(s, h):\n"
            f"    old = set_handler(s, h)\n"
            f"    if h is heartbeat.stop and s == heartbeat.STOP[-1]: pathlib.Path({str(ready)!r}).write_text('1')\n"
            f"    return old\n"
            f"signal.signal = spy\n"
            f"heartbeat.run(['sh', '-c', 'echo $$ > {kid}; sleep 60 & echo $! > {pid}; wait'], tool='term', "
            f"vd=pathlib.Path({str(vd)!r}), every=0.3)\n")
    tool = subprocess.Popen([sys.executable, "-c", code])
    end = time.monotonic() + 60
    while not (ready.exists() and pid.exists() and pid.read_text(encoding="utf-8").strip()):
        assert time.monotonic() < end and tool.poll() is None, "the tool never reached its signal handlers"
        time.sleep(0.05)
    sh, gc = int(kid.read_text(encoding="utf-8")), int(pid.read_text(encoding="utf-8"))
    try:
        tool.send_signal(getattr(signal, sig))
        assert tool.wait(timeout=30) == 128 + getattr(signal, sig)
        assert (gone(sh, 30), gone(gc, 30)) == (True, True)
        assert [r for r in rows() if r[1] != "running"] == [["term", "start"]]
    finally:
        kill_quietly(sh, gc)
        tool.kill() if tool.poll() is None else None


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


def test_the_usual_time_is_the_median_of_first_builds_or_of_fix_rounds_never_both_d39_3():
    """A fix round touches a few parts and a fix-scope review reads a few findings: pooled with first builds, they pull
    the median down and every first build looks late. The worker kind comes from the version (a later version of the
    step is a fix round; an evidence render is never a first build); the reviewer kind from its REVIEW_SCOPE."""
    from core import watch
    cfg = {"steps": [{"id": "model", "usual_min": {"worker": 60, "reviewer": 15}}]}

    def d(role, v, minutes, **kw):
        return {"step": "model", "role": role, "v": v, "at": "2026-11-10 09:00:00", "ingested": "2026-11-10 10:00:00",
                "duration_ms": minutes * 60000, "brief": f"production/assets/a/model/v{v}/brief-{role}.md"} | kw
    runs = [{"dispatches": [d("worker", 1, 40), d("reviewer", 1, 12, scope="full"), d("worker", 2, 8),
                            d("reviewer", 2, 3, scope="fix"), d("reviewer", 2, 11, scope="full"),
                            d("worker", 2, 2, brief="production/assets/a/model/v2/review/evidence-1/brief-worker.md")]},
            {"dispatches": [d("worker", 1, 50), d("reviewer", 1, 14), d("reviewer", 1, 4)]}]
    assert [watch.usual_s(cfg, "model", r, runs, k) / 60 for r in ("worker", "reviewer") for k in ("first", "fix")] == [
        45, 5, 12, 3.5]
    assert watch.usual_s(cfg, "model", "worker", [], "fix") / 60 == 60


def test_the_template_texture_worker_time_is_the_one_measured_number_w4():
    """Run 5 measured one step only: texture with Meshy SỬA took 15m32s for two versions, worker and reviewer
    together, so one texture worker dispatch fits in 16 minutes. Every other number is not measured yet."""
    import tomllib
    steps = tomllib.loads((SKILL / "templates/pipeline.toml").read_text(encoding="utf-8"))["steps"]
    assert next(s for s in steps if s["id"] == "texture")["usual_min"] == {"worker": 16, "reviewer": 15}


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


def age(vd, minutes):
    """Every file under vN last changed `minutes` ago: the job has been quiet that long."""
    import os
    import time
    t = time.time() - minutes * 60
    for p in [vd, *vd.rglob("*")]:
        os.utime(p, (t, t))


def utc_ago(minutes):
    import datetime as dt
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def test_a_late_stop_of_the_old_agent_never_marks_the_new_agent_that_shares_its_brief_c12(tmp_path):
    """After a new agent got the same brief, the old one stopped late. Its transcript names the same brief, so the hook
    took the new dispatch for it: `no_report` and the old agent id on the new record, the new agent shown KẸT at once
    and a third agent unlocked on the same vN. A prompt older than the dispatch belongs to an earlier dispatch."""
    f, out, j = project(tmp_path)
    tr = tmp_path / "agent-old.jsonl"
    tr.write_text(j.dumps({"type": "user", "timestamp": utc_ago(29),
                           "message": {"content": f"Đọc `{out['brief']}` trước tiên."}}) + "\n", encoding="utf-8")
    edit_job(f, at=ago(30), stopped="no_report")
    f.p("stall", "pilot-house")
    new = f.st()["dispatches"][-1]
    r = hook(tmp_path, {"agent_type": "zps-3dp-step-blockout", "agent_id": "old", "agent_transcript_path": str(tr)})
    assert (r.returncode, r.stdout) == (0, "")
    assert f.st()["dispatches"][-1] == new and "KẸT" not in f.p("next")
    tr.write_text(j.dumps({"type": "user", "timestamp": utc_ago(0),
                           "message": {"content": f"Đọc `{out['brief']}` trước tiên."}}) + "\n", encoding="utf-8")
    hook(tmp_path, {"agent_type": "zps-3dp-step-blockout", "agent_id": "b2", "agent_transcript_path": str(tr)})
    assert (f.st()["dispatches"][-1]["stopped"], f.st()["dispatches"][-1]["agent_id"]) == ("no_report", "b2")


def test_a_stalled_job_climbs_nudge_then_one_new_agent_then_the_user_and_the_ledger_logs_each_rung_d33_11(tmp_path):
    """One rule for every stall, decided by the script: max_nudges nudges (1), then the same brief to a new agent
    (never a resume of the stuck one), then waiting_human. Each rung waits stall_min before the next. A new agent goes
    out only after SubagentStop recorded that the old one stopped (D39.4): two agents never write one vN."""
    f, out, j = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    edit_job(f, stopped="no_report", agent_id="a1")
    assert "OK" not in f.p("next").split("↳")[1]
    r = f.p("stall", "pilot-house")
    assert "nudge 1/1: gửi tới agent a1 đúng câu \"Tiếp tục, báo trạng thái\"" in r
    assert "không kẹt" in f.p("stall", "pilot-house", ok=False)
    nudged = ago(11)
    edit_job(f, at=ago(30), nudged_at=nudged)
    age(vd, 20)
    led = f.p("ledger", "--tail", "1")
    assert f.p("stall", "pilot-house").splitlines() == [
        f"pilot-house: kẹt (không có nhịp tim, không có file đổi từ {nudged[11:16]}) → chưa giao lại: agent a1 chưa "
        "dừng. Dừng agent a1 trước, rồi `stall pilot-house` lại"]
    assert (len(f.st()["dispatches"]), [x["rung"] for x in f.st()["stalls"]], f.p("ledger", "--tail", "1")) == (
        1, ["nudge"], led)
    edit_job(f, stopped="no_report")
    r = f.p("stall", "pilot-house")
    new = j.loads(r.strip().splitlines()[-1])
    assert (new["role"], new["resume"], new["brief"]) == ("worker", None, out["brief"])
    d = f.st()["dispatches"]
    assert len(d) == 2 and "ended" in d[0] and d[1]["redispatch_of"] == d[0]["at"] and "ended" not in d[1]
    edit_job(f, stopped="no_report")
    r = f.p("stall", "pilot-house")
    assert "waiting_human" in r and f.st()["state"] == "waiting_human"
    assert [x["rung"] for x in f.st()["stalls"]] == ["nudge", "redispatch", "human"]
    led = f.p("ledger", "--tail", "6")
    assert "kẹt · worker · subagent dừng, không có report" in led and "nudge 1/1" in led and "giao lại cho agent mới" in led
    stats = f.p("stats", "pilot-house")
    assert "| Bước | Kẹt | Nudge | Giao lại | Hỏi anh |" in stats and "| blockout | 3 | 1 | 1 | 1 |" in stats
    r = f.p("retry", "pilot-house")
    assert f.st()["state"] == "running" and j.loads(r.strip().splitlines()[-1])["resume"] is None


def test_the_user_rung_names_the_agent_that_may_still_run_so_retry_never_adds_a_second_writer_d39_4(tmp_path):
    f, out, _ = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    edit_job(f, stopped="no_report")
    f.p("stall", "pilot-house")
    edit_job(f, at=ago(30), agent_id="b2")
    age(vd, 20)
    assert "nudge 1/1: gửi tới agent b2" in f.p("stall", "pilot-house")
    edit_job(f, nudged_at=ago(11))
    assert "waiting_human" in f.p("stall", "pilot-house")
    assert f.st()["note"].endswith("; agent b2 chưa dừng: dừng nó trước khi `retry`")


def stop_asked(f, vd):
    """Nudged, still silent: the ladder asks the Producer to stop the agent and records when it asked."""
    edit_job(f, agent_id="a1", at=ago(40))
    age(vd, 30)
    assert "nudge 1/1" in f.p("stall", "pilot-house")
    edit_job(f, nudged_at=ago(11))
    age(vd, 30)
    assert "→ chưa giao lại: agent a1 chưa dừng" in f.p("stall", "pilot-house")
    return f.st()["dispatches"][-1]["stop_asked_at"]


def test_without_a_stop_record_the_ladder_goes_on_once_the_agent_stayed_silent_a_stall_min_after_the_stop_was_asked(
        tmp_path):
    """The Codex edition has no SubagentStop hook, and on Claude the hook can die waiting on the lock: without a stop
    record the ladder stayed at rung 1 for ever. A silent stall_min after the ask is the stop record."""
    f, out, j = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    stop_asked(f, vd)
    assert "không kẹt" in f.p("stall", "pilot-house", ok=False)
    edit_job(f, stop_asked_at=ago(11))
    age(vd, 30)
    new = j.loads(f.p("stall", "pilot-house").strip().splitlines()[-1])
    assert (new["resume"], new["brief"], len(f.st()["dispatches"])) == (None, out["brief"], 2)
    edit_job(f, at=ago(30))
    age(vd, 30)
    assert "waiting_human" in f.p("stall", "pilot-house")
    assert [x["rung"] for x in f.st()["stalls"]] == ["nudge", "redispatch", "human"]


def test_a_file_change_after_the_stop_was_asked_proves_the_agent_alive_and_the_ladder_asks_again_d39_4(tmp_path):
    f, out, _ = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    stop_asked(f, vd)
    edit_job(f, stop_asked_at=ago(25))
    age(vd, 20)
    assert "→ chưa giao lại: agent a1 chưa dừng" in f.p("stall", "pilot-house")
    assert len(f.st()["dispatches"]) == 1 and f.st()["dispatches"][0]["stop_asked_at"] > ago(1)


def test_the_codex_runtime_waits_for_the_old_agent_to_stop_like_claude_so_two_agents_never_write_one_vn_d46(
        tmp_path, monkeypatch):
    """Codex 0.164.0 has `interrupt_agent` and a SubagentStop hook. Without trusted hooks there is no stop record, and
    the silent stall_min after the ask still moves the ladder on, so the wait never hangs."""
    monkeypatch.setenv("PRODUCER_RUNTIME", "codex")
    f, out, j = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    stop_asked(f, vd)
    assert len(f.st()["dispatches"]) == 1
    edit_job(f, stop_asked_at=ago(11))
    age(vd, 30)
    assert j.loads(f.p("stall", "pilot-house").strip().splitlines()[-1])["resume"] is None
    assert len(f.st()["dispatches"]) == 2


def test_a_job_is_stalled_only_when_vn_has_no_heartbeat_and_no_file_change_for_stall_min_d39_3(tmp_path):
    """The Run 5 rule (D33.11) is gone: a deadline alone flagged a slow job with a beat one minute old, and the ladder
    then sent a second agent on the same vN. Now: a worker that hangs, while a tool runs or while it thinks, writes no
    beat and no file, so it is stalled after stall_min (10). A file the worker writes, or a live beat past the
    deadline, is a slow job: `P next` says it is late, not KẸT."""
    f, out, _ = project(tmp_path)
    edit_job(f, at=ago(20))
    vd = (tmp_path / out["report"]).parent
    (vd / "heartbeat.log").write_text(f"{ago(15)} · blender render · done · exit 0\n", encoding="utf-8")
    age(vd, 15)
    assert "KẸT 15m · nudge 0/1" in f.p("next")
    assert "không có nhịp tim, không có file đổi từ" in f.p("stall", "pilot-house")
    edit_job(f, deadline=ago(5))
    age(vd, 15)
    (vd / "work").mkdir(exist_ok=True)
    (vd / "work/part_graph.json").write_text("{}", encoding="utf-8")
    nxt = f.p("next")
    assert "KẸT" not in nxt and "· trễ: quá hạn chót, còn file đổi" in nxt
    age(vd, 15)
    (vd / "heartbeat.log").write_text(f"{ago(1)} · blender render · running · cpu +3.0 s\n", encoding="utf-8")
    age(vd, 15)
    nxt = f.p("next")
    assert "KẸT" not in nxt and "· trễ: quá hạn chót, còn nhịp tim" in nxt
    assert "không kẹt" in f.p("stall", "pilot-house", ok=False)


def test_a_reviewer_writes_nothing_until_its_report_so_its_silence_counts_only_past_its_deadline_d39_3(tmp_path):
    """A reviewer reads and thinks; its only file is the report. Silence alone would flag every healthy review longer
    than stall_min, so a quiet reviewer is stalled only once its deadline has passed too."""
    import os
    from core import watch
    f, out, _ = project(tmp_path)
    vd = (tmp_path / out["report"]).parent
    st = f.st()
    rec = st["dispatches"][-1] | {"role": "reviewer", "at": ago(15), "deadline": ago(-5)}
    w = {"stall_min": 10, "deadline_factor": 2, "max_nudges": 1}
    age(vd, 15)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert watch.check(st, rec, w)["stalled"] is False
        assert watch.check(st, rec | {"deadline": ago(1)}, w)["why"].startswith("không có nhịp tim, không có file đổi từ")
    finally:
        os.chdir(cwd)


def test_the_board_labels_a_stalled_asset_kẹt_d33_17(tmp_path):
    from core import board, state
    f, out, _ = project(tmp_path)
    edit_job(f, stopped="no_report")
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cfg = state.load_cfg()
        assert board.asset_view(cfg, state.load_st("pilot-house"))["label"] == "kẹt"
    finally:
        os.chdir(cwd)


def start_wait(root):
    import subprocess
    import time
    from shared import P
    w = subprocess.Popen([sys.executable, str(P), "wait", "--every", "0.2", "--max-min", "1"], cwd=root,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lock = root / "production/wait.lock"
    end = time.monotonic() + 60
    while not (lock.exists() and lock.read_text(encoding="utf-8").strip() == str(w.pid)):
        assert time.monotonic() < end and w.poll() is None, "`P wait` never took its lock"
        time.sleep(0.05)
    return w


def test_a_second_p_wait_takes_over_and_the_first_ends_with_a_line_that_asks_nothing_d33_13_p6_1(tmp_path):
    """Waiting loops must not pile up (D33.13): the lock holds the pid of the one `P wait`. Pilot 6: the Producer ran
    `P wait` again after it ingested from the hand-back, and the refusal read like a fault. The new wait owns the lock;
    the old one sees that at its next look and ends."""
    f, out, _ = project(tmp_path)
    first = start_wait(tmp_path)
    second = start_wait(tmp_path)
    so, _ = first.communicate(timeout=30)
    assert (first.returncode, so) == (0, f"`P wait` mới (pid {second.pid}) thay lần chờ này → không cần làm gì\n")
    (tmp_path / out["report"]).write_text("STATUS: DONE\n", encoding="utf-8")
    so, _ = second.communicate(timeout=30)
    assert second.returncode == 0 and "có báo cáo" in so and "→ `ingest pilot-house`" in so
    assert not (tmp_path / "production/wait.lock").exists()


def test_a_wait_ends_once_the_dispatches_it_started_on_are_closed_though_a_new_one_runs_p6_1(tmp_path):
    """Pilot 6: the Producer ingested from the hand-back and dispatched the next agent within one 30 s look, so the
    wait never saw the report or an empty job list. It ran on for 18 minutes and then woke the Producer for a later
    report. Ingested or ended, the dispatches it started on are done, and so is the wait."""
    import json as _j
    from flowkit import A
    f, out, _ = project(tmp_path)
    w = start_wait(tmp_path)
    p = f.root / A / "status.json"
    st = _j.loads(p.read_text(encoding="utf-8"))
    st["dispatches"][-1]["ingested"] = ago(0)
    st["dispatches"].append(st["dispatches"][-1] | {"at": ago(-1)})
    st["dispatches"][-1].pop("ingested")
    p.write_text(_j.dumps(st), encoding="utf-8")
    so, _ = w.communicate(timeout=30)
    assert (w.returncode, so) == (0, "các lần giao `P wait` chờ đã đóng (đã ingest hoặc giao lại) → `next`\n")


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
    edit_job(f, stopped="no_report")
    assert "nudge 1/1: gửi tới agent z9" in f.p("stall", "pilot-house", "--agent-id", "z9")
    f.p("approvals", "set", "dispatch", "background", "--by", "chạy lô")
    assert "dispatch: background" in (tmp_path / "production/policy.yaml").read_text(encoding="utf-8")
    assert "dispatch phải là foreground|background" in f.p("approvals", "set", "dispatch", "fast", "--by", "x", ok=False)


def test_a_report_that_failed_the_contract_is_not_a_finished_job_for_wait_or_the_stall_check_d36_3(tmp_path):
    """Run 4: ingest refused the report, but it stayed at the report path, so `P wait` woke at once for the same
    report, again and again. The rejected report is set aside; the job is back to running."""
    f, out, _ = project(tmp_path)
    (tmp_path / out["report"]).write_text("STATUS: DONE\nOUTPUT: final/\n", encoding="utf-8")
    assert "có báo cáo" in f.p("wait", "--every", "0.05", "--max-min", "0.01")
    assert "thiếu PROFILE_HASH" in f.p("ingest", "pilot-house", ok=False)
    edit_job(f, stopped="report", deadline=ago(-60))
    woke = f.p("wait", "--every", "0.05", "--max-min", "0.01")
    assert woke.startswith("chưa có gì sau") and "có báo cáo" not in woke
    assert "· OK" in f.p("next") and "KẸT" not in f.p("next")
    (tmp_path / out["report"]).write_text("STATUS: DONE\nPROFILE_HASH: x\n", encoding="utf-8")
    assert "có báo cáo" in f.p("wait", "--every", "0.05", "--max-min", "0.01")


# ---- D39.1: the Stop hook of the main session (`P on-main-stop`) ----

BRIEF = "production/assets/a1/blockout/v1/brief-worker.md"
REPORT = "production/assets/a1/blockout/v1/worker-out.md"


def asset(state="running", **rec):
    """A status with one open worker dispatch; `rec` overrides or adds keys of that dispatch."""
    return {"id": "a1", "stage": "blockout", "state": state, "versions": {"blockout": 1},
            "dispatches": [{"step": "blockout", "v": 1, "role": "worker", "at": "2026-11-12 09:00:00", "brief": BRIEF} | rec]}


def stop_reason(sts, on_disk=(), sent=False):
    from core import watch
    return watch.main_stop_reason(sts, lambda p: str(p) in on_disk, lambda st, rec: sent)


def test_a_report_on_disk_for_an_open_dispatch_refuses_the_stop_and_names_the_ingest_command_d39_1():
    """Run 5 lost 4 hours because the Producer ended its turn with a finished report on disk."""
    assert stop_reason([asset()], {REPORT}) == "Còn report chưa ingest: chạy `P ingest a1 --agent-id <id subagent>`"
    assert stop_reason([asset(agent_id="ag7")], {REPORT}) == "Còn report chưa ingest: chạy `P ingest a1 --agent-id ag7`"
    review = asset("reviewing", role="reviewer", brief="production/assets/a1/blockout/v1/brief-review.md")
    assert stop_reason([review], {"production/assets/a1/blockout/v1/review-out.md"}) == (
        "Còn report chưa ingest: chạy `P ingest a1 --agent-id <id subagent>`")


def test_a_report_that_was_already_ingested_never_refuses_or_the_producer_could_not_stop_after_the_last_step_d39_1():
    assert stop_reason([asset(ingested="2026-11-12 09:30:00")], {REPORT}) is None


def test_the_stop_is_never_refused_while_the_asset_waits_for_the_human_or_the_report_is_not_there_d39_1():
    assert stop_reason([asset("waiting_human")], {REPORT}) is None
    assert stop_reason([asset("blocked")], {REPORT}) is None
    assert stop_reason([asset()], set(), sent=True) is None


def test_a_dispatch_line_nobody_sent_refuses_the_stop_but_a_background_subagent_may_run_on_d39_1():
    """Printed is not sent: `P brief` records the dispatch when it prints the line. Only a dispatch with no sign of a
    subagent refuses; a subagent that runs (a call in the transcript, a heartbeat, a recorded id or stop) is waited for."""
    line = "Còn dòng giao việc của a1 chưa giao: giao theo dòng JSON của `P brief a1` (chạy lại lệnh này nếu mất dòng)"
    assert stop_reason([asset()], set(), sent=False) == line
    assert stop_reason([asset("reviewing", role="reviewer")], set(), sent=False) == line
    assert stop_reason([asset(agent_id="ag7")], set()) is None
    assert stop_reason([asset(stopped="no_report")], set()) is None
    assert stop_reason([asset()], set(), sent=True) is None


def test_a_script_step_report_on_disk_refuses_the_stop_although_a_script_step_records_no_dispatch():
    script = {"id": "a1", "stage": "assemble", "state": "running", "versions": {"assemble": 1}, "dispatches": []}
    assert stop_reason([script], {"production/assets/a1/assemble/v1/report-script.md"}) == (
        "Còn report chưa ingest: chạy `P ingest a1`")
    assert stop_reason([script], set()) is None
    assert stop_reason([script | {"state": "review"}], {"production/assets/a1/assemble/v1/report-script.md"}) is None


def test_a_waiting_asset_does_not_hide_a_report_of_another_asset_and_a_report_wins_over_an_unsent_line_d39_1():
    other = asset() | {"id": "a2"}
    other["dispatches"][0]["brief"] = "production/assets/a2/blockout/v1/brief-worker.md"
    assert stop_reason([asset("waiting_human"), other], {"production/assets/a2/blockout/v1/worker-out.md"}) == (
        "Còn report chưa ingest: chạy `P ingest a2 --agent-id <id subagent>`")
    assert stop_reason([asset(), other], {"production/assets/a2/blockout/v1/worker-out.md"}).startswith(
        "Còn report chưa ingest: chạy `P ingest a2")


def call(name, key, text, at="2026-11-12T02:30:00.000Z", **block):
    import json as _j
    return _j.dumps({"type": "assistant", "timestamp": at, "message": {"content": [
        {"type": "tool_use", "name": name, "input": {key: text}} | block]}}) + "\n"


def test_a_dispatch_counts_as_sent_only_by_an_agent_or_sendmessage_call_after_it_that_names_the_brief_d39_1(tmp_path):
    from core import watch
    import datetime as dt
    rec = {"at": "2026-11-12 09:00:00", "brief": BRIEF}
    stamp_utc = dt.datetime.fromisoformat(rec["at"]).astimezone(dt.timezone.utc)

    def at(minutes):
        return (stamp_utc + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def sent(*lines):
        tr = tmp_path / "main.jsonl"
        tr.write_text("".join(lines), encoding="utf-8")
        return watch.sent_to_agent([str(tr)], rec)
    assert sent(call("Agent", "prompt", f"Đọc `{BRIEF}` trước tiên.", at(1))) is True
    assert sent(call("SendMessage", "message", f"Vòng sửa mới. Đọc lại `{BRIEF}` rồi làm.", at(1))) is True
    assert sent(call("Agent", "prompt", f"Đọc `{BRIEF}` trước tiên.", at(-5))) is False, "a call before this dispatch"
    assert sent(call("Agent", "prompt", "Đọc `production/assets/a2/blockout/v1/brief-worker.md`.", at(1))) is False
    assert sent(call("Bash", "command", f"cat {BRIEF}", at(1))) is False, "only a subagent call is a dispatch"
    assert sent("") is False
    assert watch.sent_to_agent([str(tmp_path / "gone.jsonl")], rec) is True, "an unreadable transcript never refuses"
    assert watch.sent_to_agent([], rec) is True, "no transcript known: never refuse"


def test_the_hook_allows_the_stop_when_it_already_continued_once_or_there_is_no_production_folder_d39_1(tmp_path, monkeypatch):
    """`stop_hook_active` is true when the turn goes on because a Stop hook refused: a second refusal would loop."""
    import json as _j
    from core import watch
    monkeypatch.chdir(tmp_path)
    assert watch.on_main_stop(_j.dumps({"hook_event_name": "Stop", "stop_hook_active": False})) is None
    (tmp_path / "production/assets/a1").mkdir(parents=True)
    (tmp_path / "production/assets/a1/status.json").write_text(_j.dumps(asset(agent_id="ag7")), encoding="utf-8")
    rep = tmp_path / REPORT
    rep.parent.mkdir(parents=True)
    rep.write_text("done", encoding="utf-8")
    on = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert watch.on_main_stop(_j.dumps(on)) == "Còn report chưa ingest: chạy `P ingest a1 --agent-id ag7`"
    assert watch.on_main_stop(_j.dumps(on | {"stop_hook_active": True})) is None
    assert watch.on_main_stop("not json") is None


def test_the_hook_reads_the_transcript_the_stop_payload_names_and_a_heartbeat_to_tell_sent_from_printed_d39_1(
        tmp_path, monkeypatch):
    import datetime as dt
    import json as _j
    from core import watch
    monkeypatch.chdir(tmp_path)
    a1 = tmp_path / "production/assets/a1"
    a1.mkdir(parents=True)
    now = dt.datetime.now().replace(microsecond=0)
    (a1 / "status.json").write_text(_j.dumps(asset(at=now.strftime("%Y-%m-%d %H:%M:%S"))), encoding="utf-8")
    sent_at = (now + dt.timedelta(seconds=30)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    tr = tmp_path / "main.jsonl"
    tr.write_text(call("Agent", "prompt", f"Đọc `{BRIEF}` trước tiên.", sent_at), encoding="utf-8")
    on = {"hook_event_name": "Stop", "stop_hook_active": False}
    never = watch.on_main_stop(_j.dumps(on | {"transcript_path": str(tmp_path / "other.jsonl")}))
    assert never is None, "an unreadable transcript never refuses"
    other = tmp_path / "other.jsonl"
    other.write_text(call("Bash", "command", "ls", sent_at), encoding="utf-8")
    line = watch.on_main_stop(_j.dumps(on | {"transcript_path": str(other)}))
    assert line and line.startswith("Còn dòng giao việc của a1 chưa giao")
    assert watch.on_main_stop(_j.dumps(on | {"transcript_path": str(tr)})) is None
    vd = a1 / "blockout/v1"
    vd.mkdir(parents=True)
    (vd / "heartbeat.log").write_text(f"{(now + dt.timedelta(seconds=40)):%Y-%m-%d %H:%M:%S} · blender · start\n", encoding="utf-8")
    assert watch.on_main_stop(_j.dumps(on | {"transcript_path": str(other)})) is None


def test_each_runtime_adapter_says_whether_a_hook_guards_the_end_of_the_turn_d39_1():
    """D46: Codex has a Stop hook too, but only in a trusted project: the Codex adapter must name the hook and the
    prose rule that guards a project without it, or the owner reads a guard that may not run."""
    editions = SKILL.parents[1] / "editions"
    claude = (editions / "claude/adapter.md").read_text(encoding="utf-8")
    codex = (editions / "codex/adapter.md").read_text(encoding="utf-8")
    assert "hook Stop (`P on-main-stop`)" in claude and "mã 2" in claude
    assert "hook Stop (`P on-main-stop`)" in codex and "mã 2" in codex
    assert "Không có hook (project chưa tin)" in codex and "chỗ chặn duy nhất" in codex


def skill_md():
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def receive_section():
    text = skill_md()
    return text[text.index("**Nhận kết quả**"):text.index("**Lệnh đổi state cũng in lệnh giao việc:**")]


def test_receiving_a_result_is_a_numbered_list_whose_first_three_rules_have_no_exception_d39_2():
    """Run 5: the old paragraph ended with 'when nothing else runs', and the Producer found that nothing else ran."""
    lines = receive_section().splitlines()
    items = [l for l in lines if l[:1].isdigit()]
    assert [l.split(".", 1)[0] for l in items] == [str(n) for n in range(1, len(items) + 1)] and len(items) >= 3
    first = " ".join(items[:3])
    assert ("`P ingest <id> --agent-id <id subagent>` ngay" in items[0] and "cùng lượt" in items[1]
            and items[2] == "3. Không kết thúc lượt khi còn report chưa ingest hoặc còn dòng giao việc chưa giao.")
    assert not any(w in first for w in ("trừ", "nếu không có", "khi không có việc"))
    assert not any(l.startswith("`P stats") for l in items), "P stats is not a rule of the list"
    assert "`P stats <id>` in bảng theo bước" in receive_section()


def test_no_runtime_text_asks_the_producer_to_pass_token_or_duration_numbers_d39_2():
    """Waiting for those numbers is what held Run 5; the script reads them from the subagent transcript."""
    editions = SKILL.parents[1] / "editions"
    for f in (SKILL / "SKILL.md", editions / "claude/adapter.md", editions / "codex/adapter.md"):
        assert "--tokens" not in f.read_text(encoding="utf-8") and "--duration-ms" not in f.read_text(encoding="utf-8"), f


def test_every_rule_of_the_old_receiving_paragraph_is_still_in_the_skill_d39_2():
    section = receive_section()
    for kept in ("Không giao thêm", "Bạn không bao giờ sửa report của worker hay reviewer.", "Đừng tự diễn giải report",
                 "Report sai contract: <dòng lỗi của script>. Viết lại `<report>` (bản cũ đã thành `.rejected-<k>.md`), rồi trả lại các dòng brief yêu cầu.",
                 "`references/runtime.md` mục Resume", "không giao lại", "reviewer `full` chấm lại khi PASS ở vòng `fix` còn key `not_checked` hoặc nhờ waive",
                 "chuyển state và in bước tiếp theo", "Không chờ số token hay thời lượng"):
        assert kept in section, kept


def test_a_doubt_about_the_reviewer_is_noted_and_asked_never_decided_and_no_reminder_goes_in_the_prompt_d39_7():
    """The Producer never opens reviewer output, so it cannot judge a verdict; a reminder in the next dispatch prompt
    would break 'Không thêm gì vào prompt'."""
    text = skill_md()
    auto = text[text.index("## Tự quyết hay hỏi"):text.index("Chỉ dừng lại hỏi người dùng khi")]
    assert "reviewer chấm sai" not in auto
    ask = text[text.index("Chỉ dừng lại hỏi người dùng khi"):text.index("## Giữ context nhỏ")]
    assert "nghi reviewer chấm sai" in ask and '`P feedback <id> "<nghi ngờ của bạn>" --action note`' in ask
    assert "nhắc nó giữ" not in text and "ở lần giao sau" not in text


def test_with_a_remote_board_the_producer_runs_next_again_after_every_board_pull_d39():
    text = skill_md()
    board = text[text.index("**Trang claude.ai**"):text.index("**Ai duyệt:**")]
    assert "rồi `P board pull`. Báo lại các dòng script in, rồi luôn chạy lại `P next`" in board
    assert "không chạy lại, trừ khi bạn vừa chạy `P board pull`" in text


def test_the_brief_of_a_step_with_an_external_command_never_tells_the_worker_to_run_it_in_the_background_d39():
    """A worker that starts a background command and ends its turn is never woken (D33.2): the brief must say to wait."""
    import tempfile
    from flowkit import AID, Flow
    from shared import pilot_project
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        f = Flow(root)
        pilot_project(root)
        toml = root / "production/pipeline.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace(
            'id = "blockout"\n', 'id = "blockout"\nexternal_command = "tool --in {request} --log {log}"\n', 1), encoding="utf-8")
        f.p("intake", AID)
        f.p("ready", AID)
        text = (root / f.brief("ext")["brief"]).read_text(encoding="utf-8")
    block = text[text.index("## Lệnh ngoài"):].split("\n## ", 1)[0]
    assert block.startswith("## Lệnh ngoài\nChạy lệnh, chờ lệnh xong;") and "tool --in " in block
    assert "nền" not in block.lower()
    setup = (SKILL / "references/setup.md").read_text(encoding="utf-8")
    assert "chạy nền" not in [l for l in setup.splitlines() if "external_command" in l][0]
