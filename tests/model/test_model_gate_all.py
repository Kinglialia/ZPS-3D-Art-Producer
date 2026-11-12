"""L11: the model gates the whole detail pass with one gate_all.py, the same file as the blockout's. One build, a gate for
every part, and the part checks of the model (bbox of the blockout, fixed params, winding) before the join."""
import hashlib

import pytest

from modelkit import BLOCKOUT_TOOLS, EAVE, ROUND, TOOLS, VPY, build, build_shared, gate_all, gate_args, make_spec

needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs the model tools/setup_deps.sh")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_model_copy_of_gate_all_is_the_blockout_file_byte_for_byte():
    """The model has its own copy because an agent folder must run alone; a change made in only one of them makes the two
    steps gate the same graph differently."""
    assert sha(TOOLS / "gate_all.py") == sha(BLOCKOUT_TOOLS / "gate_all.py")


@pytest.fixture
def hut(tmp_path):
    b, f = tmp_path / "blockout", tmp_path / "final"
    build(b)
    build(f, [EAVE])
    make_spec(f, b)
    return b, f


@needs_venv
def test_one_gate_all_builds_the_detail_pass_once_gates_every_part_and_checks_it_against_the_blockout(hut):
    b, f = hut
    rc, lines = gate_all(f, *gate_args(b))
    assert (rc, lines) == (0, ["gate_all pass: 7 parts, 2 checks"])
    assert sorted(p.stem for p in (f / "review/gates").iterdir()) == sorted(
        ["base", "walls", "roof", "door", "crate", "crate_l", "eave"])
    assert sorted(p.name for p in (f / "review/checks").iterdir()) == ["detail_build.json", "mesh_build.json"]


@needs_venv
def test_a_detail_part_that_leaves_the_blockout_bbox_fails_the_gate_before_any_join(hut):
    """Row M-bbox: a worker who learns this after the join has built and unwrapped a mesh that cannot pass."""
    b, _ = hut
    wide = b.parent / "wide"
    build(wide, [EAVE], eave_w=5.0)
    make_spec(wide, b)
    rc, lines = gate_all(wide, *gate_args(b))
    assert (rc, len(lines), lines[0].startswith("review/checks/detail_build.json: detail.bbox ")) == (1, 2, True), lines
    assert lines[-1] == "gate_all fail: 1 failing"


@needs_venv
def test_a_graph_with_bevel_box_builds_and_gates_in_the_venv_with_no_blender(tmp_path):
    """K15 made the shared custom functions pure Python. The model must not send such a graph to Blender: this run has
    no Blender on its path and gates all three parts, the bevel_box included."""
    b = tmp_path / "round"
    build_shared(b, ROUND)
    make_spec(b, b)
    rc, lines = gate_all(b, "--check-flag", "final", "--skip", "check_inputs", "--skip", "check_uv_edge", "--skip",
                         "check_detail", "--check-args", "check_mesh=--before-join")
    assert (rc, lines) == (0, ["gate_all pass: 3 parts, 1 checks"])
