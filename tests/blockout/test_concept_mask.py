"""concept_mask.py output is read by the kit's raster.concept_mask as a mask (coding-checklist row 5)."""
import subprocess

import pytest
from PIL import Image, ImageDraw

from conftest import TOOLS

VPY = TOOLS / ".deps/venv/bin/python"
pytestmark = pytest.mark.skipif(not VPY.is_file(), reason="run tools/setup_deps.sh first (numpy, cv2)")
KIT_READ = ("import sys; sys.path.insert(0, sys.argv[1]); import raster; m = raster.concept_mask(sys.argv[2]); "
            "print(int(m.sum()), bool(m[60, 50]), bool(m[25, 50]))")


def kit_reads(path):
    out = subprocess.run([str(VPY), "-c", KIT_READ, str(TOOLS / "lib"), str(path)], capture_output=True, text=True,
                         check=True)
    return out.stdout.split()


def test_kit_reads_the_mask_with_the_gap_between_columns_as_background(tmp_path):
    concept = tmp_path / "front.png"
    im = Image.new("RGB", (120, 100), (0, 177, 64))
    d = ImageDraw.Draw(im)
    for box in ((20, 20, 79, 29), (20, 30, 39, 89), (60, 30, 79, 89)):
        d.rectangle(box, fill=(180, 120, 60))
    im.save(concept)
    mask = tmp_path / "mask_front.png"
    r = subprocess.run([str(VPY), str(TOOLS / "concept_mask.py"), "--image", str(concept), "--out", str(mask)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.count("\n") == 1, r.stdout + r.stderr
    assert "key=#00B140" in r.stdout
    assert kit_reads(mask) == ["3000", "False", "True"]
    assert kit_reads(concept) == ["12000", "True", "True"]
