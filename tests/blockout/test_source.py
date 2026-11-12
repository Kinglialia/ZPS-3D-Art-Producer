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
    assert len(ROWS) == 8
    assert {d for d, _, _ in ROWS} >= {"tools/self_build/graph.py", "tools/lib/bootstrap.py"}


@pytest.mark.parametrize("dst,src,digest", ROWS)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(AGENT / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", ROWS)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest


REMOVED = ("fit_camera.py", "apply_edit.py", "render_blockout_views.py", "bpy_cookbook.md")


def test_no_own_file_points_to_a_kit_file_that_was_removed_from_the_skill():
    """D42.5: the pointer sends a reader to a file that is not there. Copied kit files are left as they are."""
    frozen = {d for d, _, _ in ROWS}
    own = [p for p in (AGENT / "tools").rglob("*") if p.suffix in (".py", ".sh", ".yaml") and ".deps" not in p.parts]
    own += [p for p in AGENT.rglob("*.md")] + [AGENT / "config.yaml"]
    hits = {p.relative_to(AGENT).as_posix(): name for p in own if p.relative_to(AGENT).as_posix() not in frozen
            and p.name != "SOURCE.md" for name in REMOVED if name in p.read_text(encoding="utf-8")}
    assert hits == {}


def test_config_has_no_key_that_no_tool_reads():
    """paths.blender was read only by the kit apply_edit.py. The worker passes Blender to RUN: through the brief."""
    import yaml
    cfg = yaml.safe_load((AGENT / "config.yaml").read_text(encoding="utf-8"))
    assert "paths" not in cfg
    tools = "".join(p.read_text(encoding="utf-8") for p in (AGENT / "tools").rglob("*.py") if ".deps" not in p.parts)
    assert '["paths"]' not in tools and "get(\"paths\")" not in tools
