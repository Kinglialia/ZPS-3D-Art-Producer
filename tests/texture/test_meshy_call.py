"""meshy_call.py (docs/producer.md §6.3, D24.2, D24.3; checklist 45, 46, 84) against a fake Meshy HTTP layer: the real
service costs credits. The kit gen_api.py runs unchanged; only urllib is replaced, so the kit's own charge-before-call,
task.json and wait/download run for real."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import glbkit

HERE = Path(__file__).resolve().parent
CALL = HERE.parents[1] / "src/zps-3dp-producer/scripts/meshy_call.py"
PROJECT_KEY, SHELL_KEY = "msy-project-0123456789", "msy-shell-9876543210"
AID = "chest"


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
    import hashlib
    sha = hashlib.sha256(model.read_bytes()).hexdigest()
    budget = tmp_path / f"production/assets/{AID}/texture/budget-{sha[:12]}.json"
    budget.parent.mkdir(parents=True)
    budget.write_text(json.dumps({"max_credits": 10, "used_credits": 0}), encoding="utf-8")
    log, pids = tmp_path / "meshy.jsonl", tmp_path / "production/pids/meshy"

    def run(*extra, mode="", cmd="texture", out="work/meshy/call-1", model_path=model):
        env = {**os.environ, "PYTHONPATH": str(HERE / "fake_meshy"), "FAKE_MESHY_LOG": str(log),
               "FAKE_MESHY_MODE": mode, "FAKE_MESHY_PIDS": str(pids), "MESHY_API_KEY": SHELL_KEY}
        args = {"texture": ["--asset", AID, "--model", str(model_path), "--style-image", str(style), "--out", out,
                            "--pid-file", str(pids / f"{AID}.pid")],
                "price": ["--model", str(model_path), "--style-image", str(style)], "keys": []}[cmd]
        p = subprocess.run([sys.executable, str(CALL), cmd, *args, *extra], cwd=tmp_path, capture_output=True,
                           text=True, env=env)
        rec = tmp_path / out / "meshy_call.json"
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr,
                "calls": [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else [],
                "record": json.loads(rec.read_text()) if rec.exists() else None,
                "budget": json.loads(budget.read_text()), "files": sorted(x.name for x in (tmp_path / out).glob("*"))
                if (tmp_path / out).is_dir() else []}
    run.tmp, run.model, run.budget, run.pids = tmp_path, model, budget, pids
    return run


def kinds(r):
    return [c["kind"] for c in r["calls"]]


def no_key_anywhere(r, tmp):
    text = r["out"] + r["err"] + "".join(p.read_text(errors="replace") for p in tmp.rglob("*.json"))
    return PROJECT_KEY not in text and SHELL_KEY not in text


def test_a_call_uses_the_project_key_although_the_shell_exports_another_and_charges_one_retexture(meshy):
    r = meshy()
    assert (r["rc"], r["out"]) == (0, f"[meshy_call] ok lần 1 task task-1 -> {meshy.tmp}/work/meshy/call-1/glb.glb\n")
    assert [(c["method"], c["kind"], c["auth"]) for c in r["calls"]] == [
        ("POST", "post", f"Bearer {PROJECT_KEY}"), ("GET", "poll", f"Bearer {PROJECT_KEY}"), ("GET", "download", None)]
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["files"] == ["glb.glb", "meshy_call.json", "task.json"]
    assert (meshy.tmp / "work/meshy/call-1/glb.glb").read_bytes() == meshy.model.read_bytes()
    assert {k: r["record"][k] for k in ("status", "task_id", "tries", "credits_charged", "budget_after")} == {
        "status": "ok", "task_id": "task-1", "tries": [], "credits_charged": 10,
        "budget_after": {"max_credits": 10, "used_credits": 10}}
    assert no_key_anywhere(r, meshy.tmp)


def test_the_call_holds_a_meshy_slot_of_its_own_pid_while_it_runs_and_frees_it_after(meshy):
    r = meshy()
    names = r["calls"][0]["pids"]
    assert len(names) == 1 and names[0].startswith(f"{AID}-") and names[0].endswith(".pid")
    assert list(meshy.pids.glob("*.pid")) == []


def test_a_network_error_before_the_task_exists_is_refunded_and_retried_so_one_retexture_costs_10_not_20(meshy):
    r = meshy(mode="post_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post_fail", "post", "poll", "download"])
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["record"]["tries"] == [{"stage": "before_task", "error": "<urlopen error connection reset>", "refunded": 10}]


def test_a_poll_error_after_the_task_exists_waits_on_the_same_task_and_never_creates_a_second_one(meshy):
    r = meshy(mode="poll_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll_fail", "poll", "download"])
    assert [c["url"].rsplit("/", 1)[1] for c in r["calls"] if c["method"] == "GET" and "poll" in c["kind"]] == [
        "task-1", "task-1"]
    assert r["budget"] == {"max_credits": 10, "used_credits": 10}
    assert r["record"]["tries"] == [{"stage": "after_task", "task_id": "task-1",
                                     "error": "HTTP 503 from https://api.meshy.ai/openapi/v1/retexture/task-1: busy"}]


def test_a_download_error_after_the_task_exists_downloads_the_same_task_again(meshy):
    r = meshy(mode="download_fail:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll", "download_fail", "poll", "download"])
    assert r["budget"]["used_credits"] == 10


def test_a_cut_off_glb_that_gen_api_accepted_is_not_taken_and_the_same_task_is_downloaded_again(meshy):
    r = meshy(mode="truncated:1")
    assert (r["rc"], kinds(r)) == (0, ["post", "poll", "truncated", "poll", "download"])
    assert (meshy.tmp / "work/meshy/call-1/glb.glb").read_bytes() == meshy.model.read_bytes()
    assert r["record"]["tries"] == [{"stage": "after_task", "task_id": "task-1", "error": "GLB hỏng hoặc thiếu"}]


def test_three_failures_before_the_task_exists_stop_as_blocked_with_the_whole_budget_refunded(meshy):
    r = meshy(mode="post_fail:3")
    assert (r["rc"], kinds(r)) == (1, ["post_fail"] * 3)
    assert r["out"] == "[meshy_call] BLOCKED 3/3: <urlopen error connection reset>\n"
    assert (r["budget"], r["record"]["credits_charged"]) == ({"max_credits": 10, "used_credits": 0}, 0)


def test_three_failures_after_the_task_exists_stop_as_blocked_and_keep_the_spent_credit(meshy):
    r = meshy(mode="poll_fail:3")
    assert (r["rc"], kinds(r)) == (1, ["post", "poll_fail", "poll_fail", "poll_fail"])
    assert (r["budget"]["used_credits"], r["record"]["status"], r["record"]["task_id"]) == (10, "fail", "task-1")


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
    assert (r["rc"], kinds(r)) == (0, ["echo_key", "post", "poll", "download"])
    assert r["record"]["tries"][0]["error"] == (
        "HTTP 401 from https://api.meshy.ai/openapi/v1/retexture: bad token Bearer <MESHY_API_KEY>")
    assert no_key_anywhere(r, meshy.tmp)


def test_a_folder_of_an_earlier_call_is_refused_so_one_folder_holds_one_paid_call(meshy):
    assert meshy()["rc"] == 0
    r = meshy()
    assert (r["rc"], kinds(r)) == (3, ["post", "poll", "download"])
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
