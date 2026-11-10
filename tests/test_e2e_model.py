"""End-to-end GĐ 3 on the synthetic pilot: the real CLI from the views_rest approval through model fix rounds (structure,
then param with variants and PICK) to DUYỆT 1 and the mesh lock; then texture enabled for one fake round, where a
fix_uv_mesh reopens the approved model although a regen_front already ran in the same feedback round. Fake agents."""
import hashlib
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from shared import P, finding, fixed_line, model_only, pilot_project, report, run

AID = "pilot-house"
A = f"production/assets/{AID}"
SKILL = P.parents[1]
OUTPUTS = {
    "blockout": ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"),
    "views_front": ("front.png", "guides/views.json", "concept_colors.json", "bg_color.json", "report/report.json",
                    "report/VIEWS.md"),
    "views_rest": ("back.png", "left.png", "right.png", "top.png", "README.md", "report/report.json", "report/VIEWS.md",
                   "report/VIEWS_sheet.png"),
    "model": (f"{AID}-untextured.glb", f"{AID}.blend", "part_graph.json", "parts_lib.py", "spec.json", "model.md",
              "review/model_sheet.png", "review/renders/renders.json"),
    "texture": ("albedo_2048.png", "texture_spec.json", "notes.md", "final_lit_vs_concept.png", "review/renders.json",
                "review/checks/tex_measure.json"),
}
ISSUES = "mái chìa 0.35 m đo trên concept_shadow, thẻ không ghi"
SEEN = "clay_front.png, clay_lit_34.png, detail.json"
BRIEF_MAX = 4096
# D31.1: real PNGs, so the reviewer briefs of these steps carry the sheet paths (largest briefs: PICK, COMPARE, base sheet).
SHEET_RENDERS = {"blockout": ["review/game_cam.png", "review/renders/clay_front.png"],
                 "model": ["review/lit_34_front.png", "review/thumb.png", "review/renders/clay_front.png"]}


def counts(major=0):
    return f"blocker=0; major={major}; minor=0; preference=0; unclear=0"


def mf(n, kind, region, prio="major", evidence="clay_front.png: thiếu"):
    return finding(f"F{n}", prio, kind, region=region, evidence=evidence)


def glb(name, tag="a"):
    return f"{AID}-untextured.glb {name} phương án {tag}\n".encode()


class Flow:
    def __init__(self, root: Path):
        self.root, self.cp = root, {}

    def p(self, *args):
        return run(self.root, *args)

    def st(self):
        return json.loads((self.root / A / "status.json").read_text(encoding="utf-8"))

    def doc(self, step, n):
        return json.loads((self.root / A / f"{step}/v{n}/findings.json").read_text(encoding="utf-8"))

    def keep(self, name, out, **kw):
        self.cp[name] = {"out": out, "st": self.st(), **kw}

    def brief(self, name):
        out = json.loads(self.p("brief", AID))
        self.keep(name, out, text=(self.root / out["brief"]).read_text(encoding="utf-8"))
        return out

    def work(self, name, issues="none", variants=(), failing=False):
        out = self.brief(name + " brief")
        vd = (self.root / out["report"]).parent
        step = self.st()["stage"]
        for sub, tag in (("final", "a"), *((f"variants/{x}", x) for x in variants)):
            for o in OUTPUTS[step]:
                (vd / sub / o).parent.mkdir(parents=True, exist_ok=True)
                (vd / sub / o).write_text(f"{o} {name} phương án {tag}\n", encoding="utf-8")
            if step in SHEET_RENDERS:
                for r in SHEET_RENDERS[step]:
                    (vd / sub / r).parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (64, 48), (120, 80, 40)).save(vd / sub / r)
        if failing:
            (vd / "final/review/checks").mkdir(parents=True)
            (vd / "final/review/checks/qa_screen_tris_check.json").write_text(json.dumps({
                "tool": "asset_checks/screen_tris_check", "overall": "fail"}), encoding="utf-8")
            (vd / "final/review/checks/detail.json").write_text(json.dumps({"overall": "pass"}), encoding="utf-8")
            (vd / "final/README.md").write_text("## NGOẠI LỆ\n- qa_screen_tris_check.json — 6% tam giác nhỏ ở mép mái\n",
                                                encoding="utf-8")
        ph = re.search(r"^PROFILE_HASH: (\w+)$", self.cp[name + " brief"]["text"], re.M).group(1)
        accepted = "ACCEPTED_FAIL: qa_screen_tris_check.json — 6% tam giác nhỏ ở mép mái\n" if failing else ""
        (self.root / out["report"]).write_text(
            f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: {issues}\nPROFILE_HASH: {ph}\n" + accepted
            + fixed_line(self.root, AID), encoding="utf-8")
        self.keep(name + " worker", self.p("ingest", AID, "--agent-id", f"w-{name}"))

    def review(self, name, **kw):
        out = self.brief(name + " review brief")
        (self.root / out["report"]).write_text(report(**{"evidence": SEEN, "rubric": "mass=pass"} | kw), encoding="utf-8")
        self.keep(name + " review", self.p("ingest", AID))

    def human(self, name, *args):
        self.keep(name, self.p("feedback", AID, *args))


def enable(root: Path, step: str):
    p = root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace(f'id = "{step}"\nenabled = false\n', f'id = "{step}"\n', 1),
                 encoding="utf-8")


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("model")
    f = Flow(root)
    pilot_project(root)
    model_only(root)
    (root / ".env").write_text("MESHY_API_KEY=msy-test-only\n", encoding="utf-8")
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    f.review("b1", verdict="PASS", counts=counts(), top_fix=None)
    f.human("approve blockout", "đạt", "--action", "approve")
    f.work("vf1")
    f.review("vf1", verdict="PASS", counts=counts(), top_fix=None)
    f.work("vr1")
    f.review("vr1", counts=counts(1), top_fix="regen_front: F1",
             findings=[finding("F1", "major", "regen_front", region="front: gỗ đỏ hơn back", evidence="front.png: đỏ")],
             evidence="front.png, back.png")
    f.work("vf2")
    f.review("vf2", verdict="PASS", counts=counts(), top_fix=None, compare="F1=better",
             prior=["- F1: resolved | evidence: clay_front.png"])
    f.work("vr2")
    f.review("vr2", verdict="PASS", counts=counts(), top_fix=None)
    f.human("approve set", "đạt", "--action", "approve")

    f.work("m1", issues=ISSUES, failing=True)
    f.review("m1", counts=counts(2), top_fix="structure: F1",
             findings=[mf(1, "structure", "mái: thiếu diềm"), mf(2, "param", "mái: chìa 0.2 m")])
    f.work("m2")
    f.review("m2", counts=counts(1), top_fix="param: F2", compare="F1=better",
             prior=["- F1: resolved | evidence: clay_front.png", "- F2: open"])
    f.work("m3", issues=ISSUES, variants=("b", "c"))
    f.review("m3", verdict="PASS", counts=counts(), top_fix=None, compare="F2=better", pick="b",
             prior=["- F2: resolved | evidence: v3b/clay_front.png"], evidence=SEEN + ", v3b/clay_front.png")
    f.cp["m3 files"] = {p: (root / A / "model/v3" / p).read_bytes() if (root / A / "model/v3" / p).is_file() else None
                        for p in (f"final/{AID}-untextured.glb", f"variants/a/{AID}-untextured.glb")}
    f.human("approve model", "đạt", "--action", "approve")

    enable(root, "texture")
    f.keep("retry", f.p("retry", AID))
    f.work("t1")
    f.review("t1", counts=counts(1), top_fix="fix_uv_mesh: F1", rubric="uv=fail",
             findings=[mf(1, "fix_uv_mesh", "mái: UV kéo giãn", evidence="clay_lit_34.png: vân mái giãn")])
    f.cp["model v3 doc"] = f.doc("model", 3)
    f.work("m4")
    f.review("m4", verdict="PASS", counts=counts(), top_fix=None, compare="F3=better",
             prior=["- F3: resolved | evidence: clay_lit_34.png"])
    f.human("approve model v4", "đạt", "--action", "approve")
    f.work("t2", issues="none")
    f.review("t2", counts=counts(1), top_fix="fix_uv_mesh: F1", rubric="uv=fail",
             findings=[mf(1, "fix_uv_mesh", "cửa: UV lệch", evidence="clay_lit_34.png: lệch")])
    f.human("redo texture", "UV cửa vẫn lệch", "--action", "redo")
    f.brief("t3 brief")
    f.cp["root"] = root
    return f.cp


def pick(st, *keys):
    return {k: st.get(k) for k in keys}


def missing(text, *wanted):
    return [w for w in wanted if w not in text.splitlines()]


def moved(out: str) -> tuple[str, str]:
    """D30.5: a feedback or retry that moves the asset prints its line, then the next dispatch: (line, brief path)."""
    head, line = out.splitlines()
    return head, json.loads(line)["brief"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_approving_the_view_set_moves_on_to_the_model_step(flow):
    assert moved(flow["approve set"]["out"]) == (
        "pilot-house: đã duyệt views_rest v2 → model/todo. Tiếp: giao worker → `brief pilot-house`",
        f"{A}/model/v1/brief-worker.md")


def test_the_model_brief_names_the_three_approved_finals_and_only_the_concept_files_the_model_reads(flow):
    b = flow["m1 brief"]
    assert b["out"] == {"role": "worker", "agent": "zps-3dp-step-model", "model": "opus", "resume": None,
                        "brief": f"{A}/model/v1/brief-worker.md", "report": f"{A}/model/v1/worker-out.md"}
    assert missing(b["text"], f"TOOLS: {SKILL / 'agents/zps-3dp-step-model/tools'}", "BLENDER: blender",
                   "PILOT: none (pilot_asset: null): so với pilot ghi not_checked",
                   f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v1/final/`.",
                   f"8. Đầu ra đã duyệt của bước `views_front`: `{A}/views_front/v2/final/`.",
                   f"9. Đầu ra đã duyệt của bước `views_rest`: `{A}/views_rest/v2/final/`.") == []
    concept = [l for l in b["text"].splitlines() if "Concept đã duyệt" in l]
    assert len(concept) == 1 and concept[0].endswith(
        ": chỉ đọc `concept_albedo.png`, `concept_shadow.png`, `asset-card.yaml`. Bỏ qua file và thư mục khác (bản nháp cũ).")
    assert "GEN_IMAGE" not in b["text"] and "material.md" not in b["text"]


def test_the_required_outputs_carry_the_asset_id_so_a_missing_mesh_blocks_ingest(flow):
    req = [l for l in flow["m1 brief"]["text"].splitlines() if l.startswith("- Bắt buộc có")]
    assert req == [f"- Bắt buộc có (tính từ `{A}/model/v1/`): `final/pilot-house-untextured.glb`, `final/pilot-house.blend`, "
                   "`final/part_graph.json`, `final/parts_lib.py`, `final/spec.json`, `final/model.md`, "
                   "`final/review/model_sheet.png`, `final/review/renders/renders.json`."]
    assert flow["m1 worker"]["out"].splitlines()[0] == (
        "pilot-house: worker DONE → model/review. Tiếp: giao reviewer → `brief pilot-house`")


def test_check_clay_reviews_model_against_the_blockout_only_with_the_structure_and_param_kinds(flow):
    """The clay reviewer never opens the views; listing them only spent its tokens."""
    t = flow["m1 review brief"]["text"]
    assert flow["m1 review brief"]["out"]["agent"] == "zps-3dp-check-clay"
    assert [l for l in t.splitlines() if l.startswith("- Đầu ra đã duyệt")] == [
        f"- Đầu ra đã duyệt của bước `blockout` (đầu vào, không chấm lại): `{A}/blockout/v1/final/`."]
    assert [l.split(": chỉ ")[1] for l in t.splitlines() if l.startswith("- Concept đã duyệt")] == [
        "`concept_albedo.png`, `concept_shadow.png`, `asset-card.yaml`."]
    assert missing(t,
                   "- F1 [blocker|major|minor|preference|unclear] <structure|param>",
                   "TOP_FIX: <structure|param|need_evidence>: F<n>[, F<m>]") == []


def test_a_structure_fix_resumes_the_worker_from_the_best_version_and_reads_the_failing_kit_qa_first(flow):
    head, line = flow["m1 review"]["out"].splitlines()
    assert head == "pilot-house: review FIX (major=2) → model/fix. Tiếp: giao worker → `brief pilot-house`"
    b = flow["m2 brief"]
    assert json.loads(line) == b["out"]
    assert b["out"]["resume"] == "w-m1"
    assert missing(b["text"],
                   f"10. Bản gốc: `{A}/model/v1/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
                   f"11. Đọc trước nguyên văn lỗi script của bản gốc: `{A}/model/v1/final/review/checks/qa_screen_tris_check.json`.") == []
    assert "`TOP_FIX: structure: F1`" in b["text"]


def test_a_param_fix_offers_variants_and_the_picked_variant_becomes_final(flow):
    b, rv = flow["m3 brief"], flow["m3 review brief"]["text"]
    assert (b["out"]["resume"], pick(flow["m2 review"]["st"], "fix_round", "fix_base")) == (
        "w-m2", {"fix_round": 2, "fix_base": 2})
    assert "`TOP_FIX: param: F2`" in b["text"]
    assert missing(rv, "PICK: a|b|c", f"- Phương án param: `{A}/model/v3/variants/<a|b|c>/`; a là `final/`; sheet "
                   "`review/sheet-<b|c>.png` cạnh sheet trên. Nhãn ảnh trong EVIDENCE_OPENED: `v3a/<ảnh>`, `v3b/<ảnh>`, "
                   "`v3c/<ảnh>`; ảnh bản gốc: `v2/<ảnh>`.",
                   f"- Sheet: `{A}/model/v3/review/sheet.png` (nhãn ô = tên ảnh; ảnh lẻ qua need_evidence). Số liệu: JSON "
                   "trong `final/`, `work/` của v3.",
                   f"- Bản gốc v2: sheet `{A}/model/v2/review/sheet.png`; finding đủ trường `{A}/model/v2/findings.json`.") == []
    # D31.1: one sheet per variant, from the same render list as final/.
    assert [sorted(json.loads((Path(flow["root"]) / A / f"model/v3/review/sheet-{x}.json").read_text(encoding="utf-8")))
            for x in "bc"] == [["clay_front", "lit_34_front", "thumb"]] * 2
    files = flow["m3 files"]
    assert (files[f"final/{AID}-untextured.glb"], files[f"variants/a/{AID}-untextured.glb"]) == (glb("m3", "b"), glb("m3"))


def test_a_model_pass_waits_for_duyet_1_by_the_human(flow):
    assert flow["m3 review"]["out"] == ("pilot-house: review PASS (0 mở) → model/waiting_human. "
                                        "Tiếp: chờ người dùng: duyệt model v3 (review page)\n")


def test_approving_the_model_locks_the_sha256_of_the_picked_untextured_glb(flow):
    s = flow["approve model"]
    assert s["out"] == "pilot-house: đã duyệt model v3 → model/done_enabled. Tiếp: xong các bước đang bật\n"
    assert pick(s["st"], "approved", "rejected", "locked", "note") == {
        "approved": {"blockout": 1, "views_front": 2, "views_rest": 2, "model": 3},
        "rejected": {"blockout": [], "views_front": [1], "views_rest": [1], "model": [1, 2]},
        "locked": {"model": sha(glb("m3", "b"))}, "note": "bước texture chưa bật"}


def test_once_texture_is_enabled_the_parked_asset_moves_on(flow):
    assert moved(flow["retry"]["out"]) == ("pilot-house: → todo. Tiếp: giao worker → `brief pilot-house`",
                                           f"{A}/texture/v1/brief-worker.md")
    assert pick(flow["retry"]["st"], "stage", "state") == {"stage": "texture", "state": "running"}


def test_the_texture_brief_copies_the_approved_model_issues_and_names_every_approved_final_d20_3_d20_10(flow):
    t = flow["t1 brief"]["text"]
    assert missing(t, f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v1/final/`.",
                   f"8. Đầu ra đã duyệt của bước `views_front`: `{A}/views_front/v2/final/`.",
                   f"9. Đầu ra đã duyệt của bước `views_rest`: `{A}/views_rest/v2/final/`.",
                   f"10. Đầu ra đã duyệt của bước `model`: `{A}/model/v3/final/`.",
                   f"11. ISSUES của report worker `model` v3: {ISSUES}") == []
    assert "handoff" not in t.lower()


def test_the_first_fix_uv_mesh_reopens_the_approved_model_although_regen_front_ran_in_this_feedback_round(flow):
    s = flow["t1 review"]
    head, line = s["out"].splitlines()
    assert (head, json.loads(line)["brief"]) == (
        "pilot-house: review FIX (major=1) → model/fix. Tiếp: giao worker → `brief pilot-house`",
        f"{A}/model/v4/brief-worker.md")
    assert pick(s["st"], "stage", "state", "fix_round", "fix_base", "round_versions", "worker_agent_id", "approved",
                "locked", "reopened", "note") == {
        "stage": "model", "state": "running", "fix_round": 1, "fix_base": 3, "round_versions": [3], "worker_agent_id": None,
        "approved": {"blockout": 1, "views_front": 2, "views_rest": 2}, "locked": {},
        "reopened": {"regen_front": 1, "fix_uv_mesh": 1}, "note": "fix_uv_mesh: sửa model v3 theo F3 (texture v1 F1)"}
    doc = flow["model v3 doc"]
    assert (doc["top_fix"], doc["next_id"], doc["findings"]["F3"]["kind"], doc["findings"]["F3"]["evidence"]) == (
        {"kind": "structure", "ids": ["F3"]}, 4, "structure", "texture v1 F1: clay_lit_34.png: vân mái giãn")


def test_the_reopened_model_starts_a_fresh_worker_and_a_new_approval_locks_the_new_mesh(flow):
    assert (flow["m4 brief"]["out"]["resume"], flow["m4 brief"]["out"]["brief"]) == (None, f"{A}/model/v4/brief-worker.md")
    assert "`TOP_FIX: structure: F3`" in flow["m4 brief"]["text"]
    s = flow["approve model v4"]
    assert moved(s["out"]) == ("pilot-house: đã duyệt model v4 → texture/todo. Tiếp: giao worker → `brief pilot-house`",
                               f"{A}/texture/v2/brief-worker.md")
    assert pick(s["st"], "locked", "stale") == {
        "locked": {"model": sha(glb("m4"))}, "stale": {"views_rest v1": "views_front v1", "texture v1": "model v3"}}


def test_a_model_report_without_issues_adds_no_handoff_line_to_the_texture_brief(flow):
    t = flow["t2 brief"]["text"]
    assert f"10. Đầu ra đã duyệt của bước `model`: `{A}/model/v4/final/`." in t.splitlines()
    assert "ISSUES của report worker" not in t


def test_a_second_fix_uv_mesh_in_the_same_feedback_round_goes_to_the_human(flow):
    s = flow["t2 review"]
    assert s["out"] == ("pilot-house: review FIX (major=1) → texture/waiting_human. "
                        "Tiếp: chờ người dùng: fix_uv_mesh lần 2; còn mở: F1 (review page)\n")
    assert pick(s["st"], "stage", "label", "reopened") == {
        "stage": "texture", "label": "chưa đạt", "reopened": {"regen_front": 1, "fix_uv_mesh": 1}}


def test_a_human_redo_of_a_texture_whose_top_fix_is_fix_uv_mesh_tells_the_worker_the_mesh_is_fixed_elsewhere(flow):
    t = flow["t3 brief"]["text"]
    assert pick(flow["redo texture"]["st"], "stage", "state", "reopened") == {
        "stage": "texture", "state": "running", "reopened": {}}
    assert "TOP_FIX" not in t
    assert ("Ưu tiên 1, feedback của người dùng: sửa `H1` (nguyên văn trong `acceptance` của "
            f"`{A}/texture/v2/findings.json` và feedback.md). Đối chiếu từng ý với concept; không bỏ ý nào. "
            "Mesh và UV đã duyệt ở `model`, sửa ngoài bước này: không sửa mesh và UV ở đây.") in t


def test_every_model_brief_stays_under_the_token_budget_without_the_install_and_project_paths(flow):
    strip = (str(Path(flow["root"]).resolve()), str(SKILL))
    sizes = {}
    for k, v in flow.items():
        if isinstance(v, dict) and "text" in v and k[:1] in "mt":
            t = v["text"]
            for s in strip:
                t = t.replace(s, "")
            sizes[k] = len(t.encode())
    assert len(sizes) == 13 and max(sizes.values()) < BRIEF_MAX, sizes
