"""assemble.py when a tool cannot run at all (docs/producer.md §6.4 "fail → blocked"), no Blender needed: the step must
still write a BLOCKED report, so `ingest` moves the asset to blocked and `retry` can run it again."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

import glbkit
from core.contract import parse_contract, parse_findings

SCRIPTS = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/scripts"
AID, RES = "box", 64


def project(t: Path) -> Path:
    concept = t / "concepts/_approved" / AID
    concept.mkdir(parents=True)
    (concept / "asset-card.yaml").write_text(f"asset: {AID}\ntexture_res: {RES}\n", encoding="utf-8")
    a = t / "production/assets" / AID
    mf, tf = a / "model/v1/final", a / "texture/v1/final"
    mf.mkdir(parents=True)
    tf.mkdir(parents=True)
    glb = glbkit.write(mf / f"{AID}-untextured.glb", *glbkit.box())
    Image.new("RGB", (RES, RES), (90, 60, 40)).save(tf / f"albedo_{RES}.png")
    st = {"id": AID, "title": "Box", "stage": "assemble", "state": "running", "concept_dir": str(concept),
          "versions": {"model": 1, "texture": 1, "assemble": 1}, "approved": {"model": 1, "texture": 1},
          "locked": {"model": hashlib.sha256(glb.read_bytes()).hexdigest()}, "created": "2026-11-09 08:00"}
    (a / "status.json").write_text(json.dumps(st), encoding="utf-8")
    return a / "assemble/v1/report-script.md"


def test_a_blender_that_cannot_start_still_writes_a_blocked_report_whose_finding_the_board_can_parse(tmp_path):
    rep = project(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", AID, "1",
                        "abc123"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (1, "[assemble] fail 1 điểm -> production/assets/box/assemble/v1/report-script.md\n")
    text = rep.read_text(encoding="utf-8")
    assert text.splitlines()[:3] == [
        "STATUS: BLOCKED", "OUTPUT: production/assets/box/assemble/v1/final/",
        "ISSUES: script assemble: FileNotFoundError: [Errno 2] No such file or directory: '/nonexistent/blender'"]
    c = parse_contract(text, {"FINDINGS", "EVIDENCE_OPENED"})
    errs = []
    fs = parse_findings(c["FINDINGS"], [c["EVIDENCE_OPENED"]], errs)
    assert (errs, [(f["priority"], f["kind"]) for f in fs.values()]) == ([], [("blocker", "script")])


def test_the_codex_rule_shape_reads_no_option_after_the_double_dash_so_a_second_blender_never_runs(tmp_path):
    project(tmp_path)
    evil = tmp_path / "evil.sh"
    evil.write_text(f"#!/bin/sh\ntouch {tmp_path / 'ran'}\n", encoding="utf-8")
    evil.chmod(0o755)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", AID, "1",
                        "abc123", "--blender", str(evil)], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (2, f"assemble.py: error: unrecognized arguments: --blender {evil}")
    assert not (tmp_path / "ran").exists() and not (tmp_path / "production/assets" / AID / "assemble/v1/final").exists()


def test_an_id_that_leaves_the_assets_folder_is_refused_before_assemble_deletes_anything(tmp_path):
    project(tmp_path)
    keep = tmp_path / "outside/assemble/v1/final/keep.txt"
    keep.parent.mkdir(parents=True)
    keep.write_text("keep", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--",
                        "../../outside", "1", "abc123"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (
        2, "assemble.py: error: id '../../outside' không hợp lệ: chỉ gồm a-z, 0-9 và '-'")
    assert keep.read_text(encoding="utf-8") == "keep"


def test_run_from_outside_the_project_it_refuses_before_it_writes_anything(tmp_path):
    """Run 4: started from another folder, assemble.py wrote a blocked report under that folder."""
    project(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", AID, "1",
                        "abc123"], cwd=other, capture_output=True, text=True)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (
        2, f"assemble.py: error: không thấy production/assets/{AID}/status.json: chạy lệnh từ gốc project")
    assert list(other.iterdir()) == []


def finding_doc(t: Path, step: str, n: int, notes=(), **fs):
    d = t / "production/assets" / AID / step / f"v{n}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "findings.json").write_text(json.dumps({"version": n, "findings": {
        i: {"priority": "minor", "kind": kind, "status": "open", "region": region, "repair": "sửa"}
        for i, (kind, region) in fs.items()}, **({"resolved_notes": list(notes)} if notes else {})}), encoding="utf-8")
    return d


def test_the_readme_drops_a_note_only_when_a_later_approved_reviewer_confirmed_the_worker_did_it_d27_8(tmp_path,
                                                                                                      monkeypatch):
    """Run 4: "Việc còn mở" listed views_rest F2 (back has 3 board rows), which model built. A texture review with
    `texture_note=pass` no longer drops it: only RESOLVED_CONFIRMED of an approved version does."""
    import assemble
    monkeypatch.chdir(tmp_path)
    st = {"id": AID, "approved": {"views_front": 3, "views_rest": 2, "model": 2, "texture": 4}}
    finding_doc(tmp_path, "views_front", 3, F4=("regen", "front: đinh"))
    finding_doc(tmp_path, "views_rest", 2, F2=("note_texture", "back: hàng ván"), F3=("note_texture", "top: rêu"))
    tex = finding_doc(tmp_path, "texture", 4)
    (tex / "review-out.md").write_text("--- report ---\nVERDICT: PASS\nRUBRIC: light=pass; texture_note=pass\n"
                                          "--- end ---\n", encoding="utf-8")
    finding_doc(tmp_path, "model", 3, notes=["views_rest v2 F3"])
    finding_doc(tmp_path, "model", 2, notes=["views_rest v2 F2"])
    assert assemble.open_work(st) == ["- views_front v3 F4 [minor] front: đinh: sửa",
                                      "- views_rest v2 F3 [minor] top: rêu: sửa"]
