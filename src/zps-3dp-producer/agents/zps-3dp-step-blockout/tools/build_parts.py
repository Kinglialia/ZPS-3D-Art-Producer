"""Run the kit's self_build assembly.py or param_fit.py with `custom` parts taken only from custom_lib.py and from the
JSON meshes of the asset's own functions (D27.13, D32.2).

Usage:
  PY T/build_parts.py assembly --work <w> [assembly.py options]
  PY T/build_parts.py param_fit --work <w> --spec <spec.json> [param_fit.py options]
  BLENDER -b --python T/build_parts.py -- assembly --work <w> ...     (graph with custom parts; lib/bootstrap.py puts
                                                                       tools/.deps/blender-py<ver> on sys.path)
The kit tools exec <graph dir>/parts_lib.py through graph.load_parts_lib. Here that function never imports it: it
copies custom_lib.py over <graph dir>/parts_lib.py, so the file beside the graph is the shared code that ran. A part
whose fn is a function of the asset's custom_parts.py (project_parts.find; names read with ast, the file never runs here)
gets the mesh that custom_mesh.py wrote to project_parts.mesh_dir(<w>), built by mesh_from_json.py. That mesh must have
the same fn, the same args and the sha256 of the current custom_parts.py. A refused file, a name clash, a missing or
stale mesh, or a `custom` part whose fn is in neither file stops the build with a GraphError in the kit's result JSON
(assembly.json or fit.json), exit 1. param_fit does not fit params that feed an asset function, because its mesh is
fixed until custom_mesh.py runs again; it prints them. Unknown first argument: exit 2.
"""
import glob
import hashlib
import os
import runpy
import shutil
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "self_build")
sys.path[:0] = [KIT, os.path.join(HERE, "lib"), HERE]
import bootstrap  # noqa: E402,F401
import common  # noqa: E402
import graph as G  # noqa: E402
import mesh_from_json as MJ  # noqa: E402
import project_parts as PP  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TARGETS = ("assembly", "param_fit")
LIB = os.path.join(HERE, "custom_lib.py")
FED = set()   # params that feed an asset function; approved_lib fills it before param_fit lists the params to fit


def project_functions(gdir):
    """(names, sha256) of the asset's custom_parts.py, or ([], None). Refused before anything is built."""
    path = PP.find(gdir)
    if path is None:
        return [], None
    with open(path, encoding="utf-8") as f:
        src = f.read()
    errs = PP.static_errors(src)
    if errs:
        raise G.GraphError(f"{PP.FILE} refused by the static check: {'; '.join(errs)}")
    return PP.functions(src), hashlib.sha256(src.encode("utf-8")).hexdigest()


def asset_function(fn, gdir, sha):
    """The stand-in for asset function fn: the JSON mesh custom_mesh.py made for these args, as a bmesh."""
    def build(*args):
        where = PP.mesh_dir(gdir)
        run = f"run `PY T/custom_mesh.py --work {gdir}` after each change to part_graph.json or {PP.FILE}"
        docs = [MJ.read(p) for p in sorted(glob.glob(os.path.join(where or "", "*.json")))] if where else []
        same = [d for d in docs if d.get("fn") == fn and len(d.get("args", [])) == len(args)
                and all(abs(float(x) - float(y)) <= 1e-9 for x, y in zip(d["args"], args))]
        if not same:
            raise G.GraphError(f"no JSON mesh of {fn}{tuple(args)} in {where}: {run}")
        if same[0].get("source_sha256") != sha:
            raise G.GraphError(f"the JSON mesh of {fn} in {where} was made from another {PP.FILE}: {run}")
        return MJ.to_bmesh(same[0])
    return build


def approved_lib(gdir):
    shutil.copyfile(LIB, os.path.join(gdir, "parts_lib.py"))
    graph = G.load_graph(gdir)
    custom = [p for p in graph.get("parts", []) if p.get("primitive") == "custom"]
    if not custom:
        return None
    own, sha = project_functions(gdir)
    try:
        import bpy  # noqa: F401  (with the bpy pip module, bmesh loads only after bpy)
    except ImportError:
        pass
    import custom_lib
    fns = dict(custom_lib.FUNCTIONS)
    clash = sorted(set(own) & set(fns))
    if clash:
        raise G.GraphError(f"{PP.FILE} redefines {', '.join(clash)} of custom_lib.py: give the asset function "
                           f"another name")
    fns.update({n: asset_function(n, gdir, sha) for n in own})
    unknown = sorted({str(p.get("fn")) for p in custom if p.get("fn") not in fns})
    if unknown:
        raise G.GraphError(f"custom fn not in custom_lib.py or {PP.FILE}: {', '.join(unknown)}; "
                           f"available: {', '.join(fns)}")
    FED.update(a for p in G.expand_parts(graph) if p.get("fn") in own for a in p.get("args", []) if isinstance(a, str))
    return types.SimpleNamespace(**fns)


def fit_params(graph, _kit=G.fit_params):
    names = _kit(graph)
    held = sorted(set(names) & FED)
    if held:
        print(f"[blockout/build_parts] not fitted, they feed a {PP.FILE} function: {', '.join(held)}")
    return [n for n in names if n not in FED]


def main():
    args = common.script_argv()
    if not args or args[0] not in TARGETS:
        print(f"[blockout/build_parts] error: first argument must be one of {', '.join(TARGETS)}")
        sys.exit(2)
    target = args[0]
    sys.argv = sys.argv[:len(sys.argv) - len(args)] + args[1:]
    G.load_parts_lib = approved_lib
    G.fit_params = fit_params
    runpy.run_path(os.path.join(KIT, f"{target}.py"), run_name="__main__")


if __name__ == "__main__":
    require_root()
    main()
