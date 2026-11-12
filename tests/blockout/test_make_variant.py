"""L2: make_variant.py copies a graph, sets params and runs the chain of gate_all.py: one command per variant, where the
fix round of a param finding used to take about 60 commands for two variants."""
import hashlib
import json
import subprocess

import pytest

from conftest import HUT_SOURCES, TOOLS, hut, part
from test_checks import approved, sources_for
from test_custom_lib import PILE, asset_dir, pile_graph

VPY = TOOLS / ".deps/venv/bin/python"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
SKIP = ("--skip", "check_inputs")


def base(tmp_path, graph=None):
    """final/ of v1 with a graph built and a blockout.md the worker wrote."""
    f = tmp_path / "production/assets/hut/blockout/v1/final"
    f.mkdir(parents=True)
    (f / "part_graph.json").write_text(json.dumps(graph or hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True, check=True)
    subprocess.run([str(VPY), str(TOOLS / "blockout_md.py"), "--work", str(f)], capture_output=True)
    text = (f / "blockout.md").read_text(encoding="utf-8").replace("TODO: thành phần đếm trên concept, một dòng", "1 nhà")
    (f / "blockout.md").write_text(text.replace("TODO: bảng đo", "bảng đo của worker"), encoding="utf-8")
    return f


def make(f, *args, out="b", skip=True):
    r = subprocess.run([str(VPY), str(TOOLS / "make_variant.py"), "--from", str(f), "--out",
                        str(f.parent / f"variants/{out}"), *(SKIP if skip else ()), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip().splitlines(), f.parent / f"variants/{out}"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@needs_venv
def test_one_command_builds_a_variant_gates_every_part_and_runs_every_check(tmp_path):
    """Taller roof and lower walls keep the height at 3.7 m, so the layout check passes with the new values."""
    f = base(tmp_path)
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2")
    assert (rc, lines) == (0, [f"make_variant pass: {v}, 6 parts, 7 checks"])


@needs_venv
def test_check_args_reach_check_inputs_of_the_variant(tmp_path):
    a, prof = approved(tmp_path / "proj", has_map=False)
    f = base(tmp_path)
    (f / "sources.json").write_text(json.dumps(sources_for(a, "asset-card.yaml")), encoding="utf-8")
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2", "--check-args",
                        f"check_inputs=--approved {a} --profile {prof}", skip=False)
    assert (rc, lines) == (0, [f"make_variant pass: {v}, 6 parts, 8 checks"])
    assert read(v / "review/checks/inputs.json")["overall"] == "pass"


@needs_venv
def test_the_variant_has_its_own_params_gates_and_checks_and_the_source_graph_is_not_touched(tmp_path):
    f = base(tmp_path)
    before = (f / "part_graph.json").read_bytes()
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2")
    params = read(v / "part_graph.json")["params"]
    assert (params["roof_h"], params["wall_h"], params["door_h"]) == (1.2, 2.2, 1.8)
    assert read(v / "assembly.json")["data"]["params"]["roof_h"] == 1.2
    assert sorted(p.stem for p in (v / "review/gates").iterdir()) == sorted(
        ["base", "walls", "roof", "door", "crate", "crate_l"])
    assert {"layout", "schema", "markers"} <= {p.stem for p in (v / "review/checks").iterdir()}
    assert read(v / "review/checks/layout.json")["overall"] == "pass"
    assert (f / "part_graph.json").read_bytes() == before and not (f / "review/gates").exists()


@needs_venv
def test_the_variant_carries_the_worker_text_and_its_own_bbox_line_and_hashes(tmp_path):
    f = base(tmp_path)
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2")
    text, old = (v / "blockout.md").read_text(encoding="utf-8"), (f / "blockout.md").read_text(encoding="utf-8")
    assert "1 nhà" in text and "bảng đo của worker" in text
    sha = lambda p: [l for l in p.splitlines() if l.startswith("- part_graph.json")]  # noqa: E731
    assert sha(text) != sha(old) and sha(text) == [
        "- part_graph.json: sha256 " + hashlib.sha256((v / "part_graph.json").read_bytes()).hexdigest()]


@needs_venv
def test_check_fix_runs_once_per_finding_and_a_fixed_param_cannot_be_set(tmp_path):
    f = base(tmp_path)
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2", "--old", str(f / "part_graph.json"),
                        "--finding", "F1", "--finding", "F3")
    assert sorted(p.name for p in (v / "review/checks").glob("fix_*.json")) == ["fix_F1.json", "fix_F3.json"]
    assert read(v / "review/checks/fix_F3.json")["overall"] == "pass"
    rc, lines, w = make(f, "--set", "door_h=2.0", out="c")
    assert (rc, lines, w.exists()) == (2, [f"make_variant refused: --set door_h=2.0: door_h is in fixed_params"], False)


@needs_venv
def test_a_variant_that_breaks_the_layout_is_still_written_and_the_failing_check_is_the_only_line_besides_the_summary(tmp_path):
    f = base(tmp_path)
    rc, lines, v = make(f, "--set", "wall_h=2.0")
    assert rc == 1 and (v / "assembly.json").is_file()
    assert lines[0].startswith("review/checks/layout.json: layout.bbox") and lines[-1].startswith("make_variant fail: ")


@needs_venv
@pytest.mark.parametrize("arg, why", [
    (["--set", "no_such=1"], "--set no_such=1: 'no_such' is not a param of the graph"),
    (["--set", "wall_h=tall"], "value 'tall' is not a number"),
    (["--set", "wall_h"], "--set wall_h: 'wall_h' is not a param of the graph"),
    (["--old", "x"], "--old and --finding go together")])
def test_a_name_that_is_not_a_param_a_value_that_is_not_a_number_and_a_lone_old_are_refused(tmp_path, arg, why):
    rc, lines, v = make(base(tmp_path), *arg)
    assert (rc, lines, v.exists()) == (2, [f"make_variant refused: {why}"], False)


@needs_venv
def test_a_count_param_stays_whole_and_a_float_param_stays_a_float(tmp_path):
    g = hut()
    g["params"]["rows"] = 3
    g["params"]["crate_s"] = 0.3
    f = base(tmp_path, g)
    assert make(f, "--set", "rows=3.5")[1] == ["make_variant refused: 3.5 is not whole, and the old value 3 is a count"]
    rc, lines, v = make(f, "--set", "rows=4", "--set", "crate_s=1")
    params = read(v / "part_graph.json")["params"]
    assert (params["rows"], params["crate_s"], type(params["rows"]).__name__, type(params["crate_s"]).__name__) == (
        4, 1.0, "int", "float")


@needs_venv
def test_out_must_sit_in_a_folder_called_variants_so_no_other_folder_is_deleted(tmp_path):
    f = base(tmp_path)
    r = subprocess.run([str(VPY), str(TOOLS / "make_variant.py"), "--from", str(f), "--out", str(tmp_path / "keep"),
                        "--set", "roof_h=1.2"], capture_output=True, text=True)
    assert (r.returncode, "its folder is not called variants" in r.stdout, (tmp_path / "keep").exists()) == (2, True, False)


@needs_venv
def test_a_second_run_replaces_the_old_variant_folder(tmp_path):
    f = base(tmp_path)
    rc, lines, v = make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2")
    (v / "review/gates/ghost.json").write_text("{}", encoding="utf-8")
    make(f, "--set", "roof_h=1.2", "--set", "wall_h=2.2")
    assert not (v / "review/gates/ghost.json").exists()


@needs_venv
def test_a_graph_with_an_asset_function_is_copied_and_not_built_and_the_last_line_names_the_commands(tmp_path):
    """custom_mesh.py runs agent code; the Codex edition keeps it out of run_tool.py, so no tool run through RUN starts it."""
    g = pile_graph(2)
    f = asset_dir(tmp_path, g, PILE)
    rc, lines, v = make(f, "--set", "courses=3")
    assert rc == 0 and not (v / "assembly.json").exists()
    assert lines == [f"make_variant copied {v}; not built, the graph calls custom_parts.py. next: "
                     f"RUN custom_mesh.py --work {v}; RUN gate_all.py --work {v} --skip check_inputs"], lines
    assert read(v / "part_graph.json")["params"]["courses"] == 3
    done = subprocess.run([str(VPY), str(TOOLS / "custom_mesh.py"), "--work", str(v)], capture_output=True, text=True)
    (v / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    gate = subprocess.run([str(VPY), str(TOOLS / "gate_all.py"), "--work", str(v), "--skip", "check_inputs"],
                          capture_output=True, text=True)
    assert (done.returncode, gate.returncode) == (0, 0), (done.stdout, gate.stdout)
