"""End-to-end GĐ 4 on the synthetic pilot, through all six steps with the real CLI, fake agents and a fake Meshy HTTP
layer (no paid call): a Meshy poll error retried on the same task within budget; meshy_regen → the user approves one more
call; assemble fails → blocked → retry → DUYỆT 2; Needs-fix at assemble must name texture or model; texture redone;
DUYỆT 2 fills deliver/; then a model redo changes the mesh → new budget with max 0 and the Meshy-or-VẼ MỚI question."""
import json
import shlex
import sys
from pathlib import Path

import pytest

from flowkit import AID, A, PROJECT_KEY, SHELL_KEY, counts, mf, to_texture
from shared import P

SKILL = P.parents[1]
BRIEF_MAX = 4352


def sha12(root, v):
    import hashlib
    return hashlib.sha256((root / A / f"model/v{v}/final/{AID}-untextured.glb").read_bytes()).hexdigest()[:12]


def budget(root, h):
    return json.loads((root / A / f"texture/budget-{h}.json").read_text(encoding="utf-8"))


def meshy_log(root):
    return [json.loads(l) for l in (root / "meshy.jsonl").read_text().splitlines()]


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("texture")
    f = to_texture(root)
    cp = f.cp
    cp["h1"] = sha12(root, 1)
    f.work("t1", meshy="poll_fail:1")
    cp["budget t1"] = budget(root, cp["h1"])
    f.review("t1", counts=counts(blocker=1), top_fix="meshy_regen: F1", rubric="light=fail",
             findings=[mf(1, "meshy_regen", "toàn bộ: lớp Meshy lệch style", prio="blocker")])
    cp["budget t1 review"] = budget(root, cp["h1"])
    f.human("approve meshy", "gọi lại Meshy", "--action", "approve")
    cp["budget approve"] = budget(root, cp["h1"])
    f.work("t2", meshy="")
    cp["budget t2"] = budget(root, cp["h1"])
    f.review("t2", verdict="PASS", counts=counts(), top_fix=None, compare="F1=better",
             prior=["- F1: resolved | evidence: lit_34_front.png"])
    f.assemble("a1", fail="compare.34_front: lệch 41.2 > 6")
    cp["a1 findings"] = json.loads((root / A / "assemble/v1/findings.json").read_text(encoding="utf-8"))
    f.keep("retry a1", f.p("retry", AID))
    f.assemble("a1 again")
    f.human("redo assemble", "mái tối quá", "--action", "redo", ok=False)
    f.human("redo texture", "mái tối quá", "--action", "redo", "--step", "texture")
    f.work("t3")
    f.review("t3", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.assemble("a2")
    cp["deliver before"] = (root / "deliver").exists()
    f.human("approve a2", "đạt", "--action", "approve")
    cp["deliver"] = sorted(p.relative_to(root / "deliver" / AID).as_posix()
                           for p in (root / "deliver" / AID).rglob("*") if p.is_file())
    cp["estimates"] = [json.loads(l) for l in (root / ".zps-art/estimates.jsonl").read_text().splitlines()]
    f.human("redo model", "cửa to hơn", "--action", "redo", "--step", "model")
    cp["readme redo"] = (root / "deliver" / AID / "README.md").read_text(encoding="utf-8")
    f.work("m2", mesh_size=(1.2, 1.0, 1.0))
    f.review("m2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: lit_34_front.png"])
    f.human("approve m2", "đạt", "--action", "approve")
    cp["h2"] = sha12(root, 2)
    f.brief("t4 gate")
    cp["budget h2"] = budget(root, cp["h2"])
    f.human("redo during question", "vẽ lại", "--action", "redo", ok=False)
    f.keep("paint", f.p("meshy", AID, "paint", "--by", "vẽ mới đi"))
    f.work("t4")
    f.keep("stats", f.p("texture-stats"))
    cp["root"] = root
    cp["meshy log"] = meshy_log(root)
    return cp


def pick(st, *keys):
    return {k: st.get(k) for k in keys}


def lines(text):
    return text.splitlines()


def test_the_first_texture_brief_opens_a_budget_of_one_retexture_for_the_locked_mesh(flow):
    b, h = flow["t1 brief"], flow["h1"]
    assert b["out"] == {"role": "worker", "agent": "zps-3dp-step-texture", "model": "opus", "resume": None,
                        "brief": f"{A}/texture/v1/brief-worker.md", "report": f"{A}/texture/v1/worker-out.md"}
    want = [f"TOOLS: {SKILL / 'agents/zps-3dp-step-texture/tools'}", "BLENDER: blender",
            "PILOT: none (pilot_asset: null): so với pilot ghi not_checked",
            f"MESHY: {SKILL / 'scripts/meshy_call.py'}",
            f"MESHY_ARGS: --asset {AID} --pid-file production/pids/meshy/{AID}.pid",
            f"MESHY_CALLS: 1 (giá 10 credit một lần; `{A}/texture/budget-{h}.json` chỉ script ghi)",
            f"GEN_IMAGE: {SKILL / 'scripts/gen_image_codex.py'}"]
    assert [l for l in want if l not in lines(b["text"])] == []
    assert PROJECT_KEY not in b["text"] and ".env" not in b["text"]


def test_the_texture_brief_requires_the_albedo_at_the_card_resolution_and_the_render_set(flow):
    req = [l for l in lines(flow["t1 brief"]["text"]) if l.startswith("- Bắt buộc có")]
    assert req == [f"- Bắt buộc có (tính từ `{A}/texture/v1/`): `final/albedo_2048.png`, `final/texture_spec.json`, "
                   "`final/notes.md`, `final/final_lit_vs_concept.png`, `final/review/renders.json`, "
                   "`final/review/checks/tex_measure.json`."]


def test_a_meshy_poll_error_waits_on_the_same_task_and_spends_one_call_of_the_budget(flow):
    assert (flow["t1 meshy"]["rc"], flow["budget t1"]) == (0, {"max_credits": 10, "used_credits": 10})
    log = flow["meshy log"]
    assert [(c["kind"], c["url"].rsplit("/", 1)[1]) for c in log[:4]] == [
        ("post", "retexture"), ("poll_fail", "task-1"), ("poll", "task-1"), ("download", "task-1.glb")]
    assert {c["auth"] for c in log if c["auth"]} == {f"Bearer {PROJECT_KEY}"}


def test_meshy_regen_waits_for_the_user_and_does_not_raise_the_budget_by_itself(flow):
    s, h = flow["t1 review"], flow["h1"]
    assert s["out"] == ("pilot-house: review FIX (blocker=1) → texture/waiting_human. Tiếp: chờ người dùng: meshy_regen "
                        "F1: gọi Meshy thêm một lần (10 credit) hay VẼ MỚI? (duyệt = gọi Meshy, `meshy pilot-house "
                        "paint` = VẼ MỚI) (review page)\n")
    assert pick(s["st"], "ask", "offer", "label", "fix_round") == {
        "ask": {"kind": "meshy_regen", "budget": f"budget-{h}.json", "next": "fix", "base": 1, "new_round": True},
        "offer": 1, "label": "chưa đạt", "fix_round": 0}
    assert flow["budget t1 review"] == {"max_credits": 10, "used_credits": 10}


def test_the_users_approval_adds_one_call_and_the_next_brief_says_one_call_is_left(flow):
    s, h = flow["approve meshy"], flow["h1"]
    head, line = s["out"].splitlines()
    assert head == (f"pilot-house: meshy_regen: thêm 1 lần gọi Meshy (10 credit), budget-{h}.json max_credits=20. "
                    "Tiếp: giao worker → `brief pilot-house`")
    # D30.5: the approval dispatches the fix round in the same turn.
    assert json.loads(line)["brief"] == f"{A}/texture/v2/brief-worker.md"
    assert pick(s["st"], "state", "fix_round", "fix_base", "ask") == {"state": "running", "fix_round": 1, "fix_base": 1,
                                                                      "ask": None}
    assert flow["budget approve"] == {"max_credits": 20, "used_credits": 10}
    t = flow["t2 brief"]
    assert (t["out"]["resume"], t["out"]["brief"]) == ("w-t1", f"{A}/texture/v2/brief-worker.md")
    assert f"MESHY_CALLS: 1 (giá 10 credit một lần; `{A}/texture/budget-{h}.json` chỉ script ghi)" in lines(t["text"])
    assert "`TOP_FIX: meshy_regen: F1`" in t["text"]
    assert flow["budget t2"] == {"max_credits": 20, "used_credits": 20}
    assert [c["kind"] for c in flow["meshy log"][6:11]] == ["post", "poll", "download", "poll", "base_color"]


def test_check_texture_gets_only_the_view_set_and_two_concept_images(flow):
    t = flow["t1 review brief"]
    assert t["out"]["agent"] == "zps-3dp-check-texture"
    inputs = [l for l in lines(t["text"]) if l.startswith("- Đầu ra đã duyệt")]
    assert inputs == [f"- Đầu ra đã duyệt của bước `views_rest` (đầu vào, không chấm lại): `{A}/views_rest/v1/final/`."]
    assert [l for l in lines(t["text"]) if "Concept đã duyệt" in l][0].endswith(
        ": chỉ `concept_albedo.png`, `concept_shadow.png`.")
    assert "TOP_FIX: <repaint|fix_uv_mesh|meshy_regen|need_evidence>: F<n>[, F<m>]" in lines(t["text"])


def test_a_texture_pass_moves_straight_on_to_assemble_and_its_brief_is_a_script_command(flow):
    assert flow["t2 review"]["out"] == "pilot-house: review PASS (0 mở) → assemble/todo. Tiếp: giao worker → `brief pilot-house`\n"
    b = flow["a1 brief"]
    ph = flow["t1 brief"]["text"].split("PROFILE_HASH: ")[1][:12]
    assert b["out"] == {"role": "script", "report": f"{A}/assemble/v1/report-script.md", "command": shlex.join([
        sys.executable, str(SKILL / "scripts/assemble.py"), "--blender", "blender", "--", AID, "1", ph])}


def test_an_assemble_fail_blocks_with_the_fail_points_as_findings_for_the_board(flow):
    s = flow["a1 ingest"]
    assert s["out"] == ("pilot-house: script BLOCKED → assemble/blocked. Tiếp: xử lý: BLOCKED: compare.34_front: "
                        "lệch 41.2 > 6 → bổ sung rồi `retry pilot-house`\n")
    f = flow["a1 findings"]["findings"]
    assert (list(f), f["F1"]["priority"], f["F1"]["status"], f["F1"]["acceptance"]) == (
        ["F1"], "blocker", "open", "compare.34_front mean_abs ≤ 6")


def test_retry_runs_assemble_again_as_a_new_version_so_the_failed_run_keeps_its_report_and_findings(flow):
    head, line = flow["retry a1"]["out"].splitlines()
    assert head == "pilot-house: → todo. Tiếp: giao worker → `brief pilot-house`"
    assert json.loads(line) == flow["a1 again brief"]["out"]
    assert flow["a1 again brief"]["out"]["report"] == f"{A}/assemble/v2/report-script.md"
    s = flow["a1 again ingest"]
    assert s["out"] == ("pilot-house: script DONE → assemble/waiting_human. "
                        "Tiếp: chờ người dùng: duyệt assemble v2 (review page)\n")
    assert (flow["root"] / A / "assemble/v1/report-script.md").read_text(encoding="utf-8").startswith("STATUS: BLOCKED")


def test_needs_fix_at_assemble_must_name_texture_or_model(flow):
    assert flow["redo assemble"]["out"] == ("LỖI: pilot-house: assemble không có vòng sửa: chọn bước sửa, "
                                            "`--step texture` (vẽ lại) hoặc `--step model` (mesh, UV)\n")
    s = flow["redo texture"]
    head, line = s["out"].splitlines()
    assert head == "pilot-house: làm lại texture từ v2. Tiếp: giao worker → `brief pilot-house`"
    assert json.loads(line)["brief"] == f"{A}/texture/v3/brief-worker.md"
    assert pick(s["st"], "stage", "state", "fix_round", "fix_base", "approved") == {
        "stage": "texture", "state": "running", "fix_round": 1, "fix_base": 2,
        "approved": {"blockout": 1, "views_front": 1, "views_rest": 1, "model": 1}}


def test_with_the_budget_spent_the_fix_brief_says_no_meshy_call_is_left(flow):
    t = flow["t3 brief"]["text"]
    assert "MESHY_CALLS: 0 (đã dùng 20/20 credit): không gọi Meshy" in lines(t)
    assert not any(l.startswith(("MESHY:", "MESHY_ARGS:")) for l in lines(t))


def test_duyet_2_copies_the_package_to_deliver_and_logs_the_estimate_record(flow):
    out = flow["approve a2"]["out"].splitlines()
    assert out[0] == "pilot-house: đã duyệt assemble v3 → assemble/done. Tiếp: xong"
    assert out[1].startswith("Lệnh xóa D29: ")  # D29.3: the user's DUYỆT 2 arms the deletion; tests/test_purge.py
    assert pick(flow["approve a2"]["st"], "approved", "rejected")["rejected"]["assemble"] == [1, 2]
    assert flow["deliver before"] is False
    assert flow["deliver"] == ["README.md", "model/pilot-house.blend", "model/pilot-house.glb", "review/compare.json",
                               "texture/albedo_2048.png", "texture/notes.md"]
    rec = flow["estimates"]
    assert [(r["method"], r["credits"], r["asset"]) for r in rec] == [("self", 20.0, AID)]


def test_a_model_redo_after_duyet_2_marks_the_delivered_readme_as_being_redone(flow):
    assert flow["readme redo"].startswith("**đang làm lại**\n\nTrạng thái: đã duyệt DUYỆT 2 bởi người dùng · ")


def test_a_changed_mesh_gets_a_new_budget_of_zero_and_the_meshy_or_paint_question_before_any_brief(flow):
    h2 = flow["h2"]
    assert h2 != flow["h1"]
    assert flow["t4 gate"]["out"] == (
        "pilot-house: texture → waiting_human trước khi giao. Tiếp: chờ người dùng: Mesh đổi, texture Meshy cũ mất hiệu "
        "lực. Gọi lại Meshy (tốn credit) hay VẼ MỚI? (duyệt = gọi Meshy, `meshy pilot-house paint` = VẼ MỚI) "
        "(review page)\n")
    assert flow["budget h2"] == {"max_credits": 0, "used_credits": 0}
    assert pick(flow["t4 gate"]["st"], "stage", "versions", "ask") == {
        "stage": "texture", "versions": {"blockout": 1, "views_front": 1, "views_rest": 1, "model": 2, "texture": 3,
                                         "assemble": 3},
        "ask": {"kind": "mesh_changed", "budget": f"budget-{h2}.json", "next": "todo", "base": None, "new_round": False}}


def test_a_texture_redo_cannot_answer_the_mesh_question(flow):
    assert flow["redo during question"]["out"] == (
        "LỖI: pilot-house: đang chờ chọn Meshy hay VẼ MỚI cho mesh mới: duyệt = gọi Meshy, "
        "`meshy pilot-house paint` = VẼ MỚI\n")


def test_choosing_paint_starts_a_texture_build_that_must_not_call_meshy(flow):
    h2 = flow["h2"]
    assert flow["paint"]["out"] == (f"pilot-house: mesh_changed: VẼ MỚI, không gọi Meshy cho mesh {h2} → texture/todo. "
                                    "Tiếp: giao worker → `brief pilot-house`\n")
    t = flow["t4 brief"]
    assert t["out"]["brief"] == f"{A}/texture/v4/brief-worker.md"
    assert "MODE: VẼ MỚI (người dùng chọn cho mesh này: không gọi Meshy)" in lines(t["text"])
    assert not any(l.startswith("MESHY") for l in lines(t["text"]))


def test_texture_stats_compare_the_proposal_with_the_mode_used_and_sum_the_meshy_spend(flow):
    assert list(Path(flow["root"]).rglob("texture-log.jsonl")) == []
    assert flow["stats"]["out"] == ("texture-stats: 1 asset có texture_spec.json; đề xuất khớp chế độ dùng 0/1 "
                                    "(lệch: pilot-house (meshy→paint)); Meshy 2 lần, 20 credit; "
                                    "người dùng duyệt gọi thêm 1 lần\n")


def test_no_key_reaches_a_brief_a_report_or_the_ledger(flow):
    root = Path(flow["root"])
    text = "".join(p.read_text(errors="replace") for p in (root / "production").rglob("*") if p.is_file()
                   and p.suffix in (".md", ".json"))
    assert PROJECT_KEY not in text and SHELL_KEY not in text


def test_every_texture_brief_stays_under_the_token_budget_without_the_install_and_project_paths(flow):
    strip = (str(Path(flow["root"]).resolve()), str(SKILL))
    sizes = {k: len(v["text"].replace(strip[0], "").replace(strip[1], "").encode()) for k, v in flow.items()
             if isinstance(v, dict) and v.get("text") and k.startswith("t")}
    assert len(sizes) == 7 and max(sizes.values()) < BRIEF_MAX, sizes


def test_a_second_duyet_2_of_one_asset_replaces_its_estimate_record_so_the_project_median_counts_it_once(tmp_path):
    f = to_texture(tmp_path)
    for k in (1, 2):
        f.work(f"t{k}")
        f.review(f"t{k}", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better" if k == 2 else None,
                 prior=["- H1: resolved | evidence: lit_34_front.png"] if k == 2 else ())
        f.assemble(f"a{k}")
        f.human(f"approve a{k}", "đạt", "--action", "approve")
        if k == 1:
            f.human("redo texture", "mái tối", "--action", "redo", "--step", "texture")
    assert f.st()["state"] == "done"
    rec = [json.loads(l) for l in (tmp_path / ".zps-art/estimates.jsonl").read_text().splitlines()]
    assert [r["asset"] for r in rec] == [AID]


def test_the_texture_review_brief_says_a_note_finding_is_minor_because_ingest_refuses_any_other_level(flow):
    """Pilot run: the texture reviewer wrote two `note` findings as major and ingest refused the report."""
    assert "- Loại `note`: mức `minor`." in lines(flow["t1 review brief"]["text"])


def test_assemble_compares_only_the_views_the_texture_step_rendered_and_still_blocks_on_a_missing_one_t1(tmp_path):
    """A spec with no camera leaves `unlit_game` out of renders.json. Skipping a view that was rendered would hide a defect."""
    import assemble
    from PIL import Image
    tf, work, final = tmp_path / "texture", tmp_path / "work", tmp_path / "final"
    for d in (tf / "review", work / "compare", final / "review"):
        d.mkdir(parents=True)
    for p in (tf / "review" / "unlit_34_front.png", work / "compare" / "unlit_34_front.png"):
        Image.new("RGBA", (8, 8), (200, 100, 50, 255)).save(p)
    renders = tf / "review" / "renders.json"

    renders.write_text(json.dumps({"renders": {"unlit_34_front": {}, "lit_34_front": {}}}), encoding="utf-8")
    views = assemble.recorded_views(renders)
    fails, results = assemble.compare_renders(tf, work, final, views, True, [])
    assert (views, fails, list(results)) == (["unlit_34_front"], [], ["unlit_34_front"])
    assert (final / "review" / "compare_34_front.png").is_file()

    renders.write_text(json.dumps({"renders": {"unlit_34_front": {}, "unlit_game": {}}}), encoding="utf-8")
    fails, results = assemble.compare_renders(tf, work, final, assemble.recorded_views(renders), True, [])
    assert ([f["region"] for f in fails], list(results)) == (["unlit_game"], ["unlit_34_front"])

    renders.unlink()
    assert assemble.recorded_views(renders) == []
    renders.write_text(json.dumps({"renders": {}}), encoding="utf-8")
    fails, _ = assemble.compare_renders(tf, work, final, assemble.recorded_views(renders), True, [])
    assert [f["region"] for f in fails] == ["renders.json"]
