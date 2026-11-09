"""gen_image_codex.py (D8.3, D15.1, D18) against a fake `codex` on PATH: the real one costs Codex usage."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

import fake_codex

GEN = Path(__file__).resolve().parents[2] / "src/zps-3dp-producer/scripts/gen_image_codex.py"
REQUEST = "Repaint image 2 as the FRONT view of the hut in the style of image 1."


@pytest.fixture
def gen(tmp_path):
    path = fake_codex.install(tmp_path / "bin")
    assert shutil.which("codex", path=path) == str(tmp_path / "bin/codex")
    refs = [tmp_path / "concept_albedo.png", tmp_path / "front_guide.png"]
    for r in refs:
        Image.new("RGB", (64, 64), (1, 2, 3)).save(r)
    (tmp_path / "front.md").write_text(REQUEST + "\n", encoding="utf-8")
    out = tmp_path / "work/gen/front-1.png"
    out.parent.mkdir(parents=True)
    log, pid = tmp_path / "calls.jsonl", tmp_path / "pids/codex_image/hut.pid"

    def run(mode="ok", found=True, size=None, timeout=None):
        env = {**os.environ, "FAKE_CODEX_MODE": mode, "FAKE_CODEX_LOG": str(log), "FAKE_CODEX_PID_FILE": str(pid),
               "CODEX_HOME": str(tmp_path / "codex-home"),
               "PATH": path if found else "/usr/bin:/bin"}
        args = [sys.executable, str(GEN), "--model", "gpt-6-astra", "--reasoning", "medium", "--pid-file", str(pid),
                "--prompt", str(tmp_path / "front.md"), *[f"--image={r}" for r in refs], "--out", str(out),
                *(["--size", size] if size else []), *(["--timeout", str(timeout)] if timeout else [])]
        p = subprocess.run(args, capture_output=True, text=True, env=env)
        calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        rec = out.with_suffix(".json")
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr, "calls": calls,
                "record": json.loads(rec.read_text()) if rec.exists() else None}
    run.tmp, run.out, run.refs, run.pid = tmp_path, out, refs, pid
    return run


def test_one_call_runs_codex_exec_with_the_preset_model_and_refs_and_saves_the_image_where_the_frame_says(gen):
    r = gen()
    assert r["rc"] == 0, r["out"]
    assert r["out"] == f"[gen_image_codex] ok 1536x1024 lần 1 -> {gen.out}\n"
    assert [c["argv"] for c in r["calls"]] == [[
        "exec", "-m", "gpt-6-astra", "-c", "model_reasoning_effort=medium", "-C", str(gen.out.parent),
        "-s", "workspace-write", "--skip-git-repo-check", f"--image={gen.refs[0]}", f"--image={gen.refs[1]}", "-"]]
    prompt = r["calls"][0]["prompt"]
    assert f"\nOUTPUT_PATH: {gen.out}\n" in prompt and "\nSIZE: 1536x1024\n" in prompt
    assert prompt.rstrip().endswith("REQUEST:\n" + REQUEST)
    with Image.open(gen.out) as im:
        assert im.size == (1536, 1024)
    assert {k: r["record"][k] for k in ("status", "attempts", "model", "reasoning", "size", "fallback", "errors")} == {
        "status": "ok", "attempts": 1, "model": "gpt-6-astra", "reasoning": "medium", "size": [1536, 1024],
        "fallback": False, "errors": []}
    assert r["record"]["images"] == [str(x) for x in gen.refs]


def test_three_technical_failures_in_a_row_stop_with_exit_1_and_no_fourth_paid_call(gen):
    r = gen("fail:5")
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 3, False)
    assert r["out"] == f"[gen_image_codex] fail 3/3: codex: quota exceeded -> {gen.out.with_suffix('.json')}\n"
    assert (r["record"]["status"], r["record"]["errors"]) == ("fail", ["codex: quota exceeded"] * 3)


def test_two_failures_then_an_image_passes_on_the_third_try(gen):
    r = gen("fail:2")
    assert (r["rc"], len(r["calls"]), r["record"]["attempts"]) == (0, 3, 3)


def test_an_image_with_a_long_side_of_1040_px_or_less_is_a_technical_failure(gen):
    r = gen("small")
    assert (r["rc"], len(r["calls"])) == (1, 3)
    assert r["record"]["errors"][0] == "ảnh 1024x1024, cạnh dài cần > 1040 px"


def test_relative_reference_paths_reach_codex_as_absolute_ones_because_codex_runs_in_the_out_folder(gen, monkeypatch):
    monkeypatch.chdir(gen.tmp)
    rel = [r.name for r in gen.refs]
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                        "--prompt", "front.md", *[f"--image={r}" for r in rel], "--out", "work/gen/front-1.png"],
                       capture_output=True, text=True, env={**os.environ, "PATH": fake_codex.install(gen.tmp / "bin"),
                                                            "FAKE_CODEX_LOG": str(gen.tmp / "rel.jsonl"),
                                                            "FAKE_CODEX_PID_FILE": str(gen.pid)})
    argv = json.loads((gen.tmp / "rel.jsonl").read_text().splitlines()[0])["argv"]
    assert (p.returncode, [a for a in argv if a.startswith("--image=")]) == (0, [f"--image={r}" for r in gen.refs])


def test_portrait_size_goes_into_the_frame_for_a_tall_object(gen):
    r = gen(size="1024x1536")
    assert r["rc"] == 0 and "\nSIZE: 1024x1536\n" in r["calls"][0]["prompt"]


def test_fallback_copies_the_newest_image_codex_saved_under_its_home_during_this_call(gen):
    r = gen("home")
    assert (r["rc"], r["record"]["fallback"]) == (0, True)
    with Image.open(gen.out) as im:
        assert im.getpixel((0, 0)) == (10, 120, 200)


def test_an_image_left_in_codex_home_before_the_call_is_never_taken_as_its_output(gen):
    old = gen.tmp / "codex-home/generated_images/old/img.png"
    old.parent.mkdir(parents=True)
    Image.new("RGB", (1536, 1024)).save(old)
    os.utime(old, (time.time() - 3600,) * 2)
    r = gen("none")
    assert (r["rc"], gen.out.exists(), r["record"]["errors"][0]) == (1, False, "không có file ảnh")


def test_missing_codex_cli_fails_at_once_because_a_retry_cannot_install_it(gen):
    r = gen(found=False)
    assert (r["rc"], r["calls"]) == (1, [])
    assert r["out"] == f"[gen_image_codex] fail: không thấy codex trên PATH -> {gen.out.with_suffix('.json')}\n"


def test_the_pid_file_holds_the_wrapper_pid_while_codex_runs_so_p_next_counts_the_codex_slot(gen):
    r = gen()
    c = r["calls"][0]
    assert (c["pid_file"], c["pid_name"]) == (str(c["ppid"]), f"hut-{c['ppid']}.pid")
    assert list(gen.pid.parent.glob("*.pid")) == []


def test_two_gens_of_one_asset_hold_two_pid_files_so_the_first_to_finish_does_not_free_the_other_slot(gen):
    env = {**os.environ, "PATH": fake_codex.install(gen.tmp / "bin"), "FAKE_CODEX_LOG": str(gen.tmp / "two.jsonl"),
           "FAKE_CODEX_PID_FILE": str(gen.pid), "CODEX_HOME": str(gen.tmp / "codex-home")}

    def spawn(name, secs):
        return subprocess.Popen([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                                 "--prompt", str(gen.tmp / "front.md"), "--out", str(gen.out.with_name(name))],
                                env={**env, "FAKE_CODEX_MODE": f"slow:{secs}"}, stdout=subprocess.PIPE, text=True)
    short, long = spawn("a.png", 1), spawn("b.png", 5)
    pids = lambda: sorted(p.name for p in gen.pid.parent.glob("*.pid"))
    deadline = time.time() + 10
    while len(pids()) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert pids() == sorted([f"hut-{short.pid}.pid", f"hut-{long.pid}.pid"])
    short.communicate()
    assert pids() == [f"hut-{long.pid}.pid"]
    long.communicate()
    assert (short.returncode, long.returncode, pids()) == (0, 0, [])


def test_a_codex_reported_error_is_never_overridden_by_another_assets_newer_image_under_codex_home(gen):
    r = gen("error_with_bystander")
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 3, False)
    assert r["record"]["errors"] == ["codex: content policy"] * 3 and r["record"]["fallback"] is False


def test_two_new_images_under_codex_home_are_ambiguous_so_the_fallback_takes_neither(gen):
    r = gen("home_two")
    assert (r["rc"], gen.out.exists(), r["record"]["errors"][0]) == (1, False, "không có file ảnh")


def test_a_timeout_after_codex_saved_the_image_takes_it_instead_of_paying_for_two_more_tries(gen):
    r = gen("hang_after_image", timeout=3)
    assert (r["rc"], len(r["calls"]), r["record"]["attempts"], r["record"]["fallback"]) == (0, 1, 1, True)
    with Image.open(gen.out) as im:
        assert im.getpixel((0, 0)) == (10, 120, 200)


def test_a_timeout_without_any_image_is_a_failed_try_with_the_wait_in_the_message(gen):
    r = gen("slow:60", timeout=1)
    assert (r["rc"], len(r["calls"]), r["record"]["errors"][0]) == (1, 3, "hết thời gian chờ 1 s")


def test_a_valid_out_image_is_accepted_even_if_result_json_also_carries_an_error_field_since_the_paid_image_is_good(gen):
    r = gen("ok_but_error")
    assert (r["rc"], len(r["calls"]), r["record"]["fallback"], r["record"]["errors"]) == (0, 1, False, [])
    with Image.open(gen.out) as im:
        assert im.getpixel((0, 0)) == (200, 120, 10)


def test_a_truncated_png_is_a_broken_image_because_pillow_reads_only_the_header_on_open(gen):
    r = gen("truncated")
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 3, False)
    assert r["record"]["errors"] == ["file ảnh hỏng"] * 3
