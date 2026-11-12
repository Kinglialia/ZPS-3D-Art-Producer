"""L3: init_sources.py fills the computable fields of sources.json and leaves the rest as TODO that check_inputs refuses.
The worker then writes only what needs the eyes: the material codes and, without a card entry, the height of the door."""
import json
import shutil
import subprocess
import sys

import yaml

from conftest import AGENT, TOOLS

PILOT = AGENT.parents[3] / "tests/fixtures/pilot"


def project(tmp_path, has_map=False, card=None, profile=None):
    a = tmp_path / "_approved/pilot-house"
    shutil.copytree(PILOT / "_approved/pilot-house", a)
    if card is not None:
        (a / "asset-card.yaml").write_text(yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
    prof = tmp_path / "PROJECT-PROFILE.yaml"
    doc = yaml.safe_load((PILOT / "PROJECT-PROFILE.yaml").read_text(encoding="utf-8")) | {"has_map": has_map} | (profile or {})
    prof.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    w = tmp_path / "production/assets/pilot-house/blockout/v1/final"
    w.mkdir(parents=True)
    return a, prof, w


def card_of(a):
    return yaml.safe_load((a / "asset-card.yaml").read_text(encoding="utf-8"))


def init(a, prof, w):
    r = subprocess.run([sys.executable, str(TOOLS / "init_sources.py"), "--work", str(w), "--approved", str(a),
                        "--profile", str(prof)], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), json.loads((w / "sources.json").read_text(encoding="utf-8"))


def inputs(a, prof, w):
    r = subprocess.run([sys.executable, str(TOOLS / "check_inputs.py"), "--work", str(w), "--approved", str(a),
                        "--profile", str(prof)], capture_output=True, text=True)
    doc = json.loads((w / "review/checks/inputs.json").read_text(encoding="utf-8"))
    return r.returncode, {c["check"]: c for c in doc["checks"]}


def test_every_computable_field_comes_from_the_card_the_profile_and_the_preset(tmp_path):
    a, prof, w = project(tmp_path)
    rc, line, s = init(a, prof, w)
    assert rc == 0 and line.endswith("; TODO: materials"), line
    assert s["layout"] == {"w": 4, "d": 4, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"}
    assert (s["character_h"], s["door_h"], s["door_h_source"]) == (
        1.6, 1.8, "asset-card.yaml scale_overrides cửa height_m")
    assert s["camera"] == {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}
    assert s["files"]["layout"] == str(a / "asset-card.yaml") and s["files"]["material"] == str(a / "pilot-house.material.md")
    import hashlib
    assert s["files"]["layout_sha256"] == hashlib.sha256((a / "asset-card.yaml").read_bytes()).hexdigest()
    assert s["files"]["material_sha256"] == hashlib.sha256((a / "pilot-house.material.md").read_bytes()).hexdigest()


def test_check_inputs_refuses_the_todo_value_until_the_worker_fills_it_and_then_passes(tmp_path):
    """The material codes need the eyes of the model, so init_sources leaves them; a TODO that check_inputs accepted
    would reach the build as a material that does not exist."""
    a, prof, w = project(tmp_path)
    init(a, prof, w)
    rc, checks = inputs(a, prof, w)
    assert (rc, checks["inputs.todo"]["status"], checks["inputs.todo"]["value"]) == (1, "fail", ["materials"])
    s = json.loads((w / "sources.json").read_text(encoding="utf-8"))
    s["materials"] = ["STONE", "TIMBER", "TEAL"]
    (w / "sources.json").write_text(json.dumps(s), encoding="utf-8")
    rc, checks = inputs(a, prof, w)
    assert (rc, {k: c["status"] for k, c in checks.items()}) == (0, {
        "inputs.files": "pass", "inputs.todo": "pass", "inputs.sources_keys": "pass", "inputs.layout_source": "pass"})


def test_a_card_without_a_scale_override_leaves_the_door_height_to_the_worker(tmp_path):
    a, prof, w = project(tmp_path)
    card = card_of(a) | {"scale_overrides": []}
    a, prof, w = project(tmp_path / "second", card=card)
    rc, line, s = init(a, prof, w)
    assert line.endswith("; TODO: door_h, door_h_source, materials"), line
    assert (s["door_h"].startswith("TODO"), s["door_h_source"].startswith("TODO")) == (True, True)
    rc, checks = inputs(a, prof, w)
    assert checks["inputs.todo"]["value"] == ["door_h", "door_h_source", "materials"]


def test_two_scale_override_entries_are_not_guessed(tmp_path):
    a0, _, _ = project(tmp_path / "base")
    card = card_of(a0) | {"scale_overrides": [{"name": "cửa", "height_m": 1.8}, {"name": "bàn", "height_m": 0.7}]}
    a, prof, w = project(tmp_path / "two", card=card)
    assert init(a, prof, w)[1].endswith("; TODO: door_h, door_h_source, materials")


def test_a_second_run_keeps_the_worker_values_and_writes_the_new_card_numbers_and_hashes(tmp_path):
    a, prof, w = project(tmp_path)
    init(a, prof, w)
    s = json.loads((w / "sources.json").read_text(encoding="utf-8"))
    s["materials"] = ["STONE"]
    (w / "sources.json").write_text(json.dumps(s), encoding="utf-8")
    (a / "asset-card.yaml").write_text(yaml.safe_dump(card_of(a) | {"size_m": {"w": 5, "d": 4, "h": 3.7}}), encoding="utf-8")
    rc, line, again = init(a, prof, w)
    assert (rc, line.endswith("; nothing left to fill"), again["materials"], again["layout"]["w"]) == (0, True, ["STONE"], 5)
    assert again["files"]["layout_sha256"] != s["files"]["layout_sha256"]


def test_a_door_height_the_worker_measured_stays_when_the_card_has_no_override(tmp_path):
    a0, _, _ = project(tmp_path / "base")
    a, prof, w = project(tmp_path / "second", card=card_of(a0) | {"scale_overrides": []})
    init(a, prof, w)
    s = json.loads((w / "sources.json").read_text(encoding="utf-8"))
    s["door_h"], s["door_h_source"] = 1.7, "concept_albedo.png: cửa cao 1.06 lần nhân vật"
    (w / "sources.json").write_text(json.dumps(s), encoding="utf-8")
    assert init(a, prof, w)[2]["door_h"] == 1.7


def test_with_a_map_the_layout_numbers_are_todo_because_only_the_layout_file_has_them(tmp_path):
    a, prof, w = project(tmp_path, has_map=True)
    (a / "pilot-house.layout.md").write_text("W 4.0 D 4.0 H 3.7\n", encoding="utf-8")
    rc, line, s = init(a, prof, w)
    assert line.endswith("; TODO: character_h, door_h, door_h_source, layout, materials"), line
    assert s["files"]["layout"] == str(a / "pilot-house.layout.md") and s["camera"]["elevation_deg"] == 35
    assert inputs(a, prof, w)[1]["inputs.todo"]["value"] == [
        "character_h", "door_h", "door_h_source", "layout", "materials"]
