"""One entry for the model check tools: --final F, a result JSON in F/review/checks/<name>.json, one printed line.
A tool with --before-join writes <name>_build.json instead, so its early run never stands in for the full one.
A tool that reads F/<id>-untextured.glb (glb=True) first checks glb.fresh: F/review/unwrap.json records the code_hash of
part_graph.json + parts_lib.py (self_build/graph.py) of the build the GLB comes from, and it must be the one of the files
in F now. Otherwise glb.fresh fails alone: a failed join leaves the GLB of an earlier build.
Exit 0 pass, info or not_checked; 1 fail; 2 error."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


STALE = "GLB không dựng từ part_graph.json + parts_lib.py hiện tại: chạy lại build_model.py"


def glb_fresh(final):
    """True when F/review/unwrap.json records the code_hash of the part_graph.json + parts_lib.py in F now."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "self_build"))
    import graph
    try:
        recorded = common.read_json(os.path.join(final, "review", "unwrap.json"))["data"].get("code_hash")
    except (OSError, ValueError, KeyError, AttributeError):
        return False
    return recorded == graph.code_hash(final)


def run(tool, name, doc, add_args, check, glb=False):
    p = argparse.ArgumentParser(description=doc)
    p.add_argument("--final", required=True)
    p.add_argument("--out")
    add_args(p)
    a = p.parse_args(common.script_argv())
    stem = f"{name}_build" if getattr(a, "before_join", False) else name
    out = a.out or os.path.join(a.final, "review", "checks", f"{stem}.json")
    if glb and not getattr(a, "before_join", False) and not glb_fresh(a.final):
        common.write_result(out, tool, [common.check("glb.fresh", "fail", note=STALE)])
        sys.exit(1)
    try:
        checks, data = check(a)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, tool, e)
        sys.exit(2)
    r = common.write_result(out, tool, checks, data=data)
    sys.exit(1 if r["overall"] == "fail" else 0)
