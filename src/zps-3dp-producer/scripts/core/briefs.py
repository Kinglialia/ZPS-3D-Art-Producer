"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import json

from . import findings
from .hashes import ad_text
from .loop import next_action
from .state import ASSETS, die, ledger, load_cfg, load_st, rel, save_st, step_of, vdir


def worker_brief(cfg, st, i, step, n, fix: bool) -> str:
    aid = st["id"]
    d = vdir(aid, step["id"], n)
    a = ASSETS / aid
    lines = [
        f"# Brief — {st['title']} · bước `{step['id']}` · v{n}",
        "",
        "Đọc hết file này trước khi làm. Đây là toàn bộ yêu cầu; không cần hỏi lại.",
        "",
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
            lines.append(f"{k}. Đầu ra đã duyệt của bước `{prev}`: `{rel(pd / 'final')}/` và `{rel(pd / 'handoff.md')}`.")
            k += 1
    if fix and n > 1:
        m = st.get("fix_base") or n - 1
        pd = vdir(aid, step["id"], m)
        tf = (findings.load(aid, step["id"], m) or {}).get("top_fix")
        why = (f"Sửa đúng `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}`; repair, preserve, acceptance của từng id trong "
               f"`{rel(findings.path(aid, step['id'], m))}`. Rồi tới feedback mới nhất của người dùng trong feedback.md."
               if tf else "Lý do phải sửa: feedback mới nhất của người dùng trong feedback.md.")
        lines += [
            f"{k}. Bản gốc: `{rel(pd)}/` (final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
            f"{k + 1}. {why}",
            "",
            f"Đây là vòng sửa {st['fix_round']}. Chỉ sửa đúng các điểm trên; giữ nguyên những gì đã đạt.",
        ]
    lines += [
        "",
        "## Đầu ra",
        f"- Sản phẩm vào `{rel(d / 'final')}/`; script, json, log, bản trung gian vào `{rel(d / 'work')}/`.",
    ]
    if cfg["preview"]["spec"]:
        lines.append(f"- Preview: {cfg['preview']['spec']}")
    if step["outputs"]:
        req = ", ".join(f"`{o}`" for o in step["outputs"])
        lines.append(f"- Bắt buộc có (tính từ `{rel(d)}/`): {req}.")
    lines.append(f"- Ghi bàn giao cho bước sau vào `{rel(d / 'handoff.md')}` nếu bước sau cần biết quyết định của bạn.")
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
        "PROFILE_HASH: <chép giá trị PROFILE_HASH của brief này>",
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
    m = st.get("fix_base")
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
        *([f"- Bản gốc v{m}: ảnh cùng góc `{rel(vdir(aid, sid, m) / 'final')}/`; finding đủ trường "
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


def run(a):
    cfg = load_cfg()
    st = load_st(a.id)
    i, step = step_of(cfg, st["stage"])
    s = st["state"]
    r = cfg["review"]
    if s in ("todo", "fix", "running"):
        if s == "running":
            n = st["versions"][step["id"]]
        else:
            n = st["versions"].get(step["id"], 0) + 1
            st["versions"][step["id"]] = n
        d = vdir(a.id, step["id"], n)
        (d / "final").mkdir(parents=True, exist_ok=True)
        (d / "work").mkdir(parents=True, exist_ok=True)
        fix = s == "fix" or (s == "running" and st.get("fix_round", 0) > 0)
        if s != "running":
            st["fix_base"] = n - 1 if fix and n > 1 else None
        bp = d / "brief-worker.md"
        bp.write_text(worker_brief(cfg, st, i, step, n, fix), encoding="utf-8")
        model = step.get("model")
        resume = None
        if fix and st.get("fix_round", 0) <= r["resume_rounds"]:
            resume = st.get("worker_agent_id")
        elif fix and step.get("escalate_model"):
            model = step["escalate_model"]
        st["state"] = "running"
        out = {"role": "worker", "agent": step["agent"], "model": model, "resume": resume,
               "brief": rel(bp), "report": rel(d / "report-worker.md")}
    elif s in ("review", "reviewing"):
        n = st["versions"][step["id"]]
        d = vdir(a.id, step["id"], n)
        bp = d / "brief-review.md"
        bp.write_text(review_brief(cfg, st, step, n), encoding="utf-8")
        st["state"] = "reviewing"
        out = {"role": "reviewer", "agent": step.get("reviewer") or r["reviewer_agent"], "model": r["reviewer_model"],
               "resume": None, "brief": rel(bp), "report": rel(d / "report-review.md")}
    else:
        die(f"{a.id}: state={s}, không có việc để giao ({next_action(st)})")
    save_st(st)
    ledger(f"{a.id} · {step['id']} v{n} · giao {out['role']} ({out['agent']})")
    print(json.dumps(out, ensure_ascii=False))
