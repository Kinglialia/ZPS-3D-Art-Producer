"""End-to-end blockout on the synthetic pilot (tests/fixtures/pilot): the real CLI in subprocesses, fake agents."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from shared import P, PROFILE_HASH, finding, report, run

PILOT = Path(__file__).parent / "fixtures/pilot"
AGENT = P.parents[1] / "agents/zps-3dp-step-blockout"
TOOLS = AGENT / "tools"
VPY = TOOLS / ".deps/venv/bin/python"
AID = "pilot-house"
V = f"production/assets/{AID}/blockout/v"
OUTPUTS = ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md")
PIDS = f"production/pids/blender/{AID}.pid"
KEYS = ("stage", "state", "fix_round", "fix_base", "round_versions", "offer", "label", "note", "evidence_used",
        "worker_agent_id", "approved", "rejected")
BRIEF_MAX = 4096
NEXT_HEAD = ("1 asset đang chạy · 0 done · review page: `serve` → http://127.0.0.1:8765\n"
             "Chưa có production/preflight.json → chạy `preflight` một lần mỗi phiên\n")


def counts(major=0):
    return f"blocker=0; major={major}; minor=0; preference=0; unclear=0"


def ids(*n):
    return ", ".join(f"F{i}" for i in n)


def params(*n):
    return [finding(f"F{i}", "major", "param", region=r) for i, r in zip(n, ("mái", "tường", "cửa", "nền"))]


def resolved(*n):
    return [f"- F{i}: resolved | evidence: clay_front" for i in n]


def still_open(*n):
    return [f"- F{i}: open" for i in n]


def pilot_project(root: Path):
    run(root, "init", "--project", "Pilot", "--concepts", "concepts")
    shutil.copytree(PILOT / "_approved", root / "concepts/_approved", dirs_exist_ok=True)
    shutil.copy(PILOT / "PROJECT-PROFILE.yaml", root / "production/PROJECT-PROFILE.yaml")


class Pilot:
    def __init__(self, root: Path):
        self.root, self.cp = root, {}

    def p(self, *args):
        return run(self.root, *args)

    def st(self):
        p = self.root / f"production/assets/{AID}/status.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def findings(self, n):
        return json.loads((self.root / f"{V}{n}/findings.json").read_text(encoding="utf-8"))

    def save(self, name, out, **kw):
        self.cp[name] = {"out": out, "st": self.st(), **kw}

    def brief(self, name):
        out = json.loads(self.p("brief", AID))
        self.save(name, out, text=(self.root / out["brief"]).read_text(encoding="utf-8"))
        return out

    def work(self, name, status="DONE", fixed=(), variants=(), failing=False):
        out, text = self.cp[f"{name} brief"]["out"], self.cp[f"{name} brief"]["text"]
        vd = (self.root / out["report"]).parent
        for sub, tag in (("final", "a"), *((f"variants/{x}", x) for x in variants)):
            (vd / sub).mkdir(parents=True, exist_ok=True)
            for o in OUTPUTS:
                (vd / sub / o).write_text(f"{o} {name} phương án {tag}\n", encoding="utf-8")
        if failing:
            (vd / "final/review/checks").mkdir(parents=True)
            (vd / "final/review/checks/layout.json").write_text(json.dumps({
                "tool": "blockout/check_layout", "overall": "fail",
                "checks": [{"check": "layout.bbox", "status": "fail"}]}), encoding="utf-8")
        ph = re.search(r"^PROFILE_HASH: (\w+)$", text, re.M).group(1)
        rep = [f"STATUS: {status}", f"OUTPUT: {vd.relative_to(self.root)}/final/",
               "RUBRIC: concept_match=pass; scale=pass", "ISSUES: layout.bbox lệch 8%" if failing else "ISSUES: none",
               f"PROFILE_HASH: {ph}", *([f"FIXED: {ids(*fixed)}"] if fixed else [])]
        (self.root / out["report"]).write_text("\n".join(rep) + "\n", encoding="utf-8")
        self.save(name + " worker", self.p("ingest", AID, "--agent-id", "w1"))

    def review(self, name, **kw):
        out = self.brief(name + " review brief")
        (self.root / out["report"]).write_text(report(**kw), encoding="utf-8")
        self.save(name + " review", self.p("ingest", AID))


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("pilot")
    f = Pilot(root)
    pilot_project(root)
    f.save("intake list", f.p("intake"))
    f.save("intake", f.p("intake", AID))
    f.save("ready", f.p("ready", AID))
    f.brief("v1 brief")
    f.work("v1", status="DONE_WITH_CONCERNS", failing=True)
    f.review("v1", counts=counts(4), top_fix="param: " + ids(1, 2, 3, 4), rubric="concept_match=fail; scale=fail",
             findings=params(1, 2, 3, 4))
    pids = [root / PIDS, root / "production/pids/blender/other.pid"]
    for p, pid in zip(pids, (os.getpid(), os.getppid())):
        p.write_text(str(pid), encoding="utf-8")
    f.save("next, two live blender pids", f.p("next"))
    for p in pids:
        p.unlink()
    f.brief("v2 brief")
    f.work("v2", fixed=(1, 2, 3, 4), variants=("b", "c"))
    f.review("v2", counts=counts(2), top_fix="param: " + ids(3, 4), rubric="concept_match=fail; scale=pass",
             compare="F1=better; F2=better; F3=same; F4=same", pick="b", prior=resolved(1, 2) + still_open(3, 4))
    f.brief("v3 brief")
    f.work("v3", fixed=(3, 4), variants=("b", "c"))
    f.review("v3", counts=counts(2), top_fix="param: " + ids(3, 4), rubric="concept_match=fail; scale=pass",
             compare="F3=same; F4=same", prior=still_open(3, 4))
    f.save("redo", f.p("feedback", AID, "mái chìa thêm 10 cm", "--action", "redo"))
    f.brief("v4 brief")
    f.work("v4", fixed=(3, 4))
    f.review("v4", verdict="PASS", counts=counts(0), top_fix=None, compare="F3=better; F4=better",
             rubric="concept_match=pass; scale=pass", prior=resolved(3, 4) + ["- H1: resolved | evidence: clay_front"])
    f.save("approve", f.p("feedback", AID, "đạt", "--action", "approve"))
    f.save("approve again", f.p("feedback", AID, "đạt", "--action", "approve"))
    f.save("cleanup dry-run", f.p("cleanup", AID))
    f.save("cleanup", f.p("cleanup", AID, "--yes"))
    f.cp["ledger"] = [l.split(" · ", 1)[1] for l in (root / "production/ledger.md").read_text(encoding="utf-8")
                      .splitlines() if l.startswith("- ")]
    f.cp["findings"] = {n: f.findings(n) for n in (1, 2, 3, 4)}
    f.cp["variant files"] = {p: (root / f"{V}2/{p}/blockout.md").read_text(encoding="utf-8")
                             for p in ("final", "variants/a")}
    f.cp["archive"] = {"out": f.p("archive", AID), "moved": (root / "production/archive" / AID / "status.json").is_file()}
    f.cp["root"] = str(root)
    return f.cp


def pick(st):
    return {k: st.get(k) for k in KEYS}


def state(**kw):
    base = {"stage": "blockout", "state": "fix", "fix_round": 1, "fix_base": 1, "round_versions": [1], "offer": None,
            "label": None, "note": "", "evidence_used": None, "worker_agent_id": "w1", "approved": {}, "rejected": None}
    return base | kw


def rows(doc):
    return {i: (f["status"], f["first_v"], f["last_v"]) for i, f in doc["findings"].items()}


def head(doc):
    return {k: doc[k] for k in ("version", "base", "top_fix", "pick", "next_id")}


def worker_json(n, resume):
    return {"role": "worker", "agent": "zps-3dp-step-blockout", "model": "opus", "resume": resume,
            "brief": f"{V}{n}/brief-worker.md", "report": f"{V}{n}/report-worker.md"}


def reviewer_json(n):
    return {"role": "reviewer", "agent": "zps-3dp-check-blockout", "model": "opus", "resume": None,
            "brief": f"{V}{n}/brief-review.md", "report": f"{V}{n}/report-review.md"}


def test_intake_finds_the_pilot_complete_and_registers_it_alone_because_pilot_asset_is_null(flow):
    assert flow["intake list"]["out"] == ("Mới, đủ file (1): pilot-house\n"
                                          "Chưa có pilot (pilot_asset: null): đăng ký từng asset, `intake <id>`.\n")
    assert flow["intake"]["out"] == ("Đã đăng ký 1: pilot-house.\nRubric chưa duyệt: pilot-house nằm ở draft. "
                                     "Người dùng duyệt xong thì `ready pilot-house`.\n")
    st = flow["intake"]["st"]
    assert (st["state"], st["type"], st["title"]) == ("draft", "building", "Pilot House")
    assert st["concept_dir"] == str(Path(flow["root"]).resolve() / "concepts/_approved/pilot-house")
    assert (flow["ready"]["out"], flow["ready"]["st"]["state"]) == ("pilot-house: → todo\n", "todo")


def test_the_worker_is_resumed_on_every_fix_round_within_resume_rounds_and_reviewers_never_are(flow):
    assert [flow[f"v{n} brief"]["out"] for n in (1, 2, 3, 4)] == [
        worker_json(1, None), worker_json(2, "w1"), worker_json(3, "w1"), worker_json(4, "w1")]
    assert [flow[f"v{n} review brief"]["out"] for n in (1, 2, 3, 4)] == [reviewer_json(n) for n in (1, 2, 3, 4)]


def test_the_brief_records_the_profile_hash_that_ingest_compares_with_the_worker_report(flow):
    assert "\nPROFILE_HASH: 786cfc66bdd2\n" in flow["v1 brief"]["text"]
    assert flow["v1 brief"]["st"]["inputs"]["blockout"]["v1"]["profile"] == PROFILE_HASH
    assert flow["v1 worker"]["out"] == ("pilot-house: worker DONE_WITH_CONCERNS → blockout/review. "
                                        "Tiếp: giao reviewer → `brief pilot-house`\n")


def test_the_worker_brief_names_only_the_handoff_files_so_old_drafts_beside_them_are_never_read(flow):
    line = [l for l in flow["v1 brief"]["text"].splitlines() if "Concept đã duyệt" in l]
    assert len(line) == 1
    assert line[0].endswith(": chỉ đọc `concept_albedo.png`, `concept_shadow.png`, `asset-card.yaml`, "
                            "`pilot-house.material.md`. Bỏ qua file và thư mục khác (bản nháp cũ).")
    assert "kể cả thư mục con" not in flow["v1 brief"]["text"]


def test_the_worker_brief_gives_the_pid_line_the_agent_file_tells_the_worker_to_use(flow):
    agent = (AGENT / "zps-3dp-step-blockout.md").read_text(encoding="utf-8")
    assert "Mọi lệnh `blender` chạy qua dòng PID của brief: `<lệnh> & echo $! > <file .pid>; wait $!; rm -f <file .pid>`" in agent
    assert f"`<lệnh> & echo $! > {PIDS}; wait $!; rm -f {PIDS}`" in flow["v1 brief"]["text"]


def test_two_live_blender_pids_hold_the_fix_dispatch_because_slots_count_processes_not_states(flow):
    assert flow["next, two live blender pids"]["out"] == NEXT_HEAD + "[pilot-house] blockout/fix → chờ slot blender\n"


def test_four_major_param_findings_open_fix_round_1_from_v1_as_one_batch(flow):
    assert flow["v1 review"]["out"] == "pilot-house: review FIX (major=4) → blockout/fix. Tiếp: giao worker → `brief pilot-house`\n"
    assert pick(flow["v1 review"]["st"]) == state(note="vòng sửa 1/3")
    v1 = flow["findings"][1]
    assert head(v1) == {"version": 1, "base": None, "top_fix": {"kind": "param", "ids": ["F1", "F2", "F3", "F4"]},
                        "pick": None, "next_id": 5}
    assert rows(v1) == {f"F{i}": ("open", 1, 1) for i in (1, 2, 3, 4)}


def test_the_fix_brief_starts_from_the_best_version_reads_its_failed_check_json_first_and_fixes_the_whole_batch(flow):
    text = flow["v2 brief"]["text"]
    for line in (f"7. Bản gốc: `{V}1/` (bản tốt nhất; final/ + work/). **Sửa từ bản này, không làm lại từ đầu.**",
                 f"8. Đọc trước nguyên văn lỗi script của bản gốc: `{V}1/final/review/checks/layout.json`.",
                 f"9. Sửa đúng `TOP_FIX: param: F1, F2, F3, F4`; repair, preserve, acceptance của từng id trong "
                 f"`{V}1/findings.json`.", "Đây là vòng sửa 1.", "FIXED: F<n>, ..."):
        assert line in text, line


def test_the_review_brief_prefills_prior_and_compare_for_every_open_id_so_none_is_skipped(flow):
    text = flow["v2 review brief"]["text"]
    assert "\nCOMPARE: F1=?; F2=?; F3=?; F4=?\nPICK: a|b|c\n" in text
    assert "\nPRIOR:\n" + "".join(f"- F{i}: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front\n"
                                  for i in (1, 2, 3, 4)) + "```\n" in text
    assert "\n- F5 [blocker|major|minor|preference|unclear] <structure|param>\n" in text


def test_prior_is_recorded_per_finding_and_pick_b_moves_variant_b_into_final_keeping_a(flow):
    v2 = flow["findings"][2]
    assert head(v2) == {"version": 2, "base": 1, "top_fix": {"kind": "param", "ids": ["F3", "F4"]}, "pick": "b",
                        "next_id": 5}
    assert rows(v2) == {"F1": ("resolved", 1, 2), "F2": ("resolved", 1, 2), "F3": ("open", 1, 2), "F4": ("open", 1, 2),
                        "H1": ("open", 2, 2)}
    assert flow["variant files"] == {"final": "blockout.md v2 phương án b\n", "variants/a": "blockout.md v2 phương án a\n"}


def test_two_old_majors_resolved_is_progress_so_round_2_starts_from_v2(flow):
    assert flow["v2 review"]["out"] == "pilot-house: review FIX (major=2) → blockout/fix. Tiếp: giao worker → `brief pilot-house`\n"
    assert pick(flow["v2 review"]["st"]) == state(fix_round=2, fix_base=2, round_versions=[1, 2], note="vòng sửa 2/3")


def test_the_fix_brief_lists_no_script_errors_when_the_best_version_has_no_failed_check(flow):
    text = flow["v3 brief"]["text"]
    assert f"7. Bản gốc: `{V}2/`" in text and "8. Sửa đúng `TOP_FIX: param: F3, F4`" in text
    assert "Đọc trước nguyên văn lỗi script" not in text and "Đây là vòng sửa 2." in text


def test_no_progress_at_the_review_of_v3_stops_early_and_offers_the_older_tied_version_as_not_passed(flow):
    assert flow["v3 review"]["out"] == ("pilot-house: review FIX (major=2) → blockout/waiting_human. Tiếp: chờ người dùng: "
                                        "không tiến bộ ở vòng 2; còn mở: F3, F4 (review page)\n")
    assert pick(flow["v3 review"]["st"]) == state(state="waiting_human", fix_round=2, fix_base=2, round_versions=[1, 2, 3],
                                                  offer=2, label="chưa đạt", note="không tiến bộ ở vòng 2; còn mở: F3, F4")
    assert rows(flow["findings"][3]) == {"F1": ("resolved", 1, 2), "F2": ("resolved", 1, 2), "F3": ("open", 1, 3),
                                         "F4": ("open", 1, 3)}


def test_redo_opens_a_new_feedback_round_from_the_offered_version_with_counters_reset(flow):
    assert flow["redo"]["out"] == "pilot-house: làm lại blockout từ v2. Tiếp: giao worker → `brief pilot-house`\n"
    assert pick(flow["redo"]["st"]) == state(fix_base=2, round_versions=[2], label="", evidence_used=0, rejected={},
                                             note="làm lại theo feedback người dùng")
    assert list(flow["redo"]["st"]["decisions"]) == ["blockout v2"]


def test_redo_carries_the_open_findings_of_the_offered_version_into_the_new_round(flow):
    text, review = flow["v4 brief"]["text"], flow["v4 review brief"]["text"]
    assert f"7. Bản gốc: `{V}2/`" in text and "Sửa đúng `TOP_FIX: param: F3, F4`" in text and "Đây là vòng sửa 1." in text
    assert "\nCOMPARE: F3=?; F4=?\n" in review and f"- Bản gốc v2: ảnh cùng góc `{V}2/final/`" in review
    assert "\nPRIOR:\n- F3: ? | evidence: ? | acceptance: đỉnh mái 3.2 m trên clay_front\n- F4: ? |" in review
    assert "\n- H1: ? | evidence: ? | acceptance: đạt yêu cầu của người dùng: mái chìa thêm 10 cm\n" in review
    assert head(flow["findings"][4]) == {"version": 4, "base": 2, "top_fix": None, "pick": None, "next_id": 5}
    assert rows(flow["findings"][4]) == {"F1": ("resolved", 1, 2), "F2": ("resolved", 1, 2), "F3": ("resolved", 1, 4),
                                         "F4": ("resolved", 1, 4), "H1": ("resolved", 2, 4)}


def test_pass_on_a_review_human_step_waits_for_the_human_without_a_not_passed_label(flow):
    assert flow["v4 review"]["out"] == ("pilot-house: review PASS (0 mở) → blockout/waiting_human. "
                                        "Tiếp: chờ người dùng: duyệt blockout v4 (review page)\n")
    assert pick(flow["v4 review"]["st"]) == state(state="waiting_human", fix_base=2, round_versions=[2, 4], offer=4,
                                                  label="", evidence_used=0, rejected={}, note="duyệt blockout v4")


def test_approve_rejects_the_other_versions_and_stops_at_done_enabled_since_views_front_is_off(flow):
    assert flow["approve"]["out"] == "pilot-house: đã duyệt blockout v4 → blockout/done_enabled. Tiếp: xong các bước đang bật\n"
    st = flow["approve"]["st"]
    assert pick(st) == state(state="done_enabled", fix_round=0, fix_base=None, round_versions=[], label="",
                             evidence_used=0, worker_agent_id=None, approved={"blockout": 4},
                             rejected={"blockout": [1, 2, 3]}, note="bước views_front chưa bật")
    assert re.fullmatch(r"[0-9a-f]{64}", st["approved_hash"]["blockout"])


def test_a_second_approve_of_the_same_version_is_ignored_and_changes_nothing(flow):
    assert re.fullmatch(r"pilot-house: bỏ qua approve blockout v4: đã có quyết định lúc \d{4}-\d\d-\d\d \d\d:\d\d\n",
                        flow["approve again"]["out"])
    assert flow["approve again"]["st"] == flow["approve"]["st"]


def test_cleanup_and_archive_accept_done_enabled_and_keep_the_approved_work(flow):
    assert flow["cleanup dry-run"]["out"] == ("DRY-RUN — sẽ xoá (thêm --yes sau khi người dùng đồng ý):\n"
                                              + "".join(f"  {V}{n}/work\n" for n in (1, 2, 3)))
    assert flow["cleanup"]["out"] == "Đã xoá 3 thư mục work/.\n"
    assert flow["archive"] == {"out": "Đã chuyển pilot-house vào production/archive/\n", "moved": True}


def test_the_ledger_records_every_dispatch_report_and_decision_in_order(flow):
    def rnd(n, review, worker="DONE"):
        return [f"pilot-house · blockout v{n} · giao worker (zps-3dp-step-blockout)",
                f"pilot-house · blockout v{n} · worker {worker} · concept_match=pass; scale=pass",
                f"pilot-house · blockout v{n} · giao reviewer (zps-3dp-check-blockout)",
                f"pilot-house · blockout v{n} · review {review}"]
    assert flow["ledger"] == [
        "pilot-house · tạo mới (draft, rubric chưa duyệt)", "pilot-house · ready",
        *rnd(1, "FIX (major=4) · concept_match=fail; scale=fail", "DONE_WITH_CONCERNS"),
        *rnd(2, "FIX (major=2) · concept_match=fail; scale=pass"),
        *rnd(3, "FIX (major=2) · concept_match=fail; scale=pass · không tiến bộ ở vòng 2"),
        "pilot-house · người dùng redo blockout · mái chìa thêm 10 cm",
        *rnd(4, "PASS (0 mở) · concept_match=pass; scale=pass"),
        "pilot-house · blockout v4 · duyệt bởi người dùng", "pilot-house · người dùng approve blockout · đạt",
        "pilot-house · cleanup 3 thư mục work/"]


def test_every_brief_stays_under_the_token_budget_without_the_install_and_project_paths(flow):
    strip = (str(Path(flow["root"]).resolve()), str(TOOLS))
    sizes = {}
    for k, v in flow.items():
        if isinstance(v, dict) and "text" in v:
            t = v["text"]
            for s in strip:
                t = t.replace(s, "")
            sizes[k] = len(t.encode())
    assert len(sizes) == 8 and max(sizes.values()) < BRIEF_MAX, sizes


def test_a_review_step_without_a_reviewer_fails_at_config_load_instead_of_a_dead_default(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    p = tmp_path / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('reviewer = "check-blockout"\n', "", 1), encoding="utf-8")
    assert run(tmp_path, "next", ok=False) == "LỖI: step blockout: thiếu reviewer\n"


BUILD_PARTS = ("base", "walls", "roof_f", "roof_b", "door")
CHECKS = ("inputs", "schema", "materials", "layout", "base", "support", "markers")
needs_tools = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")


def tool(*args):
    return subprocess.run([str(VPY), *map(str, args)], capture_output=True, text=True).returncode


@pytest.fixture(scope="module")
def real_build(tmp_path_factory):
    root = tmp_path_factory.mktemp("pilot-real")
    pilot_project(root)
    run(root, "intake", AID)
    run(root, "ready", AID)
    out = json.loads(run(root, "brief", AID))
    f = root / f"{V}1/final"
    g = json.loads((PILOT / "part_graph.json").read_text(encoding="utf-8"))
    g["params"]["roof_h"] = 0.6
    (f / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    src = root / "concepts/_approved" / AID
    card, mat = src / "asset-card.yaml", src / f"{AID}.material.md"
    (f / "sources.json").write_text(json.dumps({
        "files": {"layout": str(card), "layout_sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
                  "material": str(mat), "material_sha256": hashlib.sha256(mat.read_bytes()).hexdigest()},
        "layout": {"w": 4, "d": 4, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
        "door_h": 1.8, "door_h_source": "asset-card.yaml scale_overrides cửa", "character_h": 1.6,
        "materials": ["STONE", "TIMBER", "TEAL"], "camera": None}, ensure_ascii=False), encoding="utf-8")
    rc = {"assembly": tool(TOOLS / "self_build/assembly.py", "--work", f)}
    rc |= {p: tool(TOOLS / "self_build/gates.py", "--work", f, "--part", p, "--out", f / f"review/gates/{p}.json")
           for p in BUILD_PARTS}
    extra = ("--approved", src, "--profile", root / "production/PROJECT-PROFILE.yaml")
    rc |= {c: tool(TOOLS / f"check_{c}.py", "--work", f, *(extra if c == "inputs" else ())) for c in CHECKS}
    for o in ("parts_lib.py", "blockout.md"):
        (f / o).write_text(f"{o}\n", encoding="utf-8")
    ph = re.search(r"^PROFILE_HASH: (\w+)$", (root / out["brief"]).read_text(encoding="utf-8"), re.M).group(1)
    (root / out["report"]).write_text(f"STATUS: DONE_WITH_CONCERNS\nRUBRIC: scale=fail\nISSUES: layout.bbox\n"
                                      f"PROFILE_HASH: {ph}\n", encoding="utf-8")
    run(root, "ingest", AID, "--agent-id", "w1")
    rv = json.loads(run(root, "brief", AID))
    (root / rv["report"]).write_text(report(findings=[finding("F1", "major", "structure")]), encoding="utf-8")
    run(root, "ingest", AID)
    fix = json.loads(run(root, "brief", AID))
    return {"rc": rc, "review": f / "review", "fix": (root / fix["brief"]).read_text(encoding="utf-8")}


@pytest.mark.blender
@needs_tools
def test_real_tools_write_gates_and_checks_under_final_review_where_the_fix_brief_looks(real_build):
    assert real_build["rc"] == {"assembly": 0, **{p: 0 for p in BUILD_PARTS},
                                **{c: int(c == "layout") for c in CHECKS}}
    rv = real_build["review"]
    assert sorted(p.name for p in (rv / "gates").iterdir()) == sorted(f"{p}.json" for p in BUILD_PARTS)
    assert sorted(p.name for p in (rv / "checks").iterdir()) == sorted(f"{c}.json" for c in CHECKS)
    layout = json.loads((rv / "checks/layout.json").read_text(encoding="utf-8"))
    assert (layout["overall"], layout["data"]["built"]) == ("fail", [4.0, 4.0, 3.3])


@pytest.mark.blender
@needs_tools
def test_a_failing_real_check_is_the_only_script_error_named_in_the_next_fix_brief(real_build):
    assert f"\n8. Đọc trước nguyên văn lỗi script của bản gốc: `{V}1/final/review/checks/layout.json`.\n" in real_build["fix"]


def test_the_review_brief_names_the_profile_and_only_the_handoff_files_so_the_reviewer_needs_no_search(flow):
    text = flow["v2 review brief"]["text"]
    assert "- Profile dự án (`hidden_side_rules`, `scale_refs`): `production/PROJECT-PROFILE.yaml`." in text.splitlines()
    line = [l for l in text.splitlines() if "Concept đã duyệt để đối chiếu" in l]
    assert len(line) == 1 and line[0].endswith(": chỉ `concept_albedo.png`, `concept_shadow.png`, `asset-card.yaml`, "
                                               "`pilot-house.material.md`.")


def test_a_param_review_brief_names_the_image_labels_of_each_variant_so_evidence_cites_one_form(flow):
    assert ("`v2a/<ảnh>`, `v2b/<ảnh>`, `v2c/<ảnh>`; ảnh bản gốc: `v1/<ảnh>`.") in flow["v2 review brief"]["text"]
