"""The checks before a texture brief (docs/producer.md §6.3, D24.3, D21.2; checklist 41, 52, 85) and the worker's
UNFIXABLE, on the real CLI. Each test drives a fresh pilot to texture/todo with fake agents; no paid call."""
import json

import yaml

from flowkit import AID, A, PROJECT_KEY, counts, to_texture


def budgets(root):
    return {p.name: json.loads(p.read_text()) for p in sorted((root / A / "texture").glob("budget-*.json"))}


def test_an_env_file_without_the_key_blocks_texture_before_any_version_and_retry_resumes_after_the_key(tmp_path):
    f = to_texture(tmp_path, env_line="OTHER=1\n")
    f.brief("t1")
    assert f.cp["t1"]["out"] == ("pilot-house: texture → blocked trước khi giao. Tiếp: xử lý: thiếu MESHY_API_KEY trong "
                                 "env_file của profile: người dùng thêm key → bổ sung rồi `retry pilot-house`\n")
    st = f.st()
    assert ("texture" in st["versions"], st["blocked_from"], budgets(tmp_path)) == (False, "todo", {})
    (tmp_path / ".env").write_text(f"MESHY_API_KEY={PROJECT_KEY}\n", encoding="utf-8")
    assert f.p("retry", AID) == "pilot-house: → todo. Tiếp: giao worker → `brief pilot-house`\n"
    out = f.brief("t1 again")
    assert out["brief"] == f"{A}/texture/v1/brief-worker.md"
    assert list(budgets(tmp_path).values()) == [{"max_credits": 10, "used_credits": 0}]


def test_a_profile_without_env_file_paints_and_opens_no_budget(tmp_path):
    f = to_texture(tmp_path, env_line=None)
    prof = yaml.safe_load((tmp_path / "production/PROJECT-PROFILE.yaml").read_text(encoding="utf-8"))
    del prof["paths"]["env_file"]
    (tmp_path / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump(prof, allow_unicode=True), encoding="utf-8")
    f.brief("t1")
    t = f.cp["t1"]["text"].splitlines()
    assert "MODE: VẼ MỚI (profile không có `paths.env_file`: không gọi Meshy)" in t
    assert not any(l.startswith("MESHY") for l in t)
    assert budgets(tmp_path) == {}


def test_an_asset_without_an_approved_concept_folder_stops_with_one_line_not_a_traceback(tmp_path):
    f = to_texture(tmp_path)
    st = f.st() | {"concept_dir": None}
    (tmp_path / A / "status.json").write_text(json.dumps(st), encoding="utf-8")
    assert f.p("brief", AID, ok=False) == (
        "LỖI: pilot-house: bước texture cần concept trong _approved/ (asset tạo bằng `new` không có)\n")


def test_a_worker_unfixable_on_the_first_build_asks_the_user_and_approval_rebuilds_with_one_more_call(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="", unfixable=True, issues="lớp Meshy sai style toàn bộ")
    (name, b), = budgets(tmp_path).items()
    assert f.cp["t1 worker"]["out"] == (
        "pilot-house: worker DONE → texture/waiting_human. Tiếp: chờ người dùng: UNFIXABLE: lớp Meshy sai style toàn bộ: "
        "gọi Meshy thêm một lần (10 credit) hay VẼ MỚI? (duyệt = gọi Meshy, `meshy pilot-house paint` = VẼ MỚI) "
        "(review page)\n")
    assert (b, f.st()["ask"]) == ({"max_credits": 10, "used_credits": 10},
                                  {"kind": "meshy_regen", "budget": name, "next": "todo", "base": None, "new_round": False})
    f.human("approve", "gọi lại", "--action", "approve")
    assert (f.st()["state"], f.st()["fix_round"], budgets(tmp_path)[name]) == (
        "todo", 0, {"max_credits": 20, "used_credits": 10})
    out = f.brief("t2")
    assert out["brief"] == f"{A}/texture/v2/brief-worker.md"
    assert any(l.startswith("MESHY_CALLS: 1 ") for l in f.cp["t2"]["text"].splitlines())


def test_a_second_click_on_approve_after_the_answer_changes_nothing(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="", unfixable=True, issues="hỏng")
    f.human("approve", "gọi lại", "--action", "approve")
    again = f.p("feedback", AID, "gọi lại", "--action", "approve")
    assert again == ("pilot-house: bỏ qua approve texture v1: đã có quyết định lúc "
                     f"{f.st()['decisions']['texture v1']['at']}\n")
    assert list(budgets(tmp_path).values()) == [{"max_credits": 20, "used_credits": 10}]


def test_a_new_mesh_after_an_unused_budget_gets_one_call_without_a_question(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1")
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    f.work("m2", mesh_size=(1.3, 1, 1))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    out = f.brief("t2")
    assert out["brief"] == f"{A}/texture/v2/brief-worker.md"
    assert sorted(b["max_credits"] for b in budgets(tmp_path).values()) == [10, 10]


def test_answering_call_to_the_mesh_question_gives_the_new_mesh_one_call(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="")
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    f.work("m2", mesh_size=(1.3, 1, 1))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    f.brief("gate")
    new = next(n for n, b in budgets(tmp_path).items() if b["used_credits"] == 0)
    assert f.p("meshy", AID, "call", "--by", "gọi đi") == (
        f"pilot-house: mesh_changed: thêm 1 lần gọi Meshy (10 credit), {new} max_credits=10 → texture/todo. "
        "Tiếp: giao worker → `brief pilot-house`\n")
    assert budgets(tmp_path)[new] == {"max_credits": 10, "used_credits": 0}
    assert f.p("meshy", AID, "paint", ok=False) == "LỖI: pilot-house: không có câu hỏi Meshy đang chờ (state=todo)\n"


def test_approve_answers_the_mesh_question_although_the_old_texture_version_had_a_decision(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="")
    f.human("redo texture", "mái tối", "--action", "redo")
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    f.work("m2", mesh_size=(1.3, 1, 1))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    f.brief("gate")
    assert ("texture v1" in f.st()["decisions"], f.st()["state"]) == (True, "waiting_human")
    out = f.p("feedback", AID, "gọi lại Meshy", "--action", "approve")
    assert out.startswith("pilot-house: mesh_changed: thêm 1 lần gọi Meshy (10 credit)") and f.st()["state"] == "todo"
