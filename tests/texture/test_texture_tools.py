"""Texture worker tools on the synthetic box, no Blender (docs/agents/texture-artist.md §2.1, §3–§6; checklist 16, 18,
19, 31, 58, 75). The box has two codes from two parts: four walls TIMBER, top and bottom STONE."""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

import glbkit
from texkit import AID, CAPS, COLORS, TOOLS, WALLS, face_name, model_final, tool

sys.path.insert(0, str(TOOLS / "lib"))
import tex  # noqa: E402

RES = 128
PILOT = Path(__file__).resolve().parents[1] / "fixtures/pilot"


@pytest.fixture
def m(tmp_path):
    return model_final(tmp_path / "model", RES)


def profile(tmp, light="unlit_flat", top=0, **over):
    p = tmp / "profile.yaml"
    p.write_text(yaml.safe_dump({"style": {"light_convention": light, "top_vs_side_L": top},
                                 "texture_simple": {"max_materials": 2, "max_color_clusters": 6}} | over), encoding="utf-8")
    return p


def colors(tmp):
    p = tmp / "concept_colors.json"
    p.write_text(json.dumps(COLORS), encoding="utf-8")
    return p


def texels(m):
    g, tm = tex.load_map(m / f"{AID}-untextured.glb", RES)
    return tm


def by_face(img, tm, names):
    sel = tm.inside & np.isin(np.vectorize(face_name)(np.where(tm.inside, tm.face, 0)), names)
    return img[sel]


def test_the_id_map_names_each_face_by_the_material_of_its_part_in_the_part_graph(m, tmp_path):
    rc, out = tool("id_map.py", "--final", tmp_path / "F", "--model", m)
    r = json.loads((tmp_path / "F/review/id_map.json").read_text())
    assert (rc, r["overall"], r["data"]["faces"], r["data"]["unmatched"]) == (0, "pass", {"STONE": 4, "TIMBER": 8}, 0)
    assert (tmp_path / "F/review/id_map.png").is_file()


def test_a_face_no_part_explains_is_reported_instead_of_guessed(tmp_path):
    m = model_final(tmp_path / "model", RES, parts=("walls",))
    rc, out = tool("id_map.py", "--final", tmp_path / "F", "--model", m)
    assert (rc, out) == (1, f"[id_map] 1 mã, 8 mặt, 4 mặt không khớp part -> {tmp_path}/F/review/id_map.json\n")


def concept(path, cols, size=96):
    im = Image.new("RGB", (size, size), (255, 255, 255))
    w = size // (len(cols) + 1)
    for i, c in enumerate(cols):
        im.paste(c, (w // 2 + i * w, size // 4, w // 2 + (i + 1) * w, 3 * size // 4))
    im.save(path)


def complexity(tmp, mats, cols=None, card=None, note=None, concept_img=None, mode="meshy"):
    b, c, vr, f = tmp / "B", tmp / "C", tmp / "VR", tmp / "F"
    for d in (b, c, vr):
        d.mkdir(parents=True, exist_ok=True)
    (b / "sources.json").write_text(json.dumps({"materials": mats}), encoding="utf-8")
    (c / "asset-card.yaml").write_text(yaml.safe_dump(card or {"tier": "standard"}), encoding="utf-8")
    if concept_img:
        shutil.copy(concept_img, c / "concept_albedo.png")
    else:
        concept(c / "concept_albedo.png", cols)
    (vr / "README.md").write_text("# README\n## TEXTURE NOTE\n" + (note or "- không có\n"), encoding="utf-8")
    rc, out = tool("texture_complexity.py", "--final", f, "--blockout", b, "--concept", c, "--views-rest", vr,
                   "--profile", profile(tmp), "--mode", mode)
    assert rc == 0, out
    return json.loads((f / "texture_spec.json").read_text())


def test_a_simple_crate_and_rock_still_get_meshy_when_the_script_chose_meshy_because_run5_meshy_was_faster_d30_11(
        tmp_path):
    crate = complexity(tmp_path / "crate", ["WOOD", "IRON"], [(120, 80, 40), (60, 60, 64)])
    rock = complexity(tmp_path / "rock", ["ROCK"], [(110, 110, 105), (90, 95, 80), (130, 125, 118)])
    assert [(r["simple"], r["proposed"], r["scores"]["materials"], r["scores"]["color_clusters"]) for r in (crate, rock)] \
        == [(True, "meshy", 2, 2), (True, "meshy", 1, 3)]
    assert (crate["used"], crate["reason"]) == (None, None)


def test_a_complex_building_gets_paint_when_the_script_chose_paint_because_there_is_no_meshy_key(tmp_path):
    r = complexity(tmp_path, ["STONE", "TIMBER", "TEAL"],
                   concept_img=PILOT / "_approved/pilot-house/concept_albedo.png", mode="paint")
    assert (r["simple"], r["proposed"], r["scores"]["materials"]) == (False, "paint", 3)


def test_a_hero_crate_or_a_painted_sign_is_never_simple(tmp_path):
    hero = complexity(tmp_path / "hero", ["WOOD"], [(120, 80, 40)], card={"tier": "hero"})
    sign = complexity(tmp_path / "sign", ["WOOD"], [(120, 80, 40)], note="- biển chữ \"TAVERN\" trên cửa\n")
    assert [(r["simple"], r["scores"]["motif"]) for r in (hero, sign)] == [
        (False, []), (False, ['biển chữ "TAVERN" trên cửa'])]


def test_a_motif_word_inside_another_word_is_no_motif_so_a_plain_crate_stays_simple(tmp_path):
    a = complexity(tmp_path / "a", ["WOOD"], [(120, 80, 40)],
                   card={"tier": "standard", "real_texture_only_notes": ["texture_only: vân gỗ sẫm, không cần thêm"]})
    b = complexity(tmp_path / "b", ["WOOD"], [(120, 80, 40)], note="- mặt bàn trơn, đúng design\n")
    assert [(r["simple"], r["scores"]["motif"]) for r in (a, b)] == [(True, []), (True, [])]


def ortho_view(k, sign):
    m = [[sign, 0, 0, 0], [0, 0, -sign, -5 * sign], [0, 1, 0, 0.5], [0, 0, 0, 1]]
    return {"k": k, "guide": f"guide_{k}.png", "paint": f"paint_{k}.png",
            "camera": {"matrix": m, "type": "ORTHO", "ortho_scale": 2.0, "w": 96, "h": 64}}


def test_a_paint_view_of_another_aspect_is_skipped_and_named_so_only_that_view_is_painted_again(m, tmp_path):
    paint = tmp_path / "paint"
    paint.mkdir()
    (paint / "cameras.json").write_text(json.dumps({"views": [ortho_view(0, 1), ortho_view(4, -1)]}))
    for k in (0, 4):
        Image.new("RGBA", (96, 64), (128, 128, 128, 255)).save(paint / f"guide_{k}.png")
    Image.new("RGB", (96, 64), (200, 30, 30)).save(paint / "paint_0.png")
    Image.new("RGB", (100, 100), (30, 30, 200)).save(paint / "paint_4.png")
    Image.new("RGB", (RES, RES), (90, 90, 90)).save(paint / "base_fill.png")
    rc, out = tool("project_views.py", "--glb", m / f"{AID}-untextured.glb", "--model", m, "--views", paint, "--base",
                   paint / "base_fill.png", "--res", RES, "--out", paint / "projected.png", "--padding", "2")
    r = json.loads((paint / "projected.json").read_text())
    assert (rc, r["views"], r["skipped"]) == (1, 1, {"paint_4.png": "100x100 khác tỉ lệ guide 96x64"})
    assert out.endswith(f"; bỏ paint_4.png (100x100 khác tỉ lệ guide 96x64): gen lại view đó -> {paint}/projected.png\n")
    front = by_face(tex.load_rgb(paint / "projected.png"), texels(m), ["-Y"])
    assert np.abs(front - (200, 30, 30)).max() <= 2


def meshy_call_dir(path, m, shift_px=0.0, size=RES):
    """A meshy_call.py folder: glb.glb, base_color.png and the topology.json that meshy_call writes for them."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/scripts"))
    import meshy_call
    v, uv, f = glbkit.box()
    path.mkdir(parents=True)
    glbkit.write(path / "glb.glb", v * 2, uv + np.array([shift_px / RES, 0]), f)
    Image.new("RGB", (size, size), (200, 100, 50)).save(path / "base_color.png")
    meshy_call.topology_check(m / f"{AID}-untextured.glb", path, RES)
    return path


def run_check_meshy(tmp_path, m, call, locked=None):
    code, out = tool("check_meshy.py", "--final", tmp_path / "F", "--locked", locked or m / f"{AID}-untextured.glb",
                     "--call", call, "--albedo-out", tmp_path / "meshy_albedo.png")
    r = json.loads((tmp_path / "F/review/checks/meshy.json").read_text())
    return code, [c["check"] for c in r["checks"] if c["status"] == "fail"], r


def test_check_meshy_keeps_the_base_color_of_a_call_whose_topology_gate_passed_checklist_75(m, tmp_path):
    code, fails, r = run_check_meshy(tmp_path, m, meshy_call_dir(tmp_path / "call-1", m))
    assert (code, fails, r["data"]["hard_gate"]) == (0, [], True)
    assert np.asarray(Image.open(tmp_path / "meshy_albedo.png")).shape == (RES, RES, 3)
    assert Image.open(tmp_path / "meshy_albedo.png").getpixel((5, 5)) == (200, 100, 50)


@pytest.mark.parametrize("case,fails", [
    ("uv", ["meshy.uv_triples", "meshy.topology"]),
    ("size", ["meshy.base_color_px", "meshy.topology"]),
    ("edited", ["meshy.files_unchanged"]),
    ("other_mesh", ["meshy.locked_mesh"]),
])
def test_check_meshy_drops_a_layer_that_failed_or_changed_after_the_gate_so_no_wrong_albedo_reaches_sua(
        m, tmp_path, case, fails):
    call = meshy_call_dir(tmp_path / "call-1", m, shift_px=2.0 if case == "uv" else 0.0,
                          size=RES // 2 if case == "size" else RES)
    if case == "edited":
        Image.new("RGB", (RES, RES), (0, 0, 0)).save(call / "base_color.png")
    other = None
    if case == "other_mesh":
        other = glbkit.write(tmp_path / "other.glb", *glbkit.box((2, 1, 1)))
    code, got, _ = run_check_meshy(tmp_path, m, call, other)
    assert (code, got, (tmp_path / "meshy_albedo.png").exists()) == (1, fails, False)


def test_a_crop_edit_changes_pixels_inside_the_region_only_checklist_18(tmp_path):
    rng = np.random.default_rng(1)
    src = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)
    Image.fromarray(src).save(tmp_path / "a.png")
    rc, out = tool("crop_edit.py", "cut", "--albedo", tmp_path / "a.png", "--box", "20,30,60,50", "--margin", "8",
                   "--out", tmp_path / "c")
    assert (rc, out) == (0, f"[crop_edit] crop 56x36, gửi 1536x987 -> {tmp_path}/c/send.png\n")
    assert Image.open(tmp_path / "c/send.png").size == (1536, 987)
    Image.new("RGB", (1536, 987), (255, 0, 0)).save(tmp_path / "edited.png")
    rc, out = tool("crop_edit.py", "paste", "--albedo", tmp_path / "a.png", "--crop", tmp_path / "c", "--edited",
                   tmp_path / "edited.png", "--out", tmp_path / "b.png", "--feather", "4")
    got = np.asarray(Image.open(tmp_path / "b.png"))
    outside = np.ones((128, 128), bool)
    outside[30:50, 20:60] = False
    assert rc == 0 and np.array_equal(got[outside], src[outside])
    assert tuple(got[40, 40]) == (255, 0, 0) and json.loads((tmp_path / "b.json").read_text())["changed_outside"] == 0


def test_a_codex_crop_of_another_size_is_refused_and_writes_nothing(tmp_path):
    Image.new("RGB", (128, 128), (9, 9, 9)).save(tmp_path / "a.png")
    tool("crop_edit.py", "cut", "--albedo", tmp_path / "a.png", "--box", "20,30,60,50", "--margin", "8", "--out",
         tmp_path / "c")
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "edited.png")
    rc, out = tool("crop_edit.py", "paste", "--albedo", tmp_path / "a.png", "--crop", tmp_path / "c", "--edited",
                   tmp_path / "edited.png", "--out", tmp_path / "b.png")
    assert (rc, out, (tmp_path / "b.png").exists()) == (
        1, "[crop_edit] ảnh sửa 64x64 khác ảnh gửi 1536x987: bỏ kết quả\n", False)


def test_a_region_over_1024_px_must_be_split(tmp_path):
    Image.new("RGB", (2048, 2048), (9, 9, 9)).save(tmp_path / "a.png")
    rc, out = tool("crop_edit.py", "cut", "--albedo", tmp_path / "a.png", "--box", "0,0,1100,200", "--out", tmp_path / "c")
    assert (rc, out) == (1, "[crop_edit] vùng 1132x232 px > 1024: chia nhỏ vùng\n")


def base_fill(m, tmp, light="unlit_flat", top=0):
    out = tmp / f"base_{light}.png"
    rc, msg = tool("base_fill.py", "--final", tmp / "F", "--model", m, "--concept-colors", colors(tmp), "--profile",
                   profile(tmp, light, top), "--res", RES, "--out", out, "--padding", "4")
    assert rc == 0, msg
    return tex.load_rgb(out)


def test_base_fill_paints_each_code_its_concept_colour_and_the_top_light_rule_lifts_top_faces(m, tmp_path):
    tm = texels(m)
    flat = base_fill(m, tmp_path)
    walls, caps = by_face(flat, tm, WALLS), by_face(flat, tm, CAPS)
    assert (np.ptp(walls, 0).max(), np.ptp(caps, 0).max()) == (0.0, 0.0)
    assert (walls[0].tolist(), caps[0].tolist()) == (tex.hex_rgb(COLORS["TIMBER"]).tolist(),
                                                    tex.hex_rgb(COLORS["STONE"]).tolist())
    lit = base_fill(m, tmp_path, "painted_top_light", 8)
    top, bottom = (float(tex.lab(by_face(lit, tm, [n]))[:, 0].mean()) for n in ("+Z", "-Z"))
    assert round(top - bottom) == 14


def measure(m, tmp, img, light="unlit_flat", top=0):
    final = tmp / "F"
    (final / "review").mkdir(parents=True, exist_ok=True)
    tex.save_rgb(img, final / f"albedo_{RES}.png")
    rc, out = tool("tex_measure.py", "--final", final, "--glb", m / f"{AID}-untextured.glb", "--model", m, "--albedo",
                   final / f"albedo_{RES}.png", "--concept-colors", colors(tmp), "--profile", profile(tmp, light, top),
                   "--pilot", "none")
    r = json.loads((final / "review/checks/tex_measure.json").read_text())
    return rc, {c["check"]: (c["status"], c["value"]) for c in r["checks"]}, r


def test_tex_measure_passes_the_base_fill_and_reads_regions_from_the_id_map_checklist_19_58(m, tmp_path):
    rc, c, r = measure(m, tmp_path, base_fill(m, tmp_path))
    assert rc == 0, c
    assert {k: v for k, v in c.items() if k.startswith(("light.", "material."))} == {
        "light.side_spread_L.TIMBER": ("pass", 0.0), "light.shaded_share.TIMBER": ("pass", 0.0),
        "material.dE_concept.STONE": ("pass", 0.0), "material.dE_concept.TIMBER": ("pass", 0.0),
        "material.dE_pilot": ("not_checked", None)}
    assert [x["note"] for x in r["checks"] if x["check"] == "material.dE_pilot"] == ["chưa có pilot"]
    assert (c["seam.padding_empty_share"], c["seam.unpainted_share"]) == (("pass", 0.0), ("pass", 0.0))
    assert c["seam.p90_dE"][0] == "pass"


def shaded(m, tmp):
    """TIMBER walls: +X 10 L* darker, a dark band (baked AO) along the top of -Y, grain everywhere."""
    tm = texels(m)
    img = base_fill(m, tmp)
    lab = tex.lab(img)
    rng = np.random.default_rng(7)
    lab[..., 0] += np.where(tm.inside, rng.normal(0, 2.5, tm.face.shape), 0)
    names = np.vectorize(face_name)(np.where(tm.inside, tm.face, 0))
    lab[..., 0] -= np.where(tm.inside & (names == "+X"), 10, 0)
    band = tm.inside & (names == "-Y") & (tm.pos[..., 2] > 0.8)
    lab[..., 0] -= np.where(band, 18, 0)
    return np.where(tm.inside[..., None], tex.lab_to_rgb(lab), img), tm, names


def test_tex_measure_fails_a_darker_side_and_a_baked_shadow(m, tmp_path):
    img, _, _ = shaded(m, tmp_path)
    rc, c, _ = measure(m, tmp_path, img)
    assert (rc, c["light.side_spread_L.TIMBER"][0], c["light.shaded_share.TIMBER"][0]) == (1, "fail", "fail")


def test_tone_fix_brings_sides_and_the_shadow_within_tex_measure_and_keeps_the_grain_checklist_31(m, tmp_path):
    img, tm, names = shaded(m, tmp_path)
    src = tmp_path / "shaded.png"
    tex.save_rgb(img, src)
    rc, out = tool("tone_fix.py", "--glb", m / f"{AID}-untextured.glb", "--model", m, "--albedo", src, "--profile",
                   profile(tmp_path), "--res", RES, "--out", tmp_path / "fixed.png", "--padding", "4")
    assert rc == 0, out
    fixed = tex.load_rgb(tmp_path / "fixed.png")
    rc, c, _ = measure(m, tmp_path, fixed)
    assert (c["light.side_spread_L.TIMBER"][0], c["light.shaded_share.TIMBER"][0]) == ("pass", "pass"), c
    grain = tm.inside & (names == "-X")
    before, after = (float(tex.lab(x[grain])[:, 0].std()) for x in (img, fixed))
    assert after >= 0.9 * before


def test_seam_fix_makes_both_sides_of_every_uv_seam_match(m, tmp_path):
    tm = texels(m)
    rng = np.random.default_rng(3)
    face_rgb = rng.integers(40, 220, (12, 3)).astype(float)
    img = np.where(tm.inside[..., None], face_rgb[np.where(tm.inside, tm.face, 0)], 0)
    tex.save_rgb(img, tmp_path / "a.png")
    rc, out = tool("seam_fix.py", "--glb", m / f"{AID}-untextured.glb", "--albedo", tmp_path / "a.png", "--res", RES,
                   "--out", tmp_path / "b.png", "--padding", "4")
    rec = json.loads((tmp_path / "b.json").read_text())
    assert rc == 0 and rec["seam_p90_before"] > 20 and rec["seam_p90_after"] < 1.0, rec


GROOVE_RES = 256


def ring_quads(levels, w):
    """Side quads of a box whose outline steps in by `inset` at each (z, inset) level, as kit grooved_box builds it."""
    rings = [[(sx * (w / 2 - i), sy * (w / 2 - i), z) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))] for z, i in levels]
    return [(lo[k], lo[(k + 1) % 4], hi[(k + 1) % 4], hi[k]) for lo, hi in zip(rings, rings[1:]) for k in range(4)]


def slab(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    c = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    return [tuple(c[i] for i in q) for q in glbkit.FACES.values()]


def quads_model(d, parts, margin=0.1):
    """A model final/ of parts {name: (material, quads)}, each quad its own square UV island inside a grid cell,
    `margin` of the cell left empty on each side; reach of a groove = 16 px / px_per_m = 0.044 m."""
    cols = int(np.ceil(np.sqrt(sum(len(q) for _, q in parts.values()))))
    v, uv, f, part_f = [], [], [], {}
    for name, (_, quads) in parts.items():
        part_f[name] = []
        for q in quads:
            k, base = len(f) // 2, len(v)
            c, r = k % cols, k // cols
            v += q
            uv += [((c + margin + (1 - 2 * margin) * du) / cols, (r + margin + (1 - 2 * margin) * dv) / cols)
                   for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1))]
            tris = [(base, base + 1, base + 2), (base, base + 2, base + 3)]
            f += tris
            part_f[name] += tris
    v, uv, f = np.array(v, float), np.array(uv), np.array(f)
    (d / "parts").mkdir(parents=True)
    (d / "review").mkdir()
    glbkit.write(d / f"{AID}-untextured.glb", v, uv, f)
    for name, tris in part_f.items():
        glbkit.write(d / "parts" / f"{name}.glb", v, np.zeros((len(v), 2)), np.array(tris))
    (d / "part_graph.json").write_text(json.dumps({"parts": [{"name": n, "material": m} for n, (m, _) in parts.items()]}),
                                      encoding="utf-8")
    (d / "review/join.json").write_text(json.dumps({"checks": [{"check": "join.origin_offset_m", "value": [0, 0, 0]}]}),
                                        encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"asset": AID, "uv": {"resolution": GROOVE_RES},
                                             "model": {"px_per_m": 363.64, "alpha_min_px": 16}}), encoding="utf-8")
    return d


def grooved_model(d):
    """Body 1 m TIMBER, a groove 2 cm wide and 2 cm deep round the four sides at z 0.5, a 0.1 m band under a STONE lid
    that overhangs by 0.1 m."""
    body = ring_quads([(0, 0), (0.49, 0), (0.49, 0.02), (0.51, 0.02), (0.51, 0), (0.9, 0), (1.0, 0)], 1.0)
    return quads_model(d, {"body": ("TIMBER", body), "lid": ("STONE", slab((-0.6, -0.6, 1.0), (0.6, 0.6, 1.1)))})


def groove_texture(gm, tmp, ao=0.0):
    """Base fill, concept ink (L* 5) on every groove face, grain; ao: L* taken off the band under the lid overhang."""
    g, tm = tex.load_map(gm / f"{AID}-untextured.glb", GROOVE_RES)
    img = tex.load_rgb(base_fill_at(gm, tmp))
    lab = tex.lab(img)
    lab[..., 0] += np.where(tm.inside, np.random.default_rng(5).normal(0, 2.0, tm.face.shape), 0)
    x, y = np.abs(tm.pos[..., 0]), np.abs(tm.pos[..., 1])
    groove = tm.inside & (np.maximum(x, y) < 0.499) & (tm.pos[..., 2] > 0.489) & (tm.pos[..., 2] < 0.511)
    lab[..., 0] = np.where(groove, 5, lab[..., 0])
    band = tm.inside & (tm.pos[..., 2] > 0.95) & (tm.pos[..., 2] < 0.999) & (np.maximum(x, y) < 0.501)
    lab[..., 0] -= np.where(band, ao, 0)
    return np.where(tm.inside[..., None], tex.lab_to_rgb(lab), img), float(groove.sum())


def base_fill_at(gm, tmp):
    out = tmp / f"base_{gm.name}.png"
    rc, msg = tool("base_fill.py", "--final", tmp / "F", "--model", gm, "--concept-colors", colors(tmp), "--profile",
                   profile(tmp), "--res", GROOVE_RES, "--out", out, "--padding", "4")
    assert rc == 0, msg
    return out


def measure_groove(gm, tmp, img):
    final = tmp / "G"
    (final / "review").mkdir(parents=True, exist_ok=True)
    tex.save_rgb(img, final / f"albedo_{GROOVE_RES}.png")
    rc, out = tool("tex_measure.py", "--final", final, "--glb", gm / f"{AID}-untextured.glb", "--model", gm, "--albedo",
                   final / f"albedo_{GROOVE_RES}.png", "--concept-colors", colors(tmp), "--profile", profile(tmp),
                   "--pilot", "none")
    r = json.loads((final / "review/checks/tex_measure.json").read_text())
    return {c["check"]: (c["status"], c["value"]) for c in r["checks"]}, r["data"]


def test_concept_ink_in_a_narrow_groove_is_line_art_not_baked_shading_run4(tmp_path):
    gm = grooved_model(tmp_path / "model")
    img, inked = groove_texture(gm, tmp_path)
    assert inked > 0
    c, data = measure_groove(gm, tmp_path, img)
    assert c["light.shaded_share.TIMBER"] == ("pass", 0.0), c
    assert data["codes"]["TIMBER"]["groove_share"] == pytest.approx(4 / 16, abs=0.01)


def test_baked_ao_under_an_overhang_still_fails_next_to_an_inked_groove(tmp_path):
    gm = grooved_model(tmp_path / "model")
    img, _ = groove_texture(gm, tmp_path, ao=18)
    c, _ = measure_groove(gm, tmp_path, img)
    assert c["light.shaded_share.TIMBER"][0] == "fail" and c["light.shaded_share.TIMBER"][1] > 0.05, c


def test_a_bright_side_beside_a_dark_island_in_the_atlas_is_not_counted_as_shaded_run4(tmp_path):
    gm = quads_model(tmp_path / "tight", {"body": ("TIMBER", slab((-0.5, -0.5, 0), (0.5, 0.5, 1)))}, margin=0.01)
    g, tm = tex.load_map(gm / f"{AID}-untextured.glb", GROOVE_RES)
    img = tex.load_rgb(base_fill_at(gm, tmp_path))
    names = np.vectorize(face_name)(np.where(tm.inside, tm.face, 0))
    rows = np.indices(names.shape)[0]
    toward = np.sign(rows[names == "+X"].mean() - rows[names == "-Y"].mean())
    dark = tm.inside & (names == "-Y") & (toward * (rows - np.median(rows[names == "-Y"])) > 0)
    lab = tex.lab(img)
    lab[..., 0] = np.where(dark, 0, lab[..., 0])
    c, _ = measure_groove(gm, tmp_path, np.where(tm.inside[..., None], tex.lab_to_rgb(lab), img))
    side = tm.inside & np.isin(names, WALLS)
    assert c["light.shaded_share.TIMBER"] == ("fail", round(dark.sum() / side.sum(), 4)), c
