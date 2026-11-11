"""D34, D32.6: the skill repo holds only what every kind of object shares. A function, fixture or data file of one asset
would ship with the skill and steer the agent toward that asset, so nothing tracked under src/ or tests/ names one,
and every binary fixture is one a script in the repo makes from synthetic data."""
import re
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


def test_the_toon_bevel_numbers_of_one_asset_live_only_in_the_preset_with_their_origin():
    """D34.2: 9 mm / 2 segments came from one asset (Run 4). In code they would apply to every object unseen; in the
    preset they sit beside a note that says to measure again."""
    code = [p for p in tracked("src") if p.endswith(".py") and "0.009" in (ROOT / p).read_text(encoding="utf-8")]
    preset = (ROOT / "src/zps-3dp-producer/presets/topdown-mobile-lowpoly.yaml").read_text(encoding="utf-8")
    line = next(l for l in preset.splitlines() if l.strip().startswith("toon:"))
    assert (code, "radius_m: 0.009" in line, "tạm, đo lại sau 3–5 asset khác loại" in line) == ([], True, True)


# D34.4: words of each kind of object, to tell which kinds an example names. A heuristic: it reads only example
# clauses, "(ví dụ ...)", "(vd ...)" or `ví dụ "..."`.
KINDS = {"building": ("mái", "cửa", "tường", "trụ", "diềm", "tầng", "dầm", "ống máng", "nhà", "công trình"),
         "tree": ("cây", "cành", "tán", "thân", "gốc", "lá"),
         "rock": ("đá", "tảng"),
         "prop": ("bàn", "ghế", "thùng", "chân bàn")}
EXAMPLE = re.compile(r"\((?:ví dụ|vd)\b([^)]*)\)|(?:ví dụ|vd)[: ]+\"([^\"]+)\"", re.I)
# Words that only one past asset needed (board rows, lid gap, hinge): no shipped file uses them.
ONE_ASSET = ("hàng ván", "khe nắp", "bản lề", "board_rows")


def kinds_of(clause):
    low = clause.lower()
    return {k for k, words in KINDS.items() if any(re.search(rf"(?<!\w){w}(?!\w)", low) for w in words)}


def shipped_text():
    return {p: (ROOT / p).read_text(encoding="utf-8") for p in tracked("src", "editions")
            if p.endswith((".md", ".yaml", ".toml", ".py")) and not is_binary((ROOT / p).read_bytes())}


def test_the_examples_of_a_shipped_file_are_not_all_from_one_kind_of_object():
    """An agent copies its examples. A file whose every example is a building steers the agent toward buildings when
    it builds a tree or a table, so a file with two or more object examples names at least two kinds."""
    narrow = {}
    for p, text in shipped_text().items():
        hits = [k for a, b in EXAMPLE.findall(text) if (k := kinds_of(a or b))]
        if len(hits) >= 2 and len(set().union(*hits)) < 2:
            narrow[p] = sorted(set().union(*hits))
    assert narrow == {}


def test_the_heuristic_sees_a_file_of_building_examples_as_one_kind():
    text = '(ví dụ "mép mái") và (ví dụ 2 cửa sổ)'
    assert [kinds_of(a or b) for a, b in EXAMPLE.findall(text)] == [{"building"}, {"building"}]


def test_no_shipped_file_uses_the_words_of_one_past_asset():
    assert [f"{p}: {w}" for p, t in shipped_text().items() for w in ONE_ASSET if w in t.lower()] == []
