"""A/B of two runtimes (producer.md §16, review-board.md §8, D21.10, D25.J, D26.1). The user judges blind: no runtime or
model name reaches the page, each decision lands in the right runtime folder, labels open only when the batch is
decided, and the pairwise reviewer is asked twice with X/Y swapped."""
import io
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image

from shared import P
from core import ab

AID = "house-a"
HIDDEN = re.compile(r"(?i)claude|codex|opus|sonnet|haiku|gpt-|production|deliver-")


def cli(root, rt, *args, stdin=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME")}
    env |= {"PRODUCER_ROOT": f"production-{rt}", "PRODUCER_RUNTIME": rt} if rt else {}
    r = subprocess.run([sys.executable, str(P), *args], cwd=root, env=env, input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def png(path: Path, size: tuple[int, int], color=(200, 30, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def st_path(root, rt):
    return root / f"production-{rt}/assets/{AID}/status.json"


def patch_st(root, rt, **kw):
    p = st_path(root, rt)
    p.write_text(json.dumps(json.loads(p.read_text(encoding="utf-8")) | kw, ensure_ascii=False), encoding="utf-8")


DONE = {"state": "done", "stage": "assemble", "offer": None, "offer_key": None,
        "versions": {"blockout": 2, "views_front": 1, "views_rest": 1, "model": 1, "texture": 1, "assemble": 1},
        "approved": {"blockout": 2, "views_front": 1, "views_rest": 1, "model": 1, "texture": 1, "assemble": 1},
        "created": "2026-11-09 08:00", "approved_at": {"blockout": "2026-11-09 09:00", "assemble": "2026-11-09 12:30"}}


def package(root, rt, size, extra_line):
    final = root / f"production-{rt}/assets/{AID}/assemble/v1/final"
    png(final / "final_lit_vs_concept.png", size)
    png(final / "review/lit_34_front.png", size, (30, 30, 200))
    (final / "model").mkdir(parents=True, exist_ok=True)
    (final / "model" / f"{AID}.glb").write_bytes(b"glTF" + rt.encode())
    (final / "README.md").write_text(f"# {AID}\n{extra_line}\n", encoding="utf-8")


@pytest.fixture
def two(tmp_path, monkeypatch):
    for rt in ("claude", "codex"):
        cli(tmp_path, rt, "init", "--project", "Pilot", "--concepts", "concepts")
        cli(tmp_path, rt, "new", AID, "--title", "House A")
    (tmp_path / "ab").mkdir()
    (tmp_path / "ab/mapping.json").write_text(json.dumps({"assets": {AID: {"A": "codex", "B": "claude"}}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def done_both(root):
    for rt, size in (("claude", (40, 30)), ("codex", (60, 30))):
        package(root, rt, size, f"vẽ bằng {rt.title()} và gpt-6-astra")
        patch_st(root, rt, **DONE)


def test_assets_present_in_both_runtimes_get_one_random_label_each_and_keep_it(two):
    (two / "ab/mapping.json").unlink()
    cli(two, "codex", "new", "barn-b", "--title", "Barn B")
    m = ab.mapping()
    assert list(m) == [AID] and sorted(m[AID].values()) == ["claude", "codex"]
    cli(two, "claude", "new", "barn-b", "--title", "Barn B")
    m2 = ab.mapping()
    assert (m2[AID], sorted(m2)) == (m[AID], ["barn-b", AID])


@pytest.fixture
def server(two):
    srv = ab.make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def post(url, body, applied=False):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            j = json.loads(r.read())
            code = r.status
    except urllib.error.HTTPError as e:
        j, code = json.loads(e.read()), e.code
    return (code, j["message"], j["applied"]) if applied else (code, j["message"])


def test_the_pair_page_shows_no_runtime_or_model_name_in_text_urls_or_file_names_row_62(server, two):
    done_both(two)
    code, raw = get(server + "/api/board")
    p = json.loads(raw)
    urls = [u for r in p["pairs"] for s in r["sides"] for u in [s["sheet"], s["glb"], *(i["u"] for i in s["images"])]]
    pages = [get(server + x)[1].decode() for x in ("/", "/board.js")]
    assert (code, [r["asset"] for r in p["pairs"]], [s["id"] for s in p["pairs"][0]["sides"]]) == (
        200, [AID], [f"{AID}~A", f"{AID}~B"])
    assert [HIDDEN.findall(x) for x in (raw.decode(), *pages, *urls)] == [[]] * (3 + len(urls))
    assert p["pairs"][0]["sides"][0]["summary"] == [AID, "vẽ bằng … và …"]


def test_each_label_serves_the_files_of_its_own_runtime(server, two):
    done_both(two)
    sides = json.loads(get(server + "/api/board")[1])["pairs"][0]["sides"]
    sizes = [Image.open(io.BytesIO(get(server + s["sheet"])[1])).size for s in sides]
    glbs = [get(server + s["glb"])[1] for s in sides]
    assert (sizes, glbs) == ([(60, 30), (40, 30)], [b"glTFcodex", b"glTFclaude"])


@pytest.mark.parametrize("path", ["/ab/house-a/A/p/../pipeline.toml", "/ab/house-a/C/p/pipeline.toml",
                                  "/ab/barn-b/A/p/pipeline.toml", "/ab/house-a/A/x/pipeline.toml", "/ab/mapping.json",
                                  "/ab/house-a/A/p//etc/passwd"])
def test_the_pair_server_reads_only_files_under_the_root_of_a_known_label(server, path):
    assert get(server + path)[0] == 404


def test_the_pair_server_serves_only_the_images_and_glb_a_card_links_so_no_text_file_names_the_runtime(server, two):
    done_both(two)
    work = two / f"production-codex/assets/{AID}/assemble/v1/work"
    png(work / "leak.png", (8, 8))
    (two / f"production-codex/assets/{AID}/assemble/v1/final/review/ledger.png").symlink_to(two / "production-codex/ledger.md")
    final = f"/ab/{AID}/A/p/assets/{AID}/assemble/v1/final"
    assert [get(server + p)[0] for p in (
        f"/ab/{AID}/A/p/ledger.md", f"/ab/{AID}/A/p/pipeline.toml", f"{final}/README.md", f"{final}/review/ledger.png",
        f"/ab/{AID}/A/p/assets/{AID}/assemble/v1/work/leak.png", f"{final}/final_lit_vs_concept.png",
        f"{final}/model/{AID}.glb")] == [404, 404, 404, 404, 404, 200, 200]


def test_a_decision_on_one_side_lands_in_that_runtime_folder_only(server, two):
    for rt in ("claude", "codex"):
        png(two / f"production-{rt}/assets/{AID}/blockout/v1/final/game_cam.png", (20, 20))
        patch_st(two, rt, state="waiting_human", versions={"blockout": 1}, offer=1, offer_key="house-a-blockout-v1-1",
                 offer_log=[{"key": "house-a-blockout-v1-1", "step": "blockout", "v": 1, "why": "duyệt",
                             "verdict": "PASS", "at": "2026-11-09 09:00"}])
    sides = json.loads(get(server + "/api/board")[1])["pairs"][0]["sides"]
    assert [s["key"] for s in sides] == ["house-a-blockout-v1-1"] * 2
    before = st_path(two, "codex").read_text(encoding="utf-8")
    code, msg, applied = post(server + "/api/feedback", {"id": f"{AID}~B", "action": "approve", "text": "đạt",
                                                          "step": "blockout", "offer": "house-a-blockout-v1-1",
                                                          "regions": None}, applied=True)
    st = json.loads(st_path(two, "claude").read_text(encoding="utf-8"))
    assert (code, msg, applied) == (
        200, "house-a: đã duyệt blockout v1 → views_front/todo. Tiếp: giao worker → `brief house-a`", True)
    again = post(server + "/api/feedback", {"id": f"{AID}~B", "action": "approve", "text": "đạt", "step": "blockout",
                                            "offer": "house-a-blockout-v1-1", "regions": None}, applied=True)
    assert again[0::2] == (200, False)
    assert (st["approved"], st["offer_log"][0]["decision"]) == ({"blockout": 1}, "approve")
    assert st_path(two, "codex").read_text(encoding="utf-8") == before
    assert (two / "production-claude/ledger.md").read_text(encoding="utf-8").splitlines()[-1].endswith(
        " · claude · house-a · người dùng approve blockout · đạt")


def test_a_refused_decision_comes_back_without_the_runtime_folder_name(server, two):
    code, msg = post(server + "/api/feedback", {"id": f"{AID}~A", "action": "redo", "text": "x", "step": "assemble"})
    assert (code, HIDDEN.findall(msg), msg.startswith("Lỗi: house-a: không làm lại assemble được")) == (400, [], True)


def test_the_better_version_button_appends_a_preference_and_the_page_shows_it(server, two):
    assert post(server + "/api/prefer", {"asset": AID, "choice": "B"}) == (200, "Đã ghi: house-a · bản B tốt hơn")
    assert post(server + "/api/prefer", {"asset": AID, "choice": "C"}) == (400, "Lỗi: lựa chọn phải là A | B | tie")
    rows = [json.loads(l) for l in (two / "ab/preferences.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["asset"], r["choice"], r["by"]) for r in rows] == [(AID, "B", "board")]
    assert json.loads(get(server + "/api/board")[1])["pairs"][0]["prefer"] == "B"


def report(**w):
    return "WINNER: " + "; ".join(f"{c}={w.get(c, 'tie')}" for c in ab.CRITERIA) + "\nEVIDENCE_OPENED: X/lit_34_front.png\n"


def judge(two):
    code, out = cli(two, None, "ab", "judge")
    assert code == 0, out
    return out


def test_the_pairwise_reviewer_is_asked_twice_with_x_and_y_swapped_and_sees_no_runtime_d26_1(two):
    done_both(two)
    d1 = json.loads(judge(two))
    brief = (two / d1["brief"]).read_text(encoding="utf-8")
    x1 = Image.open(two / "ab/judge/house-a/o1/X/final_lit_vs_concept.png").size
    assert (d1["agent"], d1["model"], d1["report"]) == ("zps-3dp-check-ab", "opus", "ab/judge/house-a/o1/report.md")
    assert HIDDEN.findall(brief) == [] and "WINNER: concept=X|Y|tie; geometry=X|Y|tie;" in brief
    (two / d1["report"]).write_text(report(concept="X", geometry="X", texture="Y"), encoding="utf-8")
    d2 = json.loads(judge(two))
    x2 = Image.open(two / "ab/judge/house-a/o2/X/final_lit_vs_concept.png").size
    assert (d2["report"], x1, x2) == ("ab/judge/house-a/o2/report.md", (60, 30), (40, 30))
    (two / d2["report"]).write_text(f"--- report ---\n{report(concept='Y', geometry='X', texture='X')}--- end ---\n",
                                    encoding="utf-8")
    assert judge(two) == "OK: đủ so cặp (1 asset × 2 lần)\n"
    assert ab.pair_result(AID) == {"concept": "A", "geometry": "tie", "texture": "B", "coherence": "tie", "game_read": "tie"}


def test_the_judge_writes_its_report_file_and_a_reply_the_producer_saved_is_logged_as_a_fallback_d27_5(two):
    done_both(two)
    d1 = json.loads(judge(two))
    rows = (two / d1["brief"]).read_text(encoding="utf-8").splitlines()
    assert [r for r in rows if "report" in r.lower() or "DONE" in r] == [
        "Ghi vào `ab/judge/house-a/o1/report.md`, đúng hai dòng:", "Chỉ trả về dòng `DONE`.",
        "Lệnh ghi file bị chặn: trả cả report giữa dòng `--- report ---` và dòng `--- end ---`."]
    (two / d1["report"]).write_text(f"--- report ---\n{report(concept='X', geometry='X', texture='Y')}--- end ---\n",
                                    encoding="utf-8")
    assert cli(two, "claude", "ab", "judge", "--fallback")[0] == 0
    assert json.loads((two / "ab/judge/house-a/o1/result.json").read_text(encoding="utf-8"))["fallback"] is True
    ledger = (two / "production-claude/ledger.md").read_text(encoding="utf-8").splitlines()
    assert [l.split(" · ", 2)[2] for l in ledger if "report_fallback" in l] == ["house-a · ab o1 · report_fallback · reviewer"]


def test_a_judge_report_without_every_criterion_is_refused_and_asked_again(two):
    done_both(two)
    d1 = json.loads(judge(two))
    (two / d1["report"]).write_text("WINNER: concept=X; geometry=Z\nEVIDENCE_OPENED: X/a.png\n", encoding="utf-8")
    code, out = cli(two, None, "ab", "judge")
    assert (code, out.strip()) == (1, "LỖI: ab/judge/house-a/o1/report.md sai contract: thiếu texture; thiếu coherence; "
                                      "thiếu game_read; geometry=Z phải là X|Y|tie")


def test_the_judge_waits_until_both_runtimes_finished_the_asset(two):
    assert judge(two) == "OK: đủ so cặp (0 asset × 2 lần); chưa DUYỆT 2 ở cả hai bên: house-a\n"


@pytest.mark.parametrize("outcomes, expected", [
    (["claude"] * 6 + ["codex"] * 2 + ["tie"] * 2, (1066, 934)),
    (["tie"] * 5, (1000, 1000)),
    (["codex"] * 5, (792, 1208)),
])
def test_elo_over_the_pilot_batch_counts_a_tie_as_half_and_stays_finite_when_one_side_wins_all(outcomes, expected):
    assert ab.elo(outcomes, "claude", "codex") == expected


def stats(two):
    """claude: v2 of blockout was a fix round; DUYỆT 1 offered and answered redo after a reviewer PASS (a disagreement);
    DUYỆT 2 approved at once; 10 Meshy credits; one dispatch reported 48210 tokens. codex: DUYỆT 1 offered, never
    answered (silence); no token numbers."""
    done_both(two)
    log = [{"key": "model-v1-1", "step": "model", "v": 1, "why": "duyệt", "verdict": "PASS", "decision": "redo"},
           {"key": "assemble-v1-2", "step": "assemble", "v": 1, "why": "duyệt", "verdict": None, "decision": "approve"}]
    patch_st(two, "claude", offer_log=log,
             dispatches=[{"step": "blockout", "v": 1, "role": "worker", "model": "opus", "at": "2026-11-09 08:10",
                          "tokens": 48210},
                         {"step": "blockout", "v": 2, "role": "worker", "model": "opus", "at": "2026-11-09 08:40"}])
    patch_st(two, "codex", offer_log=[{"key": "model-v1-1", "step": "model", "v": 1, "why": "hết 3 vòng sửa",
                                       "verdict": "FIX"}],
             dispatches=[{"step": "blockout", "v": 1, "role": "worker", "model": None, "at": "2026-11-09 08:20"}])
    b = two / f"production-claude/assets/{AID}/texture/budget-abc.json"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"max_credits": 10, "used_credits": 10}), encoding="utf-8")
    g = two / f"production-codex/assets/{AID}/blockout/v1/final/review/gates/base.json"
    g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text(json.dumps({"overall": "fail"}), encoding="utf-8")


def compare(two, reveal=False):
    code, out = cli(two, None, "compare", *(["--reveal"] if reveal else []))
    assert code == 0, out
    return out


def test_compare_counts_per_asset_records_rejected_rounds_and_never_reads_silence_as_approval_d25_j(two):
    stats(two)
    out = compare(two)
    assert HIDDEN.findall(out) == []
    rows = [l for l in out.splitlines() if l.startswith(("| A |", "| B |"))]
    assert rows == [
        "| A | 1 (blockout 1) | chưa quyết | - | hết 3 vòng sửa 1 | 0 | 270 | 0 | không có số | 0/1 |",
        "| B | 1 (blockout 1) | không | có | duyệt 2 | 1 | 270 | 10 | 48210 (thiếu 1 lần) | 0/0 |"]
    assert "- Anh chọn: chưa chọn" in out and "- Reviewer so cặp: chưa so (`ab judge`)" in out


def test_reveal_waits_until_every_asset_is_decided_on_both_sides_and_picked(two):
    stats(two)
    code, out = cli(two, None, "compare", "--reveal")
    assert (code, out.strip()) == (1, "LỖI: chưa mở nhãn: house-a chưa DUYỆT 2 ở cả hai bên hoặc chưa chọn bản tốt hơn")
    patch_st(two, "codex", state="waiting_human")
    ab.prefer(AID, "A")
    code, out = cli(two, None, "compare", "--reveal")
    assert code == 1


def test_reveal_names_the_runtimes_with_totals_elo_and_agreement_with_the_user(two):
    stats(two)
    ab.prefer(AID, "A")
    for k, w in ((1, {"concept": "X", "geometry": "X", "texture": "X"}), (2, {"concept": "Y", "geometry": "Y"})):
        d = two / f"ab/judge/{AID}/o{k}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.md").write_text(report(**w), encoding="utf-8")
        ab.take(d, k)
    out = compare(two, reveal=True)
    assert [l for l in out.splitlines() if l.startswith(("| codex |", "| claude |"))] == [
        "| codex | 1 (blockout 1) | chưa quyết | - | hết 3 vòng sửa 1 | 0 | 270 | 0 | không có số | 0/1 |",
        "| claude | 1 (blockout 1) | không | có | duyệt 2 | 1 | 270 | 10 | opus 48210 (thiếu 1 lần) | 0/0 |"]
    assert "- Reviewer so cặp (hai lần, đổi thứ tự): codex · concept=codex, geometry=codex, texture=ngang nhau, " \
           "coherence=ngang nhau, game_read=ngang nhau" in out
    assert "- Elo reviewer so cặp: claude 940, codex 1060 (0 thắng, 2 thua, 3 hòa trên 5 tiêu chí)" in out
    assert "Reviewer so cặp trùng lựa chọn của anh: 1/1 asset" in out
    assert "- Duyệt ngay lần đầu: DUYỆT 1 0/1 asset, DUYỆT 2 1/1 asset" in out
    assert "- Token theo model: không có số" in out and "- Token theo model: opus 48210 (thiếu 1 lần)" in out
