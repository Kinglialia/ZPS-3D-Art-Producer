"""producer.main(): one `LỖI:` line for bad user files, exit codes, and one writer at a time."""
import threading
from argparse import Namespace

import pytest

import producer
from core import intake
from core.state import ROOT, load_cfg, locked

AID = "house-a"


@pytest.fixture
def proj(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    intake.new(Namespace(id=AID, title="House A", type="asset", priority=2, deadline=None), load_cfg())
    capsys.readouterr()
    return tmp_path


def error_of(*argv):
    with pytest.raises(SystemExit) as e:
        producer.main(list(argv))
    return e.value.code


def test_a_corrupt_status_file_is_one_error_line_not_a_traceback(proj):
    (ROOT / f"assets/{AID}/status.json").write_text("{bad", encoding="utf-8")
    assert error_of("feedback", AID, "x") == (
        f"LỖI: production/assets/{AID}/status.json hỏng: "
        "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)")


def test_a_bad_pipeline_toml_is_one_error_line_not_a_traceback(proj):
    (ROOT / "pipeline.toml").write_text("[[steps\n", encoding="utf-8")
    assert error_of("next").startswith("LỖI: production/pipeline.toml sai cú pháp TOML: ")


def test_preflight_before_init_creates_the_production_folder_instead_of_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BLENDER", "")
    monkeypatch.setenv("PRODUCER_KIT", str(tmp_path / "none.py"))
    producer.main(["preflight"])
    assert capsys.readouterr().out.startswith("preflight: ") and (tmp_path / "production/preflight.json").is_file()


def test_validate_exits_1_on_problems_so_a_script_can_gate_on_it(proj, capsys):
    assert error_of("validate") == 1
    assert capsys.readouterr().out == ("art direction: chưa có README.md (brief sẽ ghi 'chưa có art direction')\n"
                                       "production/rubrics/building.md: chưa duyệt (status: draft)\n"
                                       "production/rubrics/default.md: chưa duyệt (status: draft)\n")


def test_validate_names_the_steps_a_gd1_asset_rubric_lacks_so_the_views_brief_never_points_at_nothing(proj, capsys):
    rub = ROOT / f"assets/{AID}/rubric.md"
    text = rub.read_text(encoding="utf-8")
    rub.write_text(text.split("## views_front")[0] + "## model" + text.split("## model", 1)[1], encoding="utf-8")
    assert error_of("validate") == 1
    assert capsys.readouterr().out.splitlines()[0] == (
        "house-a: rubric.md thiếu mục ## views_front, ## views_rest của bước đang bật (chép từ templates/rubrics/)")


def test_ledger_tail_0_prints_nothing_instead_of_the_whole_ledger(proj, capsys):
    producer.main(["ledger", "--tail", "0"])
    assert capsys.readouterr().out == "(trống)\n"


def test_new_after_a_crash_that_left_a_folder_without_status_creates_the_asset(proj, capsys):
    (ROOT / "assets/b-barn").mkdir()
    (ROOT / "assets/b-barn/brief.md").write_text("half", encoding="utf-8")
    producer.main(["new", "b-barn", "--title", "B Barn"])
    assert capsys.readouterr().out.startswith("OK b-barn → draft.")
    assert sorted(p.name for p in (ROOT / "assets/b-barn").iterdir()) == ["brief.md", "feedback.md", "rubric.md",
                                                                         "status.json"]
    assert (ROOT / "assets/b-barn/brief.md").read_text(encoding="utf-8").startswith("# Brief — B Barn")


def test_an_issues_handoff_from_a_step_outside_inputs_is_one_error_line_so_no_brief_quotes_an_unapproved_report(proj):
    p = ROOT / "pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('issues = ["model"]', 'issues = ["views_front", "assemble"]'),
                 encoding="utf-8")
    assert error_of("next") == "LỖI: step texture: issues assemble không nằm trong inputs của bước"


@pytest.mark.parametrize("pilot, line", [(None, "PILOT: none (pilot_asset: null): so với pilot ghi not_checked"),
                                         ("pilot-prop", "PILOT: deliver/pilot-prop/")])
def test_the_pilot_line_points_at_the_pilot_package_in_this_runtime_deliver_d22_10(proj, pilot, line):
    from core import briefs
    assert briefs.pilot_line({"pilot_asset": pilot}) == line


def test_a_mutating_command_waits_for_the_lock_so_two_writers_never_interleave(proj):
    t = threading.Thread(target=producer.main, args=(["feedback", AID, "ghi chú"],))
    with locked():
        t.start()
        t.join(0.3)
        assert t.is_alive(), "feedback ran while another writer held production/.lock"
    t.join(5)
    assert (ROOT / f"assets/{AID}/feedback.md").read_text(encoding="utf-8").splitlines()[-1].endswith(
        " · blockout · note · ghi chú")
