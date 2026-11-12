"""Make a param variant of a graph and run the whole chain on it: one command per variant.

Usage: PY T/make_variant.py --from <F> --out <V>/variants/<b|c> --set name=value [--set ...]
          [--old <old graph>/part_graph.json --finding <Fid> [--finding ...]] [--check-args NAME=ARGS ...] [--skip NAME ...]
Copies part_graph.json, sources.json and blockout.md of <F> into --out (an older --out is deleted first), sets each param
(it keeps the type of the old value: 1.0 stays a float, a count stays whole), then does what gate_all.py does for that
folder: one build, every gate, every check_*.py. With --old and --finding it also runs check_fix.py once per finding id.
When the chain built the variant, it writes the bbox line, the hashes and the mesh health into the variant's blockout.md
(blockout_md.py), so the variant that is picked carries its own numbers. The render is a separate command, once per variant:
  RUN bl render_critic.py --work <out> --mode critic --outdir <out>/review/renders [--spec V/work/spec.json]
  RUN bl render_review.py --work <out>
--check-args and --skip are the ones of gate_all.py (check_inputs needs --approved and --profile).
It refuses a name that is not a param, a name in fixed_params, a value that is not a number, and an --out whose folder is not
called `variants`. A graph that calls a function of the asset's custom_parts.py is copied and not built: the meshes of
those functions are made by custom_mesh.py, which this tool never runs (it runs agent code). The last line then names the
commands to run: custom_mesh.py, gate_all.py, and check_fix.py for each finding.
Output as gate_all.py: the failing lines, then one summary line. Exit 0 pass or copied, 1 fail, 2 refused.
"""
import argparse
import json
import os
import shlex
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
import blockout_md  # noqa: E402
import gate_all  # noqa: E402
import project_parts as PP  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "make_variant"
COPY = ("part_graph.json", "sources.json", "blockout.md")


class Refused(Exception):
    pass


def number(text, old):
    try:
        value = json.loads(text)
    except ValueError:
        raise Refused(f"value {text!r} is not a number") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(f"value {text!r} is not a number")
    if isinstance(old, int) and not isinstance(old, bool):
        if value != int(value):
            raise Refused(f"{text} is not whole, and the old value {old} is a count")
        return int(value)
    return float(value)


def set_params(graph, sets):
    params, fixed = graph.get("params", {}), set(graph.get("fixed_params") or [])
    for item in sets:
        name, sep, text = item.partition("=")
        if not sep or name not in params:
            raise Refused(f"--set {item}: {name or item!r} is not a param of the graph")
        if name in fixed:
            raise Refused(f"--set {item}: {name} is in fixed_params")
        params[name] = number(text, params[name])
    return graph


def uses_asset_function(out, graph):
    path = PP.find(out)
    if path is None:
        return False
    with open(path, encoding="utf-8") as f:
        own = set(PP.functions(f.read()))
    return any(p.get("primitive") == "custom" and p.get("fn") in own for p in graph.get("parts", []))


def copy_in(src, out, graph):
    if os.path.basename(os.path.dirname(os.path.abspath(out))) != "variants":
        raise Refused(f"--out {out}: its folder is not called variants")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for name in COPY:
        if name != "part_graph.json" and os.path.isfile(os.path.join(src, name)):
            shutil.copyfile(os.path.join(src, name), os.path.join(out, name))
    with open(os.path.join(out, "part_graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
        f.write("\n")


def refresh_md(out):
    path = os.path.join(out, "blockout.md")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            text = blockout_md.render(out, f.read())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as ex:  # noqa: BLE001
        return [f"blockout.md: not refreshed: {ex}"]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    ap.add_argument("--old")
    ap.add_argument("--finding", action="append", default=[])
    ap.add_argument("--check-args", action="append", default=[], metavar="NAME=ARGS")
    ap.add_argument("--skip", action="append", default=[])
    a = ap.parse_args()
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    try:
        if bool(a.old) != bool(a.finding):
            raise Refused("--old and --finding go together")
        with open(os.path.join(src, "part_graph.json"), encoding="utf-8") as f:
            graph = set_params(json.load(f), a.set)
        copy_in(src, out, graph)
    except (Refused, OSError, ValueError) as ex:
        print(f"{NAME} refused: {ex}")
        sys.exit(2)
    extra = {n.removesuffix(".py"): shlex.split(args) for n, _, args in (i.partition("=") for i in a.check_args)}
    pending = [f"RUN custom_mesh.py --work {out}", f"RUN gate_all.py --work {out}"] + [
        f"RUN check_fix.py --work {out} --old {a.old} --finding {fid}" for fid in a.finding]
    pending[1] += "".join(f" --skip {x}" for x in a.skip)
    if uses_asset_function(out, graph):
        print(f"{NAME} copied {out}; not built, the graph calls custom_parts.py. next: " + "; ".join(pending))
        return
    lines, parts, ran = gate_all.run(out, extra, {*gate_all.ALWAYS_SKIP, *(x.removesuffix(".py") for x in a.skip)}, "--work")
    if not any(x.startswith("build:") for x in lines):
        lines += refresh_md(out)
        for fid in a.finding:
            lines += gate_all.run_check("check_fix", out, "--work", ["--old", a.old, "--finding", fid])
    if lines:
        print("\n".join(l[:gate_all.LINE_MAX] for l in lines[:gate_all.LINES_MAX]))
        print(f"{NAME} fail: {len(lines)} failing in {out}")
        sys.exit(1)
    print(f"{NAME} pass: {out}, {parts} parts, {ran + len(a.finding)} checks")


if __name__ == "__main__":
    require_root()
    main()
