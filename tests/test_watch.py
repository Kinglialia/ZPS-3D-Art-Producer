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
