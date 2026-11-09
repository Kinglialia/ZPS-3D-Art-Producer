import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

S = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer"
SCRIPTS = S / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_card  # noqa: E402
import check_profile  # noqa: E402

PROFILE = {
    "project": "Pilot",
    "preset": "topdown-mobile-lowpoly",
    "paths": {"approved": "concepts/_approved", "production": "production", "deliver": "deliver", "env_file": ".env"},
    "has_map": False,
    "pilot_asset": None,
    "scale_refs": [{"name": "nhân vật", "height_m": 1.6, "_source": "anh chốt 2026-11-09"}],
    "hidden_side_rules": ["tường trơn"],
    "style": {"light_convention": "unlit_flat", "top_vs_side_L": 0, "view_bg": None},
    "texture_simple": {"max_materials": 2, "max_color_clusters": 6},
}
CARD = {
    "asset": "05-warehouse", "type": "building", "tier": "standard", "texture_res": None, "tris_max": None,
    "scale_overrides": [{"name": "cửa", "height_m": 1.6}],
    "symmetric": {"left_right": True, "front_back": True},
    "size_m": {"w": 12, "d": 8, "h": 6},
    "hidden_sides": ["cửa sau: chưa biết"], "real_texture_only_notes": [],
}
FILES = ["concept_albedo.png", "concept_shadow.png", "asset-card.yaml", "{id}.material.md"]


def dump(d: dict) -> str:
    return yaml.safe_dump(d, allow_unicode=True, sort_keys=False)


def make_asset(root: Path, aid: str = "05-warehouse", card: dict | None = None, layout: bool = False,
               skip: tuple[str, ...] = ()) -> Path:
    d = root / aid
    d.mkdir(parents=True)
    c = copy.deepcopy(CARD if card is None else card)
    if "asset" in c:
        c["asset"] = aid if c["asset"] == "05-warehouse" else c["asset"]
    names = [f.format(id=aid) for f in FILES] + ([f"{aid}.layout.md"] if layout else [])
    for n in names:
        if n in skip:
            continue
        if n == "asset-card.yaml":
            (d / n).write_text(dump(c), encoding="utf-8")
        else:
            (d / n).write_bytes(b"x")
    return d


def messages(d: Path, has_map: bool | None = False) -> list[str]:
    return [m for _, m in check_card.check(d, has_map)]


def mutated(**kw) -> dict:
    c = copy.deepcopy(CARD)
    c.update(kw)
    return c


def test_complete_asset_dir_has_no_errors(tmp_path):
    assert messages(make_asset(tmp_path)) == []


@pytest.mark.parametrize("name", ["concept_albedo.png", "concept_shadow.png", "asset-card.yaml", "05-warehouse.material.md"])
def test_each_required_file_missing_is_reported_by_name_so_the_artist_knows_what_to_add(tmp_path, name):
    d = make_asset(tmp_path, skip=(name,))
    assert messages(d) == [f"thiếu file {name}"]


def test_empty_file_counts_as_missing_because_a_failed_copy_leaves_zero_bytes(tmp_path):
    d = make_asset(tmp_path)
    (d / "concept_albedo.png").write_bytes(b"")
    assert messages(d) == ["thiếu file concept_albedo.png"]


def test_layout_file_is_required_only_when_project_has_a_map(tmp_path):
    d = make_asset(tmp_path)
    assert messages(d, has_map=True) == ["thiếu file 05-warehouse.layout.md"]
    assert messages(d, has_map=False) == []
    (d / "05-warehouse.layout.md").write_bytes(b"x")
    assert messages(d, has_map=True) == []


def test_missing_card_is_one_error_and_skips_field_checks(tmp_path):
    d = make_asset(tmp_path, skip=("asset-card.yaml",))
    assert messages(d) == ["thiếu file asset-card.yaml"]


def test_broken_yaml_is_reported_without_a_traceback(tmp_path):
    d = make_asset(tmp_path)
    (d / "asset-card.yaml").write_text("type: [unclosed", encoding="utf-8")
    assert messages(d) == ["thẻ: YAML sai"]


@pytest.mark.parametrize("typ", ["character", "creature"])
def test_character_and_creature_are_refused_as_unsupported_in_v1(tmp_path, typ):
    d = make_asset(tmp_path, card=mutated(type=typ))
    assert check_card.check(d, False) == [("type", f"thẻ: type '{typ}' v1 chưa hỗ trợ")]


def test_unknown_type_is_a_card_error_not_an_unsupported_type(tmp_path):
    d = make_asset(tmp_path, card=mutated(type="castle"))
    assert check_card.check(d, False) == [("card", "thẻ: type sai: 'castle' (building | prop | tree | rock)")]


@pytest.mark.parametrize("typ", ["building", "prop", "tree", "rock"])
def test_the_four_v1_types_pass(tmp_path, typ):
    assert messages(make_asset(tmp_path, card=mutated(type=typ))) == []


def test_size_m_is_required_when_project_has_no_map_because_blockout_reads_w_d_h_from_it(tmp_path):
    d = make_asset(tmp_path, card=mutated(size_m=None))
    assert messages(d, has_map=False) == ["thẻ: size_m thiếu (bắt buộc khi has_map: false)"]
    assert messages(d, has_map=None) == []


def test_size_m_may_be_null_when_project_has_a_map(tmp_path):
    d = make_asset(tmp_path, card=mutated(size_m=None), layout=True)
    assert messages(d, has_map=True) == []


@pytest.mark.parametrize("bad", [
    {"w": 12, "d": 8},
    {"w": 12, "d": 8, "h": "6m"},
    {"w": 12, "d": 8, "h": 0},
    {"w": 12, "d": -8, "h": 6},
    {"w": 12, "d": 8, "h": 6, "x": 1},
    [12, 8, 6],
    "12x8x6",
    {"w": True, "d": 8, "h": 6},
])
def test_size_m_with_a_wrong_shape_is_an_error_even_when_has_map_is_unknown(tmp_path, bad):
    d = make_asset(tmp_path, card=mutated(size_m=bad))
    for has_map in (False, None):
        assert messages(d, has_map) == ["thẻ: size_m sai: cần {w, d, h} là số mét > 0"]


def test_asset_id_must_match_the_folder_name_because_the_id_follows_the_asset_to_3d(tmp_path):
    d = make_asset(tmp_path, card=mutated(asset="06-smithy"))
    assert messages(d) == ["thẻ: asset sai: '06-smithy' khác tên thư mục '05-warehouse'"]


@pytest.mark.parametrize("key", ["asset", "type", "tier", "symmetric", "hidden_sides", "real_texture_only_notes"])
def test_required_card_field_missing_is_reported_by_key(tmp_path, key):
    c = copy.deepcopy(CARD)
    del c[key]
    d = make_asset(tmp_path, card=c)
    assert messages(d) == [f"thẻ: thiếu trường {key}"]


@pytest.mark.parametrize("key", ["texture_res", "tris_max", "scale_overrides", "size_m"])
def test_optional_card_field_may_be_absent_and_means_default(tmp_path, key):
    c = copy.deepcopy(CARD)
    del c[key]
    d = make_asset(tmp_path, card=c)
    assert messages(d, has_map=None) == []


HIDDEN_ERR = ("thẻ: hidden_sides sai: cần danh sách chuỗi, hoặc {back|left|right|top|bottom|front: chuỗi}, "
              "ít nhất một dòng (ghi 'chưa biết' nếu chưa rõ)")


def test_card_with_hidden_sides_per_side_is_accepted_because_concept_artists_describe_each_unseen_face(tmp_path):
    card = mutated(hidden_sides={"back": "gỗ ghép, hai bản lề", "top": "nắp vòm, hai đai da"})
    assert messages(make_asset(tmp_path, card=card)) == []


@pytest.mark.parametrize("patch,expected", [
    ({"tier": "epic"}, "thẻ: tier sai: 'epic' (hero | standard | background)"),
    ({"texture_res": "2048"}, "thẻ: texture_res sai: cần số nguyên > 0 hoặc null"),
    ({"texture_res": 0}, "thẻ: texture_res sai: cần số nguyên > 0 hoặc null"),
    ({"tris_max": 1.5}, "thẻ: tris_max sai: cần số nguyên > 0 hoặc null"),
    ({"symmetric": {"left_right": True}}, "thẻ: symmetric sai: cần {left_right, front_back} là true | false"),
    ({"symmetric": {"left_right": "yes", "front_back": True}}, "thẻ: symmetric sai: cần {left_right, front_back} là true | false"),
    ({"hidden_sides": []}, HIDDEN_ERR),
    ({"hidden_sides": "tường trơn"}, HIDDEN_ERR),
    ({"hidden_sides": {}}, HIDDEN_ERR),
    ({"hidden_sides": {"back": ""}}, HIDDEN_ERR),
    ({"hidden_sides": {"inside": "trống"}}, HIDDEN_ERR),
    ({"real_texture_only_notes": "x"}, "thẻ: real_texture_only_notes sai: cần danh sách chuỗi"),
    ({"scale_overrides": [{"name": "cửa", "height_m": 0}]}, "thẻ: scale_overrides sai: cần danh sách {name, height_m > 0}"),
])
def test_card_field_with_a_wrong_value_is_reported_with_the_allowed_values(tmp_path, patch, expected):
    assert messages(make_asset(tmp_path, card=mutated(**patch))) == [expected]


def test_card_cli_prints_one_line_per_error_and_exits_non_zero(tmp_path):
    d = make_asset(tmp_path, card=mutated(tier="epic", type="castle"), skip=("concept_shadow.png",))
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stdout.splitlines() == [
        "thiếu file concept_shadow.png",
        "thẻ: type sai: 'castle' (building | prop | tree | rock)",
        "thẻ: tier sai: 'epic' (hero | standard | background)",
    ]


def test_card_cli_exits_zero_and_prints_nothing_for_a_valid_dir(tmp_path):
    d = make_asset(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d)], capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (0, "")


def test_card_cli_reads_has_map_from_the_profile_file(tmp_path):
    d = make_asset(tmp_path, card=mutated(size_m=None))
    prof = tmp_path / "PROJECT-PROFILE.yaml"
    prof.write_text(dump(PROFILE), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d), "--profile", str(prof)],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout.splitlines()) == (1, ["thẻ: size_m thiếu (bắt buộc khi has_map: false)"])
    prof.write_text(dump({**PROFILE, "has_map": True}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d), "--profile", str(prof)],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout.splitlines()) == (1, ["thiếu file 05-warehouse.layout.md"])


def test_card_cli_with_an_unusable_profile_fails_instead_of_guessing_has_map(tmp_path):
    d = make_asset(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_card.py"), str(d), "--profile", str(tmp_path / "none.yaml")],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stdout.splitlines() == [f"profile: không đọc được {tmp_path / 'none.yaml'}"]


@pytest.fixture
def presets(tmp_path):
    p = tmp_path / "presets"
    p.mkdir()
    (p / "topdown-mobile-lowpoly.yaml").write_text("tiers: {hero: 5000, standard: 3000, background: 1000}\n", encoding="utf-8")
    return p


def prof_errors(tmp_path, presets, profile) -> list[str]:
    f = tmp_path / "PROJECT-PROFILE.yaml"
    f.write_text(dump(profile), encoding="utf-8")
    return check_profile.check(f, presets)


def test_complete_profile_has_no_errors(tmp_path, presets):
    assert prof_errors(tmp_path, presets, PROFILE) == []


@pytest.mark.parametrize("key", ["project", "preset", "paths", "has_map", "pilot_asset", "scale_refs",
                                 "hidden_side_rules", "style", "texture_simple"])
def test_required_profile_field_missing_is_reported_by_key(tmp_path, presets, key):
    p = copy.deepcopy(PROFILE)
    del p[key]
    assert prof_errors(tmp_path, presets, p) == [f"thiếu trường {key}"]


def test_pilot_asset_must_be_written_even_as_null_because_absent_hides_the_pilot_first_rule(tmp_path, presets):
    p = copy.deepcopy(PROFILE)
    del p["pilot_asset"]
    assert prof_errors(tmp_path, presets, p) == ["thiếu trường pilot_asset"]


@pytest.mark.parametrize("section,key", [("paths", "approved"), ("paths", "production"), ("paths", "deliver"),
                                         ("style", "light_convention"), ("style", "top_vs_side_L"),
                                         ("texture_simple", "max_materials"), ("texture_simple", "max_color_clusters")])
def test_required_nested_profile_field_missing_is_reported_by_dotted_key(tmp_path, presets, section, key):
    p = copy.deepcopy(PROFILE)
    del p[section][key]
    assert prof_errors(tmp_path, presets, p) == [f"thiếu trường {section}.{key}"]


def test_env_file_and_view_bg_and_late_sections_are_optional(tmp_path, presets):
    p = copy.deepcopy(PROFILE)
    del p["paths"]["env_file"]
    del p["style"]["view_bg"]
    assert prof_errors(tmp_path, presets, p) == []
    p |= {"detail_examples": {"geometry": ["a"]}, "overrides": {}}
    assert prof_errors(tmp_path, presets, p) == []


@pytest.mark.parametrize("key", ["approvals", "review_board"])
def test_approvals_and_review_board_in_profile_are_errors_because_they_would_change_the_profile_hash(tmp_path, presets, key):
    p = copy.deepcopy(PROFILE) | {key: {"blockout": "human"}}
    assert prof_errors(tmp_path, presets, p) == [f"{key}: không thuộc profile, đặt trong production/policy.yaml"]


def test_preset_without_a_file_is_an_error(tmp_path, presets):
    p = copy.deepcopy(PROFILE) | {"preset": "isometric-pc"}
    assert prof_errors(tmp_path, presets, p) == ["preset sai: không có file presets/isometric-pc.yaml"]


def test_preset_name_with_a_path_is_refused_so_it_cannot_point_outside_the_presets_folder(tmp_path, presets):
    p = copy.deepcopy(PROFILE) | {"preset": "../topdown-mobile-lowpoly"}
    assert prof_errors(tmp_path, presets, p) == ["preset sai: tên không hợp lệ"]


@pytest.mark.parametrize("patch,expected", [
    ({"project": ""}, "project sai: cần chuỗi"),
    ({"has_map": "yes"}, "has_map sai: cần true | false"),
    ({"has_map": 1}, "has_map sai: cần true | false"),
    ({"pilot_asset": 5}, "pilot_asset sai: cần mã asset hoặc null"),
    ({"paths": ["a"]}, "paths sai: cần map"),
    ({"scale_refs": []}, "scale_refs sai: cần danh sách {name, height_m > 0}"),
    ({"scale_refs": [{"name": "x", "height_m": 0}]}, "scale_refs sai: cần danh sách {name, height_m > 0}"),
    ({"hidden_side_rules": "tường trơn"}, "hidden_side_rules sai: cần danh sách chuỗi"),
    ({"style": {"light_convention": "flat", "top_vs_side_L": 0}}, "style.light_convention sai: cần unlit_flat | painted_top_light"),
    ({"style": {"light_convention": "unlit_flat", "top_vs_side_L": "0"}}, "style.top_vs_side_L sai: cần số"),
    ({"style": {"light_convention": "unlit_flat", "top_vs_side_L": 0, "view_bg": 3}}, "style.view_bg sai: cần chuỗi hoặc null"),
    ({"texture_simple": {"max_materials": 0, "max_color_clusters": 6}}, "texture_simple.max_materials sai: cần số nguyên > 0"),
    ({"overrides": []}, "overrides sai: cần map"),
])
def test_profile_field_with_a_wrong_type_or_value_is_reported(tmp_path, presets, patch, expected):
    assert prof_errors(tmp_path, presets, copy.deepcopy(PROFILE) | patch) == [expected]


def test_profile_that_is_not_a_map_or_not_yaml_gives_one_error(tmp_path, presets):
    f = tmp_path / "PROJECT-PROFILE.yaml"
    f.write_text("- a\n- b\n", encoding="utf-8")
    assert check_profile.check(f, presets) == ["profile sai: cần map"]
    f.write_text("a: [unclosed", encoding="utf-8")
    assert check_profile.check(f, presets) == ["profile: YAML sai"]


def test_profile_cli_prints_one_line_per_error_and_exits_non_zero(tmp_path, presets):
    p = copy.deepcopy(PROFILE) | {"approvals": {}, "has_map": "yes"}
    del p["scale_refs"]
    f = tmp_path / "PROJECT-PROFILE.yaml"
    f.write_text(dump(p), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_profile.py"), str(f), "--presets", str(presets)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stdout.splitlines() == [
        "thiếu trường scale_refs",
        "has_map sai: cần true | false",
        "approvals: không thuộc profile, đặt trong production/policy.yaml",
    ]


def test_profile_cli_exits_zero_for_a_valid_profile(tmp_path, presets):
    f = tmp_path / "PROJECT-PROFILE.yaml"
    f.write_text(dump(PROFILE), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_profile.py"), str(f), "--presets", str(presets)],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (0, "")


def test_templates_pass_their_own_checks_so_a_copy_of_the_template_is_a_valid_start(tmp_path, presets):
    prof = tmp_path / "PROJECT-PROFILE.yaml"
    prof.write_text((S / "templates/PROJECT-PROFILE.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    assert check_profile.check(prof, presets) == []
    d = tmp_path / "05-warehouse"
    d.mkdir()
    (d / "asset-card.yaml").write_text((S / "templates/asset-card.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    for n in ("concept_albedo.png", "concept_shadow.png", "05-warehouse.material.md", "05-warehouse.layout.md"):
        (d / n).write_bytes(b"x")
    assert messages(d, has_map=True) == []
    assert messages(d, has_map=False) == []


class Proj:
    def __init__(self, root: Path, presets: Path):
        self.root = root
        self.env = {**os.environ, "PRODUCER_PRESETS": str(presets)}
        self.approved = root / "concepts/_approved"
        self.run("init", "--project", "Pilot", "--concepts", "concepts", check=True)

    def run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, str(SCRIPTS / "producer.py"), *args], cwd=self.root, env=self.env,
                           capture_output=True, text=True)
        if check:
            assert r.returncode == 0, r.stderr
        return r

    def profile(self, **patch):
        p = copy.deepcopy(PROFILE) | patch
        (self.root / "production/PROJECT-PROFILE.yaml").write_text(dump(p), encoding="utf-8")

    def asset(self, aid: str, **kw) -> Path:
        return make_asset(self.approved, aid, **kw)

    def status(self, aid: str) -> dict:
        return json.loads((self.root / f"production/assets/{aid}/status.json").read_text(encoding="utf-8"))

    def registered(self) -> list[str]:
        return sorted(p.name for p in (self.root / "production/assets").iterdir())


@pytest.fixture
def proj(tmp_path, presets):
    p = Proj(tmp_path, presets)
    p.profile()
    return p


def test_intake_listing_groups_valid_assets_and_each_kind_of_error(proj):
    proj.asset("01-ok")
    proj.asset("02-miss", skip=("concept_shadow.png",))
    proj.asset("03-tier", card=mutated(tier="epic"))
    proj.asset("04-orc", card=mutated(type="character"))
    (proj.approved / "Bad_Name").mkdir()
    (proj.approved / "loose.txt").write_text("x")
    out = proj.run("intake", check=True).stdout.splitlines()
    assert out == [
        "Mới, đủ file (1): 01-ok",
        "Thiếu file (1): 02-miss (thiếu file concept_shadow.png)",
        "Loại chưa hỗ trợ v1 (1): 04-orc (thẻ: type 'character' v1 chưa hỗ trợ)",
        "Thẻ sai (1): 03-tier (thẻ: tier sai: 'epic' (hero | standard | background))",
        "Tên thư mục sai quy ước (1): Bad_Name",
        "File rời (1): loose.txt",
        "Ước lượng lô 1 asset: 60–170 phút mỗi asset (mặc định kit); Meshy 10 credit cho lô (1 lần retexture × 10): "
        "người dùng duyệt tổng này một lần.",
        "Chưa có pilot (pilot_asset: null): đăng ký từng asset, `intake <id>`.",
    ]
    assert proj.registered() == []


def test_intake_takes_asset_type_from_the_card_and_points_the_brief_at_the_card(proj):
    d = proj.asset("07-barrel", card=mutated(type="prop"))
    proj.run("intake", "07-barrel", check=True)
    st = proj.status("07-barrel")
    assert (st["type"], st["concept_dir"]) == ("prop", str(d))
    brief = (proj.root / "production/assets/07-barrel/brief.md").read_text(encoding="utf-8")
    assert f"Thẻ asset: `{d / 'asset-card.yaml'}`" in brief


def test_intake_refuses_an_asset_with_a_missing_file_and_registers_nothing(proj):
    proj.asset("02-miss", skip=("concept_shadow.png",))
    r = proj.run("intake", "02-miss")
    assert r.returncode == 1
    assert "02-miss (thiếu file concept_shadow.png)" in r.stderr
    assert proj.registered() == []


def test_intake_refuses_character_as_unsupported_in_v1(proj):
    proj.asset("04-orc", card=mutated(type="character"))
    r = proj.run("intake", "04-orc")
    assert r.returncode == 1
    assert "v1 chưa hỗ trợ" in r.stderr
    assert proj.registered() == []


def test_intake_refuses_when_a_map_project_has_no_layout_file(proj):
    proj.profile(has_map=True)
    proj.asset("05-warehouse")
    r = proj.run("intake", "05-warehouse")
    assert r.returncode == 1
    assert "thiếu file 05-warehouse.layout.md" in r.stderr
    proj.asset("06-smithy", layout=True, card=mutated(size_m=None))
    proj.run("intake", "06-smithy", check=True)
    assert proj.registered() == ["06-smithy"]


def test_intake_without_a_map_requires_size_m_in_the_card(proj):
    proj.asset("05-warehouse", card=mutated(size_m=None))
    r = proj.run("intake", "05-warehouse")
    assert r.returncode == 1
    assert "thẻ: size_m thiếu (bắt buộc khi has_map: false)" in r.stderr
    proj.asset("06-smithy")
    proj.run("intake", "06-smithy", check=True)
    assert proj.registered() == ["06-smithy"]


def test_pilot_null_refuses_all_because_the_pilot_must_prove_the_pipeline_before_a_batch(proj):
    proj.asset("01-a")
    proj.asset("02-b")
    r = proj.run("intake", "--all")
    assert r.returncode == 1
    assert "pilot_asset: null" in r.stderr
    assert proj.registered() == []


def test_pilot_null_accepts_one_named_asset(proj):
    proj.asset("01-a")
    proj.run("intake", "01-a", check=True)
    assert proj.registered() == ["01-a"]


def test_pilot_null_refuses_two_named_assets_in_one_call(proj):
    proj.asset("01-a")
    proj.asset("02-b")
    r = proj.run("intake", "01-a", "02-b")
    assert r.returncode == 1
    assert "pilot_asset: null" in r.stderr
    assert proj.registered() == []


def test_pilot_null_refuses_a_second_asset_while_the_first_is_not_done(proj):
    proj.asset("01-a")
    proj.asset("02-b")
    proj.run("intake", "01-a", check=True)
    assert proj.status("01-a")["state"] == "draft"
    r = proj.run("intake", "02-b")
    assert r.returncode == 1
    assert "đang chạy: 01-a" in r.stderr
    assert proj.registered() == ["01-a"]


def test_pilot_null_accepts_the_next_asset_once_the_first_is_done(proj):
    proj.asset("01-a")
    proj.asset("02-b")
    proj.run("intake", "01-a", check=True)
    p = proj.root / "production/assets/01-a/status.json"
    p.write_text(json.dumps({**proj.status("01-a"), "state": "done"}), encoding="utf-8")
    proj.run("intake", "02-b", check=True)
    assert proj.registered() == ["01-a", "02-b"]


def test_with_a_pilot_set_all_registers_every_valid_asset_and_names_the_rest(proj):
    proj.profile(pilot_asset="01-a")
    proj.asset("01-a")
    proj.asset("02-b")
    proj.asset("03-bad", skip=("concept_albedo.png",))
    r = proj.run("intake", "--all", check=True)
    assert proj.registered() == ["01-a", "02-b"]
    assert r.stdout.splitlines()[:2] == ["Thiếu file (1): 03-bad (thiếu file concept_albedo.png)",
                                         "Đã đăng ký 2: 01-a, 02-b."]


def test_intake_without_a_profile_points_to_project_setup(proj):
    (proj.root / "production/PROJECT-PROFILE.yaml").unlink()
    proj.asset("01-a")
    r = proj.run("intake")
    assert r.returncode == 1
    assert "production/PROJECT-PROFILE.yaml" in r.stderr and "zps-3dp-project-setup" in r.stderr


def test_intake_with_an_invalid_profile_lists_the_profile_errors_and_registers_nothing(proj):
    proj.profile(approvals={"blockout": "human"})
    proj.asset("01-a")
    r = proj.run("intake", "01-a")
    assert r.returncode == 1
    assert "approvals: không thuộc profile, đặt trong production/policy.yaml" in r.stderr
    assert proj.registered() == []


def test_intake_with_a_preset_that_does_not_exist_is_refused(proj):
    proj.profile(preset="isometric-pc")
    r = proj.run("intake")
    assert r.returncode == 1
    assert "preset sai: không có file presets/isometric-pc.yaml" in r.stderr


def test_init_creates_gitignore_with_env_so_the_meshy_key_is_never_committed(tmp_path, presets):
    Proj(tmp_path, presets)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines() == [".env"]


def test_init_appends_env_to_an_existing_gitignore_once(tmp_path, presets):
    (tmp_path / ".gitignore").write_text("node_modules\n.envrc", encoding="utf-8")
    p = Proj(tmp_path, presets)
    p.run("init", "--project", "Pilot", "--concepts", "concepts", check=True)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines() == ["node_modules", ".envrc", ".env"]


def test_init_keeps_a_gitignore_that_already_lists_env(tmp_path, presets):
    (tmp_path / ".gitignore").write_text(".env\nbuild\n", encoding="utf-8")
    Proj(tmp_path, presets)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".env\nbuild\n"


def test_guideline_lists_required_files_and_the_check_command_with_no_placeholder_left(tmp_path, presets):
    Proj(tmp_path, presets)
    g = (tmp_path / "concepts/GUIDELINE.md").read_text(encoding="utf-8")
    assert "{{" not in g
    for name in ("concept_albedo.png", "concept_shadow.png", "asset-card.yaml", "<id>.material.md", "<id>.layout.md"):
        assert name in g
    venv_py = SCRIPTS / ".deps/venv/bin/python"
    assert f"{venv_py} {SCRIPTS / 'check_card.py'} " in g
    assert f"--profile {tmp_path.resolve() / 'production/PROJECT-PROFILE.yaml'}" in g
