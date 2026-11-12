"""Shared pieces of the model tests: the hut blockout with detail parts and the worker's commands on them."""
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model/tools"
BLOCKOUT_TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-blockout/tools"
VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
PILOT = ROOT / "tests/fixtures/pilot"
PRESET = ROOT / "src/zps-3dp-producer/presets/topdown-mobile-lowpoly.yaml"
HUT = json.loads((ROOT / "tests/blockout/fixtures/hut/part_graph.json").read_text(encoding="utf-8"))
SOURCES = {"layout": {"w": 4.0, "d": 4.0, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
           "door_h": 1.8, "character_h": 1.6, "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}}
STEP = {"name": "step", "primitive": "box", "dims": ["step_w", "step_d", "step_h"], "material": "STONE", "role": "mass",
        "attach": {"type": "on_top", "to": "base", "offset_uv": [0.0, -0.9]}}
EAVE = {"name": "eave", "primitive": "box", "dims": ["eave_w", "eave_d", "eave_h"], "material": "TIMBER", "role": "mass",
        "attach": {"type": "center_on_face", "to": "walls", "face": "-Y", "offset_uv": [0.0, 1.0]}}
INLAY = {"name": "inlay", "primitive": "box", "dims": ["inlay_s", "inlay_s", "inlay_h"], "material": "STONE", "role": "marker",
         "attach": {"type": "inset_into", "to": "base", "face": "+Z", "offset_uv": [0.0, -0.875], "depth": "inlay_h"}}
ROUND = {"schema": "blockout-1", "version": "v01", "units": "m", "up": "+Z", "front": "-Y",
         "params": {"base_w": 2.0, "base_d": 1.0, "base_h": 0.2, "post_r": 0.2, "post_h": 0.8, "chest_w": 0.6,
                    "chest_d": 0.5, "chest_h": 0.4, "bevel_r": 0.05},
         "fixed_params": ["base_w"],
         "parts": [{"name": "base", "primitive": "box", "dims": ["base_w", "base_d", "base_h"], "attach": None,
                    "material": "STONE", "role": "mass"},
                   {"name": "post", "primitive": "cylinder", "dims": ["post_r", "post_h"], "segments": 8,
                    "attach": {"type": "on_top", "to": "base", "offset_uv": [-0.5, 0.0]}, "material": "STONE",
                    "role": "mass"},
                   {"name": "chest", "primitive": "custom", "fn": "bevel_box",
                    "args": ["chest_w", "chest_d", "chest_h", "bevel_r", 2, 15],
                    "attach": {"type": "on_top", "to": "base", "offset_uv": [0.5, 0.0]}, "material": "STONE",
                    "role": "mass"}]}
BASE_PARAMS = {"step_w": 1.0, "step_d": 0.3, "step_h": 0.15, "inlay_s": 0.3, "inlay_h": 0.05, "eave_w": 3.0,
               "eave_d": 0.5, "eave_h": 0.1}


def sh(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def blender(script, *args, exe=BLENDER):
    return sh(exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", TOOLS / script, "--", *args)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_graph(d: Path, graph: dict):
    d.mkdir(parents=True)
    (d / "part_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (d / "sources.json").write_text(json.dumps(SOURCES), encoding="utf-8")


def build(d: Path, extra=(), **params):
    """The hut plus detail parts, built in the venv the way the kit assembly builds a graph."""
    g = copy.deepcopy(HUT)
    g["parts"] += list(extra)
    g["params"] |= BASE_PARAMS | params
    write_graph(d, g)
    rc, out = sh(VPY, TOOLS / "self_build/assembly.py", "--work", d)
    assert rc == 0, out


def build_shared(d: Path, graph: dict):
    """A graph with a shared custom function (bevel_box), built in the venv by the blockout's build tool."""
    write_graph(d, graph)
    rc, out = sh(VPY, BLOCKOUT_TOOLS / "build_parts.py", "assembly", "--work", d)
    assert rc == 0, out


def make_spec(final: Path, blockout: Path, **spec):
    rc, out = sh(VPY, TOOLS / "make_spec.py", "--final", final, "--blockout", blockout,
                 "--card", PILOT / "_approved/pilot-house/asset-card.yaml", "--profile", PILOT / "PROJECT-PROFILE.yaml",
                 "--preset", PRESET)
    assert rc == 0, out
    (final / "spec.json").write_text(json.dumps(read(final / "spec.json") | spec), encoding="utf-8")


def gate_args(blockout: Path, pilot="none", joined=False):
    """The flags of `RUN gate_all.py` in the model folder, as the agent file gives them. The call before the join skips
    check_uv_edge and gives check_detail and check_mesh --before-join; the call after the join runs all three."""
    detail = f"check_detail=--blockout '{blockout}' --pilot '{pilot}'" + ("" if joined else " --before-join")
    args = ["--check-flag", "final", "--skip", "check_inputs", "--check-args", detail]
    return args + (["--check-args", "check_mesh=--before-join", "--skip", "check_uv_edge"] if not joined else [])


def gate_all(final: Path, *args):
    rc, out = sh(VPY, TOOLS / "gate_all.py", "--work", final, *args)
    return rc, out.strip().splitlines()
