"""`custom` part functions (D33): the shared custom_lib.py holds only generic functions, and the asset's own functions
live in <PRODUCER_ROOT>/assets/<id>/custom_parts.py. build_parts.py runs only these two files, never code an agent
wrote into <work>/parts_lib.py, and it runs the asset file only after its static check passes."""
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
ROOF = "import bmesh\n\n\ndef ridge_roof(w, d, h):\n    bm = bmesh.new()\n    bmesh.ops.create_cube(bm, size=1.0)\n" \
       "    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)\n    return bm\n"


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
    """check_schema runs in plain Python: it reads the asset file's names with ast. Importing the file would raise
    SystemExit(3) and import bmesh, which plain Python does not have."""
    f = asset_dir(tmp_path, roof_graph(), f"raise SystemExit(3)\n{ROOF}")
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
    ("import os.path as p\n", "line 1: import os.path"),
    ("from subprocess import run\n", "line 1: from subprocess import"),
    ("from . import x\n", "line 1: from . import"),
    ("import socket\n", "line 1: import socket"),
    ("x = open('f', 'w')\n", "line 1: name open"),
    ("x = eval('1')\n", "line 1: name eval"),
    ("x = __import__('os')\n", "line 1: name __import__"),
    ("x = getattr(math, 'pi')\n", "line 1: name getattr"),
    ("x = ().__class__\n", "line 1: attribute __class__"),
    ("x = __builtins__\n", "line 1: name __builtins__"),
    ("def f(:\n", "line 1: syntax error: invalid syntax"),
])
def test_the_static_check_refuses_every_way_out_of_math_and_bmesh(src, error):
    """The asset file runs inside Blender with the user's rights; only geometry code may pass."""
    assert PP.static_errors(src) == [error]


def test_the_static_check_passes_plain_geometry_code():
    src = "import math\nimport bmesh\nfrom mathutils import Vector\n\n\ndef ring(r, seg):\n" \
          "    return [Vector((r * math.cos(i), 0.0, 0.0)) for i in range(int(seg))]\n"
    assert (PP.static_errors(src), PP.functions(src)) == ([], ["ring"])


def test_the_asset_file_is_found_only_above_a_folder_inside_assets_of_a_producer_root(tmp_path):
    f = asset_dir(tmp_path, hut(), ROOF)
    loose = tmp_path / "elsewhere/assets/hut/blockout/v1/final"
    loose.mkdir(parents=True)
    (loose.parents[2] / "custom_parts.py").write_text(ROOF, encoding="utf-8")
    assert (PP.find(f), PP.find(loose)) == (str(tmp_path / "production/assets/hut/custom_parts.py"), None)


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
def test_build_parts_refuses_an_asset_file_that_fails_the_static_check_before_it_runs(tmp_path):
    sentinel = tmp_path / "sentinel"
    f = asset_dir(tmp_path, roof_graph(), f"import os\nos.system('touch {sentinel}')\n{ROOF}")
    r = build(f, str(VPY))
    asm = read(f / "assembly.json")
    assert (r.returncode, asm["overall"], sentinel.exists()) == (1, "error", False)
    assert "custom_parts.py refused by the static check: line 1: import os; line 2: name os" in asm["data"]["error"]


@needs_venv
def test_build_parts_refuses_an_asset_function_named_like_a_library_function(tmp_path):
    """Either winner would run code its author did not expect, so a clash stops the build."""
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
def test_a_custom_part_builds_from_the_asset_file_and_parts_lib_records_both_files(tmp_path):
    """Reviewers read parts_lib.py as the code that ran, and the kit's code hash covers it, so it holds both files."""
    f = asset_dir(tmp_path, roof_graph(), ROOF)
    r = build(f, BLENDER, "-b", "--factory-startup", "--python")
    asm = read(f / "assembly.json")
    roof = next(p for p in asm["data"]["parts"] if p["name"] == "roof")
    assert (asm["overall"], roof["bbox_min"], roof["bbox_max"]) == ("pass", [-1.5, -1.5, 2.7], [1.5, 1.5, 3.7]), r.stdout
    lib = (TOOLS / "custom_lib.py").read_text(encoding="utf-8")
    assert (f / "parts_lib.py").read_text(encoding="utf-8") == f"{lib}\n\n{PP.MARK}\n{ROOF}"


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
try:
    lib.grooved_box(1.0, 0.8, 0.9, 0.2, 0.01, 6)
except ValueError as e:
    out["overlap"] = str(e)
print(json.dumps(out))
"""


@pytest.mark.blender
@pytest.mark.skipif(not os.access(BLENDER, os.X_OK), reason="needs Blender")
def test_vault_and_grooved_box_take_any_number_of_strips_and_stay_closed(tmp_path):
    """One function serves a lid of 2 boards, a roof of 5 tiles or a wall of 7 stone courses: the count is a param,
    so the counts gate can compare it (D30.6). planks 1 must give the plain vault, or graphs without grooves change.
    Every result is closed (0 open edges), because the gates take the union of the parts."""
    script = tmp_path / "shapes.py"
    script.write_text(SHAPES, encoding="utf-8")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(script), "--", str(TOOLS / "custom_lib.py")],
                       capture_output=True, text=True)
    out = json.loads(next(line for line in r.stdout.splitlines() if line.startswith("{")))
    assert out == {"vault": [30, 0, [2.0, 1.0, 0.6]], "vault_planks_1": True, "vault_planks_3": [42, 0, [2.0, 1.0, 0.6]],
                   "box_rows_1": [8, 0, [1.0, 0.8, 0.9]], "box_rows_3": [-0.45, -0.16, -0.14, 0.14, 0.16, 0.45],
                   "box_pitch": [-0.45, -0.26, -0.24, 0.04, 0.06, 0.45], "box_open": 0,
                   "overlap": "grooves [0.15, 0.3, 0.45, 0.6, 0.75] of gap 0.2 do not fit apart inside h 0.9"}
