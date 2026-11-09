"""Ingest state machine (docs/producer.md §3, §4, §7, §8): rounds, early stop, need_evidence, redo, gates, approve."""
from __future__ import annotations

import shutil

from . import findings, hashes, policy
from .contract import parse_review, parse_worker
from .state import ASSETS, ROOT, die, ledger, load_cfg, load_st, now, rel, save_st, step_of, vdir

NOT_PASSED = "chưa đạt"
REDOING = "**đang làm lại**\n\n"
REDO_FROM = ("todo", "fix", "review", "evidence", "waiting_human", "blocked", "done", "done_enabled")
NEXT = "next"
MOVES = {
    ("todo", "dispatch"): "running", ("fix", "dispatch"): "running", ("running", "dispatch"): "running",
    ("review", "dispatch"): "reviewing", ("reviewing", "dispatch"): "reviewing",
    ("evidence", "dispatch"): "evidence_running", ("evidence_running", "dispatch"): "evidence_running",
    ("running", "worker_done"): "review", ("running", "checks_done"): "waiting_human", ("running", "stuck"): "blocked",
    ("evidence_running", "worker_done"): "review", ("evidence_running", "stuck"): "blocked",
    ("reviewing", "fix"): "fix", ("reviewing", "need_evidence"): "evidence", ("reviewing", "reopen"): "fix",
    ("reviewing", "await_approval"): "waiting_human", ("reviewing", "ask_human"): "waiting_human",
    ("reviewing", "approve"): NEXT, ("waiting_human", "approve"): NEXT,
    ("blocked", "retry"): "running", ("blocked", "retry_evidence"): "evidence", ("blocked", "retry_todo"): "todo",
    **{(s, "redo"): "fix" for s in REDO_FROM},
}


def fresh() -> dict:
    return {"fix_round": 0, "fix_base": None, "round_versions": [], "evidence": None, "evidence_used": 0,
            "offer": None, "label": "", "note": ""}


def move(st: dict, event: str, cfg: dict | None = None):
    nxt = MOVES.get((st["state"], event)) or die(f"{st['id']}: không {event} được ở state={st['state']}")
    if nxt != NEXT:
        st["state"] = nxt
        return
    i, _ = step_of(cfg, st["stage"])
    st |= fresh() | {"worker_agent_id": None}
    after = cfg["steps"][i + 1] if i + 1 < len(cfg["steps"]) else None
    if after is None:
        st["state"] = "done"
    elif not after["enabled"]:
        st["state"], st["note"] = "done_enabled", f"bước {after['id']} chưa bật"
    else:
        st["stage"], st["state"] = after["id"], "todo"


def review_event(verdict: str, top_kind: str | None, auto: bool, fix_round: int, max_rounds: int, progressed: bool,
                 evidence_used: int, reopened: int = 0) -> tuple[str, str | None]:
    """§7: what a valid review leads to. fix_round is the fix round that built the reviewed version (0 = first build).
    reopened: earlier steps a reviewer reopened in this feedback round (regen_front costs a new front and a new set)."""
    if verdict == "ESCALATE":
        return "ask_human", "reviewer ESCALATE"
    if verdict == "PASS":
        return ("approve", None) if auto else ("await_approval", None)
    if top_kind == "need_evidence":
        return ("ask_human", "xin bằng chứng lần 2") if evidence_used else ("need_evidence", None)
    if top_kind in findings.REOPEN:
        return ("ask_human", f"{top_kind} lần 2") if reopened else ("reopen", None)
    if fix_round >= max_rounds:
        return "ask_human", f"hết {max_rounds} vòng sửa"
    if fix_round >= 2 and not progressed:
        return "ask_human", f"không tiến bộ ở vòng {fix_round}"
    return "fix", None


def review_base(st: dict, n: int) -> int | None:
    return n if st.get("evidence") else st.get("fix_base")


def next_action(st: dict) -> str:
    aid, s = st["id"], st.get("state")
    if s == "draft":
        return f"chờ người dùng duyệt brief + rubric → `ready {aid}`"
    if s in ("todo", "fix"):
        return f"giao worker → `brief {aid}`"
    if s == "evidence":
        return f"giao worker render bằng chứng → `brief {aid}`"
    if s == "review":
        return f"giao reviewer → `brief {aid}`"
    if s in ("running", "reviewing", "evidence_running"):
        n = st.get("versions", {}).get(st["stage"])
        d = vdir(aid, st["stage"], n) if n else None
        rep = {"running": "report-worker.md", "reviewing": "report-review.md"}.get(s)
        if s == "evidence_running" and st.get("evidence"):
            rep = f"review/evidence-{st['evidence']['k']}/report-worker.md"
        if d and rep and (d / rep).exists():
            return f"có báo cáo → `ingest {aid}`"
        return f"đang chờ subagent (mất kết nối thì `brief {aid}` để giao lại)"
    if s == "waiting_human":
        return f"chờ người dùng: {st.get('note') or 'duyệt'} (review page)"
    if s == "blocked":
        return f"xử lý: {st.get('note')} → bổ sung rồi `retry {aid}`"
    if s == "done_enabled":
        return "xong các bước đang bật"
    return "xong"


def read_report(rep) -> str:
    if not rep.exists():
        die(f"chưa có báo cáo {rel(rep)}")
    return rep.read_text(encoding="utf-8")


def set_aside(rep):
    """A new dispatch waits for a new report: the old one becomes `<name>-<k>.md`."""
    if rep.exists():
        rep.rename(rep.with_name(f"{rep.stem}-{1 + len(list(rep.parent.glob(f'{rep.stem}-*.md')))}.md"))


def offer(st: dict, sid: str, n: int, **kw):
    """D22.8 per offer: an offered version takes a new decision, also when it was decided in an earlier round."""
    st.setdefault("decisions", {}).pop(f"{sid} v{n}", None)
    st |= {"offer": n, **kw}


def valid(rep, parsed: tuple):
    out, errs = parsed
    if errs:
        die(f"{rel(rep)} sai contract: {'; '.join(errs)}")
    return out


def worker_report(st: dict, rep, agent_id, sid: str, n: int) -> dict:
    c = valid(rep, parse_worker(read_report(rep)))
    inp = (st.get("inputs") or {}).get(sid, {}).get(f"v{n}") or {}
    if c["PROFILE_HASH"] != inp.get("profile"):
        die(f"{rel(rep)}: PROFILE_HASH {c['PROFILE_HASH']} khác brief ({inp.get('profile')})")
    hashes.check_inputs(st, inp)
    if agent_id:
        st["worker_agent_id"] = agent_id
    return c


def stuck(c: dict) -> str | None:
    return f"{c['STATUS']}: {c.get('ISSUES', '')}" if c["STATUS"] in ("NEEDS_CONTEXT", "BLOCKED") else None


def on_worker(cfg, st, step, d, n, a) -> tuple[str, str]:
    c = worker_report(st, d / "report-worker.md", a.agent_id, step["id"], n)
    st["last_rubric"] = c.get("RUBRIC", "")
    missing = [o for o in step["outputs"] if not (d / o).exists()]
    if why := stuck(c) or (missing and "thiếu output bắt buộc: " + ", ".join(missing)):
        move(st, "stuck")
        st["note"] = why
    elif step["gate"] == "checks_human":
        move(st, "checks_done")
        offer(st, step["id"], n, note=f"duyệt {step['id']} v{n}")
    else:
        move(st, "worker_done")
        st["note"] = ""
    return f"worker {c['STATUS']}", ""


def on_evidence(cfg, st, step, d, n, a) -> tuple[str, str]:
    tag = f"evidence-{st['evidence']['k']}"
    c = worker_report(st, d / "review" / tag / "report-worker.md", a.agent_id, step["id"], n)
    if why := stuck(c):
        move(st, "stuck")
        st["note"] = why
    elif hashes.tree_hash(d / "final") != st["evidence"]["hash"]:
        move(st, "stuck")
        st["evidence"], st["note"] = None, f"{tag}: final/ đổi trong vòng bằng chứng, bỏ kết quả"
    else:
        move(st, "worker_done")
        st["note"] = ""
    return f"{tag} {c['STATUS']}", ""


def take_variant(d, pick: str):
    src = d / "variants" / pick
    if not src.is_dir():
        die(f"PICK {pick}: không có {rel(src)}/")
    a = d / "variants" / "a"
    if a.exists():
        shutil.rmtree(d / "final")
    else:
        shutil.move(str(d / "final"), str(a))
    shutil.copytree(src, d / "final")


def on_review(cfg, st, step, d, n, a) -> tuple[str, str]:
    aid, sid, r = st["id"], step["id"], cfg["review"]
    rep = d / "report-review.md"
    rv = valid(rep, parse_review(read_report(rep)))
    doc = valid(rep, findings.apply(findings.load(aid, sid, review_base(st, n)), rv, step, n))
    who = "human"
    if step["gate"] == "review":
        who = "reviewer"
    elif rv["verdict"] == "PASS" and step["gate"] == "review_human":
        who = policy.approver(policy.load(), sid, aid)
    if rv["pick"] and rv["pick"] != "a":
        take_variant(d, rv["pick"])
    findings.save(aid, sid, doc)
    rvs = st.setdefault("round_versions", [])
    if n not in rvs:
        rvs.append(n)
    base = findings.load(aid, sid, st.get("fix_base"))
    kind = (rv["top_fix"] or {}).get("kind")
    event, reason = review_event(rv["verdict"], kind, who != "human", st.get("fix_round", 0), r["max_fix_rounds"],
                                 bool(base) and findings.progress(base, doc), st.get("evidence_used", 0),
                                 st.get("reopened", 0))
    st["evidence"] = None
    st["last_rubric"] = "; ".join(f"{k}={x}" for k, x in rv["rubric"].items())
    best = findings.best_version([findings.load(aid, sid, v) for v in rvs])
    if event == "reopen":
        move(st, event)
        tid, fid = findings.REOPEN[kind], rv["top_fix"]["ids"][0]
        ti, target = step_of(cfg, tid)
        m = st["approved"].get(tid) or die(f"{aid}: {kind} cần bản {tid} đã duyệt")
        new = findings.carry(aid, doc["findings"][fid], f"{sid} v{n} {fid}", target, m)
        reopen(cfg, st, ti, target, m, f"{kind}: sửa {tid} v{m} theo {new} ({sid} v{n} {fid})")
        st["reopened"] = st.get("reopened", 0) + 1
        reason = f"{kind} → {tid} v{m} {new}"
    elif event == "approve":
        approve(cfg, st, step, n, "reviewer" if who == "reviewer" else policy.BY[who])
    elif event == "await_approval":
        move(st, event)
        offer(st, sid, n, note=f"duyệt {sid} v{n}", label="")
    elif event == "ask_human":
        move(st, event)
        ids = ", ".join(findings.open_of(findings.load(aid, sid, best)))
        offer(st, sid, best, note=reason + (f"; còn mở: {ids}" if ids else ""), label=NOT_PASSED)
    elif event == "fix":
        move(st, event)
        st["fix_round"] = st.get("fix_round", 0) + 1
        st |= {"fix_base": best, "note": f"vòng sửa {st['fix_round']}/{r['max_fix_rounds']}"}
    else:
        move(st, event)
        st["evidence_used"] = st.get("evidence_used", 0) + 1
        k = 1 + sum(1 for _ in (d / "review").glob("evidence-*"))
        st |= {"evidence": {"version": n, "k": k, "hash": hashes.tree_hash(d / "final")},
               "note": "xin bằng chứng: " + ", ".join(rv["top_fix"]["ids"])}
    return f"review {rv['verdict']} ({findings.short(findings.open_counts(doc))})", reason or ""


HANDLERS = {"running": on_worker, "evidence_running": on_evidence, "reviewing": on_review}


def ingest(a):
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(a.id)
    _, step = step_of(cfg, st["stage"])
    n = st["versions"].get(step["id"])
    h = HANDLERS.get(st["state"]) or die(f"{a.id}: state={st['state']}, không có báo cáo nào đang chờ")
    event, reason = h(cfg, st, step, vdir(a.id, step["id"], n), n, a)
    save_st(st)
    ledger(f"{a.id} · {step['id']} v{n} · {event} · {st.get('last_rubric', '')}" + (f" · {reason}" if reason else ""))
    build_outputs(cfg)
    print(f"{a.id}: {event} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")


def approve(cfg: dict, st: dict, step: dict, n: int, by: str):
    sid = step["id"]
    st["approved"][sid] = n
    st.setdefault("approved_hash", {})[sid] = hashes.tree_hash(vdir(st["id"], sid, n) / "final")
    st.setdefault("rejected", {})[sid] = [v for v in range(1, st["versions"][sid] + 1) if v != n]
    st.setdefault("prior", {}).pop(sid, None)
    if sid == "assemble":
        out = ROOT.parent / "deliver" / st["id"]
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(vdir(st["id"], sid, n) / "final", out)
    ledger(f"{st['id']} · {sid} v{n} · duyệt bởi {by}")
    move(st, "approve", cfg)
    hashes.refresh_stale(cfg, st)


def reopen(cfg: dict, st: dict, i: int, step: dict, n: int | None, note: str):
    """A fix round of `step` from version n; this step and every later one lose their approval.
    A later approved version becomes `prior`, so its next build can keep what did not change (concept-views.md §9)."""
    later = {s["id"]: st["approved"][s["id"]] for s in cfg["steps"][i + 1:] if s["id"] in st["approved"]}
    st.setdefault("prior", {}).update(later)
    if st["stage"] != step["id"]:
        st["worker_agent_id"] = None
    st |= fresh() | {"stage": step["id"], "fix_round": 1, "fix_base": n, "round_versions": [n] if n else [],
                     "note": note}
    for s in cfg["steps"][i:]:
        for k in ("approved", "approved_hash", "rejected"):
            st.setdefault(k, {}).pop(s["id"], None)
    hashes.refresh_stale(cfg, st)


def redo(cfg: dict, st: dict, i: int, step: dict, n: int | None, text: str):
    move(st, "redo")
    if n:
        findings.add_human(st["id"], step, n, text)
    reopen(cfg, st, i, step, n, "làm lại theo feedback người dùng")
    st["reopened"] = 0
    readme = ROOT.parent / "deliver" / st["id"] / "README.md"
    if readme.exists() and not (t := readme.read_text(encoding="utf-8")).startswith(REDOING):
        readme.write_text(REDOING + t, encoding="utf-8")


def retry(a):
    st = load_st(a.id)
    move(st, "retry_evidence" if st.get("evidence") else "retry" if st["versions"].get(st["stage"]) else "retry_todo")
    if st["state"] == "running":
        set_aside(vdir(a.id, st["stage"], st["versions"][st["stage"]]) / "report-worker.md")
    st["note"] = ""
    save_st(st)
    ledger(f"{a.id} · retry")
    print(f"{a.id}: → {st['state']}. Tiếp: {next_action(st)}")


def append_feedback(aid: str, step: str, n: int | None, action: str, text: str):
    tag = f"{step} v{n}" if n else step
    with open(ASSETS / aid / "feedback.md", "a", encoding="utf-8") as f:
        f.write(f"- {now()} · {tag} · {action} · {text.strip()}\n")


def shown(st: dict, step: str) -> int | None:
    if step == st["stage"] and st.get("offer"):
        return st["offer"]
    return st["approved"].get(step) or st["versions"].get(step)


def human_action(aid: str, action: str, text: str, step_id: str | None = None) -> str:
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(aid)
    if action not in ("approve", "redo", "note"):
        die("action phải là approve | redo | note")
    target = step_id or st["stage"]
    i, step = step_of(cfg, target)
    if action == "redo" and i > step_of(cfg, st["stage"])[0]:
        die(f"{aid}: không làm lại {target} được: asset đang ở bước {st['stage']}")
    n = shown(st, target)
    key = f"{target} v{n}"
    done = st.setdefault("decisions", {})
    send_back = action == "redo" and n is not None and st["approved"].get(target) == n
    if action != "note" and key in done and not send_back:
        return f"{aid}: bỏ qua {action} {key}: đã có quyết định lúc {done[key]['at']}"
    text = text.strip() or "(không ghi chú)"
    append_feedback(aid, target, n, action, text)
    msg = "đã ghi feedback"
    if action == "approve":
        if st["state"] != "waiting_human" or target != st["stage"]:
            msg = f"đã ghi feedback; {aid} không chờ duyệt {target} (state={st['state']})"
        else:
            done[key] = {"action": action, "at": now()}
            approve(cfg, st, step, n, policy.BY["human"])
            msg = f"đã duyệt {key} → {st['stage']}/{st['state']}"
    elif action == "redo":
        if st["state"] not in REDO_FROM:
            msg = f"đã ghi feedback; {aid} đang {st['state']}, sẽ áp dụng ở vòng sau"
        else:
            done[key] = {"action": action, "at": now()}
            redo(cfg, st, i, step, n, text)
            msg = f"làm lại {target}" + (f" từ v{n}" if n else "")
    save_st(st)
    ledger(f"{aid} · người dùng {action} {target} · {text.strip()[:80]}")
    build_outputs(cfg)
    return f"{aid}: {msg}. Tiếp: {next_action(st)}"
