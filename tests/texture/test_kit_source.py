"""Kit files the Producer scripts run (gen_api, finalize, estimate) stay byte-identical to kit 905dc93 (D2, D24.2)."""
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KITCOPY = ROOT / "src/zps-3dp-producer/scripts/kit"
KIT = ROOT / "upstream/zps-art-assets-kit-v0.10.4/src"
COPIED = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$", (KITCOPY / "SOURCE.md").read_text(encoding="utf-8"),
                    re.M)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_source_lists_every_file_of_the_kit_copy():
    files = [p.relative_to(KITCOPY).as_posix() for p in KITCOPY.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.name != "SOURCE.md"]
    assert sorted(d for d, _, _ in COPIED) == sorted(files)


@pytest.mark.parametrize("dst,src,digest", COPIED)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(KITCOPY / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", COPIED)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest
