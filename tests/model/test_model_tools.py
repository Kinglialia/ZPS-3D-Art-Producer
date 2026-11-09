"""Model tools without Blender: the spec numbers and where they come from (D13, D22.13), the detail pass numbers, the
joined-mesh scan and the UV border check, on GLB files written here so every expected value is known."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model/tools"
PRESET = ROOT / "src/zps-3dp-producer/presets/topdown-mobile-lowpoly.yaml"
PILOT = ROOT / "tests/fixtures/pilot"
CARD = yaml.safe_load((PILOT / "_approved/pilot-house/asset-card.yaml").read_text(encoding="utf-8"))
PROFILE = yaml.safe_load((PILOT / "PROJECT-PROFILE.yaml").read_text(encoding="utf-8"))
SOURCES = {"layout": {"w": 4.0, "d": 4.0, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
           "door_h": 1.8, "character_h": 1.6, "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}}
ZUP = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])


def box(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
         (3, 0, 4), (3, 4, 7)]
    return np.array(v, float), np.array(f)


def join(*meshes):
    vs, fs, off = [], [], 0
    for v, f in meshes:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    return np.concatenate(vs), np.concatenate(fs)


def quad(x0, y0, side, u0, us):
    v = np.array([(x0, y0, 0), (x0 + side, y0, 0), (x0 + side, y0 + side, 0), (x0, y0 + side, 0)], float)
    uv = np.array([(u0, u0), (u0 + us, u0), (u0 + us, u0 + us), (u0, u0 + us)], float)
    return v, np.array([(0, 1, 2), (0, 2, 3)]), uv


def write_glb(path, v, f, uv=None, materials=1):
    sys.path.insert(0, str(TOOLS / "optimize"))
    import optlib
    blobs = [(np.asarray(v, float) @ ZUP.T).astype(np.float32), np.asarray(f, np.uint32).reshape(-1)]
    if uv is not None:
        blobs.append(np.asarray(uv, np.float32))
    views, acc, binary = [], [], b""
    for b, (kind, comp) in zip(blobs, (("VEC3", 5126), ("SCALAR", 5125), ("VEC2", 5126))):
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": b.nbytes})
        acc.append({"bufferView": len(acc), "componentType": comp, "count": len(b), "type": kind})
        binary += b.tobytes()
    acc[0] |= {"min": blobs[0].min(0).tolist(), "max": blobs[0].max(0).tolist()}
    attrs = {"POSITION": 0} | ({"TEXCOORD_0": 2} if uv is not None else {})
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": attrs, "indices": 1, "material": 0}]}],
           "materials": [{"name": f"m{i}"} for i in range(materials)], "accessors": acc, "bufferViews": views,
           "buffers": [{"byteLength": len(binary)}]}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    optlib.write_glb(str(path), doc, binary)


def tool(name, *args):
    r = subprocess.run([sys.executable, str(TOOLS / f"{name}.py"), *map(str, args)], capture_output=True, text=True)
    return r


def result(final, name):
    r = json.loads((final / f"review/checks/{name}.json").read_text(encoding="utf-8"))
    return r["overall"], {c["check"]: (c["status"], c.get("value")) for c in r["checks"]}, r["data"]


def spec_of(final, **over):
    s = {"asset": "pilot-house", "budget": {"max_tris_total": 3000, "max_materials_total": 1},
         "uv": {"resolution": 2048, "min_padding_px": 16}, "model": {"texel_min_px_per_m": 64},
         "sources": {"tris_cap": "preset tiers.standard"}} | over
    final.mkdir(parents=True, exist_ok=True)
    (final / "spec.json").write_text(json.dumps(s), encoding="utf-8")


@pytest.fixture
def make_spec(tmp_path):
    def run(card=None, profile=None, old=None):
        b, f = tmp_path / "blockout", tmp_path / "final"
        b.mkdir(exist_ok=True)
        f.mkdir(exist_ok=True)
        (b / "sources.json").write_text(json.dumps(SOURCES), encoding="utf-8")
        (tmp_path / "card").mkdir(exist_ok=True)
        (tmp_path / "card/asset-card.yaml").write_text(yaml.safe_dump(CARD | (card or {})), encoding="utf-8")
        (tmp_path / "profile.yaml").write_text(yaml.safe_dump(PROFILE | (profile or {})), encoding="utf-8")
        if old:
            (f / "spec.json").write_text(json.dumps(old), encoding="utf-8")
        r = tool("make_spec", "--final", f, "--blockout", b, "--card", tmp_path / "card/asset-card.yaml",
                 "--profile", tmp_path / "profile.yaml", "--preset", PRESET)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout, json.loads((f / "spec.json").read_text(encoding="utf-8"))
    return run


def test_the_spec_takes_geometry_from_sources_json_and_the_rest_from_preset_with_its_source_named(make_spec):
    out, s = make_spec()
    assert out.endswith(": tris cap 3000, texture 2048, padding 16 px, 4.0x4.0x3.7 m\n")
    assert {k: s[k] for k in ("asset", "objects", "budget", "dimensions_m", "dimensions_tolerance", "height_m", "pivot",
                              "uv", "camera", "model", "sources")} == {
        "asset": "pilot-house", "objects": ["pilot-house"], "budget": {"max_tris_total": 3000, "max_materials_total": 1},
        "dimensions_m": {"pilot-house": [4.0, 4.0, 3.7]}, "dimensions_tolerance": 0.02, "height_m": 3.7,
        "pivot": "bottom_center",
        "uv": {"resolution": 2048, "min_padding_px": 16, "allow_overlap": False, "allow_out_of_bounds": False},
        "camera": {"type": "persp", "azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40, "target_px_height": 400},
        "model": {"texel_min_px_per_m": 64.0, "relief_min_px": 3, "alpha_min_px": 16, "bevel": False,
                  "target_px_height": 400, "px_per_m": 108.11, "character_h": 1.6, "door_h": 1.8},
        "sources": {"tris_cap": "preset tiers.standard", "texture_res": "mặc định", "uv.padding_px": "preset",
                    "uv.texel_min_px_per_m": "preset", "detail.relief_min_px": "mặc định",
                    "detail.alpha_min_px": "mặc định", "detail.bevel": "mặc định", "camera.target_px_height": "preset",
                    "screen_tris_max_small_ratio": "preset", "dimensions": "sources.json layout",
                    "camera": "sources.json camera", "character_h": "sources.json", "door_h": "sources.json"}}
    assert "screen_tris" not in s and "sun" not in s


def test_a_card_size_changed_after_blockout_approval_never_reaches_the_model_numbers_d22_13(make_spec):
    _, s = make_spec(card={"size_m": {"w": 9, "d": 9, "h": 9}})
    assert (s["dimensions_m"], s["sources"]["dimensions"]) == ({"pilot-house": [4.0, 4.0, 3.7]}, "sources.json layout")


def test_card_beats_profile_overrides_beat_preset_beat_skill_default_d13(make_spec):
    _, s = make_spec(card={"tris_max": 2400, "texture_res": 1024, "tier": "hero"},
                     profile={"overrides": {"uv": {"padding_px": 8}, "detail": {"relief_min_px": 4}}})
    assert (s["budget"]["max_tris_total"], s["uv"]["resolution"], s["uv"]["min_padding_px"],
            s["model"]["relief_min_px"]) == (2400, 1024, 8, 4)
    assert {k: s["sources"][k] for k in ("tris_cap", "texture_res", "uv.padding_px", "detail.relief_min_px")} == {
        "tris_cap": "thẻ asset tris_max", "texture_res": "thẻ asset", "uv.padding_px": "profile overrides",
        "detail.relief_min_px": "profile overrides"}


def test_a_real_note_asking_for_rounded_edges_turns_bevel_on_over_the_profile_so_clay_review_does_not_send_it_back(
        make_spec):
    notes = ["real: thân hộp, nắp vòm, cạnh bo toon; chưa yêu cầu nội thất.", "real: tấm khóa vát góc có lỗ khóa."]
    _, s = make_spec(card={"real_texture_only_notes": notes},
                     profile={"overrides": {"detail": {"bevel": False}}})
    assert (s["model"]["bevel"], s["sources"]["detail.bevel"]) == (True, 'thẻ asset real_texture_only_notes "cạnh bo"')


@pytest.mark.parametrize("note", ["texture_only: viền gỗ bo cạnh chỉ vẽ, không dựng.", "real: cạnh sắc, không bo cạnh.",
                                  "real: tấm khóa vát góc có lỗ khóa.", "real: cạnh bonsai."])
def test_bevel_stays_off_for_paint_only_negated_or_corner_cut_notes(make_spec, note):
    _, s = make_spec(card={"real_texture_only_notes": [note]})
    assert (s["model"]["bevel"], s["sources"]["detail.bevel"]) == (False, "mặc định")


def test_a_rerun_keeps_the_sun_and_concept_camera_the_worker_set(make_spec):
    _, s = make_spec(old={"sun": {"azimuth_deg": 300, "elevation_deg": 40}, "budget": {"max_tris_total": 1}})
    assert (s["sun"], s["budget"]["max_tris_total"]) == ({"azimuth_deg": 300, "elevation_deg": 40}, 3000)


def test_check_inputs_names_each_missing_file_the_brief_promised(tmp_path):
    names = {"blockout": ("part_graph.json", "parts_lib.py", "sources.json", "blockout.md", "assembly.json"),
             "views_front": ("front.png",), "views_rest": ("back.png", "left.png", "right.png"),
             "concept": ("concept_albedo.png", "concept_shadow.png", "asset-card.yaml")}
    for d, files in names.items():
        for n in files:
            (tmp_path / d).mkdir(exist_ok=True)
            (tmp_path / d / n).write_text("x", encoding="utf-8")
    r = tool("check_inputs", "--final", tmp_path / "final", "--blockout", tmp_path / "blockout",
             "--views-front", tmp_path / "views_front", "--views-rest", tmp_path / "views_rest", "--concept", tmp_path / "concept")
    assert (r.returncode, len(r.stdout.splitlines())) == (1, 1)
    assert result(tmp_path / "final", "inputs")[:2] == ("fail", {
        "inputs.blockout": ("pass", []), "inputs.views": ("fail", ["views_rest/top.png"]), "inputs.concept": ("pass", [])})


def parts(d, **boxes):
    for name, (lo, hi) in boxes.items():
        write_glb(d / f"parts/{name}.glb", *box(lo, hi))
    (d / "assembly.json").write_text(json.dumps({"data": {"parts": [{"name": n} for n in boxes]}}), encoding="utf-8")


@pytest.fixture
def detail(tmp_path):
    b, f = tmp_path / "blockout", tmp_path / "final"
    parts(b, body=((0, 0, 0), (1, 1, 1)))
    parts(f, body=((0, 0, 0), (1, 1, 1)), lid=((0.25, 0.25, 1), (0.75, 0.75, 1.5)))
    write_glb(f / "pilot-house-untextured.glb", *join(box((0, 0, 0), (1, 1, 1)), box((0.25, 0.25, 1), (0.75, 0.75, 1.5))))
    return b, f


def test_detail_pass_adds_tris_under_the_cap_and_reports_density_without_a_pilot(detail):
    b, f = detail
    spec_of(f)
    assert tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none").returncode == 0
    overall, checks, data = result(f, "detail")
    assert (overall, checks) == ("pass", {"detail.more_tris": ("pass", 24), "detail.cap": ("pass", 24),
                                          "detail.density": ("info", 3.2), "detail.vs_pilot": ("not_checked", None)})
    assert data == {"blockout_part_tris": 12, "part_tris": 24, "tris": 24, "cap": 3000, "area_m2": 7.5,
                    "tris_per_m2": 3.2, "cap_source": "preset tiers.standard"}


def test_detail_fails_over_the_tier_cap_and_without_new_tris(detail, tmp_path):
    b, f = detail
    spec_of(f, budget={"max_tris_total": 20})
    parts(b, body=((0, 0, 0), (1, 1, 1)), crate=((2, 0, 0), (3, 1, 1)))
    assert tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none").returncode == 1
    assert {k: v for k, v in result(f, "detail")[1].items() if v[0] == "fail"} == {
        "detail.more_tris": ("fail", 24), "detail.cap": ("fail", 24)}


def test_density_is_compared_with_the_pilot_package_of_this_runtime_d22_10(detail, tmp_path):
    b, f = detail
    spec_of(f)
    write_glb(tmp_path / "deliver/wooden-chest/model/wooden-chest.glb", *box((0, 0, 0), (1, 1, 1)))
    tool("check_detail", "--final", f, "--blockout", b, "--pilot", tmp_path / "deliver/wooden-chest")
    _, checks, data = result(f, "detail")
    assert (checks["detail.vs_pilot"], data["pilot"]["tris_per_m2"]) == (("info", 1.6), 2.0)


def test_check_mesh_finds_the_z_fight_of_an_inlay_flush_with_its_parent_top(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    write_glb(f / "pilot-house-untextured.glb", *join(box((0, 0, 0), (2, 2, 0.5)), box((0.5, 0.5, 0.4), (1, 1, 0.5))))
    assert tool("check_mesh", "--final", f).returncode == 1
    overall, checks, data = result(f, "mesh")
    assert (overall, checks["mesh.coplanar_overlap"], data["pairs"]) == ("fail", ("fail", 2), [
        {"faces": [2, 14], "at": [1.333, 0.667, 0.5]}, {"faces": [3, 15], "at": [0.667, 1.333, 0.5]}])


def test_check_mesh_passes_a_box_standing_on_another_and_fails_two_materials(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    write_glb(f / "pilot-house-untextured.glb", *join(box((0, 0, 0), (2, 2, 0.5)), box((0.5, 0.5, 0.5), (1, 1, 1))),
              materials=2)
    tool("check_mesh", "--final", f)
    assert result(f, "mesh")[1] == {
        "mesh.structure": ("fail", {"nodes": 1, "meshes": 1, "materials": 2}), "mesh.coplanar_overlap": ("pass", 0)}


def uv_case(tmp_path, *quads):
    f = tmp_path / "final"
    spec_of(f)
    vs, fs, uvs, off = [], [], [], 0
    for q in quads:
        v, t, uv = quad(*q)
        vs.append(v)
        fs.append(t + off)
        uvs.append(uv)
        off += 4
    write_glb(f / "pilot-house-untextured.glb", np.concatenate(vs), np.concatenate(fs), np.concatenate(uvs))
    rc = tool("check_uv_edge", "--final", f).returncode
    return rc, result(f, "uv_edge")


def test_uv_border_and_texel_are_reported_at_2048_and_at_1024(tmp_path):
    rc, (overall, checks, data) = uv_case(tmp_path, (0, 0, 1, 0.25, 0.5))
    assert (rc, overall, checks) == (0, "pass", {
        "uv.present": ("pass", True), "uv.edge_margin_px": ("pass", 512.0), "uv.texel_px_per_m": ("pass", 1024.0),
        "uv.texel_islands": ("pass", 1024.0)})
    assert data["at_1024"] == {"edge_margin_px": 256.0, "texel_px_per_m": 512.0, "island_texel_min": 512.0,
                               "min_padding_px": 8.0, "texel_min_px_per_m": 32.0}


def test_an_island_4_px_from_the_atlas_border_fails_although_the_kit_only_measures_gaps_between_islands(tmp_path):
    rc, (_, checks, _) = uv_case(tmp_path, (0, 0, 1, 4 / 2048, 0.5))
    assert (rc, checks["uv.edge_margin_px"]) == (1, ("fail", 4.0))


def test_one_low_density_island_fails_although_the_global_texel_passes(tmp_path):
    rc, (_, checks, _) = uv_case(tmp_path, (0, 0, 1, 0.1, 0.4), (2, 0, 1, 0.6, 0.02))
    assert (rc, checks["uv.texel_px_per_m"], checks["uv.texel_islands"]) == (1, ("pass", 580.0), ("fail", 41.0))


def test_a_mesh_without_uv_fails_uv_present(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    write_glb(f / "pilot-house-untextured.glb", *box((0, 0, 0), (1, 1, 1)))
    assert tool("check_uv_edge", "--final", f).returncode == 1
    assert result(f, "uv_edge")[1] == {"uv.present": ("fail", None)}
