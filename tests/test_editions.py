"""Two editions from one core (producer.md §16, D6.4, D24.5): build.py writes installable trees, refuses an edition that
breaks a rule Codex or the flat agent install depends on (row 87), runs the static trigger eval (row 92), and the Codex
Blender rule allows only installed Producer scripts (row 91)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from shared import PROFILE, write_profile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build", REPO / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
AGENTS = ["zps-3dp-check-ab", "zps-3dp-check-blockout", "zps-3dp-check-clay", "zps-3dp-check-texture",
          "zps-3dp-check-views", "zps-3dp-step-blockout", "zps-3dp-step-model", "zps-3dp-step-texture",
          "zps-3dp-step-views"]


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    assert [build.build(e, "9.9.9", out) for e in ("claude", "codex")] == [True, True]
    return out


def tree(dist, edition):
    return dist / f"zps-3dp-{edition}-v9.9.9"


def test_the_codex_edition_suffixes_every_skill_and_agent_and_carries_its_runtime(dist):
    m = json.loads((tree(dist, "codex") / "manifest.json").read_text(encoding="utf-8"))
    assert (m["skills"], m["agents"], m["install_root"], m["agents_root"]) == (
        ["zps-3dp-producer-codex", "zps-3dp-project-setup-codex"], [a + "-codex" for a in AGENTS], ".agents/skills", None)
    prod = tree(dist, "codex") / "skills/zps-3dp-producer-codex"
    assert json.loads((prod / "runtime.json").read_text(encoding="utf-8")) == {
        "runtime": "codex", "suffix": "-codex", "models": {"opus": None, "sonnet": None, "haiku": None}, "agent_file": True}
    assert (prod / "agents/zps-3dp-step-model-codex/zps-3dp-step-model-codex.md").is_file()
    assert (prod / "references/runtime.md").read_text(encoding="utf-8").startswith("# Runtime: Codex")
    assert not (prod / "templates/settings.snippet.json").exists()


def test_the_explicit_only_skill_stays_explicit_on_codex_through_openai_yaml_row_82(dist):
    sk = tree(dist, "codex") / "skills"
    assert (sk / "zps-3dp-project-setup-codex/agents/openai.yaml").read_text(encoding="utf-8") == (
        'interface:\n  display_name: "ZPS-3DP · Project Setup - Codex"\npolicy:\n  allow_implicit_invocation: false\n')
    assert (sk / "zps-3dp-producer-codex/agents/openai.yaml").read_text(encoding="utf-8") == (
        'interface:\n  display_name: "ZPS-3DP · Producer - Codex"\n')
    claude = (tree(dist, "claude") / "skills/zps-3dp-project-setup/SKILL.md").read_text(encoding="utf-8")
    assert build.frontmatter(claude)["disable-model-invocation"] == "true"


def test_the_codex_tree_names_codex_paths_and_the_claude_tree_names_no_codex_agent(dist):
    texts = lambda t: "".join(p.read_text(encoding="utf-8") for p in t.rglob("*") if p.suffix in build.TEXT)  # noqa: E731
    codex, claude = texts(tree(dist, "codex") / "skills"), texts(tree(dist, "claude") / "skills")
    assert (".claude/" in codex, "zps-3dp-step-model-codex" in claude, "zps-3dp-step-model`" in codex) == (False, False, False)
    skill = (tree(dist, "codex") / "skills/zps-3dp-producer-codex/SKILL.md").read_text(encoding="utf-8")
    assert "`P` = `.agents/skills/zps-3dp-producer-codex/scripts/.deps/venv/bin/python " in skill
    assert "\n# ZPS-3DP · Producer - Codex\n" in skill


def test_the_claude_edition_ships_flat_agent_files_beside_the_skills(dist):
    assert sorted(p.stem for p in (tree(dist, "claude") / "agents").glob("*.md")) == AGENTS
    assert not (tree(dist, "codex") / "agents").exists()


@pytest.fixture
def src_copy(tmp_path, monkeypatch):
    s = tmp_path / "src"
    shutil.copytree(REPO / "src", s, ignore=build.IGNORE)
    ev = tmp_path / "triggers.json"
    shutil.copy(build.EVALS, ev)
    monkeypatch.setattr(build, "SRC", s)
    monkeypatch.setattr(build, "EVALS", ev)
    return s


def failed(capsys, tmp_path, edition="codex"):
    assert build.build(edition, "9.9.9", tmp_path / "out") is False
    return [l.strip() for l in capsys.readouterr().out.split("FAILED:\n", 1)[1].strip().splitlines()]


def edit(p: Path, old: str, new: str):
    t = p.read_text(encoding="utf-8")
    assert old in t
    p.write_text(t.replace(old, new, 1), encoding="utf-8")


def test_a_codex_description_over_300_characters_fails_the_build_row_87(src_copy, tmp_path, capsys):
    f = src_copy / "zps-3dp-producer/agents/zps-3dp-check-clay.md"
    edit(f, "chỉ đọc, ghi một report.", "chỉ đọc, ghi một report." + "x" * 72)
    assert failed(capsys, tmp_path) == ["zps-3dp-check-clay-codex: description has 306 characters (max 300)"]


def test_an_agent_description_without_the_fixed_sentence_first_fails_the_build_d23_2(src_copy, tmp_path, capsys):
    edit(src_copy / "zps-3dp-producer/agents/zps-3dp-check-views.md", "description: Bước pipeline", "description: Pipeline")
    assert failed(capsys, tmp_path, "claude") == [
        "zps-3dp-check-views: description does not start with the fixed sentence (D23.2)"]


def test_a_bare_references_path_fails_because_a_flat_agent_install_cannot_resolve_it(src_copy, tmp_path, capsys):
    f = src_copy / "zps-3dp-producer/agents/zps-3dp-step-texture/zps-3dp-step-texture.md"
    edit(f, "`R/texture.md` mục 1", "`references/texture.md` mục 1")
    edit(f, "`PY T/id_map.py --final F", "`PY T/idmap.py --final F")
    assert failed(capsys, tmp_path, "claude") == [
        "zps-3dp-step-texture: bare `references/` path breaks in a flat agent install",
        "zps-3dp-step-texture: missing T/idmap.py"]


def test_the_static_trigger_eval_needs_every_agent_and_a_kit_overlap_negative_row_92(src_copy, tmp_path, capsys):
    ev = json.loads(build.EVALS.read_text(encoding="utf-8"))
    del ev["targets"]["zps-3dp-check-ab"]
    ev["targets"]["zps-3dp-step-model"]["cases"] = [
        c | {"why": "no brief"} if not c["should_trigger"] else c for c in ev["targets"]["zps-3dp-step-model"]["cases"]]
    ev["targets"]["zps-3dp-step-views"]["cases"][0]["query"] = "vẽ view cho kho-lua"
    build.EVALS.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
    assert failed(capsys, tmp_path, "claude") == [
        "evals: no cases for zps-3dp-check-ab",
        "evals: zps-3dp-step-views positive without a brief: vẽ view cho kho-lua",
        "evals: zps-3dp-step-model has no negative that overlaps a kit skill"]


def test_the_shipped_trigger_eval_covers_the_kit_overlap_the_spec_names(dist):
    cases = json.loads(build.EVALS.read_text(encoding="utf-8"))["targets"]["zps-3dp-step-model"]["cases"]
    assert {"query": "ZPS - 3D Artist dựng model cái rương", "should_trigger": False, "kind": "negative",
            "why": "Kit zps-3d-artist named"} in cases


def cli(py, script, cwd, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME")}
    return subprocess.run([py, str(script), *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def test_the_built_codex_producer_dispatches_suffixed_agents_by_file_and_ledgers_the_session_model(dist, tmp_path):
    p = tree(dist, "codex") / "skills/zps-3dp-producer-codex/scripts/producer.py"
    cli(sys.executable, p, tmp_path, "init", "--project", "Pilot", "--concepts", "concepts")
    write_profile(tmp_path, PROFILE)
    rub = tmp_path / "production/rubrics/default.md"
    rub.write_text(rub.read_text(encoding="utf-8").replace("status: draft", "status: approved", 1), encoding="utf-8")
    cli(sys.executable, p, tmp_path, "new", "house-a", "--title", "House A")
    out = json.loads(cli(sys.executable, p, tmp_path, "brief", "house-a"))
    assert (out["agent"], out["model"], out["agent_file"]) == (
        "zps-3dp-step-blockout-codex", None,
        os.path.relpath(p.parents[1] / "agents/zps-3dp-step-blockout-codex/zps-3dp-step-blockout-codex.md", tmp_path))
    brief = (tmp_path / out["brief"]).read_text(encoding="utf-8")
    assert f"TOOLS: {p.parents[1] / 'agents/zps-3dp-step-blockout-codex/tools'}" in brief
    last = (tmp_path / "production/ledger.md").read_text(encoding="utf-8").splitlines()[-1]
    assert last.endswith(" · codex · house-a · blockout v1 · giao worker (zps-3dp-step-blockout-codex, model của phiên)")


def test_install_copies_skills_and_flat_agents_and_an_upgrade_keeps_only_the_venvs(dist, tmp_path):
    t = tree(dist, "claude")
    cli(sys.executable, t / "install.py", tmp_path, "--project", str(tmp_path))
    sk = tmp_path / ".claude/skills/zps-3dp-producer"
    agent = (tmp_path / ".claude/agents/zps-3dp-step-model.md").read_text(encoding="utf-8")
    tools = sk / "agents/zps-3dp-step-model/tools"
    assert "`R` = `T/../references`" in agent and (tools / "../references/model.md").resolve().is_file()
    (sk / "scripts/.deps/venv").mkdir(parents=True)
    (sk / "scripts/.deps/venv/keep").write_text("venv", encoding="utf-8")
    (sk / "scripts/old_tool.py").write_text("removed in a later version", encoding="utf-8")
    cli(sys.executable, t / "install.py", tmp_path, "--project", str(tmp_path))
    assert ((sk / "scripts/.deps/venv/keep").is_file(), (sk / "scripts/old_tool.py").exists(),
            (tmp_path / ".claude/skills/zps-3dp-project-setup/SKILL.md").is_file()) == (True, False, True)


FAKE_CODEX = r'''import ast, json, re, sys
a = sys.argv[1:]
rules = open(a[a.index("--rules") + 1], encoding="utf-8").read()
cmd = a[a.index("--") + 1:]
for m in re.finditer(r"pattern = (\[.*?\]),\n    decision", rules, re.S):
    pat = ast.literal_eval(m.group(1))
    if len(cmd) >= len(pat) and all(c == p or (isinstance(p, list) and c in p) for c, p in zip(cmd, pat)):
        print(json.dumps({"decision": "allow"})); sys.exit(0)
print("{}")
'''


@pytest.fixture
def codex_project(dist, tmp_path):
    cli(sys.executable, tree(dist, "codex") / "install.py", tmp_path, "--project", str(tmp_path))
    venv = tmp_path / ".agents/skills/zps-3dp-producer-codex/scripts/.deps/venv/bin/python"
    venv.parent.mkdir(parents=True)
    venv.write_text("", encoding="utf-8")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "Blender").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_ / "fake_codex.py").write_text(FAKE_CODEX, encoding="utf-8")
    (bin_ / "codex").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{bin_ / "fake_codex.py"}" "$@"\n', encoding="utf-8")
    for f in bin_.iterdir():
        f.chmod(0o755)
    return tmp_path


def rules(project, dist, *args, path=True):
    env = os.environ | {"PATH": f"{project / 'bin'}{os.pathsep}{os.environ['PATH']}" if path else "/usr/bin:/bin"}
    return subprocess.run([sys.executable, str(tree(dist, "codex") / "installer/codex_rules.py"), "--skills-root",
                           str(project / ".agents/skills"), "--blender", str(project / "bin/Blender"), "--rules-dir",
                           str(project / "rules"), *args], cwd=project, env=env, capture_output=True, text=True)


def test_the_codex_rule_lets_blender_run_installed_scripts_and_nothing_else_row_91(codex_project, dist):
    r = rules(codex_project, dist)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    assert not (codex_project / "rules").exists(), "preview mode must not write the rules file"
    preview = Path(r.stdout.split("Preview only: ", 1)[1].splitlines()[0]).read_text(encoding="utf-8")
    assert [n for n in ("meshy_call.py", "gen_image_codex.py", "gen_api.py") if n in preview] == []
    assert preview.count("prefix_rule(") == 4 and f'"{codex_project / "bin/Blender"}", "-b", "--python", [' in preview


def test_the_codex_rule_ends_each_command_where_the_program_stops_reading_options_so_no_tail_runs_other_code(
        codex_project, dist):
    r = rules(codex_project, dist)
    preview = r.stdout.split("Preview only: ", 1)[1].splitlines()[0]
    sk = codex_project / ".agents/skills"
    blender, py = str(codex_project / "bin/Blender"), str(sk / "zps-3dp-producer-codex/scripts/.deps/venv/bin/python")
    script = str(sk / "zps-3dp-producer-codex/agents/zps-3dp-step-model-codex/tools/unwrap.py")
    spawner, prod = str(sk / "zps-3dp-producer-codex/scripts/assemble.py"), str(sk / "zps-3dp-producer-codex/scripts/producer.py")

    def decision(*cmd):
        out = subprocess.run([str(codex_project / "bin/codex"), "execpolicy", "check", "--rules", preview, "--", *cmd],
                             capture_output=True, text=True).stdout
        return json.loads(out or "{}").get("decision")
    assert [decision(*c) for c in (
        [blender, "-b", "--python", script, "--", "--final", "F"],
        [blender, "-b", "--python", script, "--python-expr", "print(1)"],
        [blender, "-b", "--python", script, "--python", "/tmp/evil.py", "--"],
        [blender, "-b", "--python-exit-code", "1", "--python", script, "--python", "/tmp/evil.py"],
        [py, spawner, "--blender", blender, "--", "house-a", "1", "abc123"],
        [py, spawner, "house-a", "--version", "1", "--profile-hash", "h", "--blender", "/tmp/evil.sh"],
        [py, spawner, "--blender", "/tmp/evil.sh", "--", "house-a", "1", "abc123"],
        [py, prod, "preflight"])] == ["allow", None, None, None, "allow", None, None, "allow"]


def test_the_codex_rule_is_written_only_on_write_and_never_over_a_foreign_file(codex_project, dist):
    assert rules(codex_project, dist, "--write").returncode == 0
    f = codex_project / "rules/zps-3dp-producer.rules"
    assert f.read_text(encoding="utf-8").startswith("# Generated by ZPS-3DP Producer installer/codex_rules.py.")
    f.write_text("# my own rules\n", encoding="utf-8")
    r = rules(codex_project, dist, "--write")
    assert (r.returncode, f.read_text(encoding="utf-8")) == (1, "# my own rules\n")


def test_without_the_codex_cli_the_rule_is_not_tested_and_the_output_says_so(codex_project, dist):
    r = rules(codex_project, dist, path=False)
    assert (r.returncode, "codex CLI not found: rule not tested" in r.stdout) == (0, True)
