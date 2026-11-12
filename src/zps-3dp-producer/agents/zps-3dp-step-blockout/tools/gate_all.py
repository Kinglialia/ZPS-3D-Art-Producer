"""One build, every part gate, every check of the step. Prints the failures only.

Usage: PY T/gate_all.py --work <w> [--check-args NAME=ARGS ...] [--skip NAME ...] [--check-flag NAME]
  --check-args  extra arguments for one check, as one string: --check-args "check_inputs=--approved A --profile P".
  --skip        a check that gate_all does not run. check_fix is always skipped (it needs --old and a finding id).
  --check-flag  the name of the flag that gives each check its folder, without dashes (default work, so --work <w>).
Steps, in order:
  1. Deletes <w>/review/gates/*.json: a gate JSON of an older build never counts.
  2. Runs check_schema, check_materials and check_inputs, when they exist beside this file. A failed check_schema stops
     here: the kit cannot read the graph.
  3. Builds the whole graph once: build_parts.py assembly --work <w>, found beside this file or in the blockout tools.
     The kit places each part only from the parts before it, so this build gives the same assembly.json as one build per
     part with --upto.
  4. Gates every row of assembly.json with self_build/gates.py, in this process. Part i is gated from rows[:i + 1], so the
     result equals a gates.py run per part. Writes <w>/review/gates/<part>.json.
  5. Runs every other check_*.py beside this file, each as its own process (they exit on their own).
A check that writes no result JSON, or exits non-zero without one, is reported as an error. Nothing here runs the asset's
custom_parts.py: custom_mesh.py stays its own step, before this one.
Output: one line per failing JSON (path, then each failing check with its value), then `gate_all fail: <n> failing`.
All passed: one line, `gate_all pass: <parts> parts, <checks> checks`. not_checked and info are not failures.
Exit 0 pass, 1 any failure.
"""
import argparse
import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "self_build"), os.path.join(HERE, "lib")]
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "gate_all"
PRE_BUILD = ("check_inputs", "check_materials", "check_schema")
STOPS_BUILD = ("check_schema",)
ALWAYS_SKIP = ("check_fix",)
BUILD_AT = (os.path.join(HERE, "build_parts.py"),
            os.path.join(HERE, "..", "..", "zps-3dp-step-blockout", "tools", "build_parts.py"))
LINE_MAX = 220
LINES_MAX = 12


def checks_beside():
    return sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("check_") and f.endswith(".py"))


def snapshot(folder):
    out = {}
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith(".json"):
                p = os.path.join(root, f)
                out[p] = (os.stat(p).st_mtime_ns, os.stat(p).st_size)
    return out


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def failing(path, rel):
    """One line for a result JSON whose overall is fail or error, else None."""
    try:
        doc = read(path)
    except (OSError, ValueError) as ex:
        return f"{rel}: unreadable result ({type(ex).__name__})"
    if doc.get("overall") not in ("fail", "error"):
        return None
    if doc["overall"] == "error":
        return f"{rel}: error {str((doc.get('data') or {}).get('error', ''))[:120]}"
    bad = [f"{c['check']} {json.dumps(c.get('value'), ensure_ascii=False)[:60]}"
           + (f" (limit {c['threshold']})" if "threshold" in c else "")
           for c in doc.get("checks", []) if c.get("status") == "fail"]
    return f"{rel}: " + "; ".join(bad or ["fail"])


def run_check(name, work, flag, extra):
    """(failure lines, wrote a result) for one check process."""
    folder = os.path.join(work, "review", "checks")
    before = snapshot(folder)
    p = subprocess.run([sys.executable, os.path.join(HERE, f"{name}.py"), flag, work, *extra], capture_output=True,
                       text=True)
    after = snapshot(folder)
    changed = sorted(f for f, stamp in after.items() if before.get(f) != stamp)
    lines = [x for f in changed if (x := failing(f, os.path.relpath(f, work)))]
    if not changed and p.returncode:
        tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or ["no output"]
        lines.append(f"{name}: exit {p.returncode}, no result JSON: {tail[0][:140]}")
    elif not changed:
        lines.append(f"{name}: wrote no result JSON")
    return lines


def build(work):
    """Failure lines of the one build (empty: the build ran)."""
    tool = next((os.path.abspath(p) for p in BUILD_AT if os.path.isfile(p)), None)
    if tool is None:
        return [f"build: no build_parts.py beside {NAME}.py or in the blockout tools"]
    p = subprocess.run([sys.executable, tool, "assembly", "--work", work], capture_output=True, text=True)
    path = os.path.join(work, "assembly.json")
    try:
        asm = read(path)
    except (OSError, ValueError):
        return [f"build: exit {p.returncode}, no assembly.json: {(p.stderr or p.stdout).strip()[-140:]}"]
    if p.returncode or asm.get("overall") == "error":
        return [f"build: {str((asm.get('data') or {}).get('error') or p.stderr)[:LINE_MAX]}"]
    return [x for x in [failing(path, "assembly.json")] if x]


def gate_rows(work):
    """Gate every row of assembly.json in this process; gates.py is the kit's file and runs as its own main."""
    import gates
    rows = read(os.path.join(work, "assembly.json"))["data"]["parts"]
    lines = []
    for row in rows:
        out = os.path.join(work, "review", "gates", f"{row['name']}.json")
        argv, sys.argv = sys.argv, ["gates.py", "--work", work, "--part", row["name"], "--out", out]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                gates.main()
        except SystemExit:
            pass
        finally:
            sys.argv = argv
        if not os.path.isfile(out):
            lines.append(f"review/gates/{row['name']}.json: gates.py wrote no result")
        elif line := failing(out, os.path.relpath(out, work)):
            lines.append(line)
    return len(rows), lines


def run(work, extra, skip, flag):
    """(failure lines, number of parts gated, number of checks run)."""
    shutil.rmtree(os.path.join(work, "review", "gates"), ignore_errors=True)
    names = [c for c in checks_beside() if c not in skip]
    early = [c for c in PRE_BUILD if c in names]
    lines, ran = [], 0
    for name in early:
        got = run_check(name, work, flag, extra.get(name, []))
        lines += got
        ran += 1
        if got and name in STOPS_BUILD:
            return lines + [f"build: skipped, {name} failed"], 0, ran
    built = build(work)
    lines += built
    if any(x.startswith("build:") for x in built):
        return lines, 0, ran
    parts, gated = gate_rows(work)
    lines += gated
    for name in (c for c in names if c not in early):
        lines += run_check(name, work, flag, extra.get(name, []))
        ran += 1
    return lines, parts, ran


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--check-args", action="append", default=[], metavar="NAME=ARGS")
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--check-flag", default="work")
    a = ap.parse_args()
    extra = {}
    for item in a.check_args:
        name, _, args = item.partition("=")
        extra[name.removesuffix(".py")] = shlex.split(args)
    skip = {*ALWAYS_SKIP, *(s.removesuffix(".py") for s in a.skip)}
    lines, parts, ran = run(os.path.abspath(a.work), extra, skip, "--" + a.check_flag)
    if lines:
        print("\n".join(l[:LINE_MAX] for l in lines[:LINES_MAX]))
        if len(lines) > LINES_MAX:
            print(f"... {len(lines) - LINES_MAX} more")
        print(f"{NAME} fail: {len(lines)} failing")
        sys.exit(1)
    print(f"{NAME} pass: {parts} parts, {ran} checks")


if __name__ == "__main__":
    require_root()
    main()
