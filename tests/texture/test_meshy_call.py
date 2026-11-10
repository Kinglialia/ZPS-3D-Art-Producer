"""meshy_call.py (docs/producer.md §6.3, D24.2, D24.3, D30.3; checklist 45, 46, 84) against a fake Meshy HTTP layer: the
real service costs credits. The kit gen_api.py runs unchanged; only urllib is replaced, so the kit's own
charge-before-call, task.json and wait/download run for real."""
import hashlib
import json
import struct
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

import glbkit

HERE = Path(__file__).resolve().parent
CALL = HERE.parents[1] / "src/zps-3dp-producer/scripts/meshy_call.py"
RUN5 = HERE.parent / "fixtures/meshy_run5"
PROJECT_KEY, SHELL_KEY = "msy-project-0123456789", "msy-shell-9876543210"
AID = "chest"
RES = 64
OK_KINDS = ["post", "poll", "download", "poll", "base_color"]


def budget_for(tmp, model, max_credits=10):
    sha = hashlib.sha256(model.read_bytes()).hexdigest()
    b = tmp / f"production/assets/{AID}/texture/budget-{sha[:12]}.json"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"max_credits": max_credits, "used_credits": 0}), encoding="utf-8")
    return b


@pytest.fixture
def meshy(tmp_path):
    (tmp_path / "production").mkdir()
    prof = {"project": "T", "paths": {"env_file": ".env"}}
    (tmp_path / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump(prof), encoding="utf-8")
    (tmp_path / ".env").write_text(f"MESHY_API_KEY={PROJECT_KEY}\n", encoding="utf-8")
    v, uv, f = glbkit.box()
    model = glbkit.write(tmp_path / "chest-untextured.glb", v, uv, f)
    style = tmp_path / "concept_albedo.png"
    style.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    budget = budget_for(tmp_path, model)
    card = tmp_path / "concepts/_approved" / AID / "asset-card.yaml"
    card.parent.mkdir(parents=True)
    card.write_text(yaml.safe_dump({"asset": AID, "texture_res": RES}), encoding="utf-8")
    (budget.parents[1] / "status.json").write_text(json.dumps({"id": AID, "concept_dir": str(card.parent)}),
                                                   encoding="utf-8")
    log, pids = tmp_path / "meshy.jsonl", tmp_path / "production/pids/meshy"

    def run(*extra, mode="", cmd="texture", out="work/meshy/call-1", model_path=model, glb=None, base_px=RES,
            stripes=False):
        env = {**os.environ, "PYTHONPATH": str(HERE / "fake_meshy"), "FAKE_MESHY_LOG": str(log),
               "FAKE_MESHY_MODE": mode, "FAKE_MESHY_PIDS": str(pids), "MESHY_API_KEY": SHELL_KEY,
               "FAKE_MESHY_GLB": str(glb or ""), "FAKE_MESHY_BASE_PX": str(base_px),
               "FAKE_MESHY_BASE_STRIPES": "1" if stripes else ""}
        args = {"texture": ["--asset", AID, "--model", str(model_path), "--style-image", str(style), "--out", out,
                            "--pid-file", str(pids / f"{AID}.pid")],
                "price": ["--model", str(model_path), "--style-image", str(style)], "keys": []}[cmd]
        p = subprocess.run([sys.executable, str(CALL), cmd, *args, *extra], cwd=tmp_path, capture_output=True,
                           text=True, env=env)
        rec, topo = tmp_path / out / "meshy_call.json", tmp_path / out / "topology.json"
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr,
                "calls": [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else [],
                "record": json.loads(rec.read_text()) if rec.exists() else None,
                "topology": json.loads(topo.read_text()) if topo.exists() else None,
                "budget": json.loads(budget.read_text()), "files": sorted(x.name for x in (tmp_path / out).glob("*"))
                if (tmp_path / out).is_dir() else []}
    run.tmp, run.model, run.budget, run.pids, run.card = tmp_path, model, budget, pids, card
    return run


def kinds(r):
    return [c["kind"] for c in r["calls"]]


def no_key_anywhere(r, tmp):
    text = r["out"] + r["err"] + "".join(p.read_text(errors="replace") for p in tmp.rglob("*.json"))
    return PROJECT_KEY not in text and SHELL_KEY not in text


def edit_glb(src: Path, dst: Path, edit) -> Path:
    """Copy a GLB with edit(doc, bin: bytearray) applied to its JSON and binary chunks."""
    data = src.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    doc, binary = json.loads(data[20:20 + n]), bytearray(data[28 + n:])
    edit(doc, binary)
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
    dst.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    return dst


def view(doc, binary, acc, dtype, comps, width):
    a = doc["accessors"][acc]
    off = doc["bufferViews"][a["bufferView"]].get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(binary, dtype, a["count"] * comps, off).reshape(-1, width), off


def indices_of(doc):
    return doc["meshes"][0]["primitives"][0]["indices"]


def uvs_of(doc):
    return doc["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]


def shuffled(doc, binary):
    idx, off = view(doc, binary, indices_of(doc), "<u4", 1, 3)
    rng = np.random.default_rng(5)
    out = np.roll(idx[rng.permutation(len(idx))], 1, axis=1).astype("<u4")
    binary[off:off + out.nbytes] = out.tobytes()


def one_uv_moved(doc, binary):
    uv, off = view(doc, binary, uvs_of(doc), "<f4", 2, 2)
    binary[off:off + 4] = struct.pack("<f", uv[0, 0] + 0.01)


def uv_noise(amp):
    def edit(doc, binary):
        uv, off = view(doc, binary, uvs_of(doc), "<f4", 2, 2)
        out = (uv + np.random.default_rng(7).uniform(-amp, amp, uv.shape)).astype("<f4")
        binary[off:off + out.nbytes] = out.tobytes()
    return edit


def uv_moved_by(du):
    def edit(doc, binary):
        uv, off = view(doc, binary, uvs_of(doc), "<f4", 2, 2)
        binary[off:off + 4] = struct.pack("<f", uv[0, 0] + du)
    return edit


def one_triangle_missing(doc, binary):
    doc["accessors"][indices_of(doc)]["count"] -= 3


@pytest.fixture
def run5(meshy):
    locked = meshy.tmp / "wooden-chest-untextured.glb"
    locked.write_bytes((RUN5 / "locked.glb").read_bytes())
    meshy.budget = budget_for(meshy.tmp, locked)
    return locked


def test_a_call_uses_the_project_key_although_the_shell_exports_another_and_charges_one_retexture(meshy):
    r = meshy()
    albedo = f"{meshy.tmp}/work/meshy/call-1/base_color.png"
    assert (r["rc"], r["out"]) == (0, f"[meshy_call] ok lần 1 task task-1, topology pass -> {albedo}\n")
    assert [(c["method"], c["kind"], c["auth"]) for c in r["calls"]] == [
        ("POST", "post", f"Bearer {PROJECT_KEY}"), ("GET", "poll", f"Bearer {PROJECT_KEY}"), ("GET", "download", None),
        ("GET", "poll", f"Bearer {PROJECT_KEY}"), ("GET", "base_color", None)]
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["files"] == ["base_color.png", "glb.glb", "meshy_call.json", "task.json", "topology.json"]
    assert (meshy.tmp / "work/meshy/call-1/glb.glb").read_bytes() == meshy.model.read_bytes()
    assert {k: r["record"][k] for k in ("status", "task_id", "tries", "credits_charged", "budget_after", "topology",
                                        "albedo")} == {
        "status": "ok", "task_id": "task-1", "tries": [], "credits_charged": 10,
        "budget_after": {"max_credits": 10, "used_credits": 10}, "topology": "pass", "albedo": albedo}
    assert no_key_anywhere(r, meshy.tmp)


def test_the_call_holds_a_meshy_slot_of_its_own_pid_while_it_runs_and_frees_it_after(meshy):
    r = meshy()
    names = r["calls"][0]["pids"]
    assert len(names) == 1 and names[0].startswith(f"{AID}-") and names[0].endswith(".pid")
    assert list(meshy.pids.glob("*.pid")) == []


def test_a_refused_connection_never_reached_meshy_so_it_is_refunded_and_retried_and_one_retexture_costs_10(meshy):
    r = meshy(mode="post_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post_fail", *OK_KINDS])
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["record"]["tries"] == [{"stage": "before_task", "error": "<urlopen error [Errno 61] Connection refused>",
                                     "refunded": 10}]


def test_a_post_whose_response_is_lost_keeps_the_charge_and_is_not_sent_again_because_meshy_may_hold_a_paid_task(meshy):
    r = meshy(mode="post_lost:1")
    assert (r["rc"], kinds(r)) == (1, ["post_lost"])
    assert r["out"] == ("[meshy_call] BLOCKED: POST có thể đã tới Meshy (<urlopen error [Errno 54] Connection reset by "
                        "peer>): giữ 10 credit, không gửi lại; xem task trên Meshy trước khi gọi tiếp\n")
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["record"]["tries"] == [{"stage": "maybe_sent", "error": "<urlopen error [Errno 54] Connection reset by peer>",
                                     "refunded": 0}]


def test_a_poll_error_after_the_task_exists_waits_on_the_same_task_and_never_creates_a_second_one(meshy):
    r = meshy(mode="poll_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll_fail", "poll", "download", "poll", "base_color"])
    assert [c["url"].rsplit("/", 1)[1] for c in r["calls"] if c["method"] == "GET" and "poll" in c["kind"]] == [
        "task-1", "task-1", "task-1"]
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["record"]["tries"] == [{"stage": "after_task", "task_id": "task-1",
                                     "error": "HTTP 503 from https://api.meshy.ai/openapi/v1/retexture/task-1: busy"}]


def test_a_download_error_after_the_task_exists_downloads_the_same_task_again(meshy):
    r = meshy(mode="download_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll", "download_fail", "poll", "download", "poll", "base_color"])
    assert r["budget"]["used_credits"] == 10


def test_a_cut_off_glb_that_gen_api_accepted_is_not_taken_and_the_same_task_is_downloaded_again(meshy):
    r = meshy(mode="truncated:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll", "truncated", "poll", "download", "poll", "base_color"])
    assert (meshy.tmp / "work/meshy/call-1/glb.glb").read_bytes() == meshy.model.read_bytes()
    assert r["record"]["tries"] == [{"stage": "after_task", "task_id": "task-1", "error": "GLB hỏng hoặc thiếu"}]


def test_three_failures_before_the_task_exists_stop_as_blocked_with_the_whole_budget_refunded(meshy):
    r = meshy(mode="post_fail:3")
    assert (r["rc"], kinds(r)) == (1, ["post_fail"] * 3)
    assert r["out"] == "[meshy_call] BLOCKED 3/3: <urlopen error [Errno 61] Connection refused>\n"
    assert (r["budget"], r["record"]["credits_charged"]) == ({"max_credits": 10, "used_credits": 0}, 0)


def test_three_failures_after_the_task_exists_stop_as_blocked_and_keep_the_spent_credit(meshy):
    r = meshy(mode="poll_fail:3")
    assert (r["rc"], kinds(r)) == (1, ["post", "poll_fail", "poll_fail", "poll_fail"])
    assert (r["budget"]["used_credits"], r["record"]["status"], r["record"]["task_id"]) == (10, "fail", "task-1")


def test_a_paid_task_left_without_its_glb_is_resumed_on_the_same_folder_without_a_second_post(meshy):
    assert meshy(mode="poll_fail:3")["rc"] == 1
    r = meshy()
    assert (r["rc"], kinds(r)) == (0, ["post", "poll_fail", "poll_fail", "poll_fail", "poll", "download", "poll",
                                       "base_color"])
    assert (r["budget"], r["record"]["credits_charged"]) == ({"max_credits": 10, "used_credits": 10}, 0)


def test_a_task_meshy_ends_as_failed_is_refunded_and_stops_without_a_second_paid_task(meshy):
    r = meshy(mode="task_failed:1")
    assert (r["rc"], kinds(r)) == (1, ["post", "task_failed"])
    assert r["out"] == ("[meshy_call] BLOCKED: Meshy kết thúc task task-1, đã hoàn budget: task task-1 FAILED: "
                        "{'message': 'mesh không hợp lệ'}\n")
    assert (r["budget"], r["record"]["credits_charged"]) == ({"max_credits": 10, "used_credits": 0}, 0)
    assert r["files"] == ["meshy_call.json", "task-ended.json"]


def test_a_used_up_budget_is_refused_by_the_kit_before_any_request(meshy):
    meshy.budget.write_text(json.dumps({"max_credits": 10, "used_credits": 10}), encoding="utf-8")
    r = meshy()
    assert (r["rc"], r["calls"]) == (3, [])
    assert r["out"] == ("[meshy_call] từ chối: budget would be exceeded (10+10 > 10); ask the user before you raise it\n")
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}


def test_a_mesh_other_than_the_locked_one_has_no_budget_and_is_refused(meshy):
    v, uv, f = glbkit.box((2, 1, 1))
    other = glbkit.write(meshy.tmp / "other.glb", v, uv, f)
    r = meshy(model_path=other)
    assert (r["rc"], r["calls"]) == (3, [])
    assert r["out"].startswith("[meshy_call] từ chối: không có budget-") and r["out"].endswith(
        ".json cho mesh này: chỉ gọi Meshy trên mesh đã khóa\n")


def test_an_error_body_that_repeats_the_key_is_scrubbed_from_the_output_and_the_record(meshy):
    r = meshy(mode="echo_key:1")
    assert (r["rc"], kinds(r)) == (0, ["echo_key", *OK_KINDS])
    assert r["record"]["tries"][0]["error"] == (
        "HTTP 401 from https://api.meshy.ai/openapi/v1/retexture: bad token Bearer <MESHY_API_KEY>")
    assert no_key_anywhere(r, meshy.tmp)


def test_a_folder_of_an_earlier_call_is_refused_so_one_folder_holds_one_paid_call(meshy):
    assert meshy()["rc"] == 0
    r = meshy()
    assert (r["rc"], kinds(r)) == (3, OK_KINDS)
    assert r["out"] == f"[meshy_call] từ chối: {meshy.tmp}/work/meshy/call-1 đã dùng cho một lần gọi trước: dùng thư mục mới\n"


def test_keys_reads_only_the_project_env_file_and_price_comes_from_the_kit_dry_run(meshy):
    assert meshy(cmd="keys")["out"] == "[meshy_call] meshy: key file\n"
    (meshy.tmp / ".env").write_text("OTHER=1\n", encoding="utf-8")
    assert meshy(cmd="keys")["out"] == "[meshy_call] meshy: missing\n"
    r = meshy(cmd="price")
    assert (r["out"], r["calls"]) == ("[meshy_call] retexture: 10 credit\n", [])


def test_a_dry_run_spends_nothing(meshy):
    r = meshy("--dry-run")
    assert (r["rc"], r["out"], r["calls"], r["budget"]["used_credits"]) == (
        0, "[meshy_call] dry-run 10 credit\n", [], 0)


def test_a_profile_without_env_file_means_paint_only_and_no_call(meshy):
    (meshy.tmp / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump({"project": "T", "paths": {}}),
                                                                 encoding="utf-8")
    r = meshy()
    assert (r["rc"], r["calls"]) == (3, [])
    assert r["out"] == "[meshy_call] từ chối: profile không có paths.env_file: chế độ VẼ MỚI, không gọi Meshy\n"


def test_a_second_call_on_the_same_mesh_while_one_runs_is_refused_so_the_budget_is_not_spent_twice(meshy):
    lock = meshy.budget.with_suffix(".lock")
    lock.write_text("4242", encoding="utf-8")
    r = meshy()
    assert (r["rc"], r["calls"], r["budget"]["used_credits"]) == (3, [], 0)
    assert r["out"] == (f"[meshy_call] từ chối: {lock.name} có: một lần gọi Meshy khác đang chạy trên mesh này (pid "
                        "4242); chờ nó xong, hoặc xóa file đó khi không còn process này\n")


def test_the_lock_is_freed_after_a_call_so_the_next_approved_call_can_run(meshy):
    assert meshy()["rc"] == 0
    assert list(meshy.budget.parent.glob("*.lock")) == []


def test_two_calls_started_together_on_one_mesh_post_once_and_spend_one_retexture(meshy):
    log = meshy.tmp / "meshy.jsonl"
    env = {**os.environ, "PYTHONPATH": str(HERE / "fake_meshy"), "FAKE_MESHY_LOG": str(log), "FAKE_MESHY_MODE": "",
           "MESHY_API_KEY": SHELL_KEY, "FAKE_MESHY_BASE_PX": str(RES)}
    ps = [subprocess.Popen([sys.executable, str(CALL), "texture", "--asset", AID, "--model", str(meshy.model),
                            "--style-image", str(meshy.tmp / "concept_albedo.png"), "--out", f"work/race-{k}"],
                           cwd=meshy.tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for k in range(2)]
    rcs = sorted(p.wait() for p in ps)
    posts = [json.loads(l)["kind"] for l in log.read_text().splitlines()].count("post")
    assert (rcs, posts, json.loads(meshy.budget.read_text())) == ([0, 3], 1, {"max_credits": 10, "used_credits": 10})


def test_a_key_line_with_export_is_refused_with_its_fix_because_the_kit_reads_that_line_as_no_key(meshy):
    (meshy.tmp / ".env").write_text(f"export MESHY_API_KEY={PROJECT_KEY}\n", encoding="utf-8")
    msg = "[meshy_call] từ chối: .env có `export MESHY_API_KEY=`, kit không đọc dòng đó: bỏ chữ `export ` ở đầu dòng\n"
    k, r = meshy(cmd="keys"), meshy()
    assert (k["rc"], k["out"], r["rc"], r["out"], r["calls"]) == (3, msg, 3, msg, [])


def failed(r):
    return [c["check"] for c in r["topology"]["checks"] if c["status"] == "fail"]


def test_the_real_run5_meshy_glb_passes_although_meshy_scaled_it_x2_and_moved_it_because_only_triangles_and_uvs_count(
        meshy, run5):
    meshy_max = json.loads((RUN5 / "meshy.glb").read_bytes()[20:20 + struct.unpack(
        "<I", (RUN5 / "meshy.glb").read_bytes()[12:16])[0]])["accessors"][0]["max"]
    assert meshy_max[0] == 1.0
    r = meshy(model_path=run5, glb=RUN5 / "meshy.glb")
    assert (r["rc"], r["record"]["status"], r["topology"]["overall"], failed(r)) == (0, "ok", "pass", [])
    assert [(c["check"], c["value"], c["threshold"]) for c in r["topology"]["checks"]] == [
        ("meshy.tris", 2471, 2471), ("meshy.uv_triples", 0, 0), ("meshy.base_color_px", [RES, RES], [RES, RES])]
    assert r["topology"]["data"]["locked_sha256"] == hashlib.sha256(run5.read_bytes()).hexdigest()


def test_the_same_triangles_in_another_order_and_corner_order_pass_because_meshy_may_rewrite_the_index_buffer(
        meshy, run5):
    g = edit_glb(RUN5 / "meshy.glb", meshy.tmp / "shuffled.glb", shuffled)
    r = meshy(model_path=run5, glb=g)
    assert (r["rc"], failed(r)) == (0, [])


def test_one_moved_uv_fails_as_a_hard_gate_and_leaves_no_albedo_because_the_paint_would_land_off_the_locked_uv(
        meshy, run5):
    g = edit_glb(RUN5 / "meshy.glb", meshy.tmp / "moved.glb", one_uv_moved)
    r = meshy(model_path=run5, glb=g)
    assert (r["rc"], failed(r), r["topology"]["data"]["hard_gate"]) == (4, ["meshy.uv_triples"], True)
    assert r["topology"]["checks"][1]["value"] >= 1
    assert (r["record"]["status"], r["record"]["albedo"]) == ("topology_fail", None)
    assert json.loads(meshy.budget.read_text())["used_credits"] == 10
    assert r["out"] == (f"[meshy_call] topology fail (meshy.uv_triples) task task-1: không dùng lớp Meshy này, đã tốn "
                        f"10 credit -> {meshy.tmp}/work/meshy/call-1/topology.json\n")


def test_one_missing_triangle_fails_because_the_meshy_mesh_is_no_longer_the_locked_mesh(meshy, run5):
    g = edit_glb(RUN5 / "meshy.glb", meshy.tmp / "missing.glb", one_triangle_missing)
    r = meshy(model_path=run5, glb=g)
    assert (r["rc"], failed(r)) == (4, ["meshy.tris", "meshy.uv_triples"])
    assert r["topology"]["checks"][0]["value"] == 2470


def test_a_base_color_of_another_size_than_texture_res_fails_because_assemble_needs_the_card_resolution(meshy):
    r = meshy(base_px=RES // 2)
    assert (r["rc"], failed(r)) == (4, ["meshy.base_color_px"])
    assert r["topology"]["checks"][2]["value"] == [RES // 2, RES // 2]


def test_the_albedo_is_the_base_color_of_the_task_not_the_image_inside_the_normalized_glb(meshy):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (RES, RES), (255, 0, 0)).save(buf, "PNG")
    v, uv, f = glbkit.box()
    g = glbkit.write(meshy.tmp / "with_image.glb", v, uv, f, png=buf.getvalue())
    r = meshy(glb=g)
    assert (r["rc"], r["record"]["albedo"]) == (0, f"{meshy.tmp}/work/meshy/call-1/base_color.png")
    assert Image.open(r["record"]["albedo"]).convert("RGB").getpixel((3, 3)) == (160, 110, 60)


def test_a_base_color_download_error_gets_it_again_from_the_same_task_without_a_second_paid_task(meshy):
    r = meshy(mode="base_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll", "download", "poll", "base_fail", "poll", "base_color"])
    assert (r["budget"]["used_credits"], r["record"]["tries"]) == (
        10, [{"stage": "after_task", "task_id": "task-1", "error": "<urlopen error download reset>"}])


def test_a_paid_task_left_without_its_base_color_is_finished_on_the_same_folder_without_a_post(meshy):
    assert meshy(mode="base_fail:3")["rc"] == 1
    r = meshy()
    assert (r["rc"], kinds(r)[-2:], kinds(r).count("post"), r["budget"]["used_credits"]) == (
        0, ["poll", "base_color"], 1, 10)


def test_the_signed_base_color_url_is_never_written_or_printed(meshy):
    r = meshy()
    text = r["out"] + r["err"] + "".join(p.read_text(errors="replace") for p in meshy.tmp.rglob("*.json"))
    assert r["rc"] == 0 and "Signature" not in text and "assets.meshy.fake" not in text


def test_uv_noise_inside_the_tolerance_on_every_corner_passes_so_float_rounding_never_fails_a_paid_call(meshy, run5):
    g = edit_glb(RUN5 / "meshy.glb", meshy.tmp / "noise.glb", uv_noise(9e-5))
    r = meshy(model_path=run5, glb=g)
    assert (r["rc"], failed(r)) == (0, [])


def test_one_uv_moved_just_past_the_tolerance_fails(meshy, run5):
    g = edit_glb(RUN5 / "meshy.glb", meshy.tmp / "past.glb", uv_moved_by(2e-4))
    r = meshy(model_path=run5, glb=g)
    assert (r["rc"], failed(r)) == (4, ["meshy.uv_triples"])


def card_res(meshy, res):
    meshy.card.write_text(yaml.safe_dump({"asset": AID, "texture_res": res}), encoding="utf-8")


def test_a_larger_base_color_is_cut_to_texture_res_with_an_area_filter_and_both_sizes_are_recorded(meshy):
    from PIL import Image
    card_res(meshy, 1024)
    r = meshy(base_px=2048, stripes=True)
    assert (r["rc"], failed(r)) == (0, [])
    d = r["topology"]["data"]
    assert (d["base_color_px_meshy"], d["base_color_px"]) == ([2048, 2048], [1024, 1024])
    im = Image.open(r["record"]["albedo"]).convert("RGB")
    assert im.size == (1024, 1024)
    assert set(map(tuple, np.asarray(im).reshape(-1, 3))) <= {(127, 127, 127), (128, 128, 128)}
    assert d["base_color_sha256"] == hashlib.sha256(Path(r["record"]["albedo"]).read_bytes()).hexdigest()
    ledger = (meshy.tmp / "production/ledger.md").read_text(encoding="utf-8")
    assert f"{AID} · texture · Meshy base_color 2048x2048 → 1024x1024 (BOX, texture_res) · call-1" in ledger


def test_a_base_color_smaller_than_texture_res_fails_because_upscaling_would_invent_detail(meshy):
    card_res(meshy, 2048)
    r = meshy(base_px=1024)
    assert (r["rc"], failed(r), r["record"]["albedo"]) == (4, ["meshy.base_color_px"], None)


@pytest.mark.parametrize("res,asked", [(1024, "2k"), (2048, "2k"), (4096, "4k")])
def test_the_request_asks_meshy_for_the_smallest_texture_resolution_that_covers_texture_res(meshy, res, asked):
    card_res(meshy, res)
    r = meshy(base_px=res)
    assert (r["rc"], [c["texture_resolution"] for c in r["calls"] if c["kind"] == "post"]) == (0, [asked])


def test_a_texture_res_above_8k_is_refused_before_any_charge_because_meshy_cannot_make_it(meshy):
    card_res(meshy, 16384)
    r = meshy()
    assert (r["rc"], r["calls"], r["budget"]["used_credits"]) == (3, [], 0)
    assert r["out"] == "[meshy_call] từ chối: texture_res 16384 lớn hơn 8k, mức lớn nhất của Meshy retexture: chọn VẼ MỚI\n"
