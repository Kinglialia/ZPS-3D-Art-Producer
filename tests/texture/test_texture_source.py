"""Copied kit files of the texture agent stay byte-identical to kit 905dc93 (D2: each agent keeps its own fixed copy)."""
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-texture"
KIT = ROOT / "upstream/zps-art-assets-kit-v0.10.4/src"
TEXT = (AGENT / "SOURCE.md").read_text(encoding="utf-8")
COPIED = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$", TEXT, re.M)
DRAWN = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \| [^|]+ \|$", TEXT, re.M)
OWN = {"setup_deps.sh", "tex.py", "check_inputs.py", "texture_complexity.py", "id_map.py", "check_meshy.py",
       "base_fill.py", "render_texture.py", "render_paint_views.py", "project_views.py", "seam_fix.py", "crop_edit.py",
       "tone_fix.py", "tex_measure.py"}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_source_lists_every_kit_file_in_tools_and_nothing_else():
    tools = [p.relative_to(AGENT).as_posix() for p in (AGENT / "tools").rglob("*")
             if p.is_file() and ".deps" not in p.parts and "__pycache__" not in p.parts and p.name not in OWN]
    assert sorted(d for d, _, _ in COPIED) == sorted(tools)


@pytest.mark.parametrize("dst,src,digest", COPIED)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(AGENT / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", COPIED + DRAWN)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest
