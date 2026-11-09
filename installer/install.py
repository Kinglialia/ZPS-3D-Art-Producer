#!/usr/bin/env python3
"""Install this edition into a project: skills into <project>/<install_root>/, agent files into <project>/<agents_root>/.

Usage: python3 install.py --project <project folder> [--dry-run]
A skill folder that exists is replaced except its .deps/ folders (venvs), so an upgrade drops the files a new version
removed and keeps the installed dependencies. Run setup_deps.sh after the first install."""
import argparse
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
    print(f"Tiếp: bash {skill / 'scripts/setup_deps.sh'} và setup_deps.sh của từng agent trong {skill / 'agents'}"
          + ("; rồi python3 installer/codex_rules.py --write" if (HERE / "installer").is_dir() else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
