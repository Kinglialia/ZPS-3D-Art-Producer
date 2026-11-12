"""L10: after the detail pass, one run of the model starts Blender 3 times, not 9 (join, unwrap, four kit checks, critic
renders, normal renders, review renders), and writes the same result files as the separate tools."""
import json
import os
import shutil
from pathlib import Path

import pytest

from modelkit import (BIN, BLENDER, BLOCKOUT_TOOLS, PILOT, TOOLS, VPY, blender, build, counting_blender, gate_all, gate_args,
                      make_spec, read, sh)

pytestmark = [pytest.mark.blender,
              pytest.mark.skipif(not (VPY.is_file() and os.access(BLENDER, os.X_OK)),
                                 reason="needs Blender and the model tools/setup_deps.sh")]
CONCEPT = PILOT / "_approved/pilot-house/concept_shadow.png"
LIGHT = {"sun": {"azimuth_deg": 45, "elevation_deg": 50}, "concept_cam": {"azimuth_deg": 45, "elevation_deg": 30}}
QA = ("mesh_check", "uv_check", "export_check", "screen_tris_check")


def starts(log: Path):
    return len(log.read_text().splitlines()) if log.is_file() else 0


def fresh(t: Path, name: str, blockout: Path):
    d = t / name
    build(d, [BIN])
    make_spec(d, blockout)
    return d


def set_light(d: Path):
    (d / "spec.json").write_text(json.dumps(read(d / "spec.json") | LIGHT), encoding="utf-8")


def separate(d: Path, blockout: Path, exe):
    """The commands of the worker before L10: a build, a gate and two checks per change, then one Blender start each."""
    glb = d / "pilot-house-untextured.glb"
    assert sh(VPY, BLOCKOUT_TOOLS / "build_parts.py", "assembly", "--work", d)[0] == 0
    for row in read(d / "assembly.json")["data"]["parts"]:
        assert sh(VPY, TOOLS / "self_build/gates.py", "--work", d, "--part", row["name"],
                  "--out", d / f"review/gates/{row['name']}.json")[0] == 0
    assert sh(VPY, TOOLS / "check_detail.py", "--final", d, "--blockout", blockout, "--pilot", "none", "--before-join")[0] == 0
    assert sh(VPY, TOOLS / "check_mesh.py", "--final", d, "--before-join")[0] == 0
    for script in ("join_mesh.py", "unwrap.py"):
        assert blender(script, "--final", d, exe=exe)[0] == 0
    assert sh(VPY, TOOLS / "check_detail.py", "--final", d, "--blockout", blockout, "--pilot", "none")[0] == 0
    assert sh(VPY, TOOLS / "check_mesh.py", "--final", d)[0] == 0
    assert sh(VPY, TOOLS / "check_uv_edge.py", "--final", d)[0] == 0
    for q in QA:
        assert blender(f"asset_checks/{q}.py", "--input", glb, "--spec", d / "spec.json",
                       "--out", d / f"review/checks/qa_{q}.json", exe=exe)[0] == 0
    set_light(d)
    assert blender("self_build/render_views.py", "--work", d, "--spec", d / "spec.json", "--mode", "critic",
                   "--outdir", d / "review/renders", exe=exe)[0] == 0
    assert blender("self_build/render_views.py", "--input", glb, "--mode", "normal", "--outdir", d / "review/renders",
                   "--out", d / "review/renders/normal.json", exe=exe)[0] == 0
    assert blender("render_review.py", "--final", d, "--concept", CONCEPT, exe=exe)[0] == 0


def merged(d: Path, blockout: Path, exe):
    """The commands of the worker after L10: the gate in the venv, three Blender sessions."""
    assert gate_all(d, *gate_args(blockout))[0] == 0
    out = blender("build_model.py", "--final", d, exe=exe)
    assert out[0] == 0, out[1]
    assert gate_all(d, *gate_args(blockout, joined=True))[0] == 0
    out = blender("qa_all.py", "--final", d, exe=exe)
    assert out[0] == 0, out[1]
    set_light(d)
    out = blender("render_all.py", "--final", d, "--concept", CONCEPT, exe=exe)
    assert out[0] == 0, out[1]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    t = tmp_path_factory.mktemp("merged")
    b = t / "blockout"
    build(b)
    old, new = fresh(t, "separate", b), fresh(t, "merged", b)
    (t / "old").mkdir()
    (t / "new").mkdir()
    wrapper_old, log_old = counting_blender(t / "old")
    wrapper_new, log_new = counting_blender(t / "new")
    separate(old, b, wrapper_old)
    merged(new, b, wrapper_new)
    return {"old": old, "new": new, "starts_old": starts(log_old), "starts_new": starts(log_new)}


def tree(d: Path):
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and "parts" not in p.relative_to(d).parts)


def results(d: Path):
    """{result JSON: {overall, check: status}} of every JSON under review/."""
    out = {}
    for p in sorted((d / "review").rglob("*.json")):
        doc = read(p)
        if "overall" in doc:
            out[p.relative_to(d).as_posix()] = (doc["overall"], {c["check"]: c["status"] for c in doc.get("checks", [])})
    return out


def test_the_model_starts_blender_three_times_after_the_detail_pass_not_nine(runs):
    """Every Blender start costs seconds on a laptop and a start of its own can hang."""
    assert (runs["starts_old"], runs["starts_new"]) == (9, 3)


def test_the_merged_tools_write_the_files_the_separate_tools_write(runs):
    """Ingest, the ACCEPTED_FAIL list and assemble find each result at the path the single tool wrote it."""
    assert tree(runs["new"]) == tree(runs["old"])


def test_the_merged_tools_write_the_same_overall_and_the_same_check_status_in_every_result(runs):
    got, want = results(runs["new"]), results(runs["old"])
    assert want and got == want
    assert {n for n in got if "qa_" in n} == {f"review/checks/qa_{q}.json" for q in QA}


def damaged(runs, tmp_path, *gone):
    d = tmp_path / "damaged"
    shutil.copytree(runs["new"], d)
    for name in gone:
        (d / name).unlink()
    return d


def overall(d: Path, *names):
    return {n: read(d / n)["overall"] if (d / n).is_file() else None for n in names}


def test_a_failed_join_stops_the_unwrap_and_leaves_no_unwrap_result_of_an_older_run(runs, tmp_path):
    """The unwrap opens the joined mesh. Without it, an old unwrap.json beside a new join error would read as a model
    that was unwrapped."""
    d = damaged(runs, tmp_path, "spec.json")
    assert (d / "review/unwrap.json").is_file()
    rc, _ = blender("build_model.py", "--final", d)
    assert (rc, overall(d, "review/join.json", "review/unwrap.json")) == (1, {"review/join.json": "error",
                                                                              "review/unwrap.json": None})


def test_a_kit_check_that_fails_does_not_stop_the_three_after_it_and_each_leaves_its_own_result(runs, tmp_path):
    """The four checks do not depend on each other: the worker needs all four failures in one run, not one per run."""
    d = damaged(runs, tmp_path, "pilot-house-untextured.glb")
    rc, _ = blender("qa_all.py", "--final", d)
    got = overall(d, *(f"review/checks/qa_{q}.json" for q in QA))
    assert rc == 1 and set(got.values()) <= {"fail", "error"} and None not in got.values(), got


def test_a_failed_critic_render_does_not_stop_the_normal_and_the_review_renders(runs, tmp_path):
    d = damaged(runs, tmp_path, "assembled.glb")
    rc, _ = blender("render_all.py", "--final", d, "--concept", CONCEPT)
    assert rc == 1
    assert overall(d, "review/renders/normal.json", "review/review.json") == {"review/renders/normal.json": "info",
                                                                           "review/review.json": "info"}
    assert overall(d, "review/renders/renders.json") == {"review/renders/renders.json": "error"}
    assert not (d / "renders.json").exists()


def test_the_merged_renders_are_pixel_for_pixel_the_separate_renders(runs):
    """The stages share one scene. A stage that left a light, a camera or a material behind would change the next
    image, and the names and overall values above would not show it."""
    import numpy as np
    from PIL import Image
    old, new = runs["old"], runs["new"]
    images = sorted(p.relative_to(old) for p in old.rglob("*.png"))
    assert len(images) >= 20
    for rel in images:
        a, b = (np.asarray(Image.open(d / rel).convert("RGBA")) for d in (old, new))
        assert a.shape == b.shape and (a == b).all(), rel
