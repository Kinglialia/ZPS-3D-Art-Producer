"""`P preflight` (docs/producer.md §14 1b, D25.C): what this machine can run, cached in production/preflight.json."""
from __future__ import annotations

import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import settings_merge

from .state import (EDITION, ROOT, SKILL_DIR, SUFFIX, codex_link, locked, now, rel, rule_dir, runtime_guard,
                    write_atomic)

OUT = ROOT / "preflight.json"
KIT_SIBLING = SKILL_DIR.parent / f"zps-3d-artist{SUFFIX}" / "tools" / "preflight.py"
SNIPPET = SKILL_DIR / "templates" / "settings.snippet.json"
RULES_FILE = "zps-3dp-" "producer.rules"  # split so build.py does not suffix it: codex_rules.py FILE keeps the bare name


def run(cmd: list[str], timeout: int) -> tuple[int | None, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, repr(ex)


def blender() -> dict | None:
    exe = settings_merge.blender_exe()
    if exe is None:
        return None
    rc, out = run([exe, "--version"], 120)
    m = re.search(r"Blender\s+(\d[\d.]*)", out)
    return {"path": exe, "version": m.group(1)} if rc == 0 and m else None


def codex_cli(path: str | None) -> dict | None:
    """D30.19: the codex-cli version and the `codex exec` flags of gen_image_codex.FLAGS that its help does not list.
    A missing flag makes every gen exit 2, so it turns codex_image off like a missing codex."""
    if path is None:
        return None
    import gen_image_codex
    _, help_text = run([path, "exec", "--help"], 60)
    return {"version": gen_image_codex.cli_version(), "missing_flags": gen_image_codex.missing_flags(help_text)}


def codex_direct(path: str | None) -> dict | None:
    """Edition `image_gen: direct`: the worker draws with its session's image tool, so `codex exec` flags do not count;
    the tool exists when the image_generation row of `codex features list` ends in `true`."""
    if path is None:
        return None
    import gen_image_codex
    _, out = run([path, "features", "list"], 60)
    on = any(c[0] == "image_generation" and c[-1] == "true" for c in map(str.split, out.splitlines()) if c)
    return {"version": gen_image_codex.cli_version(), "image_generation": on}


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
    tmp = ROOT / f".preflight-kit.{os.getpid()}.json"
    rc, _ = run([str(venv if venv.is_file() else sys.executable), str(path), "--out", str(tmp)], 600)
    try:
        r = json.loads(tmp.read_text(encoding="utf-8"))
        tmp.unlink()
    except (OSError, ValueError):
        return {"path": str(path), "overall": "error", "exit": rc}
    return {"path": str(path), "overall": r.get("overall"), "features": (r.get("data") or {}).get("features") or {}}


def settings_gap(b: dict | None) -> dict | None:
    """D30.7, only in an installed edition that ships the snippet: what the project settings (settings.json and
    settings.local.json beside the skills folder) still lack. None when there is nothing to check."""
    if not EDITION or not SNIPPET.is_file():
        return None
    d = SKILL_DIR.parents[1]
    have = {"permissions": {"allow": []}, "hooks": {}, "env": {}}
    for f in (d / "settings.json", d / "settings.local.json"):
        try:
            doc = settings_merge.read(f)
        except (OSError, ValueError):
            continue
        have["permissions"]["allow"] += (doc.get("permissions") or {}).get("allow") or []
        have["env"] |= doc.get("env") or {}
        for ev, groups in (doc.get("hooks") or {}).items():
            have["hooks"].setdefault(ev, []).extend(groups if isinstance(groups, list) else [])
    want = settings_merge.wanted(SNIPPET, SKILL_DIR, b["path"] if b else None)
    return {"file": rel(d / "settings.json"), "missing": settings_merge.missing(have, want)}


def patterns(text: str) -> list[list]:
    """The `pattern` of each prefix_rule that installer/codex_rules.py render() writes."""
    out = []
    for m in re.finditer(r"pattern = (\[.*?\]),\n    decision", text, re.S):
        try:
            out.append(ast.literal_eval(m.group(1)))
        except (ValueError, SyntaxError):
            continue
    return out


def codex_rules(blender: str | None) -> dict | None:
    """Codex edition (D46): Blender runs only through installer/codex_rules.py's rules, so the rules file must hold the
    rule [run_tool.py of the briefs, "--blender", the Blender the briefs print], and a skill path that needs quotes
    needs its link. None in another edition."""
    if EDITION.get("runtime") != "codex":
        return None
    f = Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser() / "rules" / RULES_FILE
    link = None if shlex.quote(str(SKILL_DIR)) == str(SKILL_DIR) else codex_link(SKILL_DIR)
    run_tool = (link or SKILL_DIR) / "scripts" / "run_tool.py"
    try:
        text = f.read_text(encoding="utf-8")
    except OSError:
        text = None
    mine = [p for p in patterns(text or "") if p[:1] == [str(run_tool)]]
    pinned = next((p[2] for p in mine if len(p) == 3 and p[1] == "--blender" and isinstance(p[2], str)), None)
    return {"file": str(f), "present": text is not None, "run_tool": str(run_tool), "names_run_tool": bool(mine),
            "blender": blender, "rule_blender": pinned,
            "link": str(link) if link else None, "link_ok": rule_dir(SKILL_DIR) == link if link else None}


def rules_ok(r: dict | None) -> bool:
    return r is None or (r["names_run_tool"] and r["rule_blender"] == r["blender"] and r["link_ok"] is not False)


def rules_why(r: dict) -> str:
    why = ([f"không có {r['file']}"] if not r["present"] else
           [f"{r['file']} không nêu {r['run_tool']}"] if not r["names_run_tool"] else
           [f"rule run_tool.py trong {r['file']} ghim --blender {r['rule_blender'] or '(không có)'}, brief in "
            f"--blender {r['blender']}"] if r["rule_blender"] != r["blender"] else []) + (
        [f"thiếu link {r['link']} → {SKILL_DIR}"] if r["link_ok"] is False else [])
    return (f"rule Codex chưa cho Blender ra ngoài sandbox ({', '.join(why)}) → từ gốc project chạy "
            f"`python3 installer/codex_rules.py --write --blender {shlex.quote(r['blender'])}` của bản build, rồi "
            "khởi động lại Codex")


def run_preflight(a):
    """The probes run outside the global lock (`blender --version` may take 120 s); only the final write takes it."""
    runtime_guard()
    ROOT.mkdir(parents=True, exist_ok=True)
    b, ef = blender(), env_file()
    codex = shutil.which("codex")
    direct = EDITION.get("image_gen") == "direct"
    cli = codex_direct(codex) if direct else codex_cli(codex)
    k = kit(Path(os.environ["PRODUCER_KIT"]) if os.environ.get("PRODUCER_KIT") else KIT_SIBLING)
    image = cli is not None and (cli["image_generation"] if direct else not cli["missing_flags"])
    rules = codex_rules(b["path"] if b else None)
    feats = {"blender": b is not None and rules_ok(rules), "codex_image": image, "meshy": has_meshy_key(ef)}
    gap = settings_gap(b)
    doc = {"at": now(), "features": feats, "blender": b, "codex": codex, "codex_cli": cli, "env_file": ef, "kit": k} | (
        {"settings": gap} if gap else {}) | ({"codex_rules": rules} if rules else {})
    with locked(create=True):
        write_atomic(OUT, json.dumps(doc, ensure_ascii=False, indent=2))
    on, down = [f for f, v in feats.items() if v], [f for f, v in feats.items() if not v]
    parts = ([f"bật {', '.join(on)}"] if on else []) + ([f"tắt {', '.join(down)}"] if down else [])
    if direct and cli is None:
        parts.append("không thấy `codex` trên PATH: worker không có tool ảnh → cài codex-cli rồi chạy lại `preflight`")
    elif direct and not image:
        parts.append(f"codex-cli {cli['version']} chưa bật feature image_generation (`codex features list`) "
                     "→ bật nó rồi chạy lại `preflight`")
    if cli and cli.get("missing_flags"):
        parts.append(f"codex-cli {cli['version']} thiếu flag {', '.join(cli['missing_flags'])} của `codex exec` "
                     "→ cài codex-cli đã test (0.164.0) rồi chạy lại `preflight`")
    if b is not None and not rules_ok(rules):
        parts.append(rules_why(rules))
    parts.append(f"kit {k['overall']}" if "overall" in k else "không có kit preflight.py")
    if gap and (gap["missing"]["allow"] or gap["missing"]["hooks"] or gap["missing"]["env"]):
        lack = ([f"{len(gap['missing']['allow'])} allow rule"] if gap["missing"]["allow"] else []) + [
            f"hook {ev}" for ev in gap["missing"]["hooks"]] + (
            [f"env {', '.join(gap['missing']['env'])} (Bash timeout, D33.4)"] if gap["missing"]["env"] else [])
        parts.append(f"{gap['file']} thiếu {', '.join(lack)} → chạy lại install.py của bản cài")
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
