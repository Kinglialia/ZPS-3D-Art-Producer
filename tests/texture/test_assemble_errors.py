"""assemble.py when a tool cannot run at all (docs/producer.md §6.4 "fail → blocked"), no Blender needed: the step must
still write a BLOCKED report, so `ingest` moves the asset to blocked and `retry` can run it again."""
import hashlib
import json
import os
import shlex
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
    (t / "production/pipeline.toml").touch()
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


def renders_json(t: Path, sha: str | None):
    tf = t / "production/assets" / AID / "texture/v1/final"
    (tf / "review").mkdir(parents=True, exist_ok=True)
    doc = {"albedo": f"final/albedo_{RES}.png", "renders": {"unlit_34_front": "review/unlit_34_front.png"}}
    (tf / "review/renders.json").write_text(json.dumps(doc | ({"albedo_sha256": sha} if sha else {})), encoding="utf-8")


def assemble_cli(t: Path):
    return subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", AID,
                           "1", "abc123"], cwd=t, capture_output=True, text=True)


def test_an_albedo_changed_after_its_renders_is_refused_before_blender_so_the_package_never_ships_old_pictures_t2(
        tmp_path):
    """The texture renders are the pictures the owner approved. An albedo edited after them would ship a texture that
    nobody saw, and the compare would only blame the renders."""
    rep = project(tmp_path)
    renders_json(tmp_path, "0" * 64)
    assert assemble_cli(tmp_path).returncode == 1
    assert rep.read_text(encoding="utf-8").splitlines()[2] == (
        f"ISSUES: albedo texture: albedo_{RES}.png đã đổi sau lần render của bước texture (sha256 khác renders.json)")


def test_a_renders_json_without_an_albedo_hash_is_accepted_as_before_t2(tmp_path):
    rep = project(tmp_path)
    renders_json(tmp_path, None)
    assemble_cli(tmp_path)
    assert "FileNotFoundError" in rep.read_text(encoding="utf-8").splitlines()[2], "it went on to start Blender"


def test_a_matching_albedo_hash_goes_on_to_blender_t2(tmp_path):
    rep = project(tmp_path)
    albedo = tmp_path / "production/assets" / AID / f"texture/v1/final/albedo_{RES}.png"
    renders_json(tmp_path, hashlib.sha256(albedo.read_bytes()).hexdigest())
    assemble_cli(tmp_path)
    assert "FileNotFoundError" in rep.read_text(encoding="utf-8").splitlines()[2], "it went on to start Blender"


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
    """Pilot run: started from another folder, assemble.py wrote a blocked report under that folder."""
    project(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", AID, "1",
                        "abc123"], cwd=other, capture_output=True, text=True)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (
        2, "LỖI: không thấy production/pipeline.toml: chạy lệnh từ gốc project")
    assert list(other.iterdir()) == []


def test_an_asset_the_project_does_not_have_is_refused_before_assemble_writes_anything(tmp_path):
    project(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", "/nonexistent/blender", "--", "ghost",
                        "1", "abc123"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (
        2, "assemble.py: error: không thấy production/assets/ghost/status.json: chạy lệnh từ gốc project")
    assert not (tmp_path / "production/assets/ghost").exists()


def finding_doc(t: Path, step: str, n: int, notes=(), **fs):
    d = t / "production/assets" / AID / step / f"v{n}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "findings.json").write_text(json.dumps({"version": n, "findings": {
        i: {"priority": "minor", "kind": kind, "status": "open", "region": region, "repair": "sửa"}
        for i, (kind, region) in fs.items()}, **({"resolved_notes": list(notes)} if notes else {})}), encoding="utf-8")
    return d


def test_the_readme_drops_a_note_only_when_a_later_approved_reviewer_confirmed_the_worker_did_it_d27_8(tmp_path,
                                                                                                      monkeypatch):
    """Pilot run: "Việc còn mở" listed views F2 (back has 3 board rows), which model built. A texture review with
    `texture_note=pass` no longer drops it: only RESOLVED_CONFIRMED of an approved version does."""
    import assemble
    monkeypatch.chdir(tmp_path)
    st = {"id": AID, "approved": {"views": 2, "model": 2, "texture": 4}}
    finding_doc(tmp_path, "views", 2, F2=("note_texture", "back: hàng ván"), F3=("note_texture", "top: rêu"),
                F4=("regen", "front: đinh"))
    tex = finding_doc(tmp_path, "texture", 4)
    (tex / "review-out.md").write_text("--- report ---\nVERDICT: PASS\nRUBRIC: light=pass; texture_note=pass\n"
                                          "--- end ---\n", encoding="utf-8")
    finding_doc(tmp_path, "model", 3, notes=["views v2 F3"])
    finding_doc(tmp_path, "model", 2, notes=["views v2 F2"])
    assert assemble.open_work(st) == ["- views v2 F3 [minor] top: rêu: sửa", "- views v2 F4 [minor] front: đinh: sửa"]


SANDBOX_STACK = "echo '7 Blender _ZN7blender3gpu10MTLBackend18metal_is_supportedEv + 364' >&2\nexit 139\n"


def blender_at(t: Path, body: str) -> Path:
    exe = t / "Blender"
    exe.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def codex_main(t: Path, mp, exe: Path):
    """assemble.main in process as the Codex edition: its runtime.json says `runtime: codex`."""
    import assemble
    mp.chdir(t)
    mp.setattr(assemble, "EDITION", {"runtime": "codex"})
    cmd = [sys.executable, str(SCRIPTS / "assemble.py"), "--blender", str(exe), "--", AID, "1", "abc123"]
    mp.setattr(sys, "argv", cmd[1:])
    try:
        assemble.main()
    except SystemExit as ex:
        return ex.code, shlex.join(cmd)


def test_a_blender_that_dies_in_the_codex_sandbox_prints_the_exact_line_to_run_again(tmp_path, monkeypatch, capsys):
    rep = project(tmp_path)
    code, line = codex_main(tmp_path, monkeypatch, blender_at(tmp_path, SANDBOX_STACK))
    err = capsys.readouterr().err
    assert code == 1
    assert "sandbox của Codex" in err and "\n" + line + "\n" in err
    assert "Blender chết trong sandbox của Codex" in rep.read_text(encoding="utf-8")


def test_inside_the_codex_sandbox_assemble_exits_2_before_it_changes_anything_so_the_line_runs_again_as_is(
        tmp_path, monkeypatch, capsys):
    """Blender always dies in the sandbox (measured 2026-11-13); Codex sets CODEX_SANDBOX only there. A BLOCKED report
    here would make `ingest` block the asset, while the help says to run the same line again."""
    rep = project(tmp_path)
    keep = rep.parent / "final/keep.txt"
    keep.parent.mkdir(parents=True)
    keep.write_text("keep", encoding="utf-8")
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    code, line = codex_main(tmp_path, monkeypatch, blender_at(tmp_path, f"touch {tmp_path / 'ran'}\n"))
    err = capsys.readouterr().err
    assert (code, (tmp_path / "ran").exists(), rep.exists(), keep.read_text(encoding="utf-8")) == (2, False, False, "keep")
    assert list((tmp_path / "production").rglob("*.pid")) == []
    assert "sandbox của Codex" in err and "\n" + line + "\n" in err and "codex_rules.py --write" in err


def test_outside_the_codex_edition_codex_sandbox_and_a_metal_crash_give_the_normal_blocked_report(tmp_path):
    """The sandbox help names installer/codex_rules.py, which only the Codex edition ships."""
    rep = project(tmp_path)
    exe = blender_at(tmp_path, SANDBOX_STACK)
    r = subprocess.run([sys.executable, str(SCRIPTS / "assemble.py"), "--blender", str(exe), "--", AID, "1", "abc123"],
                       cwd=tmp_path, env=os.environ | {"CODEX_SANDBOX": "seatbelt"}, capture_output=True, text=True)
    assert (r.returncode, r.stderr) == (1, "")
    assert rep.read_text(encoding="utf-8").splitlines()[2].startswith("ISSUES: export GLB: assemble_qa ")
