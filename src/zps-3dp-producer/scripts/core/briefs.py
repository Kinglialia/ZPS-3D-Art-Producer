"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import json

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
        pd = vdir(aid, step["id"], n - 1)
        lines += [
            f"{k}. Bản trước: `{rel(pd)}/` (final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
            f"{k + 1}. Lý do phải sửa: `{rel(pd / 'report-review.md')}` (nếu có) và feedback mới nhất của người dùng trong feedback.md.",
            "",
            f"Đây là vòng sửa {st['fix_round']}. Chỉ sửa đúng các điểm fail; giữ nguyên những gì đã đạt.",
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
        f"Ghi báo cáo đầy đủ vào `{rel(d / 'report-worker.md')}`. Bốn dòng đầu tiên đúng format:",
        "```",
        "STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED",
        f"OUTPUT: {rel(d / 'final')}/",
        "RUBRIC: <key>=pass|fail; <key>=pass|fail; ...",
        "ISSUES: <tối đa 2 vấn đề còn lại, hoặc none>",
        "```",
        "Tin nhắn trả về cho Producer: chỉ đúng bốn dòng đó.",
        "",
        "## Ràng buộc",
        f"- Không hỏi người dùng. Giả định cần thiết ghi vào `{rel(d / 'work' / 'notes.md')}`, rồi làm tiếp.",
        "- Không gọi subagent reviewer; review do Producer sắp xếp.",
        "- Không sửa brief.md, rubric.md, feedback.md, status.json, ledger.md.",
    ]
    return "\n".join(lines) + "\n"


def review_brief(cfg, st, step, n) -> str:
    aid = st["id"]
    d = vdir(aid, step["id"], n)
    a = ASSETS / aid
    return "\n".join([
        f"# Review brief — {st['title']} · bước `{step['id']}` · v{n}",
        "",
        "Bạn chấm độc lập. Không sửa output, chỉ ghi report.",
        "",
        "## Chấm cái gì",
        f"- Output: `{rel(d / 'final')}/` (ảnh preview) và số liệu trong `{rel(d / 'work')}/` nếu có.",
        f"- Báo cáo tự check của worker: `{rel(d / 'report-worker.md')}` — tham khảo, không tin thay bằng chứng.",
        f"- Theo: `{rel(a / 'rubric.md')}`, `{rel(a / 'brief.md')}`, mục \"Hiện hành\" trong `{rel(a / 'feedback.md')}`.",
        *( [f"- Concept đã duyệt để đối chiếu: `{st['concept_dir']}`."] if st.get("concept_dir") else [] ),
        f"- {ad_text(cfg, {step['id'], 'review'})}",
        "",
        "## Báo cáo",
        f"Ghi vào `{rel(d / 'report-review.md')}`, mở đầu đúng format:",
        "```",
        "VERDICT: PASS | FIX | ESCALATE",
        "RUBRIC: <key>=pass|fail; ...",
        "FINDINGS:",
        "- [critical|minor] <ở đâu> — <sai gì> — <sửa thế nào để đạt>",
        "```",
        "PASS: mọi tiêu chí pass (minor không chặn). FIX: có tiêu chí fail mà worker sửa được.",
        "ESCALATE: vấn đề thuộc gu thẩm mỹ cần người dùng chọn, hoặc rubric mâu thuẫn với brief.",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT và RUBRIC.",
    ]) + "\n"


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
