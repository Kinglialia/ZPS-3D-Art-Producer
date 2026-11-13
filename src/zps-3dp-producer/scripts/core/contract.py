"""`KEY: value` report contracts of worker and reviewer (docs/producer.md §6.1, §6.2)."""
from __future__ import annotations

import re
from pathlib import PurePath

WORKER_STATUS = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
VERDICTS = {"PASS", "FIX", "ESCALATE"}
# Kit issue-fields.json minus id, priority, status, which the header line and PRIOR carry.
FIELDS = ("region", "viewing_condition", "evidence", "consequence", "confidence", "repair", "preserve", "acceptance")
PRIORITIES = ("blocker", "major", "minor", "preference", "unclear")
STATUSES = ("open", "resolved", "regressed", "superseded")
COMPARES = ("better", "same", "worse")
CONFIDENCE = ("high", "medium", "low")
RUBRIC_VALUES = ("pass", "fail", "unclear", "not_checked")
PICKS = ("a", "b", "c")
BLOCKS = {"FINDINGS", "PRIOR"}
REVIEW_KEYS = {"VERDICT", "RUBRIC", "COUNTS", "TOP_FIX", "EVIDENCE_OPENED", "COMPARE", "PICK", "RESOLVED_CONFIRMED",
               "ESCALATE"} | BLOCKS
WORKER_KEYS = {"STATUS", "OUTPUT", "RUBRIC", "ISSUES", "PROFILE_HASH", "FIXED", "UNFIXABLE", "RESOLVED_NOTES",
               "ACCEPTED_FAIL"}
NONE = {"", "-", "—", "none"}

KEY = re.compile(r"^\s*(?P<o>\*\*|`)?([A-Za-z_]+)(?P=o)?\s*:\s*(?:(?P=o))?\s*(.*)$")
FID = r"[FH]\d+"
MARK = r"[*`]*"
HEAD = re.compile(rf"^-\s*{MARK}({FID}){MARK}\s*\[(\w+)\]\s*{MARK}(\w*){MARK}(.*)$")
PRIOR = re.compile(rf"^-\s*{MARK}({FID}){MARK}\s*:\s*([^|\s]*)(.*)$")
FIELD = re.compile(rf"^{MARK}({'|'.join(FIELDS)}){MARK}\s*:{MARK}\s*(.*)$", re.I | re.S)
SPLIT = re.compile(rf"\s*\|\s*(?={MARK}(?:{'|'.join(FIELDS)}){MARK}\s*:)", re.I)
PAREN = re.compile(r"\([^)]*\)")
DASH = re.compile(r"\s+[—–-]\s+")
WORD = re.compile(r"[*`_\s]*([A-Za-z_]+)")
CHOICES = re.compile(r"[*`\s]*[|/]")
FALLBACK = "Lệnh ghi file bị chặn: trả cả report giữa dòng `--- report ---` và dòng `--- end ---`."
NOTE_ID = re.compile(r"^\w+ v\d+ [FH]\d+$")
WRAPPED = re.compile(r"^--- report ---[ \t\r]*\n(.*?)^--- end ---[ \t\r]*$", re.M | re.S)


def unwrap(text: str) -> str:
    """D27.5 fallback: an agent whose report write was blocked returns the report between `--- report ---` and
    `--- end ---`, and the Producer saves the whole reply as the report file."""
    m = WRAPPED.search(text)
    return m.group(1) if m else text


def word(s: str) -> str:
    """The first word of a value, lower case, without bold or backticks: `**PASS** (đủ)` is `pass`. A list of choices
    (`PASS | FIX`) is a template line nobody filled, so it has no word."""
    m = WORD.match(s)
    return m.group(1).lower() if m and not CHOICES.match(s[m.end():]) else ""


def parse_contract(text: str, keys: set[str], errs: list[str] | None = None) -> dict:
    """First `KEY: value` of each key; the key may be bold, in backticks or in any case. FINDINGS and PRIOR collect
    their `- ` items and indented lines. An indented line after a one-line key continues its value. An unindented prose
    line, a `##` heading too, ends a block; a finding or PRIOR item after it would be lost, so that is an error. Other
    lines after it are notes. P6-1: `PRIOR: F1=open; F2=open` on the key line gives the items `- F1: open`, and indented
    notes right under `FINDINGS: none` are left out."""
    out, cur, last, lost, quiet = {}, None, None, None, False
    for line in text.splitlines():
        m = KEY.match(line)
        k = m.group(2).upper() if m else None
        if k in keys:
            cur = k if k in BLOCKS and k not in out else None
            last = k if k not in BLOCKS and k not in out else None
            lost = None
            out.setdefault(k, [f"- {i}: {s}" for i, s in re.findall(rf"({FID})\s*=\s*(\w+)", m.group(3))] if k in BLOCKS
                           else m.group(3).strip())
            quiet = bool(cur) and m.group(3).strip().lower() in NONE - {""}
        elif not line.strip():
            continue
        elif cur and quiet and line[:1].isspace():
            continue
        elif cur and (line.startswith("-") or line[:1].isspace()):
            quiet = False
            out[cur].append(line.rstrip())
        elif last and line[:1].isspace():
            out[last] += " " + line.strip()
        else:
            if cur:
                lost = (cur, line.strip())
            elif lost and (HEAD.match(line.strip()) or PRIOR.match(line.strip())):
                if errs is not None:
                    errs.append(f"dòng không thụt lề trong {lost[0]}: '{lost[1][:60]}'; mục sau nó "
                                f"'{line.strip()[:30]}' không được đọc")
                lost = None
            cur = last = None
    return out


def cites(text: str, labels: list[str]) -> bool:
    t = text.lower()
    return any(l.lower() in t or PurePath(l).stem.lower() in t for l in labels)


def pairs(s: str) -> list[tuple[str, str]]:
    return [tuple(x.strip() for x in p.split("=", 1)) if "=" in p else (p.strip(), "") for p in re.split(r"[;,]", s)
            if p.strip()]


def value_pairs(s: str) -> list[tuple[str, str]]:
    """`key=value` pairs where a value is its first word and a note in brackets is dropped: `roof=Pass (ok, tốt)`."""
    return [(k.strip("*` "), word(v) or v.strip("*` ")) for k, v in pairs(PAREN.sub("", s))]


def note_ids(c: dict, key: str, errs: list[str]) -> list[str]:
    """D27.8: `<step> vN F<k>` items of RESOLVED_NOTES (worker) and RESOLVED_CONFIRMED (reviewer)."""
    s = c.get(key, "")
    ids = [] if s.lower() in NONE else [x.strip() for x in s.split(",") if x.strip()]
    errs += [f"{key}: '{x}' phải là <bước> vN F<k>" for x in ids if not NOTE_ID.match(x)]
    return ids


def accepted_fails(s: str, errs: list[str]) -> list[tuple[str, str]]:
    """D31.3 `ACCEPTED_FAIL: <file JSON> — <lý do có số>; ...`, or none."""
    out = []
    for item in ([] if s.lower() in NONE else [x.strip() for x in s.split(";") if x.strip()]):
        m = DASH.search(item)
        f, why = (item[:m.start()].strip(), item[m.end():].strip()) if m else ("", "")
        if f and why:
            out.append((f, why))
        else:
            errs.append(f"ACCEPTED_FAIL: '{item[:60]}' phải là <file JSON> — <lý do có số>")
    return out


def parse_worker(text: str) -> tuple[dict, list[str]]:
    c = parse_contract(text, WORKER_KEYS)
    errs = []
    c["RESOLVED_NOTES"] = note_ids(c, "RESOLVED_NOTES", errs)
    c["ACCEPTED_FAIL"] = accepted_fails(c.get("ACCEPTED_FAIL", ""), errs)
    for k, up in (("STATUS", str.upper), ("UNFIXABLE", str.lower)):
        if k in c:
            c[k] = up(word(c[k])) or c[k]
    if c.get("STATUS") not in WORKER_STATUS:
        errs.append(f"STATUS phải là {'|'.join(sorted(WORKER_STATUS))}")
    if not c.get("PROFILE_HASH"):
        errs.append("thiếu PROFILE_HASH")
    if c.get("UNFIXABLE", "no") not in ("yes", "no"):
        errs.append("UNFIXABLE phải là yes|no")
    return c, errs


def parse_findings(lines: list[str], labels: list[str], errs: list[str]) -> dict:
    out, cur, last = {}, None, None
    for line in lines:
        if line.strip().lstrip("-").strip().lower() in NONE:
            continue
        h = HEAD.match(line)
        if h:
            fid, prio, kind, _ = h.groups()
            prio, last = prio.lower(), None
            cur = out[fid] = {"priority": prio, "kind": kind}
            if prio not in PRIORITIES:
                errs.append(f"{fid}: mức '{prio}' không hợp lệ")
            if not kind:
                errs.append(f"{fid}: thiếu loại")
        elif cur is not None and line[:1].isspace():
            for part in (x.strip() for x in SPLIT.split(line.strip())):
                if f := FIELD.match(part):
                    last = f.group(1).lower()
                    cur[last] = f.group(2).strip()
                elif last:
                    cur[last] = f"{cur[last]} {part}"
                elif part:
                    errs.append(f"dòng FINDINGS sai format: {part[:60]}")
        else:
            errs.append(f"dòng FINDINGS sai format: {line.strip()[:60]}")
    for fid, f in out.items():
        if f.get("confidence"):
            f["confidence"] = word(f["confidence"]) or f["confidence"]
        miss = [k for k in FIELDS if not f.get(k)]
        if miss:
            errs.append(f"{fid} thiếu {', '.join(miss)}")
        if f.get("confidence") and f["confidence"] not in CONFIDENCE:
            errs.append(f"{fid}: confidence phải là {'|'.join(CONFIDENCE)}")
        if f.get("evidence") and not cites(f["evidence"], labels):
            errs.append(f"{fid}: evidence phải dẫn nhãn trong EVIDENCE_OPENED")
    return out


def parse_review(text: str) -> tuple[dict, list[str]]:
    errs = []
    c = parse_contract(text, REVIEW_KEYS, errs)
    errs += [f"thiếu {k}" for k in ("VERDICT", "RUBRIC", "EVIDENCE_OPENED") if not c.get(k)]
    v = c.get("VERDICT")
    v = (word(v).upper() or v) if v else v
    if v and v not in VERDICTS:
        errs.append(f"VERDICT phải là {'|'.join(sorted(VERDICTS))}")
    rubric = {}
    for k, val in value_pairs(c.get("RUBRIC", "")):
        if val in RUBRIC_VALUES:
            rubric[k.lower()] = val
        else:
            errs.append(f"RUBRIC {k}: '{val}' phải là {'|'.join(RUBRIC_VALUES)}")
    counts = None
    cp = {k.lower(): x for k, x in pairs(PAREN.sub("", c.get("COUNTS", "")))}
    if set(cp) == set(PRIORITIES) and all(re.match(r"\d+", x) for x in cp.values()):
        counts = {k: int(re.match(r"\d+", cp[k]).group()) for k in PRIORITIES}
    top_fix = None
    tf = c.get("TOP_FIX", "")
    if tf.lower() not in NONE and word(tf) != "none":
        m = re.match(rf"^{MARK}(\w+){MARK}\s*(?::\s*((?:{FID}\s*,?\s*)+))?", tf)
        if m:
            top_fix = {"kind": m.group(1), "ids": re.findall(FID, m.group(2) or "")}
        else:
            errs.append("TOP_FIX phải là <loại>[: F<n>]")
    labels = [l.strip() for l in re.split(r"[;,]", c.get("EVIDENCE_OPENED", "")) if l.strip()]
    compare = {}
    for k, val in value_pairs(c.get("COMPARE", "")):
        if val in COMPARES:
            compare[k.upper() if re.fullmatch(FID, k, re.I) else k] = val
        else:
            errs.append(f"COMPARE {k}: '{val}' phải là {'|'.join(COMPARES)}")
    pick = c.get("PICK")
    pick = (word(pick) or pick) if pick else None
    if pick and pick not in PICKS:
        errs.append(f"PICK phải là {'|'.join(PICKS)}")
    findings = parse_findings(c.get("FINDINGS", []), labels, errs)
    prior = {}
    items = []
    for line in c.get("PRIOR", []):
        if line[:1].isspace() and items:
            items[-1] += " " + line.strip()
        else:
            items.append(line)
    for line in items:
        m = PRIOR.match(line)
        if not m:
            errs.append(f"dòng PRIOR sai format: {line.strip()[:60]}")
            continue
        fid, raw, rest = m.groups()
        s = word(raw)
        if s not in STATUSES:
            errs.append(f"PRIOR {fid}: '{raw}' phải là {'|'.join(STATUSES)}")
            continue
        ev = re.search(r"\|\s*evidence\s*:\s*([^|]*)", rest, re.I)
        if s == "resolved" and not (ev and cites(ev.group(1), labels)):
            errs.append(f"PRIOR {fid}: resolved cần evidence dẫn nhãn trong EVIDENCE_OPENED")
        prior[fid] = s
    return {"verdict": v, "rubric": rubric, "counts": counts, "counts_text": c.get("COUNTS", ""), "top_fix": top_fix,
            "evidence": labels, "compare": compare, "pick": pick, "findings": findings, "prior": prior,
            "confirmed": note_ids(c, "RESOLVED_CONFIRMED", errs),
            "escalate": None if c.get("ESCALATE", "").lower() in NONE else c["ESCALATE"]}, errs
