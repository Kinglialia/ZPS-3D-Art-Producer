"""Blockout tools on a real build of the hut (coding-checklist rows 1-4). Needs tools/setup_deps.sh and Blender."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import HUT_SOURCES, TOOLS, AGENT

VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and tools/setup_deps.sh")]
PARTS = ["base", "walls", "roof", "door", "crate", "crate_l"]


def py(*args):
    return subprocess.run([str(VPY), *map(str, args)], capture_output=True, text=True)


def blender(*args, env=None):
    return subprocess.run([BLENDER, "-b", "--factory-startup", *map(str, args)], capture_output=True, text=True,
                          env=env)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    f = tmp_path_factory.mktemp("final")
    shutil.copy(AGENT.parents[3] / "tests/blockout/fixtures/hut/part_graph.json", f)
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    r = py(TOOLS / "self_build/assembly.py", "--work", f)
    assert r.returncode == 0, r.stdout + r.stderr
    return f


def test_assembly_runs_with_plain_python_and_ignores_role_and_tag(built):
    asm = read(built / "assembly.json")
    assert (asm["overall"], asm["warnings"]) == ("pass", [])
    assert [p["name"] for p in asm["data"]["parts"]] == PARTS
    assert asm["data"]["union"]["extents"] == [4.0, 4.0, 3.7]
    assert asm["data"]["union"]["method"] == "manifold3d"


def test_gates_read_the_config_keys_and_pass_every_part(built, tmp_path):
    cfg = read_yaml(AGENT / "config.yaml")["self_build"]["gates"]
    assert {k: cfg[k] for k in ("contact_dist_m", "contact_samples", "inset_depth_tolerance")} == {
        "contact_dist_m": 0.001, "contact_samples": 4000, "inset_depth_tolerance": 0.2}
    for p in PARTS:
        out = built / f"review/gates/{p}.json"
        r = py(TOOLS / "self_build/gates.py", "--work", built, "--part", p, "--out", out)
        assert (r.returncode, read(out)["overall"]) == (0, "pass"), p
    th = read(built / "review/gates/door.json")["data"]["thresholds"]
    assert (th["contact_dist"], th["samples"], th["inset_tol"]) == (0.001, 4000, 0.2)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"config": {"self_build": {"gates": {
        "contact_dist_m": 0.002, "contact_samples": 1000, "inset_depth_tolerance": 0.25}}}}), encoding="utf-8")
    out = tmp_path / "door.json"
    py(TOOLS / "self_build/gates.py", "--work", built, "--part", "door", "--spec", spec, "--out", out)
    th = read(out)["data"]["thresholds"]
    assert (th["contact_dist"], th["samples"], th["inset_tol"]) == (0.002, 1000, 0.25)


def read_yaml(path):
    r = py("-c", "import json,sys,yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))", path)
    return json.loads(r.stdout)


def test_pure_checks_pass_on_the_real_build(built):
    for name in ("schema", "materials", "layout", "base", "support", "markers", "proportion"):
        r = py(TOOLS / f"check_{name}.py", "--work", built)
        assert (r.returncode, len(r.stdout.strip().splitlines())) == (0, 1), r.stdout + r.stderr
    assert read(built / "review/checks/base.json")["data"]["margin"] == {"walls": 0.5, "crate": 0.185, "crate_l": 0.185}
    assert read(built / "review/checks/markers.json")["data"]["relief"] == {"door": 0.05}


def test_bootstrap_finds_the_blender_deps_folder():
    r = blender("--python-expr", f"import sys; sys.path.insert(0, {str(TOOLS / 'lib')!r}); import bootstrap, trimesh, "
                "manifold3d, yaml; print('DEPS', bootstrap.DEPS, '%d%d' % sys.version_info[:2])")
    line = next(x for x in r.stdout.splitlines() if x.startswith("DEPS "))
    deps, ver = line[len("DEPS "):].rsplit(" ", 1)
    assert deps == str(TOOLS / f".deps/blender-py{ver}")


def test_assembly_in_blender_needs_the_system_env_recipe(built, tmp_path):
    """Kit assembly.py does not import bootstrap, so the worker runs it with PYTHONPATH (custom parts)."""
    plain = tmp_path / "plain.json"
    blender("--python", TOOLS / "self_build/assembly.py", "--", "--work", built, "--out", plain)
    assert read(plain)["overall"] == "error" and "No module named" in read(plain)["data"]["error"]
    deps = next((TOOLS / ".deps").glob("blender-py*"))
    out = tmp_path / "recipe.json"
    blender("--python-use-system-env", "--python", TOOLS / "self_build/assembly.py", "--", "--work", built,
            "--out", out, env={**os.environ, "PYTHONPATH": str(deps)})
    assert read(out)["overall"] == "pass"


def test_review_renders_open_blender_once_each(built, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"config": {"self_build": {"render_size": 256}}}), encoding="utf-8")
    blender("--python", TOOLS / "self_build/render_views.py", "--", "--work", built, "--mode", "critic",
            "--outdir", built / "review/renders", "--spec", spec)
    rv = read(built / "review/renders/renders.json")
    assert rv["overall"] == "info"
    assert sorted(rv["artifacts"]) == sorted([f"{m}_{v}" for m in ("clay", "normal") for v in
                                              ("front", "back", "left", "right", "34")] + ["parts_front", "parts_34"])
    blender("--python", TOOLS / "render_review.py", "--", "--work", built, "--size", "256")
    rr = read(built / "review/review.json")
    assert sorted(rr["artifacts"]) == ["foot_front_left", "foot_front_right", "game_cam", "lineup"]
    assert all(os.path.getsize(p) > 1000 for p in rr["artifacts"].values())


def test_a_prop_without_a_base_part_still_gets_foot_crops_from_the_parts_on_the_ground(tmp_path):
    f = tmp_path / "final"
    f.mkdir()
    g = json.loads((AGENT.parents[3] / "tests/blockout/fixtures/hut/part_graph.json").read_text(encoding="utf-8"))
    for p in g["parts"]:
        p.pop("tag", None)
    (f / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    assert py(TOOLS / "self_build/assembly.py", "--work", f).returncode == 0
    blender("--python", TOOLS / "render_review.py", "--", "--work", f, "--size", "256")
    rr = read(f / "review/review.json")
    assert {"foot_front_left", "foot_front_right"} <= set(rr["artifacts"])
    foot = rr["data"]["foot"]
    assert (foot["base"], foot["scale"], foot["left"], foot["right"]) == (
        False, 1.0, [2.0, -2.0, 0.0], [-2.0, -2.0, 0.0])


def test_render_critic_gives_the_kit_files_with_a_legend_a_reviewer_can_read(built, tmp_path):
    """Same files and labels as render_views.py; the words of the legend in parts_*.png are dark on the margin."""
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"config": {"self_build": {"render_size": 256}}}), encoding="utf-8")
    kit, own = tmp_path / "kit", tmp_path / "own"
    for tool, outdir in (("self_build/render_views.py", kit), ("render_critic.py", own)):
        r = blender("--python", TOOLS / tool, "--", "--work", built, "--mode", "critic", "--outdir", outdir,
                    "--spec", spec)
        assert (outdir / "renders.json").is_file(), r.stdout[-400:]
    assert sorted(read(own / "renders.json")["artifacts"]) == sorted(read(kit / "renders.json")["artifacts"])
    probe = ("import sys, numpy as np; from PIL import Image; g = np.asarray(Image.open(sys.argv[1]).convert('L')); "
             "m = g[:, g.shape[1] * 3 // 4:]; print(int(m.min()))")
    darkest = {n: int(py("-c", probe, d / "parts_front.png").stdout) for n, d in (("kit", kit), ("own", own))}
    assert darkest["kit"] >= 200 and darkest["own"] < 60, darkest
