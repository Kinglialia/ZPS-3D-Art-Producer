"""The checks before a texture brief (docs/producer.md §6.3, D24.3, D21.2; checklist 41, 52, 85) and the worker's
UNFIXABLE, on the real CLI. Each test drives a fresh pilot to texture/todo with fake agents; no paid call."""
import json
import os

import yaml

from flowkit import AID, A, PROJECT_KEY, counts, to_texture
from shared import run


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
    head, line = f.p("retry", AID).splitlines()
    assert head == "pilot-house: → todo. Tiếp: giao worker → `brief pilot-house`"
    f.sent = line
    out = f.brief("t1 again")
    assert out["brief"] == f"{A}/texture/v1/brief-worker.md"
    assert list(budgets(tmp_path).values()) == [{"max_credits": 10, "used_credits": 0}]


def test_a_profile_without_env_file_paints_and_opens_no_budget(tmp_path):
    def no_env_file():
        prof = yaml.safe_load((tmp_path / "production/PROJECT-PROFILE.yaml").read_text(encoding="utf-8"))
        del prof["paths"]["env_file"]
        (tmp_path / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump(prof, allow_unicode=True),
                                                                   encoding="utf-8")
    f = to_texture(tmp_path, env_line=None, prepare=no_env_file)
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
    # D30.5: the approval that answers the question dispatches the rebuild at once.
    assert (f.st()["state"], f.st()["fix_round"], budgets(tmp_path)[name]) == (
        "running", 0, {"max_credits": 20, "used_credits": 10})
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
    f.review("t1", verdict="ESCALATE", counts=counts(), top_fix=None)
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
    f.review("t1", verdict="ESCALATE", counts=counts(), top_fix=None)
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
    f.review("t1", verdict="ESCALATE", counts=counts(), top_fix=None)
    busy = tmp_path / "production/pids/meshy/other.pid"
    busy.parent.mkdir(parents=True, exist_ok=True)
    busy.write_text(str(os.getpid()), encoding="utf-8")  # the Meshy slot is busy, so the texture redo waits in fix
    f.human("redo texture", "mái tối", "--action", "redo")
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    busy.unlink()
    f.work("m2", mesh_size=(1.3, 1, 1))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    f.brief("gate")
    assert ("texture v1" in f.st()["decisions"], f.st()["state"]) == (True, "waiting_human")
    out = f.p("feedback", AID, "gọi lại Meshy", "--action", "approve")
    assert out.startswith("pilot-house: mesh_changed: thêm 1 lần gọi Meshy (10 credit)") and f.st()["state"] == "running"
    assert json.loads(out.splitlines()[-1])["brief"] == f"{A}/texture/v2/brief-worker.md"


def test_a_meshy_price_check_that_fails_blocks_with_one_line_instead_of_a_traceback(tmp_path):
    f = to_texture(tmp_path, prepare=(tmp_path / "concepts/_approved" / AID / "concept_albedo.png").unlink)
    f.brief("t1")
    assert f.cp["t1"]["out"] == (f"pilot-house: texture → blocked trước khi giao. Tiếp: xử lý: gen_api --dry-run: missing "
                                 f"file {f.st()['concept_dir']}/concept_albedo.png → bổ sung rồi `retry pilot-house`\n")


def test_a_key_line_with_export_blocks_texture_with_the_fix_instead_of_saying_the_key_is_missing(tmp_path):
    f = to_texture(tmp_path, env_line=f"export MESHY_API_KEY={PROJECT_KEY}\n")
    f.brief("t1")
    assert f.cp["t1"]["out"] == ("pilot-house: texture → blocked trước khi giao. Tiếp: xử lý: .env có `export "
                                 "MESHY_API_KEY=`, kit không đọc dòng đó: bỏ chữ `export ` ở đầu dòng → bổ sung rồi "
                                 "`retry pilot-house`\n")
    assert budgets(tmp_path) == {}


def to_paint(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="")
    f.review("t1", verdict="ESCALATE", counts=counts(), top_fix=None)
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    f.work("m2", mesh_size=(1.3, 1, 1))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    f.brief("gate")
    f.p("meshy", AID, "paint")
    return f


def test_unfixable_after_the_user_chose_paint_stops_with_the_reason_instead_of_asking_the_meshy_question_again(tmp_path):
    f = to_paint(tmp_path)
    before = budgets(tmp_path)
    f.work("t2", unfixable=True, issues="hỏng")
    assert f.cp["t2 worker"]["out"] == ("pilot-house: worker DONE → texture/blocked. Tiếp: xử lý: UNFIXABLE ở chế độ VẼ "
                                        "MỚI: hỏng → bổ sung rồi `retry pilot-house`\n")
    assert ("ask" in f.st(), budgets(tmp_path)) == (False, before)


def test_a_worker_dispatched_again_after_a_paid_call_is_told_to_reuse_its_glb_instead_of_painting_anew(tmp_path):
    f = to_texture(tmp_path)
    out = f.brief("t1 brief")
    f.meshy("t1", (tmp_path / out["report"]).parent, "")
    f.brief("t1 again brief")
    t = f.cp["t1 again brief"]["text"].splitlines()
    assert [l for l in t if l.startswith("MESHY")] == [
        "MESHY_CALLS: 0 (đã dùng 10/10 credit): không gọi Meshy",
        f"MESHY_DONE: `{A}/texture/v1/work/meshy/call-1` đã trả credit, topology pass: dùng lại `base_color.png`, "
        "không gọi lại Meshy"]


def test_a_paid_task_without_its_glb_is_named_in_the_next_brief_and_resumed_on_its_folder_at_no_extra_credit(tmp_path):
    f = to_texture(tmp_path)
    out = f.brief("t1 brief")
    vd = (tmp_path / out["report"]).parent
    f.meshy("t1", vd, "poll_fail:3")
    f.brief("t1 again brief")
    t = f.cp["t1 again brief"]["text"].splitlines()
    call = f"{A}/texture/v1/work/meshy/call-1"
    assert [l for l in t if l.startswith("MESHY")] == [
        "MESHY_CALLS: 0 (đã dùng 10/10 credit): không gọi Meshy",
        f"MESHY_DONE: `{call}` task task-1 đã trả credit, chưa có GLB hoặc base_color: chạy lại lệnh Meshy với "
        f"`--out {call}`, không tốn thêm credit",
        next(l for l in f.cp["t1 brief"]["text"].splitlines() if l.startswith("MESHY: ")),
        f"MESHY_ARGS: --asset {AID} --pid-file production/pids/meshy/{AID}.pid"]
    f.meshy("t1 again", vd, "")
    assert (f.cp["t1 again meshy"]["rc"], list(budgets(tmp_path).values())) == (
        0, [{"max_credits": 10, "used_credits": 10}])


def mode_lines(f, name):
    return [l for l in f.cp[name]["text"].splitlines() if l.startswith("MODE: ")]


def ledger_modes(root):
    return [l.split(f"{AID} · texture · ", 1)[1] for l in
            (root / "production/ledger.md").read_text(encoding="utf-8").splitlines() if " · texture · chế độ " in l]


def test_a_meshy_key_and_budget_make_meshy_sua_the_default_and_the_ledger_says_why_d30_11(tmp_path):
    f = to_texture(tmp_path)
    f.brief("t1")
    assert mode_lines(f, "t1") == ["MODE: Meshy SỬA (texture_default meshy: có key và budget)"]
    assert ledger_modes(tmp_path) == ["chế độ Meshy SỬA: texture_default meshy: có key và budget"]


def test_no_env_file_paints_and_the_ledger_records_that_choice_and_its_reason(tmp_path):
    def drop_env_file():
        prof = yaml.safe_load((tmp_path / "production/PROJECT-PROFILE.yaml").read_text(encoding="utf-8"))
        del prof["paths"]["env_file"]
        (tmp_path / "production/PROJECT-PROFILE.yaml").write_text(yaml.safe_dump(prof, allow_unicode=True),
                                                                   encoding="utf-8")
    f = to_texture(tmp_path, env_line=None, prepare=drop_env_file)
    f.brief("t1")
    assert ledger_modes(tmp_path) == ["chế độ VẼ MỚI: profile không có `paths.env_file`: không gọi Meshy"]


def test_a_spent_budget_keeps_meshy_sua_on_the_paid_layer_and_a_rebrief_adds_no_ledger_line(tmp_path):
    f = to_texture(tmp_path)
    out = f.brief("t1 brief")
    f.meshy("t1", (tmp_path / out["report"]).parent, "")
    f.brief("t1 again brief")
    f.brief("t1 third brief")
    why = "hết lần gọi: sửa trên lớp Meshy qua topology"
    assert mode_lines(f, "t1 third brief") == [f"MODE: Meshy SỬA ({why})"]
    assert ledger_modes(tmp_path) == ["chế độ Meshy SỬA: texture_default meshy: có key và budget",
                                      f"chế độ Meshy SỬA: {why}"]


def test_a_spent_budget_whose_only_layer_failed_topology_paints_because_that_layer_is_unusable(tmp_path, monkeypatch):
    f = to_texture(tmp_path)
    out = f.brief("t1 brief")
    monkeypatch.setenv("FAKE_MESHY_BASE_PX", "32")
    f.meshy("t1", (tmp_path / out["report"]).parent, "")
    assert f.cp["t1 meshy"]["rc"] == 4
    f.brief("t1 again brief")
    assert mode_lines(f, "t1 again brief") == [
        "MODE: VẼ MỚI (hết lần gọi, không có lớp Meshy qua topology)"]


def test_a_redo_with_the_budget_spent_names_the_passed_layer_of_v1_so_meshy_sua_has_a_layer_to_fix(tmp_path):
    f = to_texture(tmp_path)
    f.work("t1", meshy="")
    f.review("t1", verdict="ESCALATE", counts=counts(), top_fix=None)
    f.human("redo texture", "mái tối", "--action", "redo")
    f.brief("t2")
    t = f.cp["t2"]["text"].splitlines()
    assert mode_lines(f, "t2") == ["MODE: Meshy SỬA (hết lần gọi: sửa trên lớp Meshy qua topology)"]
    assert [l for l in t if l.startswith("MESHY")] == [
        "MESHY_CALLS: 0 (đã dùng 10/10 credit): không gọi Meshy",
        f"MESHY_DONE: `{A}/texture/v1/work/meshy/call-1` topology pass: dùng `base_color.png`, không gọi Meshy"]


def test_texture_mode_paint_before_the_step_never_opens_a_budget_so_no_credit_can_be_spent(tmp_path):
    said = []
    f = to_texture(tmp_path, prepare=lambda: said.append(run(tmp_path, "texture-mode", AID, "paint")))
    assert said == ["pilot-house: texture-mode paint (bởi người dùng); áp dụng từ brief texture tiếp theo\n"]
    assert f.st()["texture_choice"]["mode"] == "paint"
    f.brief("t1")
    t = f.cp["t1"]["text"].splitlines()
    assert mode_lines(f, "t1") == ["MODE: VẼ MỚI (người dùng chọn `texture-mode paint`: không gọi Meshy)"]
    assert (not any(l.startswith("MESHY") for l in t), budgets(tmp_path)) == (True, {})
    assert any(l.endswith(f"{AID} · texture · texture-mode paint · bởi người dùng")
               for l in (tmp_path / "production/ledger.md").read_text(encoding="utf-8").splitlines())


def test_texture_mode_records_who_chose_it_and_auto_returns_to_the_meshy_default(tmp_path):
    f = to_texture(tmp_path)
    f.p("texture-mode", AID, "paint", "--by", "anh Trung: vẽ tay")
    assert f.st()["texture_choice"]["by"] == "anh Trung: vẽ tay"
    f.p("texture-mode", AID, "auto")
    f.brief("t1")
    assert mode_lines(f, "t1") == ["MODE: Meshy SỬA (texture_default meshy: có key và budget)"]


def test_texture_mode_meshy_with_a_key_says_the_user_forced_meshy(tmp_path):
    f = to_texture(tmp_path, prepare=lambda: run(tmp_path, "texture-mode", AID, "meshy"))
    f.brief("t1")
    assert mode_lines(f, "t1") == ["MODE: Meshy SỬA (người dùng chọn `texture-mode meshy`)"]


def test_texture_mode_meshy_without_a_key_is_refused_and_changes_nothing(tmp_path):
    f = to_texture(tmp_path, env_line="OTHER=1\n")
    assert f.p("texture-mode", AID, "meshy", ok=False) == (
        "LỖI: pilot-house: `texture-mode meshy` cần MESHY_API_KEY trong env_file của profile: người dùng thêm key\n")
    assert "texture_choice" not in f.st()


def test_texture_mode_meshy_with_the_budget_spent_and_no_usable_layer_blocks_instead_of_painting(tmp_path, monkeypatch):
    f = to_texture(tmp_path)
    out = f.brief("t1 brief")
    monkeypatch.setenv("FAKE_MESHY_BASE_PX", "32")
    f.meshy("t1", (tmp_path / out["report"]).parent, "")
    f.p("texture-mode", AID, "meshy")
    f.brief("t1 again")
    assert f.cp["t1 again"]["out"].startswith("pilot-house: texture → blocked trước khi giao. Tiếp: xử lý: "
                                              "`texture-mode meshy`: hết budget Meshy cho mesh này")


def test_unfixable_under_texture_mode_paint_never_asks_for_another_paid_call(tmp_path):
    f = to_texture(tmp_path)
    f.brief("gate")
    f.p("texture-mode", AID, "paint")
    f.work("t1", unfixable=True, issues="hỏng")
    assert ("ask" in f.st(), f.st()["state"]) == (False, "blocked")


def set_policy(root, **kw):
    p = root / "production/policy.yaml"
    pol = yaml.safe_load(p.read_text(encoding="utf-8"))
    for k, v in kw.items():
        if v is None:
            pol.pop(k, None)
        else:
            pol[k] = v
    p.write_text(yaml.safe_dump(pol, allow_unicode=True), encoding="utf-8")


def test_texture_default_paint_in_policy_makes_auto_paint_without_a_key_check_or_a_budget_d34_2(tmp_path):
    """The Meshy default comes from one asset (Run 5), so it is the project's number, not the skill's: changing
    policy.yaml changes the mode, and painting never opens a budget, so no credit can be spent."""
    f = to_texture(tmp_path, env_line="OTHER=1\n", prepare=lambda: set_policy(tmp_path, texture_default="paint"))
    f.brief("t1")
    t = f.cp["t1"]["text"].splitlines()
    assert mode_lines(f, "t1") == ["MODE: VẼ MỚI (texture_default paint: không gọi Meshy)"]
    assert (not any(l.startswith("MESHY") for l in t), budgets(tmp_path)) == (True, {})


def test_a_policy_written_before_texture_default_takes_the_template_value(tmp_path):
    f = to_texture(tmp_path, prepare=lambda: set_policy(tmp_path, texture_default=None))
    f.brief("t1")
    assert mode_lines(f, "t1") == ["MODE: Meshy SỬA (texture_default meshy: có key và budget)"]


def test_the_template_policy_carries_the_meshy_default_with_its_origin():
    from shared import SCRIPTS
    text = (SCRIPTS.parent / "templates/policy.yaml").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("texture_default:"))
    assert line.split("#")[0].split() == ["texture_default:", "meshy"]
    assert "Run 5, 1 asset" in line and "tạm, đo lại sau 3–5 asset khác loại" in line
