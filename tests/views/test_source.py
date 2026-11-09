"""Copied kit files of the views agent stay byte-identical to kit 905dc93 (D2: each agent keeps its own fixed copy)."""
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-views"
KIT = ROOT / "upstream/zps-art-assets-kit-v0.10.4/src"
TEXT = (AGENT / "SOURCE.md").read_text(encoding="utf-8")
COPIED = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$", TEXT, re.M)
DRAWN = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \| [^|]+ \|$", TEXT, re.M)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_source_lists_the_four_copied_files_and_the_measure_fix_lives_outside_them():
    assert [d for d, _, _ in COPIED] == ["tools/render_blockout_views.py", "tools/measure_views.py",
                                         "tools/palette_report.py", "tools/lib/common.py"]
    assert "mv.flood_background = lambda bgish: bgish" in (AGENT / "tools/measure.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("dst,src,digest", COPIED)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(AGENT / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", COPIED + DRAWN)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest
