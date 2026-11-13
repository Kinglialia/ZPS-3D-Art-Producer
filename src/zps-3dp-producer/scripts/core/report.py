"""`P report [id]` and `deliver/<id>/RUN-REPORT.md` (D41): real time and tokens per step. Every number comes from a
transcript, stored in status.json at ingest and at approval; a missing number says "không có số" and a reason below the
table, never an estimate and never an even split."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

import heartbeat

from . import session, stats
from .loop import NO_NUMBER
from .state import ASSETS, DELIVER, all_status, load_cfg, load_st, now, rel, write_atomic

NAME = "RUN-REPORT.md"
DASH = "—"
SHARED = "*"
SESSION = "model của phiên"
ROLES = ("worker", "reviewer", "Producer")
HEAD = ("Bước", "Thời gian bước", "Worker", "Reviewer", "Chờ Producer", "Chờ anh",
        *(f"Token {k} {r}" for r in ROLES for k in ("mới", "cache")), "Version", "Vòng sửa", "Lần giao", "Gọi Codex",
        "Credit Meshy", "Kẹt", "Model")
TOKEN_NOTE = ("Token mới = input + output + cache creation: phần runtime tính đủ giá. Token cache = cache read: context đọc "
              "lại từ cache, giá thấp hơn nhiều. Tổng token của transcript là hai cột cộng lại.")
OLD_SPLIT = "lần giao từ bản cũ chỉ lưu tổng token, không tách mới và cache"
OLD_PRODUCER = "bản cũ chỉ lưu tổng token Producer, không tách mới và cache"
PRODUCER_WHY = {NO_NUMBER: "không thấy transcript của phiên Producer"}
NO_MESSAGE = "transcript của Producer không có message trong khoảng của bước"
NO_CODEX_COUNT = "version không có heartbeat.log, nơi ghi mỗi lần gọi codex exec hay tool ảnh"
CODEX_NOTE = ("Token bản Codex: mỗi dòng `token_count` của rollout cộng `input_tokens` + `output_tokens` của "
              "`last_token_usage`; `input_tokens` gồm `cached_input_tokens` và `cache_write_input_tokens`, "
              "`output_tokens` gồm `reasoning_output_tokens`. Script không dùng `total_tokens`: ở vài dòng số đó lớn hơn "
              "tổng hai phần. Dòng lặp lại cùng `total_token_usage` chỉ tính một lần. "
              "Thời lượng: dòng đầu tới dòng cuối của rollout sub-agent trong khoảng lần giao.")
NOT_INGESTED = "lần giao chưa ingest"
OVERLAP_NO_TRANSCRIPT = "hai asset chạy cùng lúc và không còn transcript để tính mỗi message một lần"


@dataclass
class Metric:
    total: float = 0
    got: int = 0
    miss: int = 0

    def __add__(self, o: "Metric") -> "Metric":
        return Metric(self.total + o.total, self.got + o.got, self.miss + o.miss)

    def cell(self, fmt=lambda n: str(int(n))) -> str:
        if not self.got and not self.miss:
            return DASH
        if not self.got:
            return NO_NUMBER
        return fmt(self.total) + (f" (+{self.miss} {NO_NUMBER})" if self.miss else "")


def metric(values: list) -> Metric:
    return Metric(sum(v for v in values if v is not None), sum(v is not None for v in values),
                  sum(v is None for v in values))


def credits(n: float) -> str:
    return f"{n:g}"


@dataclass
class Row:
    label: str
    span: Metric = field(default_factory=Metric)
    opened: int = 0
    worker: Metric = field(default_factory=Metric)
    reviewer: Metric = field(default_factory=Metric)
    wait_p: Metric = field(default_factory=Metric)
    wait_u: Metric = field(default_factory=Metric)
    tw: tuple = (Metric(), Metric())
    tr: tuple = (Metric(), Metric())
    tp: tuple = (Metric(), Metric())
    codex: Metric = field(default_factory=Metric)
    credit: Metric = field(default_factory=Metric)
    versions: int = 0
    rounds: int = 0
    calls: int = 0
    stalls: int = 0
    models: tuple = ((), ())
    shared: tuple = ()
    why: dict = field(default_factory=dict)

    def __add__(self, o: "Row") -> "Row":
        why = {k: list(v) for k, v in self.why.items()}
        for k, cols in o.why.items():
            why[k] = list(dict.fromkeys([*why.get(k, []), *cols]))
        return Row(
            self.label, self.span + o.span, self.opened + o.opened, self.worker + o.worker, self.reviewer + o.reviewer,
            self.wait_p + o.wait_p, self.wait_u + o.wait_u, *(tuple(a + b for a, b in zip(getattr(self, k), getattr(o, k)))
                                                             for k in ("tw", "tr", "tp")),
            self.codex + o.codex, self.credit + o.credit, self.versions + o.versions, self.rounds + o.rounds,
            self.calls + o.calls, self.stalls + o.stalls,
            tuple(tuple(dict.fromkeys([*a, *b])) for a, b in zip(self.models, o.models)),
            tuple(dict.fromkeys([*self.shared, *o.shared])), why)


def note(row: Row, reason: str, col: str):
    cols = row.why.setdefault(reason, [])
    col in cols or cols.append(col)


def span_cell(r: Row) -> str:
    if not r.span.got:
        return "chưa duyệt" if r.opened else DASH
    return stats.clock(r.span.total) + (f" (+{r.opened} chưa duyệt)" if r.opened else "")


def model_cell(r: Row) -> str:
    return " / ".join(", ".join(m) for m in r.models if m) or DASH


def cells(r: Row) -> list[str]:
    return [r.label, span_cell(r), r.worker.cell(stats.clock), r.reviewer.cell(stats.clock), r.wait_p.cell(stats.clock),
            r.wait_u.cell(stats.clock), *(m.cell() for m in (*r.tw, *r.tr)),
            *(m.cell() + (SHARED if r.shared else "") for m in r.tp),
            str(r.versions), str(r.rounds), str(r.calls), r.codex.cell(), r.credit.cell(credits), str(r.stalls),
            model_cell(r)]


def render(head: str, rows: list[Row], total: Row, extra: list[str]) -> list[str]:
    cols = (head, *HEAD[1:])
    body = [cells(r) for r in (*rows, total)]
    notes = [f"{NO_NUMBER} ({', '.join(cols)}): {reason}." for reason, cols in total.why.items()] + extra
    return ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols), *("| " + " | ".join(c) + " |" for c in body),
            *([""] + notes if notes else [])]


def worker_reason(x: dict) -> str:
    if not x.get("ingested"):
        return NOT_INGESTED
    if "usage" not in x:
        return "lần giao từ bản cũ không lưu số lúc ingest, và transcript không còn"
    return "không thấy transcript của subagent"


def seconds_of(xs: list[dict], row: Row, col: str) -> Metric:
    vals = []
    for x in xs:
        t = stats.took(x)
        if t is None:
            note(row, NOT_INGESTED, col)
        vals.append(t)
    return metric(vals)


def cols(role: str) -> tuple[str, str]:
    return f"Token mới {role}", f"Token cache {role}"


def note_both(row: Row, reason: str, role: str):
    for c in cols(role):
        note(row, reason, c)


def tokens_of(xs: list[dict], row: Row, role: str) -> tuple[Metric, Metric]:
    """P6-2: (new, cache read) of the dispatches from their stored usage split. A record that kept only the total
    renders with a reason, not a guess."""
    new, cached = [], []
    for x in xs:
        u = x.get("usage")
        if isinstance(u, dict):
            n, c = session.new_and_cached(u)
        else:
            n = c = None
            note_both(row, OLD_SPLIT if x.get("tokens") is not None else worker_reason(x), role)
        new.append(n)
        cached.append(c)
    return metric(new), metric(cached)


def window_tokens(usage, start: dt.datetime, end: dt.datetime | None) -> tuple[int, int] | str:
    """Producer (new, cache read) tokens in a step window, or the reason there is no number."""
    if isinstance(usage, str):
        return PRODUCER_WHY[usage]
    ns = [(n, c) for t, n, c in usage if t >= start and (end is None or t <= end)]
    return (sum(n for n, _ in ns), sum(c for _, c in ns)) if ns else NO_MESSAGE


def at(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def stamp_of(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def window_of(st: dict, steps: list[dict], sid: str) -> tuple[dt.datetime, dt.datetime | None] | None:
    """The window of a step that ran: first worker dispatch to approval (`stats.window`). A script step has no
    dispatch, so its window starts at the latest earlier approval, when its brief went out."""
    mine = [x for x in st.get("dispatches") or [] if x["step"] == sid]
    if mine:
        return stats.window(st, sid, mine)
    ids = [s["id"] for s in steps]
    step = next((s for s in steps if s["id"] == sid), None)
    if not (step and step.get("script") and (st.get("versions") or {}).get(sid)):
        return None
    done, approved = st.get("approved_at") or {}, st.get("approved") or {}
    prior = [at(done[p]) for p in ids[:ids.index(sid)] if p in approved and p in done]
    if not prior:
        return None
    start = max(prior)
    end = at(done[sid]) if sid in approved and sid in done else None
    return start, (max(end, start) if end else None)


def record_producer(st: dict, sid: str, steps: list[dict]):
    """X2: when a step is approved, the Producer's own tokens in its window go into status.json, so they outlive the
    transcript."""
    start, end = window_of(st, steps, sid) or (None, None)
    if end is None:
        return
    got = window_tokens(stats.producer_usage(), start, end)
    st.setdefault("producer_usage", {})[sid] = got if isinstance(got, str) else {
        "tokens": sum(got), "new": got[0], "cache_read": got[1], "from": stamp_of(start), "to": stamp_of(end)}


def windows(st: dict, steps: list[dict]) -> list[tuple[dt.datetime, dt.datetime]]:
    out = []
    for s in steps:
        if w := window_of(st, steps, s["id"]):
            out.append((w[0], w[1] or dt.datetime.now()))
    return out


def overlapping(start: dt.datetime, end: dt.datetime, others: list[dict], steps: list[dict]) -> tuple:
    return tuple(o["id"] for o in others if any(a < end and start < b for a, b in windows(o, steps)))


class Lazy:
    def __init__(self, fn):
        self.fn, self.done, self.value = fn, False, None

    def __call__(self):
        if not self.done:
            self.value, self.done = self.fn(), True
        return self.value


def budget_credits(aid: str, sid: str) -> list[float | None]:
    out = []
    for p in sorted((ASSETS / aid / sid).glob("budget-*.json")):
        try:
            out.append(float(json.loads(p.read_text(encoding="utf-8"))["used_credits"]))
        except (OSError, ValueError, KeyError, TypeError):
            out.append(None)
    return out or [0.0]


def image_calls(vd) -> int | None:
    """D46: a `codex exec` start (Claude edition) or a checked image tool try (Codex edition) is one image call."""
    ns = [heartbeat.starts(vd, t) for t in (heartbeat.CODEX_EXEC, heartbeat.IMAGE_TOOL)]
    return None if None in ns else sum(ns)


def step_row(step: dict, st: dict, disp: list[dict], waits: dict, usage, others: list[dict], steps: list[dict]) -> Row | None:
    sid = step["id"]
    mine = [x for x in disp if x["step"] == sid]
    if not (win := window_of(st, steps, sid)):
        return None
    worker, rev = [x for x in mine if x["role"] == "worker"], [x for x in mine if x["role"] == "reviewer"]
    start, end = win
    r = Row(sid, models=(tuple(dict.fromkeys(x.get("model") or SESSION for x in worker)),
                         tuple(dict.fromkeys(x.get("model") or SESSION for x in rev))))
    r.span, r.opened = (Metric((end - start).total_seconds(), 1), 0) if end else (Metric(), 1)
    r.worker, r.reviewer = seconds_of(worker, r, "Worker"), seconds_of(rev, r, "Reviewer")
    r.wait_p = Metric(waits[sid], 1) if sid in waits else Metric()
    wu = stats.user_wait(st, sid)
    r.wait_u = Metric(wu, 1) if wu is not None else Metric()
    r.tw, r.tr = tokens_of(worker, r, "worker"), tokens_of(rev, r, "reviewer")
    stored = (st.get("producer_usage") or {}).get(sid) if end else None
    got = (stored["new"], stored["cache_read"]) if isinstance(stored, dict) and "new" in stored else (
        OLD_PRODUCER if isinstance(stored, dict) else stored if isinstance(stored, str) else window_tokens(usage(), start, end))
    if isinstance(got, str):
        r.tp = (Metric(miss=1), Metric(miss=1))
        note_both(r, got, "Producer")
    else:
        r.tp = (Metric(got[0], 1), Metric(got[1], 1))
    r.shared = overlapping(start, end or dt.datetime.now(), others, steps)
    r.versions = (st.get("versions") or {}).get(sid, 0)
    r.rounds = max(r.versions - 1, 0)
    r.calls = len(mine)
    r.stalls = sum(1 for x in st.get("stalls") or [] if x["step"] == sid)
    if "codex_image" in step["uses"]:
        r.codex = metric([image_calls(ASSETS / st["id"] / sid / f"v{k}") for k in range(1, r.versions + 1)])
        if r.codex.miss:
            note(r, NO_CODEX_COUNT, "Gọi Codex")
    if "meshy" in step["uses"]:
        r.credit = metric(budget_credits(st["id"], sid))
        if r.credit.miss:
            note(r, "file budget Meshy không đọc được", "Credit Meshy")
    return r


def asset_rows(st: dict, cfg: dict, others: list[dict], usage) -> list[Row]:
    disp = stats.reread(st.get("dispatches") or [])
    waits = stats.waits(disp)
    return [r for s in cfg["steps"] if (r := step_row(s, st, disp, waits, usage, others, cfg["steps"]))]


def codex_note(sts: list[dict]) -> list[str]:
    """The fields a Codex number sums, once, when a stored split came from a rollout."""
    return [CODEX_NOTE] if any(isinstance(x.get("usage"), dict) and x["usage"].get("format") == "codex"
                               for s in sts for x in s.get("dispatches") or []) else []


def total_of(label: str, rows: list[Row]) -> Row:
    return sum(rows, Row(label))


def usage_getter(usage) -> Lazy:
    return Lazy(stats.producer_usage) if usage is None else Lazy(lambda: usage)


def others_of(st: dict) -> list[dict]:
    return [s for s in all_status() if s.get("id") != st["id"] and not s.get("broken")]


def table(st: dict, cfg: dict | None = None, others: list[dict] | None = None, usage=None) -> list[str]:
    cfg = cfg or load_cfg()
    others = others_of(st) if others is None else others
    rows = asset_rows(st, cfg, others, usage_getter(usage))
    if not rows:
        return [f"{st['id']}: chưa giao lần nào"]
    total = total_of("Tổng", rows)
    who = ", ".join(dict.fromkeys(i for r in rows for i in r.shared))
    return render(HEAD[0], rows, total, [TOKEN_NOTE] + ([f"{SHARED} Token Producer tính chung với {who}."] if who else [])
                  + codex_note([st]))


def batch(sts: list[dict], cfg: dict | None = None, usage=None) -> list[str]:
    cfg = cfg or load_cfg()
    get = usage_getter(usage)
    sts = [s for s in sts if s.get("dispatches")]
    per = []
    for s in sts:
        rows = asset_rows(s, cfg, [o for o in sts if o is not s], get)
        per.append(total_of(s["id"], rows))
    if not per:
        return ["chưa asset nào được giao việc"]
    total = total_of("Tổng lô", per)
    total.shared = ()
    total.tp, why = batch_producer(sts, cfg["steps"], get, any(r.shared for r in per))
    if why:
        note_both(total, why, "Producer")
    shared = [f"{r.label}: {', '.join(r.shared)}" for r in per if r.shared]
    return render("Asset", per, total, [TOKEN_NOTE] + ([f"{SHARED} Token Producer tính chung: " + "; ".join(shared)
                                         + ". Tổng lô tính mỗi message một lần."] if shared else []) + codex_note(sts))


def batch_producer(sts: list[dict], steps: list[dict], usage, overlap: bool) -> tuple[tuple, str | None]:
    """Each Producer message once, as (new, cache read). Stored numbers add up exactly only when no two assets overlap;
    otherwise the transcript says which messages fall in any window, and without it the total has no number."""
    none = (Metric(miss=1), Metric(miss=1))
    stored = [(s.get("producer_usage") or {}).get(sid) if sid in (s.get("approved") or {}) else None
              for s in sts for sid in (x["id"] for x in steps if window_of(s, steps, x["id"]))]
    if not overlap and stored and all(isinstance(p, dict) and "new" in p for p in stored):
        return (Metric(sum(p["new"] for p in stored), 1), Metric(sum(p["cache_read"] for p in stored), 1)), None
    u = usage()
    if isinstance(u, str):
        return none, OVERLAP_NO_TRANSCRIPT if overlap else PRODUCER_WHY[u]
    ws = [w for s in sts for w in windows(s, steps)]
    ns = [(n, c) for t, n, c in u if any(a <= t <= b for a, b in ws)]
    return ((Metric(sum(n for n, _ in ns), 1), Metric(sum(c for _, c in ns), 1)), None) if ns else (none, NO_MESSAGE)


def write(st: dict, lines: list[str] | None = None):
    lines = table(st) if lines is None else lines
    p = DELIVER / st["id"] / NAME
    write_atomic(p, "\n".join([f"# RUN-REPORT {st['id']}", "",
                               f"Ghi lúc {now()}. Số lấy từ transcript của runtime, không ước lượng.", "", *lines]) + "\n")
    return p


def finish(st: dict) -> tuple[bool, str]:
    """DUYỆT 2: write the report and give back the table to print. A failure is printed and never undoes the approval."""
    try:
        lines = table(st)
        write(st, lines)
    except Exception as ex:  # noqa: BLE001 — the approval is saved; the report must say what went wrong, not crash
        return False, f"KHÔNG ghi được {NAME}: {type(ex).__name__}: {ex}"
    return True, "\n".join(lines)


def used(st: dict) -> tuple[str, str]:
    """Time and tokens spent so far, from stored numbers only; the dashboard reads no transcript."""
    xs = [x for x in st.get("dispatches") or [] if x.get("role") != "script"]
    secs = metric([stats.took(x) for x in xs])
    toks = metric([x.get("tokens") for x in xs])
    for v in (st.get("producer_usage") or {}).values():
        if isinstance(v, dict):
            toks = toks + Metric(v["tokens"], 1)
    return secs.cell(stats.clock), toks.cell()


def run(a):
    if not a.id:
        print("\n".join(batch(all_status())))
        return
    st = load_st(a.id)
    kept = DELIVER / a.id / NAME
    if st.get("purged") and kept.is_file():
        print(kept.read_text(encoding="utf-8").rstrip())
        return
    lines = table(st)
    print("\n".join(lines))
    print(f"OK: {rel(write(st, lines))}" if st["state"] == "done" else f"{a.id}: chưa done, chưa ghi {NAME}")
