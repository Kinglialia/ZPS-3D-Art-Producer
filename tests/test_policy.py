from argparse import Namespace

import pytest
import yaml

from shared import run
from core import policy
from core.state import ProducerError

TEMPLATE = {"approvals": {"blockout": "human", "views_rest": "human", "model": "human"}, "review_board": "local",
            "delegations": [], "test_mode": False, "disk_warn_gb": 20}


@pytest.fixture
def prod(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "production").mkdir()
    (tmp_path / "production/ledger.md").write_text("", encoding="utf-8")
    return tmp_path / "production"


def setp(step, who, by="anh nói", confirm=False):
    policy.set_approval(Namespace(step=step, who=who, by=by, confirm_spend=confirm))


def test_missing_policy_file_means_template_defaults_so_a_new_project_asks_the_human(prod):
    assert policy.load() == TEMPLATE


def test_a_new_project_starts_outside_test_mode_so_the_producer_cannot_waive_findings_for_the_human(prod):
    assert policy.load()["test_mode"] is False


@pytest.mark.parametrize("key", ["views", "views_front", "assemble", "texture"])
def test_unknown_approvals_key_in_policy_file_is_refused_because_only_review_human_steps_have_a_choice(prod, key):
    (prod / "policy.yaml").write_text(yaml.safe_dump({"approvals": {key: "reviewer"}}), encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        policy.load()
    assert str(e.value) == f"production/policy.yaml: approvals.{key}: khóa không hợp lệ (blockout|views_rest|model)"


@pytest.mark.parametrize("text, error", [
    ("- a\n", "production/policy.yaml: phải là bảng `khóa: giá trị`, không phải list"),
    ("approvals: [a: b\n", "production/policy.yaml sai cú pháp YAML: "),
])
def test_a_policy_file_that_is_not_a_yaml_map_is_one_error_line_not_a_traceback(prod, text, error):
    (prod / "policy.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        policy.load()
    assert str(e.value).startswith(error)


def test_approvals_set_refuses_an_unknown_step_and_an_unknown_value(prod):
    with pytest.raises(ProducerError) as e:
        setp("assemble", "reviewer")
    assert str(e.value) == "assemble: khóa không hợp lệ (blockout|views_rest|model)"
    with pytest.raises(ProducerError) as e:
        setp("blockout", "ai")
    assert str(e.value) == "người duyệt phải là human|reviewer"
    assert not (prod / "policy.yaml").exists()


def test_model_reviewer_needs_confirm_spend_because_the_next_step_spends_meshy_credit(prod):
    with pytest.raises(ProducerError) as e:
        setp("model", "reviewer")
    assert str(e.value) == ("model: reviewer cần --confirm-spend: bước sau gọi Meshy (tốn credit) trên mesh vừa khóa. "
                            "Hỏi lại người dùng")
    setp("model", "reviewer", confirm=True)
    assert policy.load()["approvals"]["model"] == "reviewer"


def test_approvals_set_writes_the_file_prints_one_line_and_ledgers_the_words_of_the_human(prod, capsys):
    setp("blockout", "reviewer", by="blockout để reviewer duyệt")
    assert capsys.readouterr().out == "OK: approvals blockout=reviewer\n"
    assert yaml.safe_load((prod / "policy.yaml").read_text(encoding="utf-8")) == TEMPLATE | {
        "approvals": {"blockout": "reviewer", "views_rest": "human", "model": "human"}}
    assert "approvals blockout=reviewer · by: blockout để reviewer duyệt" in (prod / "ledger.md").read_text(encoding="utf-8")


def test_project_setup_sets_the_review_board_through_the_same_single_writer(prod, capsys):
    setp("review_board", "local+remote", by="dùng cả điện thoại")
    assert (capsys.readouterr().out, policy.load()["review_board"]) == ("OK: approvals review_board=local+remote\n",
                                                                        "local+remote")
    with pytest.raises(ProducerError) as e:
        setp("review_board", "remote")
    assert str(e.value) == "review_board phải là local|local+remote"


def test_delegate_model_also_needs_confirm_spend_because_it_spends_the_same_credit(prod):
    with pytest.raises(ProducerError) as e:
        policy.delegate(Namespace(step="model", ids=["house-a"], by="", confirm_spend=False))
    assert str(e.value).startswith("model: reviewer cần --confirm-spend")


def test_delegate_beats_approvals_and_approvals_beat_the_human_default(prod, capsys):
    pol = policy.load()
    assert policy.approver(pol, "blockout", "house-a") == "human"
    setp("blockout", "reviewer")
    assert policy.approver(policy.load(), "blockout", "house-a") == "policy"
    policy.delegate(Namespace(step="views_rest", ids=["house-a", "house-b"], by="lô này để reviewer", confirm_spend=False))
    assert capsys.readouterr().out.splitlines()[-1] == "OK: delegate views_rest → reviewer: house-a, house-b"
    pol = policy.load()
    assert [policy.approver(pol, "views_rest", a) for a in ("house-a", "house-c")] == ["delegate", "human"]
    assert pol["delegations"][0] | {"at": "-"} == {"step": "views_rest", "ids": ["house-a", "house-b"],
                                                   "by": "lô này để reviewer", "at": "-"}


def test_steps_without_a_policy_key_stay_with_the_human(prod):
    assert policy.approver(policy.load(), "assemble", "house-a") == "human"


def test_cli_approvals_and_delegate_print_one_line(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    assert run(tmp_path, "approvals", "set", "blockout", "reviewer", "--by", "ok") == "OK: approvals blockout=reviewer\n"
    assert run(tmp_path, "approvals", "set", "model", "reviewer", "--by", "ok", ok=False) == (
        "LỖI: model: reviewer cần --confirm-spend: bước sau gọi Meshy (tốn credit) trên mesh vừa khóa. "
        "Hỏi lại người dùng\n")
    assert run(tmp_path, "delegate", "blockout", "a", "b") == "OK: delegate blockout → reviewer: a, b\n"


def test_the_user_turns_test_mode_on_through_the_single_policy_writer_and_only_true_or_false_is_kept_d30_1(prod, capsys):
    setp("test_mode", "true", by="chạy thử wooden-chest")
    assert (capsys.readouterr().out, policy.load()["test_mode"]) == ("OK: approvals test_mode=true\n", True)
    with pytest.raises(ProducerError) as e:
        setp("test_mode", "yes")
    assert str(e.value) == "test_mode phải là true|false"
    (prod / "policy.yaml").write_text("test_mode: 'yes'\n", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        policy.load()
    assert str(e.value) == "production/policy.yaml: test_mode: phải là true|false"
