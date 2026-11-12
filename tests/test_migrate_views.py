"""N4 (D44.3): a project made with v0.7.1 has status.json files, rubrics and a pipeline.toml that name `views_front` and
`views_rest`. The rule: an asset whose status.json names an old step is refused by every command, and `P next` and
`P validate` print one line with `migrate <id>`. `migrate` then (a) changes nothing for an asset before the view steps
or with `views: none`; (b) makes the approved pair one approved `views` v1 (the old folders stay), so the asset continues
at model; (c) restarts the view work as the new `views` step for an asset in the middle of an old step or with only the
front approved. Each case starts from a literal status.json of v0.7.1."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from flowkit import A, AID, Flow, counts
from shared import SCRIPTS, pilot_project

OLD = ("views_front", "views_rest")
LINE = f"{AID}: status.json của v0.7.1 còn bước views_front/views_rest → chạy `migrate {AID}`"
FRONT_README = "## NGOẠI LỆ\n- measure.json — front (ảnh lần 2): iou 0.81\n"
REST_README = ("Thông số: xem `blockout.md`.\n\n## 1. NGOẠI LỆ\nkhông có\n## 2. TEXTURE NOTE\n- back: đầu cột xám\n"
               "## 3. Lật ảnh\nright = left lật ngang\n## 4. Trạng thái duyệt\nđã duyệt\n")


def png(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40), (120, 80, 40)).save(p)


def old_folders(root: Path, front_v=2, rest_v=2):
    """The finals of the two old steps, as v0.7.1 left them on disk."""
    ff, rf = root / A / f"views_front/v{front_v}/final", root / A / f"views_rest/v{rest_v}/final"
    for name in ("front.png", "guides/front_guide.png", "guides/back_guide.png"):
        png(ff / name)
    for name in ("back.png", "left.png", "right.png", "report/VIEWS_sheet.png"):
        png(rf / name)
    (ff / "guides/views.json").write_text('{"materials": {}}', encoding="utf-8")
    (ff / "bg_color.json").write_text('{"hex": "#3A5FCD"}', encoding="utf-8")
    (ff / "README.md").write_text(FRONT_README, encoding="utf-8")
    (rf / "README.md").write_text(REST_README, encoding="utf-8")
    (rf / "report").mkdir(exist_ok=True)
    (rf / "report/VIEWS.md").write_text("# Views pilot-house v2 · views_rest\n", encoding="utf-8")
    note = {"priority": "minor", "kind": "note_texture", "status": "open", "first_v": 2, "last_v": 2,
            "region": "back: đầu cột xám", "repair": "texture", "acceptance": "đầu cột màu gỗ"}
    regen = {"priority": "minor", "kind": "regen", "status": "open", "first_v": 2, "last_v": 2,
             "region": "front: đinh mờ", "repair": "đinh rõ hơn", "acceptance": "thấy đinh"}
    (rf.parent / "findings.json").write_text(json.dumps({"version": rest_v, "base": None, "top_fix": None, "pick": None,
                                                         "next_id": 3, "findings": {"F2": note}}), encoding="utf-8")
    (ff.parent / "findings.json").write_text(json.dumps({"version": front_v, "base": None, "top_fix": None, "pick": None,
                                                         "next_id": 2, "findings": {"F1": regen}}), encoding="utf-8")


def at_blockout_approved(root: Path) -> Flow:
    """The real pilot through an approved blockout v1, then status.json rewritten to the literal v0.7.1 fields."""
    f = Flow(root)
    pilot_project(root)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    f.review("b1", verdict="PASS", counts=counts(), top_fix=None)
    f.human("approve b1", "đạt", "--action", "approve")
    shutil.rmtree(root / A / "views")
    f.sent = None
    return f


def write_status(root: Path, fields: dict):
    p = root / A / "status.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    keep = {k: st[k] for k in ("id", "title", "type", "priority", "deadline", "concept_dir", "started", "sources")
            if k in st}
    p.write_text(json.dumps(keep | {"fix_round": 0, "worker_agent_id": None, "last_rubric": ""} | fields,
                            ensure_ascii=False), encoding="utf-8")
    return st["approved_hash"]["blockout"]


def st_of(root: Path) -> dict:
    return json.loads((root / A / "status.json").read_text(encoding="utf-8"))


def old_rubric(root: Path):
    """The rubric.md intake copied in v0.7.1: two view sections."""
    p = root / A / "rubric.md"
    text = p.read_text(encoding="utf-8")
    head, tail = text.split("## views\n", 1)
    rest = tail.split("\n## ", 1)[1]
    p.write_text(head + "## views_front\n- style: front giống concept\n- shape: front đúng guide\n\n"
                 "## views_rest\n- style: view mới giống concept\n- sync: cùng màu như front\n- props: đủ số\n\n## "
                 + rest, encoding="utf-8")


@pytest.fixture
def case_b(tmp_path):
    """Both old steps approved, the asset at model/todo: the literal status of v0.7.1."""
    f = at_blockout_approved(tmp_path)
    old_folders(tmp_path)
    bh = write_status(tmp_path, {
        "stage": "model", "state": "todo", "versions": {"blockout": 1, "views_front": 2, "views_rest": 2},
        "approved": {"blockout": 1, "views_front": 2, "views_rest": 2},
        "approved_hash": {"blockout": None, "views_front": "aa", "views_rest": "bb"},
        "approved_at": {"blockout": "2026-11-10 09:00", "views_front": "2026-11-10 10:00",
                        "views_rest": "2026-11-10 11:00"},
        "rejected": {"blockout": [], "views_front": [1], "views_rest": [1]},
        "inputs": {"views_front": {"v2": {"blockout": {"v": 1, "hash": "BH"}, "profile": "786cfc66bdd2"}},
                   "views_rest": {"v2": {"blockout": {"v": 1, "hash": "BH"}, "views_front": {"v": 2, "hash": "aa"}}}},
        "dispatches": [{"step": "views_front", "v": 2, "role": "worker", "model": None, "at": "2026-11-10 09:30:00",
                        "ingested": "2026-11-10 09:40:00"},
                       {"step": "views_rest", "v": 2, "role": "reviewer", "model": None, "at": "2026-11-10 10:30:00",
                        "ingested": "2026-11-10 10:40:00"}],
        "offer_log": [{"key": "pilot-house-views_rest-v2-1", "step": "views_rest", "v": 2, "why": "duyệt",
                       "at": "2026-11-10 10:41", "decision": "approve", "decided": "2026-11-10 11:00"}],
        "decisions": {"views_rest v2": {"action": "approve", "at": "2026-11-10 11:00"}},
        "stalls": [{"step": "views_rest", "v": 2, "role": "worker", "at": "2026-11-10 10:10"}],
        "stale": {"views_rest v1": "views_front v1"}, "prior": {}, "reopened": {"regen_front": 1}})
    st = st_of(tmp_path)
    st["approved_hash"]["blockout"] = bh
    st["inputs"]["views_front"]["v2"]["blockout"]["hash"] = bh
    (tmp_path / A / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    model_v1 = tmp_path / A / "model/v1"
    model_v1.mkdir(parents=True)
    (model_v1 / "findings.json").write_text(json.dumps({"version": 1, "base": None, "top_fix": None, "pick": None,
                                                        "next_id": 1, "findings": {},
                                                        "resolved_notes": ["views_rest v2 F2"]}), encoding="utf-8")
    old_rubric(tmp_path)
    return f


def test_every_command_on_an_old_asset_stops_with_one_line_naming_migrate_and_next_still_lists_it(case_b):
    assert case_b.p("brief", AID, ok=False) == f"LỖI: {LINE}\n"
    assert case_b.p("feedback", AID, "x", "--action", "redo", "--step", "model", ok=False) == f"LỖI: {LINE}\n"
    assert f"[{AID}] model/todo → {LINE}" in case_b.p("next").splitlines()


def test_validate_names_the_old_asset_and_the_command_and_exits_1(case_b):
    r = subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), "validate"], cwd=case_b.root, capture_output=True,
                       text=True)
    assert (r.returncode, LINE in r.stdout.splitlines()) == (1, True)


def test_an_old_asset_never_stops_next_or_the_board_for_another_asset(case_b, monkeypatch):
    case_b.p("new", "house-b", "--title", "House B")
    out = case_b.p("next").splitlines()
    assert [l for l in out if l.startswith("[house-b]")] == [
        "[house-b] blockout/draft → chờ người dùng duyệt brief + rubric → `ready house-b`"]
    from core import board
    from core.state import load_cfg
    monkeypatch.chdir(case_b.root)
    assert [a["id"] for a in board.board_payload(load_cfg())["assets"]] == ["house-b"]


def test_b_the_approved_pair_becomes_one_approved_views_v1_and_the_asset_continues_at_model(case_b):
    out = case_b.p("migrate", AID)
    assert out == (f"{AID}: views_front v2 + views_rest v2 → views v1 (đã duyệt), thư mục cũ giữ nguyên; rubric.md có "
                   f"mục ## views. Tiếp: giao worker → `brief {AID}`\n")
    st = st_of(case_b.root)
    assert {k: st[k] for k in ("stage", "state", "versions", "approved", "rejected", "prior", "stale", "reopened")} == {
        "stage": "model", "state": "todo", "versions": {"blockout": 1, "views": 1},
        "approved": {"blockout": 1, "views": 1}, "rejected": {"blockout": [], "views": []}, "prior": {}, "stale": {},
        "reopened": {}}
    assert (st["approved_at"]["views"], sorted(st["inputs"]), st["inputs"]["views"]["v1"]["blockout"]["v"]) == (
        "2026-11-10 11:00", ["views"], 1)
    assert [x["step"] for x in st["dispatches"]] == ["views", "views"]
    assert ([x["step"] for x in st["offer_log"]], [x["step"] for x in st["stalls"]], list(st["decisions"])) == (
        ["views"], ["views"], ["views_rest v2"])
    assert not [k for f in ("versions", "approved", "approved_hash", "approved_at", "rejected", "inputs", "prior")
                for k in st.get(f, {}) if k in OLD]
    final = case_b.root / A / "views/v1/final"
    assert sorted(p.relative_to(final).as_posix() for p in final.rglob("*") if p.is_file()) == [
        "README.md", "back.png", "bg_color.json", "front.png", "guides/back_guide.png", "guides/front_guide.png",
        "guides/views.json", "left.png", "report/VIEWS.md", "report/VIEWS_sheet.png", "right.png"]
    assert all((case_b.root / A / s / "v2/final").is_dir() for s in OLD)


def test_b_the_merged_folder_is_approved_with_its_own_hash_so_a_later_brief_checks_it(case_b, monkeypatch):
    case_b.p("migrate", AID)
    from core.hashes import tree_hash
    monkeypatch.chdir(case_b.root)
    assert st_of(case_b.root)["approved_hash"]["views"] == tree_hash(case_b.root / A / "views/v1/final")


def test_b_the_merged_readme_keeps_the_front_exception_and_the_findings_keep_their_ids(case_b, monkeypatch):
    case_b.p("migrate", AID)
    monkeypatch.chdir(case_b.root)
    import assemble
    st = st_of(case_b.root)
    assert assemble.exceptions(st)[:2] == ["- measure.json — front (ảnh lần 2): iou 0.81", "- back: đầu cột xám"]
    doc = json.loads((case_b.root / A / "views/v1/findings.json").read_text(encoding="utf-8"))
    assert {i: (f["kind"], f["region"]) for i, f in doc["findings"].items()} == {
        "F2": ("note_texture", "back: đầu cột xám"), "F3": ("regen", "front: đinh mờ")}
    assert json.loads((case_b.root / A / "model/v1/findings.json").read_text(encoding="utf-8"))["resolved_notes"] == [
        "views v1 F2"]
    assert assemble.open_work(st | {"approved": st["approved"] | {"model": 1}}) == [
        "- views v1 F3 [minor] front: đinh mờ: đinh rõ hơn"]


def test_b_the_model_brief_lists_the_one_views_folder_and_the_real_tools_find_every_view_file(case_b):
    """N7: the consumers read the merged folder; the model check_inputs wants front and the sides of the card."""
    case_b.p("migrate", AID)
    out = case_b.brief("m1 brief")
    text = case_b.cp["m1 brief"]["text"]
    assert f"8. Đầu ra đã duyệt của bước `views`: `{A}/views/v1/final/`." in text.splitlines()
    assert "views_front" not in text and "views_rest" not in text
    vd = case_b.root / A / "views/v1/final"
    tools = SCRIPTS.parent / "agents"
    for agent, extra in (("zps-3dp-step-model", []), ("zps-3dp-step-texture", ["--model", case_b.root / A / "model/v1/final"])):
        r = subprocess.run([sys.executable, str(tools / agent / "tools/check_inputs.py"), "--final",
                            case_b.root / A / "model/v1/final", "--blockout", case_b.root / A / "blockout/v1/final",
                            "--views", vd, "--concept", case_b.root / "concepts/_approved" / AID, *map(str, extra)],
                           cwd=case_b.root, capture_output=True, text=True)
        rep = json.loads((case_b.root / A / "model/v1/final/review/checks/inputs.json").read_text(encoding="utf-8"))
        views = [c for c in rep["checks"] if c["check"] in ("inputs.views", "inputs.missing")]
        assert len(views) == 1 and [v for v in views[0]["value"] if str(v).startswith(("views/", str(vd)))] == [], (
            agent, r.stdout)
    assert out["brief"] == f"{A}/model/v1/brief-worker.md"


def test_b_migrate_twice_changes_nothing_more(case_b):
    case_b.p("migrate", AID)
    st = st_of(case_b.root)
    assert case_b.p("migrate", AID) == f"{AID}: không có bước view cũ, không đổi gì\n"
    assert {k: v for k, v in st_of(case_b.root).items() if k != "updated"} == {k: v for k, v in st.items() if k != "updated"}


def test_the_old_rubric_gets_one_views_section_with_the_keys_of_the_old_set_section(case_b):
    case_b.p("migrate", AID)
    text = (case_b.root / A / "rubric.md").read_text(encoding="utf-8")
    assert "## views_front" not in text and "## views_rest" not in text
    assert text.split("## views\n", 1)[1].split("\n## ", 1)[0].strip().splitlines() == [
        "- style: view mới giống concept", "- sync: cùng màu như front", "- props: đủ số"]


MID = {
    "views_rest running": ("views_rest", "running", {"views_front": 2, "views_rest": 1}, {"views_front": 2}),
    "views_rest review": ("views_rest", "review", {"views_front": 2, "views_rest": 1}, {"views_front": 2}),
    "views_rest fix": ("views_rest", "fix", {"views_front": 2, "views_rest": 1}, {"views_front": 2}),
    "views_rest waiting_human": ("views_rest", "waiting_human", {"views_front": 2, "views_rest": 1}, {"views_front": 2}),
    "views_front running": ("views_front", "running", {"views_front": 1}, {}),
    "views_front reviewing": ("views_front", "reviewing", {"views_front": 1}, {}),
}


@pytest.mark.parametrize("name", MID)
def test_c_an_asset_in_the_middle_of_an_old_step_restarts_as_the_views_step_and_keeps_the_old_folders(tmp_path, name):
    stage, state, versions, approved = MID[name]
    f = at_blockout_approved(tmp_path)
    old_folders(tmp_path)
    bh = write_status(tmp_path, {
        "stage": stage, "state": state, "versions": {"blockout": 1, **versions},
        "approved": {"blockout": 1, **approved}, "approved_hash": {"blockout": None, **{k: "aa" for k in approved}},
        "rejected": {"blockout": [], **{k: [1] for k in approved}}, "fix_round": 1 if state == "fix" else 0,
        "fix_base": 1 if state == "fix" else None, "round_versions": [1], "offer": 1 if state == "waiting_human" else None,
        "offer_key": "pilot-house-views_rest-v1-1" if state == "waiting_human" else None, "label": "", "note": "đang làm",
        "worker_agent_id": "w-old", "inputs": {stage: {"v1": {"blockout": {"v": 1, "hash": "BH"}}}},
        "dispatches": [{"step": stage, "v": versions[stage], "role": "worker", "model": None, "at": "2026-11-10 10:00:00"}],
        "offer_log": [], "decisions": {}, "stalls": [], "stale": {}, "prior": {}, "reopened": {}})
    st = st_of(tmp_path)
    st["approved_hash"]["blockout"] = bh
    (tmp_path / A / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    assert f"[{AID}] {stage}/{state} → {LINE}" in f.p("next").splitlines()
    assert f.p("migrate", AID) == (f"{AID}: {stage} {state} của v0.7.1 làm lại thành bước views, thư mục cũ giữ "
                                   f"nguyên → views/todo. Tiếp: giao worker → `brief {AID}`\n")
    st = st_of(tmp_path)
    assert {k: st[k] for k in ("stage", "state", "versions", "approved", "fix_round", "fix_base", "offer",
                               "worker_agent_id")} == {
        "stage": "views", "state": "todo", "versions": {"blockout": 1}, "approved": {"blockout": 1}, "fix_round": 0,
        "fix_base": None, "offer": None, "worker_agent_id": None}
    assert (st["dispatches"][0]["step"], "ended" in st["dispatches"][0]) == ("views", True)
    assert all((tmp_path / A / s).is_dir() for s in OLD)
    assert json.loads(f.p("brief", AID))["brief"] == f"{A}/views/v1/brief-worker.md"


def test_a_blockout_redone_after_the_old_set_was_approved_keeps_the_pair_as_the_prior_views(tmp_path):
    """The old pair stays the "Bản đã duyệt trước" of the next views build, so unchanged views cost no Codex call."""
    f = at_blockout_approved(tmp_path)
    old_folders(tmp_path, 3, 2)
    bh = write_status(tmp_path, {
        "stage": "blockout", "state": "waiting_human", "versions": {"blockout": 2, "views_front": 3, "views_rest": 2},
        "approved": {"blockout": 1}, "approved_hash": {"blockout": None}, "rejected": {}, "offer": 2,
        "offer_key": "pilot-house-blockout-v2-1", "label": "", "note": "duyệt blockout v2",
        "inputs": {}, "dispatches": [], "offer_log": [], "decisions": {}, "stalls": [],
        "stale": {"views_front v3": "blockout v1"}, "prior": {"views_front": 3, "views_rest": 2}, "reopened": {}})
    st = st_of(tmp_path)
    st["approved_hash"]["blockout"] = bh
    (tmp_path / A / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    assert f.p("migrate", AID).startswith(f"{AID}: views_front v3 + views_rest v2 → views v1 (bản đã duyệt trước)")
    st = st_of(tmp_path)
    assert {k: st[k] for k in ("stage", "state", "versions", "approved", "prior")} == {
        "stage": "blockout", "state": "waiting_human", "versions": {"blockout": 2, "views": 1},
        "approved": {"blockout": 1}, "prior": {"views": 1}}
    assert (tmp_path / A / "views/v1/final/front.png").is_file()


@pytest.mark.parametrize("card", ["views: full", "views: none"])
def test_a_an_asset_before_the_view_steps_or_without_views_needs_nothing(tmp_path, card):
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    p = tmp_path / "concepts/_approved" / AID / "asset-card.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("views: full", card), encoding="utf-8")
    f.p("intake", AID)
    f.p("ready", AID)
    before = st_of(tmp_path)
    assert LINE not in f.p("next")
    assert f.p("migrate", AID) == f"{AID}: không có bước view cũ, không đổi gì\n"
    assert st_of(tmp_path) == before


def test_an_old_pipeline_toml_is_one_line_that_says_how_to_update_it_not_a_key_error(tmp_path):
    pilot_project(tmp_path)
    p = tmp_path / "production/pipeline.toml"
    text = p.read_text(encoding="utf-8")
    old = ('[[steps]]\nid = "views_front"\nagent = "step-views"\nreviewer = "check-views"\ngate = "review"\n'
           'inputs = ["blockout"]\n\n[[steps]]\nid = "views_rest"\nagent = "step-views"\nreviewer = "check-views"\n'
           'gate = "review_human"\ninputs = ["blockout", "views_front"]\n\n')
    head, tail = text.split('[[steps]]\nid = "views"\n', 1)
    p.write_text(head + old + "[[steps]]\nid = \"model\"\n" + tail.split('[[steps]]\nid = "model"\n', 1)[1]
                 .replace('inputs = ["blockout", "views"]', 'inputs = ["blockout", "views_front", "views_rest"]', 1)
                 .replace('inputs = ["blockout", "views", "model"]', 'inputs = ["blockout", "views_front", "views_rest", "model"]', 1)
                 .replace('review_inputs = ["views"]', 'review_inputs = ["views_rest"]', 1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), "next"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr) == (1, (
        "LỖI: production/pipeline.toml của v0.7.1 có bước views_front, views_rest: thay hai khối [[steps]] đó bằng "
        "khối `views` của zps-3dp-producer/templates/pipeline.toml, đổi hai id đó thành `views` trong inputs, review_inputs của model "
        "và texture, rồi chạy `migrate <id>` cho mỗi asset mà `next` nêu (references/setup.md, mục Nâng cấp từ v0.7.1)\n"))


def test_a_pipeline_toml_updated_only_for_views_stops_with_one_line_naming_the_keys_still_missing(tmp_path):
    """The upgrade steps once named only the view blocks. A texture fix round of such a file gets an empty final/: the
    brief copies final/ only with fix_copy_exclude, and the agent no longer copies it by hand. The worker results that
    ingest needs are missing from the old outputs, so a check that never ran would pass."""
    pilot_project(tmp_path)
    p = tmp_path / "production/pipeline.toml"
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'\nacceptable = \["proportion.json".*\n', "\n", text, count=1)
    text = re.sub(r'\nfix_copy_exclude = \[[^\]]*\]\n', "\n", text, count=1)
    text = re.sub(r'(\nid = "blockout"\n(?:.*\n)*?outputs = )\[[^\]]*\]',
                  r'\1["final/part_graph.json", "final/parts_lib.py", "final/assembled.glb", "final/sources.json", '
                  r'"final/blockout.md"]', text, count=1)
    p.write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), "next"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr) == (1, (
        "LỖI: production/pipeline.toml cũ hơn skill: blockout thiếu outputs (8 JSON kết quả); texture thiếu "
        "fix_copy_exclude: chép các khóa đó từ zps-3dp-producer/templates/pipeline.toml (references/setup.md, mục "
        "Nâng cấp từ v0.7.1)\n"))


def test_a_pipeline_toml_without_the_keys_that_have_a_safe_default_still_runs(tmp_path):
    """No acceptable sends every check fail back to the worker and then asks the human, which the ledger shows; the
    per-step reviewer_model and max_direct_rounds fall back to [review] and 2."""
    pilot_project(tmp_path)
    p = tmp_path / "production/pipeline.toml"
    text = re.sub(r'\nacceptable = \[[^\]]*\]\n', "\n", p.read_text(encoding="utf-8"))
    text = re.sub(r'\n(reviewer_model|max_direct_rounds) = .*\n', "\n", text)
    p.write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), "next"], cwd=tmp_path, capture_output=True, text=True)
    assert (r.returncode, r.stderr) == (0, "")


def validate(root: Path) -> list[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), "validate"], cwd=root, capture_output=True,
                          text=True).stdout.splitlines()


def test_a_an_asset_before_the_views_step_with_the_old_rubric_is_named_by_validate_and_migrate_fixes_only_its_rubric(
        tmp_path):
    """Its status.json is clean, but its next views brief would point at a `## views` its rubric.md lacks."""
    f = Flow(tmp_path)
    pilot_project(tmp_path)
    f.p("intake", AID)
    f.p("ready", AID)
    old_rubric(tmp_path)
    before = st_of(tmp_path)
    line = f"{AID}: rubric.md của v0.7.1 còn mục views_front, views_rest → chạy `migrate {AID}`"
    assert line in validate(tmp_path)
    assert f.p("migrate", AID) == f"{AID}: không có bước view cũ, không đổi gì; rubric.md có mục ## views\n"
    assert (st_of(tmp_path), [l for l in validate(tmp_path) if l.startswith(AID)]) == (before, [])


def test_b_a_model_worker_dispatched_by_v0_7_1_is_ingested_after_migrate_because_the_old_folders_stay(case_b, monkeypatch):
    """The open model dispatch recorded the hashes of the two old finals; they are still on disk and unchanged."""
    from core.hashes import tree_hash
    from flowkit import put_all, OUTPUTS
    monkeypatch.chdir(case_b.root)
    st = st_of(case_b.root)
    ph = st["inputs"]["views_front"]["v2"]["profile"]
    old = {s: {"v": 2, "hash": tree_hash(case_b.root / A / f"{s}/v2/final")} for s in OLD}
    st |= {"state": "running", "versions": st["versions"] | {"model": 1}, "dispatch_out": None,
           "inputs": st["inputs"] | {"model": {"v1": {"blockout": {"v": 1, "hash": st["approved_hash"]["blockout"]},
                                                       **old, "profile": ph}}},
           "dispatches": st["dispatches"] + [{"step": "model", "v": 1, "role": "worker", "model": None,
                                              "at": "2026-11-11 09:00:00", "brief": f"{A}/model/v1/brief-worker.md"}]}
    (case_b.root / A / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    case_b.p("migrate", AID)
    vd = case_b.root / A / "model/v1"
    put_all(vd / "final", "model", OUTPUTS["model"], "m1")
    import glbkit
    glbkit.write(vd / "final" / f"{AID}-untextured.glb", *glbkit.box((1.0, 1.0, 1.0)))
    (vd / "worker-out.md").write_text(f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: none\nPROFILE_HASH: {ph}\n",
                                      encoding="utf-8")
    assert case_b.p("ingest", AID).splitlines()[0] == (
        f"{AID}: worker DONE → model/review. Tiếp: giao reviewer → `brief {AID}`")


def test_a_pair_whose_final_is_gone_stops_migrate_with_one_line_and_changes_nothing(case_b):
    shutil.rmtree(case_b.root / A / "views_front/v2/final")
    before = st_of(case_b.root)
    assert case_b.p("migrate", AID, ok=False) == (
        f"LỖI: {AID}: thiếu {A}/views_front/v2/final: không gộp được bộ view cũ; làm lại bước views bằng tay "
        "(references/setup.md)\n")
    assert st_of(case_b.root) == before
