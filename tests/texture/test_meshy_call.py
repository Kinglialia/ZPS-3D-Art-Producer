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
PROJECT_KEY, SHELL_KEY = "msy-project-0123456789", "msy-shell-9876543210"
AID = "crate"
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
    (tmp_path / "production/pipeline.toml").touch()
    prof = {"project": "T", "paths": {"env_file": ".env"}}
    (tmp_path / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump(prof), encoding="utf-8")
    (tmp_path / ".env").write_text(f"MESHY_API_KEY={PROJECT_KEY}\n", encoding="utf-8")
    v, uv, f = glbkit.box()
    model = glbkit.write(tmp_path / f"{AID}-untextured.glb", v, uv, f)
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


def tiles(nx=3, ny=3, nz=2):
    """nx * ny * nz boxes, 12 triangles each, every box its own UV cell of a 6 x 3 grid: a locked mesh with UV islands."""
    v, uv, f = [], [], []
    for k, (i, j, m) in enumerate((i, j, m) for m in range(nz) for j in range(ny) for i in range(nx)):
        bv, buv, bf = glbkit.box()
        f += (bf + len(v)).tolist()
        v += (bv + np.array([i, j, m]) * 1.5).tolist()
        uv += ((buv + [k % 6, k // 6]) / [6, 3]).tolist()
    return np.array(v), np.array(uv), np.array(f)


@pytest.fixture
def normalized(meshy):
    """The locked mesh, and the GLB Meshy returns for it: scaled x2 about its centre, moved up, with the vertex order,
    the triangle order and the corner order of every triangle changed (D30.3). As Blender exports it, the locked mesh
    has 16-bit indices and split vertices (the second triangle of each quad of the first box has its own copies);
    Meshy welds them and writes 32-bit indices, so the two files differ in vertex count and index type."""
    v, uv, f = tiles()
    split = f.copy()
    split[1:12:2] = len(v) + np.arange(18).reshape(6, 3)
    lv, luv = np.r_[v, v[f[1:12:2].reshape(-1)]], np.r_[uv, uv[f[1:12:2].reshape(-1)]]
    locked = glbkit.write(meshy.tmp / f"{AID}-tiles-untextured.glb", lv, luv, split, index_dtype="<u2")
    rng = np.random.default_rng(3)
    perm = rng.permutation(len(v))
    mv, muv = np.empty_like(v), np.empty_like(uv)
    mv[perm], muv[perm] = (v - (v.min(0) + v.max(0)) / 2) * 2 + [0, 0, 0.37], uv
    mf = np.roll(perm[f][rng.permutation(len(f))], 1, axis=1)
    meshy.normalized = glbkit.write(meshy.tmp / "meshy-normalized.glb", mv, muv, mf)
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
    lock.write_text(str(os.getpid()), encoding="utf-8")
    r = meshy()
    assert (r["rc"], r["calls"], r["budget"]["used_credits"]) == (3, [], 0)
    assert r["out"] == (f"[meshy_call] từ chối: {lock.name} có: một lần gọi Meshy khác đang chạy trên mesh này (pid "
                        f"{os.getpid()}); chờ nó xong, hoặc xóa file đó khi không còn process này\n")
    assert lock.read_text(encoding="utf-8") == str(os.getpid())


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_a_lock_whose_process_died_does_not_block_the_asset_so_the_paid_call_runs_and_frees_it(meshy):
    """A killed call left budget-<sha>.lock behind; before, the asset was stuck until a human deleted the file."""
    lock = meshy.budget.with_suffix(".lock")
    lock.write_text(str(dead_pid()), encoding="utf-8")
    r = meshy()
    assert (r["rc"], kinds(r), r["budget"]["used_credits"]) == (0, ["post", "poll", "download", "poll", "base_color"], 10)
    assert not lock.exists()


@pytest.mark.parametrize("content", ["", "not a pid"])
def test_a_lock_without_a_readable_pid_still_refuses_because_it_may_be_a_call_that_is_starting(meshy, content):
    lock = meshy.budget.with_suffix(".lock")
    lock.write_text(content, encoding="utf-8")
    r = meshy()
    assert (r["rc"], r["calls"], r["budget"]["used_credits"]) == (3, [], 0)
    assert lock.exists()


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


def accessors(glb: Path):
    data = glb.read_bytes()
    return json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])["accessors"]


def bbox(glb: Path):
    a = accessors(glb)[0]
    return [round(x, 4) for x in a["min"]], [round(x, 4) for x in a["max"]]


def test_a_meshy_glb_scaled_x2_moved_and_reordered_passes_because_only_triangles_and_uvs_count(meshy, normalized):
    """Meshy's retexture API always normalizes the GLB; a check on position or order would fail every paid call."""
    assert (bbox(normalized), bbox(meshy.normalized)) == (([-0.5, 0.0, -3.5], [3.5, 2.5, 0.5]),
                                                          ([-4.0, -2.13, -4.0], [4.0, 2.87, 4.0]))
    assert [(a["count"], a["componentType"]) for a in accessors(normalized)] == [(450, 5126), (450, 5126), (648, 5123)]
    assert [(a["count"], a["componentType"]) for a in accessors(meshy.normalized)] == [(432, 5126), (432, 5126),
                                                                                       (648, 5125)]
    r = meshy(model_path=normalized, glb=meshy.normalized)
    assert (r["rc"], r["record"]["status"], r["topology"]["overall"], failed(r)) == (0, "ok", "pass", [])
    assert [(c["check"], c["value"], c["threshold"]) for c in r["topology"]["checks"]] == [
        ("meshy.tris", 216, 216), ("meshy.uv_triples", 0, 0), ("meshy.base_color_px", [RES, RES], [RES, RES])]
    assert r["topology"]["data"]["locked_sha256"] == hashlib.sha256(normalized.read_bytes()).hexdigest()


def test_the_same_triangles_in_another_order_and_corner_order_pass_because_meshy_may_rewrite_the_index_buffer(
        meshy, normalized):
    g = edit_glb(meshy.normalized, meshy.tmp / "shuffled.glb", shuffled)
    r = meshy(model_path=normalized, glb=g)
    assert (r["rc"], failed(r)) == (0, [])


def test_one_moved_uv_fails_as_a_hard_gate_and_leaves_no_albedo_because_the_paint_would_land_off_the_locked_uv(
        meshy, normalized):
    g = edit_glb(meshy.normalized, meshy.tmp / "moved.glb", one_uv_moved)
    r = meshy(model_path=normalized, glb=g)
    assert (r["rc"], failed(r), r["topology"]["data"]["hard_gate"]) == (4, ["meshy.uv_triples"], True)
    assert r["topology"]["checks"][1]["value"] >= 1
    assert (r["record"]["status"], r["record"]["albedo"]) == ("topology_fail", None)
    assert json.loads(meshy.budget.read_text())["used_credits"] == 10
    assert r["out"] == (f"[meshy_call] topology fail (meshy.uv_triples) task task-1: không dùng lớp Meshy này, đã tốn "
                        f"10 credit -> {meshy.tmp}/work/meshy/call-1/topology.json\n")


def test_one_missing_triangle_fails_because_the_meshy_mesh_is_no_longer_the_locked_mesh(meshy, normalized):
    g = edit_glb(meshy.normalized, meshy.tmp / "missing.glb", one_triangle_missing)
    r = meshy(model_path=normalized, glb=g)
    assert (r["rc"], failed(r)) == (4, ["meshy.tris", "meshy.uv_triples"])
    assert r["topology"]["checks"][0]["value"] == 215


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


def test_uv_noise_inside_the_tolerance_on_every_corner_passes_so_float_rounding_never_fails_a_paid_call(meshy, normalized):
    g = edit_glb(meshy.normalized, meshy.tmp / "noise.glb", uv_noise(9e-5))
    r = meshy(model_path=normalized, glb=g)
    assert (r["rc"], failed(r)) == (0, [])


def test_one_uv_moved_just_past_the_tolerance_fails(meshy, normalized):
    g = edit_glb(meshy.normalized, meshy.tmp / "past.glb", uv_moved_by(2e-4))
    r = meshy(model_path=normalized, glb=g)
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


def test_a_slow_task_exits_pending_and_resume_waits_on_that_task_without_a_second_post_or_charge_d33_5(meshy):
    """Run 5: one Meshy wait ran past what a Bash call holds. A slow task is not an error: the run ends with exit 5 and
    the task id on disk, and --resume finishes that same paid task. A second POST would cost the user credits again."""
    r = meshy("--timeout", "2", mode="running:100")
    assert (r["rc"], kinds(r)[:2], r["record"]["status"]) == (5, ["post", "running"], "pending")
    assert json.loads((meshy.tmp / "work/meshy/call-1/task.json").read_text())["task_id"] == "task-1"
    assert r["budget"]["used_credits"] == 10 and "--resume" in r["out"]
    r = meshy("--resume")
    assert r["rc"] == 0, r["out"]
    assert kinds(r).count("post") == 1 and r["record"]["task_id"] == "task-1"
    assert (r["budget"]["used_credits"], r["record"]["credits_charged"]) == (10, 0)


def test_resume_without_a_task_is_refused_d33_5(meshy):
    r = meshy("--resume")
    assert (r["rc"], kinds(r)) == (3, [])
    assert "không tạo task mới khi resume" in r["out"]


def test_past_the_total_wait_one_status_request_is_made_and_a_running_task_stays_blocked_without_a_new_task_or_charge(meshy):
    meshy("--timeout", "2", mode="running:100")
    r = meshy("--resume", "--total-s", "0", mode="running:100")
    assert (r["rc"], r["record"]["status"], kinds(r)) == (1, "blocked_total", ["post", "running", "running"])
    assert (r["budget"]["used_credits"], r["record"]["credits_charged"]) == (10, 0)
    assert r["record"]["task_id"] == "task-1"
    assert no_key_anywhere(r, meshy.tmp)


def test_past_the_total_wait_a_task_that_succeeded_meanwhile_is_downloaded_so_the_paid_result_is_not_lost(meshy):
    """The task finished on Meshy after the last wait ended. Blocking here would throw away the credit it cost."""
    meshy("--timeout", "2", mode="running:100")
    r = meshy("--resume", "--total-s", "0", mode="running:1")
    assert (r["rc"], r["record"]["status"], r["topology"]["overall"]) == (0, "ok", "pass")
    assert kinds(r) == ["post", "running", "poll", "poll", "download", "poll", "base_color"]
    assert (r["budget"]["used_credits"], r["record"]["credits_charged"]) == (10, 0)
    assert (meshy.tmp / "work/meshy/call-1/glb.glb").read_bytes() == meshy.model.read_bytes()
    assert no_key_anywhere(r, meshy.tmp)


def test_past_the_total_wait_a_task_meshy_ended_as_failed_gives_the_credit_back_instead_of_blocking_for_good(meshy):
    meshy("--timeout", "2", mode="failed_after_running:1")
    r = meshy("--resume", "--total-s", "0", mode="failed_after_running:1")
    assert (r["rc"], kinds(r).count("post"), r["budget"]["used_credits"]) == (1, 1, 0)
    assert "task-ended.json" in r["files"]


def test_a_task_that_fails_on_the_resume_run_gives_back_the_credit_the_first_run_charged(meshy):
    """On a resume run the budget already holds the first run's charge. Refunding to that level gave nothing back."""
    r = meshy("--timeout", "2", mode="failed_after_running:1")
    assert (r["rc"], r["budget"]["used_credits"]) == (5, 10)
    r = meshy("--resume", mode="failed_after_running:1")
    assert (r["rc"], kinds(r).count("post")) == (1, 1)
    assert r["budget"] == {"max_credits": 10, "used_credits": 0}
    assert (r["record"]["credits_charged"], r["files"]) == (0, ["meshy_call.json", "task-ended.json"])


def test_the_refund_does_not_depend_on_the_record_of_the_first_run_because_that_run_may_have_been_killed(meshy):
    meshy("--timeout", "2", mode="failed_after_running:1")
    (meshy.tmp / "work/meshy/call-1/meshy_call.json").unlink()
    r = meshy("--resume", mode="failed_after_running:1")
    assert (r["rc"], r["budget"]["used_credits"]) == (1, 0)


def test_the_refund_is_the_charge_of_the_task_so_credits_of_other_calls_on_the_budget_stay(meshy):
    meshy.budget.write_text(json.dumps({"max_credits": 30, "used_credits": 10}), encoding="utf-8")
    meshy("--timeout", "2", mode="failed_after_running:1")
    assert json.loads(meshy.budget.read_text())["used_credits"] == 20
    r = meshy("--resume", mode="failed_after_running:1")
    assert r["budget"] == {"max_credits": 30, "used_credits": 10}


def test_both_files_downloaded_but_no_topology_json_runs_only_the_gate_without_a_request_or_a_charge(meshy):
    """A run was killed between the last download and the gate. The folder is paid and complete; it is not 'used'."""
    assert meshy()["rc"] == 0
    topo = meshy.tmp / "work/meshy/call-1/topology.json"
    topo.unlink()
    r = meshy()
    assert (r["rc"], r["topology"]["overall"], r["record"]["status"]) == (0, "pass", "ok")
    assert (len(r["calls"]), r["budget"]["used_credits"], r["record"]["credits_charged"]) == (5, 10, 0)
    assert r["record"]["albedo"] == f"{meshy.tmp}/work/meshy/call-1/base_color.png"


def test_the_gate_only_rerun_also_works_when_the_killed_run_left_no_meshy_call_json(meshy):
    assert meshy()["rc"] == 0
    for name in ("topology.json", "meshy_call.json"):
        (meshy.tmp / "work/meshy/call-1" / name).unlink()
    r = meshy()
    assert (r["rc"], r["topology"]["overall"], len(r["calls"])) == (0, "pass", 5)


def test_a_gate_only_rerun_that_fails_the_gate_is_a_topology_fail_and_charges_nothing(meshy):
    assert meshy()["rc"] == 0
    (meshy.tmp / "work/meshy/call-1/topology.json").unlink()
    card_res(meshy, 128)
    r = meshy()
    assert (r["rc"], failed(r), r["record"]["albedo"], len(r["calls"])) == (4, ["meshy.base_color_px"], None, 5)
    assert r["budget"]["used_credits"] == 10


def test_a_folder_with_its_gate_result_is_still_refused_because_the_gate_only_rerun_is_for_a_missing_topology_json(meshy):
    assert meshy()["rc"] == 0
    r = meshy()
    assert (r["rc"], len(r["calls"])) == (3, 5)


def test_one_run_waits_up_to_1700_seconds_by_default_so_a_slow_task_is_not_cut_at_8_minutes(meshy):
    p = subprocess.run([sys.executable, str(CALL), "texture", "--help"], cwd=meshy.tmp, capture_output=True, text=True)
    assert "default: 1700" in " ".join(p.stdout.split())


def test_the_kit_wait_inside_every_child_follows_timeout_because_its_own_1200_s_would_end_a_run_as_a_retry(meshy):
    """The kit gives up at 1200 s with an error; the wrapper counts an error as a try, three tries are BLOCKED."""
    assert meshy(mode="poll_fail:3")["rc"] == 1
    r = meshy()
    assert (r["rc"], {c["kit_wait_s"] for c in r["calls"]}) == (0, {1700})


def test_an_explicit_timeout_sets_the_kit_wait_of_the_children(meshy):
    r = meshy("--timeout", "900")
    assert (r["rc"], {c["kit_wait_s"] for c in r["calls"]}) == (0, {900})


def test_a_failed_task_is_refunded_once_because_its_task_file_moves_away_before_the_refund(meshy):
    meshy("--timeout", "2", mode="failed_after_running:1")
    r = meshy("--resume", mode="failed_after_running:1")
    assert (r["rc"], r["budget"]["used_credits"], "task.json" in r["files"]) == (1, 0, False)
    r = meshy("--resume", mode="failed_after_running:1")
    assert (r["rc"], r["budget"]["used_credits"]) == (3, 0)
