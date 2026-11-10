"""D34, D32.6: the skill repo holds only what every kind of object shares. A function, fixture or data file of one asset
would ship with the skill and steer the agent toward that asset, so nothing tracked under src/ or tests/ names one,
and every binary fixture is one a script in the repo makes from synthetic data."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Built by concatenation, so this file does not match its own search.
NEEDLES = ("woo" + "den-ch" + "est", "woo" + "den_ch" + "est", "rư" + "ơng")
FIXTURE_DIRS = {"pilot"}
MADE_BY = {"tests/fixtures/pilot/_approved/pilot-house/concept_albedo.png": "tests/fixtures/pilot/make_concepts.py",
           "tests/fixtures/pilot/_approved/pilot-house/concept_shadow.png": "tests/fixtures/pilot/make_concepts.py"}


def tracked(*dirs):
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *dirs], capture_output=True, check=True)
    return [p for p in out.stdout.decode().split("\0") if p]


def is_binary(data: bytes) -> bool:
    if b"\0" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def test_no_tracked_file_under_src_or_tests_names_a_past_asset():
    hits = [f"{p}: {n}" for p in tracked("src", "tests") if not is_binary(data := (ROOT / p).read_bytes())
            for n in NEEDLES if n in data.decode("utf-8").lower()]
    assert hits == []


def test_tests_fixtures_holds_only_the_listed_synthetic_folders():
    assert {Path(p).parts[2] for p in tracked("tests/fixtures")} == FIXTURE_DIRS


def test_every_binary_under_tests_is_made_by_a_script_in_the_repo():
    """A binary copied from a real run cannot be checked for asset data; a generated one can be made again."""
    binaries = sorted(p for p in tracked("tests") if is_binary((ROOT / p).read_bytes()))
    assert binaries == sorted(MADE_BY)
    for out, script in MADE_BY.items():
        assert script in tracked("tests") and Path(out).name in (ROOT / script).read_text(encoding="utf-8")
