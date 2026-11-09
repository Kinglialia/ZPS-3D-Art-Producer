import base64
import io
import json
import os
import re
import subprocess
import sys
from argparse import Namespace

import pytest
from PIL import Image

from core import board
from core.state import ROOT, ProducerError, load_st, save_st, vdir
from shared import P
from test_board import AID, project  # noqa: F401

FINAL = "assets/house-a/blockout/v2/final"


def show(capsys, **kw):
    board.show(Namespace(**({"id": AID, "step": None, "version": None, "bundle": False} | kw)))
    return capsys.readouterr().out


def payload(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(re.search(r'<script id="board-data" type="application/json">(.*?)</script>', text, re.S).group(1))


def png(path, size, mode="RGB"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, "white").save(path)


def decoded(uri):
    head, b64 = uri.split(",", 1)
    return head, Image.open(io.BytesIO(base64.b64decode(b64))).size


def test_show_writes_one_static_page_with_relative_image_links_the_embedded_glb_and_the_shared_renderer(project, capsys):
    out = show(capsys)
    page = ROOT / "show/house-a.html"
    assert out == f"OK: production/show/house-a.html ({page.stat().st_size // 1024} KB)\n"
    p = payload(page)
    a = p["assets"][0]
    assert (p["project"], len(p["assets"]), a["sheet"], [i["u"] for i in a["images"]], a["glb"]) == (
        "Pilot", 1, f"../{FINAL}/review/game_cam.png",
        [f"../{FINAL}/review/game_cam.png", "../../concepts/_approved/house-a/concept_albedo.png", f"../{FINAL}/review/lineup.png"],
        "data:model/gltf-binary;base64,Z2xURg==")
    html = page.read_text(encoding="utf-8")
    assert 'window.BOARD = {mode: "static"};' in html
    assert (board.BOARD_DIR / "board.js").read_text(encoding="utf-8") in html


def test_text_in_the_payload_cannot_close_the_data_script(project, capsys):
    st = load_st(AID)
    st["note"] = "</script><script>alert(1)</script>"
    save_st(st)
    show(capsys)
    html = (ROOT / "show/house-a.html").read_text(encoding="utf-8")
    assert ("<script>alert(1)" in html, payload(ROOT / "show/house-a.html")["assets"][0]["reason"]) == (
        False, "</script><script>alert(1)</script>")


def test_show_of_one_step_and_version_names_the_file_after_them_and_refuses_a_missing_version(project, capsys):
    assert show(capsys, step="blockout", version=2).startswith("OK: production/show/house-a-blockout-v2.html")
    with pytest.raises(ProducerError) as ex:
        show(capsys, step="blockout", version=1)
    assert str(ex.value) == "house-a: không có blockout v1"


def test_show_of_an_asset_lists_every_step_that_has_a_version_newest_step_first(project, capsys):
    st = load_st(AID)
    png(vdir(AID, "views_front", 1) / "final/front.png", (40, 40))
    st |= {"stage": "views_front", "state": "running", "versions": {"blockout": 2, "views_front": 1},
           "approved": {"blockout": 2}, "offer": None, "offer_key": None}
    save_st(st)
    show(capsys)
    cards = payload(ROOT / "show/house-a.html")["assets"]
    assert [(c["step"], c["version"], c["header"]) for c in cards] == [
        ("views_front", 1, "House A · views_front v1 · running"), ("blockout", 2, "House A · blockout v2 · đã duyệt")]


def test_bundle_scales_images_to_1024_px_keeps_crops_and_embeds_everything_in_one_file(project, capsys):
    final = ROOT / FINAL
    png(final / "review/game_cam.png", (2000, 1500))
    png(final / "review/lineup.png", (1500, 500), "RGBA")
    png(final / "review/crop_roof.png", (1500, 1000))
    png(project / "concepts/_approved/house-a/concept_albedo.png", (800, 600))
    out = show(capsys, bundle=True)
    page = ROOT / "show/house-a-bundle.html"
    a = payload(page)["assets"][0]
    assert out.startswith("OK: production/show/house-a-bundle.html (")
    assert [(i["n"], *decoded(i["u"])) for i in a["images"]] == [
        ("review/game_cam.png", "data:image/jpeg;base64", (1024, 768)),
        ("concept/concept_albedo.png", "data:image/png;base64", (800, 600)),
        ("review/crop_roof.png", "data:image/png;base64", (1500, 1000)),
        ("review/lineup.png", "data:image/png;base64", (1024, 341))]
    assert a["sheet"] == a["images"][0]["u"]
    assert "../" not in page.read_text(encoding="utf-8").split('type="application/json">')[1].split("</script>")[0]
    assert page.stat().st_size < 400_000


def noise(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(path)


def test_bundle_scales_a_crop_over_the_byte_cap_so_one_render_cannot_swell_the_file(project, capsys):
    noise(ROOT / FINAL / "review/crop_roof.png", (700, 700))
    noise(ROOT / FINAL / "review/crop_door.png", (1300, 1300))
    assert (ROOT / FINAL / "review/crop_door.png").stat().st_size > board.CROP_BYTES > (
        ROOT / FINAL / "review/crop_roof.png").stat().st_size
    show(capsys, bundle=True)
    a = payload(ROOT / "show/house-a-bundle.html")["assets"][0]
    assert {i["n"]: decoded(i["u"])[1] for i in a["images"] if "crop" in i["n"]} == {
        "review/crop_roof.png": (700, 700), "review/crop_door.png": (1024, 1024)}


def test_bundle_over_the_total_cap_is_refused_and_names_the_way_out(project, capsys, monkeypatch):
    (ROOT / FINAL / "assembled.glb").write_bytes(b"g" * (1200 * 1024))
    monkeypatch.setattr(board, "BUNDLE_MAX", 1 << 20)
    with pytest.raises(ProducerError) as ex:
        show(capsys, bundle=True)
    assert re.fullmatch(r"house-a: --bundle ra 1\.\d MB, lớn hơn 1\.0 MB: hạ xuống bằng `show house-a --step <bước>` "
                        r"hoặc bỏ --bundle", str(ex.value))
    assert not (ROOT / "show/house-a-bundle.html").exists()


def test_a_glb_over_15_mb_stays_out_of_the_file_and_the_output_says_so(project, capsys):
    (ROOT / FINAL / "assembled.glb").write_bytes(b"g" * (15 * 2**20 + 1))
    out = show(capsys, bundle=True)
    assert (payload(ROOT / "show/house-a-bundle.html")["assets"][0]["glb"], out.rstrip().endswith(
        "; GLB lớn hơn 15 MB không nhúng: assembled.glb")) == (None, True)


def test_the_renderer_has_one_model_viewer_version_and_nothing_else_names_one_row_64(project):
    hits = [p for p in board.SKILL_DIR.rglob("*") if p.is_file() and ".deps" not in p.parts
            and p.suffix in (".js", ".html", ".py", ".md") and "model-viewer@" in p.read_text(encoding="utf-8", errors="ignore")]
    js = (board.BOARD_DIR / "board.js").read_text(encoding="utf-8")
    assert ([p.name for p in hits], re.findall(r'MODEL_VIEWER_VERSION = "([\d.]+)"', js)) == (["board.js"], ["3.5.0"])
    assert ("</script>" in js, "<!--" in js) == (False, False)


def test_board_and_static_page_never_show_the_runtime_folder_name_row_62(tmp_path):
    env = os.environ | {"PRODUCER_ROOT": "production-codex"}
    run = lambda *a: subprocess.run([sys.executable, str(P), *a], cwd=tmp_path, env=env, capture_output=True, text=True,  # noqa: E731
                                    check=True).stdout
    run("init", "--project", "Pilot", "--concepts", "concepts")
    run("new", AID, "--title", "House A")
    png(tmp_path / "production-codex/assets/house-a/blockout/v1/final/review/game_cam.png", (20, 20))
    st = json.loads((tmp_path / "production-codex/assets/house-a/status.json").read_text(encoding="utf-8"))
    st |= {"state": "waiting_human", "versions": {"blockout": 1}, "offer": 1}
    (tmp_path / "production-codex/assets/house-a/status.json").write_text(json.dumps(st), encoding="utf-8")
    out = run("show", AID)
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from core import board, state; "
            "print(json.dumps(board.board_payload(state.load_cfg())))")
    api = subprocess.run([sys.executable, "-c", code, str(P.parent)], cwd=tmp_path, env=env, capture_output=True,
                         text=True, check=True).stdout
    page = (tmp_path / "production-codex/show/house-a.html").read_text(encoding="utf-8")
    assert out.startswith("OK: production-codex/show/house-a.html")
    assert ["codex" in x for x in (page, api, "house-a.html")] == [False, False, False]
