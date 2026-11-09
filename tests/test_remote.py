import json
from argparse import Namespace

import pytest
from PIL import Image

from core import findings, loop, policy, remote
from core.state import ROOT, ProducerError, load_st, save_st, vdir
from test_board import AID, project  # noqa: F401

URL = "https://claude.ai/artifact/abc"
PUSH = "p20261109T103000"
KEY = "blockout-v2-1"
FINAL = "production/assets/house-a/blockout/v2/final"
INBOX = "production/board/inbox/feedback"


@pytest.fixture
def remote_on(project, monkeypatch):
    (ROOT / "policy.yaml").write_text("review_board: local+remote\n", encoding="utf-8")
    Image.new("RGB", (200, 100), "white").save(vdir(AID, "blockout", 2) / "final/review/game_cam.png")
    monkeypatch.setattr(remote, "stamp", lambda: PUSH)
    return project


def prepare(capsys, **kw):
    remote.prepare(Namespace(**({"url": None, "redo": False} | kw)))
    out = capsys.readouterr().out
    return json.loads(out) if out.startswith("{") else out


def test_prepare_needs_local_plus_remote_in_policy(project, capsys):
    with pytest.raises(ProducerError) as ex:
        prepare(capsys)
    assert str(ex.value) == ("board prepare: policy.yaml có review_board: local; trang claude.ai chỉ dùng khi "
                             "review_board: local+remote (review-board.md §1)")


def test_policy_refuses_an_unknown_review_board(project):
    (ROOT / "policy.yaml").write_text("review_board: remote\n", encoding="utf-8")
    with pytest.raises(ProducerError) as ex:
        policy.load()
    assert str(ex.value) == "production/policy.yaml: review_board: phải là local|local+remote"


def test_prepare_without_a_page_url_names_the_page_to_publish_first_and_packs_nothing(remote_on, capsys):
    out = prepare(capsys)
    assert (out["url"], out["then"], (ROOT / "board/push").exists()) == (
        None, "publish trang, rồi `board prepare --url <url>`", False)


def test_prepare_lists_the_files_to_upload_and_the_rows_to_write_so_the_producer_never_opens_an_image(remote_on, capsys):
    out = prepare(capsys, url=URL)
    d = f"production/board/push/{PUSH}"
    assert {k: out[k] for k in ("url", "push", "upload", "upload_one", "writes", "files_doc")} == {
        "url": URL, "push": PUSH,
        "upload": [f"{FINAL}/review/game_cam.png", "concepts/_approved/house-a/concept_albedo.png", f"{FINAL}/review/lineup.png"],
        "upload_one": [f"{d}/house-a_glb.json"],
        "writes": [{"op": "set", "collection": "offers", "doc_id": f"{PUSH}~house-a", "file_path": f"{d}/offers/{PUSH}~house-a.json"},
                   {"op": "set", "collection": "pushes", "doc_id": PUSH, "file_path": f"{d}/pushes/{PUSH}.json"}],
        "files_doc": {"op": "set", "collection": "files", "doc_id": PUSH,
                      "data": "{<đường dẫn trong upload và upload_one>: <id asset trong kết quả tải lên>}"}}
    assert (out["page"]["file_path"].endswith("scripts/board/remote.html"), list(out["page"]["files"]),
            out["page"]["capabilities"]) == (True, ["board.js"], {
                "db": {"rules": [{"path": "", "read": "view", "write": "owner"}]}, "assets": {}})
    row = json.loads((remote_on / d / f"offers/{PUSH}~house-a.json").read_text(encoding="utf-8"))
    assert {k: row[k] for k in ("id", "key", "sheet", "glb", "glb_json", "header")} == {
        "id": AID, "key": KEY, "sheet": f"{FINAL}/review/game_cam.png", "glb": f"{d}/house-a_glb.json", "glb_json": True,
        "header": "House A · blockout v2 · chờ anh duyệt"}
    assert [i["u"] for i in row["images"]] == out["upload"]
    assert json.loads((remote_on / d / "house-a_glb.json").read_text(encoding="utf-8")) == {
        "name": "assembled.glb", "base64": "Z2xURg=="}
    push = json.loads((remote_on / d / f"pushes/{PUSH}.json").read_text(encoding="utf-8"))
    assert push == {"at": push["at"], "project": "Pilot", "open": {AID: f"{PUSH}~house-a"}}


def test_a_second_prepare_with_nothing_new_writes_nothing(remote_on, capsys):
    prepare(capsys, url=URL)
    assert prepare(capsys) == "board prepare: không có gì mới (1 asset chờ duyệt đã đẩy)\n"


def test_a_new_offer_gets_a_new_row_and_the_push_lists_every_open_offer(remote_on, capsys, monkeypatch):
    prepare(capsys, url=URL)
    st = load_st(AID)
    st["offer_key"] = "blockout-v2-2"
    save_st(st)
    monkeypatch.setattr(remote, "stamp", lambda: "p20261109T110000")
    out = prepare(capsys)
    assert ([w["doc_id"] for w in out["writes"]], out["url"]) == (["p20261109T110000~house-a", "p20261109T110000"], URL)


def test_a_glb_over_15_mb_is_not_packed_and_the_output_says_so(remote_on, capsys):
    (ROOT / "assets/house-a/blockout/v2/final/assembled.glb").write_bytes(b"g" * (15 * 2**20 + 1))
    out = prepare(capsys, url=URL)
    assert (out["upload_one"], out["skipped"]) == ([], ["assembled.glb: GLB lớn hơn 15 MB"])


def inbox(root, doc, body):
    p = root / INBOX / f"{doc}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(body), encoding="utf-8")


def pull(capsys):
    remote.pull(Namespace(dir="production/board/inbox"))
    return capsys.readouterr().out.splitlines()


def row(**kw):
    return {"aid": AID, "key": KEY, "action": "note", "text": "", "step": "blockout", "regions": None,
            "at": "2026-11-09T10:00:00Z"} | kw


def test_pull_applies_each_new_row_once_in_time_order(remote_on, capsys):
    inbox(remote_on, "b", row(action="redo", text="mái thấp", at="2026-11-09T10:05:00Z"))
    inbox(remote_on, "a", {"id": "a", "version": 1, "data": row(text="xem cửa")})
    lines = pull(capsys)
    assert lines == ["a: house-a: đã ghi feedback. Tiếp: chờ người dùng: hết 3 vòng sửa; còn mở: F1, F4 (review page)",
                     "b: house-a: làm lại blockout từ v2. Tiếp: giao worker → `brief house-a`",
                     "board pull: 2 dòng mới"]
    assert pull(capsys) == ["board pull: 0 dòng mới"]


def test_a_remote_approve_after_a_local_approve_of_the_same_offer_is_skipped_d22_8(remote_on, capsys):
    loop.human_action(AID, "approve", "ok", None, offer=KEY)
    at = load_st(AID)["decisions"]["blockout v2"]["at"]
    inbox(remote_on, "c", row(action="approve"))
    assert pull(capsys)[0] == f"c: house-a: bỏ qua approve blockout v2: đã có quyết định lúc {at}"


def test_remote_regions_are_drawn_from_the_local_original_and_become_h_findings(remote_on, capsys):
    mark = {"n": 1, "image": "review/game_cam.png", "shape": "circle", "coords": [0.1, 0.1, 0.5, 0.9], "note": "cửa lệch"}
    inbox(remote_on, "d", row(action="redo", regions=[mark]))
    assert pull(capsys)[0].startswith("d: house-a: làm lại blockout từ v2; khoanh 1 vùng → H1.")
    h1 = findings.load(AID, "blockout", 2)["findings"]["H1"]
    assert (h1["repair"], (remote_on / h1["mark"]["png"]).is_file()) == ("cửa lệch", True)


@pytest.mark.parametrize("body, err", [
    (row(action="rm"), "e: LỖI: action phải là approve | redo | note | paint"),
    (row(aid="../x"), "e: LỖI: dòng sai dạng: aid"),
    (row(text=5), "e: LỖI: dòng sai dạng: text"),
    (row(key=["x"]), "e: LỖI: dòng sai dạng: key"),
    (row(aid="ghost"), "e: LỖI: không có asset 'ghost'"),
    ([1, 2], "e: LỖI: dòng sai dạng: không phải object"),
])
def test_a_bad_row_is_reported_in_one_line_and_never_retried(remote_on, capsys, body, err):
    inbox(remote_on, "e", body)
    assert pull(capsys) == [err, "board pull: 1 dòng mới"]
    assert pull(capsys) == ["board pull: 0 dòng mới"]
