"""Run the kit's self_build assembly.py or param_fit.py with `custom` parts taken only from custom_lib.py (D27.13).

Usage:
  PY T/build_parts.py assembly --work <w> [assembly.py options]
  PY T/build_parts.py param_fit --work <w> --spec <spec.json> [param_fit.py options]
  BLENDER -b --python T/build_parts.py -- assembly --work <w> ...     (graph with custom parts; lib/bootstrap.py puts
                                                                       tools/.deps/blender-py<ver> on sys.path)
The kit tools exec <graph dir>/parts_lib.py through graph.load_parts_lib. Here that function never imports it:
it copies custom_lib.py over <graph dir>/parts_lib.py, so the file beside the graph is the code that ran, and it
returns custom_lib.FUNCTIONS. A `custom` part whose fn is not in FUNCTIONS stops the build with a GraphError in the
kit's result JSON (assembly.json or fit.json), exit 1. Unknown first argument: exit 2.
"""
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
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TARGETS = ("assembly", "param_fit")
LIB = os.path.join(HERE, "custom_lib.py")


def approved_lib(gdir):
    shutil.copyfile(LIB, os.path.join(gdir, "parts_lib.py"))
    custom = [p for p in G.load_graph(gdir).get("parts", []) if p.get("primitive") == "custom"]
    if not custom:
        return None
    try:
        import bpy  # noqa: F401  (with the bpy pip module, bmesh loads only after bpy)
    except ImportError:
        pass
    import custom_lib
    unknown = sorted({str(p.get("fn")) for p in custom if p.get("fn") not in custom_lib.FUNCTIONS})
    if unknown:
        raise G.GraphError(f"custom fn not in custom_lib.py: {', '.join(unknown)}; "
                           f"approved: {', '.join(custom_lib.FUNCTIONS)}")
    return types.SimpleNamespace(**custom_lib.FUNCTIONS)


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
