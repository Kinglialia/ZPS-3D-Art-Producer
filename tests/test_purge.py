"""D40: the user's DUYỆT 2 deletes in the same command, after deliver/ and the run report exist. A Producer approval,
`P keep`, `purge: off`, a missing report and an A/B root without a result delete nothing. `P purge` deletes later, a
redo after a purge is refused, the board and the feedback links still resolve, a v0.7 pending file is only announced,
and `P next` warns above `disk_warn_gb`."""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from flowkit import A, AID, counts, to_texture
from shared import P

# The fake flow writes text into every output; these are the files a purge must delete: the GLB and .blend files of
# every final/ and all of work/ (the Meshy download, the JSON meshes of custom_parts.py, the log of the gate_all.py that ingest runs on
# the blockout, which also builds the part meshes). Text records, step text
# sources and board images stay, and so does the asset's custom_parts.py (D32.3): a redo after DUYỆT 2 rebuilds from
# the part graph, and the graph names its functions.
DELETED = [
    "assemble/v1/final/model/pilot-house.blend", "assemble/v1/final/model/pilot-house.glb",
    "blockout/v1/final/assembled.glb", "blockout/v1/final/parts/base.glb", "blockout/v1/final/parts/door.glb",
    "blockout/v1/final/parts/roof_b.glb", "blockout/v1/final/parts/roof_f.glb", "blockout/v1/final/parts/walls.glb",
    "blockout/v1/work/custom_mesh/ridge.json", "blockout/v1/work/logs/gate_all.log",
    "model/v1/final/pilot-house-untextured.glb", "model/v1/final/pilot-house.blend",
    "texture/v1/work/meshy/call-1/base_color.png", "texture/v1/work/meshy/call-1/glb.glb",
    "texture/v1/work/meshy/call-1/meshy_call.json", "texture/v1/work/meshy/call-1/task.json",
    "texture/v1/work/meshy/call-1/topology.json"]
HERO = "texture/v1/final/final_lit_vs_concept.png"
MARK = "feedback/texture-v1-1/final_lit_vs_concept.png"
REJECTED = ["blockout/v1/final/BLOCKOUT.rejected-2.md", "texture/v1/review-out.rejected-1.md"]
SHOW = ["show/pilot-house-bundle.html", "show/pilot-house-texture-v1.html", "show/pilot-house.html"]
PUSH = ["board/push/p1/offers/p1~pilot-house.json", "board/push/p1/pilot-house_glb.json"]
PIDS = ["pids/blender/pilot-house-4242.pid", "pids/meshy/pilot-house.pid"]
OTHERS_KEPT = ["show/pilot-house-2.html", "show/pilot-house-2-texture-v1.html", "board/push/p1/offers/p1~pilot-house-2.json",
               "board/push/p1/pilot-house-2_glb.json", "board/push/p1/pushes/p1.json", "pids/blender/pilot-house-2.pid"]
SOURCES = ["blockout/v1/final/part_graph.json", "blockout/v1/final/parts_lib.py", "blockout/v1/final/sources.json",
           "custom_parts.py", "model/v1/final/parts_lib.py", "model/v1/final/spec.json",
           "texture/v1/final/texture_spec.json"]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Waiting at DUYỆT 2. The texture hero is a real 2000×1000 PNG (the board links it, so it becomes a thumbnail),
    and a marked image sits in feedback/ (feedback.md links it)."""
    root = tmp_path_factory.mktemp("purge")
    f = to_texture(root)
    f.work("t1", meshy="")
    f.review("t1", verdict="PASS", counts=counts(), top_fix=None)
    f.assemble("a1")
    Image.new("RGB", (2000, 1000), (200, 80, 40)).save(root / A / HERO)
    (root / A / MARK).parent.mkdir(parents=True)
    Image.new("RGB", (64, 64)).save(root / A / MARK)
    (root / A / "custom_parts.py").write_text("def ridge(w, d, h):\n    return None\n", encoding="utf-8")
    (root / A / "blockout/v1/work/custom_mesh").mkdir(parents=True)
    (root / A / "blockout/v1/work/custom_mesh/ridge.json").write_text("{}", encoding="utf-8")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    for r in REJECTED:
        (root / A / r).write_text("# report refused\n", encoding="utf-8")
    for r in SHOW + PUSH + PIDS + OTHERS_KEPT:
        (root / "production" / r).parent.mkdir(parents=True, exist_ok=True)
        (root / "production" / r).write_text(str(dead.pid) if r.endswith(".pid") else "x" * 300, encoding="utf-8")
    (root / A.replace(AID, "pilot-house-2")).mkdir()
    (root / "production/pids/blender/pilot-house-live.pid").write_text(str(os.getpid()), encoding="utf-8")
    return root


@pytest.fixture
def proj(base, tmp_path):
    root = tmp_path / "p"
    shutil.copytree(base, root, symlinks=True)
    return root


def p(root, *args, ok=True, env=None, stdin=None):
    r = subprocess.run([sys.executable, str(P), *args], cwd=root, capture_output=True, text=True,
                       env=os.environ | (env or {}), input=stdin if stdin is not None else "")
    assert (r.returncode == 0) is ok, r.stderr
    return r.stdout if ok else r.stderr


def tree(root, prod="production"):
    a = root / prod / "assets" / AID
    return sorted(x.relative_to(a).as_posix() for x in a.rglob("*") if x.is_file())


def others(root, prod="production"):
    base = root / prod
    return sorted(x.relative_to(base).as_posix() for d in ("show", "board", "pids") for x in (base / d).rglob("*")
                  if x.is_file())


def approve(root, *extra, env=None, ok=True):
    return p(root, "feedback", AID, "đạt", "--action", "approve", *extra, env=env, ok=ok)


def ledger(root, prod="production"):
    return [l.split(" · ", 2)[2] for l in (root / prod / "ledger.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("- ")]


def total(root, rels, others_rels):
    return sum((root / A / r).stat().st_size for r in rels) + sum((root / "production" / r).stat().st_size
                                                                    for r in others_rels)


def test_a_producer_approval_deletes_nothing_because_the_user_still_looks_at_a_test_run_d29_2(proj):
    p(proj, "approvals", "set", "test_mode", "true", "--by", "bật test mode")
    before, before_others = tree(proj), others(proj)
    out = approve(proj, "--by", "producer")
    assert out.startswith("pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong\n")
    assert "Sẽ xóa" not in out and "Giữ file" not in out
    assert (tree(proj), others(proj)) == (before, before_others)
    assert not (proj / A / "purge-manifest.json").exists()
    assert ledger(proj)[-2:] == ["pilot-house · assemble v1 · duyệt bởi Producer (test_mode)",
                                 "pilot-house · Producer approve assemble · đạt"]


def test_a_producer_approval_without_test_mode_is_refused_and_changes_nothing(proj):
    st = (proj / A / "status.json").read_text(encoding="utf-8")
    assert approve(proj, "--by", "producer", ok=False) == (
        "LỖI: pilot-house: --by producer chỉ chạy khi production/policy.yaml có test_mode: true; "
        "dự án thật do người dùng duyệt\n")
    assert (proj / A / "status.json").read_text(encoding="utf-8") == st


def test_the_users_approval_deletes_in_the_same_command_after_the_report_is_written_d40_1(proj):
    """The owner chose one command: no pending file, no next session. The notice sits before the result line."""
    gone = DELETED + REJECTED
    size = total(proj, gone, SHOW + PUSH + PIDS)
    out = approve(proj).splitlines()
    n, kb = len(gone) + len(SHOW + PUSH + PIDS), f"{size / 1024:.1f} KB"
    assert out[:3] == ["pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong",
                       f"Sẽ xóa {n} file, {kb}; sau lệnh này không `redo` được.",
                       f"[pilot-house] đã xóa {n} file, thu nhỏ 1 ảnh, giải phóng "
                       + out[2].split("giải phóng ")[1]]
    assert out[2].endswith(". Manifest: production/assets/pilot-house/purge-manifest.json")
    assert (proj / "deliver" / AID / "RUN-REPORT.md").is_file()
    assert not any((proj / A / r).exists() for r in gone)
    assert not any((proj / "production" / r).exists() for r in SHOW + PUSH + PIDS)
    assert all((proj / "production" / r).exists() for r in OTHERS_KEPT + ["pids/blender/pilot-house-live.pid"])
    assert all((proj / A / r).exists() for r in SOURCES + [MARK, "status.json", "feedback.md"])
    assert Image.open(proj / A / HERO).size == (1024, 512)
    assert not (proj / A / "purge-pending.json").exists()
    assert ledger(proj)[-1].startswith(f"pilot-house · đã xóa D40 (approve): {n} file, thu nhỏ 1 ảnh, giải phóng ")


def test_the_manifest_lists_the_files_outside_the_asset_and_the_refused_reports_d40_3(proj):
    approve(proj)
    man = json.loads((proj / A / "purge-manifest.json").read_text(encoding="utf-8"))
    assert sorted(d["path"] for d in man["deleted"]) == sorted(DELETED + REJECTED)
    assert sorted(d["path"] for d in man["deleted_other"]) == sorted(SHOW + PUSH + PIDS)
    assert (man["source"], man["by"], [t["path"] for t in man["thumbnails"]]) == ("approve", None, [HERO])
    st = json.loads((proj / A / "status.json").read_text(encoding="utf-8"))
    assert st["purged"]["manifest"] == "production/assets/pilot-house/purge-manifest.json"
    assert sorted(x.name for x in (proj / "deliver" / AID / "model").iterdir()) == ["pilot-house.blend", "pilot-house.glb"]


def test_a_sibling_asset_whose_id_starts_with_ours_keeps_its_pages_pushes_and_pid_d40_3(proj):
    approve(proj)
    assert sorted(set(others(proj)) & set(OTHERS_KEPT)) == sorted(OTHERS_KEPT)
    assert "pids/blender/pilot-house-live.pid" in others(proj)


def test_keep_before_the_approval_makes_that_approval_delete_nothing_d40_5(proj):
    before, before_others = tree(proj), others(proj)
    assert p(proj, "keep", AID, "--by", "giữ lại") == "pilot-house: lần DUYỆT 2 tới sẽ không xóa file\n"
    out = approve(proj)
    assert out.splitlines()[1] == ("Giữ file, không xóa: đã `keep pilot-house` trước khi duyệt. "
                                   "Xóa sau: `purge pilot-house --by \"<nguyên văn>\"`.")
    assert (tree(proj), others(proj)) == (before, before_others)
    assert "keep_files" not in json.loads((proj / A / "status.json").read_text(encoding="utf-8"))
    assert "đã xóa" in p(proj, "purge", AID, "--by", "giờ xóa")


def test_keep_after_a_plain_approval_has_nothing_to_cancel(proj):
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ hết")
    approve(proj)
    assert p(proj, "keep", AID, ok=False) == ("LỖI: pilot-house: đã DUYỆT 2, không có lệnh xóa nào đang chờ; "
                                              "mọi file còn nguyên\n")


def test_purge_off_in_policy_deletes_nothing_and_the_manual_purge_still_works_d40_5(proj):
    before, before_others = tree(proj), others(proj)
    p(proj, "approvals", "set", "purge", "off", "--by", "tôi muốn giữ file")
    out = approve(proj)
    assert out.splitlines()[1] == ("Giữ file, không xóa: policy.yaml có purge: off. "
                                   "Xóa sau: `purge pilot-house --by \"<nguyên văn>\"`.")
    assert (tree(proj), others(proj)) == (before, before_others)
    assert "đã xóa" in p(proj, "purge", AID, "--by", "xóa đi")
    assert not any((proj / A / r).exists() for r in DELETED)


def test_purge_zip_packs_what_goes_into_the_folder_then_deletes_d40_5(proj):
    z = proj / "backup"
    p(proj, "approvals", "set", "purge_zip", str(z), "--by", "nén trước khi xóa")
    out = approve(proj)
    assert "đã xóa" in out and f" · nén {z / 'pilot-house.zip'}" in ledger(proj)[-1]
    names = zipfile.ZipFile(z / "pilot-house.zip").namelist()
    assert sorted(names) == sorted([f"{AID}/{r}" for r in DELETED + REJECTED + [HERO]]
                                   + [f"production/{r}" for r in SHOW + PUSH + PIDS])
    assert not any((proj / A / r).exists() for r in DELETED)


def test_an_explicit_zip_file_wins_over_the_purge_zip_folder(proj):
    p(proj, "approvals", "set", "purge_zip", str(proj / "backup"), "--by", "nén")
    approve(proj, "--zip", str(proj / "mine.zip"))
    assert (proj / "mine.zip").is_file() and not (proj / "backup").exists()


def test_a_zip_that_cannot_be_written_keeps_duyet_2_and_deletes_nothing(proj):
    """The approval already filled deliver/; a bad --zip path must not undo it or delete without its copy."""
    (proj / "zips").mkdir()
    before, before_others = tree(proj), others(proj)
    out = approve(proj, "--zip", str(proj / "zips")).splitlines()
    assert out[0] == "pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong"
    assert out[1].startswith("Chưa xóa, file giữ nguyên: ") and out[1].endswith(
        "Xóa sau: `purge pilot-house --by \"<nguyên văn>\"`.")
    assert json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["state"] == "done"
    assert (tree(proj), others(proj)) == (before, before_others)


def test_a_report_that_could_not_be_written_stops_the_purge_and_says_why_d40_1(proj, monkeypatch):
    """D40.1: the run report must exist before anything is deleted; the files stay and `purge` deletes them later."""
    monkeypatch.chdir(proj)
    from core import loop, report
    monkeypatch.setattr(report, "finish", lambda st: (False, "KHÔNG ghi được RUN-REPORT.md: OSError: đầy đĩa"))
    before = tree(proj)
    ok, text = loop.act(AID, "approve", "đạt")
    lines = text.splitlines()
    assert ok and lines[1] == ("Giữ file, không xóa: chưa có RUN-REPORT.md. "
                               "Xóa sau: `purge pilot-house --by \"<nguyên văn>\"`.")
    assert lines[2] == "KHÔNG ghi được RUN-REPORT.md: OSError: đầy đĩa"
    assert tree(proj) == before


def test_a_broken_policy_file_keeps_the_approval_and_the_files_and_says_so_d29_5(proj):
    """The approval is saved before the purge decides; a policy that cannot be read must not turn it into an error."""
    (proj / "production/policy.yaml").write_text("purge: [\n", encoding="utf-8")
    before, before_others = tree(proj), others(proj)
    out = approve(proj).splitlines()
    assert out[0] == "pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong"
    assert out[1].startswith("Giữ file, không xóa: production/policy.yaml sai cú pháp YAML") and "Xóa sau:" in out[1]
    assert json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["state"] == "done"
    assert (tree(proj), others(proj)) == (before, before_others)


def test_the_check_before_the_delete_still_stops_an_asset_without_its_delivered_package_d29_5(proj, monkeypatch):
    """D29.5: the approve path checks again that the package is delivered; no package, no delete."""
    monkeypatch.chdir(proj)
    from core import loop, purge
    monkeypatch.setattr(purge, "DELIVER", proj / "nowhere")
    before = tree(proj)
    ok, text = loop.act(AID, "approve", "đạt")
    assert ok and text.splitlines()[1].startswith("Giữ file, không xóa: không có ")
    assert tree(proj) == before


def test_the_remote_row_carries_the_deletion_line_and_the_purge_removes_the_files_it_pushed_d40_4(proj):
    """remote.html spreads each pushed row into the payload that board.js renders, so the row decides what the remote
    page shows. The push layout the purge deletes from is the one `board prepare` writes."""
    p(proj, "approvals", "set", "review_board", "local+remote", "--by", "cả điện thoại")
    push = json.loads(p(proj, "board", "prepare", "--url", "https://claude.ai/artifact/x"))["push"]
    d = proj / "production/board/push" / push
    pushed = [d / "offers" / f"{push}~{AID}.json", d / f"{AID}_glb.json"]
    assert all(f.is_file() for f in pushed)
    row = json.loads(pushed[0].read_text(encoding="utf-8"))
    n = len(DELETED + REJECTED + SHOW + PUSH + PIDS) + 1
    assert row["purge"].startswith(f"Sẽ xóa {n} file, ") and row["purge"].endswith("; sau lệnh này không `redo` được.")
    approve(proj)
    assert not any(f.exists() for f in pushed)
    assert (d / "pushes" / f"{push}.json").is_file()


def test_ab_folders_keep_every_file_until_the_pair_is_judged_and_then_next_only_reminds_d29_11(proj):
    """Producer decision 2026-11-10: the blind pair board must never show one side purged. With no hook left, the
    purge after the pair result is the user's `P purge`; `P next` reminds before and after."""
    for rt in ("claude", "codex"):
        shutil.copytree(proj / "production", proj / f"production-{rt}")
    env = {rt: {"PRODUCER_ROOT": f"production-{rt}", "PRODUCER_RUNTIME": rt} for rt in ("claude", "codex")}
    wait = (f"cặp A/B {AID} chưa có kết quả so (chưa `ab prefer {AID} <A|B|tie>` và chưa đủ hai lần `ab judge`): "
            "giữ mọi file tới khi có")
    for rt in ("claude", "codex"):
        out = approve(proj, env=env[rt]).splitlines()
        assert out[1] == f"Giữ file, không xóa: {wait}. Xóa sau: `purge {AID} --by \"<nguyên văn>\"`."
        assert wait in p(proj, "next", env=env[rt])
        assert p(proj, "purge", AID, "--by", "xóa", env=env[rt], ok=False) == f"LỖI: {AID}: không xóa: {wait}\n"
        assert all((proj / f"production-{rt}/assets" / AID / r).exists() for r in DELETED)
    p(proj, "ab", "prefer", AID, "A", "--by", "bản A đẹp hơn", env=env["claude"])
    reminder = (f"[{AID}] đã có kết quả so A/B: `purge {AID} --by \"<nguyên văn>\"` để xóa, `keep {AID}` để giữ")
    assert reminder in p(proj, "next", env=env["claude"])
    assert all((proj / "production-claude/assets" / AID / r).exists() for r in DELETED)
    assert "đã xóa" in p(proj, "purge", AID, "--by", "xóa", env=env["claude"])
    assert not any((proj / "production-claude/assets" / AID / r).exists() for r in DELETED)
    assert reminder not in p(proj, "next", env=env["claude"])


def test_keep_after_the_ab_hold_stops_the_reminder(proj):
    shutil.copytree(proj / "production", proj / "production-codex")
    env = {"PRODUCER_ROOT": "production-codex", "PRODUCER_RUNTIME": "codex"}
    approve(proj, env=env)
    assert p(proj, "keep", AID, env=env) == "pilot-house: không nhắc xóa nữa; mọi file giữ nguyên\n"
    assert "chờ xóa" not in p(proj, "next", env=env)


def test_purge_deletes_now_and_zip_packs_the_files_first(proj):
    """D29.5, D29.9: the user wants the space later or now, and a copy of what goes, with the full-size board images."""
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ")
    approve(proj)
    z = proj / "keep" / "pilot.zip"
    out = p(proj, "purge", AID, "--by", "xóa luôn đi", "--zip", str(z)).splitlines()
    n = len(DELETED + REJECTED + SHOW + PUSH + PIDS)
    assert out[1].startswith(f"[pilot-house] đã xóa {n} file, thu nhỏ 1 ảnh") and out[0].startswith(f"Sẽ xóa {n} file, ")
    assert not any((proj / A / r).exists() for r in DELETED)
    assert sorted(zipfile.ZipFile(z).namelist()) == sorted(
        [f"{AID}/{r}" for r in DELETED + REJECTED + [HERO]] + [f"production/{r}" for r in SHOW + PUSH + PIDS])
    assert ledger(proj)[-1].endswith(f" · by: xóa luôn đi · nén {z}")


def test_purge_refuses_an_asset_before_duyet_2(proj):
    """D29.1: before DUYỆT 2 the user still compares versions; every file stays."""
    assert p(proj, "purge", AID, "--by", "xóa", ok=False) == (
        "LỖI: pilot-house: không xóa: chưa DUYỆT 2 hoặc đang làm lại (state=waiting_human)\n")


def test_a_redo_after_a_purge_is_refused_with_the_manifest(proj):
    """The locked mesh and the GLBs are gone: a fix round would build on missing inputs."""
    approve(proj)
    at = json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["purged"]["at"]
    assert p(proj, "feedback", AID, "cửa to hơn", "--action", "redo", "--step", "model", ok=False) == (
        f"LỖI: pilot-house: không làm lại được: file trung gian đã xóa lúc {at} (manifest "
        "production/assets/pilot-house/purge-manifest.json); final/ của các bước chỉ còn file text\n")


def test_the_run_report_is_still_printed_after_the_purge_d41(proj):
    """The report is written before the delete and `P report` prints that file, so the budget files may go."""
    approve(proj)
    out = p(proj, "report", AID)
    assert out == (proj / "deliver" / AID / "RUN-REPORT.md").read_text(encoding="utf-8").rstrip() + "\n"
    assert out.startswith(f"# RUN-REPORT {AID}")


def test_the_heartbeat_log_stays_so_a_report_after_the_purge_still_counts_the_codex_calls_x4(proj):
    """The report counts the codex exec calls from vN/heartbeat.log; the purge keeps that log, so a later report agrees."""
    log = proj / A / "texture/v1/heartbeat.log"
    log.write_text("2026-11-10 10:00:00 · codex exec · start\n2026-11-10 10:05:00 · codex exec · start\n", encoding="utf-8")
    approve(proj)
    row = next(l for l in p(proj, "report", AID).splitlines() if l.startswith("| texture |"))
    assert (log.is_file(), row.split(" | ")[12]) == (True, "2")


def test_board_links_and_feedback_marks_still_resolve_after_a_purge(proj, monkeypatch):
    """Every image a card listed before the purge is listed and served after it; GLBs leave the intermediate cards
    (deliver/ keeps the delivered one)."""
    monkeypatch.chdir(proj)
    from core import board, state

    def cards():
        cfg, st = state.load_cfg(), state.load_st(AID)
        return cfg, [board.asset_view(cfg, st, x["id"]) for x in cfg["steps"]]
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ")
    approve(proj)
    _, before = cards()
    p(proj, "purge", AID, "--by", "xóa")
    cfg, after = cards()
    assert [[i["n"] for i in c["images"]] for c in after] == [[i["n"] for i in c["images"]] for c in before]
    assert [c["sheet"] for c in after] == [c["sheet"] for c in before]
    assert all(board.safe_file(cfg, i["u"]) for c in after for i in c["images"])
    assert [c["step"] for c in before if c["glb"]] == ["blockout", "model", "assemble"]
    assert [c["glb"] for c in after] == [None] * 5
    assert (proj / A / MARK).is_file()


def test_a_v07_pending_file_is_announced_never_run_and_keep_cancels_it(proj):
    """D40: the next-session path is gone. A project that still has the old file hears about it once per `P next`."""
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ")
    approve(proj)
    (proj / A / "purge-pending.json").write_text("{}", encoding="utf-8")
    before = tree(proj)
    line = (f"[{AID}] còn lệnh xóa cũ (v0.7), script không tự chạy: `purge {AID} --by \"<nguyên văn>\"` để xóa, "
            f"`keep {AID}` để giữ")
    assert p(proj, "next").splitlines().count(line) == 1
    assert p(proj, "next", "--session", stdin=json.dumps({"session_id": "s9", "source": "startup"})).count(line) == 1
    assert tree(proj) == before
    assert p(proj, "keep", AID) == "pilot-house: đã hủy lệnh xóa cũ; mọi file giữ nguyên\n"
    assert line not in p(proj, "next") and "purge-pending.json" not in tree(proj)


def test_next_tells_the_producer_what_the_final_approval_deletes_before_it_runs_d40_4(proj):
    """SKILL.md has the Producer say the size and the no-redo consequence first; this is where it reads them."""
    size = total(proj, DELETED + REJECTED, SHOW + PUSH + PIDS)
    n = len(DELETED + REJECTED + SHOW + PUSH + PIDS)
    line = f"[{AID}] DUYỆT 2: Sẽ xóa {n} file, {size / 1024:.1f} KB; sau lệnh này không `redo` được."
    assert line in p(proj, "next").splitlines()
    p(proj, "keep", AID)
    assert not any("DUYỆT 2: Sẽ xóa" in l for l in p(proj, "next").splitlines())


def test_the_duyet_2_card_carries_the_same_line_only_when_the_approval_will_delete(proj, monkeypatch):
    """D40.4: the button must never announce a deletion that `act` will skip."""
    monkeypatch.chdir(proj)
    from core import board, state

    def card():
        return board.asset_view(state.load_cfg(), state.load_st(AID))["purge"]
    n = len(DELETED + REJECTED + SHOW + PUSH + PIDS)
    size = total(proj, DELETED + REJECTED, SHOW + PUSH + PIDS)
    assert card() == f"Sẽ xóa {n} file, {size / 1024:.1f} KB; sau lệnh này không `redo` được."
    p(proj, "keep", AID)
    assert card() is None
    st = state.load_st(AID)
    st.pop("keep_files")
    state.save_st(st)
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ")
    assert card() is None
    p(proj, "approvals", "set", "purge", "on_approve", "--by", "xóa lại")
    assert card().startswith("Sẽ xóa ")
    assert board.asset_view(state.load_cfg(), state.load_st(AID), "model", 1)["purge"] is None


def test_next_warns_above_disk_warn_gb_and_disk_sums_by_asset_step_and_type(proj):
    """D29.10: the user sees the disk fill before it is full; a broken policy never silences the hook's asset list."""
    pol = proj / "production/policy.yaml"
    text = pol.read_text(encoding="utf-8")
    assert "vượt disk_warn_gb" not in p(proj, "next")
    pol.write_text(text.replace("disk_warn_gb: 20", "disk_warn_gb: 0.00001"), encoding="utf-8")
    assert "vượt disk_warn_gb 1e-05 GB → `disk` để xem chỗ lớn" in p(proj, "next")
    pol.write_text(text.replace("disk_warn_gb: 20", "disk_warn_gb: 0"), encoding="utf-8")
    out = p(proj, "next")
    assert "LỖI: production/policy.yaml: disk_warn_gb: phải là số GB lớn hơn 0" in out and f"[{AID}] assemble/" in out
    pol.write_text(text, encoding="utf-8")
    out = p(proj, "disk").splitlines()
    heads = [l for l in out if not l.startswith("  ")]
    assert heads[0].startswith("production/: ") and heads[0].endswith(" · ngưỡng disk_warn_gb 20 GB")
    assert heads[1:] == ["Theo asset:", "Theo bước:", "Theo loại file:"]
    assert out[2].startswith(f"  {AID}: ")
    steps = out[out.index("Theo bước:") + 1:out.index("Theo loại file:")]
    assert sorted(l.split(":")[0].strip() for l in steps) == ["assemble", "blockout", "feedback", "model", "texture",
                                                              "views"]


def test_an_image_that_cannot_be_shrunk_keeps_its_pixels_and_the_purge_still_records(proj):
    """A truncated PNG opens (size known) but does not decode: the purge must still write its manifest and marker."""
    raw = (proj / A / HERO).read_bytes()
    (proj / A / HERO).write_bytes(raw[:200])
    out = approve(proj)
    assert "thu nhỏ 1 ảnh" in out
    man = json.loads((proj / A / "purge-manifest.json").read_text(encoding="utf-8"))
    assert man["thumbnails"][0]["path"] == HERO and man["thumbnails"][0]["error"]
    assert (proj / A / HERO).read_bytes() == raw[:200]
    assert json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["purged"]


def test_archive_refuses_an_asset_with_a_v07_pending_file(proj):
    """`P next` and `P purge` read assets/ only: an archived pending file would never be announced."""
    p(proj, "approvals", "set", "purge", "off", "--by", "giữ")
    approve(proj)
    (proj / A / "purge-pending.json").write_text("{}", encoding="utf-8")
    assert p(proj, "archive", AID, ok=False) == (
        "LỖI: pilot-house: còn lệnh xóa D29 đang chờ (archive/ không được dọn): `keep pilot-house` hoặc "
        "`purge pilot-house` trước\n")
