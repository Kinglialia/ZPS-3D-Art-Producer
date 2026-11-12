"""The texture step through the real CLI with fake agents: ingest refuses stale renders (T2) and `P brief` prepares
final/ of a fix round (L14, C24)."""
import hashlib
import json

import pytest

from flowkit import A, AID, brief_lines, counts, to_texture
from shared import fixed_line

ALBEDO = "albedo_2048.png"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worker(f, name, renders_sha=None, extra_files=()):
    """A texture worker that writes its outputs, then a renders.json that names `renders_sha`; ingests its report."""
    out = f.brief(name + " brief")
    vd = (f.root / out["report"]).parent
    f.outputs(vd, "texture", name)
    for rel in extra_files:
        (vd / "final" / rel).parent.mkdir(parents=True, exist_ok=True)
        (vd / "final" / rel).write_text(f"{rel} {name}\n", encoding="utf-8")
    renders = vd / "final/review/renders.json"
    if renders_sha == "current":
        renders_sha = sha(vd / "final" / ALBEDO)
    if renders_sha:
        renders.write_text(json.dumps({"albedo": ALBEDO, "albedo_sha256": renders_sha, "renders": {}}), encoding="utf-8")
    ph = brief_lines(f.cp[name + " brief"]["text"], "PROFILE_HASH")
    (f.root / out["report"]).write_text(f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: none\nPROFILE_HASH: {ph}\n"
                                        + fixed_line(f.root, AID), encoding="utf-8")
    f.keep(name + " worker", f.p("ingest", AID, "--agent-id", f"w-{name}"))
    return vd


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    f = to_texture(tmp_path_factory.mktemp("texture"))
    f.vd1 = worker(f, "t1", renders_sha="0" * 64, extra_files=("review/id_map.png", "review/lit_34_front.png",
                                                                 "review/unlit_game.png", "review/thumb.png",
                                                                 "review/render_texture.json", "notes/kept.txt"))
    f.after_stale = f.st()
    f.brief("t2 brief")
    f.vd2 = f.root / A / "texture/v2"
    f.prepared = {p.relative_to(f.vd2 / "final").as_posix(): p.read_bytes() for p in (f.vd2 / "final").rglob("*") if p.is_file()}
    return f


def test_a_render_made_from_another_albedo_goes_back_to_the_worker_and_no_reviewer_is_called_t2(flow):
    """The reviewer would grade pictures of an albedo that is no longer the file: the check says to render again."""
    st = flow.after_stale
    assert (st["stage"], st["state"], st["direct"], st["fix_round"]) == ("texture", "running", 1, 1)
    assert not (flow.vd1 / "brief-review.md").exists()
    check = json.loads((flow.vd1 / "final/review/checks/render_fresh.json").read_text(encoding="utf-8"))
    assert (check["overall"], check["checks"][0]["status"]) == ("fail", "fail")
    assert check["checks"][0]["note"] == "render lại: albedo_2048.png đã đổi sau lần render (chạy lại render_texture.py)"
    assert "texture v1 · worker DONE (check fail)" in (flow.root / "production/ledger.md").read_text(encoding="utf-8")
    assert "render_fresh.json" in flow.cp["t2 brief"]["text"]


def test_a_fix_round_gets_final_prepared_from_its_base_minus_what_the_render_and_measure_write_c24(flow):
    """One wrong copy by hand left a stale measure or render in the new version; the script copies by the step's list."""
    assert set(flow.prepared) == {ALBEDO, "notes.md", "texture_spec.json", "review/id_map.png", "notes/kept.txt"}
    assert flow.prepared[ALBEDO] == (flow.vd1 / "final" / ALBEDO).read_bytes()
    assert "`final/` có sẵn, không chép tay." in flow.cp["t2 brief"]["text"]
    assert "`final/` có sẵn" not in flow.cp["t1 brief"]["text"]


def test_a_render_of_the_current_albedo_reaches_the_reviewer_t2(flow):
    worker(flow, "t2", renders_sha="current")
    check = json.loads((flow.vd2 / "final/review/checks/render_fresh.json").read_text(encoding="utf-8"))
    assert (flow.st()["state"], check["overall"], (flow.vd2 / "brief-review.md").is_file()) == ("reviewing", "pass", True)
