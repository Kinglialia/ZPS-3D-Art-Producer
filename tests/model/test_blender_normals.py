"""Shading normals of the shipped GLB on the K18 fixture: a base, an 8-segment post and a chest (bevel_box, r 0.05 m,
2 segments on its 4 upright edges). The flat faces of the chest stay flat, its bevel strips and the post side shade
round. Needs the model tools/setup_deps.sh and Blender."""
import os
import sys

import numpy as np
import pytest

from modelkit import BLENDER, ROOT, ROUND, TOOLS, VPY, blender, build_shared, make_spec, read, sh

pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model tools/setup_deps.sh")]

ASSEMBLE = ROOT / "src/zps-3dp-producer/scripts/assemble_glb.py"
LARGE_M2 = 0.1
BEVEL_M2 = 0.05


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from PIL import Image
    d = tmp_path_factory.mktemp("normals")
    f = d / "round"
    build_shared(f, ROUND)
    make_spec(f, f)
    rc, out = blender("build_model.py", "--final", f)
    assert rc == 0, out
    Image.new("RGB", (64, 64), (128, 128, 128)).save(d / "albedo.png")
    rc, out = sh(BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", ASSEMBLE, "--",
                 "--glb", f / "pilot-house-untextured.glb", "--albedo", d / "albedo.png", "--name", "pilot-house",
                 "--out", d / "assembled")
    assert rc == 0, out
    return {"final": f, "untextured": f / "pilot-house-untextured.glb", "assembled": d / "assembled/pilot-house.glb"}


def corners(glb):
    """Positions (Z up), the NORMAL of each vertex, triangles, unit face normals and areas, as the GLB stores them."""
    sys.path.insert(0, str(TOOLS / "lib"))
    import glbread
    import optlib
    doc, binary = optlib.read_glb(glb)
    (prim,) = doc["meshes"][0]["primitives"]
    p = optlib._accessor_array(doc, binary, prim["attributes"]["POSITION"]).astype(float) @ glbread.GLTF_TO_ZUP
    n = optlib._accessor_array(doc, binary, prim["attributes"]["NORMAL"]).astype(float) @ glbread.GLTF_TO_ZUP
    f = optlib._accessor_array(doc, binary, prim["indices"]).reshape(-1, 3).astype(np.int64)
    t = p[f]
    fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    area = np.linalg.norm(fn, axis=1) / 2
    return p, n / np.linalg.norm(n, axis=1, keepdims=True), f, fn / (2 * area[:, None]), area


def deg(a, b):
    return np.degrees(np.arccos(np.clip(np.einsum("...j,...j->...", a, b), -1, 1)))


def parts(p, f, fn, area):
    """Triangles of the chest (x > -0.1) and of the post (x < -0.1) above the 0.2 m base, and the area of the plane
    each triangle lies in within its part."""
    c = p[f].mean(1)
    chest, post = (c[:, 0] > -0.1) & (c[:, 2] > 0.2001), (c[:, 0] < -0.1) & (c[:, 2] > 0.2001)
    plane = np.c_[np.round(fn * 1e3), np.round(np.einsum("mj,mj->m", fn, p[f[:, 0]]) * 1e3), chest]
    _, g = np.unique(plane, axis=0, return_inverse=True)
    return chest, post, np.bincount(g.ravel(), area)[g.ravel()]


@pytest.mark.parametrize("glb", ["untextured", "assembled"])
def test_every_corner_of_a_large_flat_face_keeps_the_face_normal(built, glb):
    """The owner saw a light gradient on the large chest faces towards the bevel: averaged normals tilted them 11.25
    deg. A flat face beside a bevel must read flat in the GLB the model step ships and in the one assemble packs."""
    p, n, f, fn, area = corners(built[glb])
    chest, post, plane = parts(p, f, fn, area)
    flat = (chest & (plane >= LARGE_M2)) | (post & (fn[:, 2] > 0.9999))
    assert (chest & (plane >= LARGE_M2)).sum() == 18 and (post & (fn[:, 2] > 0.9999)).sum() == 8
    assert deg(n[f[flat]], fn[flat][:, None]).max() < 2


def test_the_bevel_strip_blends_between_its_two_faces(built):
    """Only the strip carries the turn from one face to the next, so it still reads round, not as a third flat face."""
    p, n, f, fn, area = corners(built["untextured"])
    chest, _, plane = parts(p, f, fn, area)
    strip = np.where(chest & (plane < BEVEL_M2))[0]
    spread = [deg(n[f[i]][:, None], n[f[i]][None]).max() for i in strip]
    assert (len(strip), min(spread) > 20) == (16, True)


def test_the_post_side_stays_smooth_around(built):
    """Side faces of one cylinder have the same size, so each normal is the plain average of its two neighbours: the
    same normal on both sides of a shared edge, 22.5 deg from either face of an 8-segment side."""
    p, n, f, fn, area = corners(built["untextured"])
    _, post, _ = parts(p, f, fn, area)
    side = post & (np.abs(fn[:, 2]) < 0.5)
    corner_v, corner_fn = f[side].ravel(), np.repeat(fn[side], 3, axis=0)
    _, at = np.unique(np.round(p[corner_v] * 1e5), axis=0, return_inverse=True)
    gap = max(deg(n[corner_v[at.ravel() == k]][:, None], n[corner_v[at.ravel() == k]][None]).max()
              for k in range(at.max() + 1))
    tilt = deg(n[corner_v], corner_fn)
    assert (gap < 0.5, round(float(tilt.min()), 1), round(float(tilt.max()), 1)) == (True, 22.5, 22.5)


def test_the_sharp_edges_stay_split_as_before(built):
    data = read(built["final"] / "review/join.json")["data"]
    assert data["sharp_edges"] == {"base": 8, "post": 8, "chest": 12}
