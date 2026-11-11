"""`production/policy.yaml`: who approves a `review_human` step; `P approvals set`, `P delegate` (docs/producer.md §4)."""
from __future__ import annotations

from .state import ROOT, TEMPLATES, die, ledger, now, rel, write_atomic

KEYS = ("blockout", "views_rest", "model")
WHO = ("human", "reviewer")
BOARDS = ("local", "local+remote")
BY = {"human": "người dùng", "producer": "Producer (test_mode)", "policy": "reviewer theo chính sách dự án", "delegate": "reviewer theo ủy quyền"}
DISK_WARN_GB = 20
TEXTURE_DEFAULTS = ("meshy", "paint")
DISPATCH = ("foreground", "background")
WATCH = ("stall_min", "deadline_factor", "max_nudges")
HEAD = ("# production/policy.yaml — chỉ script ghi (P approvals set, P delegate)\n"
        "# texture_default meshy của template: Run 5, 1 asset (Meshy SỬA 15m32s / 2 version; VẼ MỚI Run 4 38m25s / 4 version); tạm, đo lại sau 3–5 asset khác loại (D34.2)\n")


def path():
    return ROOT / "policy.yaml"


def check(pol: dict) -> list[str]:
    ap = pol.get("approvals") or {}
    errs = [f"approvals.{k}: khóa không hợp lệ ({'|'.join(KEYS)})" for k in ap if k not in KEYS]
    errs += [f"approvals.{k}: phải là {'|'.join(WHO)}" for k, v in ap.items() if k in KEYS and v not in WHO]
    errs += [f"delegations: mục sai dạng {d}" for d in pol.get("delegations") or []
             if not isinstance(d, dict) or d.get("step") not in KEYS or not isinstance(d.get("ids"), list)]
    if pol.get("review_board", "local") not in BOARDS:
        errs.append(f"review_board: phải là {'|'.join(BOARDS)}")
    if not isinstance(pol.get("test_mode", False), bool):
        errs.append("test_mode: phải là true|false")
    if pol.get("texture_default") is not None and pol["texture_default"] not in TEXTURE_DEFAULTS:
        errs.append(f"texture_default: phải là {'|'.join(TEXTURE_DEFAULTS)}")
    if pol.get("dispatch", "foreground") not in DISPATCH:
        errs.append(f"dispatch: phải là {'|'.join(DISPATCH)}")
    wt = pol.get("watch")
    if wt is not None and not isinstance(wt, dict):
        errs.append("watch: phải là bảng stall_min, deadline_factor, max_nudges")
    for k, v in (wt or {}).items() if isinstance(wt, dict) else ():
        if k not in WATCH:
            errs.append(f"watch.{k}: khóa không hợp lệ ({'|'.join(WATCH)})")
        elif isinstance(v, bool) or not isinstance(v, int | float) or v < (0 if k == "max_nudges" else 0.01):
            errs.append(f"watch.{k}: phải là số {'≥ 0' if k == 'max_nudges' else '> 0'}")
    w = pol.get("disk_warn_gb", DISK_WARN_GB)
    if isinstance(w, bool) or not isinstance(w, int | float) or w <= 0:
        errs.append("disk_warn_gb: phải là số GB lớn hơn 0")
    return errs


def load() -> dict:
    import yaml
    p = path() if path().exists() else TEMPLATES / "policy.yaml"
    try:
        pol = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as ex:
        die(f"{rel(p)} sai cú pháp YAML: {' '.join(str(ex).split())}")
    if not isinstance(pol, dict):
        die(f"{rel(p)}: phải là bảng `khóa: giá trị`, không phải {type(pol).__name__}")
    if errs := check(pol):
        die(f"{rel(p)}: " + "; ".join(errs))
    return pol


def texture_default(pol: dict) -> str:
    """D30.11, D34.2: the mode `texture-mode auto` takes. A policy.yaml older than the key takes the template's value."""
    import yaml
    return pol.get("texture_default") or yaml.safe_load((TEMPLATES / "policy.yaml").read_text(encoding="utf-8"))[
        "texture_default"]


def template() -> dict:
    import yaml
    return yaml.safe_load((TEMPLATES / "policy.yaml").read_text(encoding="utf-8"))


def watch(pol: dict) -> dict:
    """D33.18: the stall numbers of the project; a key the project lacks takes the template's value."""
    return template()["watch"] | (pol.get("watch") or {})


def dispatch(pol: dict) -> str:
    return pol.get("dispatch") or "foreground"


def save(pol: dict):
    import yaml
    write_atomic(path(), HEAD + yaml.safe_dump(pol, allow_unicode=True, sort_keys=False))


def approver(pol: dict, step: str, aid: str) -> str:
    if any(d["step"] == step and aid in d["ids"] for d in pol.get("delegations") or []):
        return "delegate"
    return "policy" if (pol.get("approvals") or {}).get(step) == "reviewer" else "human"


def guard(step: str, who: str, confirm_spend: bool):
    if step not in KEYS:
        die(f"{step}: khóa không hợp lệ ({'|'.join(KEYS)})")
    if who not in WHO:
        die(f"người duyệt phải là {'|'.join(WHO)}")
    if step == "model" and who == "reviewer" and not confirm_spend:
        die("model: reviewer cần --confirm-spend: bước sau gọi Meshy (tốn credit) trên mesh vừa khóa. Hỏi lại người dùng")


def set_approval(a):
    """`set review_board local|local+remote` and `set test_mode true|false` too: Project Setup and the user write the
    whole policy through this one writer."""
    pol = load()
    if a.step == "review_board":
        a.who in BOARDS or die(f"review_board phải là {'|'.join(BOARDS)}")
        pol["review_board"] = a.who
    elif a.step == "dispatch":
        a.who in DISPATCH or die(f"dispatch phải là {'|'.join(DISPATCH)}")
        pol["dispatch"] = a.who
    elif a.step == "test_mode":
        a.who in ("true", "false") or die("test_mode phải là true|false")
        pol["test_mode"] = a.who == "true"
    else:
        guard(a.step, a.who, a.confirm_spend)
        pol.setdefault("approvals", {})[a.step] = a.who
    save(pol)
    ledger(f"approvals {a.step}={a.who} · by: {a.by}")
    print(f"OK: approvals {a.step}={a.who}")


def delegate(a):
    guard(a.step, "reviewer", a.confirm_spend)
    pol = load()
    pol.setdefault("delegations", []).append({"step": a.step, "ids": list(a.ids), "by": a.by, "at": now()})
    save(pol)
    ledger(f"delegate {a.step} → reviewer: {', '.join(a.ids)} · by: {a.by}")
    print(f"OK: delegate {a.step} → reviewer: {', '.join(a.ids)}")
