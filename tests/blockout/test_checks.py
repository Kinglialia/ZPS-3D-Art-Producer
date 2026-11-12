"""Pure blockout checks (docs/agents/blockout.md §5, §9): plain Python, one JSON, one line, exit 1 on fail."""
import copy
import json
import sys

import pytest

from conftest import HUT_ROWS, HUT_SOURCES, TOOLS, hut, part, write_build


def assert_pass(r):
    assert (r.rc, r.overall, len(r.lines)) == (0, "pass", 1), (r.lines, r.stderr)


def assert_fail(r):
    assert (r.rc, r.overall, len(r.lines)) == (1, "fail", 1), (r.lines, r.stderr)


# ---------------------------------------------------------------- check_schema
def test_schema_accepts_the_hut(tmp_path, run_check):
    assert_pass(run_check("check_schema", "--work", write_build(tmp_path / "w")))


def test_schema_rejects_two_parts_with_one_name_because_attach_and_gates_address_parts_by_name(tmp_path, run_check):
    g = hut()
    g["parts"].append(copy.deepcopy(part(g, "crate")))
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.names") == {"status": "fail", "value": ["crate"]}


def test_schema_reports_orphan_part_that_never_reaches_the_root(tmp_path, run_check):
    g = hut()
    part(g, "crate")["attach"]["to"] = "shed"
    part(g, "crate_l")["attach"] = None
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.connected") == {"status": "fail", "value": {"orphans": ["crate", "crate_l"], "cycles": []}}


def test_schema_reports_attach_cycle(tmp_path, run_check):
    g = hut()
    part(g, "walls")["attach"]["to"] = "roof"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.connected") == {"status": "fail",
                                           "value": {"orphans": ["door"], "cycles": [["roof", "walls"]]}}
    assert r.check("schema.order") == {"status": "fail", "value": ["walls"]}


def test_schema_rejects_primitive_the_kit_does_not_build(tmp_path, run_check):
    g = hut()
    part(g, "roof")["primitive"] = "prism"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.primitive") == {"status": "fail", "value": ["roof"]}


def test_schema_rejects_rotation_not_a_quarter_turn(tmp_path, run_check):
    g = hut()
    part(g, "crate")["rotation_deg"] = 45
    part(g, "door")["rotation_deg"] = 270
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.rotation") == {"status": "fail", "value": ["crate"]}


def test_schema_rejects_segments_outside_8_to_24(tmp_path, run_check):
    g = hut()
    g["params"]["seg"] = 6
    g["parts"].append({"name": "pole", "primitive": "cylinder", "dims": ["crate_s", "wall_h"], "segments": "seg",
                       "attach": {"type": "on_top", "to": "base"}, "material": "TIMBER", "role": "mass"})
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.segments") == {"status": "fail", "value": ["pole"]}


def test_schema_needs_mirror_part_to_carry_its_own_material_role_and_tag(tmp_path, run_check):
    """The kit copies only shape fields to a mirror_of part, so labels must be written on it."""
    g = hut()
    del part(g, "crate_l")["material"]
    part(g, "crate")["tag"] = "base"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.fields") == {"status": "fail", "value": ["crate_l: material", "crate_l: tag"]}


MIRROR_CASES = {
    "inset_into": {"type": "inset_into", "to": "walls", "face": "+X", "depth": "door_t"},
    "through_axis": {"type": "through_axis", "to": "walls", "axis": "Y", "offset_uv": [0.5, 0.0]},
    "parent_off_plane": {"type": "on_top", "to": "crate"},
}


@pytest.mark.parametrize("case", MIRROR_CASES)
def test_schema_rejects_mirror_the_kit_gates_cannot_check(tmp_path, run_check, case):
    """The kit mirror copies the source's parent, contact and depth: gates.py crashes on a through_axis source
    (contact None), measures an inset as penetration, and finds no contact when the parent is on the other side."""
    g = hut()
    g["parts"] += [{"name": "peg", "primitive": "box", "dims": ["crate_s"] * 3, "attach": MIRROR_CASES[case],
                    "material": "TIMBER", "role": "mass"},
                   {"name": "peg_l", "attach": {"type": "mirror_of", "of": "peg", "plane": "X"},
                    "material": "TIMBER", "role": "mass"}]
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.mirror") == {"status": "fail", "value": ["peg_l"]}
    assert next(c for c in r.json["checks"] if c["check"] == "schema.mirror")["note"] == \
        "write these parts explicitly (own primitive, dims and attach), not as mirror_of"


def test_schema_accepts_mirror_of_a_child_of_a_part_centred_on_the_plane_and_a_mirror_of_a_mirror(tmp_path, run_check):
    """A mirror of a mirror keeps the first source's parent (a pilot graph built this way passed every gate)."""
    g = hut()
    g["parts"] += [{"name": "sign", "primitive": "box", "dims": ["crate_s"] * 3,
                    "attach": {"type": "on_top", "to": "walls", "offset_uv": [0.5, 0.0]}, "material": "TIMBER",
                    "role": "mass"},
                   {"name": "sign_l", "attach": {"type": "mirror_of", "of": "sign", "plane": "X"},
                    "material": "TIMBER", "role": "mass"},
                   {"name": "crate_bl", "attach": {"type": "mirror_of", "of": "crate_l", "plane": "Y"},
                    "material": "TIMBER", "role": "mass"}]
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_pass(r)
    assert r.check("schema.mirror") == {"status": "pass", "value": []}


def test_schema_needs_fixed_params_with_reason(tmp_path, run_check):
    g = hut()
    g["fixed_params"] = ["base_w", "eave"]
    del g["_fixed_reason"]
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.fixed_params") == {"status": "fail", "value": ["_fixed_reason", "eave: not in params"]}


def test_schema_rejects_wrong_header_and_enums(tmp_path, run_check):
    g = hut()
    g["schema"], g["front"] = "blockout-0", "+Y"
    part(g, "door")["role"] = "detail"
    part(g, "roof")["tag"] = "Roof"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.header") == {"status": "fail", "value": ["front", "schema"]}
    assert r.check("schema.enums") == {"status": "fail", "value": ["door: role", "roof: tag"]}


def test_schema_accepts_a_tag_named_after_a_counts_key(tmp_path, run_check):
    """D30.6: a card count is carried by parts with `tag: <key>`, and the key is the project's word, not the skill's."""
    g = hut()
    part(g, "crate")["tag"] = "crates"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert r.check("schema.enums") == {"status": "pass", "value": []}


# ---------------------------------------------------------------- check_materials
def test_materials_pass_when_every_code_is_in_sources(tmp_path, run_check):
    assert_pass(run_check("check_materials", "--work", write_build(tmp_path / "w")))


def test_materials_reject_guessed_code_and_missing_mirror_material(tmp_path, run_check):
    """Blockout must not guess a material code (D3.1)."""
    g = hut()
    part(g, "roof")["material"] = "SLATE"
    del part(g, "crate_l")["material"]
    r = run_check("check_materials", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("materials.known") == {"status": "fail", "value": ["crate_l: None", "roof: SLATE"]}


# ---------------------------------------------------------------- check_layout
def test_layout_passes_within_two_percent(tmp_path, run_check):
    s = copy.deepcopy(HUT_SOURCES)
    s["layout"]["h"] = 3.65
    r = run_check("check_layout", "--work", write_build(tmp_path / "w", sources=s))
    assert_pass(r)
    assert r.json["data"]["deviation"] == [0.0, 0.0, 0.0137]


def test_layout_fails_when_bbox_is_off_by_three_percent(tmp_path, run_check):
    s = copy.deepcopy(HUT_SOURCES)
    s["layout"]["w"] = 4.12
    r = run_check("check_layout", "--work", write_build(tmp_path / "w", sources=s))
    assert_fail(r)
    assert r.check("layout.bbox") == {"status": "fail", "value": 0.0291}
    assert r.json["data"]["built"] == [4.0, 4.0, 3.7]


def test_layout_without_base_measures_parts_above_the_base(tmp_path, run_check):
    """MAP-LAYOUT may give the size without the plinth (includes_base: false)."""
    s = copy.deepcopy(HUT_SOURCES)
    s["layout"].update({"w": 3.63, "d": 3.315, "h": 3.4, "includes_base": False})
    r = run_check("check_layout", "--work", write_build(tmp_path / "w", sources=s))
    assert_pass(r)
    assert r.json["data"]["built"] == [3.63, 3.315, 3.4]


def test_layout_fails_on_stale_assembly(tmp_path, run_check):
    r = run_check("check_layout", "--work", write_build(tmp_path / "w", stale=True))
    assert_fail(r)
    assert r.check("assembly.fresh")["status"] == "fail"


def partial_build(tmp_path, upto, total=6, rows=3):
    """An assembly.json written by `assembly.py --upto`: the first `rows` parts of the graph."""
    w = write_build(tmp_path / "w", rows=HUT_ROWS[:rows])
    path = w / "assembly.json"
    asm = json.loads(path.read_text(encoding="utf-8"))
    asm["data"].update(upto=upto, parts_total=total)
    path.write_text(json.dumps(asm), encoding="utf-8")
    return w


def test_layout_fails_on_a_partial_build_even_when_its_bbox_matches_because_the_last_parts_are_still_unchecked(
        tmp_path, run_check):
    """The base, walls and roof already span the whole 4 x 4 x 3.7 box, so a bbox-only check would pass a half-built hut."""
    r = run_check("check_layout", "--work", partial_build(tmp_path, upto=3))
    assert_fail(r)
    assert r.check("layout.bbox")["status"] == "pass"
    assert r.check("layout.complete") == {"status": "fail", "value": {"upto": 3, "parts_total": 6}}


@pytest.mark.parametrize("upto", [6, None])
def test_layout_passes_a_full_build_whether_or_not_upto_was_given(tmp_path, run_check, upto):
    r = run_check("check_layout", "--work", partial_build(tmp_path, upto=upto, rows=6))
    assert_pass(r)
    assert r.check("layout.complete")["status"] == "pass"


def test_the_other_checks_still_run_on_a_partial_build_because_only_layout_judges_completeness(tmp_path, run_check):
    w = partial_build(tmp_path, upto=3)
    assert run_check("check_base", "--work", w).overall == "pass"


# ---------------------------------------------------------------- check_base
def test_base_measures_edge_margin_of_parts_on_the_base(tmp_path, run_check):
    r = run_check("check_base", "--work", write_build(tmp_path / "w"))
    assert_pass(r)
    assert r.json["data"]["margin"] == {"walls": 0.5, "crate": 0.185, "crate_l": 0.185}


def test_base_fails_when_a_part_sits_closer_than_10_cm_to_the_edge(tmp_path, run_check):
    rows = copy.deepcopy(HUT_ROWS)
    rows[4]["bbox_min"][0], rows[4]["bbox_max"][0] = 1.62, 1.92
    r = run_check("check_base", "--work", write_build(tmp_path / "w", rows=rows))
    assert_fail(r)
    assert r.check("base.edge_margin") == {"status": "fail", "value": ["crate"]}
    assert r.json["data"]["margin"]["crate"] == 0.08


def small_base_rows(margin):
    """A 0.4 m square plinth (a lantern, a pot, a milestone) with a 0.1 m cube whose left side is `margin` from its edge."""
    return [
        {"name": "base", "parent": None, "contact": None, "depth": None,
         "bbox_min": [-0.2, -0.2, 0.0], "bbox_max": [0.2, 0.2, 0.05]},
        {"name": "post", "parent": "base", "contact": {"axis": 2, "sign": 1}, "depth": None,
         "bbox_min": [-0.2 + margin, -0.05, 0.05], "bbox_max": [-0.1 + margin, 0.05, 0.4]},
    ]


def small_base_graph():
    return {"parts": [{"name": "base", "tag": "base"}, {"name": "post"}]}


def test_base_margin_shrinks_with_a_small_base_because_a_fixed_10_cm_cannot_fit_a_pot_or_a_lantern(tmp_path, run_check):
    """0.1 m of margin on a 0.4 m base would leave a 0.2 m centred part at most. A part 3 cm from the edge of a
    plinth that small is placed on purpose, so the check must not call it a fault."""
    w = write_build(tmp_path / "w", small_base_graph(), small_base_rows(0.03), HUT_SOURCES)
    r = run_check("check_base", "--work", w)
    assert_pass(r)
    assert r.json["data"]["margin"] == {"post": 0.03}


def test_base_still_fails_a_part_that_hangs_over_the_edge_of_a_small_base(tmp_path, run_check):
    w = write_build(tmp_path / "w", small_base_graph(), small_base_rows(0.005), HUT_SOURCES)
    r = run_check("check_base", "--work", w)
    assert_fail(r)
    assert r.check("base.edge_margin") == {"status": "fail", "value": ["post"]}


def test_base_is_not_checked_without_a_base_tag(tmp_path, run_check):
    g = hut()
    del part(g, "base")["tag"]
    r = run_check("check_base", "--work", write_build(tmp_path / "w", g))
    assert (r.rc, r.overall) == (0, "not_checked")


# ---------------------------------------------------------------- check_support
def test_support_finds_walls_under_the_roof(tmp_path, run_check):
    r = run_check("check_support", "--work", write_build(tmp_path / "w"))
    assert_pass(r)
    assert r.json["data"]["support"] == {"roof": ["walls"]}


def test_support_fails_when_the_roof_floats_2_cm_above(tmp_path, run_check):
    rows = copy.deepcopy(HUT_ROWS)
    rows[2]["bbox_min"][2], rows[2]["bbox_max"][2] = 2.72, 3.72
    r = run_check("check_support", "--work", write_build(tmp_path / "w", rows=rows))
    assert_fail(r)
    assert r.check("support.roof") == {"status": "fail", "value": ["roof"]}


def test_support_fails_when_a_roof_rests_only_on_another_roof_beside_it_at_the_same_height(tmp_path, run_check):
    g = hut()
    g["parts"].append(copy.deepcopy(part(g, "roof")) | {"name": "roof_b"})
    rows = copy.deepcopy(HUT_ROWS)
    rows[1]["bbox_max"][2] = 2.6
    rows.append(copy.deepcopy(rows[2]) | {"name": "roof_b", "bbox_min": [-1.0, -1.5, 2.7], "bbox_max": [2.0, 1.5, 3.4]})
    r = run_check("check_support", "--work", write_build(tmp_path / "w", g, rows=rows))
    assert_fail(r)
    assert r.check("support.roof") == {"status": "fail", "value": ["roof", "roof_b"]}


def test_support_is_not_checked_without_a_roof_tag(tmp_path, run_check):
    g = hut()
    del part(g, "roof")["tag"]
    r = run_check("check_support", "--work", write_build(tmp_path / "w", g))
    assert (r.rc, r.overall) == (0, "not_checked")


# ---------------------------------------------------------------- check_markers
def test_markers_pass_at_5_cm(tmp_path, run_check):
    r = run_check("check_markers", "--work", write_build(tmp_path / "w"))
    assert_pass(r)
    assert r.json["data"]["relief"] == {"door": 0.05}


def test_markers_fail_at_1_cm(tmp_path, run_check):
    """A marker under 2 cm does not read in the measurement renders (D2)."""
    rows = copy.deepcopy(HUT_ROWS)
    rows[3]["bbox_min"][1] = -1.51
    r = run_check("check_markers", "--work", write_build(tmp_path / "w", rows=rows))
    assert_fail(r)
    assert r.check("markers.relief") == {"status": "fail", "value": ["door"]}
    assert r.json["data"]["relief"] == {"door": 0.01}


def test_markers_measure_inset_part_beyond_the_face(tmp_path, run_check):
    rows = copy.deepcopy(HUT_ROWS)
    rows[3].update({"bbox_min": [-0.45, -1.53, 0.3], "depth": 0.02})
    r = run_check("check_markers", "--work", write_build(tmp_path / "w", rows=rows))
    assert_pass(r)
    assert r.json["data"]["relief"] == {"door": 0.03}


# ---------------------------------------------------------------- check_fix
def test_fix_passes_when_only_free_params_change(tmp_path, run_check):
    old = write_build(tmp_path / "old")
    g = hut()
    g["params"]["roof_h"] = 1.2
    rows = copy.deepcopy(HUT_ROWS)
    rows[2]["bbox_max"][2] = 3.9
    s = copy.deepcopy(HUT_SOURCES)
    s["layout"]["h"] = 3.85
    new = write_build(tmp_path / "new", g, rows, s)
    r = run_check("check_fix", "--work", new, "--old", old / "part_graph.json", "--finding", "F2")
    assert_pass(r)
    assert r.json["data"]["finding"] == "F2"
    assert r.json["data"]["changed_params"] == {"roof_h": [1.0, 1.2]}


def test_fix_fails_when_a_fix_changes_fixed_params(tmp_path, run_check):
    """Sizes from MAP-LAYOUT or size_m are not the worker's to change (D3.2)."""
    old = write_build(tmp_path / "old")
    g = hut()
    g["params"]["door_h"] = 2.0
    g["fixed_params"] = ["base_w", "door_h"]
    r = run_check("check_fix", "--work", write_build(tmp_path / "new", g), "--old", old / "part_graph.json",
                  "--finding", "F3")
    assert_fail(r)
    assert r.check("fix.fixed_params") == {"status": "fail", "value": ["base_d", "door_h"]}


def test_fix_fails_when_the_fix_breaks_the_layout_bbox(tmp_path, run_check):
    old = write_build(tmp_path / "old")
    rows = copy.deepcopy(HUT_ROWS)
    rows[2]["bbox_max"][2] = 3.9
    r = run_check("check_fix", "--work", write_build(tmp_path / "new", rows=rows), "--old",
                  old / "part_graph.json", "--finding", "F1")
    assert_fail(r)
    assert r.check("layout.bbox") == {"status": "fail", "value": 0.0541}


def test_fix_writes_one_result_per_finding_by_default(tmp_path):
    import subprocess
    import sys
    from conftest import TOOLS
    old = write_build(tmp_path / "old")
    new = write_build(tmp_path / "new")
    for f in ("F1", "F2"):
        subprocess.run([sys.executable, str(TOOLS / "check_fix.py"), "--work", str(new), "--old",
                        str(old / "part_graph.json"), "--finding", f], check=True, capture_output=True)
    assert sorted(p.name for p in (new / "review/checks").iterdir()) == ["fix_F1.json", "fix_F2.json"]


# ---------------------------------------------------------------- check_inputs
def approved(tmp_path, has_map, card_size=(4.0, 4.0, 3.7)):
    a = tmp_path / "_approved/05-hut"
    a.mkdir(parents=True)
    (a / "concept_albedo.png").write_bytes(b"png")
    (a / "materials.md").write_text("STONE TIMBER TEAL", encoding="utf-8")
    w, d, h = card_size
    (a / "asset-card.yaml").write_text(f"asset: 05-hut\nsize_m: {{w: {w}, d: {d}, h: {h}}}\n", encoding="utf-8")
    if has_map:
        (a / "05-hut.layout.md").write_text("W 4.0", encoding="utf-8")
    prof = tmp_path / "PROJECT-PROFILE.yaml"
    prof.write_text(f"project: t\nhas_map: {'true' if has_map else 'false'}\n", encoding="utf-8")
    return a, prof


def sources_for(a, layout_name):
    s = copy.deepcopy(HUT_SOURCES)
    s["files"].update({"layout": str(a / layout_name), "material": str(a / "materials.md")})
    return s


def test_inputs_no_map_take_size_from_the_asset_card(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=False)
    w = write_build(tmp_path / "w", sources=sources_for(a, "asset-card.yaml"))
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_pass(r)
    assert r.check("inputs.layout_source") == {"status": "pass", "value": "asset-card.yaml"}


def test_inputs_no_map_fail_when_sources_differ_from_size_m(tmp_path, run_check):
    """has_map false: W×D×H come from size_m of the card (D20.12)."""
    a, prof = approved(tmp_path, has_map=False, card_size=(4.0, 4.0, 4.0))
    w = write_build(tmp_path / "w", sources=sources_for(a, "asset-card.yaml"))
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_fail(r)
    assert r.check("inputs.layout_source") == {"status": "fail", "value": ["h"]}


def test_inputs_no_map_fail_when_layout_points_elsewhere(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=False)
    w = write_build(tmp_path / "w", sources=sources_for(a, "materials.md"))
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_fail(r)
    assert r.check("inputs.layout_source")["status"] == "fail"


def test_inputs_map_needs_layout_md(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=True)
    (a / "05-hut.layout.md").unlink()
    w = write_build(tmp_path / "w", sources=sources_for(a, "05-hut.layout.md"))
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_fail(r)
    assert r.check("inputs.files") == {"status": "fail", "value": ["05-hut.layout.md", "files.layout"]}


def test_inputs_fail_instead_of_erroring_when_the_asset_card_is_missing(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=False)
    (a / "asset-card.yaml").unlink()
    w = write_build(tmp_path / "w", sources=sources_for(a, "asset-card.yaml"))
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_fail(r)
    assert r.check("inputs.files") == {"status": "fail", "value": ["asset-card.yaml", "files.layout"]}


def test_inputs_report_missing_sources_keys(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=True)
    s = sources_for(a, "05-hut.layout.md")
    del s["door_h_source"], s["layout"]["includes_base"]
    s["materials"] = []
    w = write_build(tmp_path / "w", sources=s)
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_fail(r)
    assert r.check("inputs.sources_keys") == {"status": "fail",
                                              "value": ["door_h_source", "layout.includes_base", "materials"]}


def test_inputs_accept_no_door_height_for_a_prop_without_a_door_when_the_source_says_why(tmp_path, run_check):
    a, prof = approved(tmp_path, has_map=True)
    s = sources_for(a, "05-hut.layout.md")
    s["door_h"], s["door_h_source"] = None, "không có cửa (thùng)"
    r = run_check("check_inputs", "--work", write_build(tmp_path / "w", sources=s), "--approved", a, "--profile", prof)
    assert r.check("inputs.sources_keys") == {"status": "pass", "value": []}
    s["door_h_source"] = ""
    r = run_check("check_inputs", "--work", write_build(tmp_path / "w2", sources=s), "--approved", a, "--profile", prof)
    assert r.check("inputs.sources_keys") == {"status": "fail", "value": ["door_h", "door_h_source"]}


def test_inputs_tell_the_worker_when_sources_can_be_reused(tmp_path, run_check):
    import hashlib
    a, prof = approved(tmp_path, has_map=True)
    s = sources_for(a, "05-hut.layout.md")
    s["files"]["layout_sha256"] = hashlib.sha256(b"W 4.0").hexdigest()
    s["files"]["material_sha256"] = hashlib.sha256(b"STONE TIMBER TEAL").hexdigest()
    w = write_build(tmp_path / "w", sources=s)
    r = run_check("check_inputs", "--work", w, "--approved", a, "--profile", prof)
    assert_pass(r)
    assert r.json["data"]["sources_reusable"] is True


def test_every_check_prints_one_line_and_errors_exit_2(tmp_path, run_check):
    for name in ("check_schema", "check_materials", "check_layout", "check_base", "check_support", "check_markers"):
        r = run_check(name, "--work", tmp_path / "missing")
        assert (r.rc, r.overall, len(r.lines)) == (2, "error", 1), name
        assert "No such file" in r.json["data"]["error"], name


# ---------------------------------------------------------------- render_review foot framing
def row(name, lo, hi):
    return {"name": name, "parent": None, "contact": None, "depth": None, "bbox_min": lo, "bbox_max": hi}


@pytest.fixture
def render_review():
    pytest.importorskip("numpy")
    sys.path.insert(0, str(TOOLS))
    import render_review as RR
    return RR


def test_foot_crop_of_a_prop_without_a_base_tag_aims_at_the_ground_not_at_the_top_of_a_tall_part(render_review):
    """A 3 m post on a 0.4 m footing: aiming at the top of the lowest parts puts the camera at 3 m with a 12 m frame,
    so the crop shows sky, not the corner where the post meets the ground."""
    rows = [row("post", [-0.15, -0.15, 0.0], [0.15, 0.15, 3.0]), row("cap", [-0.2, -0.2, 3.0], [0.2, 0.2, 3.2])]
    f = render_review.foot_frame(rows, {"parts": [{"name": "post"}, {"name": "cap"}]})
    assert f == {"base": False, "scale": 1.0, "left": [0.15, -0.15, 0.0], "right": [-0.15, -0.15, 0.0]}


def test_foot_crop_frame_grows_with_the_footprint_so_a_wide_prop_is_not_cropped_to_one_metre(render_review):
    rows = [row("a", [-4.0, -2.0, 0.0], [4.0, 2.0, 0.5])]
    f = render_review.foot_frame(rows, {"parts": [{"name": "a"}]})
    assert (f["scale"], f["left"], f["right"]) == (2.0, [4.0, -2.0, 0.0], [-4.0, -2.0, 0.0])


def test_foot_crop_with_a_base_tag_keeps_the_frame_on_the_base_top(render_review):
    rows = [row("plinth", [-2.0, -2.0, 0.0], [2.0, 2.0, 0.5]), row("hall", [-1.0, -1.0, 0.5], [1.0, 1.0, 3.0])]
    f = render_review.foot_frame(rows, {"parts": [{"name": "plinth", "tag": "base"}, {"name": "hall"}]})
    assert f == {"base": True, "scale": 2.0, "left": [2.0, -2.0, 0.5], "right": [-2.0, -2.0, 0.5]}
