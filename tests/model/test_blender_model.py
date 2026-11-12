"""Model tools on a real build in Blender (coding-checklist rows 6, 7): the hut blockout plus one detail part goes
through join, the kit xatlas unwrap, the model checks and the kit QA; an inlay flush with the base shows z-fighting.
Needs the model tools/setup_deps.sh and Blender."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from modelkit import (BLENDER, EAVE, INLAY, PILOT, ROUND, ROOT, STEP, TOOLS, VPY, blender, build, build_shared, make_spec,
                      read, sh)

pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model tools/setup_deps.sh")]


def checks(path):
    r = read(path)
    return r["overall"], {c["check"]: (c["status"], c.get("value")) for c in r["checks"]}


def model(final: Path, blockout: Path, **spec):
    make_spec(final, blockout, **spec)
    for script in ("join_mesh.py", "unwrap.py"):
        rc, out = blender(script, "--final", final)
        assert rc == 0, out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("model")
    b, f, g, wb, w = t / "blockout", t / "final", t / "inlay", t / "wide_blockout", t / "wide"
    e, under, flip, rnd = t / "eave", t / "bottom_visible", t / "inside_out", t / "round"
    mask(t / "work")
    build_shared(rnd, ROUND)
    model(rnd, rnd)
    build(b)
    build(f, [STEP])
    build(g, [INLAY])
    build(wb, wall_w=3.8, wall_d=3.8)
    build(w, wall_w=3.8, wall_d=3.8)
    build(e, [EAVE])
    build(under, [EAVE])
    build(flip, [STEP])
    inside_out(flip / "parts/step.glb")
    model(f, b)
    model(g, b)
    model(w, wb)
    model(e, b)
    model(under, b, bottom_visible=True)
    model(flip, b)
    rc = {"inside_out": sh(VPY, TOOLS / "check_mesh.py", "--final", flip, "--before-join")[0]}
    glb = f / "pilot-house-untextured.glb"
    for name in ("mesh", "uv_edge"):
        rc[name] = sh(VPY, TOOLS / f"check_{name}.py", "--final", f)[0]
    rc["detail"] = sh(VPY, TOOLS / "check_detail.py", "--final", f, "--blockout", b, "--pilot", "none")[0]
    rc["inlay"] = sh(VPY, TOOLS / "check_mesh.py", "--final", g)[0]
    for q in ("mesh_check", "uv_check", "export_check", "screen_tris_check"):
        rc[q] = blender(f"asset_checks/{q}.py", "--input", glb, "--spec", f / "spec.json",
                        "--out", f / f"review/checks/qa_{q}.json")[0]
    (f / "work").mkdir()
    (f / "work/spec_limit.json").write_text(json.dumps(read(f / "spec.json") | {"screen_tris": {"max_small_ratio": 1.0}}),
                                            encoding="utf-8")
    blender("asset_checks/screen_tris_check.py", "--input", glb, "--spec", f / "work/spec_limit.json",
            "--out", f / "work/screen_limit.json")
    blender("self_build/render_views.py", "--work", f, "--spec", f / "spec.json", "--mode", "critic",
            "--outdir", f / "review/renders")
    rc["normal"] = blender("self_build/render_views.py", "--input", glb, "--mode", "normal", "--outdir", f / "review/renders",
                           "--out", f / "review/renders/normal.json")[0]
    rc["render"] = blender("render_review.py", "--final", f, "--concept", PILOT / "_approved/pilot-house/concept_shadow.png",
                           "--size", "256")[0]
    return {"final": f, "inlay": g, "wide": w, "eave": e, "bottom_visible": under, "inside_out": flip, "round": rnd, "rc": rc}


def mask(work: Path):
    """The blockout's own spec with one front mask, the shape concept_mask.py writes (object white on black)."""
    from PIL import Image
    (work / "masks").mkdir(parents=True)
    im = np.zeros((200, 200), np.uint8)
    im[40:190, 30:170] = 255
    Image.fromarray(im).save(work / "masks/front.png")
    (work / "spec.json").write_text(json.dumps({"concept": {"views": {"front": "masks/front.png"}}}), encoding="utf-8")


def inside_out(glb: Path):
    sys.path.insert(0, str(TOOLS / "lib"))
    import glbread
    from test_model_tools import write_glb
    g = glbread.load(glb)
    write_glb(glb, g["v"], g["f"][:, ::-1])


def heights_up(glb: Path, xy, up=True) -> list[float]:
    """Heights of the up-facing (or down-facing) triangles a vertical line through xy crosses."""
    sys.path.insert(0, str(TOOLS / "lib"))
    import glbread
    g = glbread.load(glb)
    t = g["v"][g["f"]]
    up = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] * (1 if up else -1) > 0
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
        "join.parts": ("info", 7), "join.hidden_faces_removed": ("info", 20), "join.removed_faces_seen": ("pass", 0),
        "join.bottom_visible": ("info", False), "join.origin_offset_m": ("info", [0.0, 0.0, 0.0])}
    assert read(built["final"] / "review/join.json")["data"]["tris"] == 60


def test_the_ground_hides_the_underside_of_the_base_but_not_the_underside_of_an_eave(built):
    """A prop stands on the ground: its base underside is never on screen and only costs tris and texels. An eave
    high up looks down too, yet a low camera sees it, so only faces resting on the ground go."""
    glb = built["eave"] / "pilot-house-untextured.glb"
    assert (heights_up(glb, (1.9, 1.9), up=False), heights_up(glb, (0.7, -1.75), up=False)) == ([], [2.6])
    assert checks(built["eave"] / "review/join.json")[1]["join.removed_faces_seen"] == ("pass", 0)


def test_a_spec_with_a_visible_bottom_keeps_the_base_underside(built):
    glb = built["bottom_visible"] / "pilot-house-untextured.glb"
    assert heights_up(glb, (1.9, 1.9), up=False) == [0.0]
    assert checks(built["bottom_visible"] / "review/join.json")[1]["join.bottom_visible"] == ("info", True)


def test_a_part_built_inside_out_vanishes_in_the_join_unseen_so_check_mesh_fails_it_before(built):
    """Its faces look inwards, so every ray from them runs into the part and the join deletes all of it; the deleted
    faces show only their back to the view rays, so join.removed_faces_seen still passes."""
    d = built["inside_out"]
    assert (checks(d / "review/join.json")[1]["join.removed_faces_seen"], heights_up(d / "pilot-house-untextured.glb",
                                                                                     (0.0, -1.8))) == (("pass", 0), [0.3])
    assert (built["rc"]["inside_out"], checks(d / "review/checks/mesh_build.json")[1]) == (
        1, {"mesh.part_winding": ("fail", ["step"])})


def test_a_round_part_keeps_its_side_and_its_bevel_smooth_and_splits_only_caps_and_corners(built):
    """With one 20 deg limit an 8-segment cylinder (45 deg sides) and a 2-segment bevel (30 deg steps) came out faceted:
    16 and 24 split edges. Now the cylinder splits only its top rim (8) and the bevel_box only its top edges (12).
    The base box keeps its 8 hard edges (bottom ones are boundary after the ground removes the underside)."""
    data = read(built["round"] / "review/join.json")["data"]
    assert (data["round_parts"], data["sharp_edges"]) == (["chest", "post"], {"base": 8, "post": 8, "chest": 12})


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
        "mesh.part_winding": ("pass", []), "mesh.structure": ("pass", {"nodes": 1, "meshes": 1, "materials": 1}),
        "mesh.coplanar_overlap": ("pass", 0)})
    _, c = checks(f / "review/checks/detail.json")
    assert (c["detail.more_tris"], c["detail.cap"]) == (("pass", 80), ("pass", 60))
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


def test_the_blockout_mask_reaches_the_model_renders_as_an_overlay(built):
    files = {f["label"] for f in read(built["final"] / "review/renders/renders.json")["data"]["files"]}
    assert "overlay_front" in files


def test_normal_renders_come_from_the_joined_glb_and_keep_the_critic_render_list(built):
    """The critic renders draw the part build; a face the join flipped or deleted shows only on the joined GLB."""
    f = built["final"]
    data = read(f / "review/renders/normal.json")["data"]
    assert (built["rc"]["normal"], data["input"], sorted(x["label"] for x in data["files"])) == (
        0, str(f / "pilot-house-untextured.glb"), ["normal_34", "normal_back", "normal_front", "normal_left", "normal_right"])
    assert "clay_front" in {x["label"] for x in read(f / "review/renders/renders.json")["data"]["files"]}


def test_screen_tris_runs_at_the_fixed_game_camera_so_a_limit_blocks(built):
    """docs/agents/3d-artist.md §10: a profile limit blocks. Without distance_m the kit calibrated the camera and
    reported info whatever the limit; the fixed distance of make_spec shows the asset about target_px_height tall."""
    cam = read(built["final"] / "review/checks/qa_screen_tris_check.json")["data"]["camera"]
    assert (cam["mode"], abs(cam["asset_px_height"] / 400 - 1) < 0.1) == ("fixed", True)
    assert checks(built["final"] / "work/screen_limit.json")[1]["screen.small_tri_ratio"][0] == "pass"


def test_an_inlay_flush_with_the_base_top_is_reported_as_z_fighting(built):
    assert built["rc"]["inlay"] == 1
    assert checks(built["inlay"] / "review/checks/mesh.json")[1]["mesh.coplanar_overlap"][0] == "fail"


def test_the_review_set_renders_in_one_blender_run(built):
    assert built["rc"]["render"] == 0
    art = read(built["final"] / "review/review.json")["artifacts"]
    assert sorted(art) == ["clay_lit_concept", "lineup", "lit_34_back", "lit_34_front", "lit_front", "lit_game",
                           "model_sheet", "thumb", "uv_checker", "wire_34"]
    assert all(os.path.getsize(p) > 1000 for p in art.values())
    from PIL import Image
    assert Image.open(art["thumb"]).height == 400


def test_the_uv_checker_shows_the_colour_grid_on_the_model_not_the_clay(built):
    """The grid is what makes stretch visible; a render that fell back to clay grey would show nothing."""
    from PIL import Image
    im = np.asarray(Image.open(read(built["final"] / "review/review.json")["artifacts"]["uv_checker"]).convert("RGB"), int)
    colours = {tuple(c) for c in (im[::8, ::8] // 32).reshape(-1, 3).tolist()}
    assert len(colours) >= 12
