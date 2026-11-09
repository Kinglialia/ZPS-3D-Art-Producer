"""`P stats <id>` (docs/producer.md §16, D27.3): time and tokens per step and role, and the Producer wait."""
from __future__ import annotations

import datetime as dt

from .loop import NO_NUMBER
from .state import load_cfg, load_st

WAITS_ON_PRODUCER = ("todo", "review", "fix", "evidence")
HEAD = ("Bước", "Worker", "Reviewer", "Chờ Producer", "Token worker", "Token reviewer", "report_fallback")


def seconds(a: str, b: str) -> float:
    return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds()


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


def table(cfg: dict, st: dict) -> list[str]:
    disp = st.get("dispatches") or []
    wait = {}
    for prev, x in zip(disp, disp[1:]):
        if prev.get("ingested") and prev.get("after") in WAITS_ON_PRODUCER:
            wait[x["step"]] = wait.get(x["step"], 0) + seconds(prev["ingested"], x["at"])
    rows = ["| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    for step in cfg["steps"]:
        mine = [x for x in disp if x["step"] == step["id"]]
        if not mine:
            continue
        by = {r: [x for x in mine if x["role"] == r] for r in ("worker", "reviewer")}
        time = {r: spent(xs) for r, xs in by.items()}
        rows.append(f"| {step['id']} | {time['worker']} | {time['reviewer']} | {clock(wait.get(step['id']))} | "
                    f"{tokens(by['worker'])} | {tokens(by['reviewer'])} | {sum(bool(x.get('fallback')) for x in mine)} |")
    return rows


def run(a):
    st = load_st(a.id)
    print("\n".join(table(load_cfg(), st)) if st.get("dispatches") else f"{a.id}: chưa giao lần nào")
