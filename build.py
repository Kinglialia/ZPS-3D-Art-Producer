#!/usr/bin/env python3
"""Build the installable trees of the ZPS-3DP Producer from src/ for each edition (docs/EDITIONS.md).

Usage:
  python3 build.py                     # claude and codex
  python3 build.py --edition codex [--out DIR]

Output: <out>/zps-3dp-<edition>-v<VERSION>/ with skills/, install.py, manifest.json; the Claude edition adds agents/
(flat agent files), the Codex edition adds installer/codex_rules.py. Default <out> is dist/.
The build stops with exit 1 when a check fails, and runs the static part of evals/triggers.json.
Edit src/, editions/ or installer/, never dist/. Standard library only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
SRC, ED, EVALS = ROOT / "src", ROOT / "editions", ROOT / "evals" / "triggers.json"
PRODUCER = "zps-3dp-producer"
TEXT = {".md", ".json", ".yaml", ".yml", ".txt", ".py", ".sh", ".toml", ".mjs", ".js", ".html"}
IGNORE = shutil.ignore_patterns(".deps", "__pycache__", "*.pyc", ".DS_Store", ".pytest_cache")
DESC_MAX = 300
FIXED = ("Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. "
         "Không dùng khi người dùng gọi trực tiếp.")
ADAPTER_SECTIONS = {"Gọi agent", "Resume", "Model", "Token", "Hook mở phiên", "Gửi file", "Đường dẫn", "Sandbox",
                    "Phiên mới", "Review Board", "Ảnh"}
KIT_SKILL = re.compile(r"\bzps-(?!3dp-)[a-z0-9]+(?:-[a-z0-9]+)*")
CASE_KEYS = {"query", "should_trigger", "kind", "why"}


def skills() -> list[str]:
    return sorted(p.name for p in SRC.iterdir() if (p / "SKILL.md").is_file())


def agents(skill_dir: Path) -> dict[str, Path]:
    """name → agent file: `agents/<name>.md` or `agents/<name>/<name>.md`."""
    d = skill_dir / "agents"
    out = {p.stem: p for p in d.glob("zps-*.md")}
    out |= {p.name: p / f"{p.name}.md" for p in d.iterdir() if p.is_dir() and (p / f"{p.name}.md").is_file()}
    return dict(sorted(out.items()))


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    return dict(m.groups() for m in re.finditer(r"^([\w-]+):\s*(.*)$", text[4:text.index("\n---", 4)], re.M))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rename_pattern(names) -> re.Pattern:
    alt = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({alt})(?![\w-])")


def build(edition: str, version: str, out: Path) -> bool:
    cfg = json.loads((ED / edition / "edition.json").read_text(encoding="utf-8"))
    suffix, src_agents = cfg["skill_suffix"], agents(SRC / PRODUCER)
    names = skills() + list(src_agents)
    final = {n: n + suffix for n in names}
    stage = out / f"zps-3dp-{edition}-v{version}"
    if stage.exists():
        shutil.rmtree(stage)
    sk = stage / "skills"
    shutil.copytree(SRC, sk, ignore=IGNORE)
    prod = sk / PRODUCER
    for rel in cfg["exclude"]:
        (prod / rel).unlink()
    shutil.copy(ED / edition / "adapter.md", prod / "references" / "runtime.md")
    (prod / "runtime.json").write_text(json.dumps({"runtime": edition, "suffix": suffix, "models": cfg["models"],
                                                   "agent_file": cfg["agent_file"], "image_gen": cfg["image_gen"]}, indent=2) + "\n", encoding="utf-8")
    for n, f in src_agents.items():
        p = prod / f.relative_to(SRC / PRODUCER)
        if p.parent.name == n:
            p.rename(p.parent / f"{final[n]}.md")
            p.parent.rename(p.parent.with_name(final[n]))
        else:
            p.rename(p.with_name(f"{final[n]}.md"))
    for n in skills():
        (sk / n).rename(sk / final[n])
    pat = rename_pattern(names)
    for f in (p for p in sk.rglob("*") if p.is_file() and p.suffix in TEXT):
        t = f.read_text(encoding="utf-8")
        t2 = pat.sub(lambda m: final[m[1]], t) if suffix else t
        t2 = t2.replace(".claude/skills/", cfg["install_root"] + "/")
        if f.name == "SKILL.md":
            t2 = re.sub(r"^(# ZPS-3DP · .+)$", rf"\g<1>{cfg['display_suffix']}", t2, count=1, flags=re.M)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    built_agents = agents(sk / final[PRODUCER])
    if cfg["openai_yaml"]:
        for n in skills():
            text = (sk / final[n] / "SKILL.md").read_text(encoding="utf-8")
            title = re.search(r"^# (.+)$", text, re.M)[1]
            implicit = frontmatter(text).get("disable-model-invocation") != "true"
            (sk / final[n] / "agents").mkdir(exist_ok=True)
            (sk / final[n] / "agents" / "openai.yaml").write_text(
                f'interface:\n  display_name: "{title}"\n' + ("" if implicit else
                                                              "policy:\n  allow_implicit_invocation: false\n"),
                encoding="utf-8")
    if cfg["agents_root"]:
        (stage / "agents").mkdir()
        for n, f in built_agents.items():
            shutil.copy(f, stage / "agents" / f"{n}.md")
    if (ED / edition / "installer").is_dir():
        shutil.copytree(ED / edition / "installer", stage / "installer", ignore=IGNORE)
    shutil.copy(ROOT / "installer" / "install.py", stage / "install.py")
    files = {p.relative_to(stage).as_posix(): sha(p) for p in sorted(stage.rglob("*")) if p.is_file()}
    manifest = {"package": "ZPS-3DP Producer", "version": version, "edition": edition, "title": cfg["title"],
                "install_root": cfg["install_root"], "agents_root": cfg["agents_root"],
                "producer": final[PRODUCER], "skills": [final[n] for n in skills()], "agents": list(built_agents),
                "files": files}
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    errors = check(stage, cfg, final, built_agents)
    if errors:
        print(f"[{edition}] FAILED:\n  " + "\n  ".join(errors))
        return False
    print(f"[{edition}] OK: {stage}")
    return True


def check(stage: Path, cfg: dict, final: dict, built_agents: dict) -> list[str]:
    errors, total = [], 0
    sk = stage / "skills"
    producer = final[PRODUCER]
    for n in [final[s] for s in skills()]:
        try:
            fm = frontmatter((sk / n / "SKILL.md").read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append(f"{n}: {e}")
            continue
        total += len(fm.get("description", ""))
        errors += desc_errors(n, fm)
    for n, f in built_agents.items():
        fm = frontmatter(f.read_text(encoding="utf-8"))
        total += len(fm.get("description", ""))
        errors += desc_errors(n, fm)
        if not fm.get("description", "").startswith(FIXED.replace(PRODUCER, producer)):
            errors.append(f"{n}: description does not start with the fixed sentence (D23.2)")
        errors += path_errors(n, f)
    for f in sk.rglob("*.md"):
        for path in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", f.read_text(encoding="utf-8")):
            if not path.startswith(("http", "mailto:")) and not (f.parent / path).exists():
                errors.append(f"{f.relative_to(stage)}: broken link {path}")
    texts = [(f, f.read_text(encoding="utf-8")) for f in stage.rglob("*") if f.is_file() and f.suffix in TEXT]
    if cfg["skill_suffix"]:
        errors += [f"{f.relative_to(stage)}: Claude path in the Codex edition" for f, t in texts if ".claude/" in t]
    else:
        other = re.compile(r"(?<![\w-])zps-3dp-[a-z0-9-]+-codex(?![\w-])")
        errors += [f"{f.relative_to(stage)}: Codex name in the Claude edition" for f, t in texts if other.search(t)]
    heads = set(re.findall(r"^## (.+)$", (ED / cfg["edition"] / "adapter.md").read_text(encoding="utf-8"), re.M))
    if extra := heads - ADAPTER_SECTIONS:
        errors.append(f"adapter.md: sections outside runtime mechanics (D22.9): {sorted(extra)}")
    ev, cases = eval_errors(list(final), set(skills()))
    errors += ev
    print(f"[{cfg['edition']}] {len(skills())} skills, {len(built_agents)} agents, descriptions {total} characters, "
          f"{cases} trigger cases")
    return errors


def desc_errors(name: str, fm: dict) -> list[str]:
    d = fm.get("description", "")
    out = [] if fm.get("name") == name else [f"{name}: name is {fm.get('name')!r}"]
    return out + ([f"{name}: description has {len(d)} characters (max {DESC_MAX})"] if not d or len(d) > DESC_MAX else [])


def path_errors(name: str, f: Path) -> list[str]:
    """A flat agent install keeps only paths through the brief's TOOLS line: `T/…`, `R/…` (R = T/../references)."""
    body, tools = f.read_text(encoding="utf-8"), f.parent / "tools"
    out = [f"{name}: bare `references/` path breaks in a flat agent install" for _ in re.findall(r"`references/", body)]
    if "`R/" in body and "`R` = `T/../references`" not in body:
        out.append(f"{name}: uses R/ without defining R = T/../references")
    out += [f"{name}: missing R/{r}" for r in re.findall(r"`R/([\w./-]+)`", body) if not (f.parent / "references" / r).is_file()]
    out += [f"{name}: missing T/{t}" for t in set(re.findall(r"\bT/([\w./-]+\.(?:py|sh|mjs))", body))
            if not (tools / t).is_file()]
    return out


def eval_errors(targets: list[str], skill_names: set[str]) -> tuple[list[str], int]:
    """Static part of the trigger eval (D25.E): kit case format, coverage, and the dispatch rule of D23.2."""
    try:
        ev = json.loads(EVALS.read_text(encoding="utf-8"))["targets"]
    except (OSError, ValueError, KeyError) as e:
        return [f"evals/triggers.json: {e}"], 0
    out = [f"evals: no cases for {t}" for t in targets if t not in ev]
    out += [f"evals: {t} is not a skill or agent" for t in ev if t not in targets]
    n = 0
    for t, spec in ev.items():
        cs = spec.get("cases") or []
        n += len(cs)
        bad = [c for c in cs if set(c) != CASE_KEYS or c["kind"] not in ("positive", "negative", "edge")]
        if not spec.get("rule") or bad or not any(c["should_trigger"] for c in cs) or all(c["should_trigger"] for c in cs):
            out.append(f"evals: {t} needs a rule and both trigger and no-trigger cases; bad: {bad[:2]}")
        neg = [c for c in cs if not c["should_trigger"]]
        if not any(KIT_SKILL.search(c["why"]) for c in neg):
            out.append(f"evals: {t} has no negative that overlaps a kit skill")
        if t not in skill_names:
            out += [f"evals: {t} positive without a brief: {c['query'][:40]}" for c in cs
                    if c["should_trigger"] and "brief" not in c["query"]]
            out += [f"evals: {t} negative names a brief: {c['query'][:40]}" for c in neg if "brief" in c["query"]]
    return out, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edition", choices=["claude", "codex", "all"], default="all")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    eds = ["claude", "codex"] if a.edition == "all" else [a.edition]
    return 0 if all([build(e, version, a.out.resolve()) for e in eds]) else 1


if __name__ == "__main__":
    sys.exit(main())
