"""D29: only the user's DUYỆT 2 arms a deletion; the next session's start (hook `startup` or `clear`) deletes it, never
the session that approved, `resume`, `compact` or a hand-run `P next`. `P keep` cancels, `P purge` deletes now, a redo
after a purge is refused, the board and the feedback links still resolve, and `P next` warns above `disk_warn_gb`."""
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
# every final/ and all of work/ (the Meshy download). Text records, step text sources and board images stay.
DELETED = [
    "assemble/v1/final/model/pilot-house.blend", "assemble/v1/final/model/pilot-house.glb",
    "blockout/v1/final/assembled.glb", "model/v1/final/pilot-house-untextured.glb", "model/v1/final/pilot-house.blend",
    "texture/v1/work/meshy/call-1/base_color.png", "texture/v1/work/meshy/call-1/glb.glb",
    "texture/v1/work/meshy/call-1/meshy_call.json", "texture/v1/work/meshy/call-1/task.json",
    "texture/v1/work/meshy/call-1/topology.json"]
HERO = "texture/v1/final/final_lit_vs_concept.png"
MARK = "feedback/texture-v1-1/final_lit_vs_concept.png"
SOURCES = ["blockout/v1/final/part_graph.json", "blockout/v1/final/sources.json", "model/v1/final/spec.json",
           "texture/v1/final/texture_spec.json", "model/v1/final/parts_lib.py"]


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


def hook(root, source, sid="s2", env=None):
    doc = {"session_id": sid, "transcript_path": f"/t/{sid}.jsonl", "source": source, "hook_event_name": "SessionStart"}
    return p(root, "next", "--session", env=env, stdin=json.dumps(doc))


def tree(root, prod="production"):
    a = root / prod / "assets" / AID
    return sorted(x.relative_to(a).as_posix() for x in a.rglob("*") if x.is_file())


def approve(root, *extra, env=None, ok=True):
    return p(root, "feedback", AID, "đạt", "--action", "approve", *extra, env=env, ok=ok)


def ledger(root, prod="production"):
    return [l.split(" · ", 2)[2] for l in (root / prod / "ledger.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("- ")]


def test_a_producer_approval_arms_nothing_and_a_new_session_deletes_nothing(proj):
    """D29.2: a test run the Producer approves keeps every file for the user to look at."""
    p(proj, "approvals", "set", "test_mode", "true", "--by", "bật test mode")
    before = tree(proj)
    assert approve(proj, "--by", "producer") == "pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong\n"
    assert not (proj / A / "purge-pending.json").exists()
    hook(proj, "startup")
    assert tree(proj) == before
    assert ledger(proj)[-2:] == ["pilot-house · assemble v1 · duyệt bởi Producer (test_mode)",
                                 "pilot-house · Producer approve assemble · đạt"]


def test_a_producer_approval_without_test_mode_is_refused_and_changes_nothing(proj):
    st = (proj / A / "status.json").read_text(encoding="utf-8")
    assert approve(proj, "--by", "producer", ok=False) == (
        "LỖI: pilot-house: --by producer chỉ chạy khi production/policy.yaml có test_mode: true; "
        "dự án thật do người dùng duyệt\n")
    assert (proj / A / "status.json").read_text(encoding="utf-8") == st


def test_the_users_approval_arms_and_prints_the_list_but_nothing_is_deleted_in_that_session(proj):
    """D29.3, D29.4: the approving session (s1), a hand-run `P next`, `resume` and `compact` continue that session."""
    hook(proj, "startup", sid="s1")
    before = tree(proj)
    out = approve(proj).splitlines()
    total = sum((proj / A / r).stat().st_size for r in DELETED)
    assert out[:2] == ["pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong",
                       f"Lệnh xóa D29: 10 file, {total / 1024:.1f} KB; thu nhỏ 1 ảnh trang duyệt trỏ tới; xóa ở đầu "
                       "phiên sau (hook SessionStart: startup hoặc clear). Giữ: `keep pilot-house`. Xóa ngay: "
                       "`purge pilot-house --by \"<nguyên văn>\"`. Danh sách: "
                       "production/assets/pilot-house/purge-pending.json"]
    assert [l.split(":")[0].strip() for l in out[2:]] == ["assemble/v1", "blockout/v1", "model/v1", "texture/v1"]
    doc = json.loads((proj / A / "purge-pending.json").read_text(encoding="utf-8"))
    assert ([d["path"] for d in doc["delete"]], doc["thumbs"], doc["session"]) == (DELETED, [HERO], "s1")
    assert f"[{AID}] chờ xóa" in p(proj, "next")
    for src in ("resume", "compact"):
        hook(proj, src, sid="s1")
    hook(proj, "startup", sid="s1")
    assert tree(proj) == sorted(before + ["purge-pending.json"])


@pytest.mark.parametrize("source", ["startup", "clear"])
def test_a_new_session_deletes_exactly_the_files_outside_the_keep_set(proj, source):
    approve(proj)
    before = tree(proj)
    out = hook(proj, source)
    assert f"[{AID}] đã xóa 10 file, thu nhỏ 1 ảnh, giải phóng " in out
    after = tree(proj)
    assert sorted(set(before) - set(after)) == sorted(DELETED + ["purge-pending.json"])
    assert sorted(set(after) - set(before)) == ["purge-manifest.json"]
    assert all(r in after for r in SOURCES + [MARK, "status.json", "feedback.md", "texture/v1/findings.json",
                                              "texture/v1/review-out.md", "texture/v1/final/review/checks/tex_measure.json"])
    assert Image.open(proj / A / HERO).size == (1024, 512)
    assert not (proj / A / "texture/v1/work").exists()
    man = json.loads((proj / A / "purge-manifest.json").read_text(encoding="utf-8"))
    assert ([d["path"] for d in man["deleted"]], [t["path"] for t in man["thumbnails"]], man["source"]) == (
        DELETED, [HERO], source)
    st = json.loads((proj / A / "status.json").read_text(encoding="utf-8"))
    assert st["purged"]["manifest"] == "production/assets/pilot-house/purge-manifest.json"
    assert sorted(x.name for x in (proj / "deliver" / AID / "model").iterdir()) == ["pilot-house.blend",
                                                                                    "pilot-house.glb"]
    assert hook(proj, "startup", sid="s3").count("đã xóa") == 0


def test_keep_cancels_the_pending_deletion(proj):
    """D29.5: the user changes their mind before the next session; nothing may be lost."""
    approve(proj)
    before = tree(proj)
    assert p(proj, "keep", AID, "--by", "giữ lại") == "pilot-house: đã hủy lệnh xóa; mọi file giữ nguyên\n"
    hook(proj, "startup")
    assert tree(proj) == [r for r in before if r != "purge-pending.json"]
    assert p(proj, "keep", AID, ok=False) == "LỖI: pilot-house: không có lệnh xóa nào đang chờ\n"


def test_purge_deletes_now_and_zip_packs_the_files_first(proj):
    """D29.5, D29.9: the user wants the space now and a copy of what goes, including the full-size board images."""
    approve(proj)
    z = proj / "keep" / "pilot.zip"
    out = p(proj, "purge", AID, "--by", "xóa luôn đi", "--zip", str(z))
    assert out.startswith("[pilot-house] đã xóa 10 file, thu nhỏ 1 ảnh")
    assert not any((proj / A / r).exists() for r in DELETED)
    assert sorted(zipfile.ZipFile(z).namelist()) == sorted(f"{AID}/{r}" for r in DELETED + [HERO])
    assert ledger(proj)[-1].endswith(f" · by: xóa luôn đi · nén {z}")


def test_purge_refuses_an_asset_before_duyet_2(proj):
    """D29.1: before DUYỆT 2 the user still compares versions; every file stays."""
    assert p(proj, "purge", AID, "--by", "xóa", ok=False) == (
        "LỖI: pilot-house: không xóa: chưa DUYỆT 2 hoặc đang làm lại (state=waiting_human)\n")


def test_a_redo_between_the_arm_and_the_next_session_cancels_the_deletion(proj):
    """The fix round needs the finals the arm listed; the redo already dispatched the texture worker."""
    approve(proj)
    p(proj, "feedback", AID, "mái tối", "--action", "redo", "--step", "texture")
    out = hook(proj, "startup")
    assert "[pilot-house] hủy lệnh xóa: chưa DUYỆT 2 hoặc đang làm lại (state=running)" in out
    assert all((proj / A / r).exists() for r in DELETED)


def test_a_redo_after_a_purge_is_refused_with_the_manifest(proj):
    """The locked mesh and the GLBs are gone: a fix round would build on missing inputs."""
    approve(proj)
    hook(proj, "startup")
    at = json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["purged"]["at"]
    assert p(proj, "feedback", AID, "cửa to hơn", "--action", "redo", "--step", "model", ok=False) == (
        f"LỖI: pilot-house: không làm lại được: file trung gian đã xóa lúc {at} (manifest "
        "production/assets/pilot-house/purge-manifest.json); final/ của các bước chỉ còn file text\n")


def test_board_links_and_feedback_marks_still_resolve_after_a_purge(proj, monkeypatch):
    """Every image a card listed before the purge is listed and served after it; GLBs leave the intermediate cards
    (deliver/ keeps the delivered one)."""
    monkeypatch.chdir(proj)
    from core import board, state

    def cards():
        cfg, st = state.load_cfg(), state.load_st(AID)
        return cfg, [board.asset_view(cfg, st, x["id"]) for x in cfg["steps"]]
    approve(proj)
    _, before = cards()
    hook(proj, "startup")
    cfg, after = cards()
    assert [[i["n"] for i in c["images"]] for c in after] == [[i["n"] for i in c["images"]] for c in before]
    assert [c["sheet"] for c in after] == [c["sheet"] for c in before]
    assert all(board.safe_file(cfg, i["u"]) for c in after for i in c["images"])
    assert [c["step"] for c in before if c["glb"]] == ["blockout", "model", "assemble"]
    assert [c["glb"] for c in after] == [None] * 6
    assert (proj / A / MARK).is_file()


def test_both_ab_folders_purge_and_the_codex_edition_never_deletes_by_itself(proj):
    """D29.11: each runtime purges its own folder; Codex has no SessionStart hook, so it only reminds."""
    for rt in ("claude", "codex"):
        shutil.copytree(proj / "production", proj / f"production-{rt}")
    env = {"claude": {"PRODUCER_ROOT": "production-claude", "PRODUCER_RUNTIME": "claude"},
           "codex": {"PRODUCER_ROOT": "production-codex", "PRODUCER_RUNTIME": "codex"}}
    for rt in ("claude", "codex"):
        assert "Lệnh xóa D29: 10 file" in approve(proj, env=env[rt])
    assert "đã xóa 10 file" in hook(proj, "startup", env=env["claude"])
    out = hook(proj, "startup", env=env["codex"])
    assert (f"[{AID}] chờ xóa" in out and "bản Codex không tự xóa" in out)
    assert all((proj / "production-codex/assets" / AID / r).exists() for r in DELETED)
    assert not any((proj / "production-claude/assets" / AID / r).exists() for r in DELETED)
    assert "đã xóa 10 file" in p(proj, "purge", AID, "--by", "xóa", env=env["codex"])


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
                                                              "views_front", "views_rest"]


def test_an_arm_that_cannot_write_its_zip_keeps_duyet_2_and_deletes_nothing(proj):
    """The approval already filled deliver/; a bad --zip path must not undo it or arm a deletion without its copy."""
    (proj / "zips").mkdir()
    out = approve(proj, "--zip", str(proj / "zips"))
    assert out.splitlines()[0] == "pilot-house: đã duyệt assemble v1 → assemble/done. Tiếp: xong"
    assert out.splitlines()[1].startswith("chưa lập được lệnh xóa D29: ")
    assert json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["state"] == "done"
    assert not (proj / A / "purge-pending.json").exists()


def test_an_image_that_cannot_be_shrunk_keeps_its_pixels_and_the_purge_still_records(proj):
    """A truncated PNG opens (size known) but does not decode: the purge must still write its manifest and marker."""
    raw = (proj / A / HERO).read_bytes()
    (proj / A / HERO).write_bytes(raw[:200])
    approve(proj)
    assert "đã xóa 10 file, thu nhỏ 1 ảnh" in p(proj, "purge", AID, "--by", "xóa")
    man = json.loads((proj / A / "purge-manifest.json").read_text(encoding="utf-8"))
    assert man["thumbnails"][0]["path"] == HERO and man["thumbnails"][0]["error"]
    assert (proj / A / HERO).read_bytes() == raw[:200]
    assert json.loads((proj / A / "status.json").read_text(encoding="utf-8"))["purged"]


def test_archive_refuses_an_asset_with_a_pending_deletion(proj):
    """`P next` and `P purge` read assets/ only: an archived pending deletion would never free its space."""
    approve(proj)
    assert p(proj, "archive", AID, ok=False) == (
        "LỖI: pilot-house: còn lệnh xóa D29 đang chờ (archive/ không được dọn): `keep pilot-house` hoặc "
        "`purge pilot-house` trước\n")
