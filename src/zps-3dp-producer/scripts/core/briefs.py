"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import json

from . import findings, hashes, preflight
from .hashes import ad_text
from .loop import move, next_action, review_base
from .state import ASSETS, ROOT, SKILL_DIR, die, ledger, load_cfg, load_st, rel, save_st, step_of, vdir


def tools_line(step) -> list[str]:
    t = SKILL_DIR / "agents" / f"zps-3dp-{step.get('agent')}" / "tools"
    return [f"TOOLS: {t}", ""] if t.is_dir() else []


def failed_checks(vd) -> list[str]:
    """D26.4: kit result JSON in final/review/{gates,checks}/ whose overall is fail or error."""
    out = []
    for p in sorted(p for sub in ("gates", "checks") for p in (vd / "final" / "review" / sub).glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and (r.get("overall") in ("fail", "error") or r.get("pass") is False):
            out.append(rel(p))
    return out


def pid_line(st, step) -> list[str]:
    if "blender" not in step["uses"]:
        return []
    f = rel(ROOT / "pids" / "blender" / f"{st['id']}.pid")
    return [f"- Mỗi lệnh Blender: `<lệnh> & echo $! > {f}; wait $!; rm -f {f}` (`P next` đếm slot theo file này)."]


def worker_brief(cfg, st, i, step, n, fix: bool, ph: str) -> str:
    aid = st["id"]
    d = vdir(aid, step["id"], n)
    a = ASSETS / aid
    lines = [
        f"# Brief — {st['title']} · bước `{step['id']}` · v{n}",
        "",
        f"PROFILE_HASH: {ph}",
        "",
        "Đọc hết file này trước khi làm. Đây là toàn bộ yêu cầu; không cần hỏi lại.",
        "",
        *tools_line(step),
        "## Đầu vào (đọc theo thứ tự)",
        f"1. `{rel(a / 'brief.md')}` — yêu cầu gốc của người dùng.",
        f"2. `{rel(a / 'rubric.md')}` — tiêu chí chấm; tự check trước khi báo cáo.",
        f"3. `{rel(a / 'feedback.md')}` — đọc mục \"Hiện hành\" và các dòng log gần nhất.",
    ]
    k = 4
    if st.get("concept_dir"):
        lines.append(f"{k}. Concept đã duyệt: `{st['concept_dir']}` — xem mọi ảnh trong thư mục, kể cả thư mục con.")
        k += 1
    lines.append(f"{k}. {ad_text(cfg, {step['id']})}")
    k += 1
    if i > 0:
        prev = cfg["steps"][i - 1]["id"]
        pv = st["approved"].get(prev)
        if pv:
            pd = vdir(aid, prev, pv)
            lines.append(f"{k}. Đầu ra đã duyệt của bước `{prev}`: `{rel(pd / 'final')}/`.")
            k += 1
    m = st.get("fix_base")
    if fix and m:
        pd = vdir(aid, step["id"], m)
        bad = failed_checks(pd)
        tf = (findings.load(aid, step["id"], m) or {}).get("top_fix")
        why = (f"Sửa đúng `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}`; repair, preserve, acceptance của từng id trong "
               f"`{rel(findings.path(aid, step['id'], m))}`. Rồi tới feedback mới nhất của người dùng trong feedback.md."
               if tf else "Lý do phải sửa: feedback mới nhất của người dùng trong feedback.md.")
        lines += [
            f"{k}. Bản gốc: `{rel(pd)}/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
            *([f"{k + 1}. Đọc trước nguyên văn lỗi script của bản gốc: {', '.join(f'`{b}`' for b in bad)}."] if bad else []),
            f"{k + 1 + bool(bad)}. {why}",
            "",
            f"Đây là vòng sửa {st['fix_round']}. Chỉ sửa đúng các điểm trên; giữ nguyên những gì đã đạt.",
        ]
    lines += [
        "",
        "## Đầu ra",
        f"- Sản phẩm vào `{rel(d / 'final')}/`; JSON gate và check vào `{rel(d / 'final' / 'review')}/gates/`, `checks/`; "
        f"script, log, bản trung gian vào `{rel(d / 'work')}/`.",
    ]
    lines += pid_line(st, step)
    if cfg["preview"]["spec"]:
        lines.append(f"- Preview: {cfg['preview']['spec']}")
    if step["outputs"]:
        req = ", ".join(f"`{o}`" for o in step["outputs"])
        lines.append(f"- Bắt buộc có (tính từ `{rel(d)}/`): {req}.")
    if step.get("external_command"):
        cmd = step["external_command"].format(
            request=rel(d / "work" / f"{step['id']}_request.md"), vdir=rel(d), log=rel(d / "work" / "external.log")
        )
        lines += ["", "## Lệnh ngoài", "Chạy nền, chờ file output xuất hiện; chỉ xem cuối log khi lỗi:", "```", cmd, "```"]
    lines += [
        "",
        "## Báo cáo",
        f"Ghi báo cáo đầy đủ vào `{rel(d / 'report-worker.md')}`. Các dòng đầu tiên đúng format:",
        "```",
        "STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED",
        f"OUTPUT: {rel(d / 'final')}/",
        "RUBRIC: <key>=pass|fail; <key>=pass|fail; ...",
        "ISSUES: <tối đa 2 vấn đề còn lại, hoặc none>",
        "PROFILE_HASH: <chép dòng PROFILE_HASH ở đầu brief này>",
        *(["FIXED: F<n>, ...   (id bạn cho là đã sửa; reviewer quyết)"] if fix else []),
        "```",
        "Tin nhắn trả về cho Producer: chỉ dòng STATUS.",
        "",
        "## Ràng buộc",
        f"- Không hỏi người dùng. Giả định cần thiết ghi vào `{rel(d / 'work' / 'notes.md')}`, rồi làm tiếp.",
        "- Không gọi subagent reviewer; review do Producer sắp xếp.",
        "- Không sửa brief.md, rubric.md, feedback.md, status.json, ledger.md.",
    ]
    return "\n".join(lines) + "\n"


def review_brief(cfg, st, step, n) -> str:
    aid, sid = st["id"], step["id"]
    d = vdir(aid, sid, n)
    a = ASSETS / aid
    m = review_base(st, n)
    base = findings.load(aid, sid, m)
    op = findings.open_of(base)
    tf = (base or {}).get("top_fix")
    cmp_ids = tf["ids"] if tf and tf["kind"] != "need_evidence" else []
    pick = bool(tf and tf["kind"] == "param")
    nxt = (base or {}).get("next_id", 1)
    tie = [k for k in step["top_fix"] if k in findings.TIE_FIRST]
    lines = [
        f"# Review brief — {st['title']} · bước `{sid}` · v{n}",
        "",
        "Bạn chấm độc lập. Không sửa output, chỉ ghi report.",
        "",
        "## Chấm cái gì",
        f"- Output: `{rel(d / 'final')}/` (ảnh preview) và số liệu trong `{rel(d / 'work')}/` nếu có.",
        f"- Báo cáo tự check của worker: `{rel(d / 'report-worker.md')}` — tham khảo, không tin thay bằng chứng.",
        f"- Theo: `{rel(a / 'rubric.md')}`, `{rel(a / 'brief.md')}`, mục \"Hiện hành\" trong `{rel(a / 'feedback.md')}`.",
        *([f"- Concept đã duyệt để đối chiếu: `{st['concept_dir']}`."] if st.get("concept_dir") else []),
        f"- {ad_text(cfg, {sid, 'review'})}",
        *([f"- Chấm lại v{n} với ảnh thêm `{rel(d / 'review' / ('evidence-%d' % st['evidence']['k']))}/`; "
           f"finding đủ trường `{rel(findings.path(aid, sid, n))}`."] if m == n else
          [f"- Bản gốc v{m}: ảnh cùng góc `{rel(vdir(aid, sid, m) / 'final')}/`; finding đủ trường "
           f"`{rel(findings.path(aid, sid, m))}`."] if base else []),
        *([f"- Phương án param: `{rel(d / 'variants')}/<a|b|c>/`; a là `final/`."] if pick else []),
        "",
        "## Báo cáo",
        f"Ghi vào `{rel(d / 'report-review.md')}`, mở đầu đúng format, mỗi khóa một dòng:",
        "```",
        "VERDICT: PASS | FIX | ESCALATE",
        "RUBRIC: <key>=pass|fail|unclear; ...",
        "COUNTS: blocker=N; major=N; minor=N; preference=N; unclear=N",
        f"TOP_FIX: <{'|'.join(findings.top_fix_kinds(step))}>: F<n>[, F<m>]",
        "EVIDENCE_OPENED: <nhãn ảnh và file đã mở>",
        *([f"COMPARE: {'; '.join(f'{i}=?' for i in cmp_ids)}"] if cmp_ids else []),
        *(["PICK: a|b|c"] if pick else []),
        "FINDINGS:",
        f"- F{nxt} [blocker|major|minor|preference|unclear] <{'|'.join(step['top_fix'])}>",
        "  region: … | viewing_condition: … | evidence: <nhãn trong EVIDENCE_OPENED> …",
        "  consequence: … | confidence: high|medium|low",
        "  repair: … | preserve: … | acceptance: …",
        *(["PRIOR:", *(f"- {i}: ? | evidence: ? | acceptance: {f['acceptance']}" for i, f in op.items())] if op else []),
        "```",
        f"- FINDINGS chỉ ghi finding mới, id từ F{nxt}, đủ mọi trường; evidence dẫn nhãn trong EVIDENCE_OPENED.",
        *(["- PRIOR: thay `?` bằng open|resolved|regressed|superseded. resolved chỉ khi thấy bằng chứng cho "
           "acceptance, ghi nhãn ảnh đó vào evidence."] if op else []),
        *([f"- COMPARE: so ảnh cùng góc với v{m}: better|same|worse. resolved cần better; worse thì regressed."]
          if cmp_ids else []),
        "- VERDICT: còn blocker/major → FIX; chỉ còn unclear → FIX với TOP_FIX need_evidence; không còn → PASS; "
        "người dùng phải chọn gu hoặc rubric mâu thuẫn brief → ESCALATE. preference không chặn PASS.",
        "- TOP_FIX chỉ khi FIX: loại của finding nặng nhất" + (f" (cùng mức: {', '.join(tie)} trước)" if tie else "")
        + "; structure đúng 1 id; loại khác: mọi finding blocker/major/minor đang mở của loại đó; "
        "need_evidence: mọi finding unclear đang mở.",
        "- COUNTS: số finding đang mở (mới + open/regressed). Mỗi key unclear trong RUBRIC cần một finding unclear.",
        "",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT và COUNTS.",
    ]
    return "\n".join(lines) + "\n"


def evidence_brief(st, step, n, ed, ph: str) -> str:
    aid, sid = st["id"], step["id"]
    tf = findings.load(aid, sid, n)["top_fix"]
    lines = [
        f"# Brief bằng chứng — {st['title']} · bước `{sid}` · v{n} · {ed.name}",
        "",
        f"PROFILE_HASH: {ph}",
        "",
        *tools_line(step),
        f"Reviewer cần thêm ảnh để chấm {', '.join(tf['ids'])}: đọc region, viewing_condition, evidence, acceptance "
        f"của các id này trong `{rel(findings.path(aid, sid, n))}`.",
        f"- Chỉ render các ảnh đó, ghi vào `{rel(ed)}/`. Không tạo version mới.",
        f"- Không sửa `{rel(vdir(aid, sid, n) / 'final')}/`. Script so hash trước và sau; đổi thì bỏ kết quả vòng này.",
        *pid_line(st, step),
        "",
        "## Báo cáo",
        f"Ghi `{rel(ed / 'report-worker.md')}`, các dòng đầu đúng format:",
        "```",
        "STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED",
        f"OUTPUT: {rel(ed)}/",
        "ISSUES: <tối đa 2 vấn đề còn lại, hoặc none>",
        "PROFILE_HASH: <chép dòng PROFILE_HASH ở đầu brief này>",
        "```",
        "Tin nhắn trả về cho Producer: chỉ dòng STATUS.",
    ]
    return "\n".join(lines) + "\n"


def run(a):
    cfg = load_cfg()
    st = load_st(a.id)
    i, step = step_of(cfg, st["stage"])
    sid, s, r = step["id"], st["state"], cfg["review"]
    if not step["enabled"]:
        die(f"{a.id}: bước {sid} chưa bật (enabled = false), không giao")
    from .intake import load_profile
    ph = hashes.digest(load_profile())
    if s in ("todo", "fix", "running", "evidence", "evidence_running") and (off := preflight.off(step, preflight.load())):
        die(f"{a.id}: bước {sid} cần {', '.join(off)} đang tắt (preflight) → sửa môi trường rồi chạy lại `preflight`")
    if "blender" in step["uses"]:
        (ROOT / "pids" / "blender").mkdir(parents=True, exist_ok=True)
    if s in ("todo", "fix", "running"):
        if s == "running":
            n = st["versions"][sid]
        else:
            n = st["versions"].get(sid, 0) + 1
            st["versions"][sid] = n
        d = vdir(a.id, sid, n)
        (d / "final").mkdir(parents=True, exist_ok=True)
        (d / "work").mkdir(parents=True, exist_ok=True)
        fix = s == "fix" or (s == "running" and st.get("fix_round", 0) > 0)
        hashes.record_inputs(cfg, st, i, n, ph)
        bp = d / "brief-worker.md"
        bp.write_text(worker_brief(cfg, st, i, step, n, fix, ph), encoding="utf-8")
        model = step.get("model")
        resume = None
        if fix and st.get("fix_round", 0) <= r["resume_rounds"]:
            resume = st.get("worker_agent_id")
        elif fix and step.get("escalate_model"):
            model = step["escalate_model"]
        out = {"role": "worker", "agent": f"zps-3dp-{step['agent']}", "model": model, "resume": resume,
               "brief": rel(bp), "report": rel(d / "report-worker.md")}
    elif s in ("evidence", "evidence_running"):
        n = st["versions"][sid]
        ed = vdir(a.id, sid, n) / "review" / f"evidence-{st['evidence']['k']}"
        ed.mkdir(parents=True, exist_ok=True)
        bp = ed / "brief-worker.md"
        bp.write_text(evidence_brief(st, step, n, ed, st["inputs"][sid][f"v{n}"]["profile"]), encoding="utf-8")
        out = {"role": "worker", "agent": f"zps-3dp-{step['agent']}", "model": step.get("model"), "resume": st.get("worker_agent_id"),
               "brief": rel(bp), "report": rel(ed / "report-worker.md")}
    elif s in ("review", "reviewing"):
        n = st["versions"][sid]
        d = vdir(a.id, sid, n)
        bp = d / "brief-review.md"
        bp.write_text(review_brief(cfg, st, step, n), encoding="utf-8")
        out = {"role": "reviewer", "agent": f"zps-3dp-{step.get('reviewer') or r['reviewer_agent']}", "model": r["reviewer_model"],
               "resume": None, "brief": rel(bp), "report": rel(d / "report-review.md")}
    else:
        die(f"{a.id}: state={s}, không có việc để giao ({next_action(st)})")
    move(st, "dispatch")
    save_st(st)
    ledger(f"{a.id} · {sid} v{n} · giao {out['role']} ({out['agent']})")
    print(json.dumps(out, ensure_ascii=False))
