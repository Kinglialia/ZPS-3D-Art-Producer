"""`production/policy.yaml`: who approves a `review_human` step; `P approvals set`, `P delegate` (docs/producer.md §4)."""
from __future__ import annotations

from .state import ROOT, TEMPLATES, die, ledger, now, rel, write_atomic

KEYS = ("blockout", "views_rest", "model")
WHO = ("human", "reviewer")
BY = {"human": "người dùng", "policy": "reviewer theo chính sách dự án", "delegate": "reviewer theo ủy quyền"}
HEAD = "# production/policy.yaml — chỉ script ghi (P approvals set, P delegate)\n"


def path():
    return ROOT / "policy.yaml"


def check(pol: dict) -> list[str]:
    ap = pol.get("approvals") or {}
    errs = [f"approvals.{k}: khóa không hợp lệ ({'|'.join(KEYS)})" for k in ap if k not in KEYS]
    errs += [f"approvals.{k}: phải là {'|'.join(WHO)}" for k, v in ap.items() if k in KEYS and v not in WHO]
    errs += [f"delegations: mục sai dạng {d}" for d in pol.get("delegations") or []
             if not isinstance(d, dict) or d.get("step") not in KEYS or not isinstance(d.get("ids"), list)]
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
    guard(a.step, a.who, a.confirm_spend)
    pol = load()
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
