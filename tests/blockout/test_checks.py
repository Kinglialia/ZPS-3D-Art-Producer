"""Pure blockout checks (docs/agents/blockout.md §5, §9): plain Python, one JSON, one line, exit 1 on fail."""
import copy

from conftest import HUT_ROWS, HUT_SOURCES, hut, part, write_build


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
    part(g, "roof")["tag"] = "top"
    r = run_check("check_schema", "--work", write_build(tmp_path / "w", g))
    assert_fail(r)
    assert r.check("schema.header") == {"status": "fail", "value": ["front", "schema"]}
    assert r.check("schema.enums") == {"status": "fail", "value": ["door: role", "roof: tag"]}


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
