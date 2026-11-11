"""Merge templates/settings.snippet.json into the project's runtime settings (D30.7). Standard library only: install.py
loads this file by path before any dependency exists, and `P preflight` uses the same check.

The snippet holds two placeholders that the commands of a brief need as absolute paths: <SKILL> (the installed skill
folder, as the TOOLS, MESHY and GEN_IMAGE lines print it) and <BLENDER> (the BLENDER line). Without Blender the
Blender rule is left out. The merge only appends: an allow rule that is missing, a hook whose command no group of that
event runs yet, an `env` key the settings do not set (D33.4: the Bash timeouts). Existing keys and values never change,
so a second run adds nothing and a value the user set stays."""
from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
from pathlib import Path

SKILL, BLENDER = "<SKILL>", "<BLENDER>"
MAC_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def blender_exe() -> str | None:
    """$BLENDER wins, also when it is wrong; then the macOS app; then `blender` on PATH."""
    env = os.environ.get("BLENDER")
    exe = env if env is not None else str(MAC_BLENDER) if MAC_BLENDER.is_file() else shutil.which("blender")
    return exe if exe and os.access(exe, os.X_OK) else None


def wanted(snippet: Path, skill: Path, blender: str | None) -> dict:
    want = json.loads(snippet.read_text(encoding="utf-8"))
    allow = [r for r in want["permissions"]["allow"] if blender or BLENDER not in r]
    want["permissions"]["allow"] = [r.replace(SKILL, str(skill)).replace(BLENDER, blender or "") for r in allow]
    return want


def commands(groups) -> list[str]:
    return [h.get("command") for g in groups or [] if isinstance(g, dict) for h in g.get("hooks") or []
            if isinstance(h, dict)]


def missing(settings: dict, want: dict) -> dict:
    """{"allow": rules not in settings, "hooks": {event: commands not run by any group of that event},
    "env": {key: value the settings do not set}}."""
    have = ((settings.get("permissions") or {}).get("allow")) or []
    hooks = settings.get("hooks") or {}
    out_hooks = {}
    for ev, groups in want.get("hooks", {}).items():
        if gone := [c for c in commands(groups) if c not in commands(hooks.get(ev))]:
            out_hooks[ev] = gone
    env = settings.get("env") or {}
    return {"allow": [r for r in want["permissions"]["allow"] if r not in have], "hooks": out_hooks,
            "env": {k: v for k, v in (want.get("env") or {}).items() if k not in env}}


def merge(settings: dict, want: dict) -> dict:
    out = copy.deepcopy(settings)
    gap = missing(settings, want)
    if gap["allow"]:
        out.setdefault("permissions", {}).setdefault("allow", []).extend(gap["allow"])
    if gap["env"]:
        out.setdefault("env", {}).update(gap["env"])
    for ev, cmds in gap["hooks"].items():
        out.setdefault("hooks", {}).setdefault(ev, []).extend(
            g for g in want["hooks"][ev] if any(c in cmds for c in commands([g])))
    return out


def read(path: Path) -> dict:
    """{} when the file does not exist; ValueError when it is not a settings object a merge can extend."""
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("permissions", {}), dict) or not isinstance(
            (doc.get("permissions") or {}).get("allow", []), list) or not isinstance(doc.get("hooks", {}), dict) or not isinstance(
            doc.get("env", {}), dict):
        raise ValueError("không phải object settings có permissions.allow là list, hooks và env là object")
    return doc


def install(path: Path, snippet: Path, skill: Path, dry_run: bool) -> int:
    """Print the diff, then write unless dry_run. A file that does not parse is never touched."""
    blender = blender_exe()
    try:
        cur = read(path)
    except ValueError as ex:
        print(f"{path}: {ex}. Không ghi settings; sửa file rồi chạy lại.")
        return 2
    new = merge(cur, wanted(snippet, skill, blender))
    if new == cur:
        print(f"{path}: đã đủ rule và hook, không đổi")
        return 0
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    print("".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), str(path), str(path))),
          end="")
    if blender is None:
        print("Không thấy Blender (BLENDER, Blender.app, PATH): chưa thêm rule Blender; cài rồi chạy lại.")
    if dry_run:
        print(f"(thử) không ghi {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    print(f"đã ghi {path}")
    return 0
