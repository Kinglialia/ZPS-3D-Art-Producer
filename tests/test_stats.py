"""`P stats` (D27.3): time and tokens per step and role, and the Producer wait. Run 4 knew only tokens per step, so the
decision to keep the reviewer with the Producer rests on this table: a Producer wait over 15% of a step is a review."""
from core import stats

CFG = {"steps": [{"id": "blockout"}, {"id": "views_front"}, {"id": "model"}]}


def d(step, role, at, ingested=None, after=None, **kw):
    return {"step": step, "v": 1, "role": role, "model": None, "at": at,
            **({"ingested": ingested, "after": after} if ingested else {}), **kw}


def test_stats_splits_each_step_by_role_and_counts_only_the_gaps_the_producer_owns():
    st = {"dispatches": [
        d("blockout", "worker", "2026-11-10 09:00:00", "2026-11-10 09:10:00", "review", tokens=50000, duration_ms=590000),
        d("blockout", "reviewer", "2026-11-10 09:10:30", "2026-11-10 09:14:30", "fix", tokens=None, fallback=True),
        d("blockout", "worker", "2026-11-10 09:15:30", "2026-11-10 09:25:00", "review", tokens=30000),
        d("blockout", "reviewer", "2026-11-10 09:25:00", "2026-11-10 09:28:00", "waiting_human", tokens=20000),
        d("views_front", "worker", "2026-11-10 11:00:00"),
    ]}
    assert stats.table(CFG, st) == [
        "| Bước | Worker | Reviewer | Chờ Producer | Token worker | Token reviewer | report_fallback |",
        "|---|---|---|---|---|---|---|",
        "| blockout | 19m20s | 7m00s | 1m30s | 80000 | 20000 (+1 không có số) | 1 |",
        "| views_front | không có số | — | — | không có số | — | 0 |"]
