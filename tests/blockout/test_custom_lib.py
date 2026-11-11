"""`custom` part functions (D32): the shared custom_lib.py holds only generic functions, and the asset's own functions
live in <PRODUCER_ROOT>/assets/<id>/custom_parts.py. That file is plain Python that uses only math and returns
vertices and faces (D32.2): custom_mesh.py runs it outside Blender, after an allow-list check, and writes one JSON mesh
per part. Blender builds only custom_lib.py and those JSON meshes (mesh_from_json.py), so code an agent wrote never runs
inside Blender, where it would have the user's rights and, on Codex, no sandbox."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import HUT_SOURCES, TOOLS, hut, part, write_build

sys.path.insert(0, str(TOOLS))
import project_parts as PP  # noqa: E402

VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")
needs_blender = pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                   reason="needs Blender and tools/setup_deps.sh")
GENERIC = ["bevel_box", "grooved_box", "vault"]
# A gable roof: a triangular prism along X, w x d x h, centred on its bbox. 6 vertices, 5 faces.
ROOF = ("import math\n\n\ndef ridge_roof(w, d, h):\n"
        "    x, y, z = w / 2.0, d / 2.0, h / 2.0\n"
        "    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, 0.0, z), (x, 0.0, z)]\n"
        "    faces = [(0, 3, 2, 1), (0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5)]\n"
        "    return verts, faces\n")


def agent_lib(work, sentinel, body=""):
    (work / "parts_lib.py").write_text(f"open({str(sentinel)!r}, 'w').write('ran')\n{body}", encoding="utf-8")


def graph_dir(tmp_path, graph=None):
    f = tmp_path / "final"
    f.mkdir()
    (f / "part_graph.json").write_text(json.dumps(graph or hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    return f


def asset_dir(tmp_path, graph, source):
    """A version folder inside <root>/production/assets/hut, with the asset's custom_parts.py."""
    prod = tmp_path / "production"
    (prod / "assets/hut/blockout/v1").mkdir(parents=True)
    (prod / "pipeline.toml").touch()
    (prod / "assets/hut/custom_parts.py").write_text(source, encoding="utf-8")
    return graph_dir(prod / "assets/hut/blockout/v1", graph)


def roof_graph(fn="ridge_roof"):
    g = hut()
    part(g, "roof").update(primitive="custom", fn=fn, args=["wall_w", "wall_d", "roof_h"])
    part(g, "roof").pop("dims")
    return g


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(f, *cmd):
    return subprocess.run([*cmd, str(TOOLS / "build_parts.py"), *(["--"] if cmd[0] == BLENDER else []), "assembly",
                           "--work", str(f)], capture_output=True, text=True)


def meshes(f, *cmd):
    """custom_mesh.py on the graph in f: (exit code, stdout line, {file name: JSON})."""
    r = subprocess.run([*(cmd or [str(VPY)]), str(TOOLS / "custom_mesh.py"), *(["--"] if cmd else []), "--work", str(f)],
                       capture_output=True, text=True)
    out = f.parent / "work/custom_mesh"
    return r.returncode, r.stdout.strip(), {p.name: read(p) for p in sorted(out.glob("*.json"))} if out.is_dir() else {}


def test_the_shared_library_holds_only_generic_functions_so_no_asset_code_ships_with_the_skill():
    import ast
    tree = ast.parse((TOOLS / "custom_lib.py").read_text(encoding="utf-8"))
    public = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))
    assert public == GENERIC


def test_schema_refuses_a_custom_part_whose_fn_is_in_neither_the_library_nor_the_asset_file(tmp_path, run_check):
    g = hut()
    part(g, "roof").update(primitive="custom", fn="my_roof", args=["wall_w", "wall_d", "roof_h"])
    part(g, "walls").update(primitive="custom", fn="vault", args=["wall_w", "wall_d", "wall_h", 0.5, 12])
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert (r.rc, r.check("schema.custom_fn"), r.check("schema.custom_parts")) == (
        1, {"status": "fail", "value": ["roof: my_roof"]}, {"status": "pass", "value": []})


def test_schema_accepts_a_function_of_the_asset_file_without_running_it(tmp_path, run_check):
    """check_schema reads the asset file's names with ast. A top-level `assert False` would stop it if it ran the file."""
    f = asset_dir(tmp_path, roof_graph(), f"assert False\n{ROOF}")
    write_build(f, roof_graph())
    r = run_check("check_schema", "--work", f)
    assert (r.rc, r.check("schema.custom_fn"), r.check("schema.custom_parts")) == (
        0, {"status": "pass", "value": []}, {"status": "pass", "value": []}), r.stderr


def test_schema_fails_an_asset_file_that_imports_os_or_redefines_a_library_function(tmp_path, run_check):
    f = asset_dir(tmp_path, roof_graph(), f"import os\n{ROOF}\n\ndef vault(*a):\n    return None\n")
    write_build(f, roof_graph())
    r = run_check("check_schema", "--work", f)
    assert r.check("schema.custom_parts") == {"status": "fail", "value": ["line 1: import os"]}
    (f.parents[2] / "custom_parts.py").write_text(f"{ROOF}\n\ndef vault(*a):\n    return None\n", encoding="utf-8")
    r = run_check("check_schema", "--work", f)
    assert r.check("schema.custom_parts") == {"status": "fail", "value": ["redefines vault of custom_lib.py"]}


@pytest.mark.parametrize("src, error", [
    ("import os\n", "line 1: import os"),
    ("import bmesh\n", "line 1: import bmesh"),
    ("import os.path as p\n", "line 1: import os.path"),
    ("from subprocess import run\n", "line 1: from subprocess import"),
    ("from . import x\n", "line 1: from . import"),
    ("x = open('f', 'w')\n", "line 1: name open"),
    ("x = eval('1')\n", "line 1: name eval"),
    ("x = exec\n", "line 1: name exec"),
    ("x = compile\n", "line 1: name compile"),
    ("x = __import__('os')\n", "line 1: name __import__"),
    ("x = getattr(math, 'pi')\n", "line 1: name getattr"),
    ("x = ().__class__\n", "line 1: attribute __class__"),
    ("x = __builtins__\n", "line 1: name __builtins__"),
    ("x = '{0.__class__}'.format(1)\n", "line 1: attribute format"),
    ("class A:\n    pass\n", "line 1: ClassDef is not allowed"),
    ("with f() as g:\n    pass\n", "line 1: With is not allowed"),
    ("def f(:\n", "line 1: syntax error: invalid syntax"),
])
def test_the_static_check_refuses_everything_outside_math_and_arithmetic(src, error):
    """An allow-list: a name the file does not define, a builtin outside the short list, an import other than math, a
    dunder or a statement outside plain functions is refused, so the file cannot reach the disk, the network or the
    interpreter."""
    assert error in PP.static_errors(src)


def test_the_static_check_passes_plain_geometry_code():
    src = "import math\nfrom math import pi\n\n\ndef ring(r, seg):\n    pts = []\n    for i in range(int(seg)):\n" \
          "        pts.append((r * math.cos(2 * pi * i / seg), r * math.sin(2 * pi * i / seg), 0.0))\n" \
          "    return pts, [list(range(len(pts)))]\n"
    assert (PP.static_errors(src), PP.static_errors(ROOF), PP.functions(src)) == ([], [], ["ring"])


def test_the_asset_file_is_found_only_above_a_folder_inside_assets_of_a_producer_root(tmp_path):
    f = asset_dir(tmp_path, hut(), ROOF)
    loose = tmp_path / "elsewhere/assets/hut/blockout/v1/final"
    loose.mkdir(parents=True)
    (loose.parents[2] / "custom_parts.py").write_text(ROOF, encoding="utf-8")
    assert (PP.find(f), PP.find(loose)) == (str(tmp_path / "production/assets/hut/custom_parts.py"), None)


def test_each_graph_of_a_version_gets_its_own_mesh_folder_under_work(tmp_path):
    """final/ and the param variants b, c build the same part names with other values; one shared folder would let
    one graph build the other's mesh. work/ is deleted by the D29 purge, so the meshes go with it."""
    v = tmp_path / "blockout/v3"
    assert [PP.mesh_dir(v / s) for s in ("final", "variants/b", "final/rollouts/1")] + [PP.mesh_dir(tmp_path)] == [
        str(v / "work/custom_mesh"), str(v / "work/custom_mesh/variants/b"),
        str(v / "work/custom_mesh/final/rollouts/1"), None]


@needs_venv
def test_custom_mesh_writes_one_json_mesh_per_part_with_its_args_and_the_file_hash(tmp_path):
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    rc, line, out = meshes(f)
    doc = out["roof.json"]
    assert (rc, list(out), doc["fn"], doc["args"], len(doc["verts"]), len(doc["faces"])) == (
        0, ["roof.json"], "ridge_roof", [3.0, 3.0, 1.0], 6, 5), line
    assert doc["source_sha256"] == hashlib.sha256(ROOF.encode()).hexdigest()
    assert line == f"[blockout/custom_mesh] 1 mesh -> {f.parent / 'work/custom_mesh'}"


@needs_venv
@pytest.mark.parametrize("bad, why", [
    ("import os\n", "line 1: import os"),
    ("x = open('{s}', 'w')\n", "line 1: name open"),
    ("x = ().__class__\n", "line 1: attribute __class__"),
])
def test_custom_mesh_refuses_a_file_outside_the_allow_list_and_runs_none_of_it(tmp_path, bad, why):
    sentinel = tmp_path / "sentinel"
    f = asset_dir(tmp_path, roof_graph(), bad.format(s=sentinel) + ROOF)
    rc, line, out = meshes(f)
    assert (rc, out, sentinel.exists()) == (1, {}, False)
    assert line.startswith(f"[blockout/custom_mesh] fail: custom_parts.py refused by the static check: {why}")


@needs_venv
@pytest.mark.parametrize("body, why", [
    ("    return [], []\n", "roof: ridge_roof returned a bad mesh: verts must be a non-empty list of [x, y, z]"),
    ("    return [(0.0, 0.0, 0.0)] * 3, [(0, 1, 5)]\n",
     "roof: ridge_roof returned a bad mesh: faces[0] must hold >= 3 vertex indexes in 0..2"),
    ("    return [(0.0, 0.0, float('nan')), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)]\n",
     "roof: ridge_roof returned a bad mesh: verts[0] must be 3 finite numbers"),
    ("    raise ValueError(f'h {h} is under the eave')\n", "roof: ridge_roof failed: ValueError: h 1.0 is under the eave"),
])
def test_custom_mesh_refuses_a_function_that_fails_or_returns_no_mesh_and_writes_nothing(tmp_path, body, why):
    f = asset_dir(tmp_path, roof_graph(), f"def ridge_roof(w, d, h):\n{body}")
    rc, line, out = meshes(f)
    assert (rc, line, out) == (1, f"[blockout/custom_mesh] fail: {why}", {})


@needs_venv
def test_build_parts_stops_when_a_param_changed_after_custom_mesh_and_names_the_command(tmp_path):
    """The JSON mesh is fixed for the args it was made with; a changed param must not build the old shape."""
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    assert meshes(f)[0] == 0
    g = roof_graph()
    g["params"]["roof_h"] = 1.2
    (f / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    r = build(f, str(VPY))
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"]) == (1, "error")
    assert (f"no JSON mesh of ridge_roof(3.0, 3.0, 1.2) in {f.parent / 'work/custom_mesh'}: run "
            f"`PY T/custom_mesh.py --work {f}` after each change to part_graph.json or custom_parts.py") \
        in asm["data"]["error"]


@needs_venv
def test_build_parts_stops_when_custom_parts_changed_after_custom_mesh(tmp_path):
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    assert meshes(f)[0] == 0
    (f.parents[2] / "custom_parts.py").write_text(f"{ROOF}\n\ndef ridge_roof_2(w, d, h):\n    return [], []\n",
                                                   encoding="utf-8")
    r = build(f, str(VPY))
    assert r.returncode == 1
    assert "the JSON mesh of ridge_roof in " in read(f / "assembly.json")["data"]["error"]


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
    r = build(f, str(VPY))
    assert (r.returncode, read(f / "assembly.json")["overall"], sentinel.exists()) == (0, "pass", False), r.stderr
    assert (f / "parts_lib.py").read_bytes() == (TOOLS / "custom_lib.py").read_bytes()


@needs_venv
def test_build_parts_stops_on_a_custom_fn_outside_both_files_and_names_it_in_the_result(tmp_path):
    f, sentinel = graph_dir(tmp_path, roof_graph("my_roof")), tmp_path / "sentinel"
    agent_lib(f, sentinel, "def my_roof(w, d, h):\n    raise SystemExit('agent code')\n")
    r = build(f, str(VPY))
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"], sentinel.exists()) == (1, "error", False)
    assert "custom fn not in custom_lib.py or custom_parts.py: my_roof; available: vault, grooved_box, bevel_box" \
        in asm["data"]["error"]


@needs_venv
def test_build_parts_refuses_an_asset_file_that_fails_the_static_check(tmp_path):
    f = asset_dir(tmp_path, roof_graph(), f"import os\nos.system('true')\n{ROOF}")
    r = build(f, str(VPY))
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"]) == (1, "error")
    assert "custom_parts.py refused by the static check: line 1: import os" in asm["data"]["error"]


@needs_venv
def test_build_parts_refuses_an_asset_function_named_like_a_library_function(tmp_path):
    """Either winner would build a shape its author did not expect, so a clash stops the build."""
    f = asset_dir(tmp_path, roof_graph("vault"), f"{ROOF}\n\ndef vault(*a):\n    return None\n")
    r = build(f, str(VPY))
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"]) == (1, "error")
    assert "custom_parts.py redefines vault of custom_lib.py: give the asset function another name" in asm["data"]["error"]


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


@needs_venv
def test_param_fit_leaves_alone_the_params_that_feed_an_asset_function(tmp_path):
    """The asset mesh is fixed until custom_mesh.py runs again, so moving roof_h would only score a stale shape."""
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"config": {"self_build": {"param_fit": {"enabled": False}}}}), encoding="utf-8")
    r = subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "param_fit", "--work", str(f), "--spec", str(spec)],
                       capture_output=True, text=True)
    held = "[blockout/build_parts] not fitted, they feed a custom_parts.py function: roof_h, wall_d, wall_w"
    assert (held in r.stdout.splitlines(), read(f / "fit.json")["overall"]) == (True, "skipped"), r.stdout


def test_build_parts_refuses_a_kit_tool_other_than_assembly_or_param_fit(tmp_path):
    r = subprocess.run([str(VPY if VPY.is_file() else "python3"), str(TOOLS / "build_parts.py"), "apply_edit"],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (2, "[blockout/build_parts] error: first argument must be one of "
                                           "assembly, param_fit\n")


@pytest.mark.blender
@needs_blender
def test_a_custom_part_builds_from_the_library_function_even_when_parts_lib_defines_the_same_name(tmp_path):
    g = hut()
    part(g, "roof").update(primitive="custom", fn="vault", args=["wall_w", "wall_d", "roof_h", 0.6, 12])
    part(g, "roof").pop("dims")
    f, sentinel = graph_dir(tmp_path, g), tmp_path / "sentinel"
    agent_lib(f, sentinel, "def vault(*a):\n    raise SystemExit('agent code')\n")
    build(f, BLENDER, "-b", "--factory-startup", "--python")
    asm = read(f / "assembly.json")
    roof = next(p for p in asm["data"]["parts"] if p["name"] == "roof")
    assert (asm["overall"], sentinel.exists(), asm["data"]["union"]["extents"], roof["bbox_max"]) == (
        "pass", False, [4.0, 4.0, 3.7], [1.5, 1.5, 3.7])


@pytest.mark.blender
@needs_blender
def test_blender_builds_an_asset_part_from_its_json_mesh_and_parts_lib_holds_only_the_library(tmp_path):
    """The JSON is halved along X by hand after custom_mesh.py: the roof Blender builds is half as wide, so the shape
    came from the JSON, not from running ridge_roof. parts_lib.py is a plain copy of custom_lib.py."""
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    assert meshes(f)[0] == 0
    j = f.parent / "work/custom_mesh/roof.json"
    doc = read(j)
    doc["verts"] = [[x / 2, y, z] for x, y, z in doc["verts"]]
    j.write_text(json.dumps(doc), encoding="utf-8")
    r = build(f, BLENDER, "-b", "--factory-startup", "--python")
    asm = read(f / "assembly.json")
    roof = next(p for p in asm["data"]["parts"] if p["name"] == "roof")
    assert (asm["overall"], roof["bbox_min"], roof["bbox_max"], roof["tris"]) == (
        "pass", [-0.75, -1.5, 2.7], [0.75, 1.5, 3.7], 8), r.stdout
    assert (f / "parts_lib.py").read_bytes() == (TOOLS / "custom_lib.py").read_bytes()


@pytest.mark.blender
@needs_blender
def test_custom_mesh_refuses_to_run_inside_blender(tmp_path):
    """Every installed script can run in Blender outside the Codex sandbox; this one runs agent code, so it stops."""
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    rc, line, out = meshes(f, BLENDER, "-b", "--factory-startup", "--python")
    assert ("[blockout/custom_mesh] error: run with PY, not inside Blender; Blender builds only from the JSON meshes"
            in line, out) == (True, {}), line


SHAPES = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lib", sys.argv[-1]); lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
def verts(bm): return sorted(tuple(round(c, 6) for c in v.co) for v in bm.verts)
def info(bm):
    vs = verts(bm)
    return [len(bm.verts), sum(not e.is_manifold for e in bm.edges),
            [round(max(v[i] for v in vs) - min(v[i] for v in vs), 6) for i in range(3)]]
def levels(bm): return sorted({v[2] for v in verts(bm)})
out = {"vault": info(lib.vault(2.0, 1.0, 0.6, 0.4, 12)),
       "vault_planks_1": verts(lib.vault(2.0, 1.0, 0.6, 0.4, 12)) == verts(lib.vault(2.0, 1.0, 0.6, 0.4, 12, 1, 0.02, 0.01)),
       "vault_planks_3": info(lib.vault(2.0, 1.0, 0.6, 0.4, 12, 3, 0.02, 0.01)),
       "box_rows_1": info(lib.grooved_box(1.0, 0.8, 0.9, 0.02, 0.01, 1)),
       "box_rows_3": levels(lib.grooved_box(1.0, 0.8, 0.9, 0.02, 0.01, 3)),
       "box_pitch": levels(lib.grooved_box(1.0, 0.8, 0.9, 0.02, 0.01, 3, 0.2, 0.3)),
       "box_open": info(lib.grooved_box(1.0, 0.8, 0.9, 0.02, 0.01, 3))[1]}
for k, call in (("overlap", lambda: lib.grooved_box(1.0, 0.8, 0.9, 0.2, 0.01, 6)),
                ("old_args", lambda: lib.grooved_box(1.0, 0.8, 0.9, 0.02, 0.01, 0.25, 0.6)),
                ("half_plank", lambda: lib.vault(2.0, 1.0, 0.6, 0.4, 12, 2.5, 0.02, 0.01))):
    try:
        call()
    except ValueError as e:
        out[k] = str(e)
print(json.dumps(out))
"""


@pytest.mark.blender
@pytest.mark.skipif(not os.access(BLENDER, os.X_OK), reason="needs Blender")
def test_vault_and_grooved_box_take_any_number_of_strips_and_stay_closed(tmp_path):
    """One function serves a lid of 2 boards, a roof of 5 tiles or a wall of 7 stone courses: the count is a param,
    so the counts gate can compare it (D30.6). planks 1 must give the plain vault, or graphs without grooves change.
    Every result is closed (0 open edges), because the gates take the union of the parts. A fractional count stops
    the build: a graph written for the old grooved_box(w, d, h, gap, depth, z1, z2) would pass z1 as rows."""
    script = tmp_path / "shapes.py"
    script.write_text(SHAPES, encoding="utf-8")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(script), "--", str(TOOLS / "custom_lib.py")],
                       capture_output=True, text=True)
    out = json.loads(next(line for line in r.stdout.splitlines() if line.startswith("{")))
    assert out == {"vault": [30, 0, [2.0, 1.0, 0.6]], "vault_planks_1": True, "vault_planks_3": [42, 0, [2.0, 1.0, 0.6]],
                   "box_rows_1": [8, 0, [1.0, 0.8, 0.9]], "box_rows_3": [-0.45, -0.16, -0.14, 0.14, 0.16, 0.45],
                   "box_pitch": [-0.45, -0.26, -0.24, 0.04, 0.06, 0.45], "box_open": 0,
                   "overlap": "grooves [0.15, 0.3, 0.45, 0.6, 0.75] of gap 0.2 do not fit apart inside h 0.9",
                   "old_args": "rows must be a whole number >= 1, got 0.25",
                   "half_plank": "planks must be a whole number >= 1, got 2.5"}
