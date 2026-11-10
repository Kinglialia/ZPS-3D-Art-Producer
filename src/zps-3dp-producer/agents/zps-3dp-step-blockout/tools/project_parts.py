"""The project's own `custom` part functions (D33): <PRODUCER_ROOT>/assets/<id>/custom_parts.py, written by the step
agent for one asset and deleted by the D29 purge. Plain Python: this module reads the file with `ast` and never runs it.

static_errors() is the check build_parts.py runs before it executes the file: imports only from ALLOWED_IMPORTS, no
name in BANNED_NAMES, no dunder name or attribute. It narrows what the code can reach; it is not a sandbox.
"""
import ast
import os

FILE = "custom_parts.py"
MARK = "# ---- custom_parts.py of this asset (D33): written for this asset only ----"
ALLOWED_IMPORTS = {"math", "bmesh", "mathutils"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
                "delattr", "breakpoint", "input", "os", "sys", "subprocess", "shutil", "pathlib", "importlib",
                "builtins", "ctypes", "socket", "ssl", "http", "urllib", "requests", "ftplib", "smtplib", "asyncio"}


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


def static_errors(src):
    """Reasons to refuse the source, one line each (empty: the check passes)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as ex:
        return [f"line {ex.lineno}: syntax error: {ex.msg}"]
    errs = []
    for n in ast.walk(tree):
        line = getattr(n, "lineno", "?")
        if isinstance(n, ast.Import):
            errs += [f"line {line}: import {a.name}" for a in n.names if a.name.split(".")[0] not in ALLOWED_IMPORTS]
        elif isinstance(n, ast.ImportFrom):
            if n.level or (n.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                errs.append(f"line {line}: from {'.' * n.level}{n.module or ''} import")
        elif isinstance(n, ast.Name) and (n.id in BANNED_NAMES or n.id.startswith("__")):
            errs.append(f"line {line}: name {n.id}")
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            errs.append(f"line {line}: attribute {n.attr}")
    return errs


def functions(src):
    """Public top-level function names: the ones a `custom` part may name in `fn`."""
    return sorted(n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))
