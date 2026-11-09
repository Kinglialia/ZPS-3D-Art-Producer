"""Copied kit files stay byte-identical to kit 905dc93 (D2: Blockout keeps its own fixed copy)."""
import hashlib
import re
from pathlib import Path

import pytest

from conftest import AGENT

KIT = Path(__file__).resolve().parents[2] / "upstream/zps-art-assets-kit-v0.10.4/src"
ROWS = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$", (AGENT / "SOURCE.md").read_text(encoding="utf-8"), re.M)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_source_lists_every_copied_file():
    assert len(ROWS) == 12
    assert {d for d, _, _ in ROWS} >= {"tools/self_build/graph.py", "tools/lib/bootstrap.py", "tools/render_blockout_views.py"}


@pytest.mark.parametrize("dst,src,digest", ROWS)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(AGENT / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", ROWS)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest
