"""L3: blockout_md.py writes item 2, section 3 and section 8 of blockout.md from the JSON files and keeps what the
worker wrote. The review page shows the first three lines as the summary (board.py), so their place must not move."""
import hashlib
import json
import subprocess

import pytest

from conftest import HUT_SOURCES, TOOLS, hut

VPY = TOOLS / ".deps/venv/bin/python"
needs_venv = pytest.mark.skipif(not VPY.is_file(), reason="needs tools/setup_deps.sh")


def built(tmp_path, graph=None, version="v1"):
    f = tmp_path / f"production/assets/hut/blockout/{version}/final"
    f.mkdir(parents=True)
    (f / "part_graph.json").write_text(json.dumps(graph or hut()), encoding="utf-8")
    (f / "sources.json").write_text(json.dumps(HUT_SOURCES), encoding="utf-8")
    subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True, check=True)
    return f


def md(f, *extra):
    r = subprocess.run([str(VPY), str(TOOLS / "blockout_md.py"), "--work", str(f), *extra], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), (f / "blockout.md").read_text(encoding="utf-8") if (f / "blockout.md").is_file() else None


WORKER = {"line 2": "1 thân, 1 cửa, 2 thùng", 4: "| param | giá trị |", 5: "real: cửa nhô 5 cm", 6: "Mặt sau tường trơn.",
          7: "Không có."}


def fill(text):
    text = text.replace("TODO: thành phần đếm trên concept, một dòng", WORKER["line 2"])
    for n, key in ((4, "bảng đo"), (5, "ghi chú real"), (6, "từng chỗ"), (7, "mâu thuẫn")):
        text = "\n".join(WORKER[n] if f"TODO: {key}" in line else line for line in text.splitlines()) + "\n"
    return text


@needs_venv
def test_a_missing_file_starts_from_the_skeleton_with_the_summary_lines_first_and_a_todo_for_every_worker_section(tmp_path):
    f = built(tmp_path)
    rc, line, text = md(f)
    lines = text.splitlines()
    assert lines[:3] == [
        "# Blockout hut v1", "TODO: thành phần đếm trên concept, một dòng",
        "Bbox dựng 4 × 4 × 3.7 m so với asset-card.yaml size_m 4 × 4 × 3.7 m: lệch tối đa 0.0 % (ngưỡng 2 %), đạt."]
    assert [l for l in lines if l.startswith("## ")] == [
        "## 3. Version và hash", "## 4. Bảng đo", "## 5. Ghi chú real/texture_only", "## 6. Blockout tự quyết",
        "## 7. Mâu thuẫn giữa các nguồn", "## 8. Lỗi mesh còn lại", "## 9. Thay đổi so với version trước",
        "## 10. Trạng thái duyệt"]
    assert (rc, line.endswith("còn TODO ở dòng 2, mục 4, 5, 6, 7")) == (1, True), line


@needs_venv
def test_section_3_has_the_sha256_of_the_graph_and_the_hash_of_both_files_and_section_8_the_union_health(tmp_path):
    f = built(tmp_path)
    text = md(f)[2]
    graph = hashlib.sha256((f / "part_graph.json").read_bytes()).hexdigest()
    code = json.loads((f / "assembly.json").read_text(encoding="utf-8"))["data"]["code_hash"]
    part3 = text.split("## 3. Version và hash\n")[1].split("\n## ")[0].strip().splitlines()
    assert part3[:2] == ["- Version: v01", f"- part_graph.json: sha256 {graph}"]
    assert part3[3] == f"- Hash gộp part_graph.json + parts_lib.py: {code}"
    part8 = text.split("## 8. Lỗi mesh còn lại\n")[1].split("\n## ")[0].strip().splitlines()
    assert part8 == ["- non-manifold: 0. zero-area: 0. đỉnh rời: 0.", "- Hợp nhất: manifold3d."]


@needs_venv
def test_what_the_worker_wrote_stays_and_a_rerun_with_no_todo_left_exits_0_and_changes_nothing(tmp_path):
    f = built(tmp_path)
    md(f)
    (f / "blockout.md").write_text(fill((f / "blockout.md").read_text(encoding="utf-8")) + "\n## 11. Thêm\nghi chú tự do\n",
                                   encoding="utf-8")
    rc, line, text = md(f)
    assert (rc, line.endswith("đủ mục")) == (0, True), line
    for value in WORKER.values():
        assert value in text
    assert text.endswith("## 11. Thêm\nghi chú tự do\n")
    assert md(f)[2] == text


@needs_venv
def test_a_new_build_changes_the_three_generated_places_and_leaves_the_worker_text(tmp_path):
    g = hut()
    f = built(tmp_path, g)
    md(f)
    (f / "blockout.md").write_text(fill((f / "blockout.md").read_text(encoding="utf-8")), encoding="utf-8")
    before = (f / "blockout.md").read_text(encoding="utf-8")
    g["params"]["wall_h"] = 2.7
    (f / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    subprocess.run([str(VPY), str(TOOLS / "build_parts.py"), "assembly", "--work", str(f)], capture_output=True, check=True)
    after = md(f)[2]
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert any(a.startswith("Bbox dựng") and "4 × 4 × 4 m" in b for a, b in changed)
    assert any(a.startswith("- part_graph.json: sha256") for a, b in changed)
    assert all(a.startswith(("Bbox dựng", "- ")) for a, b in changed)
    for value in WORKER.values():
        assert value in after


@needs_venv
def test_a_version_after_the_first_asks_for_its_changes_and_the_first_says_there_are_none(tmp_path):
    text2 = md(built(tmp_path / "two", version="v2"))[2]
    text1 = md(built(tmp_path / "one", version="v1"))[2]
    assert "## 9. Thay đổi so với version trước\nTODO: part nào, param nào đổi, vì sao" in text2
    assert "## 9. Thay đổi so với version trước\nKhông có (version đầu)." in text1
    assert text2.splitlines()[0] == "# Blockout hut v2"


@needs_venv
def test_it_stops_when_assembly_json_is_not_built_from_this_graph_because_the_numbers_would_be_another_graphs(tmp_path):
    f = built(tmp_path)
    g = hut()
    g["params"]["wall_h"] = 2.7
    (f / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    rc, line, text = md(f)
    assert (rc, text, "assembly.json is not built from this part_graph.json" in line) == (2, None, True), line


@needs_venv
def test_a_file_the_worker_started_by_hand_keeps_every_line_and_gets_the_bbox_line_inserted_not_written_over_one(tmp_path):
    f = built(tmp_path)
    (f / "blockout.md").write_text("# Blockout hut v1\n1 nhà\n| param | giá trị |\n| wall_h | 2.4 |\n", encoding="utf-8")
    rc, line, text = md(f)
    lines = text.splitlines()
    assert lines[:2] == ["# Blockout hut v1", "1 nhà"] and lines[2].startswith("Bbox dựng")
    assert lines[3:5] == ["| param | giá trị |", "| wall_h | 2.4 |"]


@needs_venv
def test_a_file_that_does_not_start_with_the_title_is_refused_and_left_as_it_is(tmp_path):
    f = built(tmp_path)
    (f / "blockout.md").write_text("| param | giá trị |\n| wall_h | 2.4 |\n", encoding="utf-8")
    rc, line, text = md(f)
    assert (rc, text) == (2, "| param | giá trị |\n| wall_h | 2.4 |\n") and "does not start with" in line


@needs_venv
def test_a_file_copied_from_the_base_version_gets_its_own_title_changes_section_and_status(tmp_path):
    """The fix round copies blockout.md of v1 into v2/final: line 1 must say v2, and the first-version text of section 9
    would be a false record of the changes."""
    f1 = built(tmp_path / "one", version="v1")
    md(f1)
    f2 = built(tmp_path / "two", version="v2")
    (f2 / "blockout.md").write_text((f1 / "blockout.md").read_text(encoding="utf-8").replace(
        "Chờ duyệt,", "Anh duyệt,"), encoding="utf-8")
    rc, line, text = md(f2)
    assert text.splitlines()[0] == "# Blockout hut v2"
    assert "## 9. Thay đổi so với version trước\nTODO: part nào, param nào đổi, vì sao" in text
    assert "Anh duyệt," not in text and "## 10. Trạng thái duyệt\nChờ duyệt," in text
