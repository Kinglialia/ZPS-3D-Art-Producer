"""Ingest state machine: worker and reviewer reports, gates, approve, retry, human feedback."""
from __future__ import annotations

from . import findings
from .contract import parse_review, parse_worker
from .state import ASSETS, die, ledger, load_cfg, load_st, now, rel, save_st, step_of, vdir


def advance(cfg: dict, st: dict, i: int):
    steps = cfg["steps"]
    st["fix_round"] = 0
    st["worker_agent_id"] = None
    st["note"] = ""
    if i + 1 < len(steps):
        st["stage"] = steps[i + 1]["id"]
        st["state"] = "todo"
    elif cfg["review"]["final_human_gate"]:
        st["state"] = "waiting_human"
        st["final_pending"] = True
        st["note"] = "Duyệt cuối"
    else:
        st["state"] = "done"


def approve_step(cfg: dict, st: dict, i: int, step: dict):
    st["approved"][step["id"]] = st["versions"].get(step["id"])
    advance(cfg, st, i)


def next_action(st: dict) -> str:
    aid, s = st["id"], st.get("state")
    if s == "draft":
        return f"chờ người dùng duyệt brief + rubric → `ready {aid}`"
    if s in ("todo", "fix"):
        return f"giao worker → `brief {aid}`"
    if s == "review":
        return f"giao reviewer → `brief {aid}`"
    if s in ("running", "reviewing"):
        name = "report-worker.md" if s == "running" else "report-review.md"
        n = st.get("versions", {}).get(st["stage"])
        if n and (vdir(aid, st["stage"], n) / name).exists():
            return f"có báo cáo → `ingest {aid}`"
        return f"đang chờ subagent (mất kết nối thì `brief {aid}` để giao lại)"
    if s == "waiting_human":
        return f"chờ người dùng: {st.get('note') or 'duyệt'} (review page)"
    if s == "blocked":
        return f"xử lý: {st.get('note')} → bổ sung rồi `retry {aid}`"
    return "xong"


def read_report(rep) -> str:
    if not rep.exists():
        die(f"chưa có báo cáo {rel(rep)}")
    return rep.read_text(encoding="utf-8")


def valid(rep, parsed: tuple):
    out, errs = parsed
    if errs:
        die(f"{rel(rep)} sai contract: {'; '.join(errs)}")
    return out


def ingest(a):
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(a.id)
    i, step = step_of(cfg, st["stage"])
    n = st["versions"].get(step["id"])
    d = vdir(a.id, step["id"], n) if n else None
    r = cfg["review"]
    if st["state"] == "running":
        rep = d / "report-worker.md"
        c = valid(rep, parse_worker(read_report(rep)))
        if a.agent_id:
            st["worker_agent_id"] = a.agent_id
        st["last_rubric"] = c.get("RUBRIC", "")
        missing = [o for o in step["outputs"] if not (d / o).exists()]
        if c["STATUS"] in ("NEEDS_CONTEXT", "BLOCKED"):
            st["state"], st["note"] = "blocked", f"{c['STATUS']}: {c.get('ISSUES', '')}"
        elif missing:
            st["state"], st["note"] = "blocked", "thiếu output bắt buộc: " + ", ".join(missing)
        elif step["gate"] == "checks_human":
            st["state"], st["note"] = "waiting_human", f"duyệt {step['id']} v{n}"
        else:
            st["state"], st["note"] = "review", ""
        event = f"worker {c['STATUS']}"
    elif st["state"] == "reviewing":
        rep = d / "report-review.md"
        rv = valid(rep, parse_review(read_report(rep)))
        doc = valid(rep, findings.apply(findings.load(a.id, step["id"], st.get("fix_base")), rv, step, n))
        findings.save(a.id, step["id"], doc)
        v = rv["verdict"]
        st["last_rubric"] = "; ".join(f"{k}={x}" for k, x in rv["rubric"].items())
        if v == "PASS" and step["gate"] == "review_human":
            st["state"], st["note"] = "waiting_human", f"duyệt {step['id']} v{n}"
        elif v == "PASS":
            approve_step(cfg, st, i, step)
        elif v == "FIX":
            st["fix_round"] = st.get("fix_round", 0) + 1
            if st["fix_round"] > r["max_fix_rounds"]:
                st["state"] = "waiting_human"
                st["note"] = f"{step['id']}: quá {r['max_fix_rounds']} vòng sửa, cần người dùng quyết"
            else:
                st["state"], st["note"] = "fix", f"vòng sửa {st['fix_round']}/{r['max_fix_rounds']}"
        else:
            st["state"], st["note"] = "waiting_human", f"reviewer ESCALATE ở {step['id']} v{n}"
        event = f"review {v} ({findings.short(findings.open_counts(doc))})"
    else:
        die(f"{a.id}: state={st['state']}, không có báo cáo nào đang chờ")
    save_st(st)
    ledger(f"{a.id} · {step['id']} v{n} · {event} · {st.get('last_rubric', '')}")
    build_outputs(cfg)
    print(f"{a.id}: {event} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")


def retry(a):
    st = load_st(a.id)
    if st["state"] != "blocked":
        die(f"{a.id} không ở state blocked")
    st["state"] = "running" if st["versions"].get(st["stage"]) else "todo"
    st["note"] = ""
    save_st(st)
    ledger(f"{a.id} · retry")
    print(f"{a.id}: → {st['state']}. Tiếp: {next_action(st)}")


def append_feedback(aid: str, st: dict, action: str, text: str, step: str):
    n = st.get("versions", {}).get(step)
    tag = f"{step} v{n}" if n else step
    with open(ASSETS / aid / "feedback.md", "a", encoding="utf-8") as f:
        f.write(f"- {now()} · {tag} · {action} · {text.strip()}\n")


def human_action(aid: str, action: str, text: str, step_id: str | None = None) -> str:
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(aid)
    if action not in ("approve", "redo", "note"):
        die("action phải là approve | redo | note")
    target = step_id or st["stage"]
    step_of(cfg, target)
    append_feedback(aid, st, action, text or "(không ghi chú)", target)
    msg = "đã ghi feedback"
    if action == "approve":
        if st["state"] != "waiting_human":
            msg = f"đã ghi feedback; {aid} không chờ duyệt (state={st['state']})"
        elif st.get("final_pending"):
            st["state"], st["note"] = "done", ""
            st.pop("final_pending", None)
            msg = "đã duyệt cuối → done"
        else:
            i, step = step_of(cfg, st["stage"])
            approve_step(cfg, st, i, step)
            msg = f"đã duyệt {step['id']} → {st['stage']}/{st['state']}"
    elif action == "redo":
        if st["state"] in ("running", "reviewing", "draft"):
            msg = f"đã ghi feedback; {aid} đang {st['state']}, sẽ áp dụng ở vòng sau"
        else:
            i, _ = step_of(cfg, target)
            st["stage"], st["state"], st["fix_round"] = target, "fix", 1
            st["note"] = "làm lại theo feedback người dùng"
            st.pop("final_pending", None)
            for s in cfg["steps"][i:]:
                st["approved"].pop(s["id"], None)
            msg = f"làm lại {target}"
    save_st(st)
    ledger(f"{aid} · người dùng {action} {target} · {text.strip()[:80]}")
    build_outputs(cfg)
    return f"{aid}: {msg}. Tiếp: {next_action(st)}"
