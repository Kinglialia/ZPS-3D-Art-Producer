"""Model tools on a real build in Blender (coding-checklist rows 6, 7): the hut blockout plus one detail part goes
through join, the kit xatlas unwrap, the model checks and the kit QA; an inlay flush with the base shows z-fighting.
Needs the model tools/setup_deps.sh and Blender."""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model/tools"
VPY = TOOLS / ".deps/venv/bin/python"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
PILOT = ROOT / "tests/fixtures/pilot"
HUT = json.loads((ROOT / "tests/blockout/fixtures/hut/part_graph.json").read_text(encoding="utf-8"))
SOURCES = {"layout": {"w": 4.0, "d": 4.0, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
           "door_h": 1.8, "character_h": 1.6, "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}}
STEP = {"name": "step", "primitive": "box", "dims": ["step_w", "step_d", "step_h"], "material": "STONE", "role": "mass",
        "attach": {"type": "on_top", "to": "base", "offset_uv": [0.0, -0.9]}}
INLAY = {"name": "inlay", "primitive": "box", "dims": ["inlay_s", "inlay_s", "inlay_h"], "material": "STONE", "role": "marker",
         "attach": {"type": "inset_into", "to": "base", "face": "+Z", "offset_uv": [0.0, -0.875], "depth": "inlay_h"}}
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model tools/setup_deps.sh")]


def sh(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def blender(script, *args):
    return sh(BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", TOOLS / script, "--", *args)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checks(path):
    r = read(path)
    return r["overall"], {c["check"]: (c["status"], c.get("value")) for c in r["checks"]}


def build(d: Path, extra=(), **params):
    d.mkdir(parents=True)
    g = copy.deepcopy(HUT)
    g["parts"] += list(extra)
    g["params"] |= {"step_w": 1.0, "step_d": 0.3, "step_h": 0.15, "inlay_s": 0.3, "inlay_h": 0.05} | params
    (d / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    (d / "sources.json").write_text(json.dumps(SOURCES), encoding="utf-8")
    rc, out = sh(VPY, TOOLS / "self_build/assembly.py", "--work", d)
    assert rc == 0, out


def model(final: Path, blockout: Path):
    rc, out = sh(VPY, TOOLS / "make_spec.py", "--final", final, "--blockout", blockout,
                 "--card", PILOT / "_approved/pilot-house/asset-card.yaml", "--profile", PILOT / "PROJECT-PROFILE.yaml",
                 "--preset", ROOT / "src/zps-3dp-producer/presets/topdown-mobile-lowpoly.yaml")
    assert rc == 0, out
    for script in ("join_mesh.py", "unwrap.py"):
        rc, out = blender(script, "--final", final)
        assert rc == 0, out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("model")
    b, f, g, wb, w = t / "blockout", t / "final", t / "inlay", t / "wide_blockout", t / "wide"
    build(b)
    build(f, [STEP])
    build(g, [INLAY])
    build(wb, wall_w=3.8, wall_d=3.8)
    build(w, wall_w=3.8, wall_d=3.8)
    model(f, b)
    model(g, b)
    model(w, wb)
    glb = f / "pilot-house-untextured.glb"
    rc = {}
    for name in ("mesh", "uv_edge"):
        rc[name] = sh(VPY, TOOLS / f"check_{name}.py", "--final", f)[0]
    rc["detail"] = sh(VPY, TOOLS / "check_detail.py", "--final", f, "--blockout", b, "--pilot", "none")[0]
    rc["inlay"] = sh(VPY, TOOLS / "check_mesh.py", "--final", g)[0]
    for q in ("mesh_check", "uv_check", "export_check", "screen_tris_check"):
        rc[q] = blender(f"asset_checks/{q}.py", "--input", glb, "--spec", f / "spec.json",
                        "--out", f / f"review/checks/qa_{q}.json")[0]
    blender("self_build/render_views.py", "--work", f, "--mode", "critic", "--outdir", f / "review/renders")
    rc["render"] = blender("render_review.py", "--final", f, "--concept", PILOT / "_approved/pilot-house/concept_shadow.png",
                           "--size", "256")[0]
    return {"final": f, "inlay": g, "wide": w, "rc": rc}


def heights_up(glb: Path, xy) -> list[float]:
    """Heights of the up-facing triangles a vertical line through xy crosses."""
    sys.path.insert(0, str(TOOLS / "lib"))
    import glbread
    g = glbread.load(glb)
    t = g["v"][g["f"]]
    up = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] > 0
    out = []
    for a, b, c in t[up]:
        m = np.array([[a[0] - c[0], b[0] - c[0]], [a[1] - c[1], b[1] - c[1]]])
        l1, l2 = np.linalg.solve(m, np.asarray(xy) - c[:2])
        if min(l1, l2, 1 - l1 - l2) >= -1e-9:
            out.append(round(float(l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2]), 4))
    return sorted(out)


def test_unwrap_runs_the_kit_xatlas_in_blender_without_the_rebake_mode_checklist_6(built):
    overall, c = checks(built["final"] / "review/unwrap.json")
    assert (overall, c["unwrap.how"], c["unwrap.border_inset_px"]) == ("info", ("info", "xatlas (in-process)"), ("info", 16))
    assert read(built["final"] / "review/unwrap.json")["warnings"] == []


def test_join_keeps_parts_apart_drops_the_faces_parts_hide_and_splits_sharp_edges(built):
    overall, c = checks(built["final"] / "review/join.json")
    assert {k: v for k, v in c.items() if k != "join.sharp_edges_split"} == {
        "join.parts": ("info", 7), "join.hidden_faces_removed": ("info", 18),
        "join.removed_faces_seen": ("pass", 0), "join.origin_offset_m": ("info", [0.0, 0.0, 0.0])}
    assert read(built["final"] / "review/join.json")["data"]["tris"] == 62


def test_join_keeps_the_10_cm_base_top_rim_around_3_8_m_walls_on_a_4_m_base(built):
    """The rim is the only visible part of the two base-top triangles; sampling them only near their corners, which sit
    under the walls, deleted the whole top and left a hole the camera sees."""
    _, c = checks(built["wide"] / "review/join.json")
    assert c["join.removed_faces_seen"] == ("pass", 0)
    glb = built["wide"] / "pilot-house-untextured.glb"
    assert [heights_up(glb, xy) for xy in ((1.95, 0.5), (-1.95, -1.0), (1.0, 1.95), (-0.7, -1.95))] == [[0.3]] * 4


def test_join_and_unwrap_leave_no_blend1_backup_in_final(built):
    """final/ is hashed at approval; a Blender .blend1 backup there changes the hash and ships a stale scene."""
    assert sorted(p.name for p in built["final"].glob("*.blend*")) == ["pilot-house.blend"]


def test_the_joined_mesh_passes_the_model_checks(built):
    f, rc = built["final"], built["rc"]
    assert (rc["mesh"], rc["uv_edge"], rc["detail"]) == (0, 0, 0)
    assert checks(f / "review/checks/mesh.json") == ("pass", {
        "mesh.structure": ("pass", {"nodes": 1, "meshes": 1, "materials": 1}), "mesh.coplanar_overlap": ("pass", 0)})
    _, c = checks(f / "review/checks/detail.json")
    assert (c["detail.more_tris"], c["detail.cap"]) == (("pass", 80), ("pass", 62))
    overall, c = checks(f / "review/checks/uv_edge.json")
    assert overall == "pass" and c["uv.edge_margin_px"][1] >= 16


def test_kit_qa_passes_the_unwelded_join_and_duplicate_vertices_stay_info_checklist_7(built):
    """Kit load_input welds exact duplicates of a GLB at 1e-6 m, so split edges count 0; without
    mesh.max_duplicate_verts in the spec the check stays info even when parts share a corner (D24.6)."""
    f, rc = built["final"], built["rc"]
    assert [rc[q] for q in ("mesh_check", "uv_check", "export_check", "screen_tris_check")] == [0, 0, 0, 0]
    overall, c = checks(f / "review/checks/qa_mesh_check.json")
    assert (overall, c["pilot-house.duplicate_verts"]) == ("pass", ("info", 0))
    assert [checks(f / f"review/checks/qa_{q}.json")[0] for q in ("uv_check", "export_check")] == ["pass", "pass"]


def test_an_inlay_flush_with_the_base_top_is_reported_as_z_fighting(built):
    assert built["rc"]["inlay"] == 1
    assert checks(built["inlay"] / "review/checks/mesh.json")[1]["mesh.coplanar_overlap"][0] == "fail"


def test_the_review_set_renders_in_one_blender_run(built):
    assert built["rc"]["render"] == 0
    art = read(built["final"] / "review/review.json")["artifacts"]
    assert sorted(art) == ["clay_lit_concept", "lineup", "lit_34_back", "lit_34_front", "lit_front", "lit_game",
                           "model_sheet", "thumb", "wire_34"]
    assert all(os.path.getsize(p) > 1000 for p in art.values())
    from PIL import Image
    assert Image.open(art["thumb"]).height == 400
