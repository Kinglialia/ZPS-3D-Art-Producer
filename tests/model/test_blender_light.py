"""The sun of the lit renders in real Blender (P6-1): a cube turned 45 degrees on a ground plane, lit by the light setter
of render_review.py (model) and of render_texture.py (texture), shot from the front at 30 degrees. Pilot 6: both tools
lit every clay render from below, so the ground and the top of the cube were in shadow and shadow_read could not be
judged. The studio light of Workbench is fixed to the view, so only shadows show where the sun is."""
import json
import os

import pytest

from modelkit import BLENDER, ROOT, TOOLS, VPY, sh

TEXTURE_TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-texture/tools"
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model tools/setup_deps.sh")]

PROBE = """
import json, sys
model, texture, tool, out, az, el = sys.argv[sys.argv.index("--") + 1:]
sys.path[:0] = [model + "/lib", model + "/self_build", model, texture]
import bpy
import numpy as np
import raster
import render_views as RV
r = 0.5 ** 0.5
ring = [(-r, 0), (0, -r), (r, 0), (0, r)]
cube = [(x, y, z) for z in (0.0, 1.0) for x, y in ring]
tris = [(4, 5, 6), (4, 6, 7), (0, 2, 1), (0, 3, 2)] + [t for i in range(4) for t in (
    (i, (i + 1) % 4, 4 + (i + 1) % 4), (i, 4 + (i + 1) % 4, 4 + i))]
ground = [(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)]
scene = RV.reset_scene(bpy)
RV.set_shading(scene, "clay")
RV.add_mesh(bpy, scene, "cube", cube, tris)
RV.add_mesh(bpy, scene, "ground", ground, [(0, 1, 2), (0, 2, 3)])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
sun = {"azimuth_deg": float(az), "elevation_deg": float(el)}
if tool == "model":
    import render_review
    render_review.light(scene, sun)
else:
    import render_texture
    render_texture.shading(scene, True, sun)
import render_review
v = np.array(cube + ground, float)
d = np.asarray(raster.camera_dir(0, 30), float)
render_review.shoot(bpy, scene, cam, v, d, 256, out)
from PIL import Image
im = np.asarray(Image.open(out).convert("L"), float)
right, up = raster._basis(d / np.linalg.norm(d))
pu, pv = v @ right, v @ up
span = 1.12 * max(pu.max() - pu.min(), pv.max() - pv.min())
cu, cv = (pu.max() + pu.min()) / 2, (pv.max() + pv.min()) / 2
def grey(p):
    p = np.asarray(p, float)
    x = round((p @ right - cu) / span * 256 + 128)
    y = round(128 - (p @ up - cv) / span * 256)
    return float(im[y - 2:y + 3, x - 2:x + 3].mean())
print("PROBE " + json.dumps({"left_face": grey((-r / 2, -r / 2, 0.5)), "top": grey((0, 0, 1)),
                             "ground_left": grey((-1.0, 0.6, 0)), "ground_right": grey((1.0, 0.6, 0))}))
"""


def probe(tmp_path, tool, side):
    script = tmp_path / "probe.py"
    script.write_text(PROBE, encoding="utf-8")
    az = {"left": -45, "right": 45}[side]
    rc, out = sh(BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", script, "--", TOOLS,
                 TEXTURE_TOOLS, tool, tmp_path / f"{tool}_{side}.png", az, 45)
    assert rc == 0, out
    return json.loads(next(x for x in out.splitlines() if x.startswith("PROBE "))[6:])


@pytest.mark.parametrize("tool", ["model", "texture"])
def test_a_sun_from_the_left_at_45_degrees_lights_the_top_and_casts_the_shadow_to_the_right_p6_1(tmp_path, tool):
    """`from: left` of the card is az -45 in the front view (make_spec). The ground right of the cube lies in its cast
    shadow; the ground left of it and the top face are in the sun. Mirrored for a sun from the right."""
    left, right = probe(tmp_path, tool, "left"), probe(tmp_path, tool, "right")
    assert left["ground_left"] - left["ground_right"] > 15, left
    assert right["ground_right"] - right["ground_left"] > 15, right
    assert (left["top"] - left["ground_right"] > 15, right["top"] - right["ground_left"] > 15) == (True, True)
    assert left["left_face"] - right["left_face"] > 15, (left, right)
