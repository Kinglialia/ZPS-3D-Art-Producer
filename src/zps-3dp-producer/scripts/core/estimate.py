"""Time and Meshy credit estimate per batch at intake, and one record per finished asset (D25.I), with the kit estimate.py.
Records live in <project>/.zps-art/estimates.jsonl; under 3 records the kit defaults count."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

from .state import ASSETS, ROOT, SKILL_DIR, ledger

ESTIMATE = SKILL_DIR / "scripts" / "kit" / "tools" / "estimate.py"
METHOD = "self"
RETEXTURE = 10


def project() -> str:
    return str(ROOT.resolve().parent)


def batch_line(n: int, meshy: bool) -> str | None:
    if n <= 0:
        return None
    r = subprocess.run([sys.executable, str(ESTIMATE), "show", "--project", project(), "--json"], capture_output=True,
                       text=True)
    if r.returncode != 0:
        return f"Ước lượng: không chạy được estimate.py ({(r.stderr.strip().splitlines() or ['?'])[-1][:120]})"
    row = json.loads(r.stdout)[METHOD]
    m = row["minutes"]
    span = f"{m[0]:g}–{m[-1]:g} phút mỗi asset" + (f" (trung vị {m[1]:g})" if len(m) == 3 else "")
    src = "mặc định kit" if row["source"] == "default" else f"trung vị project, {row['records']} bản ghi"
    credit = (f"Meshy {n * RETEXTURE} credit cho lô ({n} lần retexture × {RETEXTURE}): người dùng duyệt tổng này một lần"
              if meshy else "không gọi Meshy (profile không có paths.env_file)")
    return f"Ước lượng lô {n} asset: {span} ({src}); {credit}."


def log_asset(st: dict):
    """On DUYỆT 2: minutes since the asset was created, Meshy credits from its budget files, tris of the final GLB."""
    start = dt.datetime.strptime(st["created"], "%Y-%m-%d %H:%M")
    minutes = max(1, round((dt.datetime.now() - start).total_seconds() / 60))
    credits = sum(json.loads(p.read_text(encoding="utf-8"))["used_credits"]
                  for p in (ASSETS / st["id"] / "texture").glob("budget-*.json"))
    n = st["approved"].get("assemble")
    rep = ASSETS / st["id"] / "assemble" / f"v{n}" / "final" / "review" / "compare.json"
    try:
        tris = json.loads(rep.read_text(encoding="utf-8")).get("tris")
    except (OSError, ValueError, AttributeError):
        tris = None
    args = ["log", "--project", project(), "--method", METHOD, "--minutes", str(minutes), "--credits", f"{credits:g}",
            "--asset", st["id"], *(["--tris", str(tris)] if tris else [])]
    r = subprocess.run([sys.executable, str(ESTIMATE), *args], capture_output=True, text=True)
    ledger(f"{st['id']} · estimate.py log {minutes} phút, {credits:g} credit, {tris} tris"
           + ("" if r.returncode == 0 else f" · lỗi: {(r.stderr.strip().splitlines() or ['?'])[-1][:120]}"))
