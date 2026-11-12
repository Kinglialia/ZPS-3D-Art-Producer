"""D33.9–18: the running jobs, read from files only. Deadline of a dispatch, stall check, the one stall rule (`P stall`),
`P wait` and the SubagentStop hook (`P on-stop`)."""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import sys
import time

from pathlib import Path

import heartbeat

from . import policy
from .state import ROOT, all_status, die, ledger, load_cfg, load_st, rel, save_st, stamp, step_of, vdir

ROLE_OF = {"running": "worker", "evidence_running": "worker", "reviewing": "reviewer"}
REPORT = {"brief-worker.md": "worker-out.md", "brief-review.md": "review-out.md"}
NUDGE = "Tiếp tục, báo trạng thái"
LIVE = ("start", "running")
LOCK = "wait.lock"


def at(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def fmt(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def minutes(s: float) -> str:
    return f"{max(round(s / 60), 0)}m"


def usual_s(cfg: dict, sid: str, role: str, sts: list[dict] | None = None) -> float | None:
    """D33.10: the median time of this step and role over earlier dispatches of every asset (`P stats`), else the
    `usual_min` of the step in pipeline.toml."""
    from .stats import took
    xs = [t for s in (all_status() if sts is None else sts) for x in s.get("dispatches") or []
          if x.get("step") == sid and x.get("role") == role and x.get("ingested") and (t := took(x))]
    if xs:
        return statistics.median(xs)
    m = (step_of(cfg, sid)[1].get("usual_min") or {}).get(role)
    return m * 60 if isinstance(m, int | float) and not isinstance(m, bool) and m > 0 else None


def deadline(cfg: dict, sid: str, role: str, start: str) -> str | None:
    u = usual_s(cfg, sid, role)
    return fmt(at(start) + dt.timedelta(seconds=u * policy.watch(policy.load())["deadline_factor"])) if u else None


def job(st: dict) -> dict | None:
    """The open dispatch of an asset that waits on a subagent."""
    from .loop import current_v, open_dispatch
    role = ROLE_OF.get(st.get("state"))
    if role is None:
        return None
    return open_dispatch(st, st["stage"], current_v(st, st["stage"]), role)


def report_of(rec: dict):
    b = Path(rec["brief"]) if rec.get("brief") else None  # relative to the project folder, where P runs
    return b.with_name(REPORT[b.name]) if b and b.name in REPORT else None


def check(st: dict, rec: dict, w: dict, now: dt.datetime | None = None) -> dict:
    """D33.11: stalled = no new heartbeat for stall_min while a tool still runs, or past the deadline, or the subagent
    stopped without its report (SubagentStop). Silence counts only while the last heartbeat says a tool runs: a worker
    that thinks between tools writes none. After a nudge or a new dispatch the next rung waits stall_min again."""
    now = now or dt.datetime.now()
    start = at(rec["at"])
    hb = heartbeat.last(vdir(st["id"], rec["step"], rec["v"]))
    beat = hb if hb and hb[0] >= start else None
    since = max([start, *([beat[0]] if beat else []), *([at(rec["nudged_at"])] if rec.get("nudged_at") else [])])
    grace = rec.get("nudged_at") and (now - at(rec["nudged_at"])).total_seconds() < w["stall_min"] * 60
    rep = report_of(rec)
    why = None
    if rep is not None and rep.exists():
        why = None
    elif grace:
        why = None
    elif rec.get("stopped") == "no_report":
        why = "subagent dừng, không có report"
    elif beat and beat[2] in LIVE and (now - beat[0]).total_seconds() > w["stall_min"] * 60:
        why = f"không có nhịp tim mới từ {beat[0]:%H:%M} ({beat[1]})"
    elif rec.get("deadline") and now > at(rec["deadline"]):
        why = f"quá hạn chót {at(rec['deadline']):%H:%M}"
    return {"stalled": why is not None, "why": why, "beat": beat, "ran_s": (now - start).total_seconds(),
            "quiet_s": (now - since).total_seconds()}


def line(st: dict, rec: dict, w: dict, now: dt.datetime | None = None) -> str:
    """D33.15: one line per running job."""
    c = check(st, rec, w, now)
    beat = f"{c['beat'][0]:%H:%M} {c['beat'][1]} {c['beat'][2]}" if c["beat"] else "chưa có"
    due = f"{at(rec['deadline']):%H:%M}" if rec.get("deadline") else "không có"
    state = (f"KẸT {minutes(c['quiet_s'])} · nudge {rec.get('nudges', 0)}/{w['max_nudges']} → `stall {st['id']}`"
             if c["stalled"] else "OK")
    return (f"  ↳ {st['id']} · {rec['step']} v{rec['v']} · {rec['role']} · chạy {minutes(c['ran_s'])} · nhịp tim {beat}"
            f" · hạn chót {due} · {state}")


def stalled(st: dict) -> bool:
    rec = job(st)
    return bool(rec) and check(st, rec, policy.watch(policy.load()))["stalled"]


def stall(a):
    """D33.11 `P stall <id>`: the next rung of the one stall rule. Nudge (max_nudges times, needs the agent id), then one
    new agent with the same brief, then waiting_human. The script picks the rung and logs it; the Producer only sends.
    --agent-id: the id of the stuck subagent, from its launch; on-stop also records it."""
    from .briefs import run
    from .loop import UNREVIEWED, move, offer
    from .board import build_outputs
    cfg, st = load_cfg(), load_st(a.id)
    rec = job(st) or die(f"{a.id}: state={st['state']}, không có lần giao nào đang chạy")
    w = policy.watch(policy.load())
    c = check(st, rec, w)
    c["stalled"] or die(f"{a.id}: không kẹt ({rec['step']} v{rec['v']} {rec['role']}, chạy {minutes(c['ran_s'])})")
    sid, n, role = rec["step"], rec["v"], rec["role"]
    if getattr(a, "agent_id", None):
        rec["agent_id"] = a.agent_id
    entry = {"step": sid, "v": n, "role": role, "at": stamp(), "why": c["why"]}
    head = f"{a.id} · {sid} v{n} · kẹt · {role} · {c['why']}"
    if rec.get("nudges", 0) < w["max_nudges"] and rec.get("agent_id"):
        rec["nudges"] = rec.get("nudges", 0) + 1
        rec["nudged_at"] = stamp()
        rec.pop("stopped", None)  # a nudge resumes a stopped agent (maxTurns): the next SubagentStop says again
        st.setdefault("stalls", []).append(entry | {"rung": "nudge"})
        save_st(st)
        ledger(f"{head} · nudge {rec['nudges']}/{w['max_nudges']}")
        print(f"{a.id}: kẹt ({c['why']}) → nudge {rec['nudges']}/{w['max_nudges']}: gửi tới agent "
              f"{rec['agent_id']} đúng câu \"{NUDGE}\"")
        return
    rec["ended"] = {"at": stamp(), "why": c["why"]}
    if not rec.get("redispatch_of"):
        st.setdefault("stalls", []).append(entry | {"rung": "redispatch"})
        if role == "worker":
            st["worker_agent_id"] = None
        save_st(st)
        ledger(f"{head} · giao lại cho agent mới cùng brief")
        print(f"{a.id}: kẹt ({c['why']}) → giao lại cho agent mới (không resume):")
        run(a)
        st = load_st(a.id)
        st["dispatches"][-1]["redispatch_of"] = rec["at"]
        save_st(st)
        return
    st.setdefault("stalls", []).append(entry | {"rung": "human"})
    st["stalled_from"] = st["state"]
    move(st, "ask_human")
    offer(st, sid, n, label=UNREVIEWED,
          note=f"kẹt: {c['why']}; đã nudge và giao lại → hỏi người dùng; giao lại: `retry {a.id}`")
    save_st(st)
    ledger(f"{head} · waiting_human")
    build_outputs(cfg)
    print(f"{a.id}: kẹt lần 3 ({c['why']}) → waiting_human. Báo người dùng; người dùng muốn giao lại thì `retry {a.id}`")


def running() -> list[tuple[dict, dict]]:
    return [(s, r) for s in all_status() if not s.get("broken") and (r := job(s))]


def wake(w: dict) -> list[str]:
    """What ends a `P wait`: a report on disk, a stall (silence, deadline, stop without report), or nothing running."""
    jobs = running()
    if not jobs:
        return ["không có việc nào đang chạy → `next`"]
    out = []
    for st, rec in jobs:
        rep = report_of(rec)
        if rep is not None and rep.exists():
            out.append(f"{st['id']}: có báo cáo {rel(rep)} → `ingest {st['id']}`")
        elif (c := check(st, rec, w))["stalled"]:
            out.append(f"{st['id']}: kẹt ({c['why']}) → `stall {st['id']}`")
    return out


def alive(pid: int) -> bool:
    from .limits import alive as up
    return up(pid)


def take_lock():
    """D33.13: one `P wait` at a time. The lock holds the pid; a lock whose process is gone is taken over."""
    p = ROOT / LOCK
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(p.read_text(encoding="utf-8").strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and alive(pid):
                die(f"đã có một `P wait` đang chạy (pid {pid}): không tạo thêm, chờ nó thức dậy")
            p.unlink(missing_ok=True)
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return p
    die(f"không lấy được {rel(p)}")


def wait(a):
    """D33.13 `P wait`: run in the background by the Producer in `dispatch: background`. Holds no state lock while it
    sleeps; prints what woke it and exits."""
    p = take_lock()
    try:
        end = time.monotonic() + a.max_min * 60
        while True:
            w = policy.watch(policy.load())
            if hits := wake(w):
                print("\n".join(hits))
                return
            if time.monotonic() >= end:
                print(f"chưa có gì sau {a.max_min} phút → chạy lại `wait`")
                return
            time.sleep(a.every)
    finally:
        p.unlink(missing_ok=True)


def match(hook: dict) -> tuple[dict, dict] | None:
    """The open dispatch a SubagentStop belongs to: the agent id recorded at ingest, else the brief the subagent's
    prompt names (two assets on the same step share an agent type, never a brief)."""
    from . import session
    aid, path = hook.get("agent_id"), hook.get("agent_transcript_path")
    jobs = running()
    for st, rec in jobs:
        if aid and rec.get("agent_id") == aid:
            return st, rec
    lines = session.lines_of(__import__("pathlib").Path(path)) if isinstance(path, str) and path else []
    for st, rec in jobs:
        if rec.get("brief") and any(session.asks_for(x, rec["brief"]) for x in lines):
            return st, rec
    return None


def on_stop(text: str) -> str | None:
    """D33.9: hook SubagentStop → `P on-stop`. Records on disk that the subagent stopped and whether its report exists,
    so a lost notification loses nothing. Never fails the hook: exit 2 would keep the subagent running."""
    try:
        hook = json.loads(text)
    except ValueError:
        return None
    if not isinstance(hook, dict) or not str(hook.get("agent_type") or "").startswith("zps-3dp-") or not ROOT.is_dir():
        return None
    hit = match(hook)
    if hit is None:
        return None
    st, rec = hit
    rep = report_of(rec)
    has = rep is not None and rep.exists()
    rec |= {"stopped": "report" if has else "no_report", "stopped_at": stamp()}
    if hook.get("agent_id"):
        rec["agent_id"] = hook["agent_id"]
    if isinstance(hook.get("agent_transcript_path"), str):
        rec["transcript"] = hook["agent_transcript_path"]
    save_st(st)
    msg = f"{st['id']} · {rec['step']} v{rec['v']} · on-stop {rec['role']} · " + (
        "có report" if has else "không có report → `next`, rồi `stall` theo dòng KẸT")
    ledger(msg)
    return msg


def cmd_on_stop(_a):
    try:
        text = sys.stdin.read() if sys.stdin and not sys.stdin.isatty() else ""
        msg = on_stop(text)
    except Exception as ex:  # noqa: BLE001 — a hook must never block the subagent
        msg = f"on-stop lỗi: {ex}"
    if msg:
        print(msg)


SENDERS = ("Agent", "Task", "SendMessage")


def sent_to_agent(paths: list[str], rec: dict) -> bool:
    """D39.1: a main-session transcript holds an Agent, Task or SendMessage call that names the brief of this dispatch,
    made at or after it. `P brief` records a dispatch when it prints the line, so only the call shows it was sent. A
    transcript that cannot be read, or none known, counts as sent: an unknown must never refuse a stop."""
    from . import session
    if not paths:
        return True
    since, brief = at(rec["at"]), rec["brief"]
    quoted = json.dumps(brief, ensure_ascii=False)[1:-1]
    for p in paths:
        try:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            return True
        for line in lines:
            if brief not in line and quoted not in line:
                continue
            try:
                d = json.loads(line)
                when = session.local(d["timestamp"])
                blocks = d["message"]["content"]
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if d.get("type") != "assistant" or when < since or not isinstance(blocks, list):
                continue
            if any(isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in SENDERS
                   and brief in json.dumps(b.get("input"), ensure_ascii=False) for b in blocks):
                return True
    return False


def main_stop_reason(sts: list[dict], exists, sent) -> str | None:
    """D39.1: why the main session may not stop now, as one line that names the command to run, else None.
    (a) an open dispatch whose report is on disk and not ingested; (b) an open dispatch with no sign of a subagent, so
    the line `P brief` printed was never sent. A subagent that runs without a report is waited for (background mode),
    and an asset that waits for the human has no open dispatch."""
    open_jobs = [(st, rec) for st in sts if not st.get("broken") and (rec := job(st))]
    for st, rec in open_jobs:
        rep = report_of(rec)
        if rep is not None and exists(rep):
            return f"Còn report chưa ingest: chạy `P ingest {st['id']} --agent-id {rec.get('agent_id') or '<id subagent>'}`"
    for st, rec in open_jobs:
        if not (rec.get("stopped") or rec.get("agent_id") or sent(st, rec)):
            return (f"Còn dòng giao việc của {st['id']} chưa giao: giao theo dòng JSON của `P brief {st['id']}` "
                    "(chạy lại lệnh này nếu mất dòng)")
    return None


def on_main_stop(text: str) -> str | None:
    """D39.1: hook Stop of the main session → `P on-main-stop`. Reads the disk only and prints nothing when the stop is
    allowed. Allowed too: the turn already goes on because this hook refused (`stop_hook_active`, else a loop), and a
    project with no production folder."""
    from . import session
    try:
        hook = json.loads(text)
    except ValueError:
        return None
    if not isinstance(hook, dict) or hook.get("stop_hook_active") or not ROOT.is_dir():
        return None
    paths = [p for p in [hook.get("transcript_path"), *((session.load() or {}).get("transcripts") or [])]
             if isinstance(p, str) and p]

    def sent(st: dict, rec: dict) -> bool:
        beat = heartbeat.last(vdir(st["id"], rec["step"], rec["v"]))
        return bool(beat and beat[0] >= at(rec["at"])) or sent_to_agent(paths, rec)
    return main_stop_reason(all_status(), Path.exists, sent)


def cmd_on_main_stop(_a) -> int:
    """Exit 2 and one line on stderr refuse the stop (Claude Code 2.1.318 feeds stderr to the model and goes on); every
    other outcome, a failure of this hook too, exits 0 and allows it."""
    try:
        why = on_main_stop(sys.stdin.read() if sys.stdin and not sys.stdin.isatty() else "")
    except Exception:  # noqa: BLE001 — a hook that fails must allow the stop
        return 0
    if why:
        print(why, file=sys.stderr)
        return 2
    return 0
