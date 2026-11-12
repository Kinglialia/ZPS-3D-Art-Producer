"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from . import asset_card, findings, hashes, preflight, texture
from .contract import FALLBACK, NONE, parse_worker
from .hashes import ad_text
from .loop import current_v, log_wait, move, next_action, open_dispatch, review_base, set_aside
from .state import (ASSETS, DELIVER, EDITION, ROOT, SKILL_DIR, agent_file, agent_name, die, ledger, load_cfg, load_st,
                    model_of, outputs_of, rel, save_st, stamp, step_of, vdir)


def image_gen(preset: Path) -> dict:
    import yaml
    ig = (yaml.safe_load(preset.read_text(encoding="utf-8")) or {}).get("image_gen") or {}
    if not (ig.get("codex_model") and ig.get("reasoning")):
        die(f"{rel(preset)}: thiếu image_gen: {{codex_model, reasoning}} (D15.1)")
    return ig


CODEX_TIMEOUT_S, CODEX_TIMEOUT_MIN_S = 900, 300


def codex_timeout(cfg: dict) -> int:
    """D30.20: seconds per `codex exec` call, pipeline.toml [codex] timeout_s; a project made before it gets 900."""
    t = (cfg.get("codex") or {}).get("timeout_s", CODEX_TIMEOUT_S)
    if not isinstance(t, int) or isinstance(t, bool) or t < CODEX_TIMEOUT_MIN_S:
        die(f"pipeline.toml [codex] timeout_s = {t!r}: cần số nguyên ≥ {CODEX_TIMEOUT_MIN_S} giây (D30.20)")
    return t


def pilot_line(prof: dict) -> str:
    """D21.7, D22.10: the pilot package in this runtime's own deliver/, or not_checked while there is no pilot."""
    p = prof.get("pilot_asset")
    return f"PILOT: {rel(DELIVER / p)}/" if p else "PILOT: none (pilot_asset: null): so với pilot ghi not_checked"


def run_line(step, n: int, t: Path, blender: str | None, aid: str) -> str:
    """D36.1: everything fixed for the dispatch; the worker adds `[bl] <tool> <args>` (scripts/run_tool.py)."""
    return "RUN: " + shlex.join([str(SKILL_DIR / "scripts" / "run_tool.py"), *(["--blender", blender] if blender else []),
                                 "--agent", t.parent.name, "--version-dir", rel(vdir(aid, step["id"], n))])


def tools_line(st, step, pf: dict | None, preset: Path, gen: bool = True, extra: list[str] = (),
               cfg: dict | None = None, n: int | None = None) -> list[str]:
    t = SKILL_DIR / "agents" / agent_name(step.get("agent")) / "tools"
    blender = (((pf or {}).get('blender') or {}).get('path') or 'blender') if "blender" in step["uses"] else None
    out = ([f"TOOLS: {t}"] if t.is_dir() else []) + ([f"BLENDER: {blender}"] if blender else []) + (
        [run_line(step, n, t, blender, st['id'])] if t.is_dir() and n is not None else []) + list(extra)
    if gen and "codex_image" in step["uses"]:
        ig = image_gen(preset)
        out += [f"GEN_IMAGE: {SKILL_DIR / 'scripts' / 'gen_image_codex.py'}",
                f"GEN_ARGS: --model {ig['codex_model']} --reasoning {ig['reasoning']} "
                f"--pid-file {rel(ROOT / 'pids' / 'codex_image' / (st['id'] + '.pid'))} "
                f"--timeout {codex_timeout(cfg or {})}" + (" --batch" if step.get("codex_batch") is True else "")]
    return out + [""] if out else []


REVIEW_RESULTS = ("join.json", "unwrap.json")  # model tools write these to final/review/, not to checks/


def unreadable(p: Path) -> bool:
    try:
        json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return False


def failed_checks(vd) -> list[str]:
    """D26.4, D36.4: kit result JSON in final/review/{gates,checks}/ and REVIEW_RESULTS whose overall is fail or error.
    A file that does not parse is an error: a tool killed in the middle of its write must not read as a pass."""
    out = []
    rv = vd / "final" / "review"
    for p in sorted([p for sub in ("gates", "checks") for p in (rv / sub).glob("*.json")]
                    + [rv / n for n in REVIEW_RESULTS if (rv / n).is_file()]):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append(rel(p))
            continue
        if isinstance(r, dict) and (r.get("overall") in ("fail", "error") or r.get("pass") is False):
            out.append(rel(p))
    return out


def brace(paths: list[str]) -> list[str]:
    """The result JSON of one folder under final/review/ as `final/review/checks/{a,b}.json`: the list of required files
    stays short enough for the brief."""
    groups: dict[str, list[str]] = {}
    for o in paths:
        d, _, f = o.rpartition("/")
        if d.startswith("final/review") and f.endswith(".json"):
            groups.setdefault(d, []).append(f[:-5])
    out = [o for o in paths if not (o.endswith(".json") and len(groups.get(o.rpartition("/")[0], ())) > 1)]
    return out + [f"{d}/{{{','.join(fs)}}}.json" for d, fs in groups.items() if len(fs) > 1]


def concept_files(st, step, review: bool = False) -> list[str]:
    from check_card import IMAGE_34, required_files
    d = Path(st["concept_dir"])
    alone = asset_card.views(st) == "none" and not step.get("views_set")
    want = step["review_concept"] if review and step["review_concept"] is not None and not alone else step["concept"]
    want = want and [*want, *(step.get("no_views_concept") or [] if alone else [])]
    names = [x.format(id=st["id"]) for x in want] if want else required_files(st["id"], True)
    names += [IMAGE_34] if step["id"] == "blockout" and (d / IMAGE_34).is_file() else []
    return [x for x in names if not x.endswith(".layout.md") or (d / x).is_file()]


def input_finals(st, ids: list[str]) -> list[tuple[str, Path]]:
    return [(p, vdir(st["id"], p, v) / "final") for p in ids if (v := st["approved"].get(p))]


def handoff_issues(st, prev: str, v: int) -> str | None:
    """D20.3: the ISSUES line of the approved worker report of an input step; None when it hands over nothing."""
    c, _ = parse_worker((vdir(st["id"], prev, v) / "worker-out.md").read_text(encoding="utf-8"))
    issues = c.get("ISSUES", "")
    return None if issues.lower() in NONE else issues


NO_VIEWS = "VIEWS: none"  # the role files say what a step does without a view set


def views_line(st, step) -> list[str]:
    """D35: the views of the card, for a views step; for the other steps only when there is no view set."""
    if step.get("views_set"):
        return [f"VIEWS: {asset_card.views(st)} ({', '.join(asset_card.sides(st))})", ""]
    return [NO_VIEWS, ""] if asset_card.views(st) == "none" else []


def counts_line(st, step) -> list[str]:
    """D30.6: the card counts the ingest compares with the part graph, for a counts_gate step."""
    card = Path(st["concept_dir"]) / "asset-card.yaml" if st.get("concept_dir") else None
    if not (step.get("counts_gate") and card and card.is_file()):
        return []
    import yaml
    from check_counts import lines
    return lines(yaml.safe_load(card.read_text(encoding="utf-8")) or {})


COLORS_NONE = "CONCEPT_COLORS: none (Material Handoff không có Ô lấy màu): tự chọn ô như trước"


def concept_colors_line(st, step) -> list[str]:
    """D43.1: the colours intake measured, for a step that reads or makes the concept colours."""
    if not (step.get("views_set") or step["id"] == texture.STEP):
        return []
    f = ASSETS / st["id"] / "concept_colors.json"
    return [f"CONCEPT_COLORS: {rel(f)}" if f.is_file() else COLORS_NONE]


def camera_fit_file(st) -> Path | None:
    """The fitted concept camera of the approved blockout: fit_view.py writes it to work/, or to final/ with --out."""
    v = (st.get("approved") or {}).get("blockout")
    return next((f for sub in ("final", "work") if v and (f := vdir(st["id"], "blockout", v) / sub / "camera_fit.json").is_file()),
                None)


def card_lines(st, step) -> list[str]:
    """D43: the card fields and measured files a worker would otherwise guess, one line each."""
    card = asset_card.card(st)
    light = card.get("light")
    out = []
    if step["id"] == "blockout" and card.get("view_side"):
        out.append(f"VIEW_SIDE: {card['view_side']}")
    if step["id"] == "model":
        out += [f"LIGHT: from={light['from']} elevation={light['elevation_deg']:g}"] if light else []
        out += [f"CAMERA_FIT: {rel(f)}"] if (f := camera_fit_file(st)) else []
    out += concept_colors_line(st, step)
    return [*out, ""] if out else []


def builds_parts(step) -> bool:
    """D32: a step whose output holds parts_lib.py builds a part graph, so it may use the asset's own functions, and
    its reviewer reads them."""
    return "final/parts_lib.py" in step.get("outputs", [])


def custom_parts_line(st, step) -> list[str]:
    """D32: the one file outside the version folder the worker may write: the asset's `custom` functions."""
    if not builds_parts(step):
        return []
    return [f"CUSTOM_PARTS: {rel(ASSETS / st['id'] / 'custom_parts.py')}", ""]


def pid_line(st, step) -> list[str]:
    if "blender" not in step["uses"]:
        return []
    f = rel(ROOT / "pids" / "blender" / f"{st['id']}.pid")
    return [f"- Mỗi lệnh Blender: `<lệnh> & echo $! > {f}; wait $!; rm -f {f}`."]


def profile_item(step, preset: Path) -> str:
    """The texture tools read the profile themselves from `--profile`, so its worker gets the path and no reason to
    open the file (it holds the path of the env file)."""
    f = rel(ROOT / "PROJECT-PROFILE.yaml")
    if step["id"] == texture.STEP:
        return f"`{f}` — đường dẫn profile dự án. Chỉ truyền cho tool qua `--profile`; không mở file này."
    return f"`{f}` — profile dự án; `{preset}` — preset của profile."


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
        *tools_line(st, step, pf, preset, extra=([pilot_line(prof)] if step["pilot"] else []) + list(extra), cfg=cfg, n=n),
        *views_line(st, step),
        *counts_line(st, step),
        *card_lines(st, step),
        *custom_parts_line(st, step),
        "## Đầu vào (đọc theo thứ tự)",
        f"1. `{rel(a / 'brief.md')}` — yêu cầu gốc của người dùng.",
        f"2. `{rel(a / 'rubric.md')}` mục `## {step['id']}` — tiêu chí chấm; tự check trước khi báo cáo.",
        f"3. `{rel(a / 'feedback.md')}` — đọc mục \"Hiện hành\" và các dòng log gần nhất.",
        f"4. {profile_item(step, preset)}",
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
    notes = []
    for prev in step["inputs"]:
        v = st["approved"].get(prev)
        if v and (ids := [i for i, f in findings.open_of(findings.load(aid, prev, v)).items() if f["kind"] in findings.NOTE]):
            lines.append(f"{k}. Ghi chú còn mở của reviewer `{prev}` v{v}: {', '.join(ids)} trong "
                         f"`{rel(findings.path(aid, prev, v))}` (`note_texture`: TEXTURE NOTE, `note_exception`: NGOẠI LỆ).")
            notes += [f"{prev} v{v} {i}" for i in ids]
            k += 1
    if not fix and (pv := (st.get("prior") or {}).get(step["id"])):
        lines.append(f"{k}. Bản đã duyệt trước của bước này (dựng từ đầu vào cũ): `{rel(vdir(aid, step['id'], pv) / 'final')}/`. "
                     "Giữ phần có đầu vào không đổi, theo file agent.")
        k += 1
    m = st.get("fix_base")
    src = st.get("direct") or m
    if fix and src:
        pd = vdir(aid, step["id"], src)
        bad = failed_checks(pd)
        doc = (findings.load(aid, step["id"], m) if m else None) or {}
        tf = doc.get("top_fix")
        if tf and not (tf := {**tf, "ids": [i for i in tf["ids"] if i not in findings.waived_of(doc)]})["ids"]:
            tf = None
        part = findings.REOPENED_PART.get(tf["kind"]) if tf else None
        outside = (f"{part[0].upper() + part[1:]} đã duyệt ở `{findings.REOPEN[tf['kind']]}`, sửa ngoài bước này: "
                   f"không sửa {part} ở đây." if part else "")
        tf = None if outside else tf
        fp = f"`{rel(findings.path(aid, step['id'], m))}`"
        human = [i for i, f in findings.open_of(doc).items() if i.startswith("H")]
        why = (f"Sửa đúng `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}`; repair, preserve, acceptance của từng id trong "
               f"{fp}. Rồi tới feedback mới nhất của người dùng trong feedback.md."
               if tf else "Lý do phải sửa: feedback mới nhất của người dùng trong feedback.md." + (f" {outside}" if outside else ""))
        if st.get("direct"):
            why = "Lý do phải sửa trước tiên: các JSON check fail ở trên; reviewer chưa chấm bản này. " + why
        if human:
            why = (f"Ưu tiên 1, feedback của người dùng: sửa {', '.join(f'`{i}`' for i in human)} (nguyên văn trong "
                   f"`acceptance` của {fp} và feedback.md). Đối chiếu từng ý với concept; không bỏ ý nào. "
                   + (f"Sau đó: `TOP_FIX: {tf['kind']}: {', '.join(tf['ids'])}` của reviewer." if tf else outside))
        lines += [
            f"{k}. Bản gốc: `{rel(pd)}/` ({'bản vừa dựng, check fail' if st.get('direct') else 'bản tốt nhất'}; "
            "final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
            *([f"{k + 1}. Đọc trước nguyên văn lỗi script của bản gốc: {', '.join(f'`{b}`' for b in bad)}."] if bad else []),
            f"{k + 1 + bool(bad)}. {why}",
            *(f"   - Vùng người dùng khoanh: {x}" for x in findings.mark_lines(doc)),
            "",
            f"Đây là vòng {'trả thẳng ' + str(st['direct_rounds']) if st.get('direct') else 'sửa ' + str(st['fix_round'])}. "
            "Chỉ sửa đúng các điểm trên; giữ nguyên những gì đã đạt.",
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
        req = ", ".join(f"`{o}`" for o in brace(outputs_of(step, st)))
        lines.append(f"- Bắt buộc có (tính từ `{rel(d)}/`): {req}.")
    if step.get("external_command"):
        cmd = step["external_command"].format(
            request=rel(d / "work" / f"{step['id']}_request.md"), vdir=rel(d), log=rel(d / "work" / "external.log")
        )
        lines += ["", "## Lệnh ngoài", "Chạy lệnh, chờ lệnh xong; chỉ xem cuối log khi lỗi:", "```", cmd, "```"]
    lines += [
        "",
        "## Báo cáo",
        f"Ghi báo cáo đầy đủ vào `{rel(d / 'worker-out.md')}`. Các dòng đầu tiên đúng format:",
        "```",
        "STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED",
        f"OUTPUT: {rel(d / 'final')}/",
        f"RUBRIC: <key trong mục ## {step['id']}>=pass|fail; ...",
        "ISSUES: <tối đa 2 vấn đề còn lại, hoặc none>",
        "PROFILE_HASH: <chép dòng PROFILE_HASH ở đầu brief này>",
        *(["FIXED: F<n>, ...   (id bạn cho là đã sửa; reviewer quyết)"] if fix else []),
        *([f"RESOLVED_NOTES: <ghi chú bạn đã làm, trong: {', '.join(notes)}> | none"] if notes else []),
        *([f"ACCEPTED_FAIL: <file JSON> — <lý do có số>; ... | none   (chỉ {', '.join(step['acceptable'])})"]
          if step["acceptable"] else []),
        "```",
        *(["JSON fail trong `final/review/{gates,checks}/` trả thẳng về bạn, không qua reviewer. Không sửa được check "
           "trong ACCEPTED_FAIL: ghi cùng dòng vào mục `## NGOẠI LỆ` của `final/README.md` (tạo mục nếu chưa có)."]
          if step["acceptable"] else []),
        "Tin nhắn trả về cho Producer: chỉ dòng STATUS.",
        "",
        "## Ràng buộc",
        f"- Không hỏi người dùng. Giả định cần thiết ghi vào `{rel(d / 'work' / 'notes.md')}`, rồi làm tiếp.",
        "- Không gọi subagent reviewer; review do Producer sắp xếp.",
        "- Không sửa brief.md, rubric.md, feedback.md, status.json, ledger.md.",
    ]
    return "\n".join(lines) + "\n"


def sheet_of(st, step, n: int, variant: str | None = None) -> Path | None:
    """D31.1: vN/review/sheet[-<variant>].png of the step's `sheet` globs, built at each reviewer brief.
    Outside final/, so the approval hash and the evidence-round hash stay the same. No image, or an unreadable one
    (ledgered): None, and the
    brief points at final/ as before."""
    if not step.get("sheet"):
        return None
    from review_sheet import make
    vd = vdir(st["id"], step["id"], n)
    out = vd / "review" / (f"sheet-{variant}.png" if variant else "sheet.png")
    globs = [g.replace("final/", f"variants/{variant}/", 1) for g in step["sheet"]] if variant else step["sheet"]
    try:
        make(vd, out, globs)
    except ValueError:
        return None
    except OSError as ex:
        ledger(f"{st['id']} · {step['id']} v{n} · không dựng được sheet review, brief trỏ final/ · {ex}")
        return None
    return out


def review_scope(st, sid: str, n: int) -> str:
    """D31.2: `full` for a review with no reviewed base, for the same version judged again, and for a version whose
    worker reports DONE with every open finding of the base in FIXED; `fix` otherwise. An evidence round keeps the scope
    of the review that asked for it."""
    if st.get("evidence"):
        return st.get("review_scope") or "full"
    m = review_base(st, n)
    if m == n or not (base := findings.load(st["id"], sid, m)):
        return "full"
    wr = vdir(st["id"], sid, n) / "worker-out.md"
    c = parse_worker(wr.read_text(encoding="utf-8"))[0] if wr.exists() else {}
    fixed = set(re.findall(r"[FH]\d+", c.get("FIXED", "")))
    return "full" if c.get("STATUS") == "DONE" and set(findings.open_of(base)) <= fixed else "fix"


def review_brief(cfg, st, step, n) -> str:
    aid, sid = st["id"], step["id"]
    step = step | {"regions": asset_card.regions(step, st)}
    d = vdir(aid, sid, n)
    a = ASSETS / aid
    m = review_base(st, n)
    base = findings.load(aid, sid, m)
    op = findings.open_of(base)
    tf = (base or {}).get("top_fix")
    cmp_ids = [] if m == n else findings.compare_ids(base)
    waived = findings.waived_of(base)
    pick = bool(tf and tf["kind"] == "param")
    nxt = (base or {}).get("next_id", 1)
    tie = sorted((k for k in step["top_fix"] if k in findings.TIE_RANK), key=lambda k: -findings.TIE_RANK[k])
    single = [k for k in step["top_fix"] if k in findings.SINGLE]
    notes = [k for k in step["top_fix"] if k in findings.NOTE]
    wr = d / "worker-out.md"
    claimed = parse_worker(wr.read_text(encoding="utf-8"))[0]["RESOLVED_NOTES"] if wr.exists() else []
    scope = st.get("review_scope") or "full"
    sheet = sheet_of(st, step, n)
    msheet = sheet_of(st, step, m) if sheet and base and m != n else None
    lines = [
        f"# Review brief — {st['title']} · bước `{sid}` · v{n}",
        "",
        f"REVIEW_SCOPE: {scope}",
        "",
        "Bạn chấm độc lập. Không sửa file nào ngoài report.",
        "",
        *views_line(st, step),
        "## Chấm cái gì",
        f"- Sheet: `{rel(sheet)}` (nhãn ô = tên ảnh; ảnh lẻ qua need_evidence). Số liệu: JSON trong `final/`, "
        f"`work/` của v{n}." if sheet else
        f"- Output: `{rel(d / 'final')}/` (ảnh preview) và số liệu trong `{rel(d / 'work')}/` nếu có.",
        f"- Báo cáo tự check của worker: `{rel(d / 'worker-out.md')}` — tham khảo, không tin thay bằng chứng.",
        *([f"- Hàm `custom` riêng của asset (code, đọc như bằng chứng; nhãn `custom_parts.py`): `{rel(cp)}`."]
          if builds_parts(step) and (cp := a / "custom_parts.py").is_file() else []),
        f"- Theo: `{rel(a / 'rubric.md')}` mục `## {sid}`, `{rel(a / 'brief.md')}`, mục \"Hiện hành\" trong `{rel(a / 'feedback.md')}`.",
        *([f"- Concept đã duyệt để đối chiếu, trong `{st['concept_dir']}`: chỉ "
           + ", ".join(f"`{x}`" for x in concept_files(st, step, review=True)) + "."] if st.get("concept_dir") else []),
        *(f"- Đầu ra đã duyệt của bước `{p}` (đầu vào, không chấm lại): `{rel(fd)}/`."
          for p, fd in input_finals(st, step["review_inputs"])),
        f"- Profile dự án (`hidden_side_rules`, `scale_refs`): `{rel(ROOT / 'PROJECT-PROFILE.yaml')}`.",
        f"- {ad_text(cfg, {sid, 'review'})}",
        *(f"- Vùng người dùng khoanh, kiểm từng vùng: {x}" for x in findings.mark_lines(base)),
        *([f"- Ghi chú bước trước worker ghi đã làm (RESOLVED_NOTES): {', '.join(claimed)}; region, acceptance trong "
           + ", ".join(f"`{rel(findings.path(aid, s, int(v[1:])))}`" for s, v in dict.fromkeys(
               tuple(x.split()[:2]) for x in claimed)) + "."] if claimed else []),
        *([f"- Chấm lại v{n} với ảnh thêm `{rel(d / 'review' / ('evidence-%d' % st['evidence']['k']))}/`; "
           f"finding đủ trường `{rel(findings.path(aid, sid, n))}`."] if m == n and st.get("evidence") else
          [f"- Chấm lại toàn bộ v{n}, không có bản mới; finding đủ trường `{rel(findings.path(aid, sid, n))}`."]
          if m == n else
          [f"- Bản gốc v{m}: " + (f"sheet `{rel(msheet)}`" if msheet else f"ảnh cùng góc `{rel(vdir(aid, sid, m) / 'final')}/`")
           + "; finding đủ trường "
           f"`{rel(findings.path(aid, sid, m))}`."] if base else []),
        *([f"- Worker khai ACCEPTED_FAIL (check fail không sửa được): {'; '.join(st['accepted']['items'])}. Chấm lý do: "
           "lý do không đứng được thì ghi finding."] if (st.get("accepted") or {}).get("v") == n else []),
        *([f"- Đã waive (người dùng chấp nhận là ngoại lệ): {', '.join(waived)}. Không mở lại, không ghi PRIOR, "
           "không ghi lại thành finding mới."] if waived else []),
        *([f"- Phương án param: `{rel(d / 'variants')}/<a|b|c>/`; a là `final/`"
           + ("; sheet `review/sheet-<b|c>.png` cạnh sheet trên" if sheet and all(
               sheet_of(st, step, n, x) for x in "bc" if (d / "variants" / x).is_dir()) else "")
           + f". Nhãn ảnh trong EVIDENCE_OPENED: `v{n}a/<ảnh>`, `v{n}b/<ảnh>`, `v{n}c/<ảnh>`; ảnh bản gốc: `v{m}/<ảnh>`."]
          if pick else []),
        "",
        "## Báo cáo",
        f"Ghi report vào `{rel(d / 'review-out.md')}`. Report mở đầu đúng format, mỗi khóa một dòng:",
        "```",
        "VERDICT: PASS | FIX | ESCALATE",
        f"RUBRIC: <key trong mục ## {sid}>=pass|fail|unclear{'|not_checked' if scope == 'fix' else ''}; ...",
        f"TOP_FIX: <{'|'.join(findings.top_fix_kinds(step))}>: F<n>[, F<m>]",
        "EVIDENCE_OPENED: <nhãn ảnh và file đã mở>",
        *([f"COMPARE: {'; '.join(f'{i}=?' for i in cmp_ids)}"] if cmp_ids else []),
        *(["PICK: a|b|c"] if pick else []),
        *([f"RESOLVED_CONFIRMED: <mục có bằng chứng trên ảnh, trong RESOLVED_NOTES: {', '.join(claimed)}> | none"]
          if claimed else []),
        "FINDINGS:",
        f"- F{nxt} [blocker|major|minor|preference|unclear] <{'|'.join(step['top_fix'])}>",
        "  region: … | viewing_condition: … | evidence: <nhãn trong EVIDENCE_OPENED> …",
        "  consequence: … | confidence: high|medium|low",
        "  repair: … | preserve: … | acceptance: …",
        *(["PRIOR:", *(f"- {i}: ? | evidence: ? | acceptance: {f['acceptance']}" for i, f in op.items())] if op else []),
        "```",
        f"- FINDINGS chỉ ghi finding mới, id từ F{nxt}, đủ mọi trường; evidence dẫn nhãn trong EVIDENCE_OPENED. "
        "Không có finding mới: `FINDINGS: none`.",
        "- EVIDENCE_OPENED: các nhãn cách nhau bằng dấu phẩy; nhãn không chứa dấu phẩy hay chấm phẩy. `evidence` của "
        "finding mới và của PRIOR resolved chép nguyên văn ít nhất một nhãn đó.",
        *([f"- Loại {', '.join(f'`{k}`' for k in notes)}: mức `minor`."] if notes else []),
        "- Sai số thành phần (cửa, chân bàn, đá) so với concept hoặc `blockout.md`: luôn "
        f"`{next(k for k in step['top_fix'] if k not in findings.NOTE)}`"
        + (f", không phải {', '.join(f'`{k}`' for k in notes)}." if notes else "."),
        "- `preserve`: tên chi tiết cạnh vùng sửa (vd \"nét mực mép mái\"), không ghi \"giữ phần còn lại\".",
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
        "- Không ghi COUNTS. TOP_FIX loại lô" + (f" (không phải {', '.join(single)})" if single else "")
        + ": chỉ ghi loại, script điền id. Mỗi key unclear trong RUBRIC cần một finding unclear.",
        "",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT. " + FALLBACK,
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
        *tools_line(st, step, pf, preset, gen=False, n=n),
        f"Reviewer cần thêm ảnh để chấm {', '.join(tf['ids'])}: đọc region, viewing_condition, evidence, acceptance "
        f"của các id này trong `{rel(findings.path(aid, sid, n))}`.",
        f"- Chỉ render các ảnh đó, ghi vào `{rel(ed)}/`. Không tạo version mới.",
        f"- Không sửa `{rel(vdir(aid, sid, n) / 'final')}/`. Script so hash trước và sau; đổi thì bỏ kết quả vòng này.",
        *pid_line(st, step),
        "",
        "## Báo cáo",
        f"Ghi `{rel(ed / 'worker-out.md')}`, các dòng đầu đúng format:",
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
    if st["state"] == "waiting_human":
        log_wait(st, sid, None, note)
    save_st(st)
    ledger(f"{a.id} · {sid} · {st['state']} trước khi giao: {note}")
    build_outputs(cfg)
    print(f"{a.id}: {sid} → {st['state']} trước khi giao. Tiếp: {next_action(st)}")


def stored_dispatch(st) -> dict | None:
    """C13: the JSON line the open dispatch of this asset went out with; None when no agent is out or the line is lost."""
    from .watch import job
    rec, out = job(st), st.get("dispatch_out")
    return out if rec and out and out.get("brief") == rec.get("brief") else None


def run(a):
    cfg = load_cfg()
    st = load_st(a.id)
    if sent := stored_dispatch(st):
        return print(json.dumps(sent, ensure_ascii=False))
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
    from .limits import DISPATCH, full, slots
    from .state import all_status
    if s in DISPATCH and (busy := full(step, slots(cfg, all_status()))):
        return print(f"{a.id}: chờ slot {', '.join(busy)}, chưa giao")
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
        fix = s == "fix" or (s == "running" and (st.get("fix_round", 0) > 0 or bool(st.get("direct"))))
        hashes.record_inputs(cfg, st, i, n, ph)
        if step["script"]:
            blender = ((pf or {}).get("blender") or {}).get("path") or "blender"
            cmd = [sys.executable, str(SKILL_DIR / "scripts" / step["script"]), "--blender", blender, "--", a.id, str(n),
                   ph]
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
            out = {"role": "worker", "agent": agent_name(step["agent"]), "model": model, "resume": resume,
                   "brief": rel(bp), "report": rel(d / "worker-out.md")}
    elif s in ("evidence", "evidence_running"):
        n = current_v(st, sid)
        ed = vdir(a.id, sid, n) / "review" / f"evidence-{st['evidence']['k']}"
        ed.mkdir(parents=True, exist_ok=True)
        bp = ed / "brief-worker.md"
        bp.write_text(evidence_brief(st, step, n, ed, st["inputs"][sid][f"v{n}"]["profile"], pf, preset), encoding="utf-8")
        out = {"role": "worker", "agent": agent_name(step["agent"]), "model": step.get("model"), "resume": st.get("worker_agent_id"),
               "brief": rel(bp), "report": rel(ed / "worker-out.md")}
    elif s in ("review", "reviewing"):
        n = current_v(st, sid)
        d = vdir(a.id, sid, n)
        if s == "review" or not st.get("review_scope"):
            st["review_scope"] = review_scope(st, sid, n)
        bp = d / "brief-review.md"
        bp.write_text(review_brief(cfg, st, step, n), encoding="utf-8")
        out = {"role": "reviewer", "agent": agent_name(step["reviewer"]), "model": r["reviewer_model"],
               "resume": None, "brief": rel(bp), "report": rel(d / "review-out.md")}
    else:
        die(f"{a.id}: state={s}, không có việc để giao ({next_action(st)})")
    again = s in ("running", "reviewing", "evidence_running") and open_dispatch(st, sid, n, out["role"]) is not None
    if not again:
        set_aside(Path(out["report"]))
    move(st, "dispatch")
    who, due = step["script"], None
    if out["role"] != "script":
        out["model"] = model_of(out["model"])
        if EDITION.get("agent_file"):
            out["agent_file"] = rel(agent_file(out["agent"]))
        st["dispatch_out"] = out
        if not again:
            from .watch import deadline, kind_of
            t0 = stamp()
            rec = {"step": sid, "v": n, "role": out["role"], "model": out["model"], "at": t0, "brief": out["brief"]} | (
                {"scope": st["review_scope"]} if out["role"] == "reviewer" else {})
            mine = [x for x in st.get("dispatches", []) if x.get("step") == sid and x.get("role") == out["role"]]
            due = deadline(cfg, sid, out["role"], t0, kind=kind_of([*mine, rec], rec))
            st.setdefault("dispatches", []).append(rec | ({"deadline": due} if due else {}))
        who = f"{out['agent']}, {out['model'] or 'model của phiên'}"
    save_st(st)
    if not again:
        ledger(f"{a.id} · {sid} v{n} · giao {out['role']} ({who})" + (f" · hạn chót {due}" if due else ""))
    print(json.dumps(out, ensure_ascii=False))
