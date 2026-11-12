"""D41, X1-X7, A3: the report that DUYỆT 2 prints and writes. The owner reads real time and real tokens for each step; a
number the runtime did not give is "không có số" with its reason once below the table, never an estimate and never an
even split. The numbers are stored at ingest and at approval, so they outlive the transcripts."""
import datetime as dt
import json

import pytest

from core import report, stats
from flowkit import AID, Flow, counts, to_texture
from shared import pilot_project

HEAD = ("| Bước | Thời gian bước | Worker | Reviewer | Chờ Producer | Chờ anh | Token worker | Token reviewer "
        "| Token Producer | Version | Vòng sửa | Lần giao | Gọi Codex | Credit Meshy | Kẹt | Model |")
SEP = "|" + "---|" * 16
CFG = {"steps": [{"id": "blockout", "uses": ["blender"]}, {"id": "texture", "uses": ["blender", "codex_image", "meshy"]},
                 {"id": "assemble", "uses": ["blender"]}]}


def d(step, role, at, ingested=None, after=None, v=1, **kw):
    return {"step": step, "v": v, "role": role, "model": kw.pop("model", None), "at": at,
            **({"ingested": ingested, "after": after} if ingested else {}), **kw}


def t(s):
    return dt.datetime.fromisoformat(s)


def asset(aid, dispatches, **kw):
    return {"id": aid, "approved": {}, "approved_at": {}, "versions": {}, "dispatches": dispatches} | kw


A1 = asset(
    "a1",
    [d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:10:00", "review", tokens=50000, duration_ms=590000,
       usage={}, model="opus"),
     d("blockout", "reviewer", "2026-11-10 09:10:30", "2026-11-10 09:13:30", "fix", tokens=20000, usage={},
       model="sonnet", scope="full"),
     d("blockout", "worker", "2026-11-10 09:15:30", "2026-11-10 09:25:00", "review", v=2, tokens=30000,
       duration_ms=540000, usage={}, model="opus"),
     d("blockout", "reviewer", "2026-11-10 09:25:00", "2026-11-10 09:28:00", "waiting_human", v=2, tokens=15000,
       usage={}, model="sonnet", scope="full"),
     d("texture", "worker", "2026-11-10 10:00:00", "2026-11-10 10:30:00", "review", tokens=None, usage=None,
       model="opus"),
     d("texture", "reviewer", "2026-11-10 10:30:00", "2026-11-10 10:35:00", "waiting_human", tokens=5000, usage={},
       model="sonnet", scope="full")],
    approved={"blockout": 2}, approved_at={"blockout": "2026-11-10 09:45"}, versions={"blockout": 2, "texture": 1},
    offer_log=[{"key": "k", "step": "blockout", "v": 2, "why": "duyệt", "at": "2026-11-10 09:31",
                "decision": "approve", "decided": "2026-11-10 09:45"}],
    stalls=[{"step": "blockout", "v": 1, "role": "worker", "at": "2026-11-10 09:05:00", "why": "x", "rung": "nudge"}],
    producer_usage={"blockout": {"tokens": 1500, "from": "2026-11-10 09:00:00", "to": "2026-11-10 09:45:00"}})
A2 = asset("a2", [d("texture", "worker", "2026-11-10 10:10:00")])
LIVE = [(t("2026-11-10 09:30:00"), 99999), (t("2026-11-10 10:05:00"), 700), (t("2026-11-10 10:31:00"), 300)]


@pytest.fixture
def meshy20(tmp_path, monkeypatch):
    (tmp_path / "a1/texture").mkdir(parents=True)
    (tmp_path / "a1/texture/budget-1.json").write_text(json.dumps({"max_credits": 40, "used_credits": 20}), encoding="utf-8")
    monkeypatch.setattr(report, "ASSETS", tmp_path)


def test_one_row_per_step_with_real_numbers_a_total_and_the_overlap_mark_x4_x6_a3(meshy20):
    """blockout is approved with its stored Producer tokens. texture is still open: its Producer tokens are the
    messages inside its window, its worker has no transcript (so no number, not zero), and a2 runs inside the same
    window, so the Producer cell carries the mark."""
    assert report.table(A1, CFG, [A2], LIVE) == [
        HEAD, SEP,
        "| blockout | 45m00s | 18m50s | 6m00s | 2m30s | 14m00s | 80000 | 35000 | 1500 | 2 | 1 | 4 | — | — | 1 "
        "| opus / sonnet |",
        "| texture | chưa duyệt | 30m00s | 5m00s | 0m00s | — | không có số | 5000 | 1000* | 1 | 0 | 2 | không có số | 20 "
        "| 0 | opus / sonnet |",
        "| Tổng | 45m00s (+1 chưa duyệt) | 48m50s | 11m00s | 2m30s | 14m00s | 80000 (+1 không có số) | 40000 | 2500* "
        "| 3 | 1 | 6 | không có số | 20 | 1 | opus / sonnet |",
        "",
        "không có số (Token worker): không thấy transcript của subagent.",
        "không có số (Gọi Codex): chưa có bản ghi số lần gọi Codex (gen_image_codex.py chỉ ghi model).",
        "* Token Producer tính chung với a2."]


def test_a_step_that_never_used_codex_or_meshy_shows_a_dash_not_a_zero(meshy20):
    rows = report.table(A1, CFG, [], LIVE)
    assert rows[2].split(" | ")[12:14] == ["—", "—"]
    assert "*" not in "".join(rows)


def test_the_codex_edition_has_no_transcript_and_says_so_once_below_the_table(meshy20, monkeypatch):
    monkeypatch.setattr(report, "RUNTIME", "codex")
    st = asset("a1", [d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:10:00", "review", tokens=None,
                        usage=None),
                      d("blockout", "reviewer", "2026-11-10 09:10:30", "2026-11-10 09:12:30", "waiting_human",
                        tokens=None, usage=None, scope="full")])
    rows = report.table(st, CFG, [], stats.NOT_SUPPORTED)
    assert rows[2] == ("| blockout | chưa duyệt | 10m00s | 2m00s | 0m30s | — | không có số | không có số | không có số "
                       "| 0 | 0 | 2 | — | — | 0 | model của phiên / model của phiên |")
    assert rows[5:] == ["không có số (Token worker, Token reviewer): bản Codex không có transcript.",
                        "không có số (Token Producer): bản Codex chưa đọc được transcript của Producer."]


def test_a_dispatch_from_before_this_version_names_its_own_reason(meshy20):
    """No `usage` key: the dispatch was ingested by a version that stored no split. A new ingest that found nothing
    stores `usage: null`, which is the other reason."""
    old = d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:10:00", "review", tokens=None)
    new = d("blockout", "worker", "2026-11-10 09:11:00", "2026-11-10 09:20:00", "review", v=2, tokens=None, usage=None)
    out = report.table(asset("a1", [old, new]), CFG, [], "không có số")
    assert out[5:] == [
        "không có số (Token worker): lần giao từ bản cũ không lưu số lúc ingest, và transcript không còn.",
        "không có số (Token worker): không thấy transcript của subagent.",
        "không có số (Token Producer): không thấy transcript của phiên Producer."]


def producer_messages(monkeypatch, msgs):
    monkeypatch.setattr(stats, "producer_usage", lambda: msgs)


def test_approval_stores_the_producer_tokens_so_deleting_the_transcript_keeps_them_x2(monkeypatch, meshy20):
    st = asset("a1", A1["dispatches"][:4], approved={"blockout": 2}, approved_at={"blockout": "2026-11-10 09:45"})
    producer_messages(monkeypatch, [(t("2026-11-10 08:59:59"), 5), (t("2026-11-10 09:05:00"), 1000),
                                    (t("2026-11-10 09:40:00"), 500), (t("2026-11-10 09:46:00"), 7)])
    report.record_producer(st, "blockout", CFG["steps"])
    assert st["producer_usage"]["blockout"] == {"tokens": 1500, "from": "2026-11-10 09:00:00", "to": "2026-11-10 09:45:00"}
    producer_messages(monkeypatch, "không có số")
    row = report.table(st, CFG, [], "không có số")[2]
    assert row.split(" | ")[8] == "1500"


def test_a_step_without_a_producer_transcript_stores_the_reason_not_a_zero(monkeypatch):
    st = asset("a1", A1["dispatches"][:4], approved={"blockout": 2}, approved_at={"blockout": "2026-11-10 09:45"})
    producer_messages(monkeypatch, "không có số")
    report.record_producer(st, "blockout", CFG["steps"])
    assert st["producer_usage"] == {"blockout": "không thấy transcript của phiên Producer"}
    producer_messages(monkeypatch, [(t("2026-11-10 13:00:00"), 5)])
    report.record_producer(st, "blockout", CFG["steps"])
    assert st["producer_usage"] == {"blockout": "transcript của Producer không có message trong khoảng của bước"}


SCRIPT = {"steps": [*CFG["steps"][:2], {"id": "assemble", "uses": ["blender"], "script": "assemble.py"}]}


def finished():
    """texture approved 11:00, then the assemble script: its brief goes out at 11:00, the owner decides at 11:20."""
    return asset(
        "a1", [d("texture", "worker", "2026-11-10 10:00:00", "2026-11-10 10:50:00", "review", tokens=100, usage={})],
        approved={"texture": 1, "assemble": 3}, approved_at={"texture": "2026-11-10 11:00", "assemble": "2026-11-10 11:20"},
        versions={"texture": 1, "assemble": 3},
        offer_log=[{"key": "k", "step": "assemble", "v": 3, "why": "duyệt", "at": "2026-11-10 11:10",
                    "decision": "approve", "decided": "2026-11-10 11:20"}])


def test_a_script_step_gets_a_row_from_the_previous_approval_to_its_own_with_the_owner_wait_x4(monkeypatch, meshy20):
    """DUYỆT 2 is a step the owner waits on and the Producer works on, so the table shows it. A script has no
    dispatch: its window starts when the step before it was approved."""
    st = finished()
    producer_messages(monkeypatch, [(t("2026-11-10 11:05:00"), 800), (t("2026-11-10 11:30:00"), 9)])
    report.record_producer(st, "assemble", SCRIPT["steps"])
    assert st["producer_usage"]["assemble"] == {"tokens": 800, "from": "2026-11-10 11:00:00", "to": "2026-11-10 11:20:00"}
    rows = report.table(st, SCRIPT, [], "không có số")
    assert rows[3] == "| assemble | 20m00s | — | — | — | 10m00s | — | — | 800 | 3 | 2 | 0 | — | — | 0 | — |"


def test_a_script_step_that_never_ran_has_no_row(monkeypatch):
    st = finished() | {"versions": {"texture": 1}, "approved": {"texture": 1}}
    assert not any(r.startswith("| assemble") for r in report.table(st, SCRIPT, [], "không có số"))


def test_a_batch_total_reads_each_producer_message_once_when_not_every_step_is_stored_x6(meshy20):
    """a1's texture window and a2's window both hold the 10:31 message of 300 tokens. Added up by asset the batch
    would say 2800; the Producer spoke 2500 tokens."""
    msgs = [(t("2026-11-10 09:10:00"), 1500), (t("2026-11-10 10:05:00"), 700), (t("2026-11-10 10:31:00"), 300)]
    out = report.batch([A1, A2], CFG, msgs)
    cells = {l.split(" | ")[0].lstrip("| "): l.split(" | ")[8] for l in out[2:5]}
    assert cells == {"a1": "2500*", "a2": "300*", "Tổng lô": "2500"}


def test_a_batch_total_stays_right_after_a_redo_because_it_reads_the_transcript_not_a_stored_share_x6(meshy20):
    """a1 ran 09:00-09:45 and a2 09:30-10:00. The owner sends a1's blockout back and a1 is approved again at 10:30,
    so its window now holds a2's whole window and a 10:20 message. A share saved at the first approval would be
    stale; the transcript says each of the four messages once: 1610."""
    a1 = asset("a1", A1["dispatches"][:4], approved={"blockout": 2}, approved_at={"blockout": "2026-11-10 10:30"},
               versions={"blockout": 2}, producer_usage={"blockout": {"tokens": 1610, "from": "2026-11-10 09:00:00",
                                                                      "to": "2026-11-10 10:30:00"}})
    a2 = asset("a2", [d("blockout", "worker", "2026-11-10 09:30:00", "2026-11-10 09:55:00", "review", tokens=10,
                        usage={})], approved={"blockout": 1}, approved_at={"blockout": "2026-11-10 10:00"},
               versions={"blockout": 1}, producer_usage={"blockout": {"tokens": 570, "from": "2026-11-10 09:30:00",
                                                                      "to": "2026-11-10 10:00:00"}})
    msgs = [(t("2026-11-10 09:05:00"), 1000), (t("2026-11-10 09:40:00"), 500), (t("2026-11-10 09:50:00"), 70),
            (t("2026-11-10 10:20:00"), 40)]
    out = report.batch([a1, a2], CFG, msgs)
    assert out == [
        "| Asset | " + HEAD.split(" | ", 1)[1], SEP,
        "| a1 | 90m00s | 18m50s | 6m00s | 2m30s | — | 80000 | 35000 | 1610* | 2 | 1 | 4 | — | — | 0 | opus / sonnet |",
        "| a2 | 30m00s | 25m00s | — | — | — | 10 | — | 570* | 1 | 0 | 1 | — | — | 0 | model của phiên |",
        "| Tổng lô | 120m00s | 43m50s | 6m00s | 2m30s | — | 80010 | 35000 | 1610 | 3 | 1 | 5 | — | — | 0 "
        "| opus, model của phiên / sonnet |",
        "",
        "* Token Producer tính chung: a1: a2; a2: a1. Tổng lô tính mỗi message một lần."]


def test_stored_numbers_add_up_in_a_batch_only_when_no_two_assets_overlap_x6(meshy20):
    a1 = asset("a1", A1["dispatches"][:4], approved={"blockout": 2}, approved_at={"blockout": "2026-11-10 09:45"},
               versions={"blockout": 2}, producer_usage={"blockout": {"tokens": 1500, "from": "x", "to": "y"}})
    a3 = asset("a3", [d("blockout", "worker", "2026-11-10 12:00:00", "2026-11-10 12:10:00", "review", tokens=10,
                        usage={})], approved={"blockout": 1}, approved_at={"blockout": "2026-11-10 12:30"},
               versions={"blockout": 1}, producer_usage={"blockout": {"tokens": 70, "from": "x", "to": "y"}})
    out = report.batch([a1, a3], CFG, "không có số")
    assert out[4].split(" | ")[8] == "1570"
    assert not any(l.startswith("*") for l in out)


def test_a_batch_of_overlapping_assets_without_a_transcript_says_why_instead_of_adding_twice_x6(meshy20):
    out = report.batch([A1, A2], CFG, "không có số")
    assert out[4].split(" | ")[8] == "không có số"
    assert ("không có số (Token Producer): hai asset chạy cùng lúc và không còn transcript để tính mỗi message "
            "một lần.") in out


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def test_ingest_stores_the_usage_split_and_the_report_and_stats_survive_the_transcript_x1_x5(tmp_path):
    """The worker's transcript is the only source of its tokens. Stored at ingest, the numbers stay when the runtime
    cleans its transcripts; read again at every report they would vanish."""
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    raw = f.p("brief", AID)
    main, ts = tmp_path / "main.jsonl", utc_now()
    sub = tmp_path / "main/subagents/agent-w-b1.jsonl"
    sub.parent.mkdir(parents=True)
    main.write_text("", encoding="utf-8")
    line = lambda mid, **u: json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": mid, "usage": u}})  # noqa: E731
    m1 = line("m1", input_tokens=10, output_tokens=200, cache_read_input_tokens=3000, cache_creation_input_tokens=400)
    sub.write_text("\n".join([m1, m1, line("m2", input_tokens=5, output_tokens=50)]) + "\n", encoding="utf-8")
    (tmp_path / "production/session.json").write_text(json.dumps({"transcripts": [str(main)]}), encoding="utf-8")
    f.sent = raw
    f.work("b1")
    worker = f.st()["dispatches"][0]
    assert (worker["tokens"], worker["usage"]) == (
        3665, {"input": 15, "output": 250, "cache_read": 3000, "cache_creation": 400, "duration_ms": 0})
    sub.unlink()
    main.unlink()
    cfg = {"steps": [{"id": "blockout", "uses": ["blender"]}]}
    row = report.table(f.st(), cfg, [], "không có số")[2].split(" | ")
    assert row[6] == "3665"
    assert "| 3665 |" in f.p("stats", AID)


def test_a_dispatch_with_nothing_in_its_transcript_stores_null_usage_not_zeros(tmp_path):
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    worker = f.st()["dispatches"][0]
    assert (worker["tokens"], worker["usage"]) == (None, None)


@pytest.fixture(scope="module")
def done(tmp_path_factory):
    root = tmp_path_factory.mktemp("report")
    f = to_texture(root)
    f.work("t1", meshy="")
    f.review("t1", verdict="PASS", counts=counts(), top_fix=None)
    f.assemble("a1")
    return root, f, f.p("feedback", AID, "đạt", "--action", "approve")


def test_duyet_2_writes_the_report_to_deliver_and_prints_the_table_after_the_approve_line_x3(done):
    root, f, out = done
    lines = out.splitlines()
    assert lines[0] == "pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong"
    table = lines[lines.index(HEAD):]
    assert [l.split(" | ")[0] for l in table[2:9]] == [
        "| blockout", "| views_front", "| views_rest", "| model", "| texture", "| assemble", "| Tổng"]
    assert table[7].split(" | ")[2:5] == ["—", "—", "—"]
    text = (root / "deliver" / AID / "RUN-REPORT.md").read_text(encoding="utf-8")
    assert "\n".join(table) in text


def test_the_e2e_report_says_why_nothing_has_a_producer_number_without_a_producer_transcript_x5(done):
    root, f, out = done
    assert f.st()["producer_usage"]["texture"] == "không thấy transcript của phiên Producer"
    assert "không có số (Token Producer): không thấy transcript của phiên Producer." in out.splitlines()


def test_p_report_prints_one_asset_and_rewrites_the_file_and_without_an_id_prints_the_batch_x7(done):
    root, f, _ = done
    one = f.p("report", AID)
    assert one.splitlines()[1] == SEP and one.splitlines()[-1] == "OK: deliver/pilot-house/RUN-REPORT.md"
    batch = f.p("report").splitlines()
    assert batch[0].startswith("| Asset | Thời gian bước") and batch[2].startswith("| pilot-house |")
    assert batch[3].startswith("| Tổng lô |")


def test_p_report_before_the_asset_is_done_prints_but_creates_no_deliver_folder(tmp_path):
    """`deliver/<id>/` means delivered to the purge check and to the PILOT line of a brief."""
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    out = f.p("report", AID)
    assert out.splitlines()[-1] == "pilot-house: chưa done, chưa ghi RUN-REPORT.md"
    assert not (tmp_path / "deliver").exists()
