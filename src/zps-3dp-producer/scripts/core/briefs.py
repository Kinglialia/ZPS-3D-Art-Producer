"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from . import findings, hashes, preflight, texture
from .contract import NONE, parse_worker
from .hashes import ad_text
from .loop import move, next_action, review_base, set_aside
from .state import (ASSETS, DELIVER, ROOT, SKILL_DIR, die, ledger, load_cfg, load_st, outputs_of, rel, save_st, step_of,
                    vdir)


def image_gen(preset: Path) -> dict:
    import yaml
    ig = (yaml.safe_load(preset.read_text(encoding="utf-8")) or {}).get("image_gen") or {}
    if not (ig.get("codex_model") and ig.get("reasoning")):
        die(f"{rel(preset)}: thiếu image_gen: {{codex_model, reasoning}} (D15.1)")
    return ig


def pilot_line(prof: dict) -> str:
    """D21.7, D22.10: the pilot package in this runtime's own deliver/, or not_checked while there is no pilot."""
    p = prof.get("pilot_asset")
    return f"PILOT: {rel(DELIVER / p)}/" if p else "PILOT: none (pilot_asset: null): so với pilot ghi not_checked"


def tools_line(st, step, pf: dict | None, preset: Path, gen: bool = True, extra: list[str] = ()) -> list[str]:
    t = SKILL_DIR / "agents" / f"zps-3dp-{step.get('agent')}" / "tools"
    out = ([f"TOOLS: {t}"] if t.is_dir() else []) + (
        [f"BLENDER: {((pf or {}).get('blender') or {}).get('path') or 'blender'}"] if "blender" in step["uses"] else []
    ) + list(extra)
    if gen and "codex_image" in step["uses"]:
        ig = image_gen(preset)
        out += [f"GEN_IMAGE: {SKILL_DIR / 'scripts' / 'gen_image_codex.py'}",
                f"GEN_ARGS: --model {ig['codex_model']} --reasoning {ig['reasoning']} "
                f"--pid-file {rel(ROOT / 'pids' / 'codex_image' / (st['id'] + '.pid'))}"]
    return out + [""] if out else []


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


def concept_files(st, step, review: bool = False) -> list[str]:
    from check_card import required_files
    d = Path(st["concept_dir"])
    want = step["review_concept"] if review and step["review_concept"] is not None else step["concept"]
    names = [x.format(id=st["id"]) for x in want] if want else required_files(st["id"], True)
    return [x for x in names if not x.endswith(".layout.md") or (d / x).is_file()]


def input_finals(st, ids: list[str]) -> list[tuple[str, Path]]:
    return [(p, vdir(st["id"], p, v) / "final") for p in ids if (v := st["approved"].get(p))]


def handoff_issues(st, prev: str, v: int) -> str | None:
    """D20.3: the ISSUES line of the approved worker report of an input step; None when it hands over nothing."""
    c, _ = parse_worker((vdir(st["id"], prev, v) / "report-worker.md").read_text(encoding="utf-8"))
    issues = c.get("ISSUES", "")
    return None if issues.lower() in NONE else issues


def pid_line(st, step) -> list[str]:
    if "blender" not in step["uses"]:
        return []
    f = rel(ROOT / "pids" / "blender" / f"{st['id']}.pid")
    return [f"- Mỗi lệnh Blender: `<lệnh> & echo $! > {f}; wait $!; rm -f {f}`."]


def worker_brief(cfg, st, step, n, fix: bool, ph: str, pf: dict | None, preset: Path, prof: dict,
                 extra: list[str] = ()) -> str:
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
        *tools_line(st, step, pf, preset, extra=([pilot_line(prof)] if step["pilot"] else []) + list(extra)),
        "## Đầu vào (đọc theo thứ tự)",
        f"1. `{rel(a / 'brief.md')}` — yêu cầu gốc của người dùng.",
        f"2. `{rel(a / 'rubric.md')}` mục `## {step['id']}` — tiêu chí chấm; tự check trước khi báo cáo.",
        f"3. `{rel(a / 'feedback.md')}` — đọc mục \"Hiện hành\" và các dòng log gần nhất.",
        f"4. `{rel(ROOT / 'PROJECT-PROFILE.yaml')}` — profile dự án; `{preset}` — preset của profile.",
    ]
    k = 5
    if st.get("concept_dir"):
        names = ", ".join(f"`{x}`" for x in concept_files(st, step))
        lines.append(f"{k}. Concept đã duyệt trong `{st['concept_dir']}`: chỉ đọc {names}. "
                     "Bỏ qua file và thư mục khác (bản nháp cũ).")
        k += 1
    lines.append(f"{k}. {ad_text(cfg, {step['id']})}")
    k += 1
    for prev, fd in input_finals(st, step["inputs"]):
        lines.append(f"{k}. Đầu ra đã duyệt của bước `{prev}`: `{rel(fd)}/`.")
        k += 1
    for prev in step["issues"]:
        if (v := st["approved"].get(prev)) and (issues := handoff_issues(st, prev, v)):
            lines.append(f"{k}. ISSUES của report worker `{prev}` v{v}: {issues}")
            k += 1
    for prev in step["inputs"]:
        v = st["approved"].get(prev)
        if v and (ids := [i for i, f in findings.open_of(findings.load(aid, prev, v)).items() if f["kind"] in findings.NOTE]):
            lines.append(f"{k}. Ghi chú còn mở của reviewer `{prev}` v{v}: {', '.join(ids)} trong "
                         f"`{rel(findings.path(aid, prev, v))}` (`note_texture`: TEXTURE NOTE, `note_exception`: NGOẠI LỆ).")
            k += 1
    if not fix and (pv := (st.get("prior") or {}).get(step["id"])):
        lines.append(f"{k}. Bản đã duyệt trước của bước này (dựng từ đầu vào cũ): `{rel(vdir(aid, step['id'], pv) / 'final')}/`. "
                     "Giữ phần có đầu vào không đổi, theo file agent.")
        k += 1
    m = st.get("fix_base")
    if fix and m:
        pd = vdir(aid, step["id"], m)
        bad = failed_checks(pd)
        doc = findings.load(aid, step["id"], m) or {}
        tf = doc.get("top_fix")
        part = findings.REOPENED_PART.get(tf["kind"]) if tf else None
        outside = (f"{part[0].upper() + part[1:]} đã duyệt ở `{findings.REOPEN[tf['kind']]}`, sửa ngoài bước này: "
                   f"không sửa {part} ở đây." if part else "")
        tf = None if outside else tf
        fp = f"`{rel(findings.path(aid, step['id'], m))}`"
        human = [i for i, f in findings.open_of(doc).items() if i.startswith("H")]
        why = (f"Sửa đúng `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}`; repair, preserve, acceptance của từng id trong "
               f"{fp}. Rồi tới feedback mới nhất của người dùng trong feedback.md."
               if tf else "Lý do phải sửa: feedback mới nhất của người dùng trong feedback.md." + (f" {outside}" if outside else ""))
        if human:
            why = (f"Ưu tiên 1, feedback của người dùng: sửa {', '.join(f'`{i}`' for i in human)} (nguyên văn trong "
                   f"`acceptance` của {fp} và feedback.md). Đối chiếu từng ý với concept; không bỏ ý nào. "
                   + (f"Sau đó: `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}` của reviewer." if tf else outside))
        lines += [
            f"{k}. Bản gốc: `{rel(pd)}/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
            *([f"{k + 1}. Đọc trước nguyên văn lỗi script của bản gốc: {', '.join(f'`{b}`' for b in bad)}."] if bad else []),
            f"{k + 1 + bool(bad)}. {why}",
            *(f"   - Vùng người dùng khoanh: {x}" for x in findings.mark_lines(doc)),
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
        req = ", ".join(f"`{o}`" for o in outputs_of(step, st))
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
        f"RUBRIC: <key trong mục ## {step['id']}>=pass|fail; ...",
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
    cmp_ids = findings.compare_ids(base)
    pick = bool(tf and tf["kind"] == "param")
    nxt = (base or {}).get("next_id", 1)
    tie = sorted((k for k in step["top_fix"] if k in findings.TIE_RANK), key=lambda k: -findings.TIE_RANK[k])
    single = [k for k in step["top_fix"] if k in findings.SINGLE]
    lines = [
        f"# Review brief — {st['title']} · bước `{sid}` · v{n}",
        "",
        "Bạn chấm độc lập. Không sửa output, chỉ ghi report.",
        "",
        "## Chấm cái gì",
        f"- Output: `{rel(d / 'final')}/` (ảnh preview) và số liệu trong `{rel(d / 'work')}/` nếu có.",
        f"- Báo cáo tự check của worker: `{rel(d / 'report-worker.md')}` — tham khảo, không tin thay bằng chứng.",
        f"- Theo: `{rel(a / 'rubric.md')}` mục `## {sid}`, `{rel(a / 'brief.md')}`, mục \"Hiện hành\" trong `{rel(a / 'feedback.md')}`.",
        *([f"- Concept đã duyệt để đối chiếu, trong `{st['concept_dir']}`: chỉ "
           + ", ".join(f"`{x}`" for x in concept_files(st, step, review=True)) + "."] if st.get("concept_dir") else []),
        *(f"- Đầu ra đã duyệt của bước `{p}` (đầu vào, không chấm lại): `{rel(fd)}/`."
          for p, fd in input_finals(st, step["review_inputs"])),
        f"- Profile dự án (`hidden_side_rules`, `scale_refs`): `{rel(ROOT / 'PROJECT-PROFILE.yaml')}`.",
        f"- {ad_text(cfg, {sid, 'review'})}",
        *(f"- Vùng người dùng khoanh, kiểm từng vùng: {x}" for x in findings.mark_lines(base)),
        *([f"- Chấm lại v{n} với ảnh thêm `{rel(d / 'review' / ('evidence-%d' % st['evidence']['k']))}/`; "
           f"finding đủ trường `{rel(findings.path(aid, sid, n))}`."] if m == n else
          [f"- Bản gốc v{m}: ảnh cùng góc `{rel(vdir(aid, sid, m) / 'final')}/`; finding đủ trường "
           f"`{rel(findings.path(aid, sid, m))}`."] if base else []),
        *([f"- Phương án param: `{rel(d / 'variants')}/<a|b|c>/`; a là `final/`. Nhãn ảnh trong EVIDENCE_OPENED: "
           f"`v{n}a/<ảnh>`, `v{n}b/<ảnh>`, `v{n}c/<ảnh>`; ảnh bản gốc: `v{m}/<ảnh>`."] if pick else []),
        "",
        "## Báo cáo",
        f"Ghi vào `{rel(d / 'report-review.md')}`, mở đầu đúng format, mỗi khóa một dòng:",
        "```",
        "VERDICT: PASS | FIX | ESCALATE",
        f"RUBRIC: <key trong mục ## {sid}>=pass|fail|unclear; ...",
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
        f"- FINDINGS chỉ ghi finding mới, id từ F{nxt}, đủ mọi trường; evidence dẫn nhãn trong EVIDENCE_OPENED. "
        "Không có finding mới: `FINDINGS: none`.",
        *([f"- region mở đầu bằng {'|'.join(step['regions'])}, vd `{step['regions'][0]}: mép mái`; "
           + "; ".join(f"`{k}` nói về đầu ra của `{findings.REOPEN[k]}`, không theo luật này" for k in step["top_fix"]
                       if k in findings.REOPEN) + "."] if step["regions"] else []),
        *(["- PRIOR: thay `?` bằng open|resolved|regressed|superseded. resolved chỉ khi thấy bằng chứng cho "
           "acceptance, ghi nhãn ảnh đó vào evidence."] if op else []),
        *([f"- COMPARE: so ảnh cùng góc với v{m}: better|same|worse. resolved cần better; worse thì regressed."]
          if cmp_ids else []),
        "- VERDICT: còn blocker/major → FIX; chỉ còn unclear → FIX với TOP_FIX need_evidence; không còn → PASS; "
        "người dùng phải chọn gu hoặc rubric mâu thuẫn brief → ESCALATE. preference không chặn PASS.",
        "- TOP_FIX chỉ khi FIX: loại của finding nặng nhất" + (f" (cùng mức: {', '.join(tie)} trước)" if tie else "")
        + (f"; {', '.join(single)} đúng 1 id; loại khác:" if single else ";")
        + " mọi finding blocker/major/minor đang mở của loại đó; "
        "need_evidence: mọi finding unclear đang mở. PASS hoặc ESCALATE: `TOP_FIX: none`.",
        "- COUNTS: số finding đang mở (mới + open/regressed). Mỗi key unclear trong RUBRIC cần một finding unclear.",
        "",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT và COUNTS.",
    ]
    return "\n".join(lines) + "\n"


def evidence_brief(st, step, n, ed, ph: str, pf: dict | None, preset: Path) -> str:
    aid, sid = st["id"], step["id"]
    tf = findings.load(aid, sid, n)["top_fix"]
    lines = [
        f"# Brief bằng chứng — {st['title']} · bước `{sid}` · v{n} · {ed.name}",
        "",
        f"PROFILE_HASH: {ph}",
        "",
        *tools_line(st, step, pf, preset, gen=False),
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


def model_glb(st) -> Path:
    return vdir(st["id"], "model", st["approved"]["model"]) / "final" / f"{st['id']}-untextured.glb"


def stop(a, cfg, st, sid, s, event: str, note: str):
    """The texture gate stopped the asset before a version exists (§6.3): one line instead of a dispatch."""
    from .board import build_outputs
    if event == "stuck" and s in ("todo", "fix"):
        st["blocked_from"] = s
    move(st, event)
    st["note"] = note
    save_st(st)
    ledger(f"{a.id} · {sid} · {st['state']} trước khi giao: {note}")
    build_outputs(cfg)
    print(f"{a.id}: {sid} → {st['state']} trước khi giao. Tiếp: {next_action(st)}")


def run(a):
    cfg = load_cfg()
    st = load_st(a.id)
    i, step = step_of(cfg, st["stage"])
    sid, s, r = step["id"], st["state"], cfg["review"]
    if not step["enabled"]:
        die(f"{a.id}: bước {sid} chưa bật (enabled = false), không giao")
    from check_profile import PRESETS
    from .intake import load_profile
    prof = load_profile()
    ph, pf, preset = hashes.digest(prof), preflight.load(), PRESETS / f"{prof['preset']}.yaml"
    if s in ("todo", "fix", "running", "evidence", "evidence_running") and (off := preflight.off(step, pf)):
        die(f"{a.id}: bước {sid} cần {', '.join(off)} đang tắt (preflight) → sửa môi trường rồi chạy lại `preflight`")
    for res in step["uses"]:
        if res in cfg["limits"]:
            (ROOT / "pids" / res).mkdir(parents=True, exist_ok=True)
    extra = []
    if sid == texture.STEP and s in ("todo", "fix", "running"):
        st.get("concept_dir") or die(f"{a.id}: bước {sid} cần concept trong _approved/ (asset tạo bằng `new` không có)")
        g = texture.gate(st, prof, model_glb(st), Path(st["concept_dir"]) / "concept_albedo.png")
        if isinstance(g, tuple):
            return stop(a, cfg, st, sid, s, *g)
        extra = g
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
        if step["script"]:
            blender = ((pf or {}).get("blender") or {}).get("path") or "blender"
            cmd = [sys.executable, str(SKILL_DIR / "scripts" / step["script"]), a.id, "--version", str(n),
                   "--profile-hash", ph, "--blender", blender]
            out = {"role": "script", "command": shlex.join(cmd), "report": rel(d / "report-script.md")}
        else:
            bp = d / "brief-worker.md"
            bp.write_text(worker_brief(cfg, st, step, n, fix, ph, pf, preset, prof, extra), encoding="utf-8")
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
        bp.write_text(evidence_brief(st, step, n, ed, st["inputs"][sid][f"v{n}"]["profile"], pf, preset), encoding="utf-8")
        out = {"role": "worker", "agent": f"zps-3dp-{step['agent']}", "model": step.get("model"), "resume": st.get("worker_agent_id"),
               "brief": rel(bp), "report": rel(ed / "report-worker.md")}
    elif s in ("review", "reviewing"):
        n = st["versions"][sid]
        d = vdir(a.id, sid, n)
        bp = d / "brief-review.md"
        bp.write_text(review_brief(cfg, st, step, n), encoding="utf-8")
        out = {"role": "reviewer", "agent": f"zps-3dp-{step['reviewer']}", "model": r["reviewer_model"],
               "resume": None, "brief": rel(bp), "report": rel(d / "report-review.md")}
    else:
        die(f"{a.id}: state={s}, không có việc để giao ({next_action(st)})")
    set_aside(Path(out["report"]))
    move(st, "dispatch")
    save_st(st)
    ledger(f"{a.id} · {sid} v{n} · giao {out['role']} ({out.get('agent') or step['script']})")
    print(json.dumps(out, ensure_ascii=False))
