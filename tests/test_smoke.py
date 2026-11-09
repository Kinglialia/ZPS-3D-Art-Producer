import json
import subprocess
import sys
import tomllib
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts" / "producer.py"


def run(cwd: Path, *args: str) -> str:
    r = subprocess.run([sys.executable, str(P), *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_init_then_new_creates_files_and_starts_at_blockout(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    for f in ("production/pipeline.toml", "production/rubrics/default.md", "production/rubrics/building.md",
              "production/ledger.md", "production/schedule.md", "concepts/GUIDELINE.md"):
        assert (tmp_path / f).is_file(), f
    assert (tmp_path / "concepts/_approved").is_dir()
    assert (tmp_path / "production/assets").is_dir()

    cfg = tomllib.loads((tmp_path / "production/pipeline.toml").read_text(encoding="utf-8"))
    assert cfg["project"]["name"] == "Pilot"
    assert cfg["paths"]["approved"] == f"{(tmp_path / 'concepts').resolve()}/_approved"
    steps = cfg["steps"]
    assert [s["id"] for s in steps] == ["blockout", "views_front", "views_rest", "model", "texture", "assemble"]
    assert [s.get("enabled", True) for s in steps] == [True, True, True, True, False, False]
    assert [s["gate"] for s in steps] == ["review_human", "review", "review_human", "review_human", "review",
                                          "checks_human"]
    assert (steps[0]["agent"], steps[0]["reviewer"], steps[0]["uses"]) == ("step-blockout", "check-blockout", ["blender"])
    assert "agent" not in steps[5] and "reviewer" not in steps[5]
    assert cfg["limits"] == {"blender": 2, "codex_image": 2, "meshy": 1}

    out = run(tmp_path, "new", "house-a", "--title", "House A")
    assert out.startswith("OK house-a → draft.")
    a = tmp_path / "production/assets/house-a"
    for f in ("status.json", "brief.md", "rubric.md", "feedback.md"):
        assert (a / f).is_file(), f
    st = json.loads((a / "status.json").read_text(encoding="utf-8"))
    assert {k: st[k] for k in ("id", "title", "type", "priority", "stage", "state", "versions", "approved",
                               "fix_round", "note", "concept_dir")} == {
        "id": "house-a", "title": "House A", "type": "asset", "priority": 2, "stage": "blockout",
        "state": "draft", "versions": {}, "approved": {}, "fix_round": 0, "note": "chờ duyệt rubric",
        "concept_dir": None}
    assert (a / "rubric.md").read_text(encoding="utf-8") == (tmp_path / "production/rubrics/default.md").read_text(encoding="utf-8")
    assert "house-a · tạo mới (draft, rubric chưa duyệt)" in (tmp_path / "production/ledger.md").read_text(encoding="utf-8")


def test_init_keeps_existing_files(tmp_path):
    run(tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    pt = tmp_path / "production/pipeline.toml"
    pt.write_text(pt.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    out = run(tmp_path, "init", "--project", "Other", "--concepts", "concepts")
    assert "giữ nguyên production/pipeline.toml" in out
    assert pt.read_text(encoding="utf-8").endswith("# edited\n")
