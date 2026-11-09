import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/agents/zps-3dp-step-blockout"
TOOLS = AGENT / "tools"
HUT = json.loads((Path(__file__).parent / "fixtures/hut/part_graph.json").read_text(encoding="utf-8"))

HUT_ROWS = [
    {"name": "base", "parent": None, "contact": None, "depth": None,
     "bbox_min": [-2.0, -2.0, 0.0], "bbox_max": [2.0, 2.0, 0.3]},
    {"name": "walls", "parent": "base", "contact": {"axis": 2, "sign": 1}, "depth": None,
     "bbox_min": [-1.5, -1.5, 0.3], "bbox_max": [1.5, 1.5, 2.7]},
    {"name": "roof", "parent": "walls", "contact": {"axis": 2, "sign": 1}, "depth": None,
     "bbox_min": [-1.5, -1.5, 2.7], "bbox_max": [1.5, 1.5, 3.7]},
    {"name": "door", "parent": "walls", "contact": {"axis": 1, "sign": -1}, "depth": None,
     "bbox_min": [-0.45, -1.55, 0.3], "bbox_max": [0.45, -1.5, 2.1]},
    {"name": "crate", "parent": "base", "contact": {"axis": 2, "sign": 1}, "depth": None,
     "bbox_min": [1.515, -1.815, 0.3], "bbox_max": [1.815, -1.515, 0.6]},
    {"name": "crate_l", "parent": "base", "contact": {"axis": 2, "sign": 1}, "depth": None,
     "bbox_min": [-1.815, -1.815, 0.3], "bbox_max": [-1.515, -1.515, 0.6]},
]

HUT_SOURCES = {
    "files": {"layout": "", "layout_sha256": "x", "material": "", "material_sha256": "x"},
    "layout": {"w": 4.0, "d": 4.0, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
    "door_h": 1.8, "door_h_source": "asset-card.yaml scale_overrides cửa", "character_h": 1.6,
    "materials": ["STONE", "TIMBER", "TEAL"],
    "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40},
}


def hut():
    return copy.deepcopy(HUT)


def part(g, name):
    return next(p for p in g["parts"] if p["name"] == name)


def write_build(work: Path, graph=None, rows=None, sources=None, stale=False):
    work.mkdir(parents=True, exist_ok=True)
    pg = work / "part_graph.json"
    pg.write_text(json.dumps(graph or hut(), indent=2), encoding="utf-8")
    sha = hashlib.sha256(pg.read_bytes()).hexdigest()
    rows = copy.deepcopy(HUT_ROWS if rows is None else rows)
    asm = {"tool": "self_build/assembly", "overall": "pass", "source_sha256": "0" * 64 if stale else sha,
           "data": {"upto": len(rows), "parts_total": len(rows), "parts": rows}}
    (work / "assembly.json").write_text(json.dumps(asm), encoding="utf-8")
    (work / "sources.json").write_text(json.dumps(sources or HUT_SOURCES), encoding="utf-8")
    return work


class Result:
    def __init__(self, proc, out: Path):
        self.rc, self.lines = proc.returncode, proc.stdout.strip().splitlines()
        self.stderr = proc.stderr
        self.json = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None

    @property
    def overall(self):
        return self.json["overall"]

    def check(self, name):
        c = next(c for c in self.json["checks"] if c["check"] == name)
        return {k: c[k] for k in ("status", "value") if k in c}


@pytest.fixture
def run_check(tmp_path):
    def run(script, *args):
        out = tmp_path / f"{script}.result.json"
        proc = subprocess.run([sys.executable, str(TOOLS / f"{script}.py"), *map(str, args), "--out", str(out)],
                              capture_output=True, text=True)
        return Result(proc, out)
    return run
