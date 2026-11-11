"""fit_view.py finds a 3/4 concept camera on the -X side (negative azimuth), left of the footprint."""
import json
import subprocess

import pytest

from conftest import TOOLS

VPY = TOOLS / ".deps/venv/bin/python"
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not VPY.is_file(), reason="run tools/setup_deps.sh first (numpy, cv2, trimesh)")]
BUILD = """import sys
sys.path[:0] = [sys.argv[1] + "/lib", sys.argv[1] + "/self_build"]
import cv2, numpy as np, graph as G, raster
w, d, bump, az, el, out = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4] == "1", *map(float, sys.argv[5:7]), sys.argv[7]
v, t = G.box(w, d, 0.5)
v[:, 2] += 0.25
if bump:
    bv, bt = G.box(0.2, 0.3, 0.2)
    v, t = np.concatenate([v, bv + (-w / 2 - 0.1, 0, 0.3)]), np.concatenate([t, bt + len(v)])
G.save_glb(out + "/assembled.glb", v, t)
m = raster.normalize_to_bbox(raster.silhouette(v, t, raster.camera_dir(az, el), size=512)[0], 512)
cv2.imwrite(out + "/mask_34.png", m.astype(np.uint8) * 255)
"""


def concept(tmp_path, w, d, bump, az, el):
    subprocess.run([str(VPY), "-c", BUILD, str(TOOLS), str(w), str(d), "1" if bump else "0", str(az), str(el),
                    str(tmp_path)], check=True, capture_output=True, text=True)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"concept": {"views": {"34": "mask_34.png"}}}), encoding="utf-8")
    return spec


def fitted(script, tmp_path, spec, *args):
    out = tmp_path / f"{script.replace('/', '_')}.json"
    r = subprocess.run([str(VPY), str(TOOLS / script), "--work", str(tmp_path), "--spec", str(spec), "--out", str(out),
                        *args], capture_output=True, text=True)
    return r.returncode, json.loads(out.read_text(encoding="utf-8"))


def test_a_concept_drawn_from_the_minus_x_side_gets_a_negative_azimuth_and_the_left_side(tmp_path):
    spec = concept(tmp_path, 1.0, 0.6, True, -35, 20)
    rc, res = fitted("fit_view.py", tmp_path, spec, "--write-spec")
    cam = res["data"]["cameras"]["34"]
    assert rc == 0 and -40 <= cam["azimuth_deg"] <= -30 and 15 <= cam["elevation_deg"] <= 25, res["checks"]
    assert res["data"]["views"]["34"]["side"] == "left"
    assert json.loads(spec.read_text(encoding="utf-8"))["concept"]["cameras"]["34"] == cam


def test_side_decides_a_square_footprint_that_looks_the_same_from_both_sides(tmp_path):
    spec = concept(tmp_path, 0.8, 0.8, False, -30, 20)
    rc, res = fitted("fit_view.py", tmp_path, spec, "--side", "left")
    assert rc == 0 and -35 <= res["data"]["cameras"]["34"]["azimuth_deg"] <= -25, res["checks"]
    rc, res = fitted("fit_view.py", tmp_path, spec, "--side", "right")
    assert rc == 0 and 55 <= res["data"]["cameras"]["34"]["azimuth_deg"] <= 65, res["checks"]
