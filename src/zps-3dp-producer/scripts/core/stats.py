"""`P stats <id>` (docs/producer.md §16, D27.3, D30.10, D31.4): time and tokens per step and role, reviewer rounds by
kind, the Producer and user waits, and the Producer's own tokens."""
from __future__ import annotations

import datetime as dt

from . import session
from .loop import NO_NUMBER
from .state import load_cfg, load_st

NOT_APPROVED = "chưa duyệt"
WAITS_ON_PRODUCER = ("todo", "review", "fix", "evidence")
ROUNDS = ("first", "fix", "final")
HEAD = ("Bước", "Thời gian bước", "Worker", "Reviewer đầu", "Reviewer sửa", "Reviewer cuối", "Chờ Producer", "Chờ anh",
        "Token worker", "Token reviewer đầu", "Token reviewer sửa", "Token reviewer cuối", "Token Producer",
        "report_fallback")


def at(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def seconds(a: str, b: str) -> float:
    return (at(b) - at(a)).total_seconds()


def reread(disp: list[dict]) -> list[dict]:
    """D33.22: a dispatch ingested without a number, or without the usage split (P6-2), gets it from the subagent
    transcript now; nothing is saved."""
    out = []
    for x in disp:
        if x.get("ingested") and x.get("role") != "script" and (
                x.get("tokens") is None or x.get("duration_ms") is None or not isinstance(x.get("usage"), dict)):
            u = session.dispatch_usage(x, x["ingested"])
            t, ms = (sum(u[k] for k in session.SPLIT.values()), u["duration_ms"]) if u else (None, None)
            x = x | {"tokens": x["tokens"] if x.get("tokens") is not None else t,
                     "duration_ms": x["duration_ms"] if x.get("duration_ms") is not None else ms} | (
                {"usage": u} if u and not isinstance(x.get("usage"), dict) else {})
        out.append(x)
    return out


def took(x: dict) -> float | None:
    """The runtime's duration when the Producer passed it, else dispatch to ingest."""
    if x.get("duration_ms") is not None:
        return x["duration_ms"] / 1000
    return seconds(x["at"], x["ingested"]) if x.get("ingested") else None


def clock(s: float | None) -> str:
    if s is None:
        return "—"
    s = round(s)
    return f"{s // 60}m{s % 60:02d}s"


def spent(xs: list[dict]) -> str:
    if not xs:
        return "—"
    ts = [t for x in xs if (t := took(x)) is not None]
    return clock(sum(ts)) if ts else NO_NUMBER


def tokens(xs: list[dict]) -> str:
    if not xs:
        return "—"
    told = [x["tokens"] for x in xs if x.get("tokens") is not None]
    if not told:
        return NO_NUMBER
    untold = len(xs) - len(told)
    return f"{sum(told)}" + (f" (+{untold} {NO_NUMBER})" if untold else "")


def round_kinds(revs: list[dict]) -> list[str]:
    """D31.4, D38.3: the first review is `first`. A `full` review of a version a reviewer already judged, with no worker
    between, is the closing review `final`. A review inside an evidence round (`evidence`) goes on the round it continues.
    Every other review judges a new version: `fix`, whatever its scope."""
    out = []
    for i, x in enumerate(revs):
        if i == 0:
            out.append("first")
        elif x.get("evidence"):
            out.append(out[-1])
        elif x.get("scope") == "full" and any(y["v"] == x["v"] for y in revs[:i]):
            out.append("final")
        else:
            out.append("fix")
    return out


def window(st: dict, sid: str, mine: list[dict]) -> tuple[dt.datetime, dt.datetime | None]:
    """First worker dispatch of the step to its approval; an open step runs on. `approved_at` survives a reopen, so it
    counts only while the step is approved. It has minute resolution, so the end never falls before the start."""
    start = at(next((x for x in mine if x["role"] == "worker"), mine[0])["at"])
    end = at(st["approved_at"][sid]) if sid in (st.get("approved") or {}) and sid in (st.get("approved_at") or {}) else None
    return start, (max(end, start) if end else None)


def user_wait(st: dict, sid: str) -> float | None:
    """Offer to the user's decision (offer_log `at` → `decided`), only for offers the user has answered."""
    ws = [seconds(w["at"], w["decided"]) for w in st.get("offer_log") or [] if w.get("step") == sid and w.get("decided")]
    return max(sum(ws), 0) if ws else None


def producer_tokens(usage, start: dt.datetime, end: dt.datetime | None) -> str:
    """A step with dispatches had Producer turns: no message in its window means the transcripts miss them."""
    if isinstance(usage, str):
        return usage
    ns = [n + c for t, n, c in usage if t >= start and (end is None or t <= end)]
    return str(sum(ns)) if ns else NO_NUMBER


def producer_usage() -> list[tuple[dt.datetime, int, int]] | str:
    """D30.10, D46: the main-session transcripts or rollouts the SessionStart hook recorded."""
    paths = (session.load() or {}).get("transcripts") or []
    usage = session.main_usage(paths) if paths else None
    return usage or NO_NUMBER


def waits(disp: list[dict]) -> dict[str, float]:
    """Seconds the Producer took between a dispatch's ingest and the next dispatch, per step of the next one."""
    out = {}
    for prev, x in zip(disp, disp[1:]):
        if prev.get("ingested") and prev.get("after") in WAITS_ON_PRODUCER:
            out[x["step"]] = out.get(x["step"], 0) + seconds(prev["ingested"], x["at"])
    return out


def stored_producer(st: dict, sid: str) -> int | None:
    """D41: the Producer tokens saved when the step was approved; a reopened step has no approval, so no stored number."""
    v = (st.get("producer_usage") or {}).get(sid) if sid in (st.get("approved") or {}) else None
    return v["tokens"] if isinstance(v, dict) else None


def table(cfg: dict, st: dict, usage=NO_NUMBER) -> list[str]:
    disp = st.get("dispatches") or []
    wait = waits(disp)
    rows = ["| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    for step in cfg["steps"]:
        sid = step["id"]
        mine = [x for x in disp if x["step"] == sid]
        if not mine:
            continue
        worker = [x for x in mine if x["role"] == "worker"]
        rv = {k: [] for k in ROUNDS}
        revs = [x for x in mine if x["role"] == "reviewer"]
        for k, x in zip(round_kinds(revs), revs):
            rv[k].append(x)
        start, end = window(st, sid, mine)
        cells = [sid, clock((end - start).total_seconds()) if end else NOT_APPROVED, spent(worker),
                 *(spent(rv[k]) for k in ROUNDS), clock(wait.get(sid)), clock(user_wait(st, sid)), tokens(worker),
                 *(tokens(rv[k]) for k in ROUNDS),
                 str(n) if (n := stored_producer(st, sid)) is not None else producer_tokens(usage, start, end),
                 str(sum(bool(x.get("fallback")) for x in mine))]
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def stall_rows(cfg: dict, st: dict) -> list[str]:
    """D33.16: stalls, nudges and new dispatches per step (`P stall`)."""
    xs = st.get("stalls") or []
    if not xs:
        return []
    rows = ["", "| Bước | Kẹt | Nudge | Giao lại | Hỏi anh |", "|---|---|---|---|---|"]
    for step in cfg["steps"]:
        mine = [x for x in xs if x["step"] == step["id"]]
        if mine:
            rows.append(f"| {step['id']} | {len(mine)} | " + " | ".join(
                str(sum(x["rung"] == k for x in mine)) for k in ("nudge", "redispatch", "human")) + " |")
    return rows


def run(a):
    st = load_st(a.id)
    st = st | {"dispatches": reread(st.get("dispatches") or [])}
    cfg = load_cfg()
    print("\n".join(table(cfg, st, producer_usage()) + stall_rows(cfg, st)) if st.get("dispatches")
          else f"{a.id}: chưa giao lần nào")
