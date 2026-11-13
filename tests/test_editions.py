"""Two editions from one core (producer.md §16, D6.4, D24.5): build.py writes installable trees, refuses an edition that
breaks a rule Codex or the flat agent install depends on (row 87), runs the static trigger eval (row 92), and the Codex
Blender rule allows only installed Producer scripts (row 91)."""
import importlib.util
import json
import os
import re
import shlex
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
        "runtime": "codex", "suffix": "-codex", "models": {"opus": None, "sonnet": None, "haiku": None}, "agent_file": True,
        "image_gen": "direct"}
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


@pytest.mark.parametrize("edition, name", [("claude", "zps-3dp-project-setup"), ("codex", "zps-3dp-project-setup-codex")])
def test_setup_writes_the_profile_in_the_producer_root_so_an_ab_session_reads_the_profile_it_wrote(dist, edition, name):
    text = (tree(dist, edition) / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[1]
    assert re.findall(r"production/", text) == []
    assert "`D` = thư mục làm việc của Producer: `$PRODUCER_ROOT` của phiên, mặc định `production`" in body
    assert ["D/PROJECT-PROFILE.yaml" in line for line in body.splitlines() if "PROJECT-PROFILE.yaml" in line] == [True] * 3


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


def test_the_claude_settings_snippet_lets_agents_write_reports_under_every_producer_root_d27_5(dist):
    """A blocked write sends the report through the Producer context; A/B runs write under production-<runtime>/."""
    snippet = json.loads((tree(dist, "claude") / "skills/zps-3dp-producer/templates/settings.snippet.json")
                         .read_text(encoding="utf-8"))
    assert [r for r in snippet["permissions"]["allow"] if r.startswith("Edit(")] == [
        "Edit(/production/**)", "Edit(/production-*/**)"]


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
    edit(f, "`RUN id_map.py --final F", "`RUN T/idmap.py --final F")
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
    assert {"query": "ZPS - 3D Artist dựng model cái thùng", "should_trigger": False, "kind": "negative",
            "why": "Kit zps-3d-artist named"} in cases


def cli(py, script, cwd, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME")}
    return subprocess.run([py, str(script), *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def test_the_producer_description_excludes_one_off_art_and_direct_kit_calls_and_the_eval_has_negatives_for_both_row_w11():
    """Without the exclusion the Producer wins every 3D request in a project that has _approved concepts, also the ones
    a kit skill should take. The live trigger eval is not run here."""
    text = (build.SRC / "zps-3dp-producer/SKILL.md").read_text(encoding="utf-8")
    desc = build.frontmatter(text)["description"]
    assert len(desc) <= build.DESC_MAX and "\n" not in desc
    assert desc.endswith("Không dùng cho việc art lẻ ngoài pipeline hay khi gọi thẳng skill của kit.")
    cases = json.loads(build.EVALS.read_text(encoding="utf-8"))["targets"]["zps-3dp-producer"]["cases"]
    one_off = [c for c in cases if not c["should_trigger"] and "One-off art" in c["why"]]
    direct = [c for c in cases if not c["should_trigger"] and (c["query"].startswith("/zps-") or "named" in c["why"])]
    assert len(one_off) >= 2 and len(direct) >= 1 and len([c for c in cases if not c["should_trigger"]]) >= 6


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
    assert " · codex · house-a · blockout v1 · giao worker (zps-3dp-step-blockout-codex, model của phiên) · hạn chót " in last


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


@pytest.mark.parametrize("edition", ["claude", "codex"])
def test_both_editions_install_the_bundled_font_byte_for_byte_where_views_sheet_looks_d27_12(dist, tmp_path, edition):
    import hashlib
    cli(sys.executable, tree(dist, edition) / "install.py", tmp_path, "--project", str(tmp_path))
    root = tmp_path / (".claude/skills/zps-3dp-producer" if edition == "claude" else ".agents/skills/zps-3dp-producer-codex")
    views = "zps-3dp-step-views" + ("" if edition == "claude" else "-codex")
    font = root / f"agents/{views}/tools/../../../fonts/NotoSans-Regular.ttf"
    src = REPO / "src/zps-3dp-producer/fonts"
    assert (hashlib.sha256(font.read_bytes()).digest(), (font.parent / "OFL.txt").read_text(encoding="utf-8")) == (
        hashlib.sha256((src / "NotoSans-Regular.ttf").read_bytes()).digest(), (src / "OFL.txt").read_text(encoding="utf-8"))


def test_install_refuses_a_symlinked_skill_folder_and_deletes_nothing_in_its_target(dist, tmp_path):
    t, mine = tree(dist, "claude"), tmp_path / "my-skill"
    (mine / "scripts").mkdir(parents=True)
    (mine / "scripts/mine.py").write_text("my own file", encoding="utf-8")
    (tmp_path / ".claude/skills").mkdir(parents=True)
    (tmp_path / ".claude/skills/zps-3dp-producer").symlink_to(mine, target_is_directory=True)
    r = subprocess.run([sys.executable, str(t / "install.py"), "--project", str(tmp_path)], capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (2, f"{tmp_path.resolve() / '.claude/skills/zps-3dp-producer'} là symlink tới "
                                           f"{mine.resolve()}: không cài, để khỏi xoá file ở đó. Gỡ symlink rồi chạy lại.\n")
    assert ((mine / "scripts/mine.py").read_text(encoding="utf-8"), sorted(p.name for p in mine.rglob("*")),
            (tmp_path / ".claude/skills/zps-3dp-project-setup").exists()) == ("my own file", ["mine.py", "scripts"], False)


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
    return codex_install(dist, tmp_path)


@pytest.fixture
def spaced_project(dist, tmp_path):
    """The pilot machine keeps projects under a folder with spaces; Blender stays where the app installs it."""
    b = plain_blender(tmp_path.resolve() / "my project")
    b.parent.mkdir()
    b.write_text("#!/bin/sh\necho 'Blender 5.2.3'\n", encoding="utf-8")
    b.chmod(0o755)
    return codex_install(dist, (tmp_path / "my project").resolve())


def plain_blender(project: Path) -> Path:
    return project.parent / "bin/Blender"


def codex_install(dist, tmp_path):
    tmp_path.mkdir(exist_ok=True)
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


def codex_home(project: Path) -> Path:
    """Beside the project, so a project path with a space does not give CODEX_HOME one."""
    return project.with_name(project.name.replace(" ", "_") + "-codex-home")


def rules(project, dist, *args, path=True, home=None, blender=None, rules_dir=None):
    env = os.environ | {"PATH": f"{project / 'bin'}{os.pathsep}{os.environ['PATH']}" if path else "/usr/bin:/bin",
                        "CODEX_HOME": str(home or codex_home(project))}
    return subprocess.run([sys.executable, str(tree(dist, "codex") / "installer/codex_rules.py"), "--skills-root",
                           str(project / ".agents/skills"), "--blender", str(blender or project / "bin/Blender"),
                           "--rules-dir", str(rules_dir or project / "rules"), *args], cwd=project, env=env, capture_output=True,
                          text=True)


def test_the_codex_rule_lets_blender_run_installed_scripts_and_nothing_else_row_91(codex_project, dist):
    r = rules(codex_project, dist)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    assert not (codex_project / "rules").exists(), "preview mode must not write the rules file"
    preview = Path(r.stdout.split("Preview only: ", 1)[1].splitlines()[0]).read_text(encoding="utf-8")
    assert [n for n in ("meshy_call.py", "gen_image_codex.py", "gen_api.py") if n in preview] == []
    assert preview.count("prefix_rule(") == 5 and f'"{codex_project / "bin/Blender"}", "-b", "--python", [' in preview


def test_two_codex_rule_previews_at_once_write_two_files_so_one_run_never_tests_the_other_runs_rules(codex_project, dist):
    paths = [Path(rules(codex_project, dist).stdout.split("Preview only: ", 1)[1].splitlines()[0]) for _ in range(2)]
    assert paths[0] != paths[1] and all(p.is_file() for p in paths)


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



def test_the_codex_rule_never_lets_blender_run_a_script_that_loads_agent_written_code(codex_project, dist):
    """graph.py loads `<work>/parts_lib.py`, which the agent writes; outside the sandbox that code would run unchecked.
    These commands still run, but only after the user approves each one. build_parts.py is allowed again (D32): Blender
    builds only the mesh JSON that pure Python made from custom_parts.py, never the agent's code itself.
    custom_mesh.py runs custom_parts.py, so it is agent code and never matches."""
    r = rules(codex_project, dist)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    preview = r.stdout.split("Preview only: ", 1)[1].splitlines()[0]
    agents = codex_project / ".agents/skills/zps-3dp-producer-codex/agents"
    blender = str(codex_project / "bin/Blender")

    def decision(script):
        out = subprocess.run([str(codex_project / "bin/codex"), "execpolicy", "check", "--rules", preview, "--", blender,
                              "-b", "--python", str(agents / script), "--", "--work", "w"], capture_output=True, text=True)
        return json.loads(out.stdout or "{}").get("decision")
    assert {s: decision(s) for s in (
        "zps-3dp-step-model-codex/tools/self_build/assembly.py", "zps-3dp-step-blockout-codex/tools/self_build/assembly.py",
        "zps-3dp-step-blockout-codex/tools/self_build/param_fit.py",
        "zps-3dp-step-model-codex/tools/self_build/gates.py", "zps-3dp-step-blockout-codex/tools/build_parts.py",
        "zps-3dp-step-blockout-codex/tools/custom_mesh.py")} == {
        "zps-3dp-step-model-codex/tools/self_build/assembly.py": None,
        "zps-3dp-step-blockout-codex/tools/self_build/assembly.py": None,
        "zps-3dp-step-blockout-codex/tools/self_build/param_fit.py": None,
        "zps-3dp-step-model-codex/tools/self_build/gates.py": "allow",
        "zps-3dp-step-blockout-codex/tools/build_parts.py": "allow",
        "zps-3dp-step-blockout-codex/tools/custom_mesh.py": None}


def test_the_codex_rule_lets_run_tool_start_only_the_blender_of_the_rule_so_the_run_line_runs_outside_the_sandbox(
        codex_project, dist):
    r = rules(codex_project, dist)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    preview = r.stdout.split("Preview only: ", 1)[1].splitlines()[0]
    blender = str(codex_project / "bin/Blender")
    run_tool = str(codex_project / ".agents/skills/zps-3dp-producer-codex/scripts/run_tool.py")

    def decision(*cmd):
        out = subprocess.run([str(codex_project / "bin/codex"), "execpolicy", "check", "--rules", preview, "--", *cmd],
                             capture_output=True, text=True).stdout
        return json.loads(out or "{}").get("decision")
    tail = ["--agent", "zps-3dp-step-model-codex", "--version-dir", "v", "bl", "join_mesh.py", "--final", "F"]
    assert [decision(*c) for c in (
        [run_tool, "--blender", blender, *tail],
        [run_tool, "--blender", "/tmp/evil.sh", *tail],
        [run_tool, "--agent", "zps-3dp-step-model-codex", "--version-dir", "v", "x.py"])] == ["allow", None, None]


def test_the_codex_rule_never_allows_the_codex_exec_image_call_because_each_one_spends_the_users_codex_usage(
        codex_project, dist):
    """D30.18: the gen command is `codex exec ... -s workspace-write --skip-git-repo-check` (codex-cli 0.164.0 has no
    --full-auto). It needs the network and costs Codex usage, so the user approves each run; no rule may match it."""
    r = rules(codex_project, dist)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    preview = r.stdout.split("Preview only: ", 1)[1].splitlines()[0]
    prod = codex_project / ".agents/skills/zps-3dp-producer-codex"

    def decision(*cmd):
        out = subprocess.run([str(codex_project / "bin/codex"), "execpolicy", "check", "--rules", preview, "--", *cmd],
                             capture_output=True, text=True).stdout
        return json.loads(out or "{}").get("decision")
    assert [decision(*c) for c in (
        ["codex", "exec", "-m", "m", "-C", "w", "-s", "workspace-write", "--skip-git-repo-check", "-"],
        [str(prod / "scripts/.deps/venv/bin/python"), str(prod / "scripts/gen_image_codex.py"), "--model", "m"])] == [
        None, None]

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


def rules_module():
    spec = importlib.util.spec_from_file_location("codex_rules", REPO / "editions/codex/installer/codex_rules.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def patterns(text: str) -> list:
    import ast
    return [ast.literal_eval(m.group(1)) for m in re.finditer(r"pattern = (\[.*?\]),\n    decision", text, re.S)]


def preview_of(r) -> str:
    return Path(r.stdout.split("Preview only: ", 1)[1].splitlines()[0]).read_text(encoding="utf-8")


def link_of(project: Path) -> tuple[Path, Path]:
    import hashlib
    prod = project / ".agents/skills/zps-3dp-producer-codex"
    return prod, codex_home(project) / "zps-3dp" / hashlib.sha1(str(prod).encode()).hexdigest()[:12]


def test_the_skill_and_the_rules_script_put_the_link_of_a_skill_folder_at_the_same_path(tmp_path, monkeypatch):
    """codex_rules.py runs outside the skill and cannot import it, so the two copies of the formula must agree."""
    from core.state import codex_link
    monkeypatch.setenv("CODEX_HOME", str(codex_home(tmp_path / "my project")))
    prod, link = link_of(tmp_path / "my project")
    assert rules_module().link_of(prod) == codex_link(prod) == link


def test_with_a_space_in_the_project_path_every_program_word_of_a_rule_is_the_link_and_preview_makes_no_link(
        spaced_project, dist):
    """Codex never matches a quoted first word (measured 2026-11-13), so a program path with a space never leaves the
    sandbox. Later words may be quoted: the direct Blender rules keep the real script paths."""
    r = rules(spaced_project, dist, blender=plain_blender(spaced_project))
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    prod, link = link_of(spaced_project)
    pats = patterns(preview_of(r))
    assert [p[:2] for p in pats[2:]] == [[f"{link}/scripts/run_tool.py", "--blender"],
                                         [f"{link}/scripts/.deps/venv/bin/python", [f"{link}/scripts/assemble.py"]],
                                         [f"{link}/scripts/.deps/venv/bin/python", f"{link}/scripts/producer.py"]]
    assert all(p[-2][0].startswith(f"{prod}/") for p in pats[:2]) and shlex.quote(str(link)) == str(link)
    assert f"Link: {link} -> {prod} (made by --write)" in r.stdout and not link.is_symlink()


def test_write_makes_the_link_repairs_a_stale_one_and_never_replaces_a_real_folder(spaced_project, dist):
    prod, link = link_of(spaced_project)
    assert rules(spaced_project, dist, "--write").returncode == 0
    assert (link.is_symlink(), link.resolve()) == (True, prod)
    link.unlink()
    link.symlink_to(spaced_project / "bin", target_is_directory=True)
    assert rules(spaced_project, dist, "--write").returncode == 0 and link.resolve() == prod
    link.unlink()
    link.mkdir()
    (link / "mine.txt").write_text("mine", encoding="utf-8")
    r = rules(spaced_project, dist, "--write")
    assert (r.returncode, link.is_symlink(), (link / "mine.txt").read_text(encoding="utf-8")) == (1, False, "mine")
    assert f"{link} exists and is not a link" in r.stdout


def test_a_codex_home_with_a_space_cannot_hold_the_link_so_the_rules_script_stops_with_exit_2(spaced_project, dist,
                                                                                               tmp_path):
    r = rules(spaced_project, dist, "--write", home=tmp_path / "codex home")
    assert (r.returncode, (spaced_project / "rules").exists(), (tmp_path / "codex home").exists()) == (2, False, False)
    assert "CODEX_HOME" in r.stdout


def test_a_blender_path_with_a_space_gets_no_direct_blender_rule_but_still_the_run_tool_rule(codex_project, dist):
    """Blender is the program word of the direct rules, which then can never match; for run_tool.py it is an argument."""
    b = codex_project / "Blender App/Blender"
    b.parent.mkdir()
    b.write_text("#!/bin/sh\n", encoding="utf-8")
    b.chmod(0o755)
    r = rules(codex_project, dist, blender=b)
    assert r.returncode == 0 and "rule test passed" in r.stdout, r.stdout
    prod = codex_project / ".agents/skills/zps-3dp-producer-codex"
    assert [p[0] for p in patterns(preview_of(r))] == [str(prod / "scripts/run_tool.py"),
                                                       *[str(prod / "scripts/.deps/venv/bin/python")] * 2]
    assert f"Note: {b} needs quotes, so no direct Blender rule is written" in r.stdout


def test_the_run_line_of_a_brief_in_a_project_with_a_space_starts_with_the_program_word_of_the_rule(spaced_project,
                                                                                                     dist):
    blender = str(plain_blender(spaced_project))
    assert rules(spaced_project, dist, "--write", blender=blender).returncode == 0
    sk, home = spaced_project / ".agents/skills/zps-3dp-producer-codex", codex_home(spaced_project)
    out = subprocess.run([sys.executable, "-c", (
        "import json, sys; sys.path.insert(0, sys.argv[1]); from core import briefs;"
        "print(json.dumps(briefs.tools_line({'id': 'a'}, {'id': 'blockout', 'agent': 'step-blockout', 'uses': ['blender']},"
        " {'blender': {'path': sys.argv[2]}}, None, n=1)))"), str(sk / "scripts"), blender],
        env=os.environ | {"PRODUCER_ROOT": str(spaced_project / "production"), "CODEX_HOME": str(home)},
        cwd=spaced_project, capture_output=True, text=True, check=True)
    lines = json.loads(out.stdout)
    i = next(i for i, l in enumerate(lines) if l.startswith("RUN: "))
    words = shlex.split(lines[i].removeprefix("RUN: "))
    rule = patterns((spaced_project / "rules/zps-3dp-producer.rules").read_text(encoding="utf-8"))[2]
    assert rule[:3] == [f"{link_of(spaced_project)[1]}/scripts/run_tool.py", "--blender", blender]
    assert (words[0], lines[i].split(" ")[1], lines[i + 1].startswith("RUN_MODE: ")) == (rule[0], rule[0], True)
    check = subprocess.run([str(spaced_project / "bin/codex"), "execpolicy", "check", "--rules",
                            str(spaced_project / "rules/zps-3dp-producer.rules"), "--", *words, "bl", "x.py"],
                           capture_output=True, text=True)
    assert json.loads(check.stdout)["decision"] == "allow"


def test_the_built_codex_preflight_turns_blender_on_only_once_the_rules_script_wrote_its_file_and_link(spaced_project,
                                                                                                       dist):
    """The rules file name must survive the build, which suffixes every skill name in the skill's text."""
    blender = str(plain_blender(spaced_project))
    py = spaced_project / ".agents/skills/zps-3dp-producer-codex/scripts/producer.py"
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME", "PRODUCER_KIT")} | {
        "BLENDER": blender, "CODEX_HOME": str(codex_home(spaced_project))}

    def preflight():
        r = subprocess.run([sys.executable, str(py), "preflight"], cwd=spaced_project, env=env, capture_output=True,
                           text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout, json.loads((spaced_project / "production/preflight.json").read_text(encoding="utf-8"))
    out, pf = preflight()
    assert (pf["features"]["blender"], "codex_rules.py --write" in out) == (False, True)
    assert rules(spaced_project, dist, "--write", blender=blender,
                 rules_dir=codex_home(spaced_project) / "rules").returncode == 0
    out, pf = preflight()
    assert (pf["features"]["blender"], pf["codex_rules"]["file"], "codex_rules.py" in out) == (
        True, str(codex_home(spaced_project) / "rules/zps-3dp-producer.rules"), False)


SHELL_WRITE = re.compile(r"heredoc|cat\s*>|\btee\b|<<\s*['\"]?[A-Z]+|python3?\s+-c", re.I)
DISPATCH_RULE = ("   Lời giao việc chỉ gồm file role và brief: file role là agent `agent` (Codex: `agent_file`), brief là prompt "
                 "trên. Không thêm gì vào prompt. Không hướng dẫn cách ghi file: không heredoc, không `cat >`, không `tee`, "
                 "không python. Agent ghi report bằng tool ghi file, theo brief.")


@pytest.mark.parametrize("edition, name", [("claude", "zps-3dp-producer"), ("codex", "zps-3dp-producer-codex")])
def test_the_dispatch_is_the_role_file_and_the_brief_and_nothing_tells_an_agent_to_write_through_the_shell_d30_8(
        dist, edition, name):
    """Pilot run: the Producer's dispatch prompt told the worker to write worker-out.md with a heredoc; the brief was right."""
    prod = tree(dist, edition) / "skills" / name
    skill = (prod / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert (DISPATCH_RULE in skill, any(l.startswith("**Ngoại lệ (waive):**") for l in skill)) == (True, True)
    assert any("Bạn không bao giờ sửa report của worker hay reviewer." in l for l in skill)
    hits = [f"{p.relative_to(prod)}: {l.strip()[:80]}" for p in sorted(prod.rglob("*.md"))
            for l in p.read_text(encoding="utf-8").splitlines() if SHELL_WRITE.search(l) and l != DISPATCH_RULE]
    assert hits == []


MINE = {"permissions": {"allow": ["Bash(git status:*)"], "deny": ["Bash(rm -rf:*)"]}, "model": "opus",
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}


def install(dist, project, *args, edition="claude"):
    blender = project / "bin/Blender"
    blender.parent.mkdir(exist_ok=True)
    blender.write_text("#!/bin/sh\necho 'Blender 4.2.1 LTS'\n", encoding="utf-8")
    blender.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME")} | {"BLENDER": str(blender)}
    return subprocess.run([sys.executable, str(tree(dist, edition) / "install.py"), "--project", str(project), *args],
                          env=env, capture_output=True, text=True)


def test_a_stop_hook_of_the_user_stays_and_the_installer_adds_the_producer_stop_hook_beside_it_d39_1(dist, tmp_path):
    """Claude Code runs every Stop hook and one refusal is enough, so the two hooks live side by side."""
    s = tmp_path / ".claude/settings.json"
    s.parent.mkdir()
    mine = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo my-stop"}]}]}}
    s.write_text(json.dumps(mine), encoding="utf-8")
    assert install(dist, tmp_path).returncode == 0
    stop = json.loads(s.read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert [h["command"].rsplit(" ", 1)[-1] for g in stop for h in g["hooks"]] == ["my-stop", "on-main-stop"]
    before = s.read_bytes()
    assert (install(dist, tmp_path).returncode, s.read_bytes()) == (0, before)


def test_install_appends_the_producer_rules_and_hook_to_project_settings_and_keeps_every_existing_key_d30_7(
        dist, tmp_path):
    """Without the rules every background subagent stops on a permission prompt; without the hook a new session does
    not know the pipeline state. A user's own rules, deny list and hooks must survive the merge."""
    s = tmp_path / ".claude/settings.json"
    s.parent.mkdir()
    s.write_text(json.dumps(MINE), encoding="utf-8")
    r = install(dist, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    sk, bl = tmp_path.resolve() / ".claude/skills/zps-3dp-producer", tmp_path / "bin/Blender"
    p = ".claude/skills/zps-3dp-producer/scripts/.deps/venv/bin/python .claude/skills/zps-3dp-producer/scripts/producer.py"
    assert json.loads(s.read_text(encoding="utf-8")) == {
        "permissions": {"allow": ["Bash(git status:*)", f"Bash({p}:*)",
                                  f"Bash({sk}/scripts/run_tool.py:*)",
                                  f"Bash({sk}/scripts/.deps/venv/bin/python {sk}/scripts/assemble.py:*)", f"Bash({bl}:*)",
                                  f"Bash({sk}/agents/zps-3dp-step-texture/tools/.deps/venv/bin/python "
                                  f"{sk}/scripts/meshy_call.py:*)",
                                  *(f"Bash({sk}/agents/zps-3dp-step-{s}/tools/.deps/venv/bin/python "
                                    f"{sk}/scripts/gen_image_codex.py:*)" for s in ("views", "texture")),
                                  "Bash(codex exec:*)", "Edit(/production/**)", "Edit(/production-*/**)"],
                        "deny": ["Bash(rm -rf:*)"]},
        "model": "opus", "env": {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]},
                                   {"hooks": [{"type": "command", "command": f"{p} next --session"}]}],
                  "SubagentStop": [{"hooks": [{"type": "command", "command": f"{p} on-stop"}]}],
                  "Stop": [{"hooks": [{"type": "command", "command": f"{p} on-main-stop"}]}]}}
    diff = r.stdout.split(f"+++ {s.resolve()}\n", 1)[1]
    assert f'+      "Bash({bl}:*)",\n' in diff and f'+            "command": "{p} next --session"\n' in diff
    before = s.read_bytes()
    again = install(dist, tmp_path)
    assert (again.returncode, s.read_bytes()) == (0, before)
    assert f"{s.resolve()}: đã đủ rule và hook, không đổi\n" in again.stdout and "+++" not in again.stdout


def test_the_meshy_and_blender_rules_match_the_command_lines_a_texture_brief_gives_the_worker(dist, tmp_path):
    """A rule is a command prefix: it helps only if it is exactly what the worker runs, `PY "<MESHY>"` with PY under
    the TOOLS line, and the BLENDER line, all absolute paths of the installed skill."""
    assert install(dist, tmp_path).returncode == 0
    sk = tmp_path.resolve() / ".claude/skills/zps-3dp-producer"
    sys.path.insert(0, str(sk / "scripts"))
    try:
        env = os.environ | {"PRODUCER_ROOT": str(tmp_path / "production")}
        out = subprocess.run([sys.executable, "-c", (
            "import json, sys; sys.path.insert(0, sys.argv[1]); from core import briefs, texture;"
            "print(json.dumps([briefs.tools_line({'id': 'a'}, {'agent': 'step-texture', 'uses': []}, None, None),"
            " str(texture.MESHY_CALL)]))"), str(sk / "scripts")], env=env, capture_output=True, text=True, check=True)
    finally:
        sys.path.remove(str(sk / "scripts"))
    tools, meshy = json.loads(out.stdout)
    allow = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    assert f"Bash({tools[0].removeprefix('TOOLS: ')}/.deps/venv/bin/python {meshy}:*)" in allow


def test_the_image_rules_match_the_gen_command_of_the_views_and_texture_workers_so_a_background_worker_never_waits(
        dist, tmp_path):
    """Without a rule a background worker sat on a permission prompt nobody saw. The worker runs `PY "<GEN_IMAGE>"`
    with PY under its TOOLS line. Each call still spends the user's Codex quota; the Codex edition keeps no rule."""
    assert install(dist, tmp_path).returncode == 0
    sk = tmp_path.resolve() / ".claude/skills/zps-3dp-producer"
    out = subprocess.run([sys.executable, "-c", (
        "import json, sys; sys.path.insert(0, sys.argv[1]); from core import briefs;"
        "print(json.dumps([briefs.tools_line({'id': 'a'}, {'agent': a, 'uses': []}, None, None)[0]"
        " for a in ('step-views', 'step-texture')]))"), str(sk / "scripts")],
        env=os.environ | {"PRODUCER_ROOT": str(tmp_path / "production")}, capture_output=True, text=True, check=True)
    allow = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    for tools in json.loads(out.stdout):
        assert f"Bash({tools.removeprefix('TOOLS: ')}/.deps/venv/bin/python {sk}/scripts/gen_image_codex.py:*)" in allow


def test_the_run_tool_rule_is_the_start_of_the_run_line_a_brief_gives_the_worker(dist, tmp_path):
    """A rule is a command prefix: the RUN line must begin with the run_tool.py path of the rule."""
    assert install(dist, tmp_path).returncode == 0
    sk = tmp_path.resolve() / ".claude/skills/zps-3dp-producer"
    out = subprocess.run([sys.executable, "-c", (
        "import json, sys; sys.path.insert(0, sys.argv[1]); from core import briefs;"
        "print(json.dumps(briefs.tools_line({'id': 'a'}, {'id': 'blockout', 'agent': 'step-blockout', 'uses': ['blender']},"
        " None, None, n=1)))"), str(sk / "scripts")], env=os.environ | {"PRODUCER_ROOT": str(tmp_path / "production")},
        capture_output=True, text=True, check=True)
    run = [l for l in json.loads(out.stdout) if l.startswith("RUN: ")][0]
    allow = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    tool = f"{sk}/scripts/run_tool.py"
    assert (f"Bash({tool}:*)" in allow, shlex.split(run.removeprefix("RUN: "))[0], os.access(tool, os.X_OK)) == (True, tool, True)


def test_dry_run_prints_the_diff_and_an_unparsable_settings_file_is_never_touched(dist, tmp_path):
    r = install(dist, tmp_path, "--dry-run")
    assert (r.returncode, (tmp_path / ".claude/settings.json").exists()) == (0, False)
    assert "(thử) không ghi" in r.stdout and '+      "Bash(codex exec:*)",\n' in r.stdout
    s = tmp_path / ".claude/settings.json"
    s.parent.mkdir(exist_ok=True)
    s.write_text("{ my settings, half typed", encoding="utf-8")
    r = install(dist, tmp_path)
    assert (r.returncode, s.read_text(encoding="utf-8")) == (2, "{ my settings, half typed")


def test_the_codex_edition_merges_no_claude_settings(dist, tmp_path):
    assert install(dist, tmp_path, edition="codex").returncode == 0
    assert [p.name for p in tmp_path.rglob("settings*.json")] == []


CODEX_P = (".agents/skills/zps-3dp-producer-codex/scripts/.deps/venv/bin/python "
           ".agents/skills/zps-3dp-producer-codex/scripts/producer.py")


def test_the_codex_hook_commands_run_the_installed_producer_with_its_venv_d46(dist, tmp_path):
    """Codex runs a hook command from the project root; a path that does not exist after install runs nothing."""
    hooks = json.loads((tree(dist, "codex") / "installer/codex_hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert {ev: [h["command"] for g in gs for h in g["hooks"]] for ev, gs in hooks.items()} == {
        "SessionStart": [f"{CODEX_P} next --session"], "SubagentStop": [f"{CODEX_P} on-stop"],
        "Stop": [f"{CODEX_P} on-main-stop"]}
    assert hooks["SessionStart"][0]["matcher"] == "startup|resume|clear|compact|fork", "/new is `clear`: a new rollout"
    assert install(dist, tmp_path, edition="codex").returncode == 0
    assert (tmp_path / CODEX_P.split(" ")[1]).is_file()
    assert not (tree(dist, "claude") / "installer/codex_hooks.json").exists()


def test_install_merges_the_codex_hooks_into_project_codex_hooks_json_and_keeps_the_users_hooks_d46(dist, tmp_path):
    h = tmp_path / ".codex/hooks.json"
    h.parent.mkdir()
    mine = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo my-stop"}]}],
                      "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo pre"}]}]}}
    h.write_text(json.dumps(mine), encoding="utf-8")
    r = install(dist, tmp_path, edition="codex")
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(h.read_text(encoding="utf-8"))["hooks"]
    assert got["PreToolUse"] == mine["hooks"]["PreToolUse"]
    assert [h_["command"].rsplit(" ", 1)[-1] for g in got["Stop"] for h_ in g["hooks"]] == ["my-stop", "on-main-stop"]
    assert [h_["command"] for g in got["SubagentStop"] for h_ in g["hooks"]] == [f"{CODEX_P} on-stop"]
    assert "tin hook một lần" in r.stdout and list(json.loads(h.read_text(encoding="utf-8"))) == ["hooks"]
    before = h.read_bytes()
    again = install(dist, tmp_path, edition="codex")
    assert (again.returncode, h.read_bytes()) == (0, before)
    assert f"{h.resolve()}: đã đủ hook, không đổi\n" in again.stdout
    assert not (tmp_path / ".claude").exists()
    claude = tmp_path / "c"
    claude.mkdir()
    assert install(dist, claude).returncode == 0 and not (claude / ".codex").exists()


def test_a_codex_hooks_file_that_does_not_parse_is_never_touched_d46(dist, tmp_path):
    h = tmp_path / ".codex/hooks.json"
    h.parent.mkdir()
    h.write_text("{ half typed", encoding="utf-8")
    r = install(dist, tmp_path, edition="codex")
    assert (r.returncode, h.read_text(encoding="utf-8")) == (2, "{ half typed")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    r = install(dist, fresh, "--dry-run", edition="codex")
    assert (r.returncode, (fresh / ".codex").exists()) == (0, False) and "(thử) không ghi" in r.stdout


def test_preflight_names_the_missing_rules_and_hook_until_the_installer_merged_them_d30_7(dist, tmp_path):
    assert install(dist, tmp_path).returncode == 0
    s = tmp_path / ".claude/settings.json"
    merged = s.read_text(encoding="utf-8")
    s.write_text(json.dumps(MINE), encoding="utf-8")
    py = tmp_path / ".claude/skills/zps-3dp-producer/scripts/producer.py"
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCER_ROOT", "PRODUCER_RUNTIME", "PRODUCER_KIT")} | {
        "BLENDER": str(tmp_path / "bin/Blender")}

    def preflight():
        r = subprocess.run([sys.executable, str(py), "preflight"], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout, json.loads((tmp_path / "production/preflight.json").read_text(encoding="utf-8"))["settings"]
    out, gap = preflight()
    assert (".claude/settings.json thiếu 10 allow rule, hook SessionStart, hook SubagentStop, hook Stop, env BASH_DEFAULT_TIMEOUT_MS, BASH_MAX_TIMEOUT_MS "
            "(Bash timeout, D33.4) → chạy lại install.py của bản cài") in out
    assert (len(gap["missing"]["allow"]), list(gap["missing"]["hooks"])) == (10, ["SessionStart", "SubagentStop", "Stop"])
    sk = tmp_path.resolve() / ".claude/skills/zps-3dp-producer"
    assert [r for r in gap["missing"]["allow"] if "run_tool" in r or "assemble.py" in r] == [
        f"Bash({sk}/scripts/run_tool.py:*)",
        f"Bash({sk}/scripts/.deps/venv/bin/python {sk}/scripts/assemble.py:*)"]
    s.write_text(merged, encoding="utf-8")
    out, gap = preflight()
    assert ("thiếu" in out, gap["missing"]) == (False, {"allow": [], "hooks": {}, "env": {}})
