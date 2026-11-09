"""`P next` report with `[limits]` slots (docs/producer.md §12) and preflight gating (§14 1b)."""
from __future__ import annotations

import datetime as dt
import os

from . import preflight
from .board import build_outputs
from .hashes import schedule_soon, warnings_for
from .loop import next_action
from .state import PORT, ROOT, all_status, load_cfg, rel, sort_key

FINISHED = ("done", "done_enabled")
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


def used(resource: str) -> int:
    """D21.9: a slot is a live process in production/pids/<resource>/*.pid, not an asset in state `running`."""
    n = 0
    for p in (ROOT / "pids" / resource).glob("*.pid"):
        try:
            n += alive(int(p.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            pass
    return n


def show_next(a):
    cfg = load_cfg()
    sts = sorted(all_status(), key=sort_key)
    active = [s for s in sts if s.get("state") not in FINISHED]
    build_outputs(cfg)
    if a.session:
        print("[producer] Dùng skill zps-3dp-producer cho mọi việc về asset, feedback, tiến độ. Trạng thái hiện tại:")
    print(f"{len(active)} asset đang chạy · {len(sts) - len(active)} done · review page: `serve` → http://127.0.0.1:{PORT}")
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
    steps = {s["id"]: s for s in cfg["steps"]}
    free = {r: lim - used(r) for r, lim in cfg["limits"].items()}
    for s in active:
        act, step = next_action(s), steps.get(s.get("stage"))
        if step and s.get("state") in DISPATCH:
            if off := preflight.off(step, pf):
                act = f"không giao: tắt {', '.join(off)} (preflight)"
            elif full := [r for r in step["uses"] if r in free and free[r] <= 0]:
                act = f"chờ slot {', '.join(full)}"
            else:
                for r in step["uses"]:
                    if r in free:
                        free[r] -= 1
        w = warnings_for(cfg, s)
        flag = f"  ⚠ {'; '.join(w)} → hỏi người dùng làm lại hay giữ, rồi `ack {s['id']}`" if w else ""
        print(f"[{s['id']}] {s.get('stage')}/{s.get('state')} → {act}{flag}")
    p = ROOT / "ledger.md"
    rulings = [l for l in p.read_text(encoding="utf-8").splitlines() if "RULING:" in l][-3:] if p.exists() else []
    if rulings:
        print("Ruling gần nhất:\n" + "\n".join(rulings))
