"""Turn the asset's own `custom` parts into JSON meshes, outside Blender (D32.2).

Usage: PY T/custom_mesh.py --work <w>
Reads <w>/part_graph.json and the asset's custom_parts.py (project_parts.find). The file must pass
project_parts.static_errors, and no function in it may take a name of custom_lib.FUNCTIONS. Then the file runs with only
the builtins of project_parts.BUILTINS and only `math` to import. Each `custom` part whose fn is a function of that file
gets fn(*args), with args resolved from the graph params as the kit does, and the result (vertices, faces) goes to
project_parts.mesh_dir(<w>)/<part>.json (mesh_from_json.py format; args and the sha256 of custom_parts.py included, so
build_parts.py refuses a mesh made for other values). Older files in that folder are removed first.
Run it after each change to part_graph.json or custom_parts.py, before the Blender build. It refuses to run inside
Blender: Blender builds only from the JSON. Prints one line. Exit 0 done (or nothing to do), 1 refused or failed, 2 inside
Blender.
"""
import argparse
import builtins
import glob
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "self_build"), os.path.join(HERE, "lib"), HERE]
import custom_lib  # noqa: E402
import graph as G  # noqa: E402
import mesh_from_json as MJ  # noqa: E402
import project_parts as PP  # noqa: E402
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "[blockout/custom_mesh]"


def _import_math(name, *_a, **_k):
    if name != "math":
        raise ImportError(f"custom_parts.py may import only math, not {name}")
    return math


def load(path, src):
    """The functions of the asset file, run with a cut-down set of builtins."""
    env = {"__builtins__": {n: getattr(builtins, n) for n in PP.BUILTINS} | {"__import__": _import_math},
           "__name__": "custom_parts"}
    exec(compile(src, path, "exec"), env)
    return {n: env[n] for n in PP.functions(src)}


def run(gdir):
    """(written paths, errors). Nothing is written when there is an error."""
    path = PP.find(gdir)
    if path is None:
        return [], []
    with open(path, encoding="utf-8") as f:
        src = f.read()
    errs = PP.static_errors(src)
    if errs:
        return [], [f"{PP.FILE} refused by the static check: {e}" for e in errs]
    clash = sorted(set(PP.functions(src)) & set(custom_lib.FUNCTIONS))
    if clash:
        return [], [f"{PP.FILE} redefines {', '.join(clash)} of custom_lib.py: give the asset function another name"]
    out = PP.mesh_dir(gdir)
    if out is None:
        return [], [f"{gdir} is not inside a vN folder: no place for the JSON meshes"]
    graph = G.load_graph(gdir)
    params = graph.get("params") or {}
    own = set(PP.functions(src))
    parts = [p for p in G.expand_parts(graph) if p.get("primitive") == "custom" and p.get("fn") in own
             and (p.get("attach") or {}).get("type") != "mirror_of"]
    fns, sha, docs, errs = load(path, src), hashlib.sha256(src.encode("utf-8")).hexdigest(), [], []
    for p in parts:
        name, fn = p["name"], p["fn"]
        try:
            args = [G.value(a, params, f"{name}.args") if isinstance(a, str) else a for a in p.get("args", [])]
            res = fns[fn](*args)
            verts, faces = res
            verts = [[float(c) for c in v] for v in verts]
            faces = [[int(k) for k in f] for f in faces]
        except Exception as ex:  # noqa: BLE001 - every failure of agent code is reported, not raised
            errs.append(f"{name}: {fn} failed: {type(ex).__name__}: {ex}")
            continue
        bad = MJ.errors(verts, faces)
        if bad:
            errs.append(f"{name}: {fn} returned a bad mesh: {'; '.join(bad[:3])}")
            continue
        docs.append({"tool": MJ.TOOL, "part": name, "fn": fn, "args": args, "source_sha256": sha,
                     "verts": verts, "faces": faces})
    if errs:
        return [], errs
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*.json")):
        os.remove(old)
    written = []
    for d in docs:
        dst = os.path.join(out, f"{d['part']}.json")
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(d, f, allow_nan=False)
        written.append(dst)
    return written, []


def main():
    if "bpy" in sys.modules:
        print(f"{NAME} error: run with PY, not inside Blender; Blender builds only from the JSON meshes")
        sys.exit(2)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    try:
        written, errs = run(a.work)
    except (OSError, ValueError, G.GraphError) as ex:
        written, errs = [], [str(ex)]
    if errs:
        print(f"{NAME} fail: {' | '.join(errs)}")
        sys.exit(1)
    print(f"{NAME} {len(written)} mesh" + (f" -> {os.path.dirname(written[0])}" if written else
                                            ": no part uses a function of custom_parts.py"))


if __name__ == "__main__":
    require_root()
    main()
