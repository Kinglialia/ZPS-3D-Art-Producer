"""One entry for the model check tools: --final F, a result JSON in F/review/checks/<name>.json, one printed line.
A tool with --before-join writes <name>_build.json instead, so its early run never stands in for the full one.
Exit 0 pass, info or not_checked; 1 fail; 2 error."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def run(tool, name, doc, add_args, check):
    p = argparse.ArgumentParser(description=doc)
    p.add_argument("--final", required=True)
    p.add_argument("--out")
    add_args(p)
    a = p.parse_args(common.script_argv())
    stem = f"{name}_build" if getattr(a, "before_join", False) else name
    out = a.out or os.path.join(a.final, "review", "checks", f"{stem}.json")
    try:
        checks, data = check(a)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, tool, e)
        sys.exit(2)
    r = common.write_result(out, tool, checks, data=data)
    sys.exit(1 if r["overall"] == "fail" else 0)
