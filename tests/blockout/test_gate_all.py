"""L1: gate_all.py builds the graph once, gates every part, runs every check_*.py beside it and prints the failures only.
The review of source 2026-11-11 found that one full build plus a gate per part equals one build per part with --upto,
because the kit places a part only from the parts before it; the test below compares the two."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from conftest import HUT_SOURCES, TOOLS, hut, part, write_build

VPY = TOOLS / ".deps/venv/bin/python"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
PARTS = ["base", "walls", "roof", "door", "crate", "crate_l"]
SKIP_INPUTS = ("--skip", "check_inputs")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def final_dir(tmp_path, graph=None):
    f = tmp_path / "final"
    f.mkdir()
    (f / "part_graph.json").write_text(json.dumps(graph or hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    return f


def gate_all(f, *args, tool=None):
    r = subprocess.run([str(VPY), str(tool or TOOLS / "gate_all.py"), "--work", str(f), *args], capture_output=True,
                       text=True)
    return r.returncode, r.stdout.strip().splitlines(), r.stderr


@needs_venv
def test_a_good_hut_prints_one_line_and_leaves_a_result_for_every_part_and_every_check(tmp_path):
    f = final_dir(tmp_path)
    rc, lines, err = gate_all(f, *SKIP_INPUTS)
    assert (rc, lines) == (0, ["gate_all pass: 6 parts, 7 checks"]), err
    assert sorted(p.stem for p in (f / "review/gates").iterdir()) == sorted(PARTS)
    assert sorted(p.stem for p in (f / "review/checks").iterdir()) == [
        "base", "layout", "markers", "materials", "proportion", "schema", "support"]


@needs_venv
def test_one_full_build_and_a_gate_per_row_equal_one_build_per_part_with_upto(tmp_path):
    """Why gate_all builds once: the gate of part i reads rows[:i + 1] of assembly.json, and a build with --upto i + 1
    writes the same rows, so every number of every gate JSON is the same. Mirror and nested parts included."""
    for sub in ("all", "each"):
        (tmp_path / sub).mkdir()
    f = final_dir(tmp_path / "all")
    assert gate_all(f, *SKIP_INPUTS)[0] == 0
    g = final_dir(tmp_path / "each")
    for n, name in enumerate(PARTS, 1):
        subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(g), "--upto", str(n)],
                       capture_output=True, check=True)
        subprocess.run([str(VPY), str(TOOLS / "self_build/gates.py"), "--work", str(g), "--part", name, "--out",
                        str(g / f"review/gates/{name}.json")], capture_output=True, check=True)

    def numbers(path):
        doc = read(path)
        return doc["overall"], doc["checks"], doc["metrics"], doc["data"]
    assert [numbers(f / f"review/gates/{n}.json") for n in PARTS] == [numbers(g / f"review/gates/{n}.json") for n in PARTS]


@needs_venv
def test_only_the_failing_json_are_printed_and_the_exit_code_is_1(tmp_path):
    """A crate of 1 m sits inside the walls: its gate and the base margin fail; the other parts print nothing."""
    g = hut()
    g["params"]["crate_s"] = 1.0
    f = final_dir(tmp_path, g)
    rc, lines, _ = gate_all(f, *SKIP_INPUTS)
    files = [l.split(":")[0] for l in lines[:-1]]
    assert (rc, lines[-1]) == (1, f"gate_all fail: {len(files)} failing")
    assert "review/gates/crate.json" in files and "review/gates/roof.json" not in files
    assert all(re.match(r"review/(gates|checks)/\w+\.json: ", l) for l in lines[:-1]), lines


@needs_venv
def test_gate_json_of_an_older_build_is_deleted_so_it_can_never_count(tmp_path):
    """A pass for a part that changed would hide its new fault; a fail for a part that is gone would send the worker to
    fix nothing. The check JSON of other tools is not touched."""
    f = final_dir(tmp_path)
    (f / "review/gates").mkdir(parents=True)
    (f / "review/checks").mkdir()
    (f / "review/gates/ghost.json").write_text(json.dumps({"overall": "fail", "checks": []}), encoding="utf-8")
    (f / "review/checks/elsewhere.json").write_text(json.dumps({"overall": "pass"}), encoding="utf-8")
    rc, lines, _ = gate_all(f, *SKIP_INPUTS)
    assert (rc, lines, (f / "review/gates/ghost.json").exists(), (f / "review/checks/elsewhere.json").is_file()) == (
        0, ["gate_all pass: 6 parts, 7 checks"], False, True)


@needs_venv
def test_a_graph_the_schema_check_refuses_is_not_built_and_the_output_says_so(tmp_path):
    g = hut()
    part(g, "roof")["primitive"] = "prism"
    f = final_dir(tmp_path, g)
    rc, lines, _ = gate_all(f, *SKIP_INPUTS)
    assert rc == 1 and lines[0].startswith("review/checks/schema.json: schema.primitive [\"roof\"]")
    assert lines[1:] == ["build: skipped, check_schema failed", "gate_all fail: 2 failing"]
    assert not (f / "assembly.json").exists()


@needs_venv
def test_a_build_error_is_one_line_and_no_gate_runs(tmp_path):
    g = hut()
    part(g, "door")["dims"] = ["door_w", "door_t", "no_such_param"]
    f = final_dir(tmp_path, g)
    rc, lines, _ = gate_all(f, *SKIP_INPUTS)
    assert rc == 1 and lines[0].startswith("build: ") and lines[-1] == "gate_all fail: 1 failing", lines
    assert not (f / "review/gates").exists() or not list((f / "review/gates").iterdir())


@needs_venv
def test_check_inputs_without_its_arguments_is_an_error_line_not_a_silent_pass(tmp_path):
    f = final_dir(tmp_path)
    rc, lines, _ = gate_all(f)
    assert rc == 1 and lines[0].startswith("check_inputs: exit 2, no result JSON: ")


@needs_venv
def test_check_args_reach_the_check_they_name(tmp_path):
    f = final_dir(tmp_path)
    rc, lines, _ = gate_all(f, "--check-args", f"check_inputs=--approved {tmp_path / 'nowhere'} --profile {tmp_path / 'p.yaml'}")
    assert rc == 1 and "review/checks/inputs.json: error" in lines[0], lines


@needs_venv
def test_check_fix_never_runs_here_because_it_needs_an_old_graph_and_a_finding_id(tmp_path):
    f = final_dir(tmp_path)
    gate_all(f, *SKIP_INPUTS)
    assert not list((f / "review/checks").glob("fix_*.json"))


def fake_skill(tmp_path):
    """A copy of gate_all.py in agents/other/tools with its own check_*.py, to show nothing in it is blockout only."""
    skill = tmp_path / "skill"
    tools = skill / "agents/other/tools"
    (tools / "self_build").mkdir(parents=True)
    (skill / "scripts").mkdir()
    shutil.copy(TOOLS.parents[2] / "scripts/root_guard.py", skill / "scripts")
    shutil.copy(TOOLS / "gate_all.py", tools)
    (tools / "build_parts.py").write_text(
        "import json, os, sys\nw = sys.argv[sys.argv.index('--work') + 1]\n"
        "json.dump({'overall': 'pass', 'data': {'parts': [{'name': 'a'}, {'name': 'b'}]}}, open(w + '/assembly.json', 'w'))\n",
        encoding="utf-8")
    (tools / "self_build/gates.py").write_text(
        "import json, os, sys\n\ndef main():\n    a = sys.argv\n    out = a[a.index('--out') + 1]\n"
        "    os.makedirs(os.path.dirname(out), exist_ok=True)\n"
        "    json.dump({'overall': 'fail' if a[a.index('--part') + 1] == 'b' else 'pass', 'checks': [\n"
        "        {'check': 'g.x', 'status': 'fail', 'value': 3}]}, open(out, 'w'))\n", encoding="utf-8")
    for name, overall in (("check_good", "pass"), ("check_bad", "fail")):
        (tools / f"{name}.py").write_text(
            "import json, os, sys\na = sys.argv\nf = a[a.index('--final') + 1]\nos.makedirs(f + '/review/checks', exist_ok=True)\n"
            f"json.dump({{'overall': '{overall}', 'checks': [{{'check': 'c.y', 'status': '{overall}', 'value': 1}}]}}, "
            f"open(f + '/review/checks/{name[6:]}.json', 'w'))\nsys.exit({int(overall == 'fail')})\n", encoding="utf-8")
    return tools


@pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
def test_the_copy_in_another_agent_finds_its_checks_beside_itself_and_gives_them_the_flag_it_is_told(tmp_path):
    """K19 copies gate_all.py byte for byte into the model agent, whose checks take --final: the list of checks is the
    check_*.py files beside the copy and the folder flag is an argument."""
    tools = fake_skill(tmp_path)
    work = tmp_path / "final"
    work.mkdir()
    (tmp_path / "production").mkdir(exist_ok=True)
    (tmp_path / "production/pipeline.toml").touch()
    r = subprocess.run([sys.executable, str(tools / "gate_all.py"), "--work", str(work), "--check-flag", "final"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1, r.stderr
    assert r.stdout.splitlines() == [
        "review/gates/b.json: g.x 3", "review/checks/bad.json: c.y 1", "gate_all fail: 2 failing"], r.stderr
    assert sorted(p.name for p in (work / "review/checks").iterdir()) == ["bad.json", "good.json"]
