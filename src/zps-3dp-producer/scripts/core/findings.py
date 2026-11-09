"""Findings per version (`<step>/vN/findings.json`): PRIOR/COMPARE apply, open counts, progress, best version."""
from __future__ import annotations

import json

from .contract import PRIORITIES
from .state import vdir, write_atomic

OPEN = {"open", "regressed"}
BM = ("blocker", "major")
SINGLE = {"structure", "regen_front"}
NOTE = {"note", "note_exception", "note_texture"}
TIE_FIRST = {"structure", "fix_uv_mesh", "regen_front"}
BATCH_PRIO = ("blocker", "major", "minor")
REOPEN = {"regen_front": "views_front"}


def path(aid: str, step: str, n: int):
    return vdir(aid, step, n) / "findings.json"


def load(aid: str, step: str, n: int | None) -> dict | None:
    p = path(aid, step, n) if n else None
    return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None


def save(aid: str, step: str, doc: dict):
    write_atomic(path(aid, step, doc["version"]), json.dumps(doc, ensure_ascii=False, indent=1))


def add_human(aid: str, step: dict, n: int, text: str):
    """D23.1: the user's redo text becomes finding H<k>, major, on the version sent back; the reviewer PRIORs it."""
    doc = load(aid, step["id"], n) or {"version": n, "base": None, "top_fix": None, "pick": None, "next_id": 1,
                                       "findings": {}}
    k = 1 + sum(i.startswith("H") for i in doc["findings"])
    doc["findings"][f"H{k}"] = {
        "priority": "major", "kind": next((t for t in step["top_fix"] if t not in NOTE), "human"), "status": "open",
        "first_v": n, "last_v": n, "region": "theo feedback người dùng", "viewing_condition": "review page",
        "evidence": f"feedback.md: {step['id']} v{n}", "consequence": "người dùng chưa duyệt", "confidence": "high",
        "repair": text, "preserve": "những gì feedback không nhắc", "acceptance": f"đạt yêu cầu của người dùng: {text}"}
    save(aid, step["id"], doc)


def carry(aid: str, f: dict, src: str, dst: dict, m: int) -> str:
    """D22.4: a finding on an earlier step's output joins that step's approved version m as its TOP_FIX."""
    doc = load(aid, dst["id"], m) or {"version": m, "base": None, "top_fix": None, "pick": None, "next_id": 1,
                                      "findings": {}}
    fid, kind = f"F{doc['next_id']}", next(t for t in dst["top_fix"] if t not in NOTE)
    doc["findings"][fid] = f | {"kind": kind, "status": "open", "first_v": m, "last_v": m,
                                "evidence": f"{src}: {f['evidence']}"}
    doc |= {"next_id": doc["next_id"] + 1, "top_fix": {"kind": kind, "ids": [fid]}}
    save(aid, dst["id"], doc)
    return fid


def region_ok(region: str, names: list[str]) -> bool:
    head, sep, _ = region.partition(":")
    return bool(sep) and all(x.strip() in names for x in head.split(","))


def open_of(doc: dict | None) -> dict:
    return {i: f for i, f in (doc or {}).get("findings", {}).items() if f["status"] in OPEN}


def open_counts(doc: dict) -> dict:
    o = open_of(doc).values()
    return {p: sum(f["priority"] == p for f in o) for p in PRIORITIES}


def short(c: dict, keys=PRIORITIES) -> str:
    return " ".join(f"{k}={c[k]}" for k in keys if c[k]) or "0 mở"


def top_fix_kinds(step: dict) -> list[str]:
    return [k for k in step["top_fix"] if k not in NOTE] + ["need_evidence"]


def compare_ids(base: dict | None) -> list[str]:
    tf = (base or {}).get("top_fix")
    if tf and tf["kind"] == "need_evidence":
        return []
    ids = list(tf["ids"]) if tf else []
    return ids + [i for i in open_of(base) if i.startswith("H") and i not in ids]


def apply(base: dict | None, rv: dict, step: dict, n: int) -> tuple[dict, list[str]]:
    errs = []
    fs = {i: dict(f) for i, f in (base or {}).get("findings", {}).items()}
    was = list(open_of(base))
    prior = rv["prior"]
    if miss := [i for i in was if i not in prior]:
        errs.append("PRIOR thiếu " + ", ".join(miss))
    if extra := [i for i in prior if i not in was]:
        errs.append("PRIOR có id không đang mở: " + ", ".join(extra))
    for i in was:
        if i in prior:
            fs[i] |= {"status": prior[i], "last_v": n}
    tf = (base or {}).get("top_fix")
    need = compare_ids(base)
    if miss := [i for i in need if i not in rv["compare"]]:
        errs.append("COMPARE thiếu " + ", ".join(miss))
    for i, c in rv["compare"].items():
        if i not in need:
            errs.append(f"COMPARE {i}: không có trong TOP_FIX vòng trước hay feedback của người dùng")
        elif prior.get(i) == "resolved" and c != "better":
            errs.append(f"{i}: resolved cần COMPARE better")
        elif c == "worse" and prior.get(i) != "regressed":
            errs.append(f"{i}: COMPARE worse thì PRIOR phải là regressed")
    nxt = (base or {}).get("next_id", 1)
    for i, f in rv["findings"].items():
        if i in fs:
            errs.append(f"{i} đã có; finding cũ ghi ở PRIOR")
            continue
        if not i.startswith("F") or int(i[1:]) < nxt:
            errs.append(f"{i}: id mới bắt đầu từ F{nxt}")
            continue
        if f["kind"] not in step["top_fix"]:
            errs.append(f"{i}: loại '{f['kind']}' không có ở bước {step['id']} ({'|'.join(step['top_fix'])})")
        if f["kind"] in NOTE and f["priority"] != "minor":
            errs.append(f"{i}: {f['kind']} chỉ ghi chú, mức phải là minor")
        if (names := step.get("regions")) and f["kind"] not in REOPEN and not region_ok(f.get("region", ""), names):
            errs.append(f"{i}: region phải mở đầu bằng {'|'.join(names)}, vd `{names[0]}: …`")
        fs[i] = {"priority": f["priority"], "kind": f["kind"], "status": "open", "first_v": n, "last_v": n,
                 **{k: v for k, v in f.items() if k not in ("priority", "kind")}}
    doc = {"version": n, "base": base["version"] if base else None, "top_fix": rv["top_fix"], "pick": rv["pick"],
           "next_id": max([nxt - 1] + [int(i[1:]) for i in fs if i.startswith("F")]) + 1, "findings": fs}
    c = open_counts(doc)
    if rv["counts"] != c:
        errs.append("COUNTS phải là " + "; ".join(f"{k}={v}" for k, v in c.items()))
    unclear_keys = sum(v == "unclear" for v in rv["rubric"].values())
    if unclear_keys > c["unclear"]:
        errs.append(f"RUBRIC có {unclear_keys} key unclear nhưng chỉ {c['unclear']} finding unclear đang mở")
    errs += check_top_fix(rv, open_of(doc), step)
    if rv["pick"] and not (tf and tf["kind"] == "param"):
        errs.append("PICK chỉ dùng khi TOP_FIX vòng trước là param")
    return doc, errs


def check_top_fix(rv: dict, op: dict, step: dict) -> list[str]:
    v, t = rv["verdict"], rv["top_fix"]
    bm = {i: f for i, f in op.items() if f["priority"] in BM}
    uc = [i for i, f in op.items() if f["priority"] == "unclear"]
    if v == "PASS" and (bm or uc):
        return [f"PASS nhưng còn {short(open_counts({'findings': op}), BM + ('unclear',))} đang mở"]
    if v != "FIX":
        return ["TOP_FIX chỉ ghi khi FIX"] if t else []
    if not (bm or uc):
        return ["FIX nhưng không còn blocker/major/unclear đang mở"]
    if not t:
        return ["FIX cần TOP_FIX"]
    k, kinds = t["kind"], top_fix_kinds(step)
    if k not in kinds:
        return [f"TOP_FIX '{k}' không dùng ở bước {step['id']} ({'|'.join(kinds)})"]
    errs = []
    if bm:
        rank = {i: (BM[::-1].index(f["priority"]), f["kind"] in TIE_FIRST) for i, f in bm.items()}
        top = max(rank.values())
        exp = sorted({bm[i]["kind"] for i, r in rank.items() if r == top})
        if k == "need_evidence":
            errs.append("need_evidence chỉ dùng khi không còn blocker/major")
        if k not in exp:
            errs.append(f"TOP_FIX phải là loại {'|'.join(exp)}")
    elif k != "need_evidence":
        errs.append("chỉ còn unclear: TOP_FIX phải là need_evidence")
    if errs:
        return errs
    want = uc if k == "need_evidence" else [i for i, f in op.items() if f["kind"] == k and f["priority"] in BATCH_PRIO]
    if k in SINGLE:
        return [] if len(t["ids"]) == 1 and t["ids"][0] in want else [
            f"TOP_FIX {k}: đúng một id trong {', '.join(want)}"]
    return [] if sorted(t["ids"]) == sorted(want) else [f"TOP_FIX {k}: phải đủ {', '.join(want)}"]


def progress(base: dict, doc: dict) -> bool:
    """§7.3: an old blocker/major resolved, and fewer old findings regressed than resolved."""
    old = open_of(base)
    now = {i: doc["findings"][i]["status"] for i in old}
    res = [i for i, s in now.items() if s == "resolved"]
    reg = sum(s == "regressed" for s in now.values())
    return any(old[i]["priority"] in BM for i in res) and reg < len(res)


def best_version(docs: list[dict | None]) -> int | None:
    """§7.5: fewest open blocker+major; a tie goes to the older version."""
    docs = [d for d in docs if d]
    if not docs:
        return None
    return min(docs, key=lambda d: (sum(f["priority"] in BM for f in open_of(d).values()), d["version"]))["version"]
