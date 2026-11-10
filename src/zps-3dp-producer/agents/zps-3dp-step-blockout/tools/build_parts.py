"""Run the kit's self_build assembly.py or param_fit.py with `custom` parts taken only from custom_lib.py and from the
asset's custom_parts.py (D32).

Usage:
  PY T/build_parts.py assembly --work <w> [assembly.py options]
  PY T/build_parts.py param_fit --work <w> --spec <spec.json> [param_fit.py options]
  BLENDER -b --python T/build_parts.py -- assembly --work <w> ...     (graph with custom parts; lib/bootstrap.py puts
                                                                       tools/.deps/blender-py<ver> on sys.path)
The kit tools exec <graph dir>/parts_lib.py through graph.load_parts_lib. Here that function never imports it.
It writes custom_lib.py, then the asset's custom_parts.py after project_parts.MARK, over <graph dir>/parts_lib.py, so
the file beside the graph is the code that ran and the kit's code hash covers it. The asset file is
<PRODUCER_ROOT>/assets/<id>/custom_parts.py above <w> (project_parts.find). It must pass project_parts.static_errors
before it runs, and no function in it may take a name of custom_lib.FUNCTIONS. A refused file, a name clash, or a
`custom` part whose fn is in neither file stops the build with a GraphError in the kit's result JSON (assembly.json or
fit.json), exit 1. Unknown first argument: exit 2.
"""
import os
import runpy
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "self_build")
sys.path[:0] = [KIT, os.path.join(HERE, "lib"), HERE]
import bootstrap  # noqa: E402,F401
import common  # noqa: E402
import graph as G  # noqa: E402
import project_parts as PP  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TARGETS = ("assembly", "param_fit")
LIB = os.path.join(HERE, "custom_lib.py")


def project_source(gdir):
    """(path, source) of the asset's custom_parts.py, or (None, None). Refused before anything runs or is written."""
    path = PP.find(gdir)
    if path is None:
        return None, None
    with open(path, encoding="utf-8") as f:
        src = f.read()
    errs = PP.static_errors(src)
    if errs:
        raise G.GraphError(f"{PP.FILE} refused by the static check: {'; '.join(errs)}")
    return path, src


def approved_lib(gdir):
    path, src = project_source(gdir)
    with open(LIB, encoding="utf-8") as f:
        code = f.read()
    with open(os.path.join(gdir, "parts_lib.py"), "w", encoding="utf-8") as f:
        f.write(code if src is None else f"{code}\n\n{PP.MARK}\n{src}")
    custom = [p for p in G.load_graph(gdir).get("parts", []) if p.get("primitive") == "custom"]
    if not custom:
        return None
    try:
        import bpy  # noqa: F401  (with the bpy pip module, bmesh loads only after bpy)
    except ImportError:
        pass
    import custom_lib
    fns = dict(custom_lib.FUNCTIONS)
    if src is not None:
        clash = sorted(set(PP.functions(src)) & set(fns))
        if clash:
            raise G.GraphError(f"{PP.FILE} redefines {', '.join(clash)} of custom_lib.py: give the asset function "
                               f"another name")
        mod = types.ModuleType("custom_parts")
        exec(compile(src, path, "exec"), mod.__dict__)
        fns.update({n: getattr(mod, n) for n in PP.functions(src)})
    unknown = sorted({str(p.get("fn")) for p in custom if p.get("fn") not in fns})
    if unknown:
        raise G.GraphError(f"custom fn not in custom_lib.py or {PP.FILE}: {', '.join(unknown)}; "
                           f"available: {', '.join(fns)}")
    return types.SimpleNamespace(**fns)


def main():
    args = common.script_argv()
    if not args or args[0] not in TARGETS:
        print(f"[blockout/build_parts] error: first argument must be one of {', '.join(TARGETS)}")
        sys.exit(2)
    target = args[0]
    sys.argv = sys.argv[:len(sys.argv) - len(args)] + args[1:]
    G.load_parts_lib = approved_lib
    runpy.run_path(os.path.join(KIT, f"{target}.py"), run_name="__main__")


if __name__ == "__main__":
    require_root()
    main()
