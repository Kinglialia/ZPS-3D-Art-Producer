import json
import os
import subprocess
import sys

import pytest

from shared import P, write_profile

KEY = "msy-SECRET-0123456789"
KIT = """import argparse, json, pathlib
a = argparse.ArgumentParser(); a.add_argument("--out"); o = a.parse_args().out
with open(pathlib.Path(__file__).with_name("calls.txt"), "a") as f: f.write("run\\n")
pathlib.Path(o).write_text(json.dumps({"overall": "pass", "data": {"features": {"xatlas_unwrap": False}}}))
print("[preflight] overall=pass")
"""


class Proj:
    def __init__(self, root):
        self.root, self.bin = root, root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PATH": str(self.bin), "BLENDER": str(self.bin / "blender")}
        self.kit = root / "kit/preflight.py"
        self.kit.parent.mkdir()
        self.kit.write_text(KIT, encoding="utf-8")

    def tool(self, name, out=""):
        p = self.bin / name
        p.write_text(f"#!/bin/sh\necho '{out}'\n", encoding="utf-8")
        p.chmod(0o755)

    def run(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(P), *args], cwd=self.root, env=self.env, capture_output=True, text=True)
        assert (r.returncode == 0) is ok, r.stderr
        return r

    def result(self):
        d = json.loads((self.root / "production/preflight.json").read_text(encoding="utf-8"))
        d.pop("at")
        return d


@pytest.fixture
def proj(tmp_path):
    p = Proj(tmp_path)
    p.run("init", "--project", "Pilot", "--concepts", "concepts")
    write_profile(tmp_path)
    p.run("new", "house-a", "--title", "House A")
    p.run("ready", "house-a")
    return p


def test_preflight_records_each_feature_in_one_line_and_never_prints_the_meshy_key(proj):
    proj.tool("blender", "Blender 4.2.1 LTS")
    proj.tool("codex", "codex-cli 0.50.0")
    (proj.root / ".env").write_text(f"MESHY_API_KEY={KEY}\n", encoding="utf-8")
    proj.env["PRODUCER_KIT"] = str(proj.kit)
    r = proj.run("preflight")
    assert r.stdout == "preflight: bật blender, codex_image, meshy; kit pass → production/preflight.json\n"
    assert proj.result() == {
        "features": {"blender": True, "codex_image": True, "meshy": True},
        "blender": {"path": str(proj.bin / "blender"), "version": "4.2.1"},
        "codex": str(proj.bin / "codex"), "env_file": ".env",
        "kit": {"path": str(proj.kit), "overall": "pass", "features": {"xatlas_unwrap": False}}}
    text = (proj.root / "production/preflight.json").read_text(encoding="utf-8")
    assert (KEY in r.stdout + r.stderr, KEY in text) == (False, False)


def test_feature_off_blocks_dispatch_of_the_step_that_needs_it(proj):
    (proj.root / ".env").write_text("MESHY_API_KEY=\n", encoding="utf-8")
    assert proj.run("preflight").stdout == (
        "preflight: tắt blender, codex_image, meshy; không có kit preflight.py → production/preflight.json\n")
    res = proj.result()
    assert (res["features"], res["blender"], res["codex"], res["kit"]["present"]) == (
        {"blender": False, "codex_image": False, "meshy": False}, None, None, False)
    assert "[house-a] blockout/todo → không giao: tắt blender (preflight)" in proj.run("next").stdout.splitlines()
    assert proj.run("brief", "house-a", ok=False).stderr == (
        "LỖI: house-a: bước blockout cần blender đang tắt (preflight) → sửa môi trường rồi chạy lại `preflight`\n")
    st = json.loads((proj.root / "production/assets/house-a/status.json").read_text(encoding="utf-8"))
    assert (st["state"], st["versions"]) == ("todo", {})


def test_the_kit_path_never_comes_from_the_command_line_so_the_codex_preflight_rule_runs_only_the_installed_kit(proj):
    r = proj.run("preflight", "--kit", str(proj.kit), ok=False)
    assert (r.returncode, r.stderr.splitlines()[-1]) == (2, f"producer.py: error: unrecognized arguments: --kit {proj.kit}")
    assert not (proj.kit.parent / "calls.txt").exists()


def test_next_and_brief_read_the_cached_result_and_never_rerun_the_kit(proj):
    assert "Chưa có production/preflight.json → chạy `preflight` một lần mỗi phiên" in proj.run("next").stdout
    proj.tool("blender", "Blender 4.2.1")
    proj.env["PRODUCER_KIT"] = str(proj.kit)
    proj.run("preflight")
    proj.run("next")
    proj.run("brief", "house-a")
    proj.run("next")
    assert (proj.kit.parent / "calls.txt").read_text(encoding="utf-8") == "run\n"
    assert "Chưa có production/preflight.json" not in proj.run("next").stdout
