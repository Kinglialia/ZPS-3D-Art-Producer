"""K12's follow-up: the fitted concept camera must travel blockout -> brief -> model spec. prep_overlay.py writes
camera_fit.json into final/ (its --work), the brief names that file and make_spec.py reads B/camera_fit.json."""
import json
import subprocess
import sys

import pytest

from conftest import TOOLS
from test_prep_overlay import SILHOUETTE, VPY, concept, final, needs_venv, prep

ROOT = TOOLS.parents[4]
MODEL_TOOLS = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model/tools"
PILOT = ROOT / "tests/fixtures/pilot"
PRESET = ROOT / "src/zps-3dp-producer/presets/topdown-mobile-lowpoly.yaml"


@needs_venv
def test_a_34_fit_written_by_prep_overlay_reaches_the_model_spec_through_final(tmp_path):
    f = final(tmp_path)
    img = tmp_path / "34.png"
    subprocess.run([str(VPY), "-c", SILHOUETTE, str(TOOLS), str(f / "assembled.glb"), "-35", "20", str(img)], check=True)
    rc, lines = prep(f, "--view", f"front={concept(tmp_path / 'front.png', 400, 370)}", "--view", f"34={img}", "--side", "left")
    assert rc == 0, lines
    fit = json.loads((f / "camera_fit.json").read_text(encoding="utf-8"))["data"]["cameras"]["34"]
    assert not (f.parent / "work/camera_fit.json").exists() and -40 <= fit["azimuth_deg"] <= -30
    out = tmp_path / "model_final"
    out.mkdir()
    r = subprocess.run([sys.executable, str(MODEL_TOOLS / "make_spec.py"), "--final", str(out), "--blockout", str(f),
                        "--card", str(PILOT / "_approved/pilot-house/asset-card.yaml"),
                        "--profile", str(PILOT / "PROJECT-PROFILE.yaml"), "--preset", str(PRESET)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    concept_spec = json.loads((out / "spec.json").read_text(encoding="utf-8"))["concept"]
    assert concept_spec["cameras"]["34"] == fit
    assert sorted(concept_spec["views"]) == ["34", "front"]
