"""D33: no dead time between the Producer and its agents. Nobody waits on a notification; done or not is read from disk.
D33.18b: every test here uses synthetic jobs (a long command, a hung command), never an object."""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "src/zps-3dp-producer"
ROLES = sorted([*SKILL.glob("agents/zps-3dp-*.md"), *SKILL.glob("agents/*/zps-3dp-*.md")])


def test_no_role_file_tool_or_brief_template_ever_asks_for_a_background_command_d33_2():
    """A subagent that starts a background command and ends its turn is never woken (anthropics/claude-code #108836):
    the pipeline stands still until the user types. Nothing a worker or reviewer reads may offer that flag."""
    shipped = [p for p in [*SKILL.glob("agents/**/*.md"), *SKILL.glob("agents/**/*.py"), SKILL / "scripts/core/briefs.py",
                           SKILL / "scripts/core/texture.py"] if ".deps" not in p.parts]
    assert len(shipped) > 40
    assert [p.name for p in shipped if "run_in_background" in p.read_text(encoding="utf-8")] == []


def test_every_worker_and_reviewer_role_file_forbids_background_commands_and_writes_its_report_last_d33_2_d33_8():
    """The report file is the done signal (D33.8): written last, so a report on disk means the agent finished."""
    assert len(ROLES) == 9
    for f in ROLES:
        text = f.read_text(encoding="utf-8")
        assert "Không chạy lệnh nền" in text and "D33.2" in text, f.name
        assert "Ghi `<report>` là việc cuối cùng trước khi trả kết quả" in text and "(D33.8)" in text, f.name


def test_every_agent_file_caps_its_turns_so_a_looping_agent_stops_instead_of_running_on_d33_6():
    """`maxTurns` is an agent frontmatter key of Claude Code 2.1.318 ("Maximum number of agentic turns (API
    round-trips) before stopping"). Run 5 used 45 turns for a blockout worker and 12 for its reviewer, so the caps are
    about 8x those: a cap a normal run hits would stop good work. An agent cut by the cap writes no report; P on-stop
    records that and the stall rule takes over (D33.9, D33.11)."""
    import build
    caps = {f.stem: build.frontmatter(f.read_text(encoding="utf-8")).get("maxTurns") for f in ROLES}
    assert caps == {n: ("400" if n.startswith("zps-3dp-step") else "100") for n in caps}


def test_the_settings_snippet_raises_the_bash_timeouts_and_the_brief_asks_for_the_same_cap_d33_4():
    """Claude Code 2.1.318 reads BASH_DEFAULT_TIMEOUT_MS (default 120000) and BASH_MAX_TIMEOUT_MS (default 600000) from
    the environment; settings `env` sets them. A worker or the Producer asking Bash for more than the max gets less, so
    every role file and SKILL.md ask for exactly the max (the brief has no room: 4096-byte budget)."""
    import json
    env = json.loads((SKILL / "templates/settings.snippet.json").read_text(encoding="utf-8"))["env"]
    assert env == {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"}
    asks = [f"timeout: {env['BASH_MAX_TIMEOUT_MS']}` cho Bash" in f.read_text(encoding="utf-8")
            for f in ROLES if f.name.startswith("zps-3dp-step")]
    assert asks == [True] * 4 and f"`timeout` {env['BASH_MAX_TIMEOUT_MS']}" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_the_merge_adds_a_missing_timeout_and_never_changes_one_the_user_set_d33_4():
    import settings_merge as M
    want = {"env": {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"}, "permissions": {"allow": []},
            "hooks": {}}
    mine = {"env": {"BASH_DEFAULT_TIMEOUT_MS": "900000", "OTHER": "1"}}
    assert M.missing(mine, want)["env"] == {"BASH_MAX_TIMEOUT_MS": "3600000"}
    assert M.merge(mine, want)["env"] == {"BASH_DEFAULT_TIMEOUT_MS": "900000", "OTHER": "1",
                                          "BASH_MAX_TIMEOUT_MS": "3600000"}
    assert M.missing(M.merge(mine, want), want)["env"] == {}


def beats(tmp_path):
    vd = tmp_path / "production/assets/a1/stepx/v1"
    vd.mkdir(parents=True)
    return vd, lambda: [r.split(" · ")[1:3] for r in (vd / "heartbeat.log").read_text(encoding="utf-8").splitlines()]


def test_a_hung_child_writes_no_heartbeat_between_start_and_end_so_its_silence_shows_d33_7(tmp_path):
    """A heartbeat by the clock alone would let a hung process look alive (D33.7). `sleep` uses no CPU and prints
    nothing: only the start and the end lines."""
    import heartbeat
    vd, rows = beats(tmp_path)
    r = heartbeat.run(["sleep", "2.5"], tool="hung", vd=vd, every=0.5)
    assert r.returncode == 0 and rows() == [["hung", "start"], ["hung", "done"]]


def test_a_busy_child_keeps_beating_on_cpu_alone_so_a_long_silent_render_is_not_taken_for_stuck_d33_7(tmp_path):
    import heartbeat
    vd, rows = beats(tmp_path)
    busy = "import time\nt = time.time()\nwhile time.time() - t < 3:\n    pass\n"
    heartbeat.run([sys.executable, "-c", busy], tool="busy", vd=vd, every=0.7)
    got = rows()
    assert got[0] == ["busy", "start"] and got[-1] == ["busy", "done"]
    assert got[1:-1].count(["busy", "running"]) >= 2 and len(got) == got.count(["busy", "running"]) + 2


def test_a_child_that_only_prints_keeps_beating_on_output_growth_and_its_output_is_returned_d33_7(tmp_path):
    import heartbeat
    vd, rows = beats(tmp_path)
    r = heartbeat.run(["sh", "-c", "for i in 1 2 3 4 5 6; do echo line$i; sleep 0.4; done"], tool="talk", vd=vd,
                      every=0.6)
    assert r.stdout.split() == [f"line{i}" for i in range(1, 7)]
    assert rows().count(["talk", "running"]) >= 2


def test_a_timeout_kills_the_child_raises_as_subprocess_does_and_logs_it_d33_7(tmp_path):
    import heartbeat
    import pytest
    import subprocess
    vd, rows = beats(tmp_path)
    with pytest.raises(subprocess.TimeoutExpired):
        heartbeat.run(["sleep", "30"], tool="hang", vd=vd, timeout=1, every=0.5)
    assert rows() == [["hang", "start"], ["hang", "timeout"]]
    assert heartbeat.vdir_of(vd / "work/meshy/call-1") == vd and heartbeat.vdir_of(tmp_path / "x/v1") is None
