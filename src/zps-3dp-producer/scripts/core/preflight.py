"""`P preflight` (docs/producer.md §14 1b, D25.C): what this machine can run, cached in production/preflight.json."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .state import ROOT, SKILL_DIR, now, rel, write_atomic

OUT = ROOT / "preflight.json"
KIT_SIBLING = SKILL_DIR.parent / "zps-3d-artist" / "tools" / "preflight.py"
MAC_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def run(cmd: list[str], timeout: int) -> tuple[int | None, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, repr(ex)


def blender() -> dict | None:
    env = os.environ.get("BLENDER")
    exe = env if env is not None else str(MAC_BLENDER) if MAC_BLENDER.is_file() else shutil.which("blender")
    if not exe or not os.access(exe, os.X_OK):
        return None
    rc, out = run([exe, "--version"], 120)
    m = re.search(r"Blender\s+(\d[\d.]*)", out)
    return {"path": exe, "version": m.group(1)} if rc == 0 and m else None


def env_file() -> str:
    from check_profile import load_yaml
    try:
        prof = load_yaml(ROOT / "PROJECT-PROFILE.yaml") or {}
    except (OSError, ValueError):
        prof = {}
    return ((prof.get("paths") or {}) if isinstance(prof, dict) else {}).get("env_file") or ".env"


def has_meshy_key(path: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    for line in p.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.removeprefix("export ").partition("=")
        if sep and k.strip() == "MESHY_API_KEY" and v.strip().strip("'\""):
            return True
    return False


def kit(path: Path) -> dict:
    if not path.is_file():
        return {"present": False, "tried": [str(path)]}
    venv = path.parent / ".deps" / "venv" / "bin" / "python"
    tmp = ROOT / ".preflight-kit.json"
    rc, _ = run([str(venv if venv.is_file() else sys.executable), str(path), "--out", str(tmp)], 600)
    try:
        r = json.loads(tmp.read_text(encoding="utf-8"))
        tmp.unlink()
    except (OSError, ValueError):
        return {"path": str(path), "overall": "error", "exit": rc}
    return {"path": str(path), "overall": r.get("overall"), "features": (r.get("data") or {}).get("features") or {}}


def run_preflight(a):
    ROOT.mkdir(parents=True, exist_ok=True)
    b, ef = blender(), env_file()
    codex = shutil.which("codex")
    k = kit(Path(a.kit) if a.kit else KIT_SIBLING)
    feats = {"blender": b is not None, "codex_image": codex is not None, "meshy": has_meshy_key(ef)}
    write_atomic(OUT, json.dumps({"at": now(), "features": feats, "blender": b, "codex": codex, "env_file": ef, "kit": k},
                                 ensure_ascii=False, indent=2))
    on, down = [f for f, v in feats.items() if v], [f for f, v in feats.items() if not v]
    parts = ([f"bật {', '.join(on)}"] if on else []) + ([f"tắt {', '.join(down)}"] if down else [])
    parts.append(f"kit {k['overall']}" if "overall" in k else "không có kit preflight.py")
    print(f"preflight: {'; '.join(parts)} → {rel(OUT)}")


def load() -> dict | None:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


OPTIONAL = {"meshy"}


def off(step: dict, pf: dict | None) -> list[str]:
    """Resources of the step that the cached preflight marked off; unknown counts as on. Meshy is optional: without a
    key the texture brief itself paints (no env_file) or blocks (env_file without key), docs/producer.md §6.3."""
    feats = (pf or {}).get("features") or {}
    return [r for r in step["uses"] if r not in OPTIONAL and feats.get(r) is False]
