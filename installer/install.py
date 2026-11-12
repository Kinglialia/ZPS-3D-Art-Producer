#!/usr/bin/env python3
"""Install this edition into a project: skills into <project>/<install_root>/, agent files into <project>/<agents_root>/.

Usage: python3 install.py --project <project folder> [--dry-run]
A skill folder that exists is replaced except its .deps/ folders (venvs), so an upgrade drops the files a new version
removed and keeps the installed dependencies. Run setup_deps.sh after the first install.
The Claude edition then merges templates/settings.snippet.json into <install_root>/../settings.json (D30.7); the Codex
edition merges installer/codex_hooks.json into <project>/.codex/hooks.json (D46). Both print the diff first, only
append, keep the user's other hooks, and a second run changes nothing. --dry-run prints the diff and writes nothing."""
import argparse
import difflib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace_tree(src: Path, dst: Path):
    if dst.is_dir():
        for p in sorted(dst.rglob("*"), reverse=True):
            if ".deps" in p.relative_to(dst).parts:
                continue
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    m = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    proj = a.project.expanduser().resolve()
    if not proj.is_dir():
        print(f"không thấy thư mục project {proj}")
        return 2
    plan = [(HERE / "skills" / s, proj / m["install_root"] / s) for s in m["skills"]]
    plan += [(HERE / "agents" / f"{n}.md", proj / m["agents_root"] / f"{n}.md") for n in m["agents"]] if m["agents_root"] else []
    if links := [dst for src, dst in plan if src.is_dir() and dst.is_symlink()]:
        print("\n".join(f"{d} là symlink tới {d.resolve()}: không cài, để khỏi xoá file ở đó. Gỡ symlink rồi chạy lại."
                        for d in links))
        return 2
    for src, dst in plan:
        print(f"{'(thử) ' if a.dry_run else ''}{src.relative_to(HERE)} → {dst}")
        if a.dry_run:
            continue
        if src.is_dir():
            replace_tree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    skill = proj / m["install_root"] / m["producer"]
    rc = merge_settings(m, proj, skill, a.dry_run) or merge_hooks(m, proj, a.dry_run)
    print(f"Tiếp: bash {skill / 'scripts/setup_deps.sh'} và setup_deps.sh của từng agent trong {skill / 'agents'}"
          + ("; rồi python3 installer/codex_rules.py --write" if (HERE / "installer").is_dir() else ""))
    return rc


def settings_merge(m: dict):
    path = HERE / "skills" / m["producer"] / "scripts" / "settings_merge.py"
    spec = importlib.util.spec_from_file_location("settings_merge", path)
    sm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sm)
    return sm


def merge_settings(m: dict, proj: Path, skill: Path, dry_run: bool) -> int:
    """Only an edition that ships the snippet has runtime settings to merge."""
    snippet = HERE / "skills" / m["producer"] / "templates" / "settings.snippet.json"
    if not snippet.is_file():
        return 0
    return settings_merge(m).install(proj / Path(m["install_root"]).parent / "settings.json", snippet, skill, dry_run)


def merge_hooks(m: dict, proj: Path, dry_run: bool) -> int:
    """D46: the Codex hooks, with the hook part of the settings merge. Codex runs project hooks only in a trusted
    project, so the user trusts it once."""
    snippet = HERE / "installer" / "codex_hooks.json"
    if not snippet.is_file():
        return 0
    sm, path = settings_merge(m), proj / ".codex" / "hooks.json"
    try:
        cur = sm.read(path)
    except ValueError as ex:
        print(f"{path}: {ex}. Không ghi hook; sửa file rồi chạy lại.")
        return 2
    # The merge reads an allow list; a hooks file has none, so the empty one adds nothing.
    new = sm.merge(cur, json.loads(snippet.read_text(encoding="utf-8")) | {"permissions": {"allow": []}})
    if new == cur:
        print(f"{path}: đã đủ hook, không đổi")
        return 0
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    diff = difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), str(path), str(path))
    print("".join(diff), end="")
    if dry_run:
        print(f"(thử) không ghi {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    print(f"đã ghi {path}. Codex chỉ chạy hook này khi project được tin (trust): mở Codex trong project và tin hook "
          "một lần.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
