"""`P next` report; `[limits]`, `uses` and slot count land here in T4."""
from __future__ import annotations

import datetime as dt

from .board import build_outputs
from .hashes import schedule_soon, warnings_for
from .loop import next_action
from .state import PORT, ROOT, all_status, load_cfg, sort_key


def show_next(a):
    cfg = load_cfg()
    sts = sorted(all_status(), key=sort_key)
    active = [s for s in sts if s.get("state") != "done"]
    build_outputs(cfg)
    if a.session:
        print("[producer] Dùng skill zps-3dp-producer cho mọi việc về asset, feedback, tiến độ. Trạng thái hiện tại:")
    print(f"{len(active)} asset đang chạy · {len(sts) - len(active)} done · review page: `serve` → http://127.0.0.1:{PORT}")
    soon = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    due = [s for s in active if s.get("deadline") and s["deadline"] <= soon]
    if due:
        print("Deadline ≤14 ngày: " + ", ".join(f"{s['id']} ({s['deadline']})" for s in due))
    ms = schedule_soon()
    if ms:
        print("Milestone ≤14 ngày: " + "; ".join(f"{d} {t}" for d, t in ms))
    for s in active:
        w = warnings_for(cfg, s)
        flag = f"  ⚠ {'; '.join(w)} → hỏi người dùng làm lại hay giữ, rồi `ack {s['id']}`" if w else ""
        print(f"[{s['id']}] {s.get('stage')}/{s.get('state')} → {next_action(s)}{flag}")
    p = ROOT / "ledger.md"
    rulings = [l for l in p.read_text(encoding="utf-8").splitlines() if "RULING:" in l][-3:] if p.exists() else []
    if rulings:
        print("Ruling gần nhất:\n" + "\n".join(rulings))
