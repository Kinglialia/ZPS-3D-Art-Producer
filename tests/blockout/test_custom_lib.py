"""Approved custom part library (D27.13): `custom` parts run only functions of custom_lib.py, never code an agent
wrote into <work>/parts_lib.py."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import HUT_SOURCES, TOOLS, hut, part, write_build

VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
RUN4 = ["arch_cap", "bevel_box", "grooved_box", "lock_plate", "plank_vault", "strap_band", "vault"]
USER_APPROVED = ["arch_cap_pointed"]  # run 5 wooden-chest, model F1, 2026-11-10 (seam: run 6 blockout F1)


def agent_lib(work, sentinel, body=""):
    (work / "parts_lib.py").write_text(f"open({str(sentinel)!r}, 'w').write('ran')\n{body}", encoding="utf-8")


def graph_dir(tmp_path, graph=None):
    f = tmp_path / "final"
    f.mkdir()
    (f / "part_graph.json").write_text(json.dumps(graph or hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    return f


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_library_holds_exactly_the_run4_functions_plus_the_ones_the_user_approved():
    import ast
    tree = ast.parse((TOOLS / "custom_lib.py").read_text(encoding="utf-8"))
    public = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))
    assert public == sorted(RUN4 + USER_APPROVED)


def test_schema_refuses_a_custom_part_whose_fn_is_not_in_the_library(tmp_path, run_check):
    g = hut()
    part(g, "roof").update(primitive="custom", fn="my_roof", args=["wall_w", "wall_d", "roof_h"])
    part(g, "walls").update(primitive="custom", fn="vault", args=["wall_w", "wall_d", "wall_h", 0.5, 12])
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert (r.rc, r.check("schema.custom_fn")) == (1, {"status": "fail", "value": ["roof: my_roof"]})


@needs_venv
def test_the_kit_assembly_runs_agent_code_from_parts_lib_which_is_why_agents_build_through_build_parts(tmp_path):
    f, sentinel = graph_dir(tmp_path), tmp_path / "sentinel"
    agent_lib(f, sentinel)
    subprocess.run([str(VPY), str(TOOLS / "self_build/assembly.py"), "--work", str(f)], capture_output=True)
    assert sentinel.exists()


@needs_venv
def test_build_parts_never_imports_the_agent_parts_lib_and_leaves_the_library_beside_the_graph(tmp_path):
    f, sentinel = graph_dir(tmp_path), tmp_path / "sentinel"
    agent_lib(f, sentinel)
    r = subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True,
                       text=True)
    assert (r.returncode, read(f / "assembly.json")["overall"], sentinel.exists()) == (0, "pass", False), r.stderr
    assert (f / "parts_lib.py").read_bytes() == (TOOLS / "custom_lib.py").read_bytes()


@needs_venv
def test_build_parts_stops_on_a_custom_fn_outside_the_library_and_names_it_in_the_result(tmp_path):
    g = hut()
    part(g, "roof").update(primitive="custom", fn="my_roof", args=["wall_w", "wall_d", "roof_h"])
    f, sentinel = graph_dir(tmp_path, g), tmp_path / "sentinel"
    agent_lib(f, sentinel, "def my_roof(w, d, h):\n    raise SystemExit('agent code')\n")
    r = subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True,
                       text=True)
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"], sentinel.exists()) == (1, "error", False)
    assert "custom fn not in custom_lib.py: my_roof" in asm["data"]["error"]


@needs_venv
@pytest.mark.parametrize("tool", ["self_build/param_fit.py", "build_parts.py"])
def test_param_fit_for_a_34_concept_runs_agent_code_only_through_the_kit_script(tmp_path, tool):
    f, sentinel = graph_dir(tmp_path), tmp_path / "sentinel"
    agent_lib(f, sentinel)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"config": {"self_build": {"param_fit": {"enabled": False}}}}), encoding="utf-8")
    target = ["param_fit"] if tool == "build_parts.py" else []
    subprocess.run([str(VPY), str(TOOLS / tool), *target, "--work", str(f), "--spec", str(spec)], capture_output=True)
    assert (read(f / "fit.json")["overall"], sentinel.exists()) == ("skipped", tool != "build_parts.py")


def test_build_parts_refuses_a_kit_tool_other_than_assembly_or_param_fit(tmp_path):
    r = subprocess.run([str(VPY if VPY.is_file() else "python3"), str(TOOLS / "build_parts.py"), "apply_edit"],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (2, "[blockout/build_parts] error: first argument must be one of "
                                           "assembly, param_fit\n")


@pytest.mark.blender
@pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)), reason="needs Blender and tools/setup_deps.sh")
def test_a_custom_part_builds_from_the_library_function_even_when_parts_lib_defines_the_same_name(tmp_path):
    g = hut()
    part(g, "roof").update(primitive="custom", fn="vault", args=["wall_w", "wall_d", "roof_h", 0.6, 12])
    part(g, "roof").pop("dims")
    f, sentinel = graph_dir(tmp_path, g), tmp_path / "sentinel"
    agent_lib(f, sentinel, "def vault(*a):\n    raise SystemExit('agent code')\n")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(TOOLS / "build_parts.py"), "--", "assembly",
                    "--work", str(f)], capture_output=True, text=True)
    asm = read(f / "assembly.json")
    roof = next(p for p in asm["data"]["parts"] if p["name"] == "roof")
    assert (asm["overall"], sentinel.exists(), asm["data"]["union"]["extents"], roof["bbox_max"]) == (
        "pass", False, [4.0, 4.0, 3.7], [1.5, 1.5, 3.7])


POINTED = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lib", sys.argv[-1]); lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
a = (0.065, 0.66, 0.30, 0.22, 0.05, 0.015, 1, 24)
def verts(bm): return sorted(tuple(round(c, 6) for c in v.co) for v in bm.verts)
r, p0, p = lib.arch_cap(*a), lib.arch_cap_pointed(*a, point=0.0), lib.arch_cap_pointed(*a)
moved = sorted(set(verts(p)) - set(verts(r)))
print(json.dumps({"same_at_0": verts(p0) == verts(r), "counts": [len(r.verts), len(p.verts)],
                  "open_edges": sum(not e.is_manifold for e in p.edges), "moved": len(moved),
                  "lower": all(z <= max(q[2] for q in verts(r) if abs(q[1] - y) < 1e-6) for _, y, z in moved),
                  "top": max(v[2] for v in verts(p)) == max(v[2] for v in verts(r))}))
"""


@pytest.mark.blender
@pytest.mark.skipif(not os.access(BLENDER, os.X_OK), reason="needs Blender")
def test_arch_cap_pointed_only_lowers_the_inner_rim_toward_a_peak_and_keeps_the_cap_closed(tmp_path):
    """The concept's lid end has a pointed inner arch. The outer curve, the height and the vertex count must not
    change, or the cap no longer meets the lid; point 0 must give back arch_cap exactly."""
    script = tmp_path / "pointed.py"
    script.write_text(POINTED, encoding="utf-8")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(script), "--", str(TOOLS / "custom_lib.py")],
                       capture_output=True, text=True)
    out = json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))
    assert out == {"same_at_0": True, "counts": [108, 108], "open_edges": 0, "moved": 44, "lower": True, "top": True}


SEAM = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lib", sys.argv[-1]); lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
def verts(bm): return sorted(tuple(round(c, 6) for c in v.co) for v in bm.verts)
lid = (1.0, 0.66, 0.30, 0.22, 24, 0.012, 0.006, 2)
cap = (0.065, 0.66, 0.30, 0.22, 0.05, 0.015, 1, 24, 0.012, 0.006, 2)
same = verts(lib.plank_vault(*lid)) == verts(lib.plank_vault(*lid, seam=0.0)) and \
       verts(lib.arch_cap_pointed(*cap)) == verts(lib.arch_cap_pointed(*cap, seam=0.0))
pts, norms, h, lips = lib._plank_profile(0.66, 0.30, 0.22, 24, 0.012, 2, 0.3)
p0, _, _, lips0 = lib._plank_profile(0.66, 0.30, 0.22, 24, 0.012, 2)
y, z = [(pts[k][0] + pts[k + 1][0]) / 2 for k in lips], [(pts[k][1] + pts[k + 1][1]) / 2 for k in lips]
lid_bm, cap_bm = lib.plank_vault(*lid, seam=0.3), lib.arch_cap_pointed(*cap, seam=0.3)
print(json.dumps({"same_at_0": same, "seams": len(lips), "front": y[0] < -0.05, "below_apex": z[0] < h - 0.03,
                  "apex_default": abs((p0[lips0[0]][0] + p0[lips0[0] + 1][0]) / 2) < 1e-9,
                  "steps": lib._seam_steps(24, 2, 0.3), "default_steps": lib._seam_steps(24, 2, 0.0),
                  "open_edges": sum(not e.is_manifold for e in lid_bm.edges) + sum(not e.is_manifold for e in cap_bm.edges)}))
"""


@pytest.mark.blender
@pytest.mark.skipif(not os.access(BLENDER, os.X_OK), reason="needs Blender")
def test_seam_moves_the_lid_plank_seam_off_the_apex_and_keeps_equal_planks_by_default(tmp_path):
    """Run 6 wooden-chest: with 2 planks the one lid seam sat on the apex, but the concept puts it on the front
    slope. seam moves it there for both the lid and its end caps, so the cap lips still meet the lid groove;
    seam 0 must give the old equal split exactly, or every approved graph changes."""
    script = tmp_path / "seam.py"
    script.write_text(SEAM, encoding="utf-8")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(script), "--", str(TOOLS / "custom_lib.py")],
                       capture_output=True, text=True)
    out = json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))
    assert out == {"same_at_0": True, "seams": 1, "front": True, "below_apex": True, "apex_default": True,
                   "steps": [7], "default_steps": [12], "open_edges": 0}
