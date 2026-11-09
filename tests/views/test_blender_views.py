"""Views tools on real guide renders of the hut (checklist 13): kit render_blockout_views in Blender, then
diff_guides and measure. Needs Blender and the blockout tools venv (assembly.py)."""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BLOCKOUT = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-blockout/tools"
TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-views/tools"
VPY = BLOCKOUT / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
HUT = json.loads((ROOT / "tests/blockout/fixtures/hut/part_graph.json").read_text(encoding="utf-8"))
pytestmark = [pytest.mark.blender, pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                                      reason="needs Blender and the blockout tools/setup_deps.sh")]


def hut_with_back_window(x):
    g = copy.deepcopy(HUT)
    g["params"] |= {"win_w": 0.6, "win_h": 0.6, "win_t": 0.02}
    g["parts"].append({"name": "win", "primitive": "box", "dims": ["win_w", "win_t", "win_h"],
                       "attach": {"type": "center_on_face", "to": "walls", "face": "+Y", "offset_uv": [x, 0.2]},
                       "material": "GLASS", "role": "marker"})
    return g


def guides(work: Path, graph: dict) -> Path:
    work.mkdir(parents=True)
    (work / "part_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    r = subprocess.run([str(VPY), str(BLOCKOUT / "self_build/assembly.py"), "--work", str(work)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = work / "guides"
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(TOOLS / "render_blockout_views.py"), "--",
                        "--parts", str(work / "parts"), "--graph", str(work / "part_graph.json"), "--out", str(out),
                        "--res", "512"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return out


@pytest.fixture(scope="module")
def renders(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("views-blender")
    return tmp, guides(tmp / "old", hut_with_back_window(-0.5)), guides(tmp / "new", hut_with_back_window(0.5))


def tool(name, *args):
    """The agent's own venv when tools/setup_deps.sh built it, so these runs also prove that venv is complete."""
    py = TOOLS / ".deps/venv/bin/python"
    return subprocess.run([str(py if py.is_file() else sys.executable), str(TOOLS / f"{name}.py"), *map(str, args)],
                          capture_output=True, text=True)


def test_the_kit_render_gives_guide_and_id_for_every_view_and_one_id_colour_per_material(renders):
    _, old, _ = renders
    assert sorted(p.name for p in old.iterdir()) == sorted(
        ["views.json"] + [f"{v}_{k}.png" for v in ("front", "back", "left", "right", "top", "bottom") for k in ("guide", "id")])
    meta = json.loads((old / "views.json").read_text(encoding="utf-8"))
    assert meta["materials"] == {"GLASS": "#E6194B", "STONE": "#3CB44B", "TEAL": "#FFE119", "TIMBER": "#4363D8"}


def test_moving_a_back_window_changes_only_the_back_guide_so_only_back_is_generated_again(renders):
    tmp, old, new = renders
    r = tool("diff_guides", "--old", old, "--new", new, "--out", tmp / "diff.json")
    data = json.loads((tmp / "diff.json").read_text(encoding="utf-8"))
    assert (r.returncode, data["data"]["changed"]) == (0, ["back"]), r.stdout + r.stderr


def test_an_image_painted_inside_the_guide_silhouette_measures_as_a_pass(renders):
    tmp, old, _ = renders
    f = tmp / "final"
    f.mkdir()
    with Image.open(old / "front_id.png") as idimg:
        gen = Image.new("RGBA", idimg.size, "#E8E8E8")
        gen.alpha_composite(idimg.convert("RGBA"))
        gen.convert("RGB").resize((1536, 1536)).save(f / "front.png")
    r = tool("measure", "--final", f, "--guides", old, "--views", "front")
    rep = json.loads((f / "report/report.json").read_text(encoding="utf-8"))
    assert (r.returncode, rep["regen"], round(rep["views"]["front"]["iou"], 2)) == (0, [], 1.0), r.stdout + r.stderr
