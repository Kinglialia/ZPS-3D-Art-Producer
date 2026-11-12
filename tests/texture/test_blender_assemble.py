"""assemble.py for real in Blender (docs/producer.md §6.4; checklist 57, 77, 86): a textured box goes through the unlit
GLB export, the kit QA, the kit finalize.py gate and the pixel compare against the texture step's own renders. One run
writes the albedo in linear values (the colour-space fault that survives a GLB round trip, unlike a mis-set image node);
the compare must fail it. Needs Blender and the model and texture tools/setup_deps.sh."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import glbkit

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "src/zps-3dp-producer/scripts"
TTOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-texture/tools"
MTOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model/tools"
BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
AID, RES = "box", 256
pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not ((MTOOLS / ".deps").is_dir() and (TTOOLS / ".deps").is_dir()
                                      and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model and texture tools/setup_deps.sh")]
SPEC = {"asset": AID, "objects": [AID], "budget": {"max_tris_total": 100, "max_materials_total": 1},
        "dimensions_m": {AID: [1.0, 1.0, 1.0]}, "dimensions_tolerance": 0.02, "height_m": 1.0, "pivot": "bottom_center",
        "uv": {"resolution": RES, "min_padding_px": 4, "allow_overlap": False, "allow_out_of_bounds": False},
        "export": {"path": f"{AID}-untextured.glb", "skip_export": True},
        "model": {"target_px_height": 200, "character_h": 1.6},
        "camera": {"type": "persp", "azimuth_deg": 30, "elevation_deg": 35, "fov_v_deg": 40, "target_px_height": 200},
        "sun": {"azimuth_deg": 45, "elevation_deg": 50}}


def albedo():
    """One flat colour per box face cell (3 x 2 grid) with a soft vertical gradient: mid-tones, where sRGB and linear
    differ most."""
    cells = [(180, 60, 50), (60, 150, 80), (70, 90, 170), (200, 170, 60), (140, 80, 160), (90, 160, 170)]
    y, x = np.mgrid[0:RES, 0:RES]
    img = np.zeros((RES, RES, 3))
    for k, c in enumerate(cells):
        sel = (x * 3 // RES == k % 3) & (y * 2 // RES == k // 3)
        img[sel] = np.asarray(c, float) * (0.85 + 0.3 * (y[sel] % (RES // 2)) / RES)[:, None]
    return np.clip(img, 0, 255).astype(np.uint8)


def linear(img):
    c = img / 255.0
    return np.clip(np.round(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) * 255), 0, 255).astype(np.uint8)


def sh(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def build_base(t, spec):
    concept = t / "concepts/_approved" / AID
    concept.mkdir(parents=True)
    (concept / "asset-card.yaml").write_text(f"asset: {AID}\ntexture_res: {RES}\n", encoding="utf-8")
    Image.new("RGB", (64, 64), (230, 230, 230)).save(concept / "concept_shadow.png")
    a = t / "production/assets" / AID
    mf, tf = a / "model/v1/final", a / "texture/v1/final"
    (mf / "review").mkdir(parents=True)
    glb = glbkit.write(mf / f"{AID}-untextured.glb", *glbkit.box())
    (mf / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    Image.new("RGB", (32, 32), (9, 9, 9)).save(mf / "review/model_sheet.png")
    tf.mkdir(parents=True)
    Image.fromarray(albedo()).save(tf / f"albedo_{RES}.png")
    rc, out = sh(BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", TTOOLS / "render_texture.py",
                 "--", "--glb", glb, "--albedo", tf / f"albedo_{RES}.png", "--spec", mf / "spec.json",
                 "--concept", concept / "concept_shadow.png", "--final", tf, "--size", 256)
    assert rc == 0, out
    (tf / "notes.md").write_text("# Texture box v1\nVẼ MỚI\n", encoding="utf-8")
    (tf / "texture_spec.json").write_text(json.dumps({"proposed": "paint", "used": "paint"}), encoding="utf-8")
    st = {"id": AID, "title": "Box", "stage": "assemble", "state": "running", "concept_dir": str(concept),
          "versions": {"model": 1, "texture": 1, "assemble": 1}, "approved": {"model": 1, "texture": 1},
          "locked": {"model": hashlib.sha256(glb.read_bytes()).hexdigest()}, "created": "2026-11-09 08:00"}
    (a / "status.json").write_text(json.dumps(st), encoding="utf-8")
    (t / "production/pipeline.toml").touch()
    return t


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return build_base(tmp_path_factory.mktemp("assemble"), SPEC)


@pytest.fixture(scope="module")
def base_without_camera(tmp_path_factory):
    return build_base(tmp_path_factory.mktemp("assemble_no_camera"), {k: v for k, v in SPEC.items() if k != "camera"})


def assemble(base, tmp_path, edit=None, blender=BLENDER):
    root = tmp_path / "p"
    shutil.copytree(base, root, symlinks=True)
    if edit:
        edit(root / "production/assets" / AID)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", str(blender), "--", AID, "1", "abc123"],
                       cwd=root, capture_output=True, text=True)
    d = root / "production/assets" / AID / "assemble/v1"
    rep = (d / "report-script.md").read_text(encoding="utf-8") if (d / "report-script.md").is_file() else r.stderr
    cmp_ = d / "final/review/compare.json"
    return {"rc": r.returncode, "out": r.stdout, "report": rep, "d": d,
            "compare": json.loads(cmp_.read_text()) if cmp_.is_file() else None}


def test_a_correct_texture_passes_every_check_and_the_package_holds_one_unlit_mesh_with_the_albedo(base, tmp_path):
    r = assemble(base, tmp_path)
    assert (r["rc"], r["report"].splitlines()[0], r["out"]) == (
        0, "STATUS: DONE", "[assemble] pass -> production/assets/box/assemble/v1/report-script.md\n"), r["report"]
    c = r["compare"]
    assert c["qa"] == {"mesh_check": "pass", "uv_check": "pass", "export_check": "pass", "screen_tris_check": "info"}
    assert all(v["mean_abs"] <= 1.0 and v["mask_mismatch"] <= 0.005 for v in c["views"].values()), c["views"]
    final = r["d"] / "final"
    files = sorted(p.relative_to(final).as_posix() for p in final.rglob("*") if p.is_file())
    assert [f for f in files if not f.startswith("review/")] == [
        "README.md", "model/box.blend", "model/box.glb", f"texture/albedo_{RES}.png", "texture/notes.md"]
    assert {"review/compare_34_front.png", "review/compare_game.png", "review/model_sheet.png",
            "review/final_lit_vs_concept.png", "review/unlit_34_front.png"} <= set(files)
    sys.path.insert(0, str(TTOOLS / "lib"))
    import tex
    g = tex.read_glb(final / "model/box.glb")
    doc, _ = tex.chunks(final / "model/box.glb")
    assert (g["nodes"], g["meshes"], g["materials"], len(g["f"]), list(doc["materials"][0].get("extensions", {}))) == (
        1, 1, 1, 12, ["KHR_materials_unlit"])
    from io import BytesIO
    assert Image.open(BytesIO(g["images"][0])).size == (RES, RES)
    readme = (final / "README.md").read_text(encoding="utf-8").splitlines()
    assert readme[0].startswith("Trạng thái: chờ DUYỆT 2 · ")
    assert "- Texture v1: chế độ paint (đề xuất paint); Meshy 0 lần gọi, 0 credit (file budget)." in readme


def test_an_albedo_written_in_linear_values_is_caught_by_the_pixel_compare_and_blocks(base, tmp_path):
    def bad(a):
        p = a / f"texture/v1/final/albedo_{RES}.png"
        Image.fromarray(linear(np.asarray(Image.open(p).convert("RGB")))).save(p)
    r = assemble(base, tmp_path, bad)
    assert (r["rc"], r["report"].splitlines()[0]) == (1, "STATUS: BLOCKED")
    c = r["compare"]
    assert c["qa"]["export_check"] == "pass" and all(v["mean_abs"] > 6 for v in c["views"].values()), c
    assert "- F1 [blocker] compare" in r["report"] and "- F2 [blocker] compare" in r["report"]


def test_a_mesh_that_is_not_the_locked_one_fails_before_any_export(base, tmp_path):
    def other(a):
        glbkit.write(a / f"model/v1/final/{AID}-untextured.glb", *glbkit.box((1.0, 1.0, 1.2)))
    r = assemble(base, tmp_path, other)
    assert (r["rc"], r["report"].splitlines()[:3]) == (1, [
        "STATUS: BLOCKED", "OUTPUT: production/assets/box/assemble/v1/final/",
        "ISSUES: hash mesh: sha256 box-untextured.glb khác locked.model"])
    assert not (r["d"] / "final/model").exists()


def test_a_failing_kit_qa_makes_finalize_refuse_and_assemble_block(base, tmp_path):
    def tight(a):
        p = a / "model/v1/final/spec.json"
        p.write_text(json.dumps(SPEC | {"budget": {"max_tris_total": 4, "max_materials_total": 1}}), encoding="utf-8")
    r = assemble(base, tmp_path, tight)
    assert (r["rc"], r["compare"]["qa"]["mesh_check"]) == (1, "fail")
    issues = r["report"].splitlines()[2]
    assert issues.startswith("ISSUES: qa GLB cuối: ") and "mesh_check" in issues


def test_a_kit_check_that_writes_no_result_is_a_qa_fail_because_finalize_only_requires_mesh_check(base, tmp_path):
    crash = tmp_path / "blender_drops_export_check.sh"
    crash.write_text(f'#!/bin/sh\n"{BLENDER}" "$@"\nrc=$?\nrm -f production/assets/{AID}/assemble/v1/work/evidence/qa/export_check.json\n'
                     'exit $rc\n')
    crash.chmod(0o755)
    r = assemble(base, tmp_path, blender=crash)
    assert (r["rc"], r["compare"]["qa"]) == (1, {"mesh_check": "pass", "uv_check": "pass", "export_check": "missing",
                                                  "screen_tris_check": "info"})
    assert r["report"].splitlines()[:3] == ["STATUS: BLOCKED", "OUTPUT: production/assets/box/assemble/v1/final/",
                                            "ISSUES: qa GLB cuối: export_check: missing"]


def counting_blender(tmp_path):
    """A Blender that logs each start. `exec` keeps the real Blender as the process the timeout kills."""
    log = tmp_path / "blender-starts.log"
    wrapper = tmp_path / "blender_count.sh"
    wrapper.write_text(f'#!/bin/sh\necho start >> "{log}"\nexec "{BLENDER}" "$@"\n')
    wrapper.chmod(0o755)
    return wrapper, log


def test_one_blender_start_runs_the_export_the_four_kit_checks_and_the_compare_render_l13(base, tmp_path):
    """Every Blender start costs seconds on a laptop and cannot share a hung session. The old flow started six."""
    wrapper, log = counting_blender(tmp_path)
    r = assemble(base, tmp_path, blender=wrapper)
    assert (r["rc"], r["report"].splitlines()[0]) == (0, "STATUS: DONE"), r["report"]
    assert len(log.read_text().splitlines()) == 1
    qa = sorted(p.name for p in (r["d"] / "work/evidence/qa").glob("*.json"))
    assert qa == ["export_check.json", "mesh_check.json", "screen_tris_check.json", "uv_check.json"]
    assert sorted(p.name for p in (r["d"] / "work/compare").glob("*.png")) == ["unlit_34_front.png", "unlit_game.png"]


def test_the_heartbeat_goes_to_the_assemble_version_not_to_the_approved_model_version_t17(base, tmp_path):
    """The Producer reads vN/heartbeat.log of the running step to tell a slow Blender from a hung one."""
    r = assemble(base, tmp_path)
    log = (r["d"] / "heartbeat.log").read_text(encoding="utf-8").splitlines()
    assert [row.split(" · ")[2] for row in log][0::2] == ["start"] * (len(log) // 2) and log[-1].split(" · ")[2] == "done"
    assert not (r["d"].parents[1] / "model/v1/heartbeat.log").exists()


def test_a_texture_step_without_a_game_view_is_compared_on_the_views_it_has_and_the_readme_says_so_t1(base_without_camera,
                                                                                                      tmp_path):
    """A spec with no camera makes the texture step render no unlit_game. That is no reason to block the package."""
    r = assemble(base_without_camera, tmp_path)
    assert (r["rc"], r["report"].splitlines()[0]) == (0, "STATUS: DONE"), r["report"]
    assert list(r["compare"]["views"]) == ["unlit_34_front"]
    review = sorted(p.name for p in (r["d"] / "final/review").glob("compare_*.png"))
    assert review == ["compare_34_front.png"]
    readme = (r["d"] / "final/README.md").read_text(encoding="utf-8")
    assert "- game view chưa kiểm: bước texture không render unlit_game (spec không có camera)." in readme.splitlines()


def test_a_locked_mesh_that_blender_cannot_import_blocks_at_the_export_and_no_check_runs_l13(base, tmp_path):
    def broken(a):
        glb = a / f"model/v1/final/{AID}-untextured.glb"
        glb.write_bytes(b"not a glb")
        st = json.loads((a / "status.json").read_text(encoding="utf-8"))
        st["locked"]["model"] = hashlib.sha256(glb.read_bytes()).hexdigest()
        (a / "status.json").write_text(json.dumps(st), encoding="utf-8")
    r = assemble(base, tmp_path, broken)
    assert (r["rc"], r["report"].splitlines()[0]) == (1, "STATUS: BLOCKED")
    assert r["report"].splitlines()[2].startswith("ISSUES: export GLB: ")
    assert not (r["d"] / "work/evidence/qa").exists() and not (r["d"] / "work/compare").exists()


def test_a_kit_check_that_crashes_does_not_stop_the_other_checks_or_the_compare_render_l13(base, tmp_path):
    """The checks share one Blender session now. One bad spec value must cost one result, not the rest of the run."""
    def bad_spec(a):
        p = a / "model/v1/final/spec.json"
        p.write_text(json.dumps(SPEC | {"uv": SPEC["uv"] | {"min_padding_px": "wide"}}), encoding="utf-8")
    r = assemble(base, tmp_path, bad_spec)
    assert r["rc"] == 1 and r["compare"]["qa"] == {
        "mesh_check": "pass", "uv_check": "error", "export_check": "pass", "screen_tris_check": "info"}, r["report"]
    assert sorted(r["compare"]["views"]) == ["unlit_34_front", "unlit_game"]
    session = json.loads((r["d"] / "work/evidence/session.json").read_text(encoding="utf-8"))
    assert session["stages"] == {"export": "ok", "spec": "ok", "mesh_check": "ok", "uv_check": "error: exit 1",
                                 "export_check": "ok", "screen_tris_check": "ok", "compare": "ok"}


def test_a_compare_render_that_fails_points_the_fail_point_at_the_error_file_l13(base, tmp_path):
    def bad(a):
        p = a / "texture/v1/final/review/renders.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["renders"]["unlit_game"]["camera"] = None
        p.write_text(json.dumps(doc), encoding="utf-8")
    r = assemble(base, tmp_path, bad)
    assert (r["rc"], r["report"].splitlines()[0]) == (1, "STATUS: BLOCKED")
    assert "compare unlit_game: render GLB lỗi error: exit 1, xem work/compare/render.json" in r["report"].splitlines()[2]
    assert json.loads((r["d"] / "work/compare/render.json").read_text(encoding="utf-8"))["overall"] == "error"
