"""The project's own `custom` part functions (D32.2): <PRODUCER_ROOT>/assets/<id>/custom_parts.py, written by the step
agent for one asset and kept after DUYỆT 2 as a text source (D32.3). The file is plain Python that uses only `math`:
each public function returns (vertices, faces). custom_mesh.py runs it outside Blender and writes one JSON mesh per
part into mesh_dir(); inside Blender, build_parts.py builds those meshes with mesh_from_json.py. This module reads the
file with `ast` and never runs it.

static_errors() is an allow-list: only the node types in NODES; `import math` / `from math import ...` only; every name
a function reads is one the file defines, `math`, or a builtin of BUILTINS; no name or attribute that starts with `__`;
no str.format. It narrows what the code can reach; it is not a sandbox.
"""
import ast
import os
import re

FILE = "custom_parts.py"
MESH_DIR = "custom_mesh"
BUILTINS = ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "float", "int", "isinstance", "len", "list",
            "max", "min", "pow", "range", "reversed", "round", "set", "sorted", "sum", "tuple", "zip", "ValueError")
NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.For,
         ast.While, ast.If, ast.Break, ast.Continue, ast.Pass, ast.Expr, ast.Raise, ast.Assert, ast.Import,
         ast.ImportFrom, ast.alias, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.keyword,
         ast.Constant, ast.Name, ast.Attribute, ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict, ast.Set,
         ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Starred, ast.JoinedStr,
         ast.FormattedValue, ast.Lambda, ast.expr_context, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)
BANNED_ATTRS = ("format", "format_map")


def find(gdir):
    """custom_parts.py of the asset that holds gdir (the first ancestor whose parent is `assets` under a folder with
    pipeline.toml), or None when gdir is outside an asset or the asset has no such file."""
    d = os.path.abspath(gdir)
    while os.path.dirname(d) != d:
        top = os.path.dirname(d)
        if os.path.basename(top) == "assets" and os.path.isfile(os.path.join(os.path.dirname(top), "pipeline.toml")):
            path = os.path.join(d, FILE)
            return path if os.path.isfile(path) else None
        d = top
    return None


def mesh_dir(gdir):
    """<vN>/work/custom_mesh/ for the graph in <vN>/final/, and <vN>/work/custom_mesh/<sub>/ for any other graph of the
    version (variants/b, final/rollouts/1), so two graphs of one version never share a part's file. None when gdir is
    not inside a vN folder."""
    d = os.path.abspath(gdir)
    while os.path.dirname(d) != d:
        if re.fullmatch(r"v\d+", os.path.basename(d)):
            sub = os.path.relpath(os.path.abspath(gdir), d)
            out = os.path.join(d, "work", MESH_DIR)
            return out if sub == "final" else os.path.join(out, sub)
        d = os.path.dirname(d)
    return None


def _defined(tree):
    names = {"math"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, ast.FunctionDef):
            names.add(n.name)
        elif isinstance(n, ast.alias):
            names.add(n.asname or n.name)
    return names


def static_errors(src):
    """Reasons to refuse the source, one line each (empty: the check passes)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as ex:
        return [f"line {ex.lineno}: syntax error: {ex.msg}"]
    errs, known = [], _defined(tree) | set(BUILTINS)
    for n in ast.walk(tree):
        line = getattr(n, "lineno", "?")
        if not isinstance(n, NODES):
            errs.append(f"line {line}: {type(n).__name__} is not allowed")
        elif isinstance(n, ast.Import):
            errs += [f"line {line}: import {a.name}" for a in n.names if a.name != "math"]
        elif isinstance(n, ast.ImportFrom):
            if n.level or n.module != "math":
                errs.append(f"line {line}: from {'.' * n.level}{n.module or ''} import")
        elif isinstance(n, ast.Name) and (n.id.startswith("__") or n.id not in known):
            errs.append(f"line {line}: name {n.id}")
        elif isinstance(n, ast.Attribute) and (n.attr.startswith("__") or n.attr in BANNED_ATTRS):
            errs.append(f"line {line}: attribute {n.attr}")
        elif isinstance(n, (ast.FunctionDef, ast.arg)) and (own := getattr(n, "name", None) or n.arg).startswith("__"):
            errs.append(f"line {line}: name {own}")
    return errs


def functions(src):
    """Public top-level function names: the ones a `custom` part may name in `fn`."""
    return sorted(n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))
