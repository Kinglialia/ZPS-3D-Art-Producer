"""Texture step (docs/producer.md §6.3): mode (D30.11), key check, Meshy budget per mesh hash, the two Meshy questions,
texture-stats."""
from __future__ import annotations

import json
from pathlib import Path

from .state import ASSETS, ROOT, SKILL_DIR, all_status, die, ledger, load_st, now, rel, save_st, vdir, write_atomic

STEP = "texture"
MESHY_CALL = SKILL_DIR / "scripts" / "meshy_call.py"
ASK_MESH = "Mesh đổi, texture Meshy cũ mất hiệu lực. Gọi lại Meshy (tốn credit) hay VẼ MỚI?"
ANSWER = "duyệt = gọi Meshy, `meshy {id} paint` = VẼ MỚI"
MESHY, PAINT = "Meshy SỬA", "VẼ MỚI"


def budget_path(aid: str, mesh_sha: str) -> Path:
    return ASSETS / aid / STEP / f"budget-{mesh_sha[:12]}.json"


def read_budget(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write_budget(p: Path, b: dict):
    write_atomic(p, json.dumps({"max_credits": b["max_credits"], "used_credits": b["used_credits"]}, indent=2) + "\n")


def current_budget(st: dict) -> Path | None:
    sha = (st.get("locked") or {}).get("model")
    p = budget_path(st["id"], sha) if sha else None
    return p if p and p.is_file() else None


def env_file(prof: dict) -> str | None:
    return (prof.get("paths") or {}).get("env_file") or None


def gate(st: dict, prof: dict, model_glb: Path, style: Path) -> tuple[str, str] | list[str]:
    """Before every texture worker brief: brief lines, or (event, note) when the asset must stop first (§6.3)."""
    import meshy_call
    aid, sha = st["id"], st["locked"]["model"]
    choice = choice_of(st)
    if choice == "paint":
        return [mode(st, PAINT, "người dùng chọn `texture-mode paint`: không gọi Meshy")]
    if effective(st) == "paint":
        return [mode(st, PAINT, "texture_default paint: không gọi Meshy")]
    if not env_file(prof):
        if choice == "meshy":
            return "stuck", "`texture-mode meshy` cần `paths.env_file` trong profile: thêm, hoặc `texture-mode auto|paint`"
        return [mode(st, PAINT, "profile không có `paths.env_file`: không gọi Meshy")]
    if st.get("paint_for") == sha[:12]:
        return [mode(st, PAINT, "người dùng chọn cho mesh này: không gọi Meshy")]
    try:
        if meshy_call.keys() != "key file":
            return "stuck", "thiếu MESHY_API_KEY trong env_file của profile: người dùng thêm key"
        price = st["meshy_price"] = meshy_call.price(model_glb, style)
    except meshy_call.Refused as ex:
        return "stuck", str(ex)
    p = budget_path(aid, sha)
    if not p.is_file():
        spent = [q.name for q in p.parent.glob("budget-*.json") if q != p and read_budget(q)["used_credits"] > 0]
        write_budget(p, {"max_credits": 0 if spent else price, "used_credits": 0})
        if spent:
            ask(st, "mesh_changed", nxt="todo")
            return "ask_human", f"{ASK_MESH} ({ANSWER.format(id=aid)})"
        ledger(f"{aid} · {STEP} · {p.name}: 1 lần gọi Meshy ({price} credit)")
    b = read_budget(p)
    left = int((b["max_credits"] - b["used_credits"]) // price)
    run = [f"MESHY: {MESHY_CALL}", f"MESHY_ARGS: --asset {aid} --pid-file {rel(ROOT / 'pids' / 'meshy' / f'{aid}.pid')}"]
    done, resume, blocked = paid_calls(st)
    if blocked:
        ask(st, "meshy_blocked", "fix" if st.get("fix_round") else "todo", base=st.get("fix_base"))
        return "ask_human", (f"task Meshy {blocked} chưa xong sau hạn chờ tổng, credit đã trả: gọi Meshy thêm một lần "
                             f"({price} credit) hay VẼ MỚI? ({ANSWER.format(id=aid)})")
    if left <= 0:
        layer = usable_layer(aid, sha)
        if resume:
            m = mode(st, MESHY, "task Meshy đã trả credit, chưa tải xong hoặc chưa kiểm topology")
        elif layer:
            m = mode(st, MESHY, "hết lần gọi: sửa trên lớp Meshy qua topology")
            if not any("topology pass" in line for line in done):
                done.append(f"MESHY_DONE: `{rel(layer)}` topology pass: dùng `base_color.png`, không gọi Meshy")
        elif choice == "meshy":
            return "stuck", ("`texture-mode meshy`: hết budget Meshy cho mesh này và không có lớp Meshy qua topology: "
                             "duyệt thêm lần gọi, hoặc `texture-mode auto|paint`")
        else:
            m = mode(st, PAINT, "hết lần gọi, không có lớp Meshy qua topology")
        return [m, f"MESHY_CALLS: 0 (đã dùng {b['used_credits']}/{b['max_credits']} credit): không gọi Meshy", *done,
                *(run if resume else [])]
    why = "người dùng chọn `texture-mode meshy`" if choice == "meshy" else \
        "texture_default meshy: có key và budget"
    return [mode(st, MESHY, why), *run,
            f"MESHY_CALLS: {left} (giá {price} credit một lần; `{rel(p)}` chỉ script ghi)", *done]


CHOICES = ("auto", "meshy", "paint")


def choice_of(st: dict) -> str:
    return (st.get("texture_choice") or {}).get("mode", "auto")


def effective(st: dict) -> str:
    """meshy | paint: the user's choice, or for `auto` the project's `texture_default` of policy.yaml (D34.2)."""
    from . import policy
    c = choice_of(st)
    return policy.texture_default(policy.load()) if c == "auto" else c


def set_choice(a):
    """`texture-mode <id> auto|meshy|paint`: the user's mode for the texture step; gate() reads it (D30.11)."""
    from .intake import load_profile
    import meshy_call
    st = load_st(a.id)
    if a.mode == "meshy":
        if not env_file(load_profile()):
            die(f"{a.id}: `texture-mode meshy` cần `paths.env_file` trong profile; không có thì chỉ VẼ MỚI")
        try:
            key = meshy_call.keys()
        except meshy_call.Refused as ex:
            die(f"{a.id}: `texture-mode meshy`: {ex}")
        if key != "key file":
            die(f"{a.id}: `texture-mode meshy` cần MESHY_API_KEY trong env_file của profile: người dùng thêm key")
    by = a.by or "người dùng"
    st["texture_choice"] = {"mode": a.mode, "by": by, "at": now()}
    save_st(st)
    ledger(f"{a.id} · {STEP} · texture-mode {a.mode} · bởi {by}")
    print(f"{a.id}: texture-mode {a.mode} (bởi {by}); áp dụng từ brief texture tiếp theo")


def mode(st: dict, which: str, why: str) -> str:
    """D30.11: the brief line of the mode the script chose; the ledger gets it once per change of mode or reason."""
    pick = {"mode": which, "reason": why, "mesh": st["locked"]["model"][:12]}
    if st.get("texture_mode") != pick:
        st["texture_mode"] = pick
        ledger(f"{st['id']} · {STEP} · chế độ {which}: {why}")
    return f"MODE: {which} ({why})"


def usable_layer(aid: str, sha: str) -> Path | None:
    """The newest paid Meshy call of any texture version of this asset whose topology gate passed on this mesh."""
    import meshy_call
    found = []
    for c in (ASSETS / aid / STEP).glob("v*/work/meshy/call-*"):
        t = meshy_call.topology(c)
        if t.get("overall") == "pass" and (t.get("data") or {}).get("locked_sha256") == sha:
            found.append((int(c.parents[2].name[1:]), c.name, c))
    return max(found)[2] if found else None


def paid_calls(st: dict) -> tuple[list[str], bool, str | None]:
    """A worker briefed again on the same version: the Meshy calls it already paid, to reuse instead of losing them.
    The third value is the task id of a call that ended `blocked_total`: it is the user's call, never a rerun."""
    import meshy_call
    if st["state"] != "running":
        return [], False, None
    out, resume, blocked = [], False, None
    for c in sorted((vdir(st["id"], STEP, st["versions"][STEP]) / "work" / "meshy").glob("call-*")):
        topo = meshy_call.topology(c)
        if meshy_call.complete(c) and topo.get("overall") == "pass":
            out.append(f"MESHY_DONE: `{rel(c)}` đã trả credit, topology pass: dùng lại `base_color.png`, không gọi lại "
                       "Meshy")
        elif meshy_call.complete(c) and topo:
            out.append(f"MESHY_DONE: `{rel(c)}` đã trả credit, topology fail (`topology.json`): không dùng lớp này")
        elif meshy_call.complete(c):
            resume = True
            out.append(f"MESHY_DONE: `{rel(c)}` đã trả credit, đã tải đủ, chưa kiểm topology: chạy lại lệnh Meshy với "
                       f"`--out {rel(c)}`; lệnh chỉ kiểm topology, không gọi Meshy, không tốn credit")
        elif (tid := meshy_call.task(c).get("task_id")) and meshy_call.earlier(c).get("status") == "blocked_total":
            blocked = tid
        elif tid:
            resume = True
            out.append(f"MESHY_DONE: `{rel(c)}` task {tid} đã trả credit, chưa có GLB hoặc base_color: chạy lại lệnh "
                       f"Meshy với `--out {rel(c)}`, không tốn thêm credit")
    return out, resume, blocked


def ask(st: dict, kind: str, nxt: str, base: int | None = None, new_round: bool = False):
    p = current_budget(st)
    st["ask"] = {"kind": kind, "budget": p.name if p else None, "next": nxt, "base": base, "new_round": new_round}


def ask_regen(st: dict, n: int, from_review: bool, why: str) -> str | None:
    """`TOP_FIX: meshy_regen` or `UNFIXABLE: yes`: the note for waiting_human, or None when there is no Meshy budget."""
    if not current_budget(st) or st.get("paint_for") == st["locked"]["model"][:12] or effective(st) == "paint":
        return None
    if from_review:
        ask(st, "meshy_regen", "fix", base=n, new_round=True)
    else:
        ask(st, "meshy_regen", "fix" if st.get("fix_round") else "todo", base=st.get("fix_base"))
    return f"{why}: gọi Meshy thêm một lần ({st.get('meshy_price', '?')} credit) hay VẼ MỚI? ({ANSWER.format(id=st['id'])})"


def resolve(st: dict, choice: str, by: str) -> str:
    """The user's answer to st['ask']: `call` adds one call to the budget of the current mesh, `paint` marks VẼ MỚI."""
    from .loop import move
    q = st.pop("ask")
    p = ASSETS / st["id"] / STEP / q["budget"]
    if choice == "call":
        b = read_budget(p)
        price = st.get("meshy_price") or 10
        b["max_credits"] += price
        write_budget(p, b)
        what = f"{q['kind']}: thêm 1 lần gọi Meshy ({price} credit), {p.name} max_credits={b['max_credits']}"
    else:
        st["paint_for"] = p.stem.removeprefix("budget-")
        what = f"{q['kind']}: VẼ MỚI, không gọi Meshy cho mesh {st['paint_for']}"
    move(st, f"answer_{q['next']}")
    if q["new_round"]:
        st["fix_round"] = st.get("fix_round", 0) + 1
    if q["base"] is not None:
        st["fix_base"] = q["base"]
    st["note"] = what
    ledger(f"{st['id']} · {STEP} · {what} · bởi {by}")
    return what


def answer(a):
    from .board import build_outputs
    from .loop import next_action
    from .state import load_cfg
    st = load_st(a.id)
    if not st.get("ask") or st["state"] != "waiting_human":
        die(f"{a.id}: không có câu hỏi Meshy đang chờ (state={st['state']})")
    what = resolve(st, a.choice, f"người dùng: {a.by}" if a.by else "người dùng")
    save_st(st)
    build_outputs(load_cfg())
    print(f"{a.id}: {what} → {st['stage']}/{st['state']}. Tiếp: {next_action(st)}")


def stats(_a):
    """D22.17: proposal against the mode used, from texture_spec.json of each asset's texture version, and Meshy spend
    from the budget files; the ledger gives the extra calls the user approved."""
    rows, calls, credits = [], 0, 0
    for st in all_status():
        n = (st.get("approved") or {}).get(STEP) or (st.get("versions") or {}).get(STEP)
        spec = vdir(st["id"], STEP, n) / "final" / "texture_spec.json" if n else None
        price = st.get("meshy_price") or 10
        for p in (ASSETS / st["id"] / STEP).glob("budget-*.json"):
            used = read_budget(p)["used_credits"]
            credits += used
            calls += int(used // price)
        if spec and spec.is_file():
            s = json.loads(spec.read_text(encoding="utf-8"))
            rows.append((st["id"], s.get("proposed"), s.get("used")))
    p = ROOT / "ledger.md"
    extra = sum("thêm 1 lần gọi Meshy" in l for l in p.read_text(encoding="utf-8").splitlines()) if p.exists() else 0
    off = [f"{i} ({a}→{b})" for i, a, b in rows if a != b]
    print(f"texture-stats: {len(rows)} asset có texture_spec.json; đề xuất khớp chế độ dùng {len(rows) - len(off)}/"
          f"{len(rows)}" + (f" (lệch: {', '.join(off)})" if off else "") + f"; Meshy {calls} lần, {credits:g} credit; "
          f"người dùng duyệt gọi thêm {extra} lần")
