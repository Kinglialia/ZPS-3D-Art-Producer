"""`P stats` (D27.3, D30.10, D31.4): time and tokens per step and role, and the Producer wait. A pilot run knew only tokens per
step, so the decision to keep the reviewer with the Producer rests on this table: a Producer wait over 15% of a step is
a review. A pilot run spent over a million tokens on reviewers, so R1-R3 (D31) are judged by the reviewer split per round kind."""
import datetime as dt
import json
import re
import subprocess
import sys

from shared import P
from core import session, stats
from flowkit import AID
from test_resolved_notes import to_model

CFG = {"steps": [{"id": "blockout"}, {"id": "views"}, {"id": "model"}]}
HEAD = ("| Bước | Thời gian bước | Worker | Reviewer đầu | Reviewer sửa | Reviewer cuối | Chờ Producer | Chờ anh "
        "| Token worker | Token reviewer đầu | Token reviewer sửa | Token reviewer cuối | Token Producer | report_fallback |")


def d(step, role, at, ingested=None, after=None, **kw):
    return {"step": step, "v": 1, "role": role, "model": None, "at": at,
            **({"ingested": ingested, "after": after} if ingested else {}), **kw}


def t(s):
    return dt.datetime.fromisoformat(s)


ST = {
    "approved": {"blockout": 2}, "approved_at": {"blockout": "2026-11-10 09:45", "model": "2026-11-10 08:00"},
    "offer_log": [{"key": "a-blockout-v2-1", "step": "blockout", "v": 2, "why": "duyệt", "at": "2026-11-10 09:31",
                   "decision": "approve", "decided": "2026-11-10 09:45"},
                  {"key": "a-model-v2-2", "step": "model", "v": 2, "why": "duyệt", "at": "2026-11-10 12:21"}],
    "dispatches": [
        d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:10:00", "review", tokens=50000, duration_ms=590000),
        d("blockout", "reviewer", "2026-11-10 09:10:30", "2026-11-10 09:14:30", "fix", tokens=None, fallback=True,
          scope="full"),
        d("blockout", "worker", "2026-11-10 09:15:30", "2026-11-10 09:25:00", "review", tokens=30000),
        d("blockout", "reviewer", "2026-11-10 09:25:00", "2026-11-10 09:28:00", "review", tokens=20000, scope="fix"),
        d("blockout", "reviewer", "2026-11-10 09:28:30", "2026-11-10 09:31:30", "waiting_human", tokens=15000,
          scope="full"),
        d("model", "worker", "2026-11-10 12:00:00", "2026-11-10 12:10:00", "review", tokens=1000),
        d("model", "reviewer", "2026-11-10 12:10:00", "2026-11-10 12:12:00", "fix", tokens=100),
        d("model", "worker", "2026-11-10 12:13:00", "2026-11-10 12:20:00", "review", tokens=2000),
        d("model", "reviewer", "2026-11-10 12:20:00", "2026-11-10 12:21:00", "waiting_human", tokens=200),
        d("views", "worker", "2026-11-10 13:00:00"),
    ]}
USAGE = [(t("2026-11-10 09:05:00"), 1000), (t("2026-11-10 09:40:00"), 500), (t("2026-11-10 09:50:00"), 7),
         (t("2026-11-10 12:05:00"), 300), (t("2026-11-10 13:30:00"), 40)]


def test_stats_splits_reviewer_rounds_by_scope_and_times_each_step_from_first_worker_to_approval_d31_4():
    """blockout: a `full` first review, a `fix` round, a closing `full`. model has dispatches from before REVIEW_SCOPE:
    the first review counts as the first round, the second as a fix round, none as the closing one. model's stale
    approved_at (a reopened step) does not end its window: the step is not approved."""
    assert stats.table(CFG, ST, USAGE) == [
        HEAD, "|" + "---|" * 14,
        "| blockout | 45m00s | 19m20s | 4m00s | 3m00s | 3m00s | 2m00s | 14m00s | 80000 | không có số | 20000 | 15000 "
        "| 1500 | 1 |",
        "| views | chưa duyệt | không có số | — | — | — | — | — | không có số | — | — | — | 40 | 0 |",
        "| model | chưa duyệt | 17m00s | 2m00s | 1m00s | — | 1m00s | — | 3000 | 100 | 200 | — | 340 | 0 |"]


def test_the_producer_tokens_stored_at_approval_come_before_the_transcript_d41():
    """The transcript is gone (or never found) when `P stats` runs after the approval: the stored number answers. A
    step that was reopened has no approval, so the stored number of its old window must not show."""
    stored = ST | {"producer_usage": {"blockout": {"tokens": 1234, "from": "2026-11-10 09:00:00",
                                                    "to": "2026-11-10 09:45:00", "dup": 0},
                                      "model": {"tokens": 777, "from": "2026-11-10 12:00:00", "to": "2026-11-10 12:30:00",
                                                "dup": 0}}}
    rows = stats.table(CFG, stored, "không có số")
    assert [r.split(" | ")[-2] for r in rows[2:]] == ["1234", "không có số", "không có số"]


def test_producer_tokens_count_each_main_session_message_once_and_skip_subagent_and_broken_lines_d30_10(tmp_path):
    """Claude Code repeats one message's usage on every content-block line; counting each line would triple the
    Producer's share. Subagent lines are already in the worker and reviewer columns."""
    ok, side = tmp_path / "main.jsonl", "2026-11-10T02:06:00.000Z"
    u = {"input_tokens": 2, "output_tokens": 486, "cache_creation_input_tokens": 24389, "cache_read_input_tokens": 54953}
    line = lambda mid, ts, **kw: json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": mid, "usage": u}, **kw})  # noqa: E731
    ok.write_text("\n".join([
        line("m1", "2026-11-10T02:05:00.000Z"), line("m1", "2026-11-10T02:05:01.000Z"),
        line("s1", side, isSidechain=True), "{not json", json.dumps({"type": "user", "message": {"content": "hi"}}),
        json.dumps({"type": "assistant", "timestamp": side, "message": {"id": "m9"}}),
        line("m2", "2026-11-10T02:07:00.000Z")]) + "\n", encoding="utf-8")
    assert session.main_usage([str(ok)]) == [(session.local("2026-11-10T02:05:00.000Z"), 79830),
                                             (session.local("2026-11-10T02:07:00.000Z"), 79830)]
    assert session.main_usage([str(ok), str(tmp_path / "gone.jsonl")]) is None


def test_a_transcript_without_any_usage_line_or_a_step_without_messages_shows_no_number_never_zero(tmp_path, monkeypatch):
    """D27.3: a missing number is never written as 0; a step with dispatches always had Producer turns."""
    junk = tmp_path / "junk.jsonl"
    junk.write_text("{not json\n" + json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(session, "OUT", tmp_path / "session.json")
    (tmp_path / "session.json").write_text(json.dumps({"transcripts": [str(junk)]}), encoding="utf-8")
    assert stats.producer_usage() == "không có số"
    rows = stats.table(CFG, ST, [(t("2026-11-10 13:30:00"), 40)])
    assert [r.split(" | ")[-2] for r in rows[2:]] == ["không có số", "40", "40"]


def test_an_unreadable_transcript_shows_no_number_in_either_edition(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "OUT", tmp_path / "session.json")
    (tmp_path / "session.json").write_text(json.dumps({"transcripts": [str(tmp_path / "gone.jsonl")]}), encoding="utf-8")
    assert stats.producer_usage() == "không có số"
    (tmp_path / "session.json").write_text("{broken", encoding="utf-8")
    assert stats.producer_usage() == "không có số"
    assert stats.table(CFG, ST, stats.producer_usage())[2].endswith(" | 15000 | không có số | 1 |")
    rollout = tmp_path / "rollout-main.jsonl"
    last = {"input_tokens": 900, "cached_input_tokens": 700, "output_tokens": 100, "total_tokens": 1000}
    rollout.write_text(json.dumps({"timestamp": "2026-11-10T02:00:00.000Z", "type": "session_meta", "payload": {}}) + "\n"
                       + json.dumps({"timestamp": "2026-11-10T02:05:00.000Z", "type": "event_msg", "payload": {
                           "type": "token_count", "info": {"total_token_usage": last, "last_token_usage": last}}}) + "\n",
                       encoding="utf-8")
    (tmp_path / "session.json").write_text(json.dumps({"transcripts": [str(rollout)]}), encoding="utf-8")
    assert stats.producer_usage() == [(session.local("2026-11-10T02:05:00.000Z"), 1000)], (
        "D46: the Codex edition reads its rollout; 'chưa hỗ trợ' is gone")


def hook(root, payload, **kw):
    r = subprocess.run([sys.executable, str(P), "next", "--session"], cwd=root, capture_output=True, text=True,
                       **({"input": payload} if "stdin" not in kw else kw))
    assert r.returncode == 0, r.stderr
    return r.stdout


def saved(root):
    doc = json.loads((root / "production/session.json").read_text(encoding="utf-8"))
    doc.pop("at")
    return doc


def test_the_session_start_hook_records_its_source_and_every_main_transcript_so_stats_and_d29_can_read_them(tmp_path):
    """D29.4 deletes only on `startup` or `clear`: the hook's `source` must reach the file. `/clear` starts a new transcript, and
    the Producer tokens of a run are the sum over all of them."""
    subprocess.run([sys.executable, str(P), "init", "--project", "Pilot", "--concepts", "concepts"], cwd=tmp_path,
                   check=True, capture_output=True)
    first = {"session_id": "s1", "transcript_path": "/t/a.jsonl", "source": "startup", "hook_event_name": "SessionStart"}
    assert hook(tmp_path, json.dumps(first)).startswith("[producer] Dùng skill zps-3dp-producer")
    assert saved(tmp_path) == {"session_id": "s1", "source": "startup", "transcript_path": "/t/a.jsonl",
                               "transcripts": ["/t/a.jsonl"]}
    hook(tmp_path, json.dumps(first | {"source": "resume"}))
    hook(tmp_path, json.dumps(first | {"session_id": "s2", "transcript_path": "/t/b.jsonl", "source": "clear"}))
    assert saved(tmp_path) == {"session_id": "s2", "source": "clear", "transcript_path": "/t/b.jsonl",
                               "transcripts": ["/t/a.jsonl", "/t/b.jsonl"]}


def test_a_hand_run_or_broken_hook_input_leaves_session_json_alone_and_next_still_prints(tmp_path):
    subprocess.run([sys.executable, str(P), "init", "--project", "Pilot", "--concepts", "concepts"], cwd=tmp_path,
                   check=True, capture_output=True)
    for out in (hook(tmp_path, "{not json"), hook(tmp_path, None, stdin=subprocess.DEVNULL), hook(tmp_path, "[1]")):
        assert out.startswith("[producer] ")
    assert not (tmp_path / "production/session.json").exists()


def test_p_stats_reads_the_dispatches_of_a_real_run_one_row_per_step_d27_3(tmp_path):
    f = to_model(tmp_path)
    rows = f.p("stats", AID).splitlines()
    assert rows[0] == HEAD
    # D30.5: approving views dispatched the model worker, so the model row is open with no reviewer yet.
    assert [r.split(" | ")[0] for r in rows[2:]] == ["| blockout", "| views", "| model"]
    assert [r.split(" | ")[-2] for r in rows[2:]] == ["không có số"] * 3
    assert rows[4] == ("| model | chưa duyệt | không có số | — | — | — | — | — | không có số | — | — | — | không có số "
                       "| 0 |")


def utc(local_stamp: str, plus_s: float = 0) -> str:
    at = dt.datetime.fromisoformat(local_stamp).astimezone(dt.timezone.utc) + dt.timedelta(seconds=plus_s)
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def agent_lines(at: str, brief: str, agent: str) -> str:
    """A synthetic subagent transcript: the Producer's prompt, two API messages in the dispatch (one repeated per content
    block, as Claude Code writes it), one from an earlier round of the same agent and one after the ingest."""
    u = lambda i, o: {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": 0,  # noqa: E731
                      "cache_read_input_tokens": 0}
    rows = [{"type": "assistant", "timestamp": utc(at, -3600), "agentId": agent, "isSidechain": True,
             "message": {"id": "m0", "usage": u(9000, 9000)}},
            {"type": "user", "timestamp": utc(at), "agentId": agent, "isSidechain": True,
             "message": {"role": "user", "content": f"Đọc `{brief}` trước tiên: đó là toàn bộ yêu cầu của bạn."}},
            {"type": "assistant", "timestamp": utc(at, 0.1), "isSidechain": True, "message": {"id": "m1", "usage": u(100, 20)}},
            {"type": "assistant", "timestamp": utc(at, 0.1), "isSidechain": True, "message": {"id": "m1", "usage": u(100, 20)}},
            {"type": "assistant", "timestamp": utc(at, 0.6), "isSidechain": True, "message": {"id": "m2", "usage": u(10, 20)}},
            {"type": "assistant", "timestamp": utc(at, 7200), "isSidechain": True, "message": {"id": "m9", "usage": u(5, 5)}}]
    return "\n".join(json.dumps(r) for r in rows) + "\n{broken line\n"


def test_ingest_without_numbers_takes_tokens_and_time_from_the_subagent_transcript_so_the_producer_never_waits_d33_22(
        tmp_path):
    """Run 5: the Producer ended its turn five times to wait for a subagent's token and time numbers, and the notification
    that carried them started no new turn (4h13m of 5h58m idle). `ingest` must not need them: the script reads the
    subagent's own transcript. The same agent sits in two session folders (a resumed session copies it): each API
    message counts once, and only the messages of this dispatch count (m0 is an earlier round, m9 is after ingest)."""
    from flowkit import Flow
    from shared import fixed_line, pilot_project
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    out = f.brief("b1 brief")
    rec = f.st()["dispatches"][-1]
    assert rec["brief"] == out["brief"]
    mains = [tmp_path / "t" / f"s{i}.jsonl" for i in (1, 2)]
    for m in mains:
        (m.with_suffix("") / "subagents").mkdir(parents=True)
        m.write_text("", encoding="utf-8")
        (m.with_suffix("") / "subagents" / "agent-a1.jsonl").write_text(agent_lines(rec["at"], out["brief"], "a1"),
                                                                       encoding="utf-8")
    (tmp_path / "production/session.json").write_text(json.dumps({"transcripts": [str(m) for m in mains]}),
                                                      encoding="utf-8")
    vd = (tmp_path / out["report"]).parent
    f.outputs(vd, "blockout", "b1")
    ph = re.search(r"^PROFILE_HASH: (\S+)$", f.cp["b1 brief"]["text"], re.M).group(1)
    (tmp_path / out["report"]).write_text(f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: none\nPROFILE_HASH: {ph}\n"
                                          + fixed_line(tmp_path, AID), encoding="utf-8")
    f.p("ingest", AID, "--agent-id", "a1")
    worker = f.st()["dispatches"][0]
    assert (worker["tokens"], worker["duration_ms"], worker["agent_id"]) == (150, 600, "a1")
    assert "token 150 · thời lượng 600 ms" in f.p("ledger", "--tail", "2")


def test_a_reviewer_ingested_before_its_transcript_was_found_gets_its_number_at_the_next_stats_d33_22(tmp_path):
    """The Producer passes no agent id for a reviewer; its transcript is found by the brief its prompt names. A number
    missing at ingest is never 0: `P stats` reads the transcript again, and the dispatch keeps "không có số" on disk."""
    from flowkit import Flow
    from shared import pilot_project
    from flowkit import counts
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    f.review("b1", verdict="PASS", counts=counts(), top_fix=None)
    rv = f.st()["dispatches"][1]
    assert rv["role"] == "reviewer" and rv["tokens"] is None and rv["brief"].endswith("brief-review.md")
    main = tmp_path / "t" / "s1.jsonl"
    (main.with_suffix("") / "subagents").mkdir(parents=True)
    (main.with_suffix("") / "subagents" / "agent-r7.jsonl").write_text(agent_lines(rv["at"], rv["brief"], "r7"),
                                                                       encoding="utf-8")
    (main.with_suffix("") / "subagents" / "agent-w9.jsonl").write_text(
        agent_lines(rv["at"], "production/assets/other/blockout/v1/brief-review.md", "w9"), encoding="utf-8")
    (tmp_path / "production/session.json").write_text(json.dumps({"transcripts": [str(main)]}), encoding="utf-8")
    row = f.p("stats", AID).splitlines()[2].split(" | ")
    assert row[0] == "| blockout" and row[HEAD.split(" | ").index("Token reviewer đầu")] == "150"
    assert f.st()["dispatches"][1]["tokens"] is None


def test_a_full_review_of_a_new_version_is_a_fix_round_and_only_a_rereview_of_the_same_version_is_final_d38_3():
    """D38.3: a fix round whose worker covered every blocking finding is judged `full`; counting it as the closing
    review would hide the fix rounds and show a closing cost that no longer exists. A served crop goes on its round."""
    def r(v, at, scope, **kw):
        return d("blockout", "reviewer", f"2026-11-10 09:{at}:00", f"2026-11-10 09:{at + 1}:00", "fix", tokens=10 * at,
                 scope=scope) | {"v": v} | kw
    st = {"dispatches": [d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:09:00", "review", tokens=1),
                         r(1, 10, "full"), r(1, 12, "full", evidence=1), r(2, 20, "full"), r(3, 30, "fix"),
                         r(3, 40, "full")]}
    row = stats.table({"steps": [{"id": "blockout"}]}, st, USAGE)[2].split(" | ")
    assert row[9:12] == ["220", "500", "400"]
