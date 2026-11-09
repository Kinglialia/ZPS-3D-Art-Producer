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


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    t = tmp_path_factory.mktemp("assemble")
    concept = t / "concepts/_approved" / AID
    concept.mkdir(parents=True)
    (concept / "asset-card.yaml").write_text(f"asset: {AID}\ntexture_res: {RES}\n", encoding="utf-8")
    Image.new("RGB", (64, 64), (230, 230, 230)).save(concept / "concept_shadow.png")
    a = t / "production/assets" / AID
    mf, tf = a / "model/v1/final", a / "texture/v1/final"
    (mf / "review").mkdir(parents=True)
    glb = glbkit.write(mf / f"{AID}-untextured.glb", *glbkit.box())
    (mf / "spec.json").write_text(json.dumps(SPEC), encoding="utf-8")
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
    return t


def assemble(base, tmp_path, edit=None):
    root = tmp_path / "p"
    shutil.copytree(base, root, symlinks=True)
    if edit:
        edit(root / "production/assets" / AID)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), AID, "--version", "1", "--profile-hash", "abc123",
                        "--blender", BLENDER], cwd=root, capture_output=True, text=True)
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
