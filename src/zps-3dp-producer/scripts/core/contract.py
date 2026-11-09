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
RUBRIC_VALUES = ("pass", "fail", "unclear")
PICKS = ("a", "b", "c")
BLOCKS = {"FINDINGS", "PRIOR"}
REVIEW_KEYS = {"VERDICT", "RUBRIC", "COUNTS", "TOP_FIX", "EVIDENCE_OPENED", "COMPARE", "PICK"} | BLOCKS
WORKER_KEYS = {"STATUS", "OUTPUT", "RUBRIC", "ISSUES", "PROFILE_HASH", "FIXED"}
NONE = {"", "-", "—", "none"}

KEY = re.compile(r"^\s*([A-Z_]+):\s*(.*)$")
FID = r"[FH]\d+"
HEAD = re.compile(rf"^-\s*({FID})\s*\[(\w+)\]\s*(\S*)\s*$")
PRIOR = re.compile(rf"^-\s*({FID})\s*:\s*([^|\s]*)(.*)$")
SPLIT = re.compile(rf"\s*\|\s*(?=(?:{'|'.join(FIELDS)})\s*:)")


def parse_contract(text: str, keys: set[str]) -> dict:
    """First `KEY: value` of each key; FINDINGS and PRIOR collect their `- ` items and indented lines."""
    out, cur = {}, None
    for line in text.splitlines():
        m = KEY.match(line)
        if m and m.group(1) in keys:
            k = m.group(1)
            cur = k if k in BLOCKS and k not in out else None
            out.setdefault(k, [] if k in BLOCKS else m.group(2).strip())
        elif cur and (line.startswith("-") or line[:1].isspace()):
            if line.strip():
                out[cur].append(line.rstrip())
        elif line.strip():
            cur = None
    return out


def cites(text: str, labels: list[str]) -> bool:
    t = text.lower()
    return any(l.lower() in t or PurePath(l).stem.lower() in t for l in labels)


def pairs(s: str) -> list[tuple[str, str]]:
    return [tuple(x.strip() for x in p.split("=", 1)) if "=" in p else (p.strip(), "") for p in re.split(r"[;,]", s)
            if p.strip()]


def parse_worker(text: str) -> tuple[dict, list[str]]:
    c = parse_contract(text, WORKER_KEYS)
    errs = []
    if c.get("STATUS") not in WORKER_STATUS:
        errs.append(f"STATUS phải là {'|'.join(sorted(WORKER_STATUS))}")
    if not c.get("PROFILE_HASH"):
        errs.append("thiếu PROFILE_HASH")
    return c, errs


def parse_findings(lines: list[str], labels: list[str], errs: list[str]) -> dict:
    out, cur = {}, None
    for line in lines:
        h = HEAD.match(line)
        if h:
            fid, prio, kind = h.groups()
            cur = out[fid] = {"priority": prio, "kind": kind}
            if prio not in PRIORITIES:
                errs.append(f"{fid}: mức '{prio}' không hợp lệ")
            if not kind:
                errs.append(f"{fid}: thiếu loại")
        elif cur is not None and line[:1].isspace():
            for part in SPLIT.split(line.strip()):
                k, _, v = (x.strip() for x in part.partition(":"))
                if k in FIELDS:
                    cur[k] = v
                else:
                    errs.append(f"dòng FINDINGS sai format: {part[:60]}")
        else:
            errs.append(f"dòng FINDINGS sai format: {line.strip()[:60]}")
    for fid, f in out.items():
        miss = [k for k in FIELDS if not f.get(k)]
        if miss:
            errs.append(f"{fid} thiếu {', '.join(miss)}")
        if f.get("confidence") and f["confidence"] not in CONFIDENCE:
            errs.append(f"{fid}: confidence phải là {'|'.join(CONFIDENCE)}")
        if f.get("evidence") and not cites(f["evidence"], labels):
            errs.append(f"{fid}: evidence phải dẫn nhãn trong EVIDENCE_OPENED")
    return out


def parse_review(text: str) -> tuple[dict, list[str]]:
    c = parse_contract(text, REVIEW_KEYS)
    errs = [f"thiếu {k}" for k in ("VERDICT", "RUBRIC", "COUNTS", "EVIDENCE_OPENED") if not c.get(k)]
    v = c.get("VERDICT")
    if v and v not in VERDICTS:
        errs.append(f"VERDICT phải là {'|'.join(sorted(VERDICTS))}")
    rubric = {}
    for k, val in pairs(c.get("RUBRIC", "")):
        if val in RUBRIC_VALUES:
            rubric[k] = val
        else:
            errs.append(f"RUBRIC {k}: '{val}' phải là {'|'.join(RUBRIC_VALUES)}")
    counts = None
    if c.get("COUNTS"):
        cp = dict(pairs(c["COUNTS"]))
        if set(cp) == set(PRIORITIES) and all(x.isdigit() for x in cp.values()):
            counts = {k: int(cp[k]) for k in PRIORITIES}
        else:
            errs.append("COUNTS phải là " + "; ".join(f"{k}=N" for k in PRIORITIES))
    top_fix = None
    if c.get("TOP_FIX", "").lower() not in NONE:
        m = re.match(rf"^(\w+)\s*:\s*((?:{FID}\s*,?\s*)+)$", c["TOP_FIX"])
        if m:
            top_fix = {"kind": m.group(1), "ids": re.findall(FID, m.group(2))}
        else:
            errs.append("TOP_FIX phải là <loại>: F<n>[, F<m>]")
    labels = [l.strip() for l in re.split(r"[;,]", c.get("EVIDENCE_OPENED", "")) if l.strip()]
    compare = {}
    for k, val in pairs(c.get("COMPARE", "")):
        if val in COMPARES:
            compare[k] = val
        else:
            errs.append(f"COMPARE {k}: '{val}' phải là {'|'.join(COMPARES)}")
    pick = c.get("PICK") or None
    if pick and pick not in PICKS:
        errs.append(f"PICK phải là {'|'.join(PICKS)}")
    findings = parse_findings(c.get("FINDINGS", []), labels, errs)
    prior = {}
    for line in c.get("PRIOR", []):
        m = PRIOR.match(line)
        if not m:
            errs.append(f"dòng PRIOR sai format: {line.strip()[:60]}")
            continue
        fid, s, rest = m.groups()
        if s not in STATUSES:
            errs.append(f"PRIOR {fid}: '{s}' phải là {'|'.join(STATUSES)}")
            continue
        ev = re.search(r"\|\s*evidence\s*:\s*([^|]*)", rest)
        if s == "resolved" and not (ev and cites(ev.group(1), labels)):
            errs.append(f"PRIOR {fid}: resolved cần evidence dẫn nhãn trong EVIDENCE_OPENED")
        prior[fid] = s
    return {"verdict": v, "rubric": rubric, "counts": counts, "top_fix": top_fix, "evidence": labels,
            "compare": compare, "pick": pick, "findings": findings, "prior": prior}, errs
