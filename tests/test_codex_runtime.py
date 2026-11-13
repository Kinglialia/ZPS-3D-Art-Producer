"""D46: the runtime side of the Codex edition on Codex 0.164.0. The three hooks get Codex-shaped stdin and must answer
in a form Codex accepts; tokens and time come from rollout files. Every rollout here is invented: the record and field
names match a real rollout, the numbers do not."""
import datetime as dt
import json
import re
import subprocess
import sys

import pytest

from core import session, watch
from flowkit import AID, Flow
from shared import P, fixed_line, pilot_project


def utc(local_stamp: str, plus_s: float = 0) -> str:
    at = dt.datetime.fromisoformat(local_stamp).astimezone(dt.timezone.utc) + dt.timedelta(seconds=plus_s)
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def u(inp, cached, out, reasoning=0, write=0):
    return {"input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": write, "output_tokens": out,
            "reasoning_output_tokens": reasoning, "total_tokens": inp + out}


def add(a, b):
    return {k: a[k] + b[k] for k in a}


def meta(ts, sub=False):
    src = {"subagent": {"thread_spawn": {"parent_thread_id": "th-0", "depth": 1, "agent_role": "default"}}} if sub else "cli"
    return {"timestamp": ts, "type": "session_meta", "payload": {"id": "th-1", "source": src}}


def tok(ts, last, total):
    return {"timestamp": ts, "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_token_usage": total, "last_token_usage": last}}}


def task(ts, text):
    """A child receives its spawn_agent message as plain text in the `encrypted_content` item (real rollouts, 128 of
    129 spawns); the `input_text` item does not hold it."""
    return {"timestamp": ts, "type": "response_item", "payload": {
        "type": "agent_message", "author": "/root", "recipient": "/root/w1",
        "content": [{"type": "input_text", "text": "từ /root"}, {"type": "encrypted_content", "encrypted_content": text}]}}


def call(ts, name, **args):
    return {"timestamp": ts, "type": "response_item", "payload": {
        "type": "function_call", "name": name, "namespace": "collaboration", "arguments": json.dumps(args),
        "call_id": "c1"}}


def write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n{broken line\n", encoding="utf-8")
    return path


def sub_rollout(path, at, brief):
    """A sub-agent rollout: an earlier round (forked, so its running total starts at the parent's), the task that names
    the brief, two responses and one repeat of the second running total, and a response after the ingest."""
    early, a, b = u(9000, 0, 900), u(1200, 1000, 300, reasoning=100), u(800, 600, 200, write=50)
    t0 = add(u(50000, 0, 5000), early)
    return write(path, [meta(utc(at, -3600), sub=True), tok(utc(at, -3600), early, t0),
                        task(utc(at), f"Vai của bạn nằm trong `agents/x.md`: đọc file đó trước tiên. Rồi đọc `{brief}`."),
                        tok(utc(at, 5), a, add(t0, a)), tok(utc(at, 9), b, add(add(t0, a), b)),
                        tok(utc(at, 9.5), b, add(add(t0, a), b)), tok(utc(at, 7200), u(5, 0, 5), u(1, 1, 1))])


def test_a_dispatch_sums_the_last_usage_of_each_response_in_its_window_and_maps_codex_fields_to_the_four_columns(tmp_path):
    """The running total of a forked thread starts at its parent's total, and Codex repeats a token_count with the same
    total: summing totals, or every line, would count tokens that are not this dispatch's. The four columns add up to
    Codex's own `total_tokens` (1500 + 1000)."""
    at = "2026-11-13 10:00:00"
    f = sub_rollout(tmp_path / "rollout-sub.jsonl", at, "production/assets/a1/views/v1/brief-worker.md")
    got = session.agent_usage([f], at, "2026-11-13 10:30:00")
    assert got == {"input": 350, "output": 500, "cache_read": 1600, "cache_creation": 50, "duration_ms": 9500,
                   "format": "codex"}
    assert sum(got[k] for k in session.SPLIT.values()) == 2500
    assert session.agent_usage([f, f], at, "2026-11-13 10:30:00") == got, "a copy of the file counts once"
    assert session.agent_usage([f], "2026-11-13 11:00:00", "2026-11-13 11:30:00") is None


def test_producer_tokens_come_from_the_main_rollout_and_never_from_a_sub_agent_rollout(tmp_path):
    main = write(tmp_path / "rollout-main.jsonl", [
        meta("2026-11-13T03:00:00.000Z"), tok("2026-11-13T03:01:00.000Z", u(1000, 800, 500), u(1000, 800, 500)),
        tok("2026-11-13T03:01:01.000Z", u(1000, 800, 500), u(1000, 800, 500)),
        tok("2026-11-13T03:02:00.000Z", u(600, 500, 100), u(1600, 1300, 600))])
    sub = sub_rollout(tmp_path / "rollout-sub.jsonl", "2026-11-13 10:00:00", "b.md")
    assert session.main_usage([str(main), str(sub)]) == [(session.local("2026-11-13T03:01:00.000Z"), 700, 800),
                                                         (session.local("2026-11-13T03:02:00.000Z"), 200, 500)]


def flow(tmp_path):
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    return f, f.brief("b1 brief")


def hook(root, cmd, payload):
    return subprocess.run([sys.executable, str(P), *cmd], cwd=root, input=json.dumps(payload), capture_output=True,
                          text=True)


BASE = {"session_id": "019a-main", "cwd": "/p", "model": "gpt-x"}


def test_subagent_stop_from_codex_records_the_rollout_and_ingest_reads_tokens_and_time_from_it(tmp_path):
    """The Codex Producer spawns a plain agent that reads its role file, so `agent_type` is not a zps-3dp name: the
    rollout and the brief it names identify the dispatch. stdout stays empty, the one form both runtimes accept."""
    f, out = flow(tmp_path)
    st_file = tmp_path / "production/assets" / AID / "status.json"
    st = json.loads(st_file.read_text(encoding="utf-8"))
    st["dispatches"][-1]["at"] = at = (dt.datetime.now() - dt.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    st_file.write_text(json.dumps(st), encoding="utf-8")
    tr = sub_rollout(tmp_path / "rollout-sub.jsonl", at, out["brief"])
    r = hook(tmp_path, ["on-stop"], BASE | {
        "transcript_path": "/s/rollout-main.jsonl", "hook_event_name": "SubagentStop", "agent_id": "th-77",
        "agent_type": "default", "agent_transcript_path": str(tr), "stop_hook_active": False,
        "last_assistant_message": "xong"})
    assert (r.returncode, r.stdout) == (0, ""), r.stderr
    assert "on-stop worker · không có report" in r.stderr
    got = f.st()["dispatches"][-1]
    assert (got["stopped"], got["agent_id"], got["transcript"]) == ("no_report", "th-77", str(tr))
    vd = (tmp_path / out["report"]).parent
    f.outputs(vd, "blockout", "b1")
    ph = re.search(r"^PROFILE_HASH: (\S+)$", f.cp["b1 brief"]["text"], re.M).group(1)
    (tmp_path / out["report"]).write_text(f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: none\nPROFILE_HASH: {ph}\n"
                                          + fixed_line(tmp_path, AID), encoding="utf-8")
    f.p("ingest", AID)
    worker = f.st()["dispatches"][0]
    assert (worker["tokens"], worker["duration_ms"], worker["usage"]["format"]) == (2500, 9500, "codex")


def test_a_codex_agent_whose_rollout_names_no_open_brief_is_left_alone(tmp_path):
    f, out = flow(tmp_path)
    tr = sub_rollout(tmp_path / "rollout-sub.jsonl", f.st()["dispatches"][-1]["at"], "production/assets/x/b.md")
    r = hook(tmp_path, ["on-stop"], BASE | {"hook_event_name": "SubagentStop", "agent_id": "th-9", "agent_type": "default",
                                            "agent_transcript_path": str(tr)})
    assert (r.returncode, r.stdout, "stopped" in f.st()["dispatches"][-1]) == (0, "", False)


def test_the_codex_stop_hook_refuses_with_exit_2_and_stderr_and_allows_with_no_output_after_a_spawn_agent_call(tmp_path):
    """Codex refuses plain text on the stdout of a Stop hook; exit 2 with the reason on stderr continues the turn, as on
    Claude Code. A `spawn_agent`, `followup_task` or `send_message` call that names the brief is the sign it was sent."""
    f, out = flow(tmp_path)
    rec = f.st()["dispatches"][-1]
    main = tmp_path / "rollout-main.jsonl"
    stop = BASE | {"transcript_path": str(main), "hook_event_name": "Stop", "turn_id": "t1", "stop_hook_active": False,
                   "last_assistant_message": "Đã giao."}
    write(main, [meta(utc(rec["at"], -60)), call(utc(rec["at"], 5), "exec_command", cmd=f"cat {out['brief']}")])
    r = hook(tmp_path, ["on-main-stop"], stop)
    assert (r.returncode, r.stdout) == (2, "")
    assert r.stderr.startswith(f"Còn dòng giao việc của {AID} chưa giao")
    for name, args in (("spawn_agent", {"task_name": "w1", "message": f"Rồi đọc `{out['brief']}`."}),
                       ("followup_task", {"target": "w1", "message": f"Đọc lại `{out['brief']}`."}),
                       ("send_message", {"target": "w1", "message": f"Đọc lại `{out['brief']}`."})):
        write(main, [meta(utc(rec["at"], -60)), call(utc(rec["at"], 5), name, **args)])
        r = hook(tmp_path, ["on-main-stop"], stop)
        assert (r.returncode, r.stdout, r.stderr) == (0, "", ""), name
    write(main, [meta(utc(rec["at"], -60)), call(utc(rec["at"], -30), "spawn_agent", task_name="w0",
                                                  message=f"`{out['brief']}`")])
    assert hook(tmp_path, ["on-main-stop"], stop).returncode == 2, "a call before the dispatch is an earlier one"
    assert hook(tmp_path, ["on-main-stop"], stop | {"stop_hook_active": True}).returncode == 0


def test_the_codex_session_start_hook_records_the_main_rollout_and_prints_plain_context(tmp_path):
    """Plain stdout of a SessionStart hook reaches the Codex model as context, as on Claude Code."""
    subprocess.run([sys.executable, str(P), "init", "--project", "Pilot", "--concepts", "concepts"], cwd=tmp_path,
                   check=True, capture_output=True)
    r = hook(tmp_path, ["next", "--session"], BASE | {"transcript_path": "/s/rollout-main.jsonl",
                                                      "hook_event_name": "SessionStart", "source": "startup"})
    assert r.returncode == 0 and r.stdout.startswith("[producer] Dùng skill zps-3dp-producer")
    doc = json.loads((tmp_path / "production/session.json").read_text(encoding="utf-8"))
    assert (doc["source"], doc["session_id"], doc["transcripts"]) == ("startup", "019a-main", ["/s/rollout-main.jsonl"])


def test_a_codex_rollout_names_the_brief_only_in_the_task_a_parent_sent_or_a_user_message_it_did_not_inherit():
    b = "production/assets/a1/views/v1/brief-worker.md"
    msg = lambda role, **md: {"type": "response_item", "payload": {  # noqa: E731
        "type": "message", "role": role, "content": [{"type": "input_text", "text": f"đọc `{b}`"}]}, "metadata": md}
    assert session.asks_for(task("x", f"đọc `{b}`"), b) is True
    assert session.asks_for(msg("user"), b) is True
    assert session.asks_for(msg("user", inherited_user_message=True), b) is False
    assert session.asks_for(msg("assistant"), b) is False
    assert session.asks_for(task("x", f"đọc `{b}`") | {"metadata": {"inherited_user_message": True}}, b) is False, (
        "a forked worker inherits the Producer's items, and an inherited agent_message is the Producer's own task")
    assert watch.calls(call("x", "spawn_agent", message=b)) == [json.dumps({"message": b})]
    assert watch.calls(call("x", "wait_agent", timeout_ms=1)) == []


def test_the_stop_hook_allows_the_stop_of_a_sub_agent_thread_that_the_main_thread_would_be_refused(tmp_path):
    """The Codex Stop hook is project-wide: if Codex fires it in a worker thread, the Producer's "not yet sent" line
    must not keep the worker from stopping."""
    f, out = flow(tmp_path)
    at = f.st()["dispatches"][-1]["at"]
    main, sub = write(tmp_path / "rollout-main.jsonl", [meta(utc(at, -60))]), sub_rollout(
        tmp_path / "rollout-sub.jsonl", at, out["brief"])
    stop = BASE | {"hook_event_name": "Stop", "turn_id": "t1", "stop_hook_active": False}
    got = {n: hook(tmp_path, ["on-main-stop"], stop | {"transcript_path": str(p)})
           for n, p in (("main", main), ("sub", sub), ("missing", tmp_path / "gone.jsonl"))}
    assert {n: (r.returncode, r.stdout, r.stderr[:24]) for n, r in got.items()} == {
        "main": (2, "", f"Còn dòng giao việc của {AID}"[:24]), "sub": (0, "", ""), "missing": (0, "", "")}


def test_the_session_start_hook_of_a_sub_agent_thread_prints_nothing_and_records_nothing(tmp_path):
    """A worker that got the Producer's `next` text as context could take the Producer's job."""
    subprocess.run([sys.executable, str(P), "init", "--project", "Pilot", "--concepts", "concepts"], cwd=tmp_path,
                   check=True, capture_output=True)
    sub = sub_rollout(tmp_path / "rollout-sub.jsonl", "2026-11-13 10:00:00", "b.md")
    start = BASE | {"hook_event_name": "SessionStart", "source": "startup"}
    r = hook(tmp_path, ["next", "--session"], start | {"transcript_path": str(sub)})
    assert (r.returncode, r.stdout, (tmp_path / "production/session.json").exists()) == (0, "", False)
    main = write(tmp_path / "rollout-main.jsonl", [meta("2026-11-13T03:00:00.000Z")])
    claude = tmp_path / "claude.jsonl"
    claude.write_text(json.dumps({"type": "user", "sessionId": "s1", "message": {"role": "user", "content": "hi"}}) + "\n",
                      encoding="utf-8")
    for tp in (main, claude):
        r = hook(tmp_path, ["next", "--session"], start | {"transcript_path": str(tp)})
        assert r.stdout.startswith("[producer] Dùng skill zps-3dp-producer"), tp.name
    doc = json.loads((tmp_path / "production/session.json").read_text(encoding="utf-8"))
    assert doc["transcripts"] == [str(main), str(claude)]


def edition(monkeypatch, runtime):
    monkeypatch.setattr(session, "EDITION", {"runtime": runtime} if runtime else {})


def claude_line(ts, kind="assistant", text="hi", mid="m1", inp=10, out=5):
    if kind == "user":
        return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}
    return {"type": "assistant", "timestamp": ts, "message": {"id": mid, "usage": {"input_tokens": inp, "output_tokens": out}}}


@pytest.mark.parametrize("runtime, want", [("claude", ["claude"]), ("codex", ["codex"]), (None, ["claude", "codex"])])
def test_each_edition_counts_producer_tokens_only_from_its_own_transcript_format_and_the_source_tree_from_both(
        tmp_path, monkeypatch, runtime, want):
    """Both editions can share production/: the Codex SessionStart hook adds its rollout to session.json, and the Claude
    edition counted the token_count rows of that rollout as Claude Producer tokens."""
    edition(monkeypatch, runtime)
    codex = write(tmp_path / "rollout-main.jsonl", [meta("2026-11-13T03:00:00.000Z"), tok(
        "2026-11-13T03:01:00.000Z", u(1000, 800, 500), u(1000, 800, 500))])
    claude = write(tmp_path / "claude.jsonl", [claude_line("2026-11-13T04:00:00.000Z")])
    rows = {"codex": (session.local("2026-11-13T03:01:00.000Z"), 700, 800),
            "claude": (session.local("2026-11-13T04:00:00.000Z"), 15, 0)}
    assert session.main_usage([str(claude), str(codex)]) == [rows[k] for k in want]


@pytest.mark.parametrize("runtime, want", [("claude", 10), ("codex", 2500), (None, 2510)])
def test_each_edition_counts_dispatch_tokens_only_from_its_own_transcript_format(tmp_path, monkeypatch, runtime, want):
    edition(monkeypatch, runtime)
    at = "2026-11-13 10:00:00"
    sub = sub_rollout(tmp_path / "rollout-sub.jsonl", at, "b.md")
    claude = write(tmp_path / "agent-a1.jsonl", [claude_line(utc(at, 3), mid="m2", inp=7, out=3)])
    assert session.agent_numbers([claude, sub], at, "2026-11-13 10:30:00")[0] == want


@pytest.mark.parametrize("runtime, kept", [("claude", ["claude", "missing"]), ("codex", ["codex", "missing"]),
                                           (None, ["codex", "claude", "missing"])])
def test_the_session_start_hook_records_only_its_own_format_and_prints_nothing_for_the_other(tmp_path, monkeypatch,
                                                                                              runtime, kept):
    """A transcript that is not written yet has no format: it is recorded, as before."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "production").mkdir()
    edition(monkeypatch, runtime)
    paths = {"codex": write(tmp_path / "rollout-main.jsonl", [meta("2026-11-13T03:00:00.000Z")]),
             "claude": write(tmp_path / "claude.jsonl", [claude_line("2026-11-13T04:00:00.000Z", "user")]),
             "missing": tmp_path / "not-yet.jsonl"}
    got = {n: session.record(json.dumps({"session_id": "s1", "source": "startup", "transcript_path": str(p)}))
           for n, p in paths.items()}
    assert [n for n, d in got.items() if d is session.SUB] == [n for n in paths if n not in kept]
    assert session.load()["transcripts"] == [str(paths[n]) for n in kept]


@pytest.mark.parametrize("runtime, refused", [("claude", ["claude"]), ("codex", ["codex"]), (None, ["claude", "codex"])])
def test_a_stop_hook_given_a_transcript_of_the_other_edition_allows_the_stop(tmp_path, monkeypatch, runtime, refused):
    f, out = flow(tmp_path)
    at = f.st()["dispatches"][-1]["at"]
    monkeypatch.chdir(tmp_path)
    edition(monkeypatch, runtime)
    paths = {"claude": write(tmp_path / "claude.jsonl", [claude_line(utc(at, -60), "user")]),
             "codex": write(tmp_path / "rollout-main.jsonl", [meta(utc(at, -60))])}
    stop = BASE | {"hook_event_name": "Stop", "turn_id": "t1", "stop_hook_active": False}
    assert [n for n, p in paths.items() if watch.on_main_stop(json.dumps(stop | {"transcript_path": str(p)}))] == refused


@pytest.mark.parametrize("runtime", ["claude", "codex", None])
@pytest.mark.parametrize("fmt", ["claude", "codex"])
def test_a_subagent_stop_hook_records_a_stop_only_from_a_transcript_of_its_own_edition(tmp_path, monkeypatch, runtime,
                                                                                       fmt):
    f, out = flow(tmp_path)
    at = f.st()["dispatches"][-1]["at"]
    tr = (sub_rollout(tmp_path / "rollout-sub.jsonl", at, out["brief"]) if fmt == "codex" else
          write(tmp_path / "agent-a1.jsonl", [claude_line(utc(at, 1), "user", f"Đọc `{out['brief']}` trước tiên.")]))
    monkeypatch.chdir(tmp_path)
    edition(monkeypatch, runtime)
    got = watch.on_stop(json.dumps(BASE | {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_transcript_path": str(
        tr), "agent_type": "zps-3dp-step-blockout" if fmt == "claude" else "default"}))
    assert (got is not None, "stopped" in f.st()["dispatches"][-1]) == (runtime in (None, fmt),) * 2


def test_a_main_transcript_line_whose_message_is_not_an_object_is_skipped_not_a_crash(tmp_path):
    """A crash in the Stop hook allows the stop, so a bad line before the real call would hide a dispatch not sent."""
    rec = {"at": "2026-11-13 10:00:00", "brief": "production/assets/a1/blockout/v1/brief-worker.md"}
    p = tmp_path / "main.jsonl"
    p.write_text(json.dumps({"type": "assistant", "timestamp": utc(rec["at"], 5), "message": f"`{rec['brief']}`"}) + "\n"
                 + json.dumps(call(utc(rec["at"], 6), "spawn_agent", message=rec["brief"])) + "\n", encoding="utf-8")
    assert watch.sent_to_agent([str(p)], rec) is True
