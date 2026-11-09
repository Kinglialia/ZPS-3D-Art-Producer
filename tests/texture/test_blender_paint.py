"""VẼ MỚI round trip in Blender (docs/agents/texture-artist.md §4; checklist 17): base fill → 8 paint guides →
projection back onto the UV. A small box stands in front of a big one, in another colour. With each paint view equal to
its guide (a painter who changes nothing), the projection must give the base fill back: a texel of the big box hidden
behind the small one in some view must not take the small box's colour. Needs Blender and the texture setup_deps.sh."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import glbkit
from texkit import TOOLS, tool

sys.path.insert(0, str(TOOLS / "lib"))
import tex  # noqa: E402

BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
RES = 128
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not ((TOOLS / ".deps").is_dir() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the texture tools/setup_deps.sh")]


def two_boxes(m: Path):
    v1, uv1, f1 = glbkit.box((1.0, 1.0, 1.0))
    v2, uv2, f2 = glbkit.box((0.3, 0.3, 0.4))
    v2 = v2 + np.array([0.0, -0.8, 0.0])
    v = np.concatenate([v1, v2])
    uv = np.concatenate([uv1 * [0.5, 1], uv2 * [0.5, 1] + [0.5, 0]])
    f = np.concatenate([f1, f2 + len(v1)])
    (m / "parts").mkdir(parents=True)
    (m / "review").mkdir()
    glbkit.write(m / "pair-untextured.glb", v, uv, f)
    glbkit.write(m / "parts/big.glb", v1, uv1, f1)
    glbkit.write(m / "parts/small.glb", v2, uv2, f2)
    (m / "part_graph.json").write_text(json.dumps({"parts": [{"name": "big", "material": "TIMBER"},
                                                             {"name": "small", "material": "STONE"}]}))
    (m / "review/join.json").write_text(json.dumps({"checks": [{"check": "join.origin_offset_m", "value": [0, 0, 0]}]}))
    (m / "spec.json").write_text(json.dumps({"asset": "pair", "uv": {"resolution": RES}}))


def test_projecting_unchanged_guides_gives_the_base_fill_back_and_respects_occlusion(tmp_path):
    m, paint = tmp_path / "model", tmp_path / "paint"
    two_boxes(m)
    (tmp_path / "cc.json").write_text(json.dumps({"TIMBER": "#8A5A3C", "STONE": "#3060C0"}))
    (tmp_path / "p.yaml").write_text("style: {light_convention: unlit_flat, top_vs_side_L: 0}\n")
    rc, out = tool("base_fill.py", "--final", tmp_path / "F", "--model", m, "--concept-colors", tmp_path / "cc.json",
                   "--profile", tmp_path / "p.yaml", "--res", RES, "--out", paint / "base_fill.png", "--padding", "2")
    assert rc == 0, out
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                        str(TOOLS / "render_paint_views.py"), "--", "--glb", str(m / "pair-untextured.glb"), "--albedo",
                        str(paint / "base_fill.png"), "--outdir", str(paint), "--width", "384", "--height", "256"], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    cams = json.loads((paint / "cameras.json").read_text())["views"]
    assert [(c["azimuth_deg"], c["elevation_deg"]) for c in cams] == [
        (0, 30), (45, -30), (90, 30), (135, -30), (180, 30), (225, -30), (270, 30), (315, -30)]
    for c in cams:
        shutil.copy(paint / c["guide"], paint / c["paint"])
    rc, out = tool("project_views.py", "--glb", m / "pair-untextured.glb", "--model", m, "--views", paint, "--base",
                   paint / "base_fill.png", "--res", RES, "--out", paint / "projected.png", "--padding", "2")
    assert rc == 0, out
    g, tm = tex.load_map(m / "pair-untextured.glb", RES)
    base, got = tex.load_rgb(paint / "base_fill.png"), tex.load_rgb(paint / "projected.png")
    diff = np.abs(base[tm.inside] - got[tm.inside]).max(-1)
    share = json.loads((paint / "projected.json").read_text())["share"]
    assert share["projected"] >= 0.9 and share["base"] == 0.0, share
    assert float((diff > 30).mean()) <= 0.01, float((diff > 30).mean())
