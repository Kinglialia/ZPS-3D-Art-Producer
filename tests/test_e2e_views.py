"""End-to-end GĐ 2 on the synthetic pilot: the real CLI from blockout approval through views_front and views_rest to
approval, one regen_front round and one blockout redo after the set was approved. Fake agents, no Codex call."""
import json
import re
from pathlib import Path

import pytest

from shared import P, finding, pilot_project, report, run, views_only

AID = "pilot-house"
A = f"production/assets/{AID}"
SKILL = P.parents[1]
OUTPUTS = {
    "blockout": ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"),
    "views_front": ("front.png", "guides/views.json", "concept_colors.json", "bg_color.json", "report/report.json",
                    "report/VIEWS.md"),
    "views_rest": ("back.png", "left.png", "right.png", "top.png", "README.md", "report/report.json", "report/VIEWS.md",
                   "report/VIEWS_sheet.png"),
}
SEEN = "front.png, back.png, report.json"
KEYS = ("stage", "state", "fix_round", "fix_base", "round_versions", "offer", "label", "note", "worker_agent_id",
        "approved", "rejected", "reopened", "prior", "stale")
BRIEF_MAX = 4096
TIMING = r" · (worker|reviewer|script) giao .*$"


def counts(major=0, minor=0):
    return f"blocker=0; major={major}; minor={minor}; preference=0; unclear=0"


def vf(region, kind="regen", prio="major", n=1, **kw):
    return finding(f"F{n}", prio, kind, region=region, evidence=f"{region.split(':')[0]}.png: lệch", **kw)


class Flow:
    def __init__(self, root: Path):
        self.root, self.cp = root, {}

    def p(self, *args):
        return run(self.root, *args)

    def st(self):
        return json.loads((self.root / A / "status.json").read_text(encoding="utf-8"))

    def doc(self, step, n):
        return json.loads((self.root / A / f"{step}/v{n}/findings.json").read_text(encoding="utf-8"))

    def brief(self, name):
        out = json.loads(self.p("brief", AID))
        self.cp[name] = {"out": out, "text": (self.root / out["brief"]).read_text(encoding="utf-8"), "st": self.st()}
        return out

    def work(self, name, failing=False):
        out = self.brief(name + " brief")
        vd = (self.root / out["report"]).parent
        for o in OUTPUTS[self.st()["stage"]]:
            (vd / "final" / o).parent.mkdir(parents=True, exist_ok=True)
            (vd / "final" / o).write_text(f"{o} {name}\n", encoding="utf-8")
        if failing:
            (vd / "final/review/checks").mkdir(parents=True)
            (vd / "final/review/checks/measure.json").write_text(json.dumps({"tool": "views/measure", "overall": "fail"}))
        ph = re.search(r"^PROFILE_HASH: (\w+)$", self.cp[name + " brief"]["text"], re.M).group(1)
        (self.root / out["report"]).write_text(f"STATUS: DONE\nRUBRIC: style=pass\nISSUES: none\nPROFILE_HASH: {ph}\n",
                                               encoding="utf-8")
        self.cp[name + " worker"] = {"out": self.p("ingest", AID, "--agent-id", f"w-{name}"), "st": self.st()}

    def review(self, name, **kw):
        out = self.brief(name + " review brief")
        (self.root / out["report"]).write_text(report(evidence=SEEN, rubric="style=pass", **kw), encoding="utf-8")
        self.cp[name + " review"] = {"out": self.p("ingest", AID), "st": self.st()}

    def human(self, name, *args):
        self.cp[name] = {"out": self.p("feedback", AID, *args), "st": self.st()}


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("views")
    f = Flow(root)
    pilot_project(root)
    views_only(root)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    f.review("b1", verdict="PASS", counts=counts(), top_fix=None)
    f.human("approve blockout", "đạt", "--action", "approve")
    f.work("vf1", failing=True)
    f.review("vf1", counts=counts(1), top_fix="regen: F1", findings=[vf("front: bóng đổ dưới mái")])
    f.work("vf2")
    f.review("vf2", verdict="PASS", counts=counts(), top_fix=None, compare="F1=better",
             prior=["- F1: resolved | evidence: front.png"])
    f.work("vr1")
    f.review("vr1", counts=counts(1, 1), top_fix="regen_front: F1",
             findings=[vf("front: gỗ đỏ hơn back, left", "regen_front"), vf("back: đầu dầm xám", "note_texture", "minor", 2)])
    f.cp["front v2 doc"] = f.doc("views_front", 2)
    f.work("vf3")
    f.review("vf3", verdict="PASS", counts=counts(), top_fix=None, compare="F2=better",
             prior=["- F2: resolved | evidence: front.png"])
    f.work("vr2")
    f.review("vr2", verdict="PASS", counts=counts(0, 1), top_fix=None,
             findings=[vf("back: đầu dầm xám", "note_texture", "minor")])
    f.human("approve set", "đạt", "--action", "approve")
    f.human("redo blockout", "mái cao thêm 20 cm", "--action", "redo", "--step", "blockout")
    f.work("b2")
    f.review("b2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: front.png"])
    f.human("approve blockout v2", "đạt", "--action", "approve")
    f.brief("vf4 brief")
    f.cp["ledger"] = [re.sub(TIMING, "", l.split(" · ", 2)[2]) for l in (root / "production/ledger.md").read_text(encoding="utf-8")
                      .splitlines() if l.startswith("- ")]
    f.cp["root"] = root
    return f.cp


def pick(st):
    return {k: st.get(k) for k in KEYS}


def lines(text, *wanted):
    return [w for w in wanted if w not in text.splitlines()]


def test_approved_blockout_moves_on_to_views_front_instead_of_parking(flow):
    assert flow["approve blockout"]["out"] == ("pilot-house: đã duyệt blockout v1 → views_front/todo. "
                                               "Tiếp: giao worker → `brief pilot-house`\n")


def test_the_front_brief_names_the_approved_blockout_only_the_concept_files_views_need_and_the_codex_call(flow):
    b = flow["vf1 brief"]
    assert b["out"] == {"role": "worker", "agent": "zps-3dp-step-views", "model": "opus", "resume": None,
                        "brief": f"{A}/views_front/v1/brief-worker.md", "report": f"{A}/views_front/v1/report-worker.md"}
    assert lines(b["text"], f"TOOLS: {SKILL / 'agents/zps-3dp-step-views/tools'}", "BLENDER: blender",
                 f"GEN_IMAGE: {SKILL / 'scripts/gen_image_codex.py'}",
                 "GEN_ARGS: --model gpt-6-astra --reasoning medium --pid-file production/pids/codex_image/pilot-house.pid",
                 f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v1/final/`.",
                 f"- Mỗi lệnh Blender: `<lệnh> & echo $! > production/pids/blender/{AID}.pid; wait $!; "
                 f"rm -f production/pids/blender/{AID}.pid`.") == []
    concept = [l for l in b["text"].splitlines() if "Concept đã duyệt" in l]
    assert len(concept) == 1 and concept[0].endswith(
        ": chỉ đọc `concept_albedo.png`, `asset-card.yaml`, `pilot-house.material.md`. Bỏ qua file và thư mục khác (bản nháp cũ).")
    assert (flow["root"] / "production/pids/codex_image").is_dir()


def test_the_front_reviewer_sees_the_blockout_as_input_not_as_work_to_judge(flow):
    t = flow["vf1 review brief"]["text"]
    assert lines(t, f"- Đầu ra đã duyệt của bước `blockout` (đầu vào, không chấm lại): `{A}/blockout/v1/final/`.",
                 "- F1 [blocker|major|minor|preference|unclear] <regen>", "TOP_FIX: <regen|need_evidence>: F<n>[, F<m>]") == []
    assert "region mở đầu bằng" not in t


def test_a_regen_fix_of_the_front_reads_the_failing_measure_json_first_and_resumes_the_worker(flow):
    b = flow["vf2 brief"]
    assert b["out"]["resume"] == "w-vf1"
    assert lines(b["text"], f"8. Bản gốc: `{A}/views_front/v1/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
                 f"9. Đọc trước nguyên văn lỗi script của bản gốc: `{A}/views_front/v1/final/review/checks/measure.json`.",
                 f"10. Sửa đúng `TOP_FIX: regen: F1`; repair, preserve, acceptance của từng id trong "
                 f"`{A}/views_front/v1/findings.json`. Rồi tới feedback mới nhất của người dùng trong feedback.md.") == []


def test_a_front_pass_is_approved_by_the_reviewer_since_views_front_has_no_human_gate(flow):
    assert flow["vf2 review"]["out"] == "pilot-house: review PASS (0 mở) → views_rest/todo. Tiếp: giao worker → `brief pilot-house`\n"
    assert pick(flow["vf2 review"]["st"])["approved"] == {"blockout": 1, "views_front": 2}


def test_the_set_brief_points_at_the_approved_front_folder_without_a_copy_and_needs_no_blender(flow):
    b = flow["vr1 brief"]
    assert (b["out"]["agent"], b["out"]["resume"]) == ("zps-3dp-step-views", None)
    assert lines(b["text"], f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v1/final/`.",
                 f"8. Đầu ra đã duyệt của bước `views_front`: `{A}/views_front/v2/final/`.") == []
    assert "BLENDER:" not in b["text"] and "Mỗi lệnh Blender" not in b["text"]


def test_the_set_reviewer_gets_the_view_region_rule_and_both_inputs(flow):
    assert lines(flow["vr1 review brief"]["text"],
                 f"- Đầu ra đã duyệt của bước `views_front` (đầu vào, không chấm lại): `{A}/views_front/v2/final/`.",
                 "- region mở đầu bằng back|left|right|top, vd `back: mép mái`; `regen_front` nói về đầu ra của "
                 "`views_front`, không theo luật này.",
                 "- F1 [blocker|major|minor|preference|unclear] <regen|regen_front|note_exception|note_texture>") == []


def test_the_set_reviewer_is_told_a_wrong_part_count_is_a_regen_and_preserve_names_the_neighbours_d27_11(flow):
    """Run 4: `back.png` had 2 board rows for 3 and passed as a `note_texture`."""
    assert lines(flow["vr1 review brief"]["text"],
                 "- Sai số thành phần (hàng ván, cửa, trụ) so với concept hoặc `blockout.md`: luôn `regen`, không phải "
                 "`note_exception`, `note_texture`.",
                 "- `preserve`: tên chi tiết cạnh vùng sửa (vd \"nét mực khe nắp\"), không ghi \"giữ phần còn lại\".") == []


def test_regen_front_reopens_the_approved_front_with_a_fresh_worker_and_carries_the_finding_as_its_top_fix(flow):
    assert flow["vr1 review"]["out"] == ("pilot-house: review FIX (major=1 minor=1) → views_front/fix. "
                                         "Tiếp: giao worker → `brief pilot-house`\n")
    assert pick(flow["vr1 review"]["st"]) == {
        "stage": "views_front", "state": "fix", "fix_round": 1, "fix_base": 2, "round_versions": [2], "offer": None,
        "label": "", "note": "regen_front: sửa views_front v2 theo F2 (views_rest v1 F1)", "worker_agent_id": None,
        "approved": {"blockout": 1}, "rejected": {"blockout": []}, "reopened": {"regen_front": 1}, "prior": {},
        "stale": {"views_rest v1": "views_front v2"}}
    doc = flow["front v2 doc"]
    assert {k: doc[k] for k in ("version", "top_fix", "next_id")} == {
        "version": 2, "top_fix": {"kind": "regen", "ids": ["F2"]}, "next_id": 3}
    assert {i: (f["kind"], f["status"], f["first_v"], f["region"], f["evidence"]) for i, f in doc["findings"].items()} == {
        "F1": ("regen", "resolved", 1, "front: bóng đổ dưới mái", "front.png: lệch"),
        "F2": ("regen", "open", 2, "front: gỗ đỏ hơn back, left", "views_rest v1 F1: front.png: lệch")}


def test_the_reopened_front_is_fixed_from_its_approved_version_and_its_reviewer_compares_the_carried_id(flow):
    b, rv = flow["vf3 brief"], flow["vf3 review brief"]["text"]
    assert (b["out"]["brief"], b["out"]["resume"]) == (f"{A}/views_front/v3/brief-worker.md", None)
    assert f"8. Bản gốc: `{A}/views_front/v2/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**" in b["text"]
    assert "Sửa đúng `TOP_FIX: regen: F2`" in b["text"]
    assert "\nCOMPARE: F2=?\n" in rv and "\nPRIOR:\n- F2: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front\n" in rv


def test_the_set_is_rebuilt_from_scratch_after_the_front_changes_because_the_front_is_the_colour_standard(flow):
    b = flow["vr2 brief"]
    assert b["out"]["brief"] == f"{A}/views_rest/v2/brief-worker.md"
    assert f"8. Đầu ra đã duyệt của bước `views_front`: `{A}/views_front/v3/final/`." in b["text"]
    assert "Bản gốc" not in b["text"] and "vòng sửa" not in b["text"]


def test_a_minor_texture_note_does_not_block_the_set_which_then_waits_for_the_human(flow):
    assert flow["vr2 review"]["out"] == ("pilot-house: review PASS (minor=1) → views_rest/waiting_human. "
                                         "Tiếp: chờ người dùng: duyệt views_rest v2 (review page)\n")


def test_approving_the_set_parks_at_done_enabled_before_the_disabled_model_step(flow):
    assert flow["approve set"]["out"] == ("pilot-house: đã duyệt views_rest v2 → views_rest/done_enabled. "
                                          "Tiếp: xong các bước đang bật\n")
    st = flow["approve set"]["st"]
    assert {k: st[k] for k in ("approved", "rejected", "note", "reopened")} == {
        "approved": {"blockout": 1, "views_front": 3, "views_rest": 2},
        "rejected": {"blockout": [], "views_front": [1, 2], "views_rest": [1]}, "note": "bước model chưa bật",
        "reopened": {"regen_front": 1}}


def test_a_blockout_redo_after_the_set_keeps_the_old_views_as_prior_so_the_next_build_reuses_unchanged_ones(flow):
    st = flow["redo blockout"]["st"]
    assert {k: st[k] for k in ("stage", "state", "approved", "prior", "reopened", "worker_agent_id")} == {
        "stage": "blockout", "state": "fix", "approved": {}, "prior": {"views_front": 3, "views_rest": 2},
        "reopened": {}, "worker_agent_id": None}
    assert flow["b2 brief"]["out"]["resume"] is None
    b = flow["vf4 brief"]
    assert b["out"]["brief"] == f"{A}/views_front/v4/brief-worker.md"
    assert lines(b["text"], f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v2/final/`.",
                 f"8. Bản đã duyệt trước của bước này (dựng từ đầu vào cũ): `{A}/views_front/v3/final/`. "
                 "Giữ phần có đầu vào không đổi, theo file agent.") == []
    assert {k: b["st"][k] for k in ("prior", "stale")} == {
        "prior": {"views_front": 3, "views_rest": 2}, "stale": {"views_front v1": "blockout v1", "views_front v2": "blockout v1",
                                              "views_front v3": "blockout v1", "views_rest v1": "views_front v2",
                                              "views_rest v2": "views_front v3"}}


def test_the_ledger_records_the_reopen_with_the_carried_id(flow):
    def rnd(step, n, review, aid="pilot-house", by_reviewer=False):
        agent = "blockout" if step == "blockout" else "views"
        return [f"{aid} · {step} v{n} · giao worker (zps-3dp-step-{agent}, opus)",
                f"{aid} · {step} v{n} · worker DONE · style=pass",
                f"{aid} · {step} v{n} · giao reviewer (zps-3dp-check-{agent}, opus)",
                *([f"{aid} · {step} v{n} · duyệt bởi reviewer"] if by_reviewer else []),
                f"{aid} · {step} v{n} · review {review}"]
    assert flow["ledger"] == [
        "pilot-house · tạo mới (draft, rubric chưa duyệt)", "pilot-house · ready",
        *rnd("blockout", 1, "PASS (0 mở) · style=pass"),
        "pilot-house · blockout v1 · duyệt bởi người dùng", "pilot-house · người dùng approve blockout · đạt",
        *rnd("views_front", 1, "FIX (major=1) · style=pass"),
        *rnd("views_front", 2, "PASS (0 mở) · style=pass", by_reviewer=True),
        *rnd("views_rest", 1, "FIX (major=1 minor=1) · style=pass · regen_front → views_front v2 F2"),
        *rnd("views_front", 3, "PASS (0 mở) · style=pass", by_reviewer=True),
        *rnd("views_rest", 2, "PASS (minor=1) · style=pass"),
        "pilot-house · views_rest v2 · duyệt bởi người dùng", "pilot-house · người dùng approve views_rest · đạt",
        "pilot-house · người dùng redo blockout · mái cao thêm 20 cm",
        *rnd("blockout", 2, "PASS (0 mở) · style=pass"),
        "pilot-house · blockout v2 · duyệt bởi người dùng", "pilot-house · người dùng approve blockout · đạt",
        "pilot-house · views_front v4 · giao worker (zps-3dp-step-views, opus)"]


def test_every_views_brief_stays_under_the_token_budget_without_the_install_and_project_paths(flow):
    strip = (str(Path(flow["root"]).resolve()), str(SKILL))
    sizes = {}
    for k, v in flow.items():
        if isinstance(v, dict) and "text" in v:
            t = v["text"]
            for s in strip:
                t = t.replace(s, "")
            sizes[k] = len(t.encode())
    assert len(sizes) == 15 and max(sizes.values()) < BRIEF_MAX, sizes
