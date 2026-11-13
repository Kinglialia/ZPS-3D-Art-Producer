"""Worker and reviewer briefs, and `P brief` dispatch."""
from __future__ import annotations

import fnmatch
import json
import re
import shlex
import shutil
import sys
from pathlib import Path

from . import asset_card, findings, hashes, preflight, texture
from .contract import FALLBACK, NONE, parse_worker
from .hashes import ad_text
from .loop import current_v, log_wait, move, next_action, open_dispatch, review_base, set_aside
from .state import (ASSETS, DELIVER, EDITION, ROOT, SKILL_DIR, agent_file, agent_name, die, ledger, load_cfg, load_st,
                    model_of, outputs_of, rel, rule_dir, rule_path, save_st, stamp, step_of, vdir)


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
    return "RUN: " + shlex.join([str(rule_dir(SKILL_DIR) / "scripts" / "run_tool.py"),
                                 *(["--blender", blender] if blender else []),
                                 "--agent", t.parent.name, "--version-dir", rel(vdir(aid, step["id"], n))])


RUN_MODE = ("RUN_MODE: gõ dòng RUN thành cả lệnh, chỉ thêm `[bl] <tool> <tham số>` ở cuối: không gì đứng trước, không dấu "
            "nháy quanh từ đầu, không pipe, không `&&`, không `;`, không `cd`, không chuyển hướng như `2>&1` (run_tool.py "
            "đã ghi log). Sai dạng thì lệnh chạy trong sandbox, nơi Blender chết.")


GEN_MODE = ("GEN_MODE: lệnh GEN_IMAGE không vẽ, chỉ kiểm ảnh. Với từng cặp --prompt/--out: gọi tool ảnh `image_gen` "
            "một lần, `prompt` = nội dung file --prompt (có --size WxH: thêm câu cuối \"Output: <W>x<H> pixels, "
            "<landscape|portrait|square>.\"), `referenced_image_paths` = mọi --image của cặp, ảnh chung trước, đúng thứ "
            "tự; chép PNG tool trả về sang --out; rồi chạy lệnh chỉ với cặp đó (giữ --image, --size chung) trước ảnh "
            "sau. Thoát 3: gen lại file được in, chạy lại lệnh. Thoát 1: dừng, `STATUS: BLOCKED`, chép dòng lỗi vào "
            "`ISSUES`. Tool báo lỗi: chạy lệnh với --tool-error \"<lỗi>\".")


def tools_line(st, step, pf: dict | None, preset: Path, gen: bool = True, extra: list[str] = (),
               cfg: dict | None = None, n: int | None = None) -> list[str]:
    t = SKILL_DIR / "agents" / agent_name(step.get("agent")) / "tools"
    blender = (((pf or {}).get('blender') or {}).get('path') or 'blender') if "blender" in step["uses"] else None
    has_run = t.is_dir() and n is not None
    out = ([f"TOOLS: {t}"] if t.is_dir() else []) + ([f"BLENDER: {blender}"] if blender else []) + (
        [run_line(step, n, t, blender, st['id'])] if has_run else []) + (
        [RUN_MODE] if has_run and blender and EDITION.get("runtime") == "codex" else []) + list(extra)
    if gen and "codex_image" in step["uses"] and EDITION.get("image_gen") == "direct":
        out += [f"GEN_IMAGE: {SKILL_DIR / 'scripts' / 'gen_image_codex.py'}", "GEN_ARGS: --direct", GEN_MODE]
    elif gen and "codex_image" in step["uses"]:
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


def prepare_final(base: Path, new: Path, exclude: list[str]):
    """C24: final/ of a fix round = final/ of its base version minus the paths that match a pattern of `exclude`."""
    for f in sorted(p for p in (base / "final").rglob("*") if p.is_file()):
        r = f.relative_to(base / "final").as_posix()
        if not any(fnmatch.fnmatchcase(r, pat) for pat in exclude):
            (new / "final" / r).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, new / "final" / r)


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


COLORS_NONE = "CONCEPT_COLORS: none (Material Handoff không có Ô lấy màu): tự chọn ô theo file agent"


def concept_colors_line(st, step) -> list[str]:
    """D43.1: the colours intake measured, for a step that reads or makes the concept colours."""
    if not (step.get("views_set") or step["id"] == texture.STEP):
        return []
    f = ASSETS / st["id"] / "concept_colors.json"
    return [f"CONCEPT_COLORS: {rel(f)}" if f.is_file() else COLORS_NONE]


def card_lines(st, step) -> list[str]:
    """D43: the card fields and measured files a worker would otherwise guess, one line each."""
    card = asset_card.card(st)
    light = card.get("light")
    out = []
    if step["id"] == "blockout" and card.get("view_side"):
        out.append(f"VIEW_SIDE: {card['view_side']}")
    if step["id"] == "model":
        out += [f"LIGHT: from={light['from']} elevation={light['elevation_deg']:g}"] if light else []
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


def profile_item(step, preset: Path) -> str:
    """The texture tools read the profile themselves from `--profile`, so its worker gets the path and no reason to
    open the file (it holds the path of the env file)."""
    f = rel(ROOT / "PROJECT-PROFILE.yaml")
    if step["id"] == texture.STEP:
        return f"`{f}` — đường dẫn profile dự án. Chỉ truyền cho tool qua `--profile`; không mở file này."
    return f"`{f}` — profile dự án; `{preset}` — preset của profile."


def worker_brief(cfg, st, step, n, fix: bool, ph: str, pf: dict | None, preset: Path, prof: dict,
                 extra: list[str] = (), why: str | None = None) -> str:
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
        *(["## Lần giao trước", f"Lần giao trước của bạn dừng ở: {why}.",
           "Bạn là phiên đó, làm tiếp. Giữ phần đã làm trong thư mục version; chỉ bổ sung phần thiếu. Không dựng lại cả bước.",
           ""] if why else []),
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
    pv = None if fix else (st.get("prior") or {}).get(step["id"])
    if pv and step["id"] == texture.STEP:
        lines.append(f"{k}. Bản đã duyệt trước của bước này là v{pv}; mesh hoặc UV đã đổi: chỉ đọc "
                     f"`{rel(vdir(aid, step['id'], pv) / 'work' / 'notes.md')}` của bản đó, không chép albedo cũ.")
        k += 1
    elif pv:
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
            why = ("Lý do phải sửa trước tiên: các JSON check fail ở trên; reviewer chưa chấm bản này. " + why if tf else
                   "Lý do phải sửa: các JSON check fail ở trên; reviewer chưa chấm bản này. feedback.md có yêu cầu mới của "
                   "người dùng thì sửa cả yêu cầu đó." + (f" {outside}" if outside else ""))
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
        f"script, log, bản trung gian vào `{rel(d / 'work')}/`."
        + (" `final/` có sẵn, không chép tay." if fix and src and step.get("fix_copy_exclude") else ""),
    ]
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


SUMMARY = "summary.json"
PRIOR_RULE = ("- PRIOR: thay `?` bằng open|resolved|regressed|superseded. resolved chỉ khi thấy bằng chứng cho acceptance, "
              "ghi nhãn ảnh đó vào evidence.")
NOTES_RULE = ("- ESCALATE: thêm dòng `ESCALATE: <lý do; các phương án>`. Ghi chú khác: cuối report, dưới dòng `## Ghi chú`, "
              "không trong FINDINGS hay PRIOR.")
BRIEF_BYTES = 4096  # the budget of a reviewer brief, project and install paths left out; the part legend leaves it when it does not fit


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def checks_of(p: Path) -> dict[str, dict]:
    """The `checks` of a result JSON by name; {} for a missing, unreadable or odd file."""
    doc = read_json(p)
    rows = doc.get("checks") if isinstance(doc, dict) else None
    return {c["check"]: c for c in rows if isinstance(c, dict) and "check" in c} if isinstance(rows, list) else {}


def by_code(checks: dict[str, dict], prefix: str) -> dict:
    """{code: value} of the checks `<prefix><code>`."""
    return {name[len(prefix):]: c.get("value") for name, c in checks.items() if name.startswith(prefix)}


def accepted_names(st, n: int) -> set[str]:
    """Names of the failed JSON that the worker of version n accepted and ingest allowed."""
    acc = st.get("accepted") or {}
    return {i.split(" — ")[0] for i in acc.get("items", [])} if acc.get("v") == n else set()


def rubric_keys(aid: str, sid: str) -> list[str]:
    """The keys of the section `## <step>` in the rubric.md of the asset, in lower case as parse_review reads RUBRIC."""
    try:
        text = (ASSETS / aid / "rubric.md").read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(rf"^## {re.escape(sid)}[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return [k.lower() for k in re.findall(r"^- ([A-Za-z0-9_]+):", m.group(1), re.M)] if m else []


def decide(pairs: list[tuple[str, str]], accepted: set[str]) -> str | None:
    """pairs of (result file, status): `pass` when all pass, `fail` when each file that does not pass failed and the worker
    accepted it, else None, which leaves the key to the reviewer."""
    if pairs and all(s == "pass" for _, s in pairs):
        return "pass"
    bad = {f for f, s in pairs if s != "pass"}
    return "fail" if bad and all(s in ("pass", "fail") for _, s in pairs) and bad <= accepted else None


def density_rule(fr: Path, accepted: set[str]):
    c = checks_of(fr / "checks" / "detail.json").get("detail.vs_pilot")
    v = c.get("value") if c else None
    ok = c and c.get("status") == "info" and isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 2
    return ("pass", "detail.json") if ok else None


def blockout_match_rule(fr: Path, accepted: set[str]):
    detail, qa = checks_of(fr / "checks" / "detail.json"), checks_of(fr / "checks" / "qa_mesh_check.json")
    dims = {n: c for n, c in qa.items() if n.endswith(".dimensions")}
    if not (dims and "detail.bbox" in detail and "detail.fixed_params" in detail):
        return None
    pairs = [("detail.json", detail[k].get("status")) for k in ("detail.bbox", "detail.fixed_params")] + [
        ("qa_mesh_check.json", c.get("status")) for n, c in qa.items() if n.endswith((".dimensions", ".pivot_bottom_center"))]
    v = decide(pairs, accepted)
    return (v, "detail.json, qa_mesh_check.json") if v else None


# Rubric keys a result JSON decides alone. A key that also asks for a look at the renders (texture light, material,
# seams) is not here: its numbers go to the summary and the reviewer judges the key.
PREFILL = {"model": {"density": density_rule, "blockout_match": blockout_match_rule}}


def prefilled(st, step, n: int) -> dict[str, tuple[str, str]]:
    """{rubric key: (value, source)} the script fills for the review of version n. Only a key of the asset rubric, and
    only from a JSON that exists."""
    fr = vdir(st["id"], step["id"], n) / "final" / "review"
    keys, acc = rubric_keys(st["id"], step["id"]), accepted_names(st, n)
    return {k: got for k, rule in PREFILL.get(step["id"], {}).items() if k in keys and (got := rule(fr, acc))}


def prefill_line(pre: dict[str, tuple[str, str]]) -> str:
    return ("- Key script đã điền từ JSON, chép nguyên vào RUBRIC, không chấm lại (report đổi giá trị bị từ chối): "
            + "; ".join(f"{k}={v} ({src})" for k, (v, src) in pre.items()) + ".")


def parts_of(vd: Path, accepted: set[str]) -> list[dict]:
    """One row per part in the order the renders number them (assembly.json index, else the order of the graph)."""
    fd = vd / "final"
    graph, asm = read_json(fd / "part_graph.json"), read_json(fd / "assembly.json")
    if not (isinstance(graph, dict) and isinstance(graph.get("parts"), list)):
        return []
    rows = {r.get("name"): r for r in ((asm or {}).get("data") or {}).get("parts") or [] if isinstance(r, dict)}
    out = []
    for i, p in enumerate(graph["parts"], 1):
        r, name = rows.get(p.get("name"), {}), p.get("name")
        gate = (read_json(fd / "review" / "gates" / f"{name}.json") or {}).get("overall") or "none"
        row = {"n": r.get("index", i), "name": name, "prim": r.get("primitive") or p.get("primitive"),
               "mat": p.get("material"), "tag": p.get("tag"),
               "size": [round(x, 2) for x in r["extents"]] if r.get("extents") else None,
               "gate": None if gate == "pass" else "fail (accepted)" if gate == "fail" and f"{name}.json" in accepted else gate}
        out.append({k: v for k, v in row.items() if v is not None})
    return sorted(out, key=lambda r: r["n"])


def legend_of(parts: list[dict]) -> str:
    return ", ".join(f"{p['n']} {p['name']}" for p in parts)


def blockout_numbers(fr: Path) -> dict:
    counts = {n[len("counts."):]: c.get("threshold") for n, c in checks_of(fr / "checks" / "counts.json").items()}
    prop = read_json(fr / "checks" / "proportion.json")
    ratios = ((prop or {}).get("data") or {}).get("ratios") if isinstance(prop, dict) else None
    marks = by_code(checks_of(fr / "checks" / "proportion.json"), "proportion.mark.")
    layout = read_json(fr / "checks" / "layout.json")
    relief = read_json(fr / "checks" / "markers.json")
    pick = lambda d, k: ((d or {}).get("data") or {}).get(k) if isinstance(d, dict) else None  # noqa: E731
    return {"counts": counts, "proportion": {v: r.get("deviation") for v, r in (ratios or {}).items()}, "marks_off_m": marks,
            "relief_m": pick(relief, "relief"), "size_m": pick(layout, "built")}


def model_numbers(fr: Path) -> dict:
    detail_doc = read_json(fr / "checks" / "detail.json")
    d = (detail_doc or {}).get("data") or {} if isinstance(detail_doc, dict) else {}
    detail, uv, screen = (checks_of(fr / "checks" / f"{f}.json") for f in ("detail", "uv_edge", "qa_screen_tris_check"))
    val = lambda checks, name: (checks.get(name) or {}).get("value")  # noqa: E731
    moved = val(detail, "detail.fixed_params")
    return {"density": {"tris": d.get("tris"), "cap": d.get("cap"), "tris_m2": d.get("tris_per_m2"),
                        "vs_pilot": (d.get("pilot") or {}).get("ratio")},
            "blockout_match": {"bbox_ratio": d.get("bbox_ratio"), "fixed_params_diff": "none" if moved == [] else moved},
            "uv": {"texel_px_m": val(uv, "uv.texel_px_per_m"), "stretch_share": val(uv, "uv.stretch")},
            "screen_tris": {"small_tri_ratio": val(screen, "screen.small_tri_ratio"), "thin": val(screen, "screen.thin_tris")}}


def texture_numbers(fr: Path) -> dict:
    t = checks_of(fr / "checks" / "tex_measure.json")
    val = lambda name: (t.get(name) or {}).get("value")  # noqa: E731
    mirrored = t.get("uv.mirrored_faces") or {}
    return {"light": {"side_spread_L": by_code(t, "light.side_spread_L."), "top_vs_side_L": by_code(t, "light.top_vs_side_L."),
                      "shaded_share": by_code(t, "light.shaded_share."), "highlight_share": by_code(t, "light.highlight_share.")},
            "material": {"dE_concept": by_code(t, "material.dE_concept.")},
            "seams": {"p90_dE": val("seam.p90_dE"), "unpainted_share": val("seam.unpainted_share"),
                      "padding_empty_share": val("seam.padding_empty_share")},
            "mirrored_uv": {"faces": mirrored.get("value"), "note": mirrored.get("note")}}


NUMBERS = {"blockout": blockout_numbers, "model": model_numbers, "texture": texture_numbers}


def drop_empty(x):
    if isinstance(x, dict):
        return {k: v for k, v in ((k, drop_empty(v)) for k, v in x.items()) if v not in (None, {}, [])}
    return x


def write_summary(st, step, n: int) -> Path | None:
    """vN/review/summary.json: per part its number, name, primitive, material, tag, size in metres and gate verdict, then the
    numbers each rubric key needs. A reviewer reads this instead of assembly.json and every gate JSON, which all pass
    because a failed check never reaches the reviewer. None when the step has neither parts nor numbers."""
    vd = vdir(st["id"], step["id"], n)
    parts = parts_of(vd, accepted_names(st, n)) if builds_parts(step) else []
    numbers = drop_empty(NUMBERS[step["id"]](vd / "final" / "review")) if step["id"] in NUMBERS else {}
    if not (parts or numbers):
        return None
    dump = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    body = ([f'"gate":"pass unless a part says otherwise","parts":[\n' + ",\n".join(dump(p) for p in parts) + "\n]"] if parts else []) + (
        [f'"numbers":{dump(numbers)}'] if numbers else [])
    out = vd / "review" / SUMMARY
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("{" + ",\n".join(body) + "}\n", encoding="utf-8")
    return out


def sheet_files(sheet: Path) -> str:
    """The first page of a sheet by path, the further pages by name with "cùng thư mục": they sit in the same folder."""
    from review_sheet import pages
    first, *more = pages(sheet)
    return f"`{rel(first)}`" + (f" và {', '.join(f'`{p.name}`' for p in more)}, cùng thư mục" if more else "")


def sheet_line(sheet: Path, summary: Path | None, n: int) -> tuple[str, str | None]:
    """The bullet that names the sheet pages and where the numbers are, and the same bullet without the part legend
    ("n = name" of the parts_* renders) for a brief that would pass BRIEF_BYTES with it. With a summary the reviewer file
    carries the sheet rules."""
    if not summary:
        return f"- Sheet: {sheet_files(sheet)} (nhãn ô = tên ảnh; ảnh lẻ qua need_evidence). Số liệu: JSON trong `final/`, `work/` của v{n}.", None
    parts = (read_json(summary) or {}).get("parts") or []
    tiles = read_json(sheet.with_suffix(".json")) or {}
    head = f"- Sheet: {sheet_files(sheet)}."
    if not (parts and any(label.startswith("parts_") for label in tiles)):
        return f"{head} Số liệu: `{SUMMARY}` cùng thư mục.", None
    return (f"{head} Số liệu: `{SUMMARY}` cùng thư mục. Số = tên part: {legend_of(parts)}.",
            f"{head} Số liệu và số = tên part (`n`): `{SUMMARY}` cùng thư mục.")


def brief_size(text: str) -> int:
    """Bytes of a brief without the project and install paths, which differ per machine."""
    for p in (ROOT.resolve(), SKILL_DIR.resolve()):
        text = text.replace(str(p), "")
    return len(text.encode())


def review_scope(st, sid: str, n: int) -> str:
    """D31.2, D38.3: `full` for a review with no reviewed base, for the same version judged again, and for a version
    whose worker reports DONE with every open blocker, major and unclear finding of the base in FIXED; `fix` otherwise.
    The fix brief names only the TOP_FIX ids, so an open minor or preference finding must not make the scope `fix`. An
    evidence round keeps the scope of the review that asked for it."""
    if st.get("evidence"):
        return st.get("review_scope") or "full"
    m = review_base(st, n)
    if m == n or not (base := findings.load(st["id"], sid, m)):
        return "full"
    wr = vdir(st["id"], sid, n) / "worker-out.md"
    c = parse_worker(wr.read_text(encoding="utf-8"))[0] if wr.exists() else {}
    fixed = set(re.findall(r"[FH]\d+", c.get("FIXED", "")))
    return "full" if c.get("STATUS") == "DONE" and set(findings.blocking(base)) <= fixed else "fix"


def review_brief(cfg, st, step, n) -> str:
    aid, sid = st["id"], step["id"]
    step = step | {"regions": asset_card.regions(step, st), "sheet": asset_card.sheet(step, st)}
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
    summary = write_summary(st, step, n)
    pre = prefilled(st, step, n)
    sheet_bullet, short_bullet = sheet_line(sheet, summary, n) if sheet else (None, None)
    lines = [
        f"# Review brief — {st['title']} · bước `{sid}` · v{n}",
        "",
        f"REVIEW_SCOPE: {scope}",
        "",
        "Bạn chấm độc lập. Không sửa file nào ngoài report.",
        "",
        *views_line(st, step),
        "## Chấm cái gì",
        sheet_bullet if sheet else
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
          [f"- Bản gốc v{m}: " + (f"sheet {sheet_files(msheet)}" if msheet else f"ảnh cùng góc `{rel(vdir(aid, sid, m) / 'final')}/`")
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
        f"TOP_FIX: <{'|'.join(findings.top_fix_kinds(step))}>[: F<n>[, F<m>]]",
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
        *(prior_block(op) if op else []),
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
        *([f"- region mở đầu bằng {'|'.join(step['regions'])}, vd `{step['regions'][0]}: mép mái`"
           + "".join(f"; `{k}` nói về đầu ra của `{findings.REOPEN[k]}`, không theo luật này" for k in step["top_fix"]
                     if k in findings.REOPEN) + "."] if step["regions"] else []),
        *([PRIOR_RULE] if op else []),
        *([f"- COMPARE: so ảnh cùng góc với v{m}: better|same|worse. resolved cần better; worse thì regressed."]
          if cmp_ids else []),
        "- VERDICT: còn blocker/major → FIX; chỉ còn unclear → FIX với TOP_FIX need_evidence; không còn → PASS; "
        "người dùng phải chọn gu hoặc rubric mâu thuẫn brief → ESCALATE. preference không chặn PASS.",
        "- TOP_FIX chỉ khi FIX: loại của finding nặng nhất" + (f" (cùng mức: {', '.join(tie)} trước)" if tie else "")
        + "; " + "".join(f"{k} " + ("1 id mỗi part, region `<part>: …`" if k == findings.PER_PART else "1 id") + "; "
                          for k in single)
        + "loại lô chỉ ghi loại, script điền mọi finding blocker/major/minor đang mở của loại đó; need_evidence chỉ ghi "
        "loại, script điền mọi finding unclear đang mở. PASS hoặc ESCALATE: `TOP_FIX: none`.",
        "- Không ghi COUNTS. Mỗi key unclear trong RUBRIC cần một finding unclear.",
        NOTES_RULE,
        *([prefill_line(pre)] if pre else []),
        "",
        "Tin nhắn trả về cho Producer: chỉ dòng VERDICT. " + FALLBACK,
    ]
    text = "\n".join(lines) + "\n"
    return text.replace(sheet_bullet, short_bullet) if short_bullet and brief_size(text) > BRIEF_BYTES else text


def prior_block(op: dict) -> list[str]:
    return ["PRIOR:", *(f"- {i}: ? | evidence: ? | acceptance: {f['acceptance']}" for i, f in op.items())]


def resumed_review_brief(st, step, n, ed) -> str:
    """D38.4: the reviewer that asked for images already on disk judges them in the same review of the same version. It
    has read everything else, so the brief names the images and what the report changes: the base is now version n."""
    doc = findings.load(st["id"], step["id"], n)
    lines = [
        f"# Review brief — {st['title']} · bước `{step['id']}` · v{n} · tiếp",
        "",
        f"REVIEW_SCOPE: {st.get('review_scope') or 'full'}",
        "",
        f"Ảnh bạn xin đã có: {', '.join(f'`{rel(p)}`' for p in sorted(ed.glob('*.png')))}.",
        f"Chấm lại v{n} với ảnh này. Report cùng format như lần trước, ghi vào "
        f"`{rel(vdir(st['id'], step['id'], n) / 'review-out.md')}`. Không ghi COMPARE.",
        "```", *prior_block(findings.open_of(doc)), "```",
        PRIOR_RULE,
        f"- FINDINGS: chỉ finding mới, id từ F{doc['next_id']}, hoặc `FINDINGS: none`.",
        "- EVIDENCE_OPENED: thêm tên ảnh mới.",
        NOTES_RULE,
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
        why = st.get("retry_why") if s == "running" and st.get("worker_agent_id") else None
        fix = s == "fix" or (s == "running" and (st.get("fix_round", 0) > 0 or bool(st.get("direct"))))
        if s == "fix" and (base := st.get("direct") or st.get("fix_base")) and step.get("fix_copy_exclude"):
            prepare_final(vdir(a.id, sid, base), d, step["fix_copy_exclude"])
        hashes.record_inputs(cfg, st, i, n, ph)
        if step["script"]:
            blender = ((pf or {}).get("blender") or {}).get("path") or "blender"
            cmd = [str(rule_path(Path(sys.executable), SKILL_DIR)), str(rule_dir(SKILL_DIR) / "scripts" / step["script"]),
                   "--blender", blender, "--", a.id, str(n), ph]
            out = {"role": "script", "command": shlex.join(cmd), "report": rel(d / "report-script.md")}
        else:
            bp = d / "brief-worker.md"
            bp.write_text(worker_brief(cfg, st, step, n, fix, ph, pf, preset, prof, extra, why), encoding="utf-8")
            model = step.get("model")
            resume = None
            if fix and st.get("fix_round", 0) <= r["resume_rounds"] or why:
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
        ev = st.get("evidence") or {}
        resume = ev.pop("agent_id", None) if ev.get("served") else None
        if resume:
            ed = d / "review" / f"evidence-{ev['k']}"
            bp = ed / "brief-review.md"
            bp.write_text(resumed_review_brief(st, step, n, ed), encoding="utf-8")
        else:
            bp = d / "brief-review.md"
            bp.write_text(review_brief(cfg, st, step, n), encoding="utf-8")
        out = {"role": "reviewer", "agent": agent_name(step["reviewer"]),
               "model": step.get("reviewer_model") or r["reviewer_model"],
               "resume": resume, "brief": rel(bp), "report": rel(d / "review-out.md")}
    else:
        die(f"{a.id}: state={s}, không có việc để giao ({next_action(st)})")
    again = s in ("running", "reviewing", "evidence_running") and open_dispatch(st, sid, n, out["role"]) is not None
    if not again:
        set_aside(Path(out["report"]))
    move(st, "dispatch")
    who, due = step["script"], None
    if out["role"] != "script":
        out["model"] = model_of(out["model"])
        if out["role"] == "worker" and EDITION.get("image_gen") == "direct" and "codex_image" in step["uses"]:
            ig = image_gen(preset)
            out |= {"model": ig["codex_model"], "reasoning_effort": ig["reasoning"]}
        if EDITION.get("agent_file"):
            out["agent_file"] = rel(agent_file(out["agent"]))
        st["dispatch_out"] = out
        if not again:
            from .watch import deadline, kind_of
            t0 = stamp()
            rec = {"step": sid, "v": n, "role": out["role"], "model": out["model"], "at": t0, "brief": out["brief"],
                   "report": out["report"]} | (
                {"scope": st["review_scope"]} if out["role"] == "reviewer" else {}) | (
                {"evidence": st["evidence"]["k"]} if out["role"] == "reviewer" and st.get("evidence") else {})
            mine = [x for x in st.get("dispatches", []) if x.get("step") == sid and x.get("role") == out["role"]]
            due = deadline(cfg, sid, out["role"], t0, kind=kind_of([*mine, rec], rec))
            st.setdefault("dispatches", []).append(rec | ({"deadline": due} if due else {}))
        who = f"{out['agent']}, {out['model'] or 'model của phiên'}"
    save_st(st)
    if not again:
        ledger(f"{a.id} · {sid} v{n} · giao {out['role']} ({who})" + (f" · hạn chót {due}" if due else ""))
    print(json.dumps(out, ensure_ascii=False))
