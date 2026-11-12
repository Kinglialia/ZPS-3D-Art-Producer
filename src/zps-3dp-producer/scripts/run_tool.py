#!/usr/bin/env python3
"""D36.1: the one entry for every tool command of a worker.

  run_tool.py [--blender EXE] [--agent NAME] --version-dir DIR [bl] <tool> [tool args...]

The `RUN:` line of a brief holds everything before `[bl] <tool>`. A worker adds the tool name and the tool's own arguments.
The script starts itself on the python of scripts/.deps/venv.
  --version-dir  production/assets/<id>/<step>/vN of the project in the working folder. Logs go to vN/work/logs/, the
                 heartbeat to vN/heartbeat.log.
  --agent NAME   the agent of the step. A relative <tool> is resolved against agents/NAME/tools, the `TOOLS:` line of the
                 brief. A plain tool runs on the python of agents/NAME/tools/.deps/venv. Without it the base is scripts/.
  --blender EXE  only in the brief of a step that uses Blender. It must equal the Blender in production/preflight.json.
                 That guards a mistyped path; a worker who edits that file can still change it. The Codex rule pins the
                 first --blender, and a flag given twice exits 2, so there the pinned Blender is the one that runs.
                 agents/NAME/tools/setup_deps.sh gets it as $BLENDER when agents/NAME/tools/.deps is missing.
  bl             run the tool in Blender: EXE -b --python-exit-code 1 --python <tool> -- <tool args>. It holds the slot file
                 production/pids/blender/<id>-<pid>.pid (the file limits.used counts) while Blender runs.
                 Without it: <python> <tool> <tool args>.
  <tool>         a .py file in scripts/ or agents/*/tools/ of the skill, by absolute path or relative to --agent.
                 Any other path, also through `..` or a symlink, exits 2 and runs nothing.
                 In the Codex edition (runtime.json) only agents/*/tools/ run here, and CODEX_DIRECT never does: the Codex
                 rule runs this script outside the sandbox, so it must not reach producer.py or agent-written code.

Prints one line: `<tool> <pass|fail|error> [path ...]`. fail: a result JSON written during this run has `overall` fail or
error, or `pass` false (core.briefs.failed_checks), and the paths are those JSON. error: the tool exited non-zero and
wrote no such JSON, and the path is its log.
Exit code: 0 pass; 1 fail or error; 2 refused or wrong command."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import heartbeat
import root_guard

SKILL_DIR = Path(__file__).resolve().parents[1]
FLAGS = ("--blender", "--agent", "--version-dir")
USAGE = "usage: run_tool.py [--blender EXE] [--agent NAME] --version-dir DIR [bl] <tool> [tool args]"
AGENT_NAME = re.compile(r"[A-Za-z0-9_-]+")
NOT_IN_DEPS = {".deps", "__pycache__"}
CODEX_DIRECT = ("gen_api.py", "generate_image.py", "meshy_call.py", "gen_image_codex.py",
                "self_build/assembly.py", "self_build/param_fit.py", "tools/custom_mesh.py")


class Refused(Exception):
    pass


def roots(skill: Path) -> list[Path]:
    """scripts/ and agents/*/tools/, each only when the folder is not itself a link out of the skill."""
    return [r for r in [skill / "scripts", *sorted((skill / "agents").glob("*/tools"))] if r.resolve() == r]


def is_codex(skill: Path) -> bool:
    try:
        return json.loads((skill / "runtime.json").read_text(encoding="utf-8")).get("runtime") == "codex"
    except (OSError, ValueError):
        return False


def parse(argv: list[str]) -> tuple[dict, bool, str, list[str]]:
    opts, i = {}, 0
    while i < len(argv) and argv[i].startswith("--"):
        if argv[i] not in FLAGS or i + 1 == len(argv):
            raise Refused(USAGE)
        if argv[i] in opts:
            raise Refused(f"refused {argv[i]}: given twice")
        opts[argv[i]] = argv[i + 1]
        i += 2
    bl = argv[i:i + 1] == ["bl"]
    i += bl
    if "--version-dir" not in opts or i == len(argv) or (bl and "--blender" not in opts):
        raise Refused(USAGE)
    return opts, bl, argv[i], argv[i + 1:]


def tools_dir(agent: str | None, skill: Path) -> Path:
    d = skill / "scripts" if agent is None else skill / "agents" / agent / "tools"
    if (agent is not None and not AGENT_NAME.fullmatch(agent)) or d not in roots(skill):
        raise Refused(f"refused --agent {agent}: not an agent folder of the skill with a tools/ folder")
    return d


def tool_file(raw: str, tools: Path, skill: Path) -> Path:
    p = Path(raw)
    real = (p if p.is_absolute() else tools / p).resolve()
    root = next((r for r in roots(skill) if real.is_relative_to(r)), None)
    if root is None or real.suffix != ".py" or not real.is_file() or NOT_IN_DEPS & set(real.relative_to(root).parts):
        raise Refused(f"refused {raw}: not a .py file in scripts/ or agents/*/tools/ of the skill")
    if is_codex(skill) and (root.name == "scripts" or any(real.as_posix().endswith("/" + x) for x in CODEX_DIRECT)):
        raise Refused(f"refused {raw}: in the Codex edition only agents/*/tools/ run here, except CODEX_DIRECT")
    return real


def version_dir(raw: str) -> Path:
    d = Path(raw).resolve()
    if heartbeat.vdir_of(d) != d or not d.is_dir():
        raise Refused(f"refused --version-dir {raw}: not production/assets/<id>/<step>/vN")
    if not d.is_relative_to(Path(root_guard.MARK).parent.resolve() / "assets"):
        raise Refused(f"refused --version-dir {raw}: not under the production folder of this project")
    return d


def check_blender(exe: str):
    from core import preflight
    want = ((preflight.load() or {}).get("blender") or {}).get("path") or "blender"
    if exe != want:
        raise Refused(f"refused --blender {exe}: not the Blender of production/preflight.json")


def write_log(vd: Path, stem: str, p: subprocess.CompletedProcess) -> Path:
    f = vd / "work" / "logs" / f"{stem}.log"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(p.stdout + (f"--- stderr ---\n{p.stderr}" if p.stderr else ""), encoding="utf-8")
    return f


def snapshot(vd: Path) -> dict[Path, int]:
    return {p: p.stat().st_mtime_ns for p in (vd / "final" / "review").rglob("*.json")}


def written_fails(vd: Path, before: dict[Path, int]) -> list[str]:
    from core.briefs import failed_checks
    after = snapshot(vd)
    changed = {p for p, m in after.items() if before.get(p) != m}
    return [x for x in failed_checks(vd) if Path(os.path.abspath(x)) in changed]


def finish(name: str, overall: str, paths: list[str]) -> int:
    print(" ".join([name, overall, *paths]))
    return 0 if overall == "pass" else 1


def run(argv: list[str], skill: Path) -> int:
    opts, bl, name, args = parse(argv)
    tools = tools_dir(opts.get("--agent"), skill)
    real, vd = tool_file(name, tools, skill), version_dir(opts["--version-dir"])
    exe = opts.get("--blender")
    if exe:
        check_blender(exe)
    pid = vd.parents[3] / "pids" / "blender" / f"{vd.parents[1].name}-{os.getpid()}.pid" if bl else None
    setup = tools / "setup_deps.sh"
    if setup.is_file() and not (tools / ".deps").exists():
        p = heartbeat.run(["bash", str(setup)], tool="setup_deps", vd=vd, env=os.environ | ({"BLENDER": exe} if exe else {}))
        log = write_log(vd, "setup_deps", p)
        if p.returncode:
            return finish("setup_deps", "error", [os.path.relpath(log)])
    venv = tools / ".deps" / "venv" / "bin" / "python"
    cmd = ([exe, "-b", "--python-exit-code", "1", "--python", str(real), "--", *args] if bl
           else [str(venv) if venv.is_file() else sys.executable, str(real), *args])
    before = snapshot(vd)
    try:
        if pid:
            pid.parent.mkdir(parents=True, exist_ok=True)
            pid.write_text(str(os.getpid()), encoding="utf-8")
        try:
            p = heartbeat.run(cmd, tool=real.stem, vd=vd)
        except OSError as ex:
            p = subprocess.CompletedProcess(cmd, 127, "", f"{type(ex).__name__}: {ex}\n")
    finally:
        if pid:
            pid.unlink(missing_ok=True)
    log = write_log(vd, real.stem, p)
    fails = written_fails(vd, before)
    overall = "fail" if fails else "error" if p.returncode else "pass"
    return finish(real.stem, overall, fails or ([os.path.relpath(log)] if overall == "error" else []))


def main(argv: list[str], skill: Path = SKILL_DIR) -> int:
    try:
        return run(argv, skill.resolve())
    except Refused as ex:
        print(f"run_tool: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    root_guard.require_root()
    venv = SKILL_DIR / "scripts" / ".deps" / "venv"
    if (venv / "bin" / "python").is_file() and Path(sys.prefix).resolve() != venv.resolve():
        os.execv(str(venv / "bin" / "python"), [str(venv / "bin" / "python"), *sys.argv])
    sys.exit(main(sys.argv[1:]))
