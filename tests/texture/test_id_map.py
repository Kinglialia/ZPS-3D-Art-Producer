"""id_map matches each face of the joined mesh to its part triangle (row T18). The join keeps triangles exactly, so a
lookup by centroid cell finds the same part as a search over every part triangle, without an F x 4096 x 3 array
(about 490 MB per chunk at 5000 faces, enough to stop a pilot on a small machine)."""
import json
import sys
import tracemalloc
from pathlib import Path

import numpy as np

import glbkit
from texkit import TOOLS

sys.path.insert(0, str(TOOLS / "lib"))
sys.path.insert(0, str(TOOLS))
import id_map  # noqa: E402
import tex  # noqa: E402

OFFSET = [0.1234567, -2.3456789, 0.7501234]
CODES = ("TIMBER", "STONE", "TEAL")


def random_model(d: Path, faces=3000, seed=4):
    """Three parts of random small triangles; the join is their triangles moved by a non-round origin offset, stored
    as float32 like any GLB, so some centroids land on the other side of a cell border than their part's."""
    rng = np.random.default_rng(seed)
    v = rng.uniform(-1, 1, (faces, 3))[:, None, :] + rng.normal(0, 0.01, (faces, 3, 3))
    part = rng.integers(0, len(CODES), faces)
    (d / "parts").mkdir(parents=True)
    (d / "review").mkdir()
    for k in range(len(CODES)):
        tris = v[part == k].reshape(-1, 3)
        glbkit.write(d / "parts" / f"p{k}.glb", tris, np.zeros((len(tris), 2)), np.arange(len(tris)).reshape(-1, 3))
    joined = np.concatenate([v[part == k] for k in range(len(CODES))]).reshape(-1, 3) + OFFSET
    glbkit.write(d / "box-untextured.glb", joined, np.zeros((len(joined), 2)), np.arange(len(joined)).reshape(-1, 3))
    (d / "part_graph.json").write_text(json.dumps({"parts": [{"name": f"p{k}", "material": c}
                                                             for k, c in enumerate(CODES)]}), encoding="utf-8")
    (d / "review/join.json").write_text(json.dumps({"checks": [{"check": "join.origin_offset_m", "value": OFFSET}]}),
                                        encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"asset": "box", "uv": {"resolution": 64}}), encoding="utf-8")
    return d


def search_every_triangle(model):
    """The match before T18: the nearest part centroid of all, by brute force in chunks of 4096."""
    g = tex.read_glb(model / "box-untextured.glb")
    c = g["v"][g["f"]].mean(1)
    code, off = id_map.part_codes(str(model)), id_map.offset(str(model))
    cents, names = [], []
    for p in sorted((model / "parts").glob("*.glb")):
        q = tex.read_glb(p)
        cents.append(q["v"][q["f"]].mean(1) + off)
        names += [p.stem] * len(q["f"])
    cents = np.concatenate(cents)
    best, dist = np.zeros(len(c), int), np.full(len(c), np.inf)
    for s in range(0, len(cents), 4096):
        d = np.linalg.norm(c[:, None, :] - cents[None, s:s + 4096, :], axis=2)
        k = d.argmin(1)
        closer = d[np.arange(len(c)), k] < dist
        best[closer], dist[closer] = k[closer] + s, d[np.arange(len(c)), k][closer]
    return [code(names[b]) if d <= id_map.MATCH_M else id_map.UNKNOWN for b, d in zip(best, dist)]


def test_the_cell_lookup_gives_the_codes_of_the_search_over_every_triangle(tmp_path):
    m = random_model(tmp_path / "m")
    got, _ = id_map.face_codes(str(m))
    assert len(got) == 3000 and id_map.UNKNOWN not in got
    assert got == search_every_triangle(m)


def test_a_centroid_just_across_a_cell_border_is_still_its_part():
    cents = np.array([[0.002, 0.5, -0.003], [0.0035, 0.5, -0.003]])
    points = np.array([[0.0019999999, 0.5, -0.0030000001], [0.0027, 0.5, -0.003], [0.009, 0.5, -0.003]])
    assert id_map.nearest(points, cents, 1e-3).tolist() == [0, 0, -1]


def test_a_face_moved_off_its_part_is_still_unmatched(tmp_path):
    m = random_model(tmp_path / "m", faces=200)
    g = tex.read_glb(m / "box-untextured.glb")
    v = g["v"].copy()
    v[g["f"][7]] += 0.01
    glbkit.write(m / "box-untextured.glb", v, np.zeros((len(v), 2)), g["f"])
    got, _ = id_map.face_codes(str(m))
    assert [i for i, c in enumerate(got) if c == id_map.UNKNOWN] == [7]


def test_matching_5000_faces_needs_memory_of_the_order_of_the_mesh_not_faces_times_4096(tmp_path):
    m = random_model(tmp_path / "m", faces=5000)
    tracemalloc.start()
    id_map.face_codes(str(m))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 40e6, f"{peak / 1e6:.0f} MB"
