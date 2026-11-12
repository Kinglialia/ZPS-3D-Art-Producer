"""`P next` report with `[limits]` slots (docs/producer.md §12) and preflight gating (§14 1b)."""
from __future__ import annotations

import datetime as dt
import os

from . import asset_card, preflight, purge
from .board import build_outputs
from .hashes import schedule_soon, warnings_for
from .loop import next_action
from .state import FINISHED, ProducerError, PORT, ROOT, all_status, load_cfg, rel, sort_key

DISPATCH = ("todo", "fix", "evidence")


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def used(cfg: dict, resource: str, sts: list[dict]) -> int:
    """C17: a slot is held by every open worker dispatch of a step that uses the resource, from its dispatch to its
    ingest. A pid file lives only while a tool runs, so counting them when the Producer dispatches capped nothing."""
    from .watch import job
    uses = {s["id"]: s["uses"] for s in cfg["steps"]}
    return sum(1 for s in sts if not s.get("broken") and (r := job(s)) and r["role"] == "worker"
               and resource in uses.get(r["step"], ()))


def slots(cfg: dict, sts: list[dict]) -> dict[str, int]:
    return {r: lim - used(cfg, r, sts) for r, lim in cfg["limits"].items()}


def full(step: dict, free: dict[str, int]) -> list[str]:
    return [r for r in step["uses"] if r in free and free[r] <= 0]


def gate(step: dict, pf, free: dict[str, int]) -> str | None:
    """Why a worker of this step cannot go out now, else None; a None takes its slots, so one `P next` offers no more
    workers than the slots hold."""
    if off := preflight.off(step, pf):
        return f"không giao: tắt {', '.join(off)} (preflight)"
    if busy := full(step, free):
        return f"chờ slot {', '.join(busy)}"
    for r in step["uses"]:
        if r in free:
            free[r] -= 1
    return None


def ready(cfg: dict, sts: list[dict], pf) -> list[dict]:
    """C17: the assets `P next` offers to dispatch now: a reviewer always, a worker when its gate is open."""
    steps, free, out = {s["id"]: s for s in cfg["steps"]}, slots(cfg, sts), []
    for s in sorted(sts, key=sort_key):
        step = steps.get(s.get("stage"))
        if step and not s.get("broken") and (s["state"] == "review" or s["state"] in DISPATCH and not gate(step, pf, free)):
            out.append(s)
    return out


def show_next(a):
    cfg = load_cfg()
    sts = sorted(all_status(), key=sort_key)
    active = [s for s in sts if s.get("state") not in FINISHED]
    build_outputs(cfg)
    if a.session:
        print("[producer] Dùng skill zps-3dp-producer cho mọi việc về asset, feedback, tiến độ. Trạng thái hiện tại:")
    print(f"{len(active)} asset đang chạy · {len(sts) - len(active)} done · review page: `serve` → http://127.0.0.1:{PORT}")
    for line in purge.on_next(a):
        print(line)
    if w := purge.disk_warning():
        print(w)
    pf = preflight.load()
    if pf is None:
        print(f"Chưa có {rel(preflight.OUT)} → chạy `preflight` một lần mỗi phiên")
    soon = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    due = [s for s in active if s.get("deadline") and s["deadline"] <= soon]
    if due:
        print("Deadline ≤14 ngày: " + ", ".join(f"{s['id']} ({s['deadline']})" for s in due))
    ms = schedule_soon()
    if ms:
        print("Milestone ≤14 ngày: " + "; ".join(f"{d} {t}" for d, t in ms))
    from . import policy, watch
    try:
        wt = policy.watch(policy.load())
    except ProducerError:  # a broken policy.yaml never hides the asset list; the purge line above names the error
        wt = policy.template()["watch"]
    steps = {s["id"]: s for s in cfg["steps"]}
    free = slots(cfg, sts)
    for s in sts:
        ids = [x["id"] for x in asset_card.steps(cfg, s)] if s.get("state") == "done_enabled" else []
        i = ids.index(s["stage"]) if s.get("stage") in ids else -1
        if 0 <= i < len(ids) - 1 and steps[ids[i + 1]]["enabled"]:
            print(f"[{s['id']}] {s['stage']}/done_enabled → bước {ids[i + 1]} đã bật → `retry {s['id']}`")
    for s in active:
        act, step = next_action(s), steps.get(s.get("stage"))
        if step and s.get("state") in DISPATCH and (held := gate(step, pf, free)):
            act = held
        w = warnings_for(cfg, s)
        flag = f"  ⚠ {'; '.join(w)} → hỏi người dùng làm lại hay giữ, rồi `ack {s['id']}`" if w else ""
        print(f"[{s['id']}] {s.get('stage')}/{s.get('state')} → {act}{flag}")
        if rec := watch.job(s):
            print(watch.line(s, rec, wt))
    p = ROOT / "ledger.md"
    rulings = [l for l in p.read_text(encoding="utf-8").splitlines() if "RULING:" in l][-3:] if p.exists() else []
    if rulings:
        print("Ruling gần nhất:\n" + "\n".join(rulings))
