"""End-to-end GĐ 2 on the synthetic pilot: the real CLI from blockout approval through the one `views` step to the human
approval. One regen round that names the front, one crop served from the sheet, one human redo, and one blockout redo
after the set was approved. Fake agents, no Codex call (D44.3)."""
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from flowkit import put_all
from shared import P, finding, fixed_line, pilot_project, report, run, views_only

AID = "pilot-house"
A = f"production/assets/{AID}"
SKILL = P.parents[1]
OUTPUTS = {
    "blockout": ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"),
    "views": ("front.png", "back.png", "left.png", "right.png", "top.png", "guides/views.json", "bg_color.json",
              "README.md", "report/report.json", "report/VIEWS.md", "report/VIEWS_sheet.png"),
}
SIDES = ("front", "back", "left", "right", "top")
SEEN = "front, back, left, overlay_front"
KEYS = ("stage", "state", "fix_round", "fix_base", "round_versions", "offer", "label", "note", "worker_agent_id",
        "approved", "rejected", "reopened", "prior", "stale")
BRIEF_MAX = 4096
TIMING = r" · ((worker|reviewer|script) giao .*|hạn chót \S+ \S+)$"  # timing and deadline: tests/test_watch.py


def counts(major=0, minor=0, unclear=0):
    return f"blocker=0; major={major}; minor={minor}; preference=0; unclear={unclear}"


def vf(region, kind="regen", prio="major", n=1, **kw):
    return finding(f"F{n}", prio, kind, region=region, evidence=f"{region.split(':')[0]}: lệch", **kw)


def images(final: Path):
    """Real PNGs for the sheet: each view, its guide and its overlay."""
    for v in SIDES:
        for rel in (f"{v}.png", f"guides/{v}_guide.png", f"report/overlay_{v}.png"):
            (final / rel).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (200, 100), (40 * SIDES.index(v), 90, 30)).save(final / rel)


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
        step = self.st()["stage"]
        put_all(vd / "final", step, OUTPUTS[step], name)
        if step == "views":
            images(vd / "final")
        if failing:
            (vd / "final/review/checks/measure.json").write_text(json.dumps({"tool": "views/measure", "overall": "fail"}))
            (vd / "final/README.md").write_text("## NGOẠI LỆ\n- measure.json — IoU front 0.81 < 0.85 do bóng đổ\n",
                                                encoding="utf-8")
        ph = re.search(r"^PROFILE_HASH: (\w+)$", self.cp[name + " brief"]["text"], re.M).group(1)
        accepted = "ACCEPTED_FAIL: measure.json — IoU front 0.81 < 0.85 do bóng đổ\n" if failing else ""
        (self.root / out["report"]).write_text(f"STATUS: DONE\nRUBRIC: style=pass\nISSUES: none\nPROFILE_HASH: {ph}\n"
                                               + accepted + fixed_line(self.root, AID), encoding="utf-8")
        self.cp[name + " worker"] = {"out": self.p("ingest", AID, "--agent-id", f"w-{name}"), "st": self.st()}

    def review(self, name, evidence=SEEN, **kw):
        out = self.brief(name + " review brief")
        (self.root / out["report"]).write_text(report(evidence=evidence, rubric="style=pass", **kw), encoding="utf-8")
        self.cp[name + " review"] = {"out": self.p("ingest", AID, "--agent-id", f"r-{name}"), "st": self.st()}

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
    f.work("v1", failing=True)
    f.review("v1", counts=counts(1, 1), top_fix="regen",
             findings=[vf("front: bóng đổ dưới mép trên"), vf("back: đầu cột xám", "note_texture", "minor", 2)])
    f.cp["v1 doc"] = f.doc("views", 1)
    f.work("v2")
    f.review("v2", counts=counts(0, 1, 1), top_fix="need_evidence", compare="F1=better",
             prior=["- F1: resolved | evidence: front", "- F2: open"],
             findings=[vf("left: số khối rời", prio="unclear", n=3, viewing_condition="xin ảnh left box 0.25,0,0.75,0.5")])
    f.review("v2 again", evidence=SEEN + ", left-crop1.png", verdict="PASS", counts=counts(0, 1), top_fix=None,
             prior=["- F2: open", "- F3: resolved | evidence: left-crop1.png"])
    f.human("redo set", "back tối quá so với front", "--action", "redo")
    f.work("v3")
    f.review("v3", verdict="PASS", counts=counts(0, 1), top_fix=None, compare="H1=better",
             prior=["- F2: open", "- H1: resolved | evidence: back"])
    f.human("approve set", "đạt", "--action", "approve")
    f.human("redo blockout", "mái cao thêm 20 cm", "--action", "redo", "--step", "blockout")
    f.work("b2")
    f.review("b2", verdict="PASS", counts=counts(), top_fix=None, compare="H1=better",
             prior=["- H1: resolved | evidence: front"])
    f.human("approve blockout v2", "đạt", "--action", "approve")
    f.brief("v4 brief")
    f.cp["ledger"] = [re.sub(TIMING, "", l.split(" · ", 2)[2]) for l in (root / "production/ledger.md").read_text(encoding="utf-8")
                      .splitlines() if l.startswith("- ")]
    f.cp["root"] = root
    return f.cp


def pick(st):
    return {k: st.get(k) for k in KEYS}


def lines(text, *wanted):
    return [w for w in wanted if w not in text.splitlines()]


def test_approved_blockout_moves_on_to_the_one_views_step(flow):
    head, line = flow["approve blockout"]["out"].splitlines()
    assert head == "pilot-house: đã duyệt blockout v1 → views/todo. Tiếp: giao worker → `brief pilot-house`"
    assert json.loads(line)["brief"] == "production/assets/pilot-house/views/v1/brief-worker.md"


def test_the_views_brief_names_the_approved_blockout_the_concept_files_the_codex_call_and_every_output_of_the_set(flow):
    b = flow["v1 brief"]
    assert b["out"] == {"role": "worker", "agent": "zps-3dp-step-views", "model": "opus", "resume": None,
                        "brief": f"{A}/views/v1/brief-worker.md", "report": f"{A}/views/v1/worker-out.md"}
    assert lines(b["text"], f"TOOLS: {SKILL / 'agents/zps-3dp-step-views/tools'}", "BLENDER: blender",
                 f"GEN_IMAGE: {SKILL / 'scripts/gen_image_codex.py'}",
                 "GEN_ARGS: --model gpt-6-astra --reasoning medium --pid-file production/pids/codex_image/pilot-house.pid "
                 "--timeout 900",
                 "VIEWS: full (back, left, right)",
                 f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v1/final/`.",
                 f"- Bắt buộc có (tính từ `{A}/views/v1/`): `final/front.png`, `final/back.png`, `final/left.png`, "
                 "`final/right.png`, `final/guides/views.json`, `final/bg_color.json`, `final/README.md`, "
                 "`final/report/report.json`, `final/report/VIEWS.md`, `final/report/VIEWS_sheet.png`, "
                 "`final/review/checks/{measure,package}.json`.") == []
    assert not re.search(r"echo \$!|wait \$!|PID|concept_colors\.json`", b["text"])
    concept = [l for l in b["text"].splitlines() if "Concept đã duyệt" in l]
    assert len(concept) == 1 and concept[0].endswith(
        ": chỉ đọc `concept_albedo.png`, `asset-card.yaml`, `pilot-house.material.md`. Bỏ qua file và thư mục khác (bản nháp cũ).")
    assert (flow["root"] / "production/pids/codex_image").is_dir()


def test_the_views_reviewer_gets_the_view_region_rule_with_front_and_the_three_kinds(flow):
    t = flow["v1 review brief"]["text"]
    assert lines(t, f"- Đầu ra đã duyệt của bước `blockout` (đầu vào, không chấm lại): `{A}/blockout/v1/final/`.",
                 "- region mở đầu bằng front|back|left|right, vd `front: mép mái`.",
                 "- F1 [blocker|major|minor|preference|unclear] <regen|note_exception|note_texture>",
                 "TOP_FIX: <regen|need_evidence>[: F<n>[, F<m>]]",
                 "- Sai số thành phần (cửa, chân bàn, đá) so với concept hoặc `blockout.md`: luôn `regen`, không phải "
                 "`note_exception`, `note_texture`.") == []


def test_the_views_reviewer_reads_a_sheet_where_each_view_sits_beside_its_guide_and_no_side_outside_the_card(flow):
    """Q6: no top tile for a `full` card, although the worker's guides hold all five views."""
    t = flow["v1 review brief"]["text"]
    sheet = f"{A}/views/v1/review/sheet.png"
    assert (f"- Sheet: `{sheet}`, `sheet-2.png` (nhãn ô = tên ảnh; ảnh lẻ qua need_evidence). Số liệu: JSON trong "
            "`final/`, `work/` của v1.") in t
    tiles = json.loads((flow["root"] / A / "views/v1/review/sheet.json").read_text(encoding="utf-8"))
    assert [(label, t["page"]) for label, t in tiles.items()] == [
        (f"{x}{v}{y}", f"review/sheet{'' if k < 6 else '-2'}.png") for k, (v, (x, y)) in enumerate(
            (v, xy) for v in ("front", "back", "left", "right") for xy in (("", ""), ("", "_guide"), ("overlay_", "")))]


def test_a_measure_fail_the_worker_accepts_reaches_the_reviewer_with_its_reason(flow):
    assert "- Worker khai ACCEPTED_FAIL (check fail không sửa được): measure.json — IoU front 0.81 < 0.85 do bóng đổ. " \
           "Chấm lý do: lý do không đứng được thì ghi finding." in flow["v1 review brief"]["text"]


def test_a_regen_that_names_the_front_stays_in_the_views_step_and_resumes_the_worker(flow):
    """D44.3: a wrong front is a regen inside the same step; no earlier step reopens."""
    head, line = flow["v1 review"]["out"].splitlines()
    assert head == "pilot-house: review FIX (major=1 minor=1) → views/fix. Tiếp: giao worker → `brief pilot-house`"
    assert pick(flow["v1 review"]["st"])["approved"] == {"blockout": 1}
    assert flow["v1 doc"]["top_fix"] == {"kind": "regen", "ids": ["F1"]}
    b = flow["v2 brief"]
    assert json.loads(line) == b["out"] and b["out"]["resume"] == "w-v1"
    assert lines(b["text"], f"8. Bản gốc: `{A}/views/v1/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
                 f"9. Đọc trước nguyên văn lỗi script của bản gốc: `{A}/views/v1/final/review/checks/measure.json`.",
                 f"10. Sửa đúng `TOP_FIX: regen: F1`; repair, preserve, acceptance của từng id trong "
                 f"`{A}/views/v1/findings.json`. Rồi tới feedback mới nhất của người dùng trong feedback.md.") == []


def test_a_crop_of_a_sheet_tile_is_served_from_disk_to_the_same_reviewer_without_a_worker(flow):
    s = flow["v2 review"]
    head, line = s["out"].splitlines()
    assert head == "pilot-house: review FIX (minor=1 unclear=1) → views/review. Tiếp: giao reviewer → `brief pilot-house`"
    assert (json.loads(line)["resume"], s["st"]["versions"], s["st"]["evidence_served"]) == ("r-v2", {"blockout": 1, "views": 2}, 1)
    with Image.open(flow["root"] / A / "views/v2/review/evidence-1/left-crop1.png") as im:
        assert im.size == (100, 50)
    assert "Ảnh bạn xin đã có: `production/assets/pilot-house/views/v2/review/evidence-1/left-crop1.png`." in \
        flow["v2 again review brief"]["text"]


def test_a_minor_texture_note_does_not_block_the_set_which_then_waits_for_the_human(flow):
    assert flow["v2 again review"]["out"] == ("pilot-house: review PASS (minor=1) → views/waiting_human. "
                                              "Tiếp: chờ người dùng: duyệt views v2 (review page)\n")


def test_a_human_redo_of_the_set_opens_a_fix_round_from_the_offered_version(flow):
    st = flow["redo set"]["st"]
    assert {k: st[k] for k in ("stage", "state", "fix_round", "fix_base", "approved")} == {
        "stage": "views", "state": "running", "fix_round": 1, "fix_base": 2, "approved": {"blockout": 1}}
    assert "Ưu tiên 1, feedback của người dùng: sửa `H1`" in flow["v3 brief"]["text"]


def test_approving_the_set_parks_at_done_enabled_before_the_disabled_model_step(flow):
    assert flow["approve set"]["out"] == ("pilot-house: đã duyệt views v3 → views/done_enabled. "
                                          "Tiếp: xong các bước đang bật\n")
    st = flow["approve set"]["st"]
    assert {k: st[k] for k in ("approved", "rejected", "note", "reopened")} == {
        "approved": {"blockout": 1, "views": 3}, "rejected": {"blockout": [], "views": [1, 2]},
        "note": "bước model chưa bật", "reopened": {}}


def test_a_blockout_redo_after_the_set_keeps_the_old_views_as_prior_so_the_next_build_reuses_unchanged_ones(flow):
    st = flow["redo blockout"]["st"]
    assert {k: st[k] for k in ("stage", "state", "approved", "prior", "reopened", "worker_agent_id")} == {
        "stage": "blockout", "state": "running", "approved": {}, "prior": {"views": 3}, "reopened": {},
        "worker_agent_id": None}
    b = flow["v4 brief"]
    assert b["out"]["brief"] == f"{A}/views/v4/brief-worker.md"
    assert lines(b["text"], f"7. Đầu ra đã duyệt của bước `blockout`: `{A}/blockout/v2/final/`.",
                 f"8. Bản đã duyệt trước của bước này (dựng từ đầu vào cũ): `{A}/views/v3/final/`. "
                 "Giữ phần có đầu vào không đổi, theo file agent.") == []
    assert {k: b["st"][k] for k in ("prior", "stale")} == {
        "prior": {"views": 3}, "stale": {"views v1": "blockout v1", "views v2": "blockout v1", "views v3": "blockout v1"}}


def test_the_ledger_records_one_views_step_with_its_rounds(flow):
    def rnd(step, n, review, aid="pilot-house", accepted=False):
        agent = "blockout" if step == "blockout" else "views"
        acc = [f"{aid} · views v1 · ACCEPTED_FAIL measure.json · lần 1 · IoU front 0.81 < 0.85 do bóng đổ"]
        return [f"{aid} · {step} v{n} · giao worker (zps-3dp-step-{agent}, opus)", *(acc if accepted else []),
                f"{aid} · {step} v{n} · worker DONE · style=pass",
                f"{aid} · {step} v{n} · giao reviewer (zps-3dp-check-{agent}, opus)",
                f"{aid} · {step} v{n} · review {review}"]
    assert flow["ledger"] == [
        "pilot-house · tạo mới (draft, rubric chưa duyệt)", "pilot-house · ready",
        *rnd("blockout", 1, "PASS (0 mở) · style=pass"),
        "pilot-house · blockout v1 · duyệt bởi người dùng", "pilot-house · người dùng approve blockout · đạt",
        *rnd("views", 1, "FIX (major=1 minor=1) · style=pass", accepted=True),
        *rnd("views", 2, "FIX (minor=1 unclear=1) · style=pass · script lấy ảnh có sẵn, không giao worker: left-crop1.png"),
        "pilot-house · views v2 · giao reviewer (zps-3dp-check-views, opus)",
        "pilot-house · views v2 · review PASS (minor=1) · style=pass",
        "pilot-house · người dùng redo views · back tối quá so với front",
        *rnd("views", 3, "PASS (minor=1) · style=pass"),
        "pilot-house · views v3 · duyệt bởi người dùng", "pilot-house · người dùng approve views · đạt",
        "pilot-house · người dùng redo blockout · mái cao thêm 20 cm",
        *rnd("blockout", 2, "PASS (0 mở) · style=pass"),
        "pilot-house · blockout v2 · duyệt bởi người dùng", "pilot-house · người dùng approve blockout · đạt",
        "pilot-house · views v4 · giao worker (zps-3dp-step-views, opus)"]


def test_every_views_brief_stays_under_the_token_budget_without_the_install_and_project_paths(flow):
    strip = (str(Path(flow["root"]).resolve()), str(SKILL))
    sizes = {}
    for k, v in flow.items():
        if isinstance(v, dict) and "text" in v:
            t = v["text"]
            for s in strip:
                t = t.replace(s, "")
            sizes[k] = len(t.encode())
    assert len(sizes) == 12 and max(sizes.values()) < BRIEF_MAX, sizes


def test_the_set_brief_names_the_views_of_the_card_and_the_full_set_has_no_top_d35(flow):
    assert "VIEWS: full (back, left, right)" in flow["v1 brief"]["text"].splitlines()
    assert "`final/top.png`" not in flow["v1 brief"]["text"]
