"""check_proportion.py: the built model has the proportions of the concept in every orthographic view (D36, B9).

The concept has no scale, so only the width : height ratio of the silhouette box is compared. The model box comes from
assembly.json, the concept box from the mask file the spec names for that view."""
import json
import struct
import subprocess
import zlib

import pytest

from conftest import HUT_ROWS, HUT_SOURCES, TOOLS, hut, write_build

VPY = TOOLS / ".deps/venv/bin/python"
pytestmark = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh (numpy, cv2)")


def write_mask(path, w, h, pad=20):
    """A grey PNG: black border, white object of w x h pixels (the form concept_mask.py writes)."""
    W, H = w + 2 * pad, h + 2 * pad
    rows = [bytes([0]) + bytes(W) if not pad <= y < pad + h else bytes([0]) + bytes(pad) + b"\xff" * w + bytes(pad)
            for y in range(H)]

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    path.write_bytes(png)


def box_rows(w, d, h):
    return [{"name": "base", "parent": None, "contact": None, "depth": None,
             "bbox_min": [-w / 2, -d / 2, 0.0], "bbox_max": [w / 2, d / 2, h]}]


def spec_for(tmp_path, **views):
    """{view: (width px, height px)} -> spec.json with one mask file per view."""
    spec = {"concept": {"views": {}}}
    for view, (w, h) in views.items():
        write_mask(tmp_path / f"{view}.png", w, h)
        spec["concept"]["views"][view] = f"{view}.png"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def run_proportion(tmp_path, work, spec=None):
    out = tmp_path / "proportion.result.json"
    cmd = [str(VPY), str(TOOLS / "check_proportion.py"), "--work", str(work), "--out", str(out)]
    r = subprocess.run(cmd + (["--spec", str(spec)] if spec else []), capture_output=True, text=True)
    return r, (json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None)


def statuses(res):
    return {c["check"]: c["status"] for c in res["checks"]}


def test_a_concept_with_the_proportions_of_the_model_passes_in_every_view_and_prints_one_line(tmp_path):
    work = write_build(tmp_path / "w", rows=HUT_ROWS)
    spec = spec_for(tmp_path, front=(400, 370), back=(400, 370), left=(400, 370), right=(400, 370), top=(400, 400))
    r, res = run_proportion(tmp_path, work, spec)
    assert (r.returncode, res["overall"], len(r.stdout.strip().splitlines())) == (0, "pass", 1), r.stdout + r.stderr
    assert statuses(res) == {"assembly.fresh": "pass", **{f"proportion.{v}": "pass" for v in
                                                          ("front", "back", "left", "right", "top")}}


def test_a_concept_ten_percent_wider_than_the_model_fails_and_names_the_view_and_both_ratios(tmp_path):
    """The hut box is 4 x 3.7 m: ratio 1.081. A mask 450 x 370 px (1.216) is 11 % wider: a roof or a wall in the
    wrong place. 430 x 370 (1.162) is 7 % off and passes."""
    work = write_build(tmp_path / "w", rows=HUT_ROWS)
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(450, 370), left=(430, 370)))
    assert (r.returncode, res["overall"]) == (1, "fail")
    assert statuses(res)["proportion.front"] == "fail" and statuses(res)["proportion.left"] == "pass"
    front = next(c for c in res["checks"] if c["check"] == "proportion.front")
    assert front["value"] == -0.111 and front["threshold"] == 0.1
    assert "model 1.081" in front["note"] and "concept 1.216" in front["note"]


def test_each_view_reads_the_axes_it_shows_so_a_long_thin_model_fails_a_front_shaped_side_mask(tmp_path):
    """A 4 x 2 x 3.7 m model: front ratio 1.081 (x : z), left ratio 0.541 (y : z), top ratio 2.0 (x : y)."""
    work = write_build(tmp_path / "w", rows=box_rows(4.0, 2.0, 3.7))
    good = spec_for(tmp_path, front=(400, 370), left=(200, 370), top=(400, 200))
    r, res = run_proportion(tmp_path, work, good)
    assert (r.returncode, res["overall"]) == (0, "pass"), res["checks"]
    bad = spec_for(tmp_path, left=(400, 370))
    r, res = run_proportion(tmp_path, work, bad)
    assert (r.returncode, statuses(res)["proportion.left"]) == (1, "fail")


def test_without_a_spec_or_a_mask_file_nothing_is_compared_and_the_result_is_not_checked(tmp_path):
    work = write_build(tmp_path / "w")
    r, res = run_proportion(tmp_path, work)
    assert (r.returncode, res["overall"], len(r.stdout.strip().splitlines())) == (0, "not_checked", 1)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"concept": {"views": {"front": "missing.png"}}}), encoding="utf-8")
    r, res = run_proportion(tmp_path, work, spec)
    assert (r.returncode, res["overall"], statuses(res)["proportion.front"]) == (0, "not_checked", "not_checked")


def test_a_three_quarter_view_is_not_compared_because_its_box_depends_on_the_camera(tmp_path):
    work = write_build(tmp_path / "w")
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(400, 370), **{"34": (300, 300)}))
    assert (r.returncode, statuses(res)["proportion.34"], statuses(res)["proportion.front"]) == (0, "not_checked", "pass")


def test_the_spec_defaults_to_the_one_the_worker_writes_beside_final(tmp_path):
    work = write_build(tmp_path / "v1" / "final")
    (tmp_path / "v1" / "work").mkdir()
    spec_for(tmp_path / "v1" / "work", front=(400, 450))
    r, res = run_proportion(tmp_path, work)
    assert (r.returncode, statuses(res)["proportion.front"]) == (1, "fail")


def test_a_stale_assembly_fails_instead_of_comparing_an_old_build(tmp_path):
    work = write_build(tmp_path / "w", stale=True)
    r, res = run_proportion(tmp_path, work, spec_for(tmp_path, front=(400, 370)))
    assert (r.returncode, res["overall"]) == (1, "fail")
