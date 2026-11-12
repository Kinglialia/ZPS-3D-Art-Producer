"""The guideline is the only text a Concept Artist agent reads before it hands an asset to the pipeline. An example in it
that the pipeline rejects teaches the agent a handoff that fails, so each example here goes through the code that
reads it."""
import inspect
import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

S = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer"
sys.path.insert(0, str(S / "scripts"))

import check_card  # noqa: E402
from core import intake  # noqa: E402

TEXT = (S / "templates/GUIDELINE.md").read_text(encoding="utf-8")
SIZE = 1024


def fenced(lang: str) -> list[str]:
    return re.findall(rf"^```{lang}\n(.*?)\n```$", TEXT, re.S | re.M)


CARDS = fenced("yaml")
HANDOFFS = fenced("markdown")


def boxes_of(handoff: str) -> dict[str, tuple[int, int, int, int]]:
    _, rows = intake.handoff_rows(handoff)
    key = next(k for k in rows[0] if intake.BOX_HEADER in k)
    return {r["mã"]: tuple(map(int, re.findall(r"\d+", r[key]))) for r in rows}


def hexes_of(handoff: str) -> dict[str, str]:
    _, rows = intake.handoff_rows(handoff)
    key = next(k for k in rows[0] if intake.HEX_HEADER in k)
    return {r["mã"]: intake.HEX.search(r[key])[0].upper() for r in rows}


def paint(path: Path, handoff: str) -> None:
    """A concept whose background is the BG line and whose box of each code holds that code's hex."""
    im = Image.new("RGB", (SIZE, SIZE), intake.BG_LINE.search(handoff)[1])
    hexes = hexes_of(handoff)
    for code, (x, y, w, h) in boxes_of(handoff).items():
        im.paste(tuple(int(hexes[code][i:i + 2], 16) for i in (1, 3, 5)), (x, y, x + w, y + h))
    im.save(path)


def handoff_dir(tmp_path: Path, i: int) -> Path:
    card = yaml.safe_load(CARDS[i])
    d = tmp_path / card["asset"]
    d.mkdir()
    for name in ("concept_albedo.png", "concept_shadow.png"):
        paint(d / name, HANDOFFS[i])
    (d / "asset-card.yaml").write_text(CARDS[i], encoding="utf-8")
    (d / f"{card['asset']}.material.md").write_text(HANDOFFS[i], encoding="utf-8")
    return d


def test_each_card_example_has_a_handoff_example_of_the_same_asset():
    assert len(CARDS) == len(HANDOFFS) >= 2
    for card, handoff in zip(CARDS, HANDOFFS):
        assert f"# Material Handoff — {yaml.safe_load(card)['asset']}" in handoff.splitlines()


def test_the_examples_cover_a_building_and_a_prop_with_a_card_that_asks_for_no_view_images():
    cards = [yaml.safe_load(c) for c in CARDS]
    assert {"building", "prop"} <= {c["type"] for c in cards}
    assert "none" in {c["views"] for c in cards}


@pytest.mark.parametrize("i", range(len(CARDS)))
def test_a_card_example_passes_check_card_so_an_agent_that_copies_it_is_accepted(tmp_path, i):
    d = handoff_dir(tmp_path, i)
    assert check_card.check(d, has_map=False) == []
    assert check_card.warnings(d, None) == []


@pytest.mark.parametrize("i", range(len(CARDS)))
def test_the_text_codes_of_a_card_example_are_codes_of_its_handoff(i):
    assert set(yaml.safe_load(CARDS[i]).get("text_codes") or []) <= set(boxes_of(HANDOFFS[i]))


def test_the_first_card_example_shows_every_field_of_the_card_template():
    """templates/asset-card.yaml lists the fields the code reads; a field the guideline never shows is a field
    the Concept Artist never writes."""
    fields = set(yaml.safe_load((S / "templates/asset-card.yaml").read_text(encoding="utf-8")))
    assert set(yaml.safe_load(CARDS[0])) == fields


@pytest.mark.parametrize("i", range(len(HANDOFFS)))
def test_a_handoff_example_gives_every_code_a_colour_with_no_warning_from_intake(tmp_path, i):
    d = handoff_dir(tmp_path, i)
    aid = d.name
    dest = tmp_path / "concept_colors.json"
    assert intake.measure_handoff(aid, d, dest) == []
    assert json.loads(dest.read_text(encoding="utf-8")) == hexes_of(HANDOFFS[i])


@pytest.mark.parametrize("i", range(len(HANDOFFS)))
def test_the_boxes_of_a_handoff_example_do_not_overlap_so_each_lies_in_one_material(i):
    boxes = list(boxes_of(HANDOFFS[i]).items())
    for n, (a, (ax, ay, aw, ah)) in enumerate(boxes):
        for b, (bx, by, bw, bh) in boxes[n + 1:]:
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, f"{a} overlaps {b}"


@pytest.mark.parametrize("i", range(len(HANDOFFS)))
def test_a_handoff_example_has_the_background_as_one_line_the_intake_reads(i):
    assert intake.BG_LINE.search(HANDOFFS[i])
    assert not re.search(r"^Nền ảnh concept:", HANDOFFS[i], re.M)


def test_the_measuring_snippet_prints_the_median_colour_that_intake_measures_in_the_same_box(tmp_path, monkeypatch, capsys):
    """A hex the agent measures with the snippet must match what intake finds, or every handoff gets a warning."""
    im = Image.new("RGB", (SIZE, SIZE), (238, 238, 238))
    im.paste((90, 64, 48), (400, 100, 500, 200))
    im.paste((250, 250, 250), (400, 100, 500, 130))
    im.save(tmp_path / "concept_albedo.png")
    monkeypatch.chdir(tmp_path)
    x, y, w, h = 400, 100, 100, 100
    exec(fenced("python")[0], {"x": x, "y": y, "w": w, "h": h})
    assert capsys.readouterr().out.strip() == intake.colors_tool().median_hex(im, (x, y, x + w, y + h)) == "#5A4030"


def test_the_template_keeps_every_placeholder_that_init_fills_and_no_other():
    filled = set(re.findall(r"\{\{(\w+)\}\}", inspect.getsource(intake.init)))
    assert filled == {"PROJECT", "CONCEPTS", "DATE", "CHECK_CARD", "PROFILE"}
    assert set(re.findall(r"\{\{(\w+)\}\}", TEXT)) == filled


def test_the_check_command_is_a_numbered_step_of_the_handoff_procedure():
    assert re.search(r"^\d+\. Chạy `\{\{CHECK_CARD\}\} <thư mục asset> --profile \{\{PROFILE\}\}`", TEXT, re.M)


def test_the_title_carries_the_version():
    assert TEXT.splitlines()[0] == "# {{PROJECT}} — Guideline cho agent · v1.5 · {{DATE}}"


def test_no_line_names_a_decision_a_spec_file_or_an_earlier_run():
    """The reader cannot open the spec, and history in a rule reads as a rule."""
    bad = [l for l in TEXT.splitlines()
           if re.search(r"(?<![#\w])D\d+\b|docs/|^Nguồn:|\bv0\.\d|lần chạy thử|Run \d", l)]
    assert bad == []
