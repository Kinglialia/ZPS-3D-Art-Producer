"""Ingest state machine (docs/producer.md §3, §4, §7, §8): rounds, early stop, need_evidence, redo, gates, approve."""
from __future__ import annotations

import hashlib
import re
import shutil

from . import annotate, findings, hashes, policy, texture
from .contract import parse_contract, parse_findings, parse_review, parse_worker, unwrap
from .state import ASSETS, DELIVER, die, ledger, load_cfg, load_st, now, outputs_of, rel, save_st, step_of, vdir

NOT_PASSED = "chưa đạt"
ACTIONS = ("approve", "redo", "note", "paint")
STATUS_LINE = "Trạng thái:"
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
    ("reviewing", "stuck"): "blocked",
    ("reviewing", "await_approval"): "waiting_human", ("reviewing", "ask_human"): "waiting_human",
    ("reviewing", "approve"): NEXT, ("waiting_human", "approve"): NEXT, ("done_enabled", "resume"): NEXT,
    ("blocked", "retry"): "running", ("blocked", "retry_evidence"): "evidence", ("blocked", "retry_todo"): "todo",
    ("blocked", "retry_fix"): "fix", ("todo", "stuck"): "blocked", ("fix", "stuck"): "blocked",
    ("todo", "ask_human"): "waiting_human", ("fix", "ask_human"): "waiting_human", ("running", "ask_human"): "waiting_human",
    ("waiting_human", "answer_fix"): "fix", ("waiting_human", "answer_todo"): "todo",
    **{(s, "redo"): "fix" for s in REDO_FROM},
}


def fresh() -> dict:
    return {"fix_round": 0, "fix_base": None, "round_versions": [], "evidence": None, "evidence_used": 0,
            "offer": None, "offer_key": None, "label": "", "note": ""}


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
    reopened: times this TOP_FIX kind reopened an earlier step in this feedback round (regen_front costs a new front and
    a new set; fix_uv_mesh a new DUYỆT 1)."""
    if verdict == "ESCALATE":
        return "ask_human", "reviewer ESCALATE"
    if verdict == "PASS":
        return ("approve", None) if auto else ("await_approval", None)
    if top_kind == "need_evidence":
        return ("ask_human", "xin bằng chứng lần 2") if evidence_used else ("need_evidence", None)
    if top_kind == "meshy_regen":
        return "ask_human", "meshy_regen"
    if top_kind in findings.REOPEN:
        return ("ask_human", f"{top_kind} lần 2") if reopened else ("reopen", None)
    if fix_round >= max_rounds:
        return "ask_human", f"hết {max_rounds} vòng sửa"
    if fix_round >= 2 and not progressed:
        return "ask_human", f"không tiến bộ ở vòng {fix_round}"
    return "fix", None


def reopened_of(st: dict) -> dict:
    """Reopens per TOP_FIX kind in this feedback round. GĐ 2 kept one int, which only regen_front raised."""
    r = st.get("reopened") or {}
    return r if isinstance(r, dict) else {"regen_front": r}


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
        rep = {"running": ("report-worker.md", "report-script.md"), "reviewing": ("report-review.md",)}.get(s, ())
        if s == "evidence_running" and st.get("evidence"):
            rep = (f"review/evidence-{st['evidence']['k']}/report-worker.md",)
        if d and any((d / r).exists() for r in rep):
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
    return unwrap(rep.read_text(encoding="utf-8"))


def set_aside(rep):
    """A new dispatch waits for a new report: the old one becomes `<name>-<k>.md`."""
    if rep.exists():
        rep.rename(rep.with_name(f"{rep.stem}-{1 + len(list(rep.parent.glob(f'{rep.stem}-*.md')))}.md"))


def log_wait(st: dict, sid: str, n: int | None, note: str, key: str | None = None, verdict: str | None = None):
    """`P compare` (§16, D25.J) counts waits per reason and the user's answer to each offer, so silence stays visible."""
    why = "duyệt" if note.startswith("duyệt ") else note.split(";")[0].split(" (")[0].strip()
    st.setdefault("offer_log", []).append({"key": key, "step": sid, "v": n, "why": why, "verdict": verdict, "at": now()})


def offer(st: dict, sid: str, n: int, verdict: str | None = None, **kw):
    """D22.8 per offer: an offered version takes a new decision, also when it was decided in an earlier round.
    `offer_key` names this offer, so a board click answers the offer it saw and no later one. It starts with the asset
    id: pages that list several assets key their decisions by it alone."""
    st.setdefault("decisions", {}).pop(f"{sid} v{n}", None)
    st["offers"] = st.get("offers", 0) + 1
    st |= {"offer": n, "offer_key": f"{st['id']}-{sid}-v{n}-{st['offers']}", **kw}
    log_wait(st, sid, n, kw.get("note", ""), st["offer_key"], verdict)


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


def script_findings(st, sid: str, n: int, rep):
    """§6.4: the fail points a script step writes as findings in its report go to findings.json, for the board."""
    c = parse_contract(read_report(rep), {"FINDINGS", "EVIDENCE_OPENED"})
    errs = []
    fs = parse_findings(c.get("FINDINGS", []), [x.strip() for x in c.get("EVIDENCE_OPENED", "").split(",") if x.strip()],
                        errs)
    if errs:
        die(f"{rel(rep)} sai contract: {'; '.join(errs)}")
    doc = {"version": n, "base": None, "top_fix": None, "pick": None, "next_id": len(fs) + 1,
           "findings": {i: {"priority": f["priority"], "kind": f["kind"], "status": "open", "first_v": n, "last_v": n,
                            **{k: v for k, v in f.items() if k not in ("priority", "kind")}} for i, f in fs.items()}}
    findings.save(st["id"], sid, doc)


def on_worker(cfg, st, step, d, n, a) -> tuple[str, str]:
    script = not step.get("agent")
    rep = d / ("report-script.md" if script else "report-worker.md")
    c = worker_report(st, rep, a.agent_id, step["id"], n)
    st["last_rubric"] = c.get("RUBRIC", "")
    if script:
        script_findings(st, step["id"], n, rep)
    missing = [o for o in outputs_of(step, st) if not (d / o).exists()]
    if why := stuck(c):
        move(st, "stuck")
        st["note"] = why
    elif c.get("UNFIXABLE", "").lower() == "yes":
        q = texture.ask_regen(st, n, False, f"UNFIXABLE: {c.get('ISSUES', '')}")
        move(st, "ask_human" if q else "stuck")
        if q:
            offer(st, step["id"], n, note=q, label=NOT_PASSED)
        else:
            st["note"] = f"UNFIXABLE ở chế độ VẼ MỚI: {c.get('ISSUES', '')}"
    elif missing:
        move(st, "stuck")
        st["note"] = "thiếu output bắt buộc: " + ", ".join(missing)
    elif step["gate"] == "checks_human":
        move(st, "checks_done")
        offer(st, step["id"], n, note=f"duyệt {step['id']} v{n}")
    else:
        move(st, "worker_done")
        st["note"] = ""
    return f"{'script' if script else 'worker'} {c['STATUS']}", ""


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


def take_variant(d, pick: str, outputs: list[str]) -> str | None:
    src = d / "variants" / pick
    if not src.is_dir():
        die(f"PICK {pick}: không có {rel(src)}/")
    if missing := [o[6:] for o in outputs if o.startswith("final/") and not (src / o[6:]).exists()]:
        return f"PICK {pick}: {rel(src)}/ thiếu output bắt buộc: " + ", ".join(missing)
    a = d / "variants" / "a"
    if a.exists():
        shutil.rmtree(d / "final")
    else:
        shutil.move(str(d / "final"), str(a))
    shutil.copytree(src, d / "final")
    return None


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
    if rv["pick"] and rv["pick"] != "a" and (why := take_variant(d, rv["pick"], outputs_of(step, st))):
        move(st, "stuck")
        st["note"] = why
        return f"review {rv['verdict']} PICK {rv['pick']}", why
    findings.save(aid, sid, doc)
    rvs = st.setdefault("round_versions", [])
    if n not in rvs:
        rvs.append(n)
    base = findings.load(aid, sid, st.get("fix_base"))
    kind = (rv["top_fix"] or {}).get("kind")
    event, reason = review_event(rv["verdict"], kind, who != "human", st.get("fix_round", 0), r["max_fix_rounds"],
                                 bool(base) and findings.progress(base, doc), st.get("evidence_used", 0),
                                 reopened_of(st).get(kind, 0))
    st["evidence"] = None
    st["last_rubric"] = "; ".join(f"{k}={x}" for k, x in rv["rubric"].items())
    best = findings.best_version([findings.load(aid, sid, v) for v in rvs])
    if event == "reopen":
        move(st, event)
        tid, ids = findings.REOPEN[kind], rv["top_fix"]["ids"]
        ti, target = step_of(cfg, tid)
        m = st["approved"].get(tid) or die(f"{aid}: {kind} cần bản {tid} đã duyệt")
        new = ", ".join(findings.carry(aid, {i: doc["findings"][i] for i in ids}, f"{sid} v{n}", target, m))
        reopen(cfg, st, ti, target, m, f"{kind}: sửa {tid} v{m} theo {new} ({sid} v{n} {', '.join(ids)})")
        r = reopened_of(st)
        st["reopened"] = r | {kind: r.get(kind, 0) + 1}
        reason = f"{kind} → {tid} v{m} {new}"
    elif event == "approve":
        approve(cfg, st, step, n, "reviewer" if who == "reviewer" else policy.BY[who])
    elif event == "await_approval":
        move(st, event)
        offer(st, sid, n, rv["verdict"], note=f"duyệt {sid} v{n}", label="")
    elif event == "ask_human":
        move(st, event)
        q = texture.ask_regen(st, n, True, f"meshy_regen {', '.join(rv['top_fix']['ids'])}") if kind == "meshy_regen" else None
        ids = ", ".join(findings.open_of(findings.load(aid, sid, best)))
        offer(st, sid, n if q else best, rv["verdict"], note=q or reason + (f"; còn mở: {ids}" if ids else ""),
              label=NOT_PASSED)
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
    if (tokens := getattr(a, "tokens", None)) is not None and st.get("dispatches"):
        st["dispatches"][-1]["tokens"] = tokens
    save_st(st)
    ledger(f"{a.id} · {step['id']} v{n} · {event} · {st.get('last_rubric', '')}" + (f" · {reason}" if reason else "")
           + (f" · tokens {tokens}" if tokens is not None else ""))
    build_outputs(cfg)
    print(f"{a.id}: {event} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")


def approve(cfg: dict, st: dict, step: dict, n: int, by: str):
    sid = step["id"]
    st["approved"][sid] = n
    st.setdefault("approved_at", {})[sid] = now()
    st.setdefault("approved_hash", {})[sid] = hashes.tree_hash(vdir(st["id"], sid, n) / "final")
    if step["lock"]:
        p = vdir(st["id"], sid, n) / step["lock"].format(id=st["id"])
        p.is_file() or die(f"{rel(p)}: không có file để khóa khi duyệt")
        st.setdefault("locked", {})[sid] = hashlib.sha256(p.read_bytes()).hexdigest()
    st.setdefault("rejected", {})[sid] = [v for v in range(1, st["versions"][sid] + 1) if v != n]
    st.setdefault("prior", {}).pop(sid, None)
    current(st["id"], sid)
    if sid == "assemble":
        from .estimate import log_asset
        out = DELIVER / st["id"]
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(vdir(st["id"], sid, n) / "final", out)
        readme = out / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        body = text.split("\n", 1)[1] if text.startswith(STATUS_LINE) else text
        readme.write_text(f"{STATUS_LINE} đã duyệt DUYỆT 2 bởi {by} · {now()}\n" + body, encoding="utf-8")
        log_asset(st)
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
        for k in ("approved", "approved_hash", "rejected", "locked"):
            st.setdefault(k, {}).pop(s["id"], None)
    hashes.refresh_stale(cfg, st)


def redo(cfg: dict, st: dict, i: int, step: dict, n: int | None, text: str | None, marks: list[dict] = ()) -> list[str]:
    move(st, "redo")
    ids = findings.add_human(st["id"], step, n, text, marks) if n else []
    reopen(cfg, st, i, step, n, "làm lại theo feedback người dùng")
    st["reopened"] = {}
    readme = DELIVER / st["id"] / "README.md"
    if readme.exists() and not (t := readme.read_text(encoding="utf-8")).startswith(REDOING):
        readme.write_text(REDOING + t, encoding="utf-8")
    return ids


def retry(a):
    st = load_st(a.id)
    if st["state"] == "done_enabled":
        move(st, "resume", load_cfg())
    elif st["state"] == "blocked" and st.get("blocked_from"):
        move(st, f"retry_{st.pop('blocked_from')}")
        st["note"] = ""
    elif st["state"] == "blocked" and step_of(load_cfg(), st["stage"])[1]["script"]:
        move(st, "retry_todo")
        st["note"] = ""
    else:
        move(st, "retry_evidence" if st.get("evidence") else "retry" if st["versions"].get(st["stage"]) else "retry_todo")
        st["note"] = ""
    if st["state"] == "running":
        set_aside(vdir(a.id, st["stage"], st["versions"][st["stage"]]) / "report-worker.md")
    save_st(st)
    ledger(f"{a.id} · retry")
    print(f"{a.id}: → {st['state']}. Tiếp: {next_action(st)}")


def append_feedback(aid: str, step: str, n: int | None, action: str, text: str):
    tag = f"{step} v{n}" if n else step
    head = f"- {now()} · {tag} · {action} · "
    with open(ASSETS / aid / "feedback.md", "a", encoding="utf-8") as f:
        f.write(head + text.strip() + "\n")
    if action == "redo":
        current(aid, step, head + " ".join(text.split()))


def current(aid: str, step: str, line: str | None = None):
    """Section "Hiện hành" of feedback.md: a redo adds its log line; approving the step drops that step's redo lines.
    Lines the Producer merged by hand stay."""
    p = ASSETS / aid / "feedback.md"
    if not p.is_file():
        return
    head, sep, log = p.read_text(encoding="utf-8").partition("\n## Log")
    rows = head.rstrip("\n").split("\n")
    if line is None:
        rows = [r for r in rows if not re.match(rf"- [^·]+ · {re.escape(step)}(?: v\d+)? · redo · ", r)]
    else:
        rows.append(line)
    p.write_text("\n".join(rows) + "\n" + sep + log, encoding="utf-8")


def shown(st: dict, step: str) -> int | None:
    if step == st["stage"] and st.get("offer"):
        return st["offer"]
    return st["approved"].get(step) or st["versions"].get(step)


def human_action(*args, **kw) -> str:
    return act(*args, **kw)[1]


def act(aid: str, action: str, text: str, step_id: str | None = None, regions=None,
        offer: str | None = None) -> tuple[bool, str]:
    """One decision per offer (D22.8), from the CLI, the local board or a remote row. `offer` is the offer the page
    showed; `regions` are marks on images of the current card (review-board.md §4). Returns (applied, message):
    applied is False for a skipped call, so a page keeps the user's marks. Nothing reaches the disk before the
    decision can no longer die."""
    from .board import build_outputs, view_images
    cfg = load_cfg()
    st = load_st(aid)
    if action not in ACTIONS:
        die("action phải là " + " | ".join(ACTIONS))
    target = step_id or st["stage"]
    i, step = step_of(cfg, target)
    if action == "redo" and i > step_of(cfg, st["stage"])[0]:
        die(f"{aid}: không làm lại {target} được: asset đang ở bước {st['stage']}")
    n = shown(st, target)
    key = f"{target} v{n}"
    done = st.setdefault("decisions", {})
    send_back = action == "redo" and n is not None and st["approved"].get(target) == n
    answer = action in ("approve", "paint") and st.get("ask") and st["state"] == "waiting_human" and target == st["stage"]
    old = done.get(key) if action != "note" else None
    if old and (offer and old.get("offer") == offer or not (send_back or answer)):
        return False, f"{aid}: bỏ qua {action} {key}: đã có quyết định lúc {old['at']}"
    if offer is not None and offer != st.get("offer_key") and (action != "note" or regions is not None):
        return False, (f"{aid}: bỏ qua {action}: lần đưa duyệt {offer} đã qua "
                       f"(hiện tại: {st.get('offer_key') or 'không chờ duyệt'})")
    if action == "paint" and not answer:
        die(f"{aid}: không có câu hỏi Meshy đang chờ")
    if action == "redo" and step["gate"] == "checks_human" and not step.get("agent"):
        die(f"{aid}: {target} không có vòng sửa: chọn bước sửa, `--step texture` (vẽ lại) hoặc `--step model` (mesh, UV)")
    if action == "redo" and (st.get("ask") or {}).get("kind") == "mesh_changed" and target == "texture":
        die(f"{aid}: đang chờ chọn Meshy hay VẼ MỚI cho mesh mới: duyệt = gọi Meshy, `meshy {aid} paint` = VẼ MỚI")
    marks, files, tag, folder = None, None, None, None
    if regions is not None:
        card = shown(st, st["stage"])
        files = dict((name, p) for p, name in view_images(cfg, st, st["stage"], card))
        marks = annotate.check(regions, files, f"{aid} {st['stage']} v{card}")
        n or die(f"{aid}: {target} chưa có version để gắn vùng khoanh")
        tag = f"{st['stage']}-v{card}"
    raw = text.strip()
    text = raw or "(không ghi chú)"
    waiting = st["state"] == "waiting_human" and target == st["stage"]

    def decide():
        done[key] = {"action": action, "at": now(), "offer": st.get("offer_key")}
        if w := next((w for w in st.get("offer_log", []) if w["key"] == st.get("offer_key") and w["step"] == target
                      and "decision" not in w), None):
            w |= {"decision": action, "decided": now()}

    def keep():
        nonlocal folder
        folder = annotate.save(aid, tag, marks, files) if marks else None
        append_feedback(aid, target, n, action, text + (f" · khoanh: {rel(folder)}" if folder else ""))

    def settle() -> list[str]:
        keep()
        return findings.add_human(aid, step, n, None, marks) if marks and waiting else []

    ids, msg = [], "đã ghi feedback"
    if answer:
        decide()
        msg = texture.resolve(st, "call" if action == "approve" else "paint", policy.BY["human"])
        ids = settle()
    elif action == "approve" and waiting:
        decide()
        approve(cfg, st, step, n, policy.BY["human"])
        ids = settle()
        if not step.get("reviewer"):
            findings.close_human(aid, target, n)
        msg = f"đã duyệt {key} → {st['stage']}/{st['state']}"
    elif action == "redo" and st["state"] in REDO_FROM:
        decide()
        st.pop("ask", None)
        keep()
        got = redo(cfg, st, i, step, n, raw or (None if marks else text), marks or ())
        ids = got[len(got) - len(marks):] if marks else []
        msg = f"làm lại {target}" + (f" từ v{n}" if n else "")
    else:
        if action == "approve":
            msg = f"đã ghi feedback; {aid} không chờ duyệt {target} (state={st['state']})"
        elif action == "redo":
            msg = f"đã ghi feedback; {aid} đang {st['state']}, sẽ áp dụng ở vòng sau"
        ids = settle()
    if marks:
        annotate.record(folder, marks, ids)
        msg += (f"; khoanh {len(marks)} vùng → {', '.join(ids)}" if ids else
                f"; khoanh {len(marks)} vùng lưu ở {rel(folder)}, chưa thành finding (state={st['state']})")
    save_st(st)
    ledger(f"{aid} · người dùng {action} {target} · {text[:80]}")
    build_outputs(cfg)
    return True, f"{aid}: {msg}. Tiếp: {next_action(st)}"
