"""run_tool.py, the one entry for a worker's tool call (D36.1, plan rows R0 to R5).

The tests call `run_tool.main` in process against a copy of the skill layout made in tmp_path. A fake Blender, a
small script, stands in for the real one: no test starts Blender."""
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import heartbeat
import run_tool
import settings_merge
from shared import write_profile
from core import briefs, intake
from core.state import SKILL_DIR, load_cfg

REPO = Path(__file__).resolve().parents[1]
FAKE_BLENDER_PY = r'''import json, os, runpy, sys, traceback
a = sys.argv[1:]
if os.environ.get("FAKE_BLENDER_LOG"):
    with open(os.environ["FAKE_BLENDER_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(a) + "\n")
if "--python-expr" in a:
    print("DEPS_PROBE " + os.environ["FAKE_BLENDER_PY"])
    sys.exit(0)
print("Blender 5.2.3 LTS")
tool = a[a.index("--python") + 1]
sys.argv = [tool, *a[a.index("--") + 1:]]
code = 0
try:
    runpy.run_path(tool, run_name="__main__")
except SystemExit as e:
    code = e.code or 0
except BaseException:
    traceback.print_exc()
    code = 1
print("\nBlender quit")
sys.exit(code)
'''
REAL_SETUP_DEPS = SKILL_DIR / "agents/zps-3dp-step-model/tools/setup_deps.sh"
TOUCH = 'import pathlib; pathlib.Path(r"{marker}").write_text("ran")\n'


class RT:
    def __init__(self, base: Path, cap, mp):
        self.base, self.cap, self.mp = base, cap, mp
        self.skill = base / "skill"
        self.scripts = self.skill / "scripts"
        self.model_tools = self.skill / "agents/zps-3dp-step-model/tools"
        self.blockout_tools = self.skill / "agents/zps-3dp-step-blockout/tools"
        self.vd = base / "production/assets/hut/model/v1"
        self.pids = base / "production/pids/blender"
        self.rv = self.vd / "final/review"
        for d in (self.scripts, self.model_tools, self.blockout_tools, self.rv / "gates", self.rv / "checks",
                  self.vd / "work", self.pids):
            d.mkdir(parents=True)
        self.bl = self.fake_blender("Blender", "3.13")
        self.blender_log = base / "blender-calls.jsonl"
        mp.setenv("FAKE_BLENDER_LOG", str(self.blender_log))
        (base / "production/preflight.json").write_text(
            json.dumps({"features": {"blender": True}, "blender": {"path": str(self.bl), "version": "5.2.3"}}), encoding="utf-8")

    def fake_blender(self, name: str, py: str) -> Path:
        bin_ = self.base / "bin"
        bin_.mkdir(exist_ok=True)
        (bin_ / "fake_blender.py").write_text(FAKE_BLENDER_PY, encoding="utf-8")
        exe = bin_ / name
        exe.write_text(f'#!/bin/sh\nFAKE_BLENDER_PY={py} exec "{sys.executable}" "{bin_ / "fake_blender.py"}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
        return exe

    def tool(self, name: str, body: str, in_dir: Path | None = None) -> Path:
        p = (in_dir or self.model_tools) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def result(self, rel: str, doc: dict, old: bool = False) -> Path:
        p = self.rv / rel
        p.write_text(json.dumps(doc), encoding="utf-8")
        if old:
            os.utime(p, ns=(1, 1))
        return p

    def log(self, stem: str) -> Path:
        return self.vd / "work/logs" / f"{stem}.log"

    def relpath(self, p: Path) -> str:
        return os.path.relpath(p)

    def run(self, *args: str, blender: bool = False, agent: str = "zps-3dp-step-model"):
        argv = (["--blender", str(self.bl)] if blender else []) + ["--agent", agent, "--version-dir", self.relpath(self.vd), *args]
        rc = run_tool.main(argv, skill=self.skill)
        cap = self.cap.readouterr()
        return rc, cap.out, cap.err


@pytest.fixture
def rt(tmp_path, monkeypatch, capsys):
    base = tmp_path.resolve()
    monkeypatch.chdir(base)
    monkeypatch.delenv("BLENDER", raising=False)
    return RT(base, capsys, monkeypatch)


def plant(rt: RT, case: str) -> tuple[str, Path]:
    """A tool the guard must refuse, as the argument a worker types, and the file it writes if it ever runs."""
    marker = rt.base / f"ran-{case}"
    body = TOUCH.format(marker=marker)
    evil = rt.base / "evil.py"
    evil.write_text(body, encoding="utf-8")
    if case == "absolute path outside the skill":
        return str(evil), marker
    if case == "dotdot out of the skill":
        return "../../../../evil.py", marker
    if case == "dotdot to the skill root":
        (rt.skill / "evil.py").write_text(body, encoding="utf-8")
        return "../../../evil.py", marker
    if case == "symlink out of the tools folder":
        (rt.model_tools / "link.py").symlink_to(evil)
        return "link.py", marker
    if case == "file the agent wrote under production":
        mine = rt.vd / "work/mine.py"
        mine.write_text(body, encoding="utf-8")
        return str(mine), marker
    if case == "module inside a .deps folder":
        rt.tool(".deps/venv/lib/site.py", body)
        return ".deps/venv/lib/site.py", marker
    raise AssertionError(case)


CASES = ["absolute path outside the skill", "dotdot out of the skill", "dotdot to the skill root",
         "symlink out of the tools folder", "file the agent wrote under production", "module inside a .deps folder"]


@pytest.mark.parametrize("case", CASES)
def test_r0_refuses_a_tool_outside_the_skill_tool_folders_and_runs_nothing(rt, case):
    """The allow rule for run_tool.py is an open rule: a tool the guard lets through runs without a prompt."""
    tool, marker = plant(rt, case)
    rc, out, err = rt.run(tool)
    assert (rc, out, marker.exists()) == (2, "", False)
    assert err.startswith("run_tool: refused ") and err.count("\n") == 1


def test_r0_refuses_a_tool_outside_the_skill_tool_folders_also_in_blender_shape(rt):
    tool, marker = plant(rt, "symlink out of the tools folder")
    rc, out, _ = rt.run("bl", tool, blender=True)
    assert (rc, out, marker.exists(), rt.blender_log.exists()) == (2, "", False, False)


def test_r0_runs_a_tool_of_scripts_and_a_tool_of_a_sibling_agent_by_a_path_that_resolves_inside_the_skill(rt):
    one, two = rt.base / "ran-scripts", rt.base / "ran-sibling"
    rt.tool("scripts_tool.py", TOUCH.format(marker=one), in_dir=rt.scripts)
    rt.tool("shared_tool.py", TOUCH.format(marker=two), in_dir=rt.blockout_tools)
    assert rt.run("../../../scripts/scripts_tool.py")[:2] == (0, "scripts_tool pass\n")
    assert rt.run("../../zps-3dp-step-blockout/tools/shared_tool.py")[:2] == (0, "shared_tool pass\n")
    assert (one.exists(), two.exists()) == (True, True)


def test_r0_refuses_a_flag_value_that_would_make_the_open_rule_run_something_else(rt):
    """--agent picks the python, --blender picks the program, --version-dir picks where logs go."""
    marker = rt.base / "ran-flag"
    evil_py = rt.base / "evil/tools/.deps/venv/bin/python"
    evil_py.parent.mkdir(parents=True)
    evil_py.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    evil_py.chmod(0o755)
    evil_bl = rt.base / "bin/evil"
    evil_bl.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    evil_bl.chmod(0o755)
    rt.tool("ok.py", "")
    elsewhere = rt.base / "elsewhere"
    elsewhere.mkdir()
    vd = ["--version-dir", rt.relpath(rt.vd)]
    codes = [rt.run("ok.py", agent="../../../evil")[0],
             rt.run("ok.py", agent="zps-3dp-no-such-step")[0],
             run_tool.main(["--blender", str(evil_bl), "--agent", "zps-3dp-step-model", *vd, "bl", "ok.py"], skill=rt.skill),
             run_tool.main(["--agent", "zps-3dp-step-model", "--version-dir", str(elsewhere), "ok.py"], skill=rt.skill)]
    assert (codes, marker.exists(), (elsewhere / "work").exists()) == ([2, 2, 2, 2], False, False)


def test_r0_refuses_the_network_and_agent_code_scripts_in_the_codex_edition_only(rt):
    """The Codex rule for run_tool.py lets Blender run outside the sandbox. Those scripts never match a Codex rule."""
    marker = rt.base / "ran-meshy"
    rt.tool("meshy_call.py", TOUCH.format(marker=marker), in_dir=rt.scripts)
    rt.tool("self_build/assembly.py", TOUCH.format(marker=marker))
    args = ("../../../scripts/meshy_call.py", "self_build/assembly.py")
    assert [rt.run(a)[0] for a in args] == [0, 0]
    marker.unlink()
    (rt.skill / "runtime.json").write_text(json.dumps({"runtime": "codex", "suffix": "-codex"}), encoding="utf-8")
    assert [rt.run(a)[0] for a in args] == [2, 2]
    assert not marker.exists()


def test_r0_codex_direct_list_is_the_list_the_codex_rule_keeps_outside_every_allow():
    spec = importlib.util.spec_from_file_location("codex_rules", REPO / "editions/codex/installer/codex_rules.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(run_tool.CODEX_DIRECT) == tuple(mod.NETWORK_SCRIPTS) + tuple(mod.AGENT_CODE)


def test_r1_a_blender_tool_that_crashes_makes_run_tool_exit_1_and_the_pid_file_is_gone_after(rt):
    """The old PID line returned the exit code of `rm`, so a crashed Blender looked like a pass."""
    rt.tool("crash.py", "raise RuntimeError('boom')\n")
    rc, out, _ = rt.run("bl", "crash.py", "--final", "F", blender=True)
    assert (rc, out) == (1, f"crash error {rt.relpath(rt.log('crash'))}\n")
    assert list(rt.pids.iterdir()) == []
    call = json.loads(rt.blender_log.read_text(encoding="utf-8").splitlines()[0])
    assert call == ["-b", "--python-exit-code", "1", "--python", str(rt.model_tools / "crash.py"), "--", "--final", "F"]


def test_r1_the_pid_file_exists_while_blender_runs_and_holds_the_pid_of_run_tool(rt):
    """limits.used counts `<id>-<pid>.pid` files whose process is alive, as gen_image_codex.py and assemble.py write them."""
    seen = rt.base / "seen.json"
    rt.tool("peek.py", f'import json, os, pathlib\nd = r"{rt.pids}"\n'
                       f'pathlib.Path(r"{seen}").write_text(json.dumps([[n, open(os.path.join(d, n)).read()] for n in sorted(os.listdir(d))]))\n')
    rc, out, _ = rt.run("bl", "peek.py", blender=True)
    me = os.getpid()
    assert (rc, out, json.loads(seen.read_text(encoding="utf-8")), list(rt.pids.iterdir())) == (
        0, "peek pass\n", [[f"hut-{me}.pid", str(me)]], [])


def test_r1_a_venv_python_tool_writes_no_pid_file_and_runs_on_the_python_of_the_tools_folder(rt):
    seen = rt.base / "seen.txt"
    rt.tool("plain.py", f'import os, pathlib\npathlib.Path(r"{seen}").write_text(os.environ.get("VIA_VENV", "no") + "|" + str(os.listdir(r"{rt.pids}")))\n')
    py = rt.model_tools / ".deps/venv/bin/python"
    py.parent.mkdir(parents=True)
    py.write_text(f'#!/bin/sh\nVIA_VENV=yes exec "{sys.executable}" "$@"\n', encoding="utf-8")
    py.chmod(0o755)
    assert rt.run("plain.py")[:2] == (0, "plain pass\n")
    assert (seen.read_text(encoding="utf-8"), rt.blender_log.exists()) == ("yes|[]", False)


def stale(rt):
    rt.result("gates/old.json", {"overall": "fail"}, old=True)


R2_CASES = {
    "a non-zero exit with no result JSON": ("import sys\nsys.exit(3)\n", None, 1, "{n} error {log}"),
    "exit 0 and a result JSON that says fail": ("W('gates/x.json', {'overall': 'fail'})\n", None, 1, "{n} fail {rv}/gates/x.json"),
    "exit 0 and a result JSON that says error": ("W('checks/y.json', {'overall': 'error'})\n", None, 1, "{n} fail {rv}/checks/y.json"),
    "exit 0 and a result JSON with pass false": ("W('checks/z.json', {'pass': False})\n", None, 1, "{n} fail {rv}/checks/z.json"),
    "the join result at the review root": ("W('join.json', {'overall': 'fail'})\n", None, 1, "{n} fail {rv}/join.json"),
    "exit 1 and a fail JSON names the JSON, not the log": ("W('gates/x.json', {'overall': 'fail'})\nimport sys\nsys.exit(1)\n",
                                                           None, 1, "{n} fail {rv}/gates/x.json"),
    "a result JSON that says pass": ("W('gates/x.json', {'overall': 'pass'})\n", None, 0, "{n} pass"),
    "an old fail JSON the tool did not touch": ("pass\n", stale, 0, "{n} pass"),
    "an old fail JSON the tool rewrote as pass": ("W('gates/old.json', {'overall': 'pass'})\n", stale, 0, "{n} pass"),
    "an old fail JSON the tool rewrote as fail again": ("W('gates/old.json', {'overall': 'fail'})\n", stale, 1,
                                                       "{n} fail {rv}/gates/old.json"),
}


@pytest.mark.parametrize("case", list(R2_CASES))
def test_r2_exit_code_is_1_when_the_tool_exits_non_zero_or_wrote_a_fail_result_during_this_run(rt, case):
    """gates.py, join_mesh.py and the QA checks exit 0 on a fail; a stale fail from an earlier run is not this run's."""
    body, setup, want_rc, line = R2_CASES[case]
    if setup:
        setup(rt)
    rt.tool("tool_a.py", f"import json, pathlib\nRV = pathlib.Path(r'{rt.rv}')\n"
                         "def W(rel, doc):\n    (RV / rel).write_text(json.dumps(doc))\n" + body)
    rc, out, _ = rt.run("tool_a.py")
    rv = rt.relpath(rt.rv)
    assert (rc, out) == (want_rc, line.format(n="tool_a", log=rt.relpath(rt.log("tool_a")), rv=rv) + "\n")


def test_r3_stdout_and_stderr_go_to_the_log_and_run_tool_prints_exactly_one_line(rt):
    """A bare Blender call prints a banner and `Blender quit`: four lines before the tool says anything."""
    rt.tool("chatty.py", 'import sys\nprint("tool says hi")\nprint("warn", file=sys.stderr)\n')
    rc, out, err = rt.run("bl", "chatty.py", blender=True)
    assert (rc, out, err) == (0, "chatty pass\n", "")
    assert rt.log("chatty").read_text(encoding="utf-8") == (
        "Blender 5.2.3 LTS\ntool says hi\n\nBlender quit\n--- stderr ---\nwarn\n")
    assert heartbeat.last(rt.vd)[1:] == ("chatty", "done")


def test_r3_a_second_run_of_the_same_tool_replaces_its_log(rt):
    rt.tool("again.py", 'import os\nprint(os.environ["ROUND"])\n')
    for n in ("one", "two"):
        rt.mp.setenv("ROUND", n)
        rt.run("again.py")
    assert rt.log("again").read_text(encoding="utf-8") == "two\n"


def test_r4_the_settings_snippet_allows_run_tool_and_assemble_and_the_run_line_starts_with_the_run_tool_rule(rt):
    snippet = SKILL_DIR / "templates/settings.snippet.json"
    allow = json.loads(snippet.read_text(encoding="utf-8"))["permissions"]["allow"]
    assert [r for r in allow if "run_tool" in r or "assemble" in r] == [
        "Bash(<SKILL>/scripts/run_tool.py:*)", "Bash(<SKILL>/scripts/.deps/venv/bin/python <SKILL>/scripts/assemble.py:*)"]
    rule = settings_merge.wanted(snippet, SKILL_DIR, None)["permissions"]["allow"]
    assert f"Bash({SKILL_DIR}/scripts/run_tool.py:*)" in rule
    line = briefs.tools_line({"id": "hut"}, {"id": "model", "agent": "step-model", "uses": ["blender"]}, None, None, n=1)[2]
    assert shlex.split(line.removeprefix("RUN: "))[0] == f"{SKILL_DIR}/scripts/run_tool.py"


def test_r4_run_tool_py_is_executable_and_starts_on_the_scripts_venv_when_run_by_its_path(tmp_path, monkeypatch):
    """The allow rule names the script alone: the brief line does not carry the venv python."""
    proj = tmp_path.resolve()
    (proj / "production/assets/hut/model/v1").mkdir(parents=True)
    (proj / "production/pipeline.toml").write_text("", encoding="utf-8")
    monkeypatch.chdir(proj)
    r = subprocess.run([str(SKILL_DIR / "scripts/run_tool.py"), "--version-dir", "production/assets/hut/model/v1",
                        str(tmp_path / "evil.py")], capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (2, "") and r.stderr.startswith("run_tool: refused ") and r.stderr.count("\n") == 1
    ok = subprocess.run([str(SKILL_DIR / "scripts/run_tool.py"), "--version-dir", "production/assets/hut/model/v1",
                         "check_profile.py", "--help"], capture_output=True, text=True)
    assert (ok.returncode, ok.stdout, ok.stderr) == (0, "check_profile pass\n", "")


def test_r5_run_tool_hands_the_blender_of_the_brief_to_setup_deps_so_the_deps_go_to_that_blender(rt, monkeypatch):
    """setup_deps.sh reads only $BLENDER. A worker shell with another Blender in $BLENDER put the deps under the wrong
    Python version, and the tool then could not import them."""
    other = rt.fake_blender("Blender-old", "3.11")
    monkeypatch.setenv("BLENDER", str(other))
    monkeypatch.setenv("DRY_RUN", "1")
    (rt.model_tools / "setup_deps.sh").write_text(REAL_SETUP_DEPS.read_text(encoding="utf-8"), encoding="utf-8")
    rt.tool("any.py", "print(1)\n")
    rc, out, _ = rt.run("bl", "any.py", blender=True)
    log = rt.log("setup_deps").read_text(encoding="utf-8")
    assert (rc, out) == (0, "any pass\n")
    assert "blender-py313" in log and "blender-py311" not in log


def test_r5_run_tool_does_not_run_setup_deps_when_the_tools_folder_has_its_deps(rt):
    (rt.model_tools / ".deps").mkdir()
    (rt.model_tools / "setup_deps.sh").write_text("exit 1\n", encoding="utf-8")
    rt.tool("any.py", "print(1)\n")
    assert rt.run("any.py")[:2] == (0, "any pass\n")
    assert not rt.log("setup_deps").exists()


@pytest.fixture
def briefed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path.resolve())
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    write_profile(tmp_path)
    intake.new(Namespace(id="a-hut", title="a-hut", type="asset", priority=1, deadline=None), load_cfg())
    intake.ready(Namespace(ids=["a-hut"]))
    capsys.readouterr()
    return tmp_path.resolve()


def test_the_worker_brief_gets_a_run_line_with_everything_fixed_for_the_dispatch_and_keeps_the_pid_line(briefed, capsys):
    briefs.run(Namespace(id="a-hut"))
    capsys.readouterr()
    text = (briefed / "production/assets/a-hut/blockout/v1/brief-worker.md").read_text(encoding="utf-8").splitlines()
    want = "RUN: " + shlex.join([f"{SKILL_DIR}/scripts/run_tool.py", "--blender", "blender", "--agent", "zps-3dp-step-blockout",
                                 "--version-dir", "production/assets/a-hut/blockout/v1"])
    assert text.index(want) == text.index("BLENDER: blender") + 1
    assert ("- Mỗi lệnh Blender: `<lệnh> & echo $! > production/pids/blender/a-hut.pid; wait $!; "
            "rm -f production/pids/blender/a-hut.pid`.") in text


def test_the_run_line_names_the_blender_of_the_preflight_and_a_step_without_blender_gets_no_blender_flag(briefed):
    step = {"id": "blockout", "agent": "step-blockout", "uses": ["blender"]}
    line = briefs.tools_line({"id": "a-hut"}, step, {"blender": {"path": "/opt/blender/blender"}}, None, n=3)[2]
    assert shlex.split(line) == ["RUN:", f"{SKILL_DIR}/scripts/run_tool.py", "--blender", "/opt/blender/blender", "--agent",
                                 "zps-3dp-step-blockout", "--version-dir", "production/assets/a-hut/blockout/v3"]
    plain = briefs.tools_line({"id": "a-hut"}, step | {"uses": []}, None, None, n=3)
    assert shlex.split(plain[1]) == ["RUN:", f"{SKILL_DIR}/scripts/run_tool.py", "--agent", "zps-3dp-step-blockout",
                                     "--version-dir", "production/assets/a-hut/blockout/v3"]
