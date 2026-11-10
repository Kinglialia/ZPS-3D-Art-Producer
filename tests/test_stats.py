"""`P stats` (D27.3, D30.10, D31.4): time and tokens per step and role, and the Producer wait. Run 4 knew only tokens per
step, so the decision to keep the reviewer with the Producer rests on this table: a Producer wait over 15% of a step is
a review. Run 5 spent 1.33M tokens on reviewers, so R1-R3 (D31) are judged by the reviewer split per round kind."""
import datetime as dt
import json
import subprocess
import sys

from shared import P
from core import session, stats
from flowkit import AID
from test_resolved_notes import to_model

CFG = {"steps": [{"id": "blockout"}, {"id": "views_front"}, {"id": "model"}]}
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
        d("views_front", "worker", "2026-11-10 13:00:00"),
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
        "| views_front | chưa duyệt | không có số | — | — | — | — | — | không có số | — | — | — | 40 | 0 |",
        "| model | chưa duyệt | 17m00s | 2m00s | 1m00s | — | 1m00s | — | 3000 | 100 | 200 | — | 340 | 0 |"]


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


def test_an_unreadable_transcript_shows_no_number_and_the_codex_edition_says_not_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "OUT", tmp_path / "session.json")
    (tmp_path / "session.json").write_text(json.dumps({"transcripts": [str(tmp_path / "gone.jsonl")]}), encoding="utf-8")
    assert stats.producer_usage() == "không có số"
    (tmp_path / "session.json").write_text("{broken", encoding="utf-8")
    assert stats.producer_usage() == "không có số"
    assert stats.table(CFG, ST, stats.producer_usage())[2].endswith(" | 15000 | không có số | 1 |")
    monkeypatch.setattr(stats, "RUNTIME", "codex")
    assert stats.table(CFG, ST, stats.producer_usage())[2].endswith(" | 15000 | chưa hỗ trợ | 1 |")


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
    """D29.4 deletes only on `startup`: the hook's `source` must reach the file. `/clear` starts a new transcript, and
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
    # D30.5: approving views_rest dispatched the model worker, so the model row is open with no reviewer yet.
    assert [r.split(" | ")[0] for r in rows[2:]] == ["| blockout", "| views_front", "| views_rest", "| model"]
    assert [r.split(" | ")[-2] for r in rows[2:]] == ["không có số"] * 4
    assert rows[5] == ("| model | chưa duyệt | không có số | — | — | — | — | — | không có số | — | — | — | không có số "
                       "| 0 |")
