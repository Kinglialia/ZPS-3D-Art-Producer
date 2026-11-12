"""Copied kit files of the model agent stay byte-identical to kit 905dc93 (D2: each agent keeps its own fixed copy)."""
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "src/zps-3dp-producer/agents/zps-3dp-step-model"
KIT = ROOT / "upstream/zps-art-assets-kit-v0.10.4/src"
TEXT = (AGENT / "SOURCE.md").read_text(encoding="utf-8")
COPIED = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$", TEXT, re.M)
DRAWN = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \| [^|]+ \|$", TEXT, re.M)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


OWN = {"setup_deps.sh", "check_inputs.py", "make_spec.py", "join_mesh.py", "unwrap.py", "check_detail.py",
       "check_mesh.py", "check_uv_edge.py", "render_review.py", "cli.py", "glbread.py"}


def test_source_lists_every_kit_file_in_tools_and_nothing_else():
    tools = [str(p.relative_to(AGENT)) for p in (AGENT / "tools").rglob("*")
             if p.is_file() and ".deps" not in p.parts and "__pycache__" not in p.parts and p.name not in OWN]
    assert sorted(d for d, _, _ in COPIED) == sorted(tools)


@pytest.mark.parametrize("dst,src,digest", COPIED)
def test_copied_file_matches_its_recorded_sha256(dst, src, digest):
    assert sha(AGENT / dst) == digest


@pytest.mark.skipif(not KIT.is_dir(), reason="kit copy under upstream/ is gitignored; root checkout only")
@pytest.mark.parametrize("dst,src,digest", COPIED + DRAWN)
def test_recorded_sha256_is_the_kit_file(dst, src, digest):
    assert sha(KIT / src) == digest


def test_source_names_the_three_bake_functions_unwrap_calls():
    unwrap = (AGENT / "tools/unwrap.py").read_text(encoding="utf-8")
    used = set(re.findall(r"\bbake\.(\w+)\(", unwrap))
    assert used == {"xatlas_unwrap", "set_uv_layer", "uv_occupancy"} and all(f"`{f}()`" in TEXT for f in used)


def test_source_says_export_check_does_not_validate_gltf_while_setup_deps_installs_no_validator():
    """A reader of qa_export_check.json pass must not take it for a glTF validation that never ran."""
    assert "gltf" not in (AGENT / "tools/setup_deps.sh").read_text(encoding="utf-8").lower()
    assert "check `gltf_validator` của `qa_export_check.json` là `not_checked`: `export_check` không validate glTF" in TEXT
