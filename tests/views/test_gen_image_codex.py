"""gen_image_codex.py (D8.3, D15.1, D18) against a fake `codex` on PATH: the real one costs Codex usage."""
import contextlib
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

    def run(mode="ok", found=True, size=None, timeout=None, keys=None, extra=()):
        env = {**os.environ, **(keys or {}), "FAKE_CODEX_MODE": mode, "FAKE_CODEX_LOG": str(log), "FAKE_CODEX_PID_FILE": str(pid),
               "CODEX_HOME": str(tmp_path / "codex-home"),
               "PATH": path if found else "/usr/bin:/bin"}
        args = [sys.executable, str(GEN), "--model", "gpt-6-astra", "--reasoning", "medium", "--pid-file", str(pid),
                "--prompt", str(tmp_path / "front.md"), *[f"--image={r}" for r in refs], "--out", str(out),
                *(["--size", size] if size else []), *(["--timeout", str(timeout)] if timeout else []), *extra]
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


def test_codex_gets_no_api_key_of_another_service_so_a_meshy_key_never_reaches_the_image_agent(gen):
    r = gen(keys={"MESHY_API_KEY": "msy-shell-9876543210", "TRIPO_API_KEY": "tsk-1", "OPENAI_API_KEY": "sk-test"})
    assert (r["rc"], [c["api_keys"] for c in r["calls"]]) == (0, [["OPENAI_API_KEY"]])


def test_three_technical_failures_in_a_row_stop_with_exit_1_and_no_fourth_paid_call(gen):
    r = gen("fail:5")
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 3, False)
    assert r["out"] == f"[gen_image_codex] fail 3/3: codex: internal error -> {gen.out.with_suffix('.json')}\n"
    assert (r["record"]["status"], r["record"]["errors"]) == ("fail", ["codex: internal error"] * 3)


def test_two_failures_then_an_image_passes_on_the_third_try(gen):
    r = gen("fail:2")
    assert (r["rc"], len(r["calls"]), r["record"]["attempts"]) == (0, 3, 3)


def test_an_image_with_a_long_side_of_1040_px_or_less_is_a_technical_failure(gen):
    r = gen("small")
    assert (r["rc"], len(r["calls"])) == (1, 3)
    assert r["record"]["errors"][0] == "ảnh 1024x1024, cạnh dài cần > 1040 px"


def test_relative_reference_paths_reach_codex_as_absolute_ones_because_codex_runs_in_the_out_folder(gen, monkeypatch):
    monkeypatch.chdir(gen.tmp)
    (gen.tmp / "production").mkdir()
    (gen.tmp / "production/pipeline.toml").touch()
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
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 2, False)
    assert r["record"]["errors"] == ["codex: content policy"] * 2 and r["record"]["fallback"] is False


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


def gen_in_version(tmp_path, model=None, version=None, extra=()):
    """A gen whose --out lies in a version folder of a Producer root, as the views and texture briefs give it."""
    path = fake_codex.install(tmp_path / "bin")
    root = tmp_path / "production"
    st = {"id": "hut", "inputs": {"views_front": {"v2": {"profile": "786cfc66bdd2"}}}}
    (root / "assets/hut").mkdir(parents=True)
    (root / "pipeline.toml").touch()
    (root / "assets/hut/status.json").write_text(json.dumps(st), encoding="utf-8")
    out = root / "assets/hut/views_front/v2/work/gen/front-1.png"
    out.parent.mkdir(parents=True)
    ref = tmp_path / "ref.png"
    Image.new("RGB", (64, 64)).save(ref)
    (tmp_path / "front.md").write_text(REQUEST, encoding="utf-8")
    env = {**os.environ, "FAKE_CODEX_LOG": str(tmp_path / "calls.jsonl"), "PATH": path,
           "FAKE_CODEX_PID_FILE": str(root / "pids/codex_image/hut.pid"), "CODEX_HOME": str(tmp_path / "codex-home"),
           **({"FAKE_CODEX_MODEL": model} if model else {}), **({"FAKE_CODEX_VERSION": version} if version else {})}
    env.pop("PRODUCER_ROOT", None)
    p = subprocess.run([sys.executable, str(GEN), "--model", "gpt-6-astra", "--reasoning", "medium", "--pid-file",
                        str(root / "pids/codex_image/hut.pid"), "--prompt", str(tmp_path / "front.md"),
                        f"--image={ref}", "--out", str(out), *extra], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    rec = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    inp = json.loads((root / "assets/hut/status.json").read_text(encoding="utf-8"))["inputs"]["views_front"]["v2"]
    return rec, inp, (root / "ledger.md").read_text(encoding="utf-8").splitlines()


def test_the_ledger_and_the_version_inputs_keep_the_requested_and_the_actual_image_model_d28_1(tmp_path):
    """Image models change over time (D28): a version must say which model made its images, so a later comparison
    does not mix models. The actual model is what `codex exec` reports, not what the brief asked for."""
    rec, inp, led = gen_in_version(tmp_path, "gpt-6-astra-2026-11")
    assert (rec["model_requested"], rec["model_actual"]) == ("gpt-6-astra", "gpt-6-astra-2026-11")
    assert inp == {"profile": "786cfc66bdd2", "image_model_requested": "gpt-6-astra",
                   "image_model_actual": "gpt-6-astra-2026-11"}
    assert [l.split(" · ", 2)[2] for l in led] == [
        "hut · views_front v2 · gen ảnh front-1.png: model yêu cầu gpt-6-astra · model thực tế gpt-6-astra-2026-11"
        " · codex-cli 0.164.0"]


def test_without_a_model_line_from_codex_the_actual_model_is_no_number_never_the_requested_one(tmp_path):
    rec, inp, led = gen_in_version(tmp_path)
    assert (rec["model_actual"], inp["image_model_actual"]) == ("không có số", "không có số")
    assert led[0].endswith(" · gen ảnh front-1.png: model yêu cầu gpt-6-astra · model thực tế không có số · codex-cli 0.164.0")


def test_each_gen_keeps_the_codex_cli_version_in_its_record_and_the_ledger_d30_19(tmp_path):
    """codex-cli changes flags between versions (0.164.0 dropped --full-auto): a gen that broke after an upgrade must
    show which version made it."""
    rec, inp, led = gen_in_version(tmp_path, version="codex-cli 0.171.2")
    assert (rec["codex_cli"], led[0].rsplit(" · ", 1)[1]) == ("0.171.2", "codex-cli 0.171.2")
    assert "codex_cli" not in inp


def test_every_flag_of_the_gen_command_is_one_that_preflight_checks_in_codex_exec_help(gen):
    """P preflight checks gen_image_codex.FLAGS against `codex exec --help`; a flag outside that list would pass
    preflight and still fail every gen on a codex-cli without it."""
    import gen_image_codex
    argv = gen()["calls"][0]["argv"]
    assert sorted({x.split("=", 1)[0] for x in argv if x.startswith("-") and x != "-"}) == sorted(gen_image_codex.FLAGS)


def test_a_broken_status_json_only_warns_because_the_image_is_already_paid_for(tmp_path):
    path = fake_codex.install(tmp_path / "bin")
    out = tmp_path / "production/assets/hut/views_front/v1/work/gen/front-1.png"
    out.parent.mkdir(parents=True)
    (tmp_path / "production/pipeline.toml").touch()
    (tmp_path / "production/assets/hut/status.json").write_text("{broken", encoding="utf-8")
    ref = tmp_path / "ref.png"
    Image.new("RGB", (64, 64)).save(ref)
    (tmp_path / "front.md").write_text(REQUEST, encoding="utf-8")
    env = {**os.environ, "FAKE_CODEX_LOG": str(tmp_path / "calls.jsonl"), "PATH": path,
           "FAKE_CODEX_PID_FILE": str(tmp_path / "hut.pid"), "CODEX_HOME": str(tmp_path / "codex-home")}
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file",
                        str(tmp_path / "hut.pid"), "--prompt", str(tmp_path / "front.md"), f"--image={ref}", "--out",
                        str(out)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert (p.returncode, out.is_file(), "không ghi được model" in p.stderr) == (0, True, True)


FORBIDDEN = ("--full-auto", "--approve-for-me", "--dangerously-bypass-approvals-and-sandbox")


def test_the_default_gen_command_has_no_flag_that_lifts_the_sandbox_or_approves_for_the_user_d30_18(gen):
    """codex-cli 0.164.0 removed --full-auto (it exits 2), and --approve-for-me approves every permission request by
    itself (D30.21). A default command with either one breaks every gen or hands the user's approval away."""
    r = gen()
    assert r["rc"] == 0, r["out"]
    assert [f for f in FORBIDDEN for c in r["calls"] if f in c["argv"]] == []
    assert r["record"]["approve_for_me"] is None


def test_no_shipped_file_names_the_removed_full_auto_flag(tmp_path):
    """A doc or brief that still says --full-auto makes an agent type a command that codex-cli 0.164.0 refuses."""
    repo = Path(__file__).resolve().parents[2]
    hits = [str(p.relative_to(repo)) for d in ("src", "editions") for p in (repo / d).rglob("*")
            if p.is_file() and ".deps" not in p.parts and p.suffix in (".py", ".md", ".json", ".toml", ".yaml", ".sh")
            and "--full-auto" in p.read_text(encoding="utf-8", errors="replace")]
    assert hits == []


def gen_many(gen, names, mode="ok", extra=(), env=None):
    """One run of the script with a --prompt/--out pair per name; the prompts sit beside the fixture's front.md."""
    log = gen.tmp / "many.jsonl"
    env = {**os.environ, "FAKE_CODEX_MODE": mode, "FAKE_CODEX_LOG": str(log), "FAKE_CODEX_PID_FILE": str(gen.pid),
           "CODEX_HOME": str(gen.tmp / "codex-home"), "PATH": fake_codex.install(gen.tmp / "bin"), **(env or {})}
    pairs = []
    for n in names:
        (gen.tmp / f"{n}.md").write_text(f"Paint the {n} view.\n", encoding="utf-8")
        pairs += ["--prompt", str(gen.tmp / f"{n}.md"), "--out", str(gen.out.with_name(f"{n}.png"))]
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                        *[f"--image={r}" for r in gen.refs], *pairs, *extra], capture_output=True, text=True, env=env)
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    recs = {n: json.loads(gen.out.with_name(f"{n}.json").read_text()) for n in names}
    return p, calls, recs


def test_one_broken_file_of_three_is_the_only_one_made_again_d30_20(gen):
    """Each image costs Codex usage: a cut-off PNG for one view must not pay again for the two good ones."""
    p, calls, recs = gen_many(gen, ["front", "left", "back"], "break_once:left.png")
    assert p.returncode == 0, p.stdout
    assert [c["outs"] for c in calls] == [["front.png"], ["left.png"], ["back.png"], ["left.png"]]
    assert {n: (r["status"], r["attempts"], r["errors"]) for n, r in recs.items()} == {
        "front": ("ok", 1, []), "left": ("ok", 2, ["file ảnh hỏng"]), "back": ("ok", 1, [])}
    assert p.stdout.splitlines()[1] == f"[gen_image_codex] ok 1536x1024 lần 2 -> {gen.out.with_name('left.png')}"


def test_a_missing_file_is_made_again_alone_and_every_call_carries_the_same_reference_images(gen):
    p, calls, recs = gen_many(gen, ["front", "left"], "miss_once:front.png")
    assert (p.returncode, [c["outs"] for c in calls]) == (0, [["front.png"], ["left.png"], ["front.png"]])
    assert [c["images"] for c in calls] == [[str(r) for r in gen.refs]] * 3
    assert recs["front"]["errors"] == ["không có file ảnh"]


def test_a_file_that_keeps_failing_fails_alone_and_the_good_files_stay_but_the_run_exits_1(gen):
    """The worker reads exit 1 as BLOCKED; the good images stay on disk with their records, so a rerun of only the
    failed view is possible."""
    p, calls, recs = gen_many(gen, ["front", "left"], "fail_for:front.png")
    assert [c["outs"] for c in calls] == [["front.png"], ["left.png"], ["front.png"], ["front.png"]]
    assert {n: (r["status"], r["attempts"]) for n, r in recs.items()} == {"front": ("fail", 3), "left": ("ok", 1)}
    assert (p.returncode, p.stdout.splitlines()[0]) == (
        1, f"[gen_image_codex] fail 3/3: codex: internal error -> {gen.out.with_name('front.json')}")
    assert (gen.out.with_name("front.png").exists(), gen.out.with_name("left.png").exists()) == (False, True)


def test_a_jpeg_saved_under_a_png_name_is_converted_to_png_and_accepted_since_the_image_is_paid_for_v11(gen):
    """The next tools read <name>.png as PNG, so the bytes must be PNG. A JPEG that Pillow reads is a good image with
    the wrong container: converting costs nothing, a second Codex call costs usage. This replaces the D18 rule that
    counted it as a failed try."""
    r = gen("jpeg")
    assert (r["rc"], len(r["calls"]), r["record"]["errors"], r["record"]["converted"]) == (0, 1, [], True)
    assert gen.out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(gen.out) as im:
        assert (im.format, im.size) == ("PNG", (1536, 1024))
        assert all(abs(got - want) <= 3 for got, want in zip(im.getpixel((5, 5)), (200, 120, 10)))


def test_a_file_without_a_png_header_that_pillow_cannot_read_is_still_a_broken_image_v11(gen):
    r = gen("not_an_image")
    assert (r["rc"], len(r["calls"]), r["record"]["errors"], r["record"]["converted"]) == (1, 3, ["file ảnh hỏng"] * 3, False)


@pytest.mark.parametrize("error", ["quota exceeded", "Rate limit reached for gpt-image", "429 Too Many Requests",
                                   "You have hit your usage limit"])
def test_a_quota_or_rate_limit_error_stops_after_one_paid_call_because_a_retry_cannot_pass_v12(gen, error):
    """kit gen-craft: stop at once on a quota error. D8.3 retried 3 times, paying the same refusal 3 times."""
    r = gen("fail:5", extra=(), keys={"FAKE_CODEX_ERROR": error})
    assert (r["rc"], len(r["calls"]), gen.out.exists()) == (1, 1, False)
    assert r["record"]["errors"] == [f"codex: {error}"] and r["record"]["attempts"] == 1
    assert r["out"] == f"[gen_image_codex] fail 1/1: codex: {error} -> {gen.out.with_suffix('.json')}\n"


def test_a_quota_error_on_one_file_stops_the_files_still_waiting_because_the_quota_is_shared_v12(gen):
    p, calls, recs = gen_many(gen, ["front", "left", "back"], "fail_for:front.png", env={"FAKE_CODEX_ERROR": "quota exceeded"})
    assert (p.returncode, [c["outs"] for c in calls]) == (1, [["front.png"]])
    assert {n: (r["status"], r["attempts"]) for n, r in recs.items()} == {
        "front": ("fail", 1), "left": ("fail", 0), "back": ("fail", 0)}
    assert recs["left"]["errors"] == ["không gọi: codex hết quota ở file khác"]


def test_a_policy_error_is_tried_at_most_one_more_time_v12(gen):
    r = gen("fail:5", keys={"FAKE_CODEX_ERROR": "Content policy violation"})
    assert (r["rc"], len(r["calls"]), r["record"]["errors"]) == (1, 2, ["codex: Content policy violation"] * 2)
    assert r["out"] == f"[gen_image_codex] fail 2/2: codex: Content policy violation -> {gen.out.with_suffix('.json')}\n"


def test_a_policy_error_that_passes_on_the_retry_is_accepted_v12(gen):
    r = gen("fail:1", keys={"FAKE_CODEX_ERROR": "request blocked by safety system"})
    assert (r["rc"], len(r["calls"]), r["record"]["attempts"]) == (0, 2, 2)


def test_a_quota_text_in_the_stderr_tail_of_a_codex_that_wrote_no_file_also_stops_v12(gen):
    r = gen("ok", keys={"FAKE_CODEX_STDERR": "ERROR: Quota exceeded. Check your plan"})
    assert (r["rc"], len(r["calls"])) == (1, 1)


def test_the_codex_home_fallback_saves_a_jpeg_as_png_so_the_header_check_passes(gen):
    r = gen("home_jpeg")
    assert (r["rc"], r["record"]["fallback"], gen.out.read_bytes()[:8]) == (0, True, b"\x89PNG\r\n\x1a\n")


def test_each_prompt_needs_its_own_out_so_no_image_is_saved_under_the_wrong_name(gen):
    (gen.tmp / "b.md").write_text("x", encoding="utf-8")
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                        "--prompt", str(gen.tmp / "front.md"), "--prompt", str(gen.tmp / "b.md"), "--out", str(gen.out)],
                       capture_output=True, text=True, env={**os.environ, "PATH": fake_codex.install(gen.tmp / "bin")})
    assert (p.returncode, p.stderr.splitlines()[-1]) == (
        2, "gen_image_codex.py: error: mỗi --out cần đúng một --prompt, cùng thứ tự")


BLOCKED = "codex xin quyền ghi ngoài workspace-write, không ai duyệt trong codex exec"


def test_approve_for_me_reaches_codex_only_with_a_reason_and_the_ledger_keeps_that_reason_d30_21(tmp_path):
    """--approve-for-me lets Codex approve its own permission requests. A later reader of the ledger must see each gen
    that ran with it and why, or a lifted guard looks like a normal run."""
    rec, inp, led = gen_in_version(tmp_path, extra=("--approve-for-me", BLOCKED))
    argv = json.loads((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()[0])["argv"]
    assert argv[9:11] == ["--skip-git-repo-check", "--approve-for-me"]
    assert rec["approve_for_me"] == BLOCKED
    assert led[0].endswith(f" · codex-cli 0.164.0 · --approve-for-me: {BLOCKED}")


@pytest.mark.parametrize("reason", ["", "   "])
def test_approve_for_me_without_a_reason_is_refused_before_any_codex_call(gen, reason):
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                        "--prompt", str(gen.tmp / "front.md"), "--out", str(gen.out), "--approve-for-me", reason],
                       capture_output=True, text=True, env={**os.environ, "PATH": fake_codex.install(gen.tmp / "bin"),
                                                            "FAKE_CODEX_LOG": str(gen.tmp / "none.jsonl")})
    assert (p.returncode, p.stderr.splitlines()[-1], (gen.tmp / "none.jsonl").exists()) == (
        2, "gen_image_codex.py: error: --approve-for-me cần lý do: lần gọi trước bị chặn ở đâu", False)


def test_without_batch_each_paint_view_is_its_own_codex_call_d30_22(gen):
    """Batching is off by default: one call per image keeps the references of one view out of the others."""
    p, calls, recs = gen_many(gen, ["paint_1", "paint_2", "paint_3"])
    assert (p.returncode, [c["outs"] for c in calls]) == (0, [["paint_1.png"], ["paint_2.png"], ["paint_3.png"]])
    assert [r["batch"] for r in recs.values()] == [False] * 3


def test_with_batch_the_views_go_in_one_call_with_every_shared_reference_and_each_file_is_checked(gen):
    """D30.22: about 11.7 s of overhead per call; one call for the views that share the references saves it. The
    files are still checked one by one."""
    p, calls, recs = gen_many(gen, ["paint_1", "paint_2", "paint_3"], extra=["--batch"])
    assert p.returncode == 0, p.stdout
    assert [c["outs"] for c in calls] == [["paint_1.png", "paint_2.png", "paint_3.png"]]
    assert calls[0]["images"] == [str(r) for r in gen.refs]
    assert [f"JOB {k}\n" in calls[0]["prompt"] for k in (1, 2, 3)] == [True] * 3
    assert {n: (r["status"], r["attempts"], r["batch"]) for n, r in recs.items()} == {
        n: ("ok", 1, True) for n in ("paint_1", "paint_2", "paint_3")}


def test_with_batch_one_broken_file_of_three_is_asked_for_again_alone(gen):
    p, calls, recs = gen_many(gen, ["paint_1", "paint_2", "paint_3"], "break_once:paint_2.png", extra=["--batch"])
    assert (p.returncode, [c["outs"] for c in calls]) == (
        0, [["paint_1.png", "paint_2.png", "paint_3.png"], ["paint_2.png"]])
    assert [recs[n]["attempts"] for n in ("paint_1", "paint_2", "paint_3")] == [1, 2, 1]


def test_with_batch_a_new_image_under_codex_home_is_never_given_to_one_of_several_missing_files(gen):
    """Codex saved one image but wrote none of the outputs: no rule maps it to one job, so the fallback waits for a
    call with one job."""
    p, calls, recs = gen_many(gen, ["paint_1", "paint_2"], "home", extra=["--batch"])
    assert [c["outs"] for c in calls][:2] == [["paint_1.png", "paint_2.png"], ["paint_1.png", "paint_2.png"]]
    assert (p.returncode, [r["fallback"] for r in recs.values()]) == (1, [False, False])


def test_batch_refuses_outputs_in_two_folders_because_codex_exec_opens_one_working_folder(gen):
    (gen.tmp / "a.md").write_text("x", encoding="utf-8")
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(gen.pid),
                        "--prompt", str(gen.tmp / "a.md"), "--out", str(gen.tmp / "x/a.png"),
                        "--prompt", str(gen.tmp / "a.md"), "--out", str(gen.tmp / "y/a.png"), "--batch"],
                       capture_output=True, text=True, env={**os.environ, "PATH": fake_codex.install(gen.tmp / "bin")})
    assert (p.returncode, p.stderr.splitlines()[-1]) == (
        2, "gen_image_codex.py: error: --batch cần mọi --out trong cùng một thư mục: codex exec -C chỉ mở một thư mục")


def test_the_fake_parser_logs_every_image_of_one_i_flag_and_of_each_equals_form(gen):
    """The help of codex-cli 0.164.0 says `-i, --image <FILE>...`: one flag may carry several files. The fake logs
    both forms, so a batch test sees every reference the call attached."""
    assert fake_codex.image_args(["-i", "a.png", "b.png", "--skip-git-repo-check", "--image=c.png", "-"]) == [
        "a.png", "b.png", "c.png"]


def test_no_new_codex_call_starts_when_it_could_end_after_the_total_cap_so_the_run_ends_before_the_bash_limit_d33_3(gen):
    """Run 5 had no Bash call cut, but 3 tries of 900 s per file outlast any Bash timeout. With --wall-s 2 and 1 s per
    call, the second try could end after 2 s: it never starts, and the record says why."""
    r = gen("slow:60", timeout=1, extra=("--wall-s", "2"))
    assert (r["rc"], len(r["calls"])) == (1, 1)
    assert r["record"]["errors"] == ["hết thời gian chờ 1 s", "hết thời gian tổng 2 s (D33.3): không gọi thêm"]


def test_the_fallback_takes_only_an_image_of_this_calls_own_session_folder_v1(gen):
    """Another asset's Codex run saves under its own session folder in the same CODEX_HOME. Taking the one new image
    there puts the wrong asset's art into this view."""
    r = gen("other_session", keys={"FAKE_CODEX_SESSION": "mine"})
    assert (r["rc"], gen.out.exists(), r["record"]["errors"][0], r["record"]["fallback"]) == (
        1, False, "không có file ảnh", False)


def test_with_the_session_id_known_the_fallback_ignores_other_sessions_even_when_both_images_are_new_v1(gen):
    r = gen("own_and_other_session", keys={"FAKE_CODEX_SESSION": "mine"})
    assert (r["rc"], r["record"]["fallback"], r["record"]["session"]) == (0, True, "mine")
    with Image.open(gen.out) as im:
        assert im.getpixel((0, 0)) == (10, 120, 200)


def test_the_session_id_is_read_from_the_codex_exec_header_on_stderr_v1():
    import gen_image_codex
    header = "OpenAI Codex v0.164.0\n--------\nworkdir: /x\nmodel: gpt-6\nsession id: 0199-abc\n--------\n"
    assert (gen_image_codex.session_id(header), gen_image_codex.session_id("model: gpt-6\n"),
            gen_image_codex.session_id(None)) == ("0199-abc", None, None)


def test_without_a_session_id_the_fallback_waits_while_another_codex_image_run_is_alive_v1(gen):
    """No id to tell the runs apart: an image that appears while a second run is alive may be the second run's."""
    other = subprocess.Popen(["sleep", "60"])
    try:
        gen.pid.parent.mkdir(parents=True, exist_ok=True)
        (gen.pid.parent / f"other-{other.pid}.pid").write_text(str(other.pid), encoding="utf-8")
        r = gen("home")
    finally:
        other.kill()
        other.wait()
    assert (r["rc"], gen.out.exists(), r["record"]["fallback"], r["record"]["errors"][0]) == (
        1, False, False, "không có file ảnh")


def test_without_a_session_id_a_pid_file_of_a_dead_run_does_not_block_the_fallback_v1(gen):
    dead = subprocess.Popen(["true"])
    dead.wait()
    gen.pid.parent.mkdir(parents=True, exist_ok=True)
    (gen.pid.parent / f"old-{dead.pid}.pid").write_text(str(dead.pid), encoding="utf-8")
    r = gen("home")
    assert (r["rc"], r["record"]["fallback"]) == (0, True)


def test_only_text_from_codex_is_classified_so_a_429_s_timeout_is_not_a_quota_error_v12():
    import gen_image_codex
    assert [gen_image_codex.error_kind(e) for e in (
        "hết thời gian chờ 429 s", "hết thời gian tổng 429 s (D33.3): không gọi thêm", "codex: rate limit reached",
        "không có file ảnh (codex exit 1: Quota exceeded)", "file ảnh hỏng", "codex: content policy")] == [
        None, None, "quota", "quota", None, "policy"]


PARALLEL_SECS = 3


@contextlib.contextmanager
def other_runs(count):
    """`count` live processes, each as the pid file of another run in the codex_image folder."""
    procs = [subprocess.Popen(["sleep", "60"]) for _ in range(count)]
    try:
        yield procs
    finally:
        for h in procs:
            h.kill()
            h.wait()


def gen_slots(tmp_path, names, limit=2, mode="ok", delay=None, holders=(), keys=None, extra=()):
    """A run of the script in a project root whose pipeline.toml allows `limit` codex_image slots; each of `holders`
    is a live process with a pid file of another run. Returns the process, the logged calls, the records, the seconds,
    and the pid file name the brief would give."""
    root = tmp_path / "production"
    (root / "pids/codex_image").mkdir(parents=True)
    (root / "pipeline.toml").write_text(f"[limits]\ncodex_image = {limit}\n" if limit else "", encoding="utf-8")
    for h in holders:
        (root / "pids/codex_image" / f"other-{h.pid}.pid").write_text(str(h.pid), encoding="utf-8")
    ref = tmp_path / "ref.png"
    Image.new("RGB", (64, 64)).save(ref)
    pairs, outs = [], {}
    for n in names:
        (tmp_path / f"{n}.md").write_text(f"Paint the {n} view.\n", encoding="utf-8")
        outs[n] = root / f"assets/hut/views/v1/work/gen/{n}.png"
        outs[n].parent.mkdir(parents=True, exist_ok=True)
        pairs += ["--prompt", str(tmp_path / f"{n}.md"), "--out", str(outs[n])]
    log, pid = tmp_path / "calls.jsonl", root / "pids/codex_image/hut.pid"
    env = {**os.environ, "FAKE_CODEX_MODE": mode, "FAKE_CODEX_LOG": str(log), "FAKE_CODEX_PID_FILE": str(pid),
           "CODEX_HOME": str(tmp_path / "codex-home"), "PATH": fake_codex.install(tmp_path / "bin"),
           **({"FAKE_CODEX_DELAY": delay} if delay else {}), **(keys or {})}
    env.pop("PRODUCER_ROOT", None)
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, str(GEN), "--model", "m", "--reasoning", "low", "--pid-file", str(pid),
                        f"--image={ref}", *pairs, *extra], capture_output=True, text=True, env=env, cwd=tmp_path)
    secs = time.monotonic() - t0
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    recs = {n: json.loads(o.with_suffix(".json").read_text()) for n, o in outs.items()}
    return p, calls, recs, secs, pid


def test_two_jobs_with_two_free_slots_finish_in_about_the_time_of_one_call_so_the_step_does_not_wait_n_times(tmp_path):
    """The views of one step are independent images. Run one after another, a 4-view step costs 4 call times; with the
    free codex_image slots it costs about one. The pid files show that each call holds its own slot."""
    p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, delay=f"*:{PARALLEL_SECS}")
    print(f"L8 two jobs, two free slots: {secs:.2f} s for {PARALLEL_SECS} s calls")
    assert p.returncode == 0, p.stdout
    assert secs < 1.6 * PARALLEL_SECS, secs
    assert sorted(c["outs"][0] for c in calls) == ["back.png", "left.png"]
    assert {len(c["pid_names"]) for c in calls} == {2}
    assert {n: r["status"] for n, r in recs.items()} == {"back": "ok", "left": "ok"}
    assert list(pid.parent.glob("*.pid")) == []


def test_with_one_free_slot_two_jobs_run_one_after_the_other_because_the_other_slot_belongs_to_another_run(tmp_path):
    with other_runs(1) as holders:
        p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, delay=f"*:{PARALLEL_SECS}",
                                              holders=holders)
        print(f"L8 two jobs, one free slot: {secs:.2f} s for {PARALLEL_SECS} s calls")
        assert [f.name for f in pid.parent.glob("*.pid")] == [f"other-{holders[0].pid}.pid"]
    assert p.returncode == 0, p.stdout
    assert secs > 1.8 * PARALLEL_SECS, secs
    assert {len(c["pid_names"]) for c in calls} == {1}


def test_with_no_slot_free_the_run_still_makes_one_call_at_a_time_because_it_needs_at_least_one(tmp_path):
    with other_runs(2) as holders:
        p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, holders=holders)
    assert (p.returncode, [c["outs"] for c in calls]) == (0, [["back.png"], ["left.png"]])


def test_without_a_codex_image_limit_in_pipeline_toml_the_jobs_run_one_after_the_other(tmp_path):
    p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=None, delay=f"*:{PARALLEL_SECS}")
    assert (p.returncode, [c["outs"] for c in calls]) == (0, [["back.png"], ["left.png"]])
    assert secs > 1.8 * PARALLEL_SECS, secs


def test_a_quota_error_in_one_thread_stops_the_job_that_has_not_started_but_not_the_call_in_flight(tmp_path):
    """The quota is shared by every file: a third job must not pay for a refusal that is already known. The call that
    already runs holds a paid image, so it is kept."""
    p, calls, recs, secs, pid = gen_slots(
        tmp_path, ["front", "left", "back"], limit=2, mode="fail_for:front.png", delay="left.png:2",
        keys={"FAKE_CODEX_ERROR": "quota exceeded"})
    assert p.returncode == 1
    assert sorted(c["outs"][0] for c in calls) == ["front.png", "left.png"]
    assert {n: (r["status"], r["attempts"]) for n, r in recs.items()} == {
        "front": ("fail", 1), "left": ("ok", 1), "back": ("fail", 0)}
    assert recs["back"]["errors"] == ["không gọi: codex hết quota ở file khác"]
    assert list(pid.parent.glob("*.pid")) == []


def test_each_thread_keeps_the_retry_of_its_own_file_so_one_broken_image_is_made_again_alone(tmp_path):
    p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, mode="break_once:left.png")
    assert p.returncode == 0, p.stdout
    assert sorted(c["outs"][0] for c in calls) == ["back.png", "left.png", "left.png"]
    assert {n: (r["attempts"], r["errors"]) for n, r in recs.items()} == {"back": (1, []), "left": (2, ["file ảnh hỏng"])}


def test_the_total_cap_still_applies_to_calls_in_threads(tmp_path):
    p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, mode="slow:60",
                                          extra=("--timeout", "1", "--wall-s", "2"))
    assert (p.returncode, len(calls)) == (1, 2)
    assert {r["errors"][-1] for r in recs.values()} == {"hết thời gian tổng 2 s (D33.3): không gọi thêm"}


def test_an_image_under_codex_home_is_never_taken_while_another_call_of_the_same_run_is_open(tmp_path):
    """No session id and two calls at once: the one new image may belong to the other call, so neither job takes it."""
    p, calls, recs, secs, pid = gen_slots(tmp_path, ["back", "left"], limit=2, mode="home", delay="*:1")
    assert p.returncode == 1
    assert {n: (r["status"], r["fallback"], r["errors"][0]) for n, r in recs.items()} == {
        n: ("fail", False, "không có file ảnh") for n in ("back", "left")}
