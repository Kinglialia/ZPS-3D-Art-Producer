import http.client
import json
import threading
from argparse import Namespace

import pytest

from core import board, findings, intake, loop
from core.state import ROOT, load_cfg, load_st, save_st, vdir

AID = "house-a"
PNG = b"\x89PNG"
SUMMARY = ["# Blockout house-a v2", "4 trụ, 1 cửa, 3 thùng", "Mái chìa 0.25 m", "## Đo", "param roof_overhang = 0.25"]


def fnd(prio, status, **over):
    base = {"priority": prio, "kind": "param", "status": status, "first_v": 1, "last_v": 2, "region": "mái",
            "evidence": "chìa thiếu 20 cm", "repair": "tăng roof_overhang", "acceptance": "chìa ≥ 0,4 m trên clay_34",
            "viewing_condition": "front ortho", "consequence": "sai silhouette", "confidence": "high",
            "preserve": "chiều cao tường"}
    return base | over


@pytest.fixture
def project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    intake.new(Namespace(id=AID, title="House A", type="asset", priority=2, deadline=None), load_cfg())
    intake.ready(Namespace(ids=[AID]))
    capsys.readouterr()
    final = vdir(AID, "blockout", 2) / "final"
    (final / "review").mkdir(parents=True)
    (final / "blockout.md").write_text("\n".join(SUMMARY[:3] + ["", *SUMMARY[3:]]), encoding="utf-8")
    for name in ("review/lineup.png", "review/game_cam.png"):
        (final / name).write_bytes(PNG)
    (final / "assembled.glb").write_bytes(b"glTF")
    findings.save(AID, "blockout", {"version": 2, "base": None, "top_fix": None, "pick": None, "next_id": 5, "findings": {
        "F1": fnd("major", "open"), "F2": fnd("preference", "open", region="cửa", evidence="cửa hơi hẹp", repair="rộng thêm",
                                              acceptance="cửa ≥ 1 m"),
        "F3": fnd("major", "resolved"), "F4": fnd("minor", "regressed", region="thùng", evidence="thùng lệch",
                                                  repair="xoay 5°", acceptance="thùng thẳng hàng")}})
    (tmp_path / "secret.txt").write_text("k", encoding="utf-8")
    (tmp_path / "concepts/secret.txt").write_text("k", encoding="utf-8")
    concept = tmp_path / "concepts/_approved" / AID
    concept.mkdir(parents=True)
    (concept / "concept_albedo.png").write_bytes(PNG)
    st = load_st(AID)
    st |= {"state": "waiting_human", "versions": {"blockout": 2}, "offer": 2, "label": loop.NOT_PASSED,
           "note": "hết 3 vòng sửa; còn mở: F1, F4", "concept_dir": str(concept)}
    save_st(st)
    return tmp_path


def view():
    cfg = load_cfg()
    return board.asset_view(cfg, load_st(AID))


def test_payload_of_a_not_passed_version_puts_images_first_and_findings_one_per_line(project):
    v = view()
    assert v == {
        "id": AID, "step": "blockout", "version": 2, "waiting": True,
        "header": "House A · blockout v2 · chờ anh duyệt",
        "sheet": "/p/assets/house-a/blockout/v2/final/review/game_cam.png",
        "images": [
            {"u": "/p/assets/house-a/blockout/v2/final/review/game_cam.png", "n": "review/game_cam.png"},
            {"u": "/p/assets/house-a/blockout/v2/final/review/lineup.png", "n": "review/lineup.png"},
            {"u": "/a/house-a/concept_albedo.png", "n": "concept/concept_albedo.png"}],
        "glb": "/p/assets/house-a/blockout/v2/final/assembled.glb",
        "summary": ["# Blockout house-a v2", "4 trụ, 1 cửa, 3 thùng", "Mái chìa 0.25 m"],
        "more": ["## Đo", "param roof_overhang = 0.25"],
        "reason": "hết 3 vòng sửa; còn mở: F1, F4",
        "label": "chưa đạt", "stale": None, "decided": None,
        "open": [
            {"line": "F1 [major] mái — chìa thiếu 20 cm — tăng roof_overhang — acceptance: chìa ≥ 0,4 m trên clay_34",
             "fields": {"viewing_condition": "front ortho", "consequence": "sai silhouette", "confidence": "high",
                        "preserve": "chiều cao tường"}},
            {"line": "F4 [minor] thùng — thùng lệch — xoay 5° — acceptance: thùng thẳng hàng",
             "fields": {"viewing_condition": "front ortho", "consequence": "sai silhouette", "confidence": "high",
                        "preserve": "chiều cao tường"}}],
        "preference": [
            {"line": "F2 [preference] cửa — cửa hơi hẹp — rộng thêm — acceptance: cửa ≥ 1 m",
             "fields": {"viewing_condition": "front ortho", "consequence": "sai silhouette", "confidence": "high",
                        "preserve": "chiều cao tường"}}],
    }


def test_resolved_findings_stay_out_of_the_open_list(project):
    assert [f["line"][:2] for f in view()["open"]] == ["F1", "F4"]


def test_a_decided_version_reports_the_time_so_the_page_shows_the_dedupe_state(project):
    st = load_st(AID)
    st["decisions"] = {"blockout v2": {"action": "approve", "at": "2026-11-09 10:00"}}
    save_st(st)
    assert view()["decided"] == "2026-11-09 10:00"


def test_a_version_built_from_old_input_gets_the_stale_label(project):
    st = load_st(AID)
    st |= {"stage": "views_rest", "versions": {"views_rest": 1}, "offer": 1, "label": "",
           "stale": {"views_rest v1": "blockout v1"}}
    save_st(st)
    v = view()
    assert (v["step"], v["version"], v["stale"], v["label"]) == ("views_rest", 1, "dựng từ blockout v1 — cũ", "")


def test_asset_without_a_version_still_has_a_header(project):
    st = load_st(AID)
    st |= {"state": "todo", "versions": {}, "offer": None, "label": ""}
    save_st(st)
    v = view()
    assert (v["header"], v["images"], v["sheet"], v["glb"], v["summary"], v["open"]) == (
        "House A · blockout · todo", [{"u": "/a/house-a/concept_albedo.png", "n": "concept/concept_albedo.png"}],
        None, None, [], [])


def test_board_payload_lists_waiting_assets_first(project, capsys):
    intake.new(Namespace(id="a-first", title="A", type="asset", priority=1, deadline=None), load_cfg())
    capsys.readouterr()
    p = board.board_payload(load_cfg())
    assert (p["project"], [a["id"] for a in p["assets"]]) == ("Pilot", [AID, "a-first"])


@pytest.mark.parametrize("url", ["/p/../secret.txt", "/p/assets/../../secret.txt", "/p/%2e%2e/secret.txt", "/p//etc/passwd", "/p/",
                                 "/a/../secret.txt", "/x/ledger.md", "/p/assets/house-a/blockout/v2/final/review/%00"])
def test_path_guard_rejects_escapes(project, url):
    assert board.safe_file(load_cfg(), url) is None


def test_path_guard_rejects_a_symlink_that_leaves_the_root(project, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("k", encoding="utf-8")
    (ROOT / "link.txt").symlink_to(secret)
    assert board.safe_file(load_cfg(), "/p/link.txt") is None


def test_path_guard_serves_files_under_production_and_approved_only(project):
    cfg = load_cfg()
    got = board.safe_file(cfg, "/p/assets/house-a/blockout/v2/final/review/game_cam.png")
    assert got == (ROOT / "assets/house-a/blockout/v2/final/review/game_cam.png").resolve()
    assert board.safe_file(cfg, "/a/house-a/concept_albedo.png") == (cfg["paths"]["approved"] / AID / "concept_albedo.png").resolve()
    assert board.safe_file(cfg, "/p/assets/house-a/blockout/v2/final") is None


@pytest.fixture
def server(project):
    srv = board.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def get(srv, path, host=None):
    c = http.client.HTTPConnection(*srv.server_address)
    c.request("GET", path, headers={"Host": host} if host else {})
    r = c.getresponse()
    return r.status, r.read()


def test_server_binds_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_server_serves_json_shell_script_and_files_and_refuses_the_rest(server):
    status, body = get(server, "/api/board")
    assert status == 200 and json.loads(body)["assets"][0]["id"] == AID
    assert get(server, "/")[0] == 200 and get(server, "/board.js")[0] == 200
    assert get(server, "/p/assets/house-a/blockout/v2/final/review/game_cam.png") == (200, PNG)
    assert get(server, "/p/../secret.txt")[0] == 404
    assert get(server, "/p/%2e%2e/secret.txt")[0] == 404
    assert get(server, "/api/board", host="evil.example")[0] == 403


def post_raw(srv, body, ctype="application/json"):
    c = http.client.HTTPConnection(*srv.server_address)
    c.request("POST", "/api/feedback", json.dumps(body), {"Content-Type": ctype})
    r = c.getresponse()
    return r.status, r.read()


def post(srv, body):
    code, raw = post_raw(srv, body)
    return code, json.loads(raw)["message"]


def test_second_decision_on_the_same_version_shows_the_dedupe_message(server):
    first = post(server, {"id": AID, "action": "approve", "text": "ok", "step": "blockout"})
    assert first[0] == 200 and first[1].startswith("house-a: đã duyệt blockout v2")
    st = load_st(AID)
    again = post(server, {"id": AID, "action": "redo", "text": "", "step": "blockout"})
    assert again[0] == 200
    assert again[1] == f"house-a: bỏ qua redo blockout v2: đã có quyết định lúc {st['decisions']['blockout v2']['at']}"


def test_a_cross_site_form_post_cannot_decide(server):
    code, _ = post_raw(server, {"id": AID, "action": "approve", "text": ""}, ctype="text/plain")
    assert code == 403 and load_st(AID)["state"] == "waiting_human"
