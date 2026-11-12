"""Ingest state machine (docs/producer.md §3, §4, §7, §8): rounds, early stop, need_evidence, redo, gates, approve."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path, PurePosixPath

from . import annotate, asset_card, findings, hashes, policy, purge, texture
from .contract import parse_contract, parse_findings, parse_review, parse_worker, unwrap
from .state import (ASSETS, DELIVER, FINISHED, HARD_GATES, ROOT, SKILL_DIR, ProducerError, agent_name, die, ledger, load_cfg,
                    load_st, now, outputs_of, rel, save_st, stamp, step_of, vdir)

NOT_PASSED = "chưa đạt"
UNREVIEWED = "chưa chấm"
NO_NUMBER = "không có số"
ACTIONS = ("approve", "redo", "note", "paint")
STATUS_LINE = "Trạng thái:"
REDOING = "**đang làm lại**\n\n"
REDO_FROM = ("todo", "fix", "review", "evidence", "waiting_human", "blocked", "done", "done_enabled")
PENDING_FROM = ("running", "reviewing", "evidence_running")
NEXT = "next"
MOVES = {
    ("todo", "dispatch"): "running", ("fix", "dispatch"): "running", ("running", "dispatch"): "running",
    ("review", "dispatch"): "reviewing", ("reviewing", "dispatch"): "reviewing",
    ("evidence", "dispatch"): "evidence_running", ("evidence_running", "dispatch"): "evidence_running",
    ("running", "worker_done"): "review", ("running", "checks_done"): "waiting_human", ("running", "stuck"): "blocked",
    ("running", "checks_failed"): "fix",
    ("evidence_running", "worker_done"): "review", ("evidence_running", "stuck"): "blocked",
    ("evidence_running", "ask_human"): "waiting_human", ("waiting_human", "restall_running"): "running",
    ("waiting_human", "restall_reviewing"): "review", ("waiting_human", "restall_evidence_running"): "evidence",
    ("reviewing", "fix"): "fix", ("reviewing", "need_evidence"): "evidence", ("reviewing", "reopen"): "fix",
    ("reviewing", "served"): "review",
    ("reviewing", "stuck"): "blocked",
    ("reviewing", "await_approval"): "waiting_human", ("reviewing", "ask_human"): "waiting_human",
    ("reviewing", "approve"): NEXT, ("waiting_human", "approve"): NEXT, ("done_enabled", "resume"): NEXT,
    ("blocked", "retry"): "running", ("blocked", "retry_evidence"): "evidence", ("blocked", "retry_todo"): "todo",
    ("blocked", "retry_fix"): "fix", ("todo", "stuck"): "blocked", ("fix", "stuck"): "blocked",
    ("todo", "ask_human"): "waiting_human", ("fix", "ask_human"): "waiting_human", ("running", "ask_human"): "waiting_human",
    ("waiting_human", "answer_fix"): "fix", ("waiting_human", "answer_todo"): "todo",
    ("fix", "full_again"): "review", ("waiting_human", "full_again"): "review", ("evidence", "full_again"): "review",
    ("reviewing", "full_again"): "review",
    **{(s, "redo"): "fix" for s in REDO_FROM},
}


def fresh() -> dict:
    return {"fix_round": 0, "fix_base": None, "round_versions": [], "evidence": None, "evidence_used": 0, "evidence_served": 0,
            "offer": None, "offer_key": None, "label": "", "note": "", "rereview": None, "direct": None, "direct_rounds": 0,
            "direct_names": None, "retry_why": None}


def move(st: dict, event: str, cfg: dict | None = None):
    nxt = MOVES.get((st["state"], event)) or die(f"{st['id']}: không {event} được ở state={st['state']}")
    if st["state"] == "waiting_human":
        st.pop("stalled_from", None)
    if nxt != NEXT:
        st["state"] = nxt
        return
    i, _ = step_of(cfg, st["stage"])
    st |= fresh() | {"worker_agent_id": None}
    after = next((s for s in cfg["steps"][i + 1:] if not asset_card.skipped(s, st)), None)
    if after is None:
        st["state"] = "done"
    elif not after["enabled"]:
        st["state"], st["note"] = "done_enabled", f"bước {after['id']} chưa bật"
    else:
        st["stage"], st["state"] = after["id"], "todo"


def review_event(verdict: str, top_kind: str | None, auto: bool, fix_round: int, max_rounds: int, progressed: bool,
                 evidence_used: int, reopened: int = 0) -> tuple[str, str | None]:
    """§7: what a valid review leads to. fix_round is the fix round that built the reviewed version (0 = first build).
    reopened: times this TOP_FIX kind reopened an earlier step in this feedback round (fix_uv_mesh costs a new DUYỆT 1)."""
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
    """Reopens per TOP_FIX kind in this feedback round. GĐ 2 kept one int, for a kind that no step has now: it counts
    for nothing."""
    r = st.get("reopened") or {}
    return r if isinstance(r, dict) else {}


def review_base(st: dict, n: int) -> int | None:
    """An evidence round and a review of the same version again (D30.1) judge version n against its own findings."""
    return n if st.get("evidence") or st.get("rereview") == n else st.get("fix_base")


def current_v(st: dict, sid: str) -> int | None:
    """The version a review judges: the one an evidence round stands on, else `rereview` when the same version is judged
    again without a worker, else the newest."""
    if (ev := st.get("evidence")) and sid == st["stage"]:
        return ev["version"]
    rr = st.get("rereview")
    return rr if rr and sid == st["stage"] and st["state"] in ("review", "reviewing") else st["versions"].get(sid)


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
        n = current_v(st, st["stage"]) if st.get("versions") else None
        d = vdir(aid, st["stage"], n) if n else None
        rep = {"running": ("worker-out.md", "report-script.md"), "reviewing": ("review-out.md",)}.get(s, ())
        if s == "evidence_running" and st.get("evidence"):
            rep = (f"review/evidence-{st['evidence']['k']}/worker-out.md",)
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


def set_rejected(rep):
    """A report the contract refuses becomes `<name>.rejected-<k>.md`: its path is free for the rewrite, and `P wait`
    and the stall check no longer read it as a finished report."""
    k = 1
    while (to := rep.with_name(f"{rep.stem}.rejected-{k}.md")).exists():
        k += 1
    rep.rename(to)


def reject(rep, why: str):
    set_rejected(rep)
    die(f"{rel(rep)} sai contract: {why}")


def valid(rep, parsed: tuple):
    out, errs = parsed
    if errs:
        reject(rep, "; ".join(errs))
    return out


def worker_report(st: dict, rep, agent_id, sid: str, n: int) -> dict:
    c = valid(rep, parse_worker(read_report(rep)))
    inp = (st.get("inputs") or {}).get(sid, {}).get(f"v{n}") or {}
    if c["PROFILE_HASH"] != inp.get("profile"):
        set_rejected(rep)
        die(f"{rel(rep)}: PROFILE_HASH {c['PROFILE_HASH']} khác brief ({inp.get('profile')})")
    hashes.check_inputs(st, inp)
    if agent_id:
        st["worker_agent_id"] = agent_id
    return c


def stuck(c: dict) -> str | None:
    return f"{c['STATUS']}: {c.get('ISSUES', '')}" if c["STATUS"] in ("NEEDS_CONTEXT", "BLOCKED") else None


def script_findings(st, sid: str, n: int, rep):
    """§6.4: the fail points a script step writes as findings in its report go to findings.json, for the board."""
    errs = []
    c = parse_contract(read_report(rep), {"FINDINGS", "EVIDENCE_OPENED"}, errs)
    fs = parse_findings(c.get("FINDINGS", []), [x.strip() for x in c.get("EVIDENCE_OPENED", "").split(",") if x.strip()],
                        errs)
    if errs:
        reject(rep, "; ".join(errs))
    doc = {"version": n, "base": None, "top_fix": None, "pick": None, "next_id": len(fs) + 1,
           "findings": {i: {"priority": f["priority"], "kind": f["kind"], "status": "open", "first_v": n, "last_v": n,
                            **{k: v for k, v in f.items() if k not in ("priority", "kind")}} for i, f in fs.items()}}
    findings.save(st["id"], sid, doc)


def readme_exceptions(d) -> str:
    """Text under the NGOẠI LỆ heading of final/README.md, up to the next heading."""
    p = d / "final" / "README.md"
    m = re.search(r"^#+[^\n]*NGOẠI LỆ[^\n]*\n(.*?)(?=^#|\Z)", p.read_text(encoding="utf-8"), re.M | re.S | re.I) \
        if p.is_file() else None
    return m.group(1) if m else ""


def failing_checks(path: str) -> list[str]:
    try:
        r = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c.get("check", "") for c in (r.get("checks") or []) if isinstance(c, dict) and c.get("status") in ("fail", "error")]


def acceptable_hit(step: dict, hit: str) -> bool:
    """A name of `acceptable` covers a file of that name outside gates/, because the gate JSON of a part is named after
    the part and `base` is a part. `<glob>#<check>,...` covers a file whose path from final/review/ matches the glob and
    whose every failing check is listed."""
    p = PurePosixPath(hit)
    for entry in step["acceptable"]:
        glob, _, only = entry.partition("#")
        if only:
            failing = failing_checks(hit)
            if failing and set(failing) <= set(only.split(",")) and fnmatch.fnmatchcase("/".join(p.parts[-2:]), glob):
                return True
        elif p.name == entry and p.parent.name != "gates":
            return True
    return False


def accept_fails(step: dict, d, bad: list[str], claims: list[tuple[str, str]]) -> tuple[dict, list[str]]:
    """D31.3: which failed JSON the worker may leave failed. Returns ({failed path: (name, why)}, refusals)."""
    from .briefs import unreadable
    ok, refused, notes = {}, [], readme_exceptions(d)
    for f, why in claims:
        hit = next((b for b in bad if b == f or b.endswith("/" + f.removeprefix("./"))), None)
        name = PurePosixPath(hit or f).name
        if hit is None:
            refused.append(f"{f}: không phải JSON fail trong final/review/{{gates,checks}}/, join.json, unwrap.json")
        elif name in HARD_GATES:
            refused.append(f"{name}: gate cứng, không bao giờ được ACCEPTED_FAIL")
        elif unreadable(Path(hit)):
            refused.append(f"{name}: JSON không đọc được, không có kết quả để chấp nhận")
        elif not acceptable_hit(step, hit):
            refused.append(f"{name}: không có trong acceptable của bước {step['id']}")
        elif not re.search(r"\d", why):
            refused.append(f"{name}: lý do phải có số")
        elif name not in notes:
            refused.append(f"{name}: chưa ghi vào mục NGOẠI LỆ của final/README.md")
        else:
            ok[hit] = (name, why)
    return ok, refused


RECHECK = {"blockout": "gate_all.py"}
RECHECK_TIMEOUT_S = 600


def recheck(st: dict, step: dict, d) -> tuple[list[str], str | None]:
    """D37.6: the pure-Python checks of the step, run by ingest through run_tool.py instead of trusted from the worker
    (Blender never starts). Returns (paths of a run that failed without a result JSON, why nothing ran or None)."""
    tool = RECHECK.get(step["id"])
    if not tool:
        return [], None
    agent = agent_name(step["agent"])
    tools = SKILL_DIR / "agents" / agent / "tools"
    if not (tools / ".deps" / "venv" / "bin" / "python").is_file():
        return [], f"ingest không kiểm lại {tool} được: thiếu venv của tool ({rel(tools)}/.deps), chạy setup_deps.sh"
    card = st.get("concept_dir")
    check_inputs = ["--approved", card, "--profile", str(ROOT / "PROJECT-PROFILE.yaml")] if card else None
    cmd = [sys.executable, str(SKILL_DIR / "scripts" / "run_tool.py"), "--agent", agent, "--version-dir", rel(d), tool,
           "--work", rel(d / "final"), *(["--check-args", "check_inputs=" + shlex.join(check_inputs)] if card else
                                       ["--skip", "check_inputs"])]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=RECHECK_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return [], f"ingest không kiểm lại {tool} được: quá {RECHECK_TIMEOUT_S} giây"
    line = (p.stdout.strip().splitlines() or [""])[-1].split()
    if p.returncode == 2:
        return [], f"ingest không kiểm lại {tool} được: {(p.stderr.strip().splitlines() or ['bị từ chối'])[-1]}"
    return (line[2:] if p.returncode and line[1:2] == ["error"] else []), None


RENDER_FRESH = "render_fresh.json"


def render_fresh(d: Path):
    """T2: the albedo changed after its renders were made, so a reviewer would grade old pictures. renders.json names the
    albedo and its sha256; checks/render_fresh.json fails when the file now differs. No hash in renders.json (older
    versions): no file."""
    out = d / "final" / "review" / "checks" / RENDER_FRESH
    out.unlink(missing_ok=True)
    try:
        r = json.loads((d / "final" / "review" / "renders.json").read_text(encoding="utf-8"))
        want, name = r["albedo_sha256"], PurePosixPath(r["albedo"]).name
        got = hashlib.sha256((d / "final" / name).read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError):
        return
    ok = got == want
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"overall": "pass" if ok else "fail", "checks": [{
        "check": "render.fresh", "status": "pass" if ok else "fail",
        "note": None if ok else f"render lại: {name} đã đổi sau lần render (chạy lại render_texture.py)"}]},
        ensure_ascii=False, indent=1), encoding="utf-8")


def checks_failed(cfg, st, step, d, n, c) -> bool:
    """D31.3, D39.5: a failed gate or check JSON the worker did not validly accept goes straight back to the worker, no
    reviewer. A direct round does not count toward max_fix_rounds; [review] max_direct_rounds caps them, and the same
    failing names as the round before ask the human at once."""
    from .briefs import failed_checks
    if step.get("counts_gate") and st.get("concept_dir") and (card := Path(st["concept_dir"]) / "asset-card.yaml").is_file():
        from check_counts import write
        write(d / "final", card)
    if step["gate"] == "checks_human":
        return False
    if step["id"] == texture.STEP:
        render_fresh(d)
    extra, skipped = recheck(st, step, d)
    if skipped:
        ledger(f"{st['id']} · {step['id']} v{n} · {skipped}")
        print(f"{st['id']}: {skipped}", file=sys.stderr)
    done = {"direct_rounds": 0, "direct_names": None}
    if not (bad := [*failed_checks(d), *extra]):
        st |= done
        return False
    sid, r = step["id"], cfg["review"]
    ok, refused = accept_fails(step, d, bad, c["ACCEPTED_FAIL"])
    for name, why in ok.values():
        k = st.setdefault("accepted_fail", {}).setdefault(sid, {})
        k[name] = k.get(name, 0) + 1
        ledger(f"{st['id']} · {sid} v{n} · ACCEPTED_FAIL {name} · lần {k[name]} · {why}")
    for x in refused:
        ledger(f"{st['id']} · {sid} v{n} · ACCEPTED_FAIL từ chối · {x}")
    st["accepted"] = {"v": n, "items": [f"{name} — {why}" for name, why in ok.values()]} if ok else None
    if not (left := [b for b in bad if b not in ok]):
        st |= done
        return False
    failing = sorted({PurePosixPath(b).name for b in left})
    names = ", ".join(PurePosixPath(b).name for b in left) + (f" (từ chối: {'; '.join(refused)})" if refused else "")
    rounds, cap = st.get("direct_rounds", 0), r["max_direct_rounds"]
    stop = (f"check fail y hệt vòng trả thẳng trước, ở v{n}: {names}" if failing == st.get("direct_names") else
            f"hết {cap} vòng trả thẳng; check fail ở v{n}: {names}" if rounds >= cap else None)
    if stop:
        move(st, "ask_human")
        best = findings.best_version([findings.load(st["id"], sid, v) for v in st.get("round_versions", [])]) or n
        offer(st, sid, best, note=stop, label=NOT_PASSED)
    else:
        move(st, "checks_failed")
        st |= {"direct": n, "direct_rounds": rounds + 1, "direct_names": failing,
               "note": f"vòng trả thẳng {rounds + 1}/{cap}: check fail {names}"}
    return True


def on_worker(cfg, st, step, d, n, a) -> tuple[str, str]:
    script = not step.get("agent")
    st |= {"direct": None, "retry_why": None}
    rep = d / ("report-script.md" if script else "worker-out.md")
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
    elif checks_failed(cfg, st, step, d, n, c):
        return f"worker {c['STATUS']} (check fail)", st["note"]
    else:
        move(st, "worker_done")
        st["note"] = ""
    return f"{'script' if script else 'worker'} {c['STATUS']}", ""


def on_evidence(cfg, st, step, d, n, a) -> tuple[str, str]:
    tag = f"evidence-{st['evidence']['k']}"
    c = worker_report(st, d / "review" / tag / "worker-out.md", a.agent_id, step["id"], n)
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
    rep = d / "review-out.md"
    rv = valid(rep, parse_review(read_report(rep)))
    from .briefs import prefilled
    pre = {k: v for k, (v, _) in prefilled(st, step, n).items()}
    if changed := [f"{k}={rv['rubric'][k]} (script điền {v})" for k, v in pre.items()
                   if rv["rubric"].get(k, v) not in (v, "not_checked")]:
        reject(rep, f"RUBRIC đổi key script đã điền từ JSON: {', '.join(changed)}")
    rv["rubric"] = {**rv["rubric"], **pre}
    scope = st.get("review_scope") or "full"
    if scope == "full" and (nc := [k for k, x in rv["rubric"].items() if x == "not_checked"]):
        reject(rep, f"RUBRIC {', '.join(nc)}=not_checked chỉ dùng khi REVIEW_SCOPE: fix")
    wr = d / "worker-out.md"
    claimed = parse_worker(read_report(wr))[0]["RESOLVED_NOTES"] if wr.exists() else []
    if extra := [x for x in rv["confirmed"] if x not in claimed]:
        reject(rep, f"RESOLVED_CONFIRMED {', '.join(extra)} không có trong RESOLVED_NOTES của worker")
    warns = []
    doc = valid(rep, findings.apply(findings.load(aid, sid, review_base(st, n)), rv,
                                    step | {"regions": asset_card.regions(step, st)}, n, warns))
    rv = rv | {"top_fix": doc["top_fix"]}
    for w in warns:
        ledger(f"{aid} · {sid} v{n} · cảnh báo report reviewer · {w}")
    st["rereview"] = None
    if pend := (st.get("waive_pending") or {}).pop(sid, None):
        findings.waive(aid, sid, st["versions"][sid], pend, doc)
        tf = doc["top_fix"]
        doc["top_fix"] = tf and ({**tf, "ids": ids} if (ids := [i for i in tf["ids"] if i not in pend]) else None)
        if rv["verdict"] == "FIX" and not findings.blocking(doc):
            rv = rv | {"verdict": "PASS", "top_fix": None, "waived_pass": True}
            doc["top_fix"] = None
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
                                 not base or findings.progress(base, doc), st.get("evidence_used", 0),
                                 reopened_of(st).get(kind, 0))
    if event == "approve" and st.get("pending_redo"):
        event = "await_approval"
    st["evidence"] = None
    st["last_rubric"] = "; ".join(f"{k}={x}" for k, x in rv["rubric"].items())
    asks = evidence_on_disk(d, doc, rv["top_fix"]["ids"]) if kind == "need_evidence" and event in (
        "need_evidence", "ask_human") and st.get("evidence_served", 0) < r.get("served_evidence", 2) else None
    if asks:
        event, reason = "served", None
    best = findings.best_version([findings.load(aid, sid, v) for v in rvs])
    if event in ("approve", "await_approval") and scope == "fix" and (
            rv.get("waived_pass") or "not_checked" in rv["rubric"].values()):
        event, reason = "full_again", f"PASS ở vòng fix → reviewer chấm full lại v{n}, không gọi worker"
    if event == "full_again":
        move(st, event)
        st |= {"rereview": n, "note": f"chấm full lại v{n}"}
    elif event == "reopen":
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
    elif event == "served":
        move(st, event)
        k = 1 + sum(1 for _ in (d / "review").glob("evidence-*"))
        names = serve(d, asks, k)
        st["evidence_served"] = st.get("evidence_served", 0) + 1
        st |= {"evidence": {"version": n, "k": k, "hash": hashes.tree_hash(d / "final"), "served": True,
                            "agent_id": getattr(a, "agent_id", None)},
               "note": f"ảnh trên đĩa cho {', '.join(rv['top_fix']['ids'])}: {', '.join(names)}"}
        reason = f"script lấy ảnh có sẵn, không giao worker: {', '.join(names)}"
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


EVIDENCE_ASK = re.compile(r"xin ảnh\s+([^\s,;|]+?)(?:\.png)?(?:\s+box\s+([\d.]+),([\d.]+),([\d.]+),([\d.]+))?(?=[\s,;|]|$)")


def evidence_on_disk(d, doc: dict, ids: list[str]) -> list[tuple[str, str, tuple | None]] | None:
    """D31.1, D38.5: what a need_evidence asks, when every id names a tile of vN/review/sheet.json (any page) in its
    viewing_condition (`xin ảnh <nhãn>[ box x0,y0,x1,y1]`, box in 0–1 of the image). The tile gives the image file; a
    crop tile gives its own 1:1 file. None when one id asks for an image not on disk or a box outside 0–1 (a pixel
    box): the worker round handles those."""
    sj = d / "review" / "sheet.json"
    tiles = {label: t["src"] if isinstance(t, dict) else t
             for label, t in (json.loads(sj.read_text(encoding="utf-8")) if sj.is_file() else {}).items()}
    out = []
    for i in ids:
        asks = EVIDENCE_ASK.findall(doc["findings"][i].get("viewing_condition", ""))
        if not asks or any(label not in tiles for label, *_ in asks):
            return None
        for label, *box in asks:
            b = tuple(float(x) for x in box) if box[0] else None
            if b and not (0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1):
                return None
            out.append((label, tiles[label], b))
    return out


def serve(d, asks, k: int) -> list[str]:
    """Copy each asked image, or its box at full resolution, to review/evidence-<k>/; returns the file names."""
    from PIL import Image
    ed = d / "review" / f"evidence-{k}"
    ed.mkdir(parents=True, exist_ok=True)
    names = []
    for j, (label, src, box) in enumerate(asks, 1):
        name = label.replace("/", "_") + (f"-crop{j}" if box else "") + ".png"
        with Image.open(d / src) as im:
            if box:
                x0, y0, x1, y1 = box
                im = im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height)))
            im.save(ed / name)
        names.append(name)
    return names


HANDLERS = {"running": on_worker, "evidence_running": on_evidence, "reviewing": on_review}


def open_dispatch(st: dict, sid: str, n: int, role: str) -> dict | None:
    """The dispatch an ingest closes: its step, version and role, not yet ingested. A script step has none."""
    return next((x for x in reversed(st.get("dispatches", [])) if (x["step"], x["v"], x["role"]) == (sid, n, role)
                 and "ingested" not in x and "ended" not in x), None)


def number(x, unit: str = "") -> str:
    return NO_NUMBER if x is None else f"{x}{unit}"


def ingest(a):
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(a.id)
    _, step = step_of(cfg, st["stage"])
    sid = step["id"]
    n = current_v(st, sid)
    h = HANDLERS.get(st["state"]) or die(f"{a.id}: state={st['state']}, không có báo cáo nào đang chờ")
    role = "reviewer" if st["state"] == "reviewing" else "script" if step["script"] else "worker"
    rec = open_dispatch(st, sid, n, role)
    event, reason = h(cfg, st, step, vdir(a.id, sid, n), n, a)
    if applied := apply_pending(cfg, st, sid, n):
        reason = "; ".join(x for x in (reason, applied) if x)
    tokens, ms, at = getattr(a, "tokens", None), getattr(a, "duration_ms", None), stamp()
    fallback = bool(getattr(a, "fallback", False))
    if rec is not None:
        if getattr(a, "agent_id", None):
            rec["agent_id"] = a.agent_id
        from . import session
        usage = session.dispatch_usage(rec, at)
        if usage and tokens is None:
            tokens = sum(usage[k] for k in session.SPLIT.values())
        if usage and ms is None:
            ms = usage["duration_ms"]
        rec |= {"ingested": at, "tokens": tokens, "duration_ms": ms, "usage": usage, "after": st["state"]} | (
            {"fallback": True} if fallback else {})
    save_st(st)
    if fallback:
        ledger(f"{a.id} · {sid} v{n} · report_fallback · {role}")
    ledger(f"{a.id} · {sid} v{n} · {event} · {st.get('last_rubric', '')}" + (f" · {reason}" if reason else "")
           + f" · {role} giao {rec['at'] if rec else NO_NUMBER} · ingest {at} · token {number(tokens)}"
           + f" · thời lượng {number(ms, ' ms')}")
    print(f"{a.id}: {event} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")
    dispatch_next(cfg, st)
    build_outputs(cfg)


INGEST_DISPATCH = ("review", "fix", "evidence", "todo")
CHANGE_DISPATCH = ("todo", "fix", "review", "evidence", "running")
WAIVE_DISPATCH = ("todo", "fix", "review", "evidence")  # running: the worker already has its brief


def dispatch_next(cfg: dict, st: dict, states: tuple = INGEST_DISPATCH):
    """D27.2, D30.5: the next dispatch goes out in the same turn as the state change: the dispatch line of `P brief`.
    An ingest ends in review, fix, evidence (a worker renders the asked image) or the todo of the next step (an auto
    approve). A worker waits while a resource of its step has no free slot, as in `P next`. A `retry` that already moved the asset
    to running goes out: held there, nothing would show it waits."""
    if st["state"] not in states or st["state"] in FINISHED:
        return
    from .briefs import run
    from .limits import DISPATCH, full, slots
    from .state import all_status
    _, step = step_of(cfg, st["stage"])
    if st["state"] in DISPATCH and full(step, slots(cfg, all_status())):
        return
    try:
        run(Namespace(id=st["id"]))
    except ProducerError as ex:
        print(f"{st['id']}: chưa giao được: {ex}")


WAIVE_BY = {"user": "người dùng", "producer": "Producer"}


def waive(a):
    """D30.1 `P waive <id> F<n> "lý do"`: in any state. The finding closes as `waived` now, or at the next ingest while a
    reviewer judges a brief that still lists it. Waiving the last blocking finding of the version a fix round, an
    offer or an evidence round stands on sends that version to a `full` review again, without a worker."""
    from .board import build_outputs
    cfg = load_cfg()
    st = load_st(a.id)
    sid = a.step or st["stage"]
    _, step = step_of(cfg, sid)
    if a.by == "producer" and policy.load().get("test_mode") is not True:
        die(f"{a.id}: --by producer chỉ chạy khi production/policy.yaml có test_mode: true; dự án thật do người dùng waive")
    why = " ".join(a.why.split()) or die("waive cần lý do")
    top = st["versions"].get(sid, 0)
    hit = [d["findings"][a.fid] for v in range(1, top + 1) if a.fid in findings.open_of(d := findings.load(a.id, sid, v))]
    hit or die(f"{a.id}: {sid} không có {a.fid} đang mở")
    rec = {"by": a.by, "why": why, "at": now()}
    here = sid == st["stage"]
    if here and st["state"] == "reviewing":
        st.setdefault("waive_pending", {}).setdefault(sid, {})[a.fid] = rec
        msg = "reviewer đang chấm, áp dụng ở lần ingest tới"
    else:
        findings.waive(a.id, sid, top, {a.fid: rec})
        msg = "đã đóng"
        target = {"fix": st.get("fix_base"), "waiting_human": st.get("offer"),
                  "evidence": (st.get("evidence") or {}).get("version")}.get(st["state"])
        doc = findings.load(a.id, sid, target) if here and target and step.get("reviewer") and not st.get("ask") else None
        if doc and hit[-1]["priority"] in findings.BLOCKING and not findings.blocking(doc):
            move(st, "full_again")
            st |= {"rereview": target, "evidence": None, "direct": None, "offer": None, "label": "",
                   "note": f"chấm lại v{target} sau waive {a.fid}"}
            msg += f"; v{target} hết lỗi chặn → reviewer chấm lại v{target}, không gọi worker"
    save_st(st)
    ledger(f"{a.id} · {sid} {a.fid} · waive bởi {WAIVE_BY[a.by]} · {why}")
    print(f"{a.id}: waive {sid} {a.fid} ({WAIVE_BY[a.by]}): {msg} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")
    dispatch_next(cfg, st, WAIVE_DISPATCH)
    build_outputs(cfg)


def approve(cfg: dict, st: dict, step: dict, n: int, by: str):
    sid = step["id"]
    st["approved"][sid] = n
    st.setdefault("approved_at", {})[sid] = now()
    from .report import record_producer
    record_producer(st, sid, cfg["steps"])
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


def marks_as_notes(aid: str, step: dict, n: int, ids: list[str]) -> list[str]:
    """C10: marks sent with an approve are notes for the later steps, not open `major` findings on a version nobody fixes.
    The kind is the first `note*` kind of the step; a step with none uses `note`, which every brief reads."""
    if ids:
        doc = findings.load(aid, step["id"], n)
        kind = next((k for k in step["top_fix"] if k in findings.NOTE), "note")
        for i in ids:
            doc["findings"][i] |= {"kind": kind, "priority": "minor", "consequence": "người dùng duyệt kèm vùng khoanh"}
        findings.save(aid, step["id"], doc)
    return ids


def apply_pending(cfg: dict, st: dict, sid: str, n: int) -> str:
    """C6: the redos stored while the step ran become `H` findings now, on the version just ingested (or the approved
    version of an earlier step), and the asset goes to a fix round as a normal redo does. Only the earliest step that holds
    some is applied; the others wait for the next ingest. Nothing is applied when the ingest moved the asset before it."""
    pend = st.get("pending_redo") or {}
    here = step_of(cfg, st["stage"])[0]
    due = sorted((step_of(cfg, k)[0], k) for k in pend if pend[k] and step_of(cfg, k)[0] <= here)
    if not due or st["state"] not in REDO_FROM:
        return ""
    i, k = due[0]
    step = cfg["steps"][i]
    v = n if k == sid == st["stage"] else st["approved"].get(k) or st["versions"].get(k)
    if v is None:
        return ""
    entries = pend.pop(k)
    if w := next((w for w in st.get("offer_log", []) if w["key"] == st.get("offer_key") and "decision" not in w), None):
        w |= {"decision": "redo", "decided": now()}
    st.pop("ask", None)
    got = []
    for e in entries[:-1]:
        got.append(findings.add_human(st["id"], step, v, e["text"], e["marks"]))
    got.append(redo(cfg, st, i, step, v, entries[-1]["text"], entries[-1]["marks"]))
    for e, ids in zip(entries, got):
        if e["folder"]:
            annotate.record(Path(e["folder"]), e["marks"], ids[len(ids) - len(e["marks"]):])
    ids = [x for g in got for x in g]
    return f"Cần sửa nhận lúc đang chạy → {k} {', '.join(ids)}"


def retry(a):
    st = load_st(a.id)
    if st["state"] == "done_enabled":
        move(st, "resume", load_cfg())
    elif st["state"] == "waiting_human" and st.get("stalled_from"):
        was = st["stalled_from"]
        move(st, f"restall_{was}")
        st |= {"note": "", "offer": None, "offer_key": None, "label": ""}
        if was in ("running", "evidence_running"):
            st["worker_agent_id"] = None
    elif st["state"] == "blocked" and st.get("blocked_from"):
        move(st, f"retry_{st.pop('blocked_from')}")
        st["note"] = ""
    elif st["state"] == "blocked" and step_of(load_cfg(), st["stage"])[1]["script"]:
        move(st, "retry_todo")
        st["note"] = ""
    else:
        ev = "retry_evidence" if st.get("evidence") else "retry" if st["versions"].get(st["stage"]) else "retry_todo"
        move(st, ev)
        if ev == "retry" and st.get("note"):
            st["retry_why"] = st["note"].replace("thiếu output bắt buộc:", "thiếu output:", 1)
        st["note"] = ""
    if st["state"] == "running":
        set_aside(vdir(a.id, st["stage"], st["versions"][st["stage"]]) / "worker-out.md")
    save_st(st)
    ledger(f"{a.id} · retry")
    print(f"{a.id}: → {st['state']}. Tiếp: {next_action(st)}")
    dispatch_next(load_cfg(), st, CHANGE_DISPATCH)


def after_feedback(aid: str, before: tuple):
    """D30.5: `feedback --action approve|redo` that moved the asset or took a decision prints the next dispatch, as
    `ingest` does. A redo of a held fix round stays in `fix` but opens a new round."""
    st = load_st(aid)
    if (st["stage"], st["state"], len(st.get("decisions", {}))) != before:
        dispatch_next(load_cfg(), st, CHANGE_DISPATCH)


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
        offer: str | None = None, by: str = "user", zip_path: str | None = None) -> tuple[bool, str]:
    """One decision per offer (D22.8), from the CLI, the local board or a remote row. `offer` is the offer the page
    showed; `regions` are marks on images of the current card (review-board.md §4). Returns (applied, message):
    applied is False for a skipped call, so a page keeps the user's marks. Nothing reaches the disk before the
    decision can no longer die. by: `producer` is the Producer's own approval (test_mode only); only `user` deletes at
    DUYỆT 2 (D40)."""
    from .board import build_outputs, view_images
    cfg = load_cfg()
    st = load_st(aid)
    if action not in ACTIONS:
        die("action phải là " + " | ".join(ACTIONS))
    target = step_id or st["stage"]
    i, step = step_of(cfg, target)
    if action == "redo" and i > step_of(cfg, st["stage"])[0]:
        die(f"{aid}: không làm lại {target} được: asset đang ở bước {st['stage']}")
    if asset_card.skipped(step, st):
        die(f"{aid}: bước {target} không chạy cho asset này (thẻ views: none)")
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
    if (action == "approve" and st["state"] == "waiting_human" and target == st["stage"] and st.get("stalled_from")
            and step.get("reviewer")):
        die(f"{aid}: không duyệt được {key}: bản {UNREVIEWED} (kẹt ở {st['stalled_from']}) → `retry {aid}` để giao lại, "
            "hoặc Cần sửa, hoặc ghi chú")
    if by == "producer" and policy.load().get("test_mode") is not True:
        die(f"{aid}: --by producer chỉ chạy khi production/policy.yaml có test_mode: true; dự án thật do người dùng duyệt")
    if zip_path and not (action == "approve" and target == "assemble" and by == "user"):
        die(f"{aid}: --zip chỉ dùng khi người dùng duyệt assemble (DUYỆT 2)")
    if action == "redo" and st.get("purged"):
        die(purge.refused(st))
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

    def settle(approved: bool = False) -> list[str]:
        keep()
        ids = findings.add_human(aid, step, n, None, marks) if marks and waiting else []
        return marks_as_notes(aid, step, n, ids) if approved else ids

    ids, msg, armed, finished, hold = [], "đã ghi feedback", False, False, False
    if answer:
        decide()
        msg = texture.resolve(st, "call" if action == "approve" else "paint", policy.BY["human"])
        ids = settle()
    elif action == "approve" and waiting:
        decide()
        approve(cfg, st, step, n, policy.BY["human" if by == "user" else "producer"])
        ids = settle(approved=True)
        if not step.get("reviewer"):
            findings.close_human(aid, target, n)
        msg = f"đã duyệt {key} → {st['stage']}/{st['state']}"
        armed = target == "assemble" and by == "user"
        finished = st["state"] == "done"
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
            hold = st["state"] in PENDING_FROM and n is not None
            msg = (f"đã ghi feedback; {aid} đang {st['state']}, lưu Cần sửa {target}: áp dụng ở lần ingest kế" if hold else
                   f"đã ghi feedback; {aid} đang {st['state']}, sẽ áp dụng ở vòng sau")
        ids = settle()
        if hold:
            st.setdefault("pending_redo", {}).setdefault(target, []).append(
                {"text": raw or (None if marks else text), "at": now(), "offer": offer, "marks": marks or [],
                 "folder": rel(folder) if folder else None})
    if marks:
        annotate.record(folder, marks, ids)
        msg += (f"; khoanh {len(marks)} vùng → {', '.join(ids)}" if ids else
                f"; khoanh {len(marks)} vùng lưu ở {rel(folder)}, chưa thành finding (state={st['state']})")
    save_st(st)
    ledger(f"{aid} · {'người dùng' if by == 'user' else 'Producer'} {action} {target} · {text[:80]}")
    build_outputs(cfg)
    from .report import finish
    report_ok, table = finish(st) if finished else (False, "")
    if armed:
        armed = "\n" + purge.on_approve(cfg, st, zip_path, report_ok)
    return True, f"{aid}: {msg}. Tiếp: {next_action(st)}{armed or ''}" + (f"\n{table}" if table else "")
