"""D35: the `views` field of the asset card decides which views steps run and which side images they make."""
import copy
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from flowkit import AID, A, PROJECT_KEY, Flow, counts
from shared import SCRIPTS, pilot_project
from test_intake import CARD, make_asset, messages, mutated

import check_card
from core import asset_card, loop
from core.state import TEMPLATES

TOOLS = SCRIPTS.parent / "agents"


def test_the_four_values_and_their_side_views_are_the_d32_table():
    """full has no top: no step after views needs a top image (D35.5); back keeps front as the colour reference."""
    assert check_card.VIEW_SETS == {"none": (), "back": ("back",), "full": ("back", "left", "right"),
                                    "full_top": ("back", "left", "right", "top")}
    assert check_card.NO_CARD_VIEWS == "full"


@pytest.mark.parametrize("value", ["none", "back", "full", "full_top"])
def test_each_views_value_passes_check_card(tmp_path, value):
    assert messages(make_asset(tmp_path, card=mutated(views=value))) == []


def test_a_card_without_views_fails_check_card_because_guideline_and_code_once_disagreed_on_the_default(tmp_path):
    card = copy.deepcopy(CARD)
    del card["views"]
    assert messages(make_asset(tmp_path, card=card)) == ["thẻ: thiếu trường views"]


@pytest.mark.parametrize("value", ["top", "all", ["back"], True])
def test_an_unknown_views_value_fails_check_card_with_the_allowed_values(tmp_path, value):
    assert messages(make_asset(tmp_path, card=mutated(views=value))) == [
        f"thẻ: views sai: '{value}' (none | back | full | full_top)"]


def test_an_asset_made_by_new_has_no_card_and_gets_the_full_set(tmp_path):
    """No card = no choice was made: the whole set stays as it was before the field was required."""
    st = {"id": "x", "concept_dir": None}
    assert (asset_card.views(st), asset_card.sides(st)) == ("full", ("back", "left", "right"))
    assert check_card.card_views(tmp_path) == "full"


def asset(tmp_path, value):
    card = copy.deepcopy(CARD)
    if value is None:
        del card["views"]
    d = make_asset(tmp_path, card=card if value is None else mutated(views=value))
    return {"id": "05-warehouse", "concept_dir": str(d), "state": "waiting_human", "stage": "blockout"}


def cfg():
    import tomllib
    c = tomllib.loads((TEMPLATES / "pipeline.toml").read_text(encoding="utf-8"))
    for s in c["steps"]:
        s.setdefault("enabled", True)
        s.setdefault("regions", [])
    return c


@pytest.mark.parametrize("value, steps, sides", [
    ("none", ["blockout", "model", "texture", "assemble"], []),
    ("back", ["blockout", "views_front", "views_rest", "model", "texture", "assemble"], ["final/back.png"]),
    ("full", ["blockout", "views_front", "views_rest", "model", "texture", "assemble"],
     ["final/back.png", "final/left.png", "final/right.png"]),
    (None, ["blockout", "views_front", "views_rest", "model", "texture", "assemble"],
     ["final/back.png", "final/left.png", "final/right.png"]),
    ("full_top", ["blockout", "views_front", "views_rest", "model", "texture", "assemble"],
     ["final/back.png", "final/left.png", "final/right.png", "final/top.png"]),
])
def test_each_value_gives_its_step_list_and_its_views_rest_images(tmp_path, value, steps, sides):
    """A full set must not go blocked for a missing top.png, so the outputs follow the card."""
    from core.state import outputs_of
    c = cfg()
    st = asset(tmp_path, value)
    assert [s["id"] for s in asset_card.steps(c, st)] == steps
    rest = next(s for s in c["steps"] if s["id"] == "views_rest")
    assert [o for o in outputs_of(rest, st) if o.endswith(("back.png", "left.png", "right.png", "top.png"))] == sides
    assert asset_card.regions(rest, st) == [s[6:-4] for s in sides]


@pytest.mark.parametrize("value, nxt", [("none", "model"), ("back", "views_front"), (None, "views_front")])
def test_approving_the_blockout_moves_to_model_when_the_card_has_no_view_set(tmp_path, value, nxt):
    c = cfg()
    st = asset(tmp_path, value)
    loop.move(st, "approve", c)
    assert (st["stage"], st["state"]) == (nxt, "todo")


def no_views_flow(root: Path) -> Flow:
    """The pilot with `views: none` from intake to the texture brief, one round per step."""
    f = Flow(root)
    pilot_project(root)
    card = root / "concepts/_approved" / AID / "asset-card.yaml"
    card.write_text(card.read_text(encoding="utf-8").replace("views: full", "views: none"), encoding="utf-8")
    (root / ".env").write_text(f"MESHY_API_KEY={PROJECT_KEY}\n", encoding="utf-8")
    f.p("intake", AID)
    f.p("ready", AID)
    for name in ("b1", "m1"):
        f.work(name)
        f.review(name, verdict="PASS", counts=counts(), top_fix=None, evidence="lit_34_front.png")
        f.human(f"approve {name}", "đạt", "--action", "approve")
    f.brief("t1")
    return f


@pytest.fixture(scope="module")
def none_flow(tmp_path_factory):
    return no_views_flow(tmp_path_factory.mktemp("none"))


def test_views_none_goes_from_blockout_straight_to_model_and_then_texture_d35(none_flow):
    assert none_flow.cp["approve b1"]["st"]["stage"] == "model"
    assert none_flow.cp["approve m1"]["st"]["stage"] == "texture"
    assert not (none_flow.root / A / "views_front").exists()


@pytest.mark.parametrize("name", ["m1 brief", "m1 review brief", "t1"])
def test_views_none_model_and_texture_briefs_build_and_point_at_no_view_folder_d35(none_flow, name):
    text = none_flow.cp[name]["text"]
    assert ("views_front" in text, "views_rest" in text) == (False, False)
    assert "VIEWS: none" in text.splitlines()


def test_views_none_texture_brief_names_the_material_file_for_the_texture_notes_d35(none_flow):
    row = next(l for l in none_flow.cp["t1"]["text"].splitlines() if l.startswith("5. Concept đã duyệt"))
    assert row.endswith("chỉ đọc `concept_albedo.png`, `concept_shadow.png`, `asset-card.yaml`, `pilot-house.material.md`. "
                        "Bỏ qua file và thư mục khác (bản nháp cũ).")


def test_views_none_redo_of_a_views_step_is_refused(none_flow):
    out = none_flow.p("feedback", AID, "x", "--action", "redo", "--step", "views_rest", ok=False)
    assert out.strip().endswith("pilot-house: bước views_rest không chạy cho asset này (thẻ views: none)")


def test_views_none_exceptions_of_the_final_readme_take_the_texture_only_notes_of_the_card_d35(tmp_path):
    import assemble
    d = make_asset(tmp_path, card=mutated(views="none", real_texture_only_notes=[
        "real: cửa nhô 5 cm", "texture_only: vân gỗ, không dựng"]))
    assert assemble.exceptions({"id": "05-warehouse", "concept_dir": str(d), "approved": {}}) == [
        "- thẻ: texture_only: vân gỗ, không dựng"]


def tool(agent, name, *args):
    import subprocess
    return subprocess.run([sys.executable, str(TOOLS / agent / "tools" / name), *map(str, args)], capture_output=True,
                          text=True)


def test_texture_check_inputs_with_views_none_wants_the_material_file_not_the_view_folders_d35(tmp_path):
    import json
    c, b, m = tmp_path / "C", tmp_path / "B", tmp_path / "M"
    for d in (c, b, m / "parts", m / "review"):
        d.mkdir(parents=True)
    (c / "asset-card.yaml").write_text("views: none\n", encoding="utf-8")
    for p in (b / "sources.json", m / "spec.json", m / "part_graph.json", m / "review/join.json",
              c / "concept_albedo.png", c / "concept_shadow.png", m / "x-untextured.glb"):
        p.write_text(json.dumps({"asset": "x"}), encoding="utf-8")
    r = tool("zps-3dp-step-texture", "check_inputs.py", "--final", tmp_path / "F", "--blockout", b, "--model", m,
             "--concept", c)
    assert (r.returncode, r.stdout) == (1, f"[check_inputs] thiếu {c / 'C.material.md'}\n")
    (c / "C.material.md").write_text("# Material\n", encoding="utf-8")
    assert tool("zps-3dp-step-texture", "check_inputs.py", "--final", tmp_path / "F", "--blockout", b, "--model", m,
                "--concept", c).returncode == 0


def test_texture_complexity_with_views_none_reads_the_motif_from_the_material_file_d35(tmp_path):
    import json
    from PIL import Image
    b, c, f = tmp_path / "B", tmp_path / "C", tmp_path / "F"
    for d in (b, c):
        d.mkdir()
    (b / "sources.json").write_text(json.dumps({"materials": ["WOOD"]}), encoding="utf-8")
    (c / "asset-card.yaml").write_text("tier: standard\nviews: none\n", encoding="utf-8")
    im = Image.new("RGB", (64, 64), (255, 255, 255))
    im.paste((120, 80, 40), (16, 16, 48, 48))
    im.save(c / "concept_albedo.png")
    (c / "C.material.md").write_text("| WOOD | gỗ | biển chữ TAVERN trên mái |\n", encoding="utf-8")
    prof = tmp_path / "p.yaml"
    prof.write_text("texture_simple: {max_materials: 2, max_color_clusters: 6}\n", encoding="utf-8")
    r = tool("zps-3dp-step-texture", "texture_complexity.py", "--final", f, "--blockout", b, "--concept", c,
             "--profile", prof, "--mode", "paint")
    assert r.returncode == 0, r.stdout
    spec = json.loads((f / "texture_spec.json").read_text(encoding="utf-8"))
    assert (spec["simple"], spec["scores"]["motif"]) == (False, ["| WOOD | gỗ | biển chữ TAVERN trên mái |"])
