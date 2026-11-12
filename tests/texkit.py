"""A model final/ the texture tools can read, without Blender: the glbkit box as the locked mesh, split into two parts
(four walls TIMBER, top and bottom STONE) as kit assembly.py would write them, join offset zero."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import glbkit

TOOLS = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer/agents/zps-3dp-step-texture/tools"
AID = "box"
WALLS, CAPS = ("-Y", "+Y", "-X", "+X"), ("-Z", "+Z")
COLORS = {"TIMBER": "#8A5A3C", "STONE": "#B8B0A0"}


def model_final(d: Path, res=128, parts=("walls", "caps"), mirror=()) -> Path:
    """mirror: names of the faces whose UV island is flipped left to right."""
    v, uv, f = glbkit.box()
    for n in mirror:
        k = list(glbkit.FACES).index(n) * 4
        uv[k:k + 4, 0] = uv[k:k + 4, 0].min() + uv[k:k + 4, 0].max() - uv[k:k + 4, 0]
    (d / "parts").mkdir(parents=True)
    (d / "review").mkdir()
    glbkit.write(d / f"{AID}-untextured.glb", v, uv, f)
    names = list(glbkit.FACES)
    for part, faces in (("walls", WALLS), ("caps", CAPS)):
        if part in parts:
            tris = [f[2 * names.index(n) + k] for n in faces for k in (0, 1)]
            glbkit.write(d / "parts" / f"{part}.glb", v, np.zeros((len(v), 2)), np.array(tris))
    (d / "part_graph.json").write_text(json.dumps({"parts": [
        {"name": "walls", "primitive": "box", "material": "TIMBER"},
        {"name": "caps", "primitive": "box", "material": "STONE"}]}), encoding="utf-8")
    (d / "review/join.json").write_text(json.dumps({"checks": [{"check": "join.origin_offset_m", "value": [0, 0, 0]}]}),
                                        encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"asset": AID, "uv": {"resolution": res}}), encoding="utf-8")
    return d


def face_name(face_index):
    return list(glbkit.FACES)[face_index // 2]


def tool(name, *args):
    r = subprocess.run([sys.executable, str(TOOLS / name), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr
