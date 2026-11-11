"""D33: no dead time between the Producer and its agents. Nobody waits on a notification; done or not is read from disk.
D33.18b: every test here uses synthetic jobs (a long command, a hung command), never an object."""
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
        assert "Không chạy lệnh nền" in text and "(D33.2)" in text, f.name
        assert "Ghi `<report>` là việc cuối cùng trước khi trả kết quả" in text and "(D33.8)" in text, f.name


def test_every_agent_file_caps_its_turns_so_a_looping_agent_stops_instead_of_running_on_d33_6():
    """`maxTurns` is an agent frontmatter key of Claude Code 2.1.318 ("Maximum number of agentic turns (API
    round-trips) before stopping"). Run 5 used 45 turns for a blockout worker and 12 for its reviewer, so the caps are
    about 8x those: a cap a normal run hits would stop good work. An agent cut by the cap writes no report; P on-stop
    records that and the stall rule takes over (D33.9, D33.11)."""
    import build
    caps = {f.stem: build.frontmatter(f.read_text(encoding="utf-8")).get("maxTurns") for f in ROLES}
    assert caps == {n: ("400" if n.startswith("zps-3dp-step") else "100") for n in caps}
