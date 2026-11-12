import http.client
import json
import shutil
import subprocess
import threading
from argparse import Namespace

import pytest

from core import board, findings, intake, loop
from core.state import ROOT, load_cfg, load_st, locked, save_st, vdir
from shared import P

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
    st |= {"state": "waiting_human", "versions": {"blockout": 2}, "offer": 2, "offer_key": "blockout-v2-1",
           "label": loop.NOT_PASSED, "note": "hết 3 vòng sửa; còn mở: F1, F4", "concept_dir": str(concept)}
    save_st(st)
    return tmp_path


def view():
    cfg = load_cfg()
    return board.asset_view(cfg, load_st(AID))


def test_concept_sits_next_to_the_hero_and_newest_evidence_replaces_the_same_render_so_the_user_compares_at_once(project):
    v2 = project / "production/assets" / AID / "blockout/v2"
    for k in (1, 2):
        (v2 / f"review/evidence-{k}").mkdir(parents=True)
        (v2 / f"review/evidence-{k}/lineup.png").write_bytes(PNG)
    drafts = project / "concepts/_approved" / AID / "review"
    drafts.mkdir()
    (drafts / "v01.png").write_bytes(PNG)
    assert [i["u"] for i in view()["images"]] == [
        "/p/assets/house-a/blockout/v2/final/review/game_cam.png",
        "/a/house-a/concept_albedo.png",
        "/p/assets/house-a/blockout/v2/review/evidence-2/lineup.png"]


def test_the_blockout_card_shows_the_material_side_views_right_after_hero_and_concept_so_the_sides_are_approved_there(project):
    """D44.1: the owner approves the layout of the hidden sides at the blockout gate, so the mat_* renders come before the
    other renders, in the order left, right, back, top."""
    review = project / "production/assets" / AID / "blockout/v2/final/review"
    for name in ("mat_top.png", "mat_back.png", "mat_right.png", "mat_left.png", "foot_front_left.png"):
        (review / name).write_bytes(PNG)
    assert [i["n"] for i in view()["images"]] == [
        "review/game_cam.png", "concept/concept_albedo.png", "review/mat_left.png", "review/mat_right.png",
        "review/mat_back.png", "review/mat_top.png", "review/foot_front_left.png", "review/lineup.png"]


def test_a_blockout_without_material_side_views_keeps_its_old_card(project):
    assert [i["n"] for i in view()["images"]] == [
        "review/game_cam.png", "concept/concept_albedo.png", "review/lineup.png"]


def test_payload_of_a_not_passed_version_puts_images_first_and_findings_one_per_line(project):
    v = view()
    assert v == {
        "id": AID, "step": "blockout", "version": 2, "waiting": True,
        "header": "House A · blockout v2 · chờ anh duyệt",
        "sheet": "/p/assets/house-a/blockout/v2/final/review/game_cam.png",
        "images": [
            {"u": "/p/assets/house-a/blockout/v2/final/review/game_cam.png", "n": "review/game_cam.png"},
            {"u": "/a/house-a/concept_albedo.png", "n": "concept/concept_albedo.png"},
            {"u": "/p/assets/house-a/blockout/v2/final/review/lineup.png", "n": "review/lineup.png"}],
        "glb": "/p/assets/house-a/blockout/v2/final/assembled.glb",
        "summary": ["Blockout house-a v2", "4 trụ, 1 cửa, 3 thùng", "Mái chìa 0.25 m"],
        "more": ["Đo", "param roof_overhang = 0.25"],
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
        "redo_steps": [], "key": "blockout-v2-1", "ask": None, "report": None, "purge": None,
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
    st |= {"stage": "views", "versions": {"views": 1}, "offer": 1, "label": "",
           "stale": {"views v1": "blockout v1"}}
    save_st(st)
    v = view()
    assert (v["step"], v["version"], v["stale"], v["label"]) == ("views", 1, "dựng từ blockout v1 — cũ", "")


def views_version(step, files, note, label=""):
    final = vdir(AID, step, 1) / "final"
    for name in files:
        (final / name).parent.mkdir(parents=True, exist_ok=True)
        (final / name).write_bytes(PNG)
    (final / "report/VIEWS.md").write_text("# Views house-a v1\nfront: bóng đổ còn dưới mái\nđã gen 3 lần\n\nchi tiết\n",
                                           encoding="utf-8")
    st = load_st(AID)
    st |= {"stage": step, "versions": {"blockout": 2, step: 1}, "offer": 1, "label": label, "note": note}
    save_st(st)
    return view()


def test_the_views_card_puts_the_set_sheet_first_the_views_md_summary_and_why_because_the_user_approves_the_set(
        project):
    v = views_version("views", ("back.png", "front.png", "report/VIEWS_sheet.png", "report/overlay_back.png"),
                      "hết 3 vòng sửa; còn mở: F1", loop.NOT_PASSED)
    assert (v["sheet"], [i["n"] for i in v["images"]][:3], v["summary"], v["reason"], v["label"]) == (
        "/p/assets/house-a/views/v1/final/report/VIEWS_sheet.png",
        ["report/VIEWS_sheet.png", "concept/concept_albedo.png", "back.png"],
        ["Views house-a v1", "front: bóng đổ còn dưới mái", "đã gen 3 lần"], "hết 3 vòng sửa; còn mở: F1", "chưa đạt")


def test_duyet_1_shows_the_model_sheet_first_and_the_untextured_glb_not_the_blockout_union(project):
    final = vdir(AID, "model", 1) / "final"
    for name in ("assembled.glb", "house-a-untextured.glb", "review/renders/clay_front.png", "review/model_sheet.png"):
        (final / name).parent.mkdir(parents=True, exist_ok=True)
        (final / name).write_bytes(PNG)
    (final / "model.md").write_text("# Model house-a v1\nThêm diềm mái: 6 px ở game cam\n1200 → 2400 tris / trần 3000\n\n"
                                    "## Detail pass\n", encoding="utf-8")
    st = load_st(AID)
    st |= {"stage": "model", "versions": {"blockout": 2, "model": 1}, "offer": 1, "label": "", "note": "duyệt model v1"}
    save_st(st)
    v = view()
    assert (v["sheet"], [i["n"] for i in v["images"]], v["glb"], v["summary"]) == (
        "/p/assets/house-a/model/v1/final/review/model_sheet.png",
        ["review/model_sheet.png", "concept/concept_albedo.png", "review/renders/clay_front.png"],
        "/p/assets/house-a/model/v1/final/house-a-untextured.glb",
        ["Model house-a v1", "Thêm diềm mái: 6 px ở game cam", "1200 → 2400 tris / trần 3000"])


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
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
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
    again = post(server, {"id": AID, "action": "approve", "text": "", "step": "blockout"})
    assert again[0] == 200
    assert again[1] == f"house-a: bỏ qua approve blockout v2: đã có quyết định lúc {st['decisions']['blockout v2']['at']}"


def test_a_corrupt_status_file_drops_out_of_the_board_instead_of_breaking_it(server):
    (ROOT / "assets/bad").mkdir()
    (ROOT / "assets/bad/status.json").write_text("{x", encoding="utf-8")
    status, body = get(server, "/api/board")
    assert (status, [a["id"] for a in json.loads(body)["assets"]]) == (200, [AID])


@pytest.mark.parametrize("body, headers", [
    (json.dumps([1]), {}),
    ("{}", {"Content-Length": "abc"}),
])
def test_a_malformed_post_gets_400_and_the_connection_stays_answered(server, body, headers):
    c = http.client.HTTPConnection(*server.server_address)
    c.putrequest("POST", "/api/feedback")
    for k, v in ({"Content-Type": "application/json", "Content-Length": str(len(body))} | headers).items():
        c.putheader(k, v)
    c.endheaders(body.encode())
    r = c.getresponse()
    assert (r.status, json.loads(r.read())["message"].startswith("Lỗi: ")) == (400, True)


def test_a_board_click_waits_for_the_lock_so_it_never_interleaves_with_a_running_p_command(server):
    got = []
    t = threading.Thread(target=lambda: got.append(post(server, {"id": AID, "action": "note", "text": "n1"})[0]))
    with locked():
        t.start()
        t.join(0.3)
        assert t.is_alive(), "the board wrote while a P command held production/.lock"
    t.join(5)
    assert got == [200]


def test_dashboard_lists_done_enabled_as_finished_like_every_other_command():
    sts = [{"id": "a", "state": "done_enabled", "stage": "blockout"}, {"id": "b", "state": "done", "stage": "assemble"}]
    out = board.render_dashboard(sts).splitlines()
    assert (out[2:4], out[-1]) == (["| Asset | Bước | State | Phiên bản | Rubric gần nhất | Deadline | Việc tiếp "
                                    "| Thời gian đã dùng | Token đã dùng |", "|---|---|---|---|---|---|---|---|---|"],
                                   "Done (2): a, b")
    assert len(out) == 6


def test_a_cross_site_form_post_cannot_decide(server):
    code, _ = post_raw(server, {"id": AID, "action": "approve", "text": ""}, ctype="text/plain")
    assert code == 403 and load_st(AID)["state"] == "waiting_human"


def test_texture_sent_to_the_user_shows_the_lit_render_beside_the_concept_first_and_the_notes_summary_d20_16(project):
    final = vdir(AID, "texture", 2) / "final"
    for name in ("final_lit_vs_concept.png", "albedo_2048.png", "review/lit_34_front.png"):
        (final / name).parent.mkdir(parents=True, exist_ok=True)
        (final / name).write_bytes(PNG)
    (final / "notes.md").write_text("# Texture house-a v2\nMeshy 1 lần, 10 credit\nSửa 2 vùng mái\nchưa kiểm: engine\n",
                                    encoding="utf-8")
    st = load_st(AID)
    st |= {"stage": "texture", "versions": {"blockout": 2, "texture": 2}, "offer": 2, "label": loop.NOT_PASSED,
           "note": "UNFIXABLE: lớp Meshy sai style: gọi Meshy thêm một lần (10 credit) hay VẼ MỚI?"}
    save_st(st)
    v = view()
    assert (v["sheet"], v["images"][0]["n"], v["summary"], v["reason"], v["redo_steps"]) == (
        "/p/assets/house-a/texture/v2/final/final_lit_vs_concept.png", "final_lit_vs_concept.png",
        ["Texture house-a v2", "Meshy 1 lần, 10 credit", "Sửa 2 vùng mái"],
        "UNFIXABLE: lớp Meshy sai style: gọi Meshy thêm một lần (10 credit) hay VẼ MỚI?", [])


def test_duyet_2_offers_needs_fix_at_texture_or_model_and_shows_the_final_glb_d21_6(project):
    final = vdir(AID, "assemble", 1) / "final"
    for name in ("model/house-a.glb", "review/final_lit_vs_concept.png", "review/compare_34_front.png"):
        (final / name).parent.mkdir(parents=True, exist_ok=True)
        (final / name).write_bytes(PNG)
    (final / "README.md").write_text("Trạng thái: chờ DUYỆT 2 · 2026-11-09\n", encoding="utf-8")
    st = load_st(AID)
    st |= {"stage": "assemble", "versions": {"blockout": 2, "assemble": 1}, "offer": 1, "label": "", "note": "duyệt"}
    save_st(st)
    v = view()
    assert (v["sheet"], v["glb"], v["redo_steps"], v["summary"]) == (
        "/p/assets/house-a/assemble/v1/final/review/final_lit_vs_concept.png",
        "/p/assets/house-a/assemble/v1/final/model/house-a.glb", ["texture", "model"],
        ["Trạng thái: chờ DUYỆT 2 · 2026-11-09"])


def test_dashboard_shows_time_and_tokens_used_so_far_from_stored_numbers_only_x7():
    """D41: no transcript is read here. A dispatch that was never ingested has no time; one ingested without tokens
    says so instead of showing zero."""
    done = {"at": "2026-11-10 09:00:00", "ingested": "2026-11-10 09:10:00", "duration_ms": 590000, "tokens": 50000}
    nothing = {"at": "2026-11-10 09:11:00", "ingested": "2026-11-10 09:12:00", "tokens": None}
    sts = [{"id": "a", "state": "fix", "stage": "blockout", "dispatches": [
               {"step": "blockout", "v": 1, "role": "worker"} | done, {"step": "blockout", "v": 1, "role": "reviewer"} | nothing],
            "producer_usage": {"model": {"tokens": 400, "from": "x", "to": "y", "dup": 0}}},
           {"id": "b", "state": "todo", "stage": "blockout"},
           {"id": "c", "state": "fix", "stage": "blockout", "dispatches": [
               {"step": "blockout", "v": 1, "role": "worker", "at": "2026-11-10 09:00:00"}]}]
    rows = [l.split(" | ")[-2:] for l in board.render_dashboard(sts).splitlines()[4:7]]
    assert rows == [["10m50s", "50400 (+1 không có số) |"], ["—", "— |"], ["không có số", "không có số |"]]


def test_a_done_asset_card_links_its_run_report_and_the_board_serves_it_x9(project):
    st = load_st(AID)
    save_st(st | {"state": "done", "stage": "assemble"})
    assert view()["report"] is None
    (project / "deliver" / AID).mkdir(parents=True)
    (project / "deliver" / AID / "RUN-REPORT.md").write_text("# RUN-REPORT\n", encoding="utf-8")
    assert board.asset_view(load_cfg(), load_st(AID), "assemble", 1)["report"] == f"/d/{AID}/RUN-REPORT.md"
    assert board.safe_file(load_cfg(), f"/d/{AID}/RUN-REPORT.md").name == "RUN-REPORT.md"
    assert board.safe_file(load_cfg(), "/d/../production/pipeline.toml") is None
    assert board.asset_view(load_cfg(), load_st(AID), "blockout", 2)["report"] is None


BUTTONS_JS = r"""
const vm = require("vm"), fs = require("fs");
const [js, payload] = [fs.readFileSync(process.argv[2], "utf8"), JSON.parse(fs.readFileSync(process.argv[3], "utf8"))];
const el = tag => ({ tag, children: [], style: {}, classList: { add() {}, remove() {}, toggle() {} },
  append(...k) { this.children.push(...k); }, replaceChildren(...k) { this.children = k; },
  addEventListener() {}, setAttribute() {} });
const app = el("div");
const document = { createElement: el, createElementNS: (_, t) => el(t), head: el("head"), body: el("body"),
                   getElementById: id => (id === "app" ? app : null), addEventListener() {} };
const ctx = { document, window: { BOARD: { mode: "none" } }, addEventListener() {}, console };
vm.runInNewContext(js, ctx);
const walk = n => (n && typeof n === "object" ? [...(n.tag === "button" ? [n.textContent] : []), ...n.children.flatMap(walk)] : []);
ctx.window.Board.start({ load: async () => payload, send: async () => ({}) }).then(() => console.log(JSON.stringify(walk(app))));
"""


def board_buttons(tmp_path, payload) -> list[str]:
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node không có trên máy: không chạy được board.js")
    js, data = tmp_path / "buttons.js", tmp_path / "payload.json"
    js.write_text(BUTTONS_JS, encoding="utf-8")
    data.write_text(json.dumps(payload), encoding="utf-8")
    r = subprocess.run([node, str(js), str(board.BOARD_DIR / "board.js"), str(data)], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_board_hides_approve_for_a_version_no_reviewer_passed_d36_2_c1(project):
    """A stalled review reaches the user labelled "chưa chấm": the page offers only Cần sửa and Ghi chú, so a click never
    sends an approval the script must refuse."""
    st = load_st(AID)
    st |= {"label": loop.UNREVIEWED, "stalled_from": "reviewing"}
    save_st(st)
    unreviewed = {"project": "Pilot", "assets": [view()]}
    st["label"] = loop.NOT_PASSED
    save_st(st)
    assert board_buttons(project, {"project": "Pilot", "assets": [view()]}) == ["Model 3D", "Duyệt", "Cần sửa", "Ghi chú"]
    assert board_buttons(project, unreviewed) == ["Model 3D", "Cần sửa", "Ghi chú"]


LINE = "Sẽ xóa 21 file, 24.4 KB; sau lệnh này không `redo` được."
DOM = """
const fs = require("fs"), vm = require("vm");
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.className = ""; this.textContent = ""; }
  append(...k) { this.children.push(...k.map(x => typeof x === "string" ? Object.assign(new El("#text"), { textContent: x }) : x)); }
  replaceChildren(...k) { this.children = []; this.append(...k); }
  addEventListener() {} setAttribute() {} remove() {} getBoundingClientRect() { return { left: 0, top: 0, width: 1, height: 1 }; }
  all() { return [this, ...this.children.flatMap(c => c.all())]; }
}
const ids = {};
global.document = { createElement: t => new El(t), createElementNS: (n, t) => new El(t), head: new El("head"),
                    body: new El("body"), getElementById: id => ids[id] ||= new El("div"), addEventListener() {} };
global.window = { BOARD: { mode: "none" }, addEventListener() {} };
global.addEventListener = () => {};
global.fetch = async () => { throw new Error("no network"); };
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));
const payload = JSON.parse(fs.readFileSync(0, "utf8")), sent = [];
const find = (tag, text) => ids.app.all().filter(e => e.tag === tag && (text === undefined || e.textContent === text));
(async () => {
  await window.Board.start({ load: async () => payload, send: async body => { sent.push(body); return { ok: true, applied: true, message: "ok" }; } });
  const out = { warn: find("p").filter(e => e.className === "warn").map(e => e.textContent),
                buttons: find("button").map(e => e.textContent), links: find("a").map(e => [e.textContent, e.href]) };
  const approve = () => find("button").find(e => e.className === "ok");
  approve()?.onclick();
  out.after_first = { sent: sent.length, buttons: find("button").map(e => e.textContent) };
  approve()?.onclick();
  out.after_second = sent.map(b => [b.action, b.id, b.offer]);
  console.log(JSON.stringify(out));
})();
"""


def page_card(**over):
    card = {"id": AID, "step": "assemble", "version": 1, "waiting": True, "header": "House A · assemble v1", "sheet": None,
            "images": [], "glb": None, "summary": [], "more": [], "reason": "", "label": "", "stale": None, "decided": None,
            "open": [], "preference": [], "redo_steps": [], "key": "assemble-v1-1", "ask": None, "report": None,
            "purge": LINE}
    return card | over


def run_board_js(tmp_path, card):
    (tmp_path / "dom.js").write_text(DOM, encoding="utf-8")
    js = P.parent / "board" / "board.js"
    r = subprocess.run(["node", str(tmp_path / "dom.js"), str(js)], input=json.dumps({"project": "Pilot", "assets": [card]}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@needs_node
def test_the_duyet_2_button_shows_the_deletion_line_and_sends_only_on_the_second_click_d40_4(tmp_path):
    """The page cannot undo a delete, so the first click only asks: nothing reaches the Producer until the second."""
    out = run_board_js(tmp_path, page_card())
    assert out["warn"] == [LINE]
    assert out["buttons"] == ["Duyệt", "Cần sửa", "Ghi chú"]
    assert out["after_first"] == {"sent": 0, "buttons": ["Bấm lần nữa để duyệt và xóa", "Cần sửa", "Ghi chú"]}
    assert out["after_second"] == [["approve", AID, "assemble-v1-1"]]


@needs_node
def test_a_card_without_a_deletion_approves_on_the_first_click_d40_4(tmp_path):
    """Intermediate steps, Producer approvals, `purge: off` and `keep` have no line, so no extra click."""
    out = run_board_js(tmp_path, page_card(purge=None))
    assert out["warn"] == []
    assert (out["after_first"]["sent"], out["after_second"]) == (1, [["approve", AID, "assemble-v1-1"]] * 2)


@needs_node
def test_a_version_nobody_reviewed_has_no_approve_button_so_the_page_shows_no_deletion_line(tmp_path):
    """A stalled review offers only Cần sửa and Ghi chú (the script refuses the approval), so no deletion is announced."""
    out = run_board_js(tmp_path, page_card(label="chưa chấm"))
    assert (out["warn"], out["buttons"], out["after_second"]) == ([], ["Cần sửa", "Ghi chú"], [])


@needs_node
def test_a_done_card_links_the_run_report_and_a_card_without_one_has_no_link(tmp_path):
    out = run_board_js(tmp_path, page_card(purge=None, report=f"/d/{AID}/RUN-REPORT.md"))
    assert out["links"] == [["Report thời gian và token", f"/d/{AID}/RUN-REPORT.md"]]
    assert run_board_js(tmp_path, page_card(purge=None))["links"] == []


def test_the_served_script_has_the_report_link_and_the_two_step_confirm_d40_4():
    """Without node the behaviour tests skip; the code that matters must still be in the file the board serves."""
    js = (P.parent / "board" / "board.js").read_text(encoding="utf-8")
    assert 'a.report ? $("p", {}, $("a", { href: a.report, textContent: "Report thời gian và token" }))' in js
    assert "Bấm lần nữa để duyệt và xóa" in js and "a.purge" in js


def test_the_remote_page_gets_the_line_from_the_row_so_it_needs_no_code_of_its_own_d40_4():
    """remote.html spreads each pushed row into the payload that board.js renders, `purge` included."""
    html = (P.parent / "board" / "remote.html").read_text(encoding="utf-8")
    assert "...r," in html and "window.Board.start" in html
