"""A/B of the two runtimes (producer.md §16, review-board.md §8, D21.10, D25.J, D26.1): the blind pair board, the
user's "Bản nào tốt hơn", the pairwise reviewer asked twice with X/Y swapped, and P compare.

Each runtime keeps its own `production-<runtime>/`. This module reads them as files; anything that needs the
production code of one runtime (cards, decisions) runs `producer.py ab side` with that runtime's PRODUCER_ROOT."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from .contract import FALLBACK, pairs
from .state import (EDITION, IMAGE_EXT, ROOT, RUNTIMES, SKILL_DIR, agent_file, agent_name, die, ledger, load_cfg,
                    model_of, now, rel, write_atomic)

AB = ROOT.parent / "ab"
PORT = 8766
LABELS = ("A", "B")
CHOICES = ("A", "B", "tie")
SAY = {"A": "bản A tốt hơn", "B": "bản B tốt hơn", "tie": "ngang nhau"}
HIDE = re.compile(r"(?i)claude|codex|anthropic|openai|opus|sonnet|haiku|gpt-[\w.-]*|(?:production|deliver)-\w+")
CRITERIA = {
    "concept": "giống concept: khối, tỉ lệ, màu và vật liệu chính",
    "geometry": "hình học: khối rõ, chi tiết đúng chỗ, không lỗi mesh nhìn thấy",
    "texture": "texture: vật liệu, màu, độ chi tiết; không bóng bake, không lỗi ảnh AI",
    "coherence": "texture khớp hình học: ranh giới vật liệu trùng cạnh và khối",
    "game_read": "đọc được ở camera game và ở thumbnail kích thước thật",
}
DUYET = {"model": "DUYỆT 1", "assemble": "DUYỆT 2"}
SERVED = IMAGE_EXT | {".glb"}
PRODUCER = SKILL_DIR / "scripts" / "producer.py"


def root_of(rt: str) -> Path:
    return ROOT.parent / f"production-{rt}"


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def status(rt: str, aid: str) -> dict:
    return read_json(root_of(rt) / "assets" / aid / "status.json", {})


def ids(rt: str) -> set[str]:
    return {p.parent.name for p in (root_of(rt) / "assets").glob("*/status.json")}


def mapping() -> dict:
    """{asset: {"A": runtime, "B": runtime}}; a label once given never changes."""
    m = read_json(AB / "mapping.json", {}).get("assets", {})
    new = sorted(set.intersection(*(ids(rt) for rt in RUNTIMES)) - set(m))
    for aid in new:
        rts = RUNTIMES if secrets.randbelow(2) == 0 else RUNTIMES[::-1]
        m[aid] = dict(zip(LABELS, rts))
    if new:
        write_atomic(AB / "mapping.json", json.dumps({"assets": dict(sorted(m.items()))}, indent=2) + "\n")
    return dict(sorted(m.items()))


def scrub(x):
    """Nothing on the page names a runtime, a model or a runtime folder (review-board.md §8, checklist row 62).
    Asset ids and offer keys stay as they are: the page sends them back."""
    if isinstance(x, str):
        return HIDE.sub("…", x)
    if isinstance(x, list):
        return [scrub(v) for v in x]
    return {k: v if k in ("id", "asset", "key") else scrub(v) for k, v in x.items()} if isinstance(x, dict) else x


def prefs() -> dict:
    """The latest "Bản nào tốt hơn" per asset; an asset nobody picked has no entry (silence is not a choice)."""
    p = AB / "preferences.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
    return {r["asset"]: r["choice"] for r in rows}


def prefer(aid: str, choice: str, text: str = "", by: str = "board") -> str:
    if aid not in mapping():
        die(f"{aid}: không có trong lô so sánh")
    if choice not in CHOICES:
        die(f"lựa chọn phải là {' | '.join(CHOICES)}")
    AB.mkdir(parents=True, exist_ok=True)
    with open(AB / "preferences.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"asset": aid, "choice": choice, "text": text, "by": by, "at": now()}, ensure_ascii=False) + "\n")
    return f"Đã ghi: {aid} · {SAY[choice]}"


def side_call(rt: str, req: dict) -> tuple[bool, dict | str]:
    env = os.environ | {"PRODUCER_ROOT": str(root_of(rt)), "PRODUCER_RUNTIME": rt}
    r = subprocess.run([sys.executable, str(PRODUCER), "ab", "side"], input=json.dumps(req), env=env,
                       capture_output=True, text=True)
    return (True, json.loads(r.stdout)) if r.returncode == 0 else (False, (r.stderr or r.stdout).strip())


def side(_a):
    """Inside one runtime root: `cards` = board cards of the given assets; `act` = one decision from the pair board."""
    from .board import asset_view
    from .loop import act
    from .state import ASSETS, load_st, locked
    req = json.loads(sys.stdin.read())
    cfg = load_cfg()
    if req["op"] == "cards":
        out = {"project": cfg.get("project", {}).get("name", "Producer"),
               "cards": {aid: asset_view(cfg, load_st(aid)) for aid in req["ids"] if (ASSETS / aid / "status.json").exists()}}
    else:
        b = req["body"]
        if not isinstance(b.get("offer", ""), str | None):
            die("offer phải là chuỗi")
        with locked():
            applied, msg = act(b["id"], b["action"], b.get("text", ""), b.get("step"), b.get("regions"), b.get("offer"))
        out = {"applied": applied, "message": msg}
    print(json.dumps(out, ensure_ascii=False))


def relink(card: dict, aid: str, label: str) -> dict:
    """`/p/…`, `/a/…` of one root become `/ab/<asset>/<label>/p/…`: the label, never the runtime, picks the root."""
    def u(x):
        return f"/ab/{quote(aid)}/{label}{x}" if isinstance(x, str) and x.startswith(("/p/", "/a/")) else x
    return card | {"id": f"{aid}~{label}", "header": f"Bản {label} · {card['header']}", "sheet": u(card["sheet"]),
                   "glb": u(card["glb"]), "images": [im | {"u": u(im["u"])} for im in card["images"]]}


def payload() -> dict:
    m = mapping()
    got = {rt: side_call(rt, {"op": "cards", "ids": list(m)}) for rt in RUNTIMES}
    if bad := [v for ok, v in got.values() if not ok]:
        die("; ".join(bad))
    cards = {rt: v["cards"] for rt, (_, v) in got.items()}
    pf = prefs()
    rows = []
    for aid, lab in m.items():
        sides = [relink(cards[lab[L]][aid], aid, L) for L in LABELS if aid in cards[lab[L]]]
        rows.append({"asset": aid, "title": status(lab["A"], aid).get("title", aid), "sides": sides, "prefer": pf.get(aid)})
    return scrub({"project": got[RUNTIMES[0]][1]["project"], "pairs": rows,
                  "empty": "Chưa có asset nào ở cả hai runtime."})


def ab_file(url_path: str) -> Path | None:
    """`/ab/<asset>/<A|B>/p/assets/<asset>/<step>/v<n>/{final,review}/…` or `/ab/<asset>/<A|B>/a/<path under its
    _approved/>`: only the images and GLBs a card links, since the other files of a root name its runtime."""
    parts = unquote(url_path).split("/", 5)
    if len(parts) != 6 or parts[1] != "ab" or parts[4] not in ("p", "a"):
        return None
    _, _, aid, label, key, rest = parts
    rt = mapping().get(aid, {}).get(label)
    if not rt or not rest or rest.startswith("/") or "\0" in rest or ".." in PurePosixPath(rest).parts:
        return None
    root = root_of(rt)
    if key == "a":
        import tomllib
        ap = (tomllib.loads((root / "pipeline.toml").read_text(encoding="utf-8")).get("paths") or {}).get("approved")
        root = Path(os.path.expanduser(ap)) if ap else None
    if root is None:
        return None
    base, f = root.resolve(), (root / rest).resolve()
    if not (f.is_file() and f.is_relative_to(base) and f.suffix.lower() in SERVED):
        return None
    q = f.relative_to(base).parts
    return f if key == "a" or (len(q) > 5 and q[:2] == ("assets", aid) and q[4] in ("final", "review")) else None


def make_server(port: int):
    import mimetypes
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from .board import BOARD_DIR, HOSTS, MAX_BODY

    class Handler(BaseHTTPRequestHandler):
        def send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def reply(self, code: int, msg: str, applied: bool = False):
            self.send(code, json.dumps({"applied": applied, "message": scrub(msg)}, ensure_ascii=False).encode(),
                      "application/json; charset=utf-8")

        def local(self) -> bool:
            if self.headers.get("Host", "").rsplit(":", 1)[0] in HOSTS:
                return True
            self.send_error(403)
            return False

        def do_GET(self):
            if not self.local():
                return
            path = urlsplit(self.path).path
            if path == "/api/board":
                try:
                    body, code = json.dumps(payload(), ensure_ascii=False), 200
                except Exception as ex:  # noqa: BLE001
                    body, code = json.dumps({"message": scrub(f"Lỗi: {ex}")}, ensure_ascii=False), 500
                return self.send(code, body.encode(), "application/json; charset=utf-8")
            if path in ("/", "/index.html", "/board.js"):
                name = "board.js" if path == "/board.js" else "index.html"
                return self.send(200, (BOARD_DIR / name).read_bytes(), mimetypes.guess_type(name)[0] + "; charset=utf-8")
            f = ab_file(path)
            if f is None:
                return self.send_error(404)
            self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        def do_POST(self):
            if not self.local():
                return
            path = urlsplit(self.path).path
            if path not in ("/api/feedback", "/api/prefer"):
                return self.send_error(404)
            if self.headers.get_content_type() != "application/json":
                return self.send_error(403)
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    raise ValueError(f"body lớn hơn {MAX_BODY} byte")
                data = json.loads(self.rfile.read(size))
                if path == "/api/prefer":
                    return self.reply(200, prefer(str(data["asset"]), data["choice"], str(data.get("text") or "")), True)
                aid, _, label = str(data["id"]).rpartition("~")
                rt = mapping().get(aid, {}).get(label) or die(f"{data['id']}: không có trong lô so sánh")
                ok, out = side_call(rt, {"op": "act", "body": data | {"id": aid}})
                if ok:
                    return self.reply(200, out["message"], out["applied"])
                self.reply(400, "Lỗi: " + out.removeprefix("LỖI: "))
            except Exception as ex:  # noqa: BLE001
                self.reply(400, f"Lỗi: {ex}")

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def board(a):
    n = len(mapping())
    srv = make_server(a.port)
    print(f"Trang so A/B: http://127.0.0.1:{a.port}  ({n} asset; Ctrl+C để dừng)")
    srv.serve_forever()


def done(st: dict) -> bool:
    return st.get("state") == "done" and bool((st.get("approved") or {}).get("assemble"))


def order(k: int) -> dict:
    """Ask 1: X = A, Y = B. Ask 2 swaps them (D26.1), so a position bias shows as disagreement, not as a win."""
    return {"X": "A", "Y": "B"} if k == 1 else {"X": "B", "Y": "A"}


def judge_brief(aid: str, d: Path, k: int, lab: dict) -> str:
    base = AB / "judge" / aid
    st = status(lab["A"], aid)
    cd = Path(st["concept_dir"]) if st.get("concept_dir") else None
    for x in ("concept_albedo.png", "concept_shadow.png"):
        if cd and (cd / x).is_file():
            (base / "concept").mkdir(parents=True, exist_ok=True)
            shutil.copy(cd / x, base / "concept" / x)
    for slot, label in order(k).items():
        rt = lab[label]
        s = status(rt, aid)
        final = root_of(rt) / "assets" / aid / "assemble" / f"v{s['approved']['assemble']}" / "final"
        if (d / slot).exists():
            shutil.rmtree(d / slot)
        for p in (p for p in final.rglob("*") if p.suffix.lower() in IMAGE_EXT):
            (d / slot / p.relative_to(final)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, d / slot / p.relative_to(final))
    crit = "\n".join(f"- `{c}`: {t}" for c, t in CRITERIA.items())
    shape = "; ".join(f"{c}=X|Y|tie" for c in CRITERIA)
    return "\n".join([
        f"# So cặp · {aid} · lần {k}/2", "",
        f"Chỉ đọc file trong `{rel(base)}/`. Không mở thư mục nào khác. Không chạy script.", "",
        "## Đầu vào",
        f"- Concept: `{rel(base / 'concept')}/`",
        f"- Bản X: `{rel(d / 'X')}/`",
        f"- Bản Y: `{rel(d / 'Y')}/`",
        "- Hai bản có cùng bộ ảnh, cùng tên file. Mở ảnh cùng tên của X và Y cạnh nhau.", "",
        "## Tiêu chí", crit, "",
        "## Báo cáo",
        f"Ghi vào `{rel(d / 'report.md')}`, đúng hai dòng:",
        "```", f"WINNER: {shape}", "EVIDENCE_OPENED: <ảnh đã mở, cách nhau bằng dấu phẩy>", "```",
        "Chỉ trả về dòng `DONE`.", FALLBACK, ""])


def take(d: Path, k: int, fallback: bool = False) -> dict:
    from .contract import parse_contract, unwrap
    c = parse_contract(unwrap((d / "report.md").read_text(encoding="utf-8")), {"WINNER", "EVIDENCE_OPENED"})
    w = dict(pairs(c.get("WINNER", "")))
    errs = [f"thiếu {x}" for x in CRITERIA if x not in w] + [f"{x}={v} phải là X|Y|tie" for x, v in w.items()
                                                              if x in CRITERIA and v not in ("X", "Y", "tie")]
    errs += [f"tiêu chí lạ {x}" for x in w if x not in CRITERIA] + ([] if c.get("EVIDENCE_OPENED") else ["thiếu EVIDENCE_OPENED"])
    if errs:
        die(f"{rel(d / 'report.md')} sai contract: {'; '.join(errs)}")
    o = order(k)
    res = {"order": k, "winner": {x: o.get(w[x], "tie") for x in CRITERIA}, "at": now(), "fallback": fallback}
    if fallback and ROOT.is_dir():
        ledger(f"{d.parent.name} · ab o{k} · report_fallback · reviewer")
    write_atomic(d / "result.json", json.dumps(res, ensure_ascii=False, indent=2))
    return res


def judge(a):
    """One pairwise ask at a time: ingest a report that is there, else print the next dispatch, else `đủ`."""
    m, waiting = mapping(), []
    for aid, lab in m.items():
        if not all(done(status(rt, aid)) for rt in RUNTIMES):
            waiting.append(aid)
            continue
        for k in (1, 2):
            d = AB / "judge" / aid / f"o{k}"
            if (d / "result.json").exists():
                continue
            if (d / "report.md").exists():
                take(d, k, bool(getattr(a, "fallback", False)))
                continue
            d.mkdir(parents=True, exist_ok=True)
            (d / "brief.md").write_text(judge_brief(aid, d, k, lab), encoding="utf-8")
            generic = load_cfg()["review"]["reviewer_model"] if (ROOT / "pipeline.toml").exists() else "opus"
            out = {"role": "reviewer", "agent": agent_name("check-ab"), "model": model_of(generic), "resume": None,
                   "brief": rel(d / "brief.md"), "report": rel(d / "report.md")}
            if EDITION.get("agent_file"):
                out["agent_file"] = rel(agent_file(out["agent"]))
            print(json.dumps(out, ensure_ascii=False))
            return
    print(f"OK: đủ so cặp ({len(m) - len(waiting)} asset × 2 lần)" + (f"; chưa DUYỆT 2 ở cả hai bên: {', '.join(waiting)}"
                                                                       if waiting else ""))


def pair_result(aid: str) -> dict | None:
    """Per criterion: the label both asks agree on; any disagreement or tie is a tie (D26.1)."""
    rs = [read_json(AB / "judge" / aid / f"o{k}" / "result.json") for k in (1, 2)]
    if not all(rs):
        return None
    return {c: rs[0]["winner"][c] if rs[0]["winner"][c] == rs[1]["winner"][c] else "tie" for c in CRITERIA}


def overall(res: dict) -> str:
    n = Counter(res.values())
    return "A" if n["A"] > n["B"] else "B" if n["B"] > n["A"] else "tie"


def elo(outcomes: list[str], a: str, b: str) -> tuple[int, int]:
    """Two players: the Bradley-Terry rating gap from the score share, ties half, +0.5 each side so one-sided batches
    stay finite. Order-free, unlike sequential Elo updates."""
    s = (outcomes.count(a) + outcomes.count("tie") / 2 + 0.5) / (len(outcomes) + 1)
    d = 400 * math.log10(s / (1 - s))
    return round(1000 + d / 2), round(1000 - d / 2)


def minutes(a: str | None, b: str | None) -> int | None:
    if not (a and b):
        return None
    f = "%Y-%m-%d %H:%M"
    return int((dt.datetime.strptime(b, f) - dt.datetime.strptime(a, f)).total_seconds() // 60)


def first_pass(rt: str, aid: str, step: str) -> bool | None:
    """v1 of a step passed its scripted checks: no fail in final/review/{gates,checks}/*.json; a script step: DONE."""
    v1 = root_of(rt) / "assets" / aid / step / "v1"
    rep = v1 / "report-script.md"
    if rep.exists():
        return bool(re.search(r"^STATUS:\s*DONE\b", rep.read_text(encoding="utf-8"), re.M))
    rs = [read_json(p) for sub in ("gates", "checks") for p in sorted((v1 / "final" / "review" / sub).glob("*.json"))]
    rs = [r for r in rs if isinstance(r, dict)]
    return None if not rs else not any(r.get("overall") in ("fail", "error") or r.get("pass") is False for r in rs)


def metrics(rt: str, aid: str) -> dict:
    st = status(rt, aid)
    log = st.get("offer_log") or []
    first = {s: next((w.get("decision") for w in log if w["step"] == s), "-") for s in DUYET}
    budgets = (root_of(rt) / "assets" / aid / "texture").glob("budget-*.json")
    disp = st.get("dispatches") or []
    tokens = Counter()
    for x in disp:
        if x.get("tokens") is not None:
            tokens[x["model"] or "model của phiên"] += x["tokens"]
    started = {}
    for x in disp:
        started.setdefault(x["step"], x["at"])
    return {
        "rounds": {s: v - 1 for s, v in (st.get("versions") or {}).items()},
        "first": {s: "có" if d == "approve" else "không" if d in ("redo", "paint") else "-" if d == "-" else "chưa quyết"
                  for s, d in first.items()},
        "waits": Counter(w["why"] for w in log),
        "disagree": sum(1 for w in log if w.get("verdict") and (
            (w["verdict"] == "PASS" and w.get("decision") == "redo")
            or (w["verdict"] != "PASS" and w.get("decision") == "approve"))),
        "minutes": minutes(st.get("created"), (st.get("approved_at") or {}).get("assemble")),
        "step_minutes": {s: m for s in started if (m := minutes(started[s], (st.get("approved_at") or {}).get(s))) is not None},
        "meshy": sum((read_json(p, {}) or {}).get("used_credits", 0) for p in budgets),
        "tokens": tokens, "untold": sum(1 for x in disp if x.get("tokens") is None), "dispatches": len(disp),
        "first_pass": {s: r for s in (st.get("versions") or {}) if (r := first_pass(rt, aid, s)) is not None},
    }


def token_text(tok: Counter, untold: int, by_model: bool) -> str:
    if not tok:
        return "không có số"
    body = ", ".join(f"{k} {v}" for k, v in sorted(tok.items())) if by_model else str(sum(tok.values()))
    return body + (f" (thiếu {untold} lần)" if untold else "")


def row(name: str, x: dict, by_model: bool) -> str:
    r = sum(x["rounds"].values())
    detail = ", ".join(f"{s} {v}" for s, v in x["rounds"].items() if v)
    waits = ", ".join(f"{k} {v}" for k, v in sorted(x["waits"].items())) or "0"
    fp = x["first_pass"]
    return (f"| {name} | {r}{f' ({detail})' if detail else ''} | {x['first']['model']} | {x['first']['assemble']} | {waits} "
            f"| {x['disagree']} | {x['minutes'] if x['minutes'] is not None else 'chưa xong'} | {x['meshy']:g} "
            f"| {token_text(x['tokens'], x['untold'], by_model)} | {sum(fp.values())}/{len(fp)} |")


HEAD = ["| Bản | Vòng sửa | DUYỆT 1 lần đầu | DUYỆT 2 lần đầu | Chờ anh (lý do) | Reviewer lệch anh | Phút | Meshy credit "
        "| Token | Script pass v1 |", "|---|---|---|---|---|---|---|---|---|---|"]


def compare(a):
    m = mapping()
    if not m:
        die("chưa có asset nào ở cả hai runtime (production-claude/, production-codex/)")
    pf = prefs()
    if a.reveal and (left := [x for x in m if not (all(done(status(rt, x)) for rt in RUNTIMES) and x in pf)]):
        die(f"chưa mở nhãn: {', '.join(left)} chưa DUYỆT 2 ở cả hai bên hoặc chưa chọn bản tốt hơn")
    data = {aid: {rt: metrics(rt, aid) for rt in RUNTIMES} for aid in m}
    out = [f"# So A/B · {len(m)} asset · {now()}", "",
           "Đếm theo asset; lần thử bị loại có trong vòng sửa; không bấm thì không tính là duyệt."
           + (" Kết quả gộp runtime và model đi kèm." if a.reveal else " Nhãn A/B ẩn; mở bằng `compare --reveal`."), ""]
    agree, judged, outcomes = 0, 0, []
    for aid, lab in m.items():
        out += [f"## {aid}", "", *HEAD]
        out += [row(lab[L] if a.reveal else L, data[aid][lab[L]], a.reveal) for L in LABELS]
        res, pick = pair_result(aid), pf.get(aid)

        def name(L: str, lab=lab) -> str:
            return SAY["tie"] if L == "tie" else lab[L] if a.reveal else L
        out += ["", f"- Anh chọn: {name(pick) if pick else 'chưa chọn'}"]
        if res:
            out.append(f"- Reviewer so cặp (hai lần, đổi thứ tự): {name(overall(res))} · "
                       + ", ".join(f"{c}={name(v)}" for c, v in res.items()))
            outcomes += [lab.get(v, "tie") for v in res.values()]
            if pick:
                judged += 1
                agree += overall(res) == pick
        else:
            out.append("- Reviewer so cặp: chưa so (`ab judge`)")
        out.append("")
    out.append(f"Reviewer so cặp trùng lựa chọn của anh: {agree}/{judged} asset")
    if a.reveal:
        out += ["", "## Theo runtime", ""] + [line for rt in RUNTIMES for line in totals(rt, [data[x][rt] for x in m])]
        r1, r2 = elo(outcomes, *RUNTIMES)
        won = Counter(outcomes)
        out += [f"- Elo reviewer so cặp: {RUNTIMES[0]} {r1}, {RUNTIMES[1]} {r2} "
                f"({won[RUNTIMES[0]]} thắng, {won[RUNTIMES[1]]} thua, {won['tie']} hòa trên {len(outcomes)} tiêu chí)",
                "- Anh chọn: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(m[x].get(pf[x], 'tie') for x in m).items()))]
    text = "\n".join(out) + "\n"
    write_atomic(AB / "compare.md", text)
    print(text, end="")


def totals(rt: str, xs: list[dict]) -> list[str]:
    n = len(xs)
    steps = Counter()
    for x in xs:
        steps.update(x["rounds"])
    waits, tok, untold = Counter(), Counter(), sum(x["untold"] for x in xs)
    for x in xs:
        waits.update(x["waits"])
        tok.update(x["tokens"])
    sm = {}
    for x in xs:
        for s, v in x["step_minutes"].items():
            sm.setdefault(s, []).append(v)
    fp = {}
    for x in xs:
        for s, v in x["first_pass"].items():
            fp.setdefault(s, []).append(v)
    mins = [x["minutes"] for x in xs if x["minutes"] is not None]
    first = {s: sum(1 for x in xs if x["first"][s] == "có") for s in DUYET}
    return [f"**{rt}**",
            "- Vòng sửa theo bước: " + (", ".join(f"{s} {v}" for s, v in steps.items()) or "0"),
            "- Duyệt ngay lần đầu: " + ", ".join(f"{DUYET[s]} {first[s]}/{n} asset" for s in DUYET),
            "- Chờ anh theo lý do: " + (", ".join(f"{k} {v}" for k, v in sorted(waits.items())) or "0"),
            f"- Reviewer lệch anh: {sum(x['disagree'] for x in xs)} lần ở {sum(1 for x in xs if x['disagree'])}/{n} asset",
            "- Phút trung bình mỗi bước: " + (", ".join(f"{s} {round(sum(v) / len(v))}" for s, v in sm.items()) or "không có số")
            + f"; cả asset: {round(sum(mins) / len(mins)) if mins else 'không có số'}",
            f"- Token theo model: {token_text(tok, untold, True)}",
            f"- Meshy: {sum(x['meshy'] for x in xs):g} credit",
            "- Script pass v1: " + (", ".join(f"{s} {sum(v)}/{len(v)}" for s, v in fp.items()) or "không có số"), ""]
