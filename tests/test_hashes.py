import copy
import json
from argparse import Namespace

import pytest

from shared import PROFILE, PROFILE_HASH, write_profile
from test_loop import AID, Flow, counts, pass_v2
from core import briefs, hashes, intake, loop, policy
from core.state import ProducerError, load_cfg, save_st


@pytest.fixture
def flow(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(loop, "recheck", lambda st, step, d: ([], None))
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    write_profile(tmp_path)
    intake.new(Namespace(id=AID, title="House A", type="asset", priority=2, deadline=None), load_cfg())
    intake.ready(Namespace(ids=[AID]))
    capsys.readouterr()
    return Flow(tmp_path, capsys)


def enable_views(f):
    p = f.root / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views"\nenabled = false', 'id = "views"'),
                 encoding="utf-8")


def approve_blockout(f):
    enable_views(f)
    pass_v2(f)
    f.human("approve")
    assert (f.st["stage"], f.st["state"]) == ("views", "todo")


def test_profile_hash_ignores_paths_and_underscore_keys_so_editing_notes_or_paths_warns_no_running_asset():
    edited = copy.deepcopy(PROFILE)
    edited["scale_refs"][0]["_source"] = "từ pilot 01-hut"
    edited["paths"]["approved"] = "/khác/_approved"
    edited["_note"] = "ghi chú"
    reordered = dict(reversed(list(PROFILE.items())))
    assert (hashes.digest(PROFILE), hashes.digest(edited), hashes.digest(reordered)) == (PROFILE_HASH,) * 3
    assert hashes.digest(PROFILE | {"has_map": True}) != PROFILE_HASH


def test_an_unquoted_yaml_date_in_the_profile_hashes_like_its_text_instead_of_crashing_the_brief():
    import datetime as dt
    assert hashes.digest(PROFILE | {"start": dt.date(2026, 11, 9)}) == hashes.digest(PROFILE | {"start": "2026-11-09"})


def test_tree_hash_skips_dot_files_so_finder_metadata_never_flags_an_edit(tmp_path):
    (tmp_path / "part_graph.json").write_text("{}", encoding="utf-8")
    before = hashes.tree_hash(tmp_path)
    (tmp_path / ".DS_Store").write_bytes(b"\0finder")
    (tmp_path / "review").mkdir()
    (tmp_path / "review/.DS_Store").write_bytes(b"\0finder")
    assert hashes.tree_hash(tmp_path) == before


@pytest.mark.parametrize("profile, error", [
    (None, "chưa có production/PROJECT-PROFILE.yaml: nạp skill zps-3dp-project-setup"),
    (PROFILE | {"approvals": {"blockout": "human"}},
     "profile sai:\n  approvals: không thuộc profile, đặt trong production/policy.yaml"),
])
def test_brief_refuses_while_the_profile_is_missing_or_invalid_so_no_worker_builds_on_wrong_numbers(flow, profile, error):
    if profile is None:
        (flow.root / "production/PROJECT-PROFILE.yaml").unlink()
    else:
        write_profile(flow.root, profile)
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert (str(e.value), flow.st["state"], flow.st["versions"]) == (error, "todo", {})


def test_brief_writes_the_profile_hash_records_inputs_and_names_the_full_agent(flow):
    out = flow.brief()
    assert out["agent"] == "zps-3dp-step-blockout"
    assert "PROFILE_HASH: 786cfc66bdd2" in flow.text(out).splitlines()
    st = flow.st
    assert (st["inputs"], st["sources"]) == (
        {"blockout": {"v1": {"concept": None, "card": None, "profile": PROFILE_HASH, "art_direction": ""}}},
        {"concept": None, "card": None, "profile": PROFILE_HASH})
    flow.work(out=out)
    assert flow.brief()["agent"] == "zps-3dp-check-blockout"


@pytest.mark.parametrize("line, error", [
    ("PROFILE_HASH: 000000000000",
     f"production/assets/{AID}/blockout/v1/worker-out.md: PROFILE_HASH 000000000000 khác brief ({PROFILE_HASH})"),
    ("OUTPUT: final/", f"production/assets/{AID}/blockout/v1/worker-out.md sai contract: thiếu PROFILE_HASH"),
])
def test_ingest_rejects_a_missing_or_foreign_profile_hash_and_keeps_the_asset_running(flow, line, error):
    out = flow.brief()
    (flow.root / out["report"]).write_text(f"STATUS: DONE\n{line}\n", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        loop.ingest(Namespace(id=AID, agent_id="w1"))
    assert (str(e.value), flow.st["state"]) == (error, "running")


def test_one_byte_edit_to_an_approved_part_graph_is_caught_at_brief_and_at_ingest_of_the_next_step(flow):
    approve_blockout(flow)
    graph = flow.v(2) / "final/part_graph.json"
    graph.write_text("y", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert (str(e.value), flow.st["state"]) == ("blockout v2: final/ đã duyệt bị sửa sau khi duyệt (hash lệch)", "todo")
    graph.write_text("x", encoding="utf-8")
    out = flow.brief()
    inp = flow.st["inputs"]["views"]["v1"]["blockout"]
    assert (inp["v"], inp["hash"]) == (2, flow.st["approved_hash"]["blockout"])
    graph.write_text("y", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        flow.work(out=out)
    assert (str(e.value), flow.st["state"]) == ("blockout v2: final/ đã duyệt bị sửa sau khi duyệt (hash lệch)", "running")


def test_a_version_built_from_an_older_blockout_is_labelled_stale_without_the_producer_doing_anything(flow):
    approve_blockout(flow)
    flow.work()
    assert flow.st["stale"] == {}
    flow.human("redo", "mái cao hơn", "blockout")
    assert flow.st["stale"] == {"views v1": "blockout v2"}
    flow.work(fixed="H1")
    (flow.v(3) / "final/part_graph.json").write_text("v3", encoding="utf-8")
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="H1=better", prior=["- H1: resolved | evidence: clay_front"])
    flow.human("approve")
    assert (flow.st["approved"], flow.st["stale"]) == ({"blockout": 3}, {"views v1": "blockout v2"})


def test_reapproving_identical_content_is_not_stale_because_inputs_compare_content(flow):
    approve_blockout(flow)
    flow.work()
    flow.human("redo", "thử lại", "blockout")
    flow.work(fixed="H1")
    flow.review(verdict="PASS", top_fix=None, counts=counts(), rubric="massing=pass", compare="H1=better", prior=["- H1: resolved | evidence: clay_front"])
    flow.human("approve")
    assert (flow.st["approved"], flow.st["stale"]) == ({"blockout": 3}, {})


def test_warnings_follow_content_of_concept_card_and_profile_and_ack_clears_them(flow):
    concept = flow.root / "concepts/_approved/house-a"
    concept.mkdir(parents=True)
    (concept / "concept_albedo.png").write_bytes(b"png1")
    (concept / "asset-card.yaml").write_text("size_m: {w: 6, d: 5, h: 4}\n", encoding="utf-8")
    st = flow.st
    st["concept_dir"] = str(concept)
    save_st(st)
    flow.brief()
    cfg = load_cfg()

    def warn():
        return hashes.warnings_for(cfg, flow.st)

    (concept / "concept_albedo.png").write_bytes(b"png1")
    edited = copy.deepcopy(PROFILE)
    edited["scale_refs"][0]["_source"] = "từ pilot"
    write_profile(flow.root, edited)
    policy.set_approval(Namespace(step="blockout", who="reviewer", by="anh nói", confirm_spend=False))
    assert warn() == []
    (concept / "asset-card.yaml").write_text("size_m: {w: 6, d: 5, h: 5}\n", encoding="utf-8")
    assert warn() == ["thẻ đổi sau khi bắt đầu"]
    (concept / "concept_albedo.png").write_bytes(b"png2")
    write_profile(flow.root, PROFILE | {"has_map": True})
    assert warn() == ["concept đổi sau khi bắt đầu", "thẻ đổi sau khi bắt đầu", "profile đổi sau khi bắt đầu"]
    hashes.ack(Namespace(id=AID, note="giữ"))
    assert warn() == []
    assert json.loads((flow.root / f"production/assets/{AID}/status.json").read_text())["sources"]["profile"] == (
        hashes.digest(PROFILE | {"has_map": True}))


def reference_tree_hash(d):
    """The hash as it was before the cache: relative path, NUL, bytes of every file, dot files and `skip` left out."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file() and not any(s.startswith(".") for s in x.relative_to(d).parts)):
        h.update(p.relative_to(d).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A final/ with a nested GLB-like file; `reads` lists the files tree_hash read from disk."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "production").mkdir()
    d = tmp_path / "final"
    (d / "review").mkdir(parents=True)
    (d / "part_graph.json").write_text("{}", encoding="utf-8")
    (d / "assembled.glb").write_bytes(b"glTF" * 1000)
    (d / "review/lineup.png").write_bytes(b"png")
    (d / ".DS_Store").write_bytes(b"finder")
    reads = []
    real = hashes.read_file
    monkeypatch.setattr(hashes, "read_file", lambda p: reads.append(p.name) or real(p))
    return d, reads


def test_a_cached_tree_hash_equals_the_hash_of_the_bytes_so_the_hashes_stored_at_approval_stay_valid_c15(tree):
    d, reads = tree
    first = hashes.tree_hash(d)
    assert first == reference_tree_hash(d)
    reads.clear()
    assert (hashes.tree_hash(d), reads) == (first, [])
    assert (d.parent / "production/hash-cache.json").is_file()


def test_a_tree_that_did_not_change_is_not_read_again_c15(tree):
    """The reproduction: every brief and ingest read each byte of every approved final/ again, under the global lock."""
    d, reads = tree
    hashes.tree_hash(d)
    assert sorted(reads) == ["assembled.glb", "lineup.png", "part_graph.json"]
    reads.clear()
    for _ in range(3):
        hashes.tree_hash(d)
    assert reads == []


def test_a_changed_file_changes_the_hash_even_when_its_size_stays_c15(tree):
    d, reads = tree
    before = hashes.tree_hash(d)
    (d / "part_graph.json").write_text("[]", encoding="utf-8")
    after = hashes.tree_hash(d)
    assert (after != before, after == reference_tree_hash(d), "part_graph.json" in reads[3:]) == (True, True, True)


def test_a_touched_file_is_read_again_and_the_hash_stays_c15(tree):
    import os
    d, reads = tree
    before = hashes.tree_hash(d)
    reads.clear()
    st = (d / "assembled.glb").stat()
    os.utime(d / "assembled.glb", ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert (hashes.tree_hash(d), "assembled.glb" in reads) == (before, True)
    reads.clear()
    assert (hashes.tree_hash(d), reads) == (before, [])


def test_the_cache_is_keyed_by_folder_and_skip_so_the_concept_tree_without_its_card_keeps_its_own_hash_c15(tree):
    d, _ = tree
    (d / "asset-card.yaml").write_text("a: 1", encoding="utf-8")
    full, without = hashes.tree_hash(d), hashes.tree_hash(d, skip="asset-card.yaml")
    assert full != without
    (d / "asset-card.yaml").write_text("a: 2", encoding="utf-8")
    assert (hashes.tree_hash(d, skip="asset-card.yaml"), hashes.tree_hash(d) != full) == (without, True)


def test_a_broken_cache_file_is_ignored_and_rebuilt_c15(tree):
    d, _ = tree
    expect = hashes.tree_hash(d)
    (d.parent / "production/hash-cache.json").write_text("{not json", encoding="utf-8")
    assert hashes.tree_hash(d) == expect
    assert hashes.tree_hash(d) == expect


def test_a_same_size_edit_of_an_approved_file_after_the_cache_is_warm_still_stops_the_next_brief_c15(flow):
    approve_blockout(flow)
    assert (flow.root / "production/hash-cache.json").is_file()
    flow.brief()
    st = flow.st
    st["dispatches"][-1]["ended"] = st["dispatches"][-1]["at"]
    save_st(st)
    graph = flow.v(2) / "final/part_graph.json"
    assert graph.read_text(encoding="utf-8") == "x"
    graph.write_text("z", encoding="utf-8")
    with pytest.raises(ProducerError) as e:
        briefs.run(Namespace(id=AID))
    assert str(e.value) == "blockout v2: final/ đã duyệt bị sửa sau khi duyệt (hash lệch)"
