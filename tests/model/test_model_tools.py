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
    s = {"asset": "pilot-house", "budget": {"max_tris_total": 3000, "max_materials_total": 1}, "dimensions_tolerance": 0.02,
         "uv": {"resolution": 2048, "min_padding_px": 16},
         "model": {"texel_min_px_per_m": 64, "uv_stretch": {"max_ratio": 2.0, "max_share": 0.05}},
         "sources": {"tris_cap": "preset tiers.standard"}} | over
    final.mkdir(parents=True, exist_ok=True)
    (final / "spec.json").write_text(json.dumps(s), encoding="utf-8")


@pytest.fixture
def make_spec(tmp_path):
    def run(card=None, profile=None, old=None, sources=SOURCES, light=None, expect=0):
        b, f = tmp_path / "blockout", tmp_path / "final"
        b.mkdir(exist_ok=True)
        f.mkdir(exist_ok=True)
        (b / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
        (tmp_path / "card").mkdir(exist_ok=True)
        (tmp_path / "card/asset-card.yaml").write_text(yaml.safe_dump(CARD | (card or {})), encoding="utf-8")
        (tmp_path / "profile.yaml").write_text(yaml.safe_dump(PROFILE | (profile or {})), encoding="utf-8")
        if old:
            (f / "spec.json").write_text(json.dumps(old), encoding="utf-8")
        r = tool("make_spec", "--final", f, "--blockout", b, "--card", tmp_path / "card/asset-card.yaml",
                 "--profile", tmp_path / "profile.yaml", "--preset", PRESET, *(["--light", light] if light else []))
        assert r.returncode == expect, r.stdout + r.stderr
        if expect:
            return r.stdout, None
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
        "camera": {"type": "persp", "azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40, "target_px_height": 400,
                   "screen": [1920, 1080], "distance_m": 19.752},
        "model": {"texel_min_px_per_m": 64.0, "relief_min_px": 3, "alpha_min_px": 16, "bevel": False,
                  "uv_stretch": {"max_ratio": 2.0, "max_share": 0.05},
                  "target_px_height": 400, "px_per_m": 75.11, "character_h": 1.6, "door_h": 1.8},
        "sources": {"tris_cap": "preset tiers.standard", "texture_res": "mặc định", "uv.padding_px": "preset",
                    "uv.texel_min_px_per_m": "preset", "detail.relief_min_px": "mặc định",
                    "detail.alpha_min_px": "mặc định", "bevel": "mặc định", "camera.target_px_height": "preset",
                    "screen_tris_max_small_ratio": "preset", "uv_stretch.max_ratio": "mặc định",
                    "uv_stretch.max_share": "mặc định", "dimensions": "sources.json layout",
                    "px_per_m": "camera.target_px_height / chiều cao bbox trên màn hình ở camera game",
                    "camera": "sources.json camera", "character_h": "sources.json", "door_h": "sources.json"}}
    assert "screen_tris" not in s and "sun" not in s


@pytest.mark.parametrize("layout, px_per_m, distance_m", [((4.0, 4.0, 3.7), 75.11, 19.752), ((4.0, 4.0, 0.5), 147.94, 10.029)])
def test_px_per_m_is_the_thumbnail_scale_and_the_camera_distance_puts_the_asset_at_target_px(
        make_spec, layout, px_per_m, distance_m):
    """From 35 deg above, a 4 x 4 x 0.5 m slab is 2.7 m tall on screen, not 0.5 m: 400 / 0.5 = 800 px/m made a 4 mm
    bump look like 3 px, while the thumbnail showed it at 0.6 px. The same screen height sets the fixed distance, so
    screen_tris_check measures at the game size and its limit can block."""
    _, s = make_spec(sources=SOURCES | {"layout": SOURCES["layout"] | dict(zip("wdh", layout))})
    assert (s["model"]["px_per_m"], s["camera"]["distance_m"]) == (px_per_m, distance_m)


def test_without_a_camera_px_per_m_falls_back_to_the_real_height(make_spec):
    _, s = make_spec(sources={k: v for k, v in SOURCES.items() if k != "camera"})
    assert ("camera" in s, s["model"]["px_per_m"]) == (False, 108.11)


def test_a_card_size_changed_after_blockout_approval_never_reaches_the_model_numbers_d22_13(make_spec):
    _, s = make_spec(card={"size_m": {"w": 9, "d": 9, "h": 9}})
    assert (s["dimensions_m"], s["sources"]["dimensions"]) == ({"pilot-house": [4.0, 4.0, 3.7]}, "sources.json layout")


def test_card_beats_profile_overrides_beat_preset_beat_skill_default_d13(make_spec):
    _, s = make_spec(card={"tris_max": 2400, "texture_res": 1024, "tier": "hero"},
                     profile={"overrides": {"uv": {"padding_px": 8}, "detail": {"relief_min_px": 4}}})
    assert (s["budget"]["max_tris_total"], s["uv"]["resolution"], s["uv"]["min_padding_px"],
            s["model"]["relief_min_px"]) == (2400, 1024, 4, 4)
    assert {k: s["sources"][k] for k in ("tris_cap", "texture_res", "uv.padding_px", "detail.relief_min_px")} == {
        "tris_cap": "thẻ asset tris_max", "texture_res": "thẻ asset", "uv.padding_px": "profile overrides; × 1024/2048",
        "detail.relief_min_px": "profile overrides"}


@pytest.mark.parametrize("res, pad", [(512, 4), (1024, 8), (2048, 16), (4096, 32)])
def test_uv_padding_is_stated_at_2048_and_scales_with_the_texture_resolution(make_spec, res, pad):
    """The same texel gap at every resolution: 16 px at 1024 doubled the kit table (8) and wasted atlas space."""
    _, s = make_spec(card={"texture_res": res})
    assert s["uv"]["min_padding_px"] == pad


TOON = {"style": "toon", "radius_m": 0.009, "segments": 2}


@pytest.mark.parametrize("card, style, want", [
    ({"bevel": "toon"}, None, (TOON, "thẻ asset bevel; số: preset bevel.toon")),
    ({}, "toon", (TOON, "profile style.bevel; số: preset bevel.toon")),
    ({"bevel": "none"}, "toon", (False, "thẻ asset bevel")),
    ({"bevel": None}, "toon", (TOON, "profile style.bevel; số: preset bevel.toon")),
    ({}, None, (False, "mặc định")),
])
def test_bevel_comes_from_the_card_field_over_the_profile_field_with_numbers_from_the_preset_d27_10(
        make_spec, card, style, want):
    profile = {"style": PROFILE["style"] | {"bevel": style}} if style else {}
    _, s = make_spec(card=card, profile=profile)
    assert (s["model"]["bevel"], s["sources"]["bevel"]) == want


@pytest.mark.parametrize("card, profile", [
    ({"real_texture_only_notes": ["real: thân hộp, mái vòm, cạnh bo toon."]}, {}),
    ({}, {"overrides": {"detail": {"bevel": True}}}),
])
def test_bevel_stays_off_for_notes_and_profile_overrides_because_only_the_two_fields_decide_it_d27_10(
        make_spec, card, profile):
    _, s = make_spec(card=card, profile=profile)
    assert (s["model"]["bevel"], s["sources"]["bevel"]) == (False, "mặc định")


def test_the_blockout_concept_masks_and_fitted_cameras_reach_the_model_spec(make_spec, tmp_path):
    """render_views.py draws overlay_* only from spec.concept; without it the model reviewer had no silhouette check.
    The masks live in the blockout work folder, which the purge removes, so the model keeps its own copy."""
    (tmp_path / "work/masks").mkdir(parents=True)
    for v in ("front", "34"):
        (tmp_path / f"work/masks/{v}.png").write_bytes(v.encode())
    (tmp_path / "work/spec.json").write_text(json.dumps({"concept": {
        "views": {"front": "masks/front.png", "34": "masks/34.png"}, "cameras": {"34": {"azimuth_deg": 45}}},
        "config": {"paths": {"blender": "/x"}}}), encoding="utf-8")
    (tmp_path / "blockout").mkdir()
    (tmp_path / "blockout/camera_fit.json").write_text(json.dumps({"data": {"cameras": {
        "34": {"azimuth_deg": 38.0, "elevation_deg": 27.0}}}}), encoding="utf-8")
    _, s = make_spec()
    assert ({k: s[k] for k in ("concept",) if k in s}, "config" in s, s["sources"]["concept"]) == (
        {"concept": {"views": {"front": "concept/front.png", "34": "concept/34.png"},
                     "cameras": {"34": {"azimuth_deg": 38.0, "elevation_deg": 27.0}}}},
        False, "blockout work/spec.json, camera_fit.json")
    assert [(tmp_path / f"final/concept/{v}.png").read_bytes() for v in ("front", "34")] == [b"front", b"34"]


def test_a_blockout_without_masks_gives_the_model_spec_no_concept(make_spec):
    _, s = make_spec()
    assert "concept" not in s


def test_a_rerun_keeps_the_sun_and_concept_camera_the_worker_set(make_spec):
    _, s = make_spec(old={"sun": {"azimuth_deg": 300, "elevation_deg": 40}, "budget": {"max_tris_total": 1}})
    assert (s["sun"], s["budget"]["max_tris_total"]) == ({"azimuth_deg": 300, "elevation_deg": 40}, 3000)


def with_camera_fit(tmp_path, az, el=20.0):
    (tmp_path / "blockout").mkdir(exist_ok=True)
    (tmp_path / "work/masks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "work/masks/front.png").write_bytes(b"x")
    (tmp_path / "work/spec.json").write_text(json.dumps({"concept": {"views": {"front": "masks/front.png"}}}), encoding="utf-8")
    (tmp_path / "blockout/camera_fit.json").write_text(json.dumps({"data": {"cameras": {
        "34": {"azimuth_deg": az, "elevation_deg": el}}}}), encoding="utf-8")


@pytest.mark.parametrize("light, sun", [
    ("from=left elevation=45", {"azimuth_deg": -45.0, "elevation_deg": 45.0}),
    ("from=right elevation=50", {"azimuth_deg": 45.0, "elevation_deg": 50.0}),
    ("from=front elevation=30", {"azimuth_deg": 0.0, "elevation_deg": 30.0})])
def test_the_light_of_the_card_gives_the_sun_in_the_front_view_when_no_concept_camera_is_known_g6(make_spec, light, sun):
    """Image left is -X in the front view, and sun azimuth 0 is the camera side, positive toward +X (render_review.light)."""
    out, s = make_spec(light=light)
    assert (s["sun"], s["sources"]["sun"]) == (sun, f"thẻ light ({light}), camera concept az 0")


@pytest.mark.parametrize("light, az", [("from=left elevation=45", -80.0), ("from=right elevation=45", 10.0),
                                       ("from=front elevation=45", -35.0)])
def test_a_34_concept_turns_the_sun_with_the_camera_that_drew_concept_shadow_g6(make_spec, tmp_path, light, az):
    """`left` is the left edge of the image, so with the camera at -35 deg the sun sits 45 deg further toward -X."""
    with_camera_fit(tmp_path, -35.0)
    _, s = make_spec(card={"view": "34", "view_side": "left"}, light=light)
    assert s["sun"] == {"azimuth_deg": az, "elevation_deg": 45.0}


def test_a_front_card_ignores_the_fitted_camera_of_concept_34_because_concept_shadow_shares_the_front_frame_g6(
        make_spec, tmp_path):
    with_camera_fit(tmp_path, -35.0)
    _, s = make_spec(card={"view": "front", "view_side": "left"}, light="from=left elevation=45")
    assert s["sun"]["azimuth_deg"] == -45.0


def test_the_concept_camera_the_worker_wrote_wins_and_the_azimuth_wraps_at_180_g6(make_spec):
    _, s = make_spec(old={"concept_cam": {"azimuth_deg": -150.0, "elevation_deg": 30}}, light="from=left elevation=45")
    assert s["sun"]["azimuth_deg"] == 165.0


def test_light_replaces_the_kept_sun_and_a_rerun_without_it_keeps_the_sun_g6(make_spec):
    old = {"sun": {"azimuth_deg": 300, "elevation_deg": 40}}
    _, s = make_spec(old=old, light="from=right elevation=20")
    assert s["sun"] == {"azimuth_deg": 45.0, "elevation_deg": 20.0}
    _, s = make_spec(old=old)
    assert s["sun"] == old["sun"] and "sun" not in s["sources"]


@pytest.mark.parametrize("light", ["from=up elevation=45", "from=left", "left 45"])
def test_a_light_value_that_is_not_the_brief_line_is_one_error_line_g6(make_spec, light):
    out, _ = make_spec(light=light, expect=2)
    assert out.startswith("[model/make_spec] error: ") and len(out.splitlines()) == 1


@pytest.mark.parametrize("card, old, want", [
    ({"bottom_visible": True}, None, True), ({"bottom_visible": False}, {"bottom_visible": True}, False),
    ({}, {"bottom_visible": True}, True), ({}, None, "absent")])
def test_bottom_visible_comes_from_the_card_and_survives_a_rerun_g6(make_spec, card, old, want):
    """The pilot-house card has no bottom_visible, so only the card or the earlier spec can set it."""
    _, s = make_spec(card=card, old=old)
    assert s.get("bottom_visible", "absent") == want


def inputs_of(tmp_path, card, views=True):
    names = {"blockout": ("part_graph.json", "parts_lib.py", "sources.json", "blockout.md", "assembly.json"),
             "views": ("front.png", "back.png", "left.png", "right.png"),
             "concept": ("concept_albedo.png", "concept_shadow.png")}
    for d, files in names.items():
        for n in files:
            (tmp_path / d).mkdir(exist_ok=True)
            (tmp_path / d / n).write_text("x", encoding="utf-8")
    (tmp_path / "concept/asset-card.yaml").write_text(card, encoding="utf-8")
    vs = ["--views", tmp_path / "views"] if views else []
    r = tool("check_inputs", "--final", tmp_path / "final", "--blockout", tmp_path / "blockout", *vs,
             "--concept", tmp_path / "concept")
    return r.returncode, result(tmp_path / "final", "inputs")[1]["inputs.views"]


def test_check_inputs_names_each_missing_file_the_brief_promised(tmp_path):
    (tmp_path / "blockout").mkdir()
    r = tool("check_inputs", "--final", tmp_path / "final", "--blockout", tmp_path / "blockout",
             "--views", tmp_path / "views", "--concept", tmp_path / "concept")
    assert (r.returncode, len(r.stdout.splitlines())) == (1, 1)
    assert result(tmp_path / "final", "inputs")[1]["inputs.concept"] == (
        "fail", ["concept/concept_albedo.png", "concept/concept_shadow.png", "concept/asset-card.yaml"])


@pytest.mark.parametrize("card, views, out", [
    ("views: full_top\n", True, (1, ("fail", ["views/top.png"]))),
    ("asset: x\n", True, (0, ("pass", []))),
    ("views: none\n", False, (0, ("pass", []))),
])
def test_check_inputs_wants_the_view_files_of_the_card_and_none_when_views_is_none_d35(tmp_path, card, views, out):
    """D35: the default set has no top, and `views: none` has no view set, so the model brief names no view folder."""
    assert inputs_of(tmp_path, card, views) == out


GRAPH = {"params": {"base_w": 4.0, "door_h": 1.8, "roof_h": 1.0}, "fixed_params": ["base_w", "door_h"]}


def parts(d, graph=GRAPH, **boxes):
    for name, (lo, hi) in boxes.items():
        write_glb(d / f"parts/{name}.glb", *box(lo, hi))
    ext = (np.max([hi for _, hi in boxes.values()], 0) - np.min([lo for lo, _ in boxes.values()], 0)).tolist()
    (d / "assembly.json").write_text(json.dumps({"data": {"parts": [{"name": n} for n in boxes],
                                                          "union": {"extents": ext}}}), encoding="utf-8")
    (d / "part_graph.json").write_text(json.dumps(graph), encoding="utf-8")


@pytest.fixture
def detail(tmp_path):
    b, f = tmp_path / "blockout", tmp_path / "final"
    parts(b, body=((0, 0, 0), (1, 1, 1.5)))
    parts(f, body=((0, 0, 0), (1, 1, 1)), lid=((0.25, 0.25, 1), (0.75, 0.75, 1.5)))
    write_glb(f / "pilot-house-untextured.glb", *join(box((0, 0, 0), (1, 1, 1)), box((0.25, 0.25, 1), (0.75, 0.75, 1.5))))
    return b, f


def test_detail_pass_adds_tris_under_the_cap_and_reports_density_without_a_pilot(detail):
    b, f = detail
    spec_of(f)
    assert tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none").returncode == 0
    overall, checks, data = result(f, "detail")
    assert (overall, checks) == ("pass", {"detail.more_tris": ("pass", 24), "detail.bbox": ("pass", [1.0, 1.0, 1.5]),
                                          "detail.fixed_params": ("pass", []), "detail.cap": ("pass", 24),
                                          "detail.density": ("info", 3.2), "detail.vs_pilot": ("not_checked", None)})
    assert data == {"blockout_part_tris": 12, "part_tris": 24, "bbox_ratio": [1.0, 1.0, 1.0], "tris": 24, "cap": 3000,
                    "area_m2": 7.5, "tris_per_m2": 3.2, "cap_source": "preset tiers.standard"}


def test_detail_fails_over_the_tier_cap_and_without_new_tris(detail, tmp_path):
    b, f = detail
    spec_of(f, budget={"max_tris_total": 20})
    parts(b, body=((0, 0, 0), (1, 1, 1.5)), crate=((0, 0, 0), (1, 1, 1)))
    assert tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none").returncode == 1
    assert {k: v for k, v in result(f, "detail")[1].items() if v[0] == "fail"} == {
        "detail.more_tris": ("fail", 24), "detail.cap": ("fail", 24)}


@pytest.mark.parametrize("top, want", [(1.52, "pass"), (1.6, "fail")])
def test_the_detail_pass_stays_within_2_percent_of_the_blockout_bbox(detail, top, want):
    """The approved blockout fixes the size; a lid that adds 10 cm to a 1.5 m prop changes what the owner approved."""
    b, f = detail
    spec_of(f)
    parts(f, body=((0, 0, 0), (1, 1, 1)), lid=((0.25, 0.25, 1), (0.75, 0.75, top)))
    tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none")
    assert result(f, "detail")[1]["detail.bbox"] == (want, [1.0, 1.0, top])


def test_a_fixed_param_the_model_changed_or_dropped_fails(detail):
    """fixed_params come from the map and the card (door height, base size); the model may not move them."""
    b, f = detail
    spec_of(f)
    parts(f, {"params": {"base_w": 4.0, "door_h": 2.0, "roof_h": 1.2}, "fixed_params": ["door_h"]},
          body=((0, 0, 0), (1, 1, 1)), lid=((0.25, 0.25, 1), (0.75, 0.75, 1.5)))
    assert tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none").returncode == 1
    assert result(f, "detail")[1]["detail.fixed_params"] == ("fail", ["base_w: bỏ khỏi fixed_params", "door_h: 1.8 → 2.0"])


def test_before_join_checks_the_parts_alone_into_its_own_file(detail):
    """Right after a build there is no GLB yet; the early run must not leave a detail.json without the cap check."""
    b, f = detail
    spec_of(f)
    (f / "pilot-house-untextured.glb").unlink()
    parts(f, body=((0, 0, 0), (1, 1, 1)), lid=((0.25, 0.25, 1), (0.75, 0.75, 1.6)))
    r = tool("check_detail", "--final", f, "--blockout", b, "--pilot", "none", "--before-join")
    assert (r.returncode, (f / "review/checks/detail.json").exists()) == (1, False)
    assert result(f, "detail_build")[1] == {"detail.more_tris": ("pass", 24), "detail.bbox": ("fail", [1.0, 1.0, 1.6]),
                                            "detail.fixed_params": ("pass", [])}


def test_density_is_compared_with_the_pilot_package_of_this_runtime_d22_10(detail, tmp_path):
    b, f = detail
    spec_of(f)
    write_glb(tmp_path / "deliver/pilot-prop/model/pilot-prop.glb", *box((0, 0, 0), (1, 1, 1)))
    tool("check_detail", "--final", f, "--blockout", b, "--pilot", tmp_path / "deliver/pilot-prop")
    _, checks, data = result(f, "detail")
    assert (checks["detail.vs_pilot"], data["pilot"]["tris_per_m2"]) == (("info", 1.6), 2.0)


def two_boxes(f, a, b, materials=1):
    parts(f, base=a, top=b)
    write_glb(f / "pilot-house-untextured.glb", *join(box(*a), box(*b)), materials=materials)


def test_check_mesh_finds_the_z_fight_of_an_inlay_flush_with_its_parent_top(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    two_boxes(f, ((0, 0, 0), (2, 2, 0.5)), ((0.5, 0.5, 0.4), (1, 1, 0.5)))
    assert tool("check_mesh", "--final", f).returncode == 1
    overall, checks, data = result(f, "mesh")
    assert (overall, checks["mesh.coplanar_overlap"], data["pairs"]) == ("fail", ("fail", 2), [
        {"faces": [2, 14], "at": [1.333, 0.667, 0.5]}, {"faces": [3, 15], "at": [0.667, 1.333, 0.5]}])


@pytest.mark.parametrize("top, want", [(0.3005, ("fail", 2)), (0.301, ("pass", 0))])
def test_an_inlay_under_1_mm_above_its_parent_is_z_fighting_and_1_mm_is_not(tmp_path, top, want):
    """model.md tells the worker to raise a part at least 1 mm; a 0.5 mm step still flickers on a phone depth buffer,
    and the check that enforces the rule must not fail the 1 mm the rule allows (stored as float32 in the GLB)."""
    f = tmp_path / "final"
    spec_of(f)
    two_boxes(f, ((0, 0, 0), (2, 2, 0.3)), ((0.5, 0.5, 0.2), (1, 1, top)))
    tool("check_mesh", "--final", f)
    assert result(f, "mesh")[1]["mesh.coplanar_overlap"] == want


def test_check_mesh_passes_a_box_standing_on_another_and_fails_two_materials(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    two_boxes(f, ((0, 0, 0), (2, 2, 0.5)), ((0.5, 0.5, 0.5), (1, 1, 1)), materials=2)
    tool("check_mesh", "--final", f)
    assert result(f, "mesh")[1] == {
        "mesh.part_winding": ("pass", []), "mesh.structure": ("fail", {"nodes": 1, "meshes": 1, "materials": 2}),
        "mesh.coplanar_overlap": ("pass", 0)}


def flipped(lo, hi):
    v, f = box(lo, hi)
    return v, f[:, ::-1]


def test_a_part_built_inside_out_fails_before_join(tmp_path):
    """A custom function may return faces in the wrong order; join_mesh then drops the whole part as hidden, so the
    worker must hear it right after the build. An open card part has no inside and is not judged."""
    f = tmp_path / "final"
    spec_of(f)
    parts(f, base=((0, 0, 0), (2, 2, 0.5)), lid=((0.5, 0.5, 0.5), (1, 1, 1)), card=((0, 0, 1), (1, 1, 1)))
    write_glb(f / "parts/lid.glb", *flipped((0.5, 0.5, 0.5), (1, 1, 1)))
    v, t = box((0, 0, 1), (1, 1, 1.2))
    write_glb(f / "parts/card.glb", v, t[:2])
    r = tool("check_mesh", "--final", f, "--before-join")
    assert (r.returncode, (f / "review/checks/mesh.json").exists()) == (1, False)
    overall, checks, data = result(f, "mesh_build")
    assert (overall, checks, data) == ("fail", {"mesh.part_winding": ("fail", ["lid"])}, {"open_parts": ["card"]})


def test_a_build_of_open_parts_only_leaves_winding_not_checked(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    parts(f, card=((0, 0, 0), (1, 1, 1)))
    v, t = box((0, 0, 0), (1, 1, 1))
    write_glb(f / "parts/card.glb", v, t[:2])
    assert tool("check_mesh", "--final", f, "--before-join").returncode == 0
    assert result(f, "mesh_build")[1] == {"mesh.part_winding": ("not_checked", [])}


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
        "uv.texel_islands": ("pass", 1024.0), "uv.stretch": ("pass", 0.0)})
    assert data["at_1024"] == {"edge_margin_px": 256.0, "texel_px_per_m": 512.0, "island_texel_min": 512.0,
                               "min_padding_px": 8.0, "texel_min_px_per_m": 32.0}


def test_an_island_4_px_from_the_atlas_border_fails_although_the_kit_only_measures_gaps_between_islands(tmp_path):
    rc, (_, checks, _) = uv_case(tmp_path, (0, 0, 1, 4 / 2048, 0.5))
    assert (rc, checks["uv.edge_margin_px"]) == (1, ("fail", 4.0))


def test_one_low_density_island_fails_although_the_global_texel_passes(tmp_path):
    rc, (_, checks, _) = uv_case(tmp_path, (0, 0, 1, 0.1, 0.4), (2, 0, 1, 0.6, 0.02))
    assert (rc, checks["uv.texel_px_per_m"], checks["uv.texel_islands"]) == (1, ("pass", 580.0), ("fail", 41.0))


def test_a_faceted_mesh_of_300_loose_triangles_is_measured_piece_by_piece_instead_of_crashing(tmp_path):
    """Every sharp edge splits the file's vertices, so a faceted mesh has no piece with 0.5 % of the surface; the check
    then had no island to measure and stopped with an error instead of a texel number."""
    f = tmp_path / "final"
    spec_of(f)
    k = np.arange(300)
    x, y = (k % 20).astype(float), (k // 20).astype(float)
    v = np.stack([np.c_[x, y, 0 * x], np.c_[x + 0.5, y, 0 * x], np.c_[x, y + 0.5, 0 * x]], 1).reshape(-1, 3)
    uv = np.stack([np.c_[x, y], np.c_[x + 0.5, y], np.c_[x, y + 0.5]], 1).reshape(-1, 2) / 30 + 0.1
    write_glb(f / "pilot-house-untextured.glb", v, np.arange(900).reshape(-1, 3), uv)
    assert tool("check_uv_edge", "--final", f).returncode == 0
    _, checks, data = result(f, "uv_edge")
    assert (checks["uv.texel_islands"], data["at_2048"]["islands_checked"]) == (("pass", 68.3), 300)


@pytest.mark.parametrize("sx, sy, want", [(0.3, 0.3, ("pass", 0.0)), (0.3, 0.1, ("fail", 1.0)), (0.3, 0.0, ("fail", 1.0))])
def test_a_uv_squeezed_3x_along_one_axis_fails_uv_stretch(tmp_path, sx, sy, want):
    """A texel density check passes a UV squeezed on one axis, yet every painted circle comes out an ellipse; a UV of
    zero area is stretch without end. The share is of the surface whose singular value ratio is over the limit."""
    f = tmp_path / "final"
    spec_of(f)
    v, t, uv = quad(0, 0, 1, 0, 1)
    write_glb(f / "pilot-house-untextured.glb", v, t, 0.1 + uv * (sx, sy))
    tool("check_uv_edge", "--final", f)
    assert result(f, "uv_edge")[1]["uv.stretch"] == want


def test_uv_stretch_is_not_checked_on_a_spec_made_before_its_limits(tmp_path):
    rc, (_, checks, _) = uv_case(tmp_path, (0, 0, 1, 0.25, 0.5))
    f = tmp_path / "final"
    spec_of(f, model={"texel_min_px_per_m": 64})
    tool("check_uv_edge", "--final", f)
    assert result(f, "uv_edge")[1]["uv.stretch"] == ("not_checked", None)


def test_a_mesh_without_uv_fails_uv_present(tmp_path):
    f = tmp_path / "final"
    spec_of(f)
    write_glb(f / "pilot-house-untextured.glb", *box((0, 0, 0), (1, 1, 1)))
    assert tool("check_uv_edge", "--final", f).returncode == 1
    assert result(f, "uv_edge")[1] == {"uv.present": ("fail", None)}


def test_round_parts_are_cylinders_bevel_boxes_and_custom_parts_marked_round_with_their_mirrors(tmp_path):
    """join_mesh keeps edges up to 60 deg smooth only in these parts; a box or an unmarked custom part keeps 20 deg,
    so its corners stay crisp. The kit copies only shape fields to a mirror, so the mark comes from the source."""
    def part(name, **kw):
        return {"name": name, "attach": {"type": "on_top", "to": "base"}, **kw}
    graph = {"params": {}, "parts": [
        {"name": "base", "primitive": "box", "attach": None}, part("post", primitive="cylinder"),
        part("chest", primitive="custom", fn="bevel_box"), part("knob", primitive="custom", fn="knob", round=True),
        {"name": "knob_r", "attach": {"type": "mirror_of", "of": "knob", "plane": "X"}},
        part("crate", primitive="custom", fn="crate"),
        {"name": "crate_r", "attach": {"type": "mirror_of", "of": "crate", "plane": "X"}}]}
    (tmp_path / "part_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    sys.path.insert(0, str(TOOLS))
    import join_mesh
    assert join_mesh.round_parts(tmp_path) == {"post", "chest", "knob", "knob_r"}
