"""Shared helpers for tools/self_build and tools/optimize. Pure Python: importable inside
Blender (bpy) and outside it. Result JSON matches asset_checks so the orchestrator reads
every step the same way.

Result shape:
  {"tool": "<dir>/<script>", "tool_version", "run_at", "overall": pass|fail|info|error|skipped,
   "summary": {pass, fail, info, not_checked}, "checks": [check()...],
   "metrics": {...}, "warnings": [...], "artifacts": {name: path}, "data": {...}}
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

TOOL_VERSION = "0.3.0"
SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOLS_ROOT = os.path.join(SKILL_ROOT, "tools")


def script_argv():
    """Arguments after `--` when run as `blender -b --python x.py -- args`; else sys.argv[1:]."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def make_parser(description=""):
    return argparse.ArgumentParser(description=description)


def load_config(path=None):
    import yaml
    path = path or os.path.join(SKILL_ROOT, "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(spec_path=None, config_path=None):
    """config.yaml defaults, overridden by the task spec's optional "config" block.
    Returns (settings, spec). spec is {} when no spec path is given."""
    cfg = load_config(config_path)
    spec = {}
    if spec_path:
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        cfg = deep_merge(cfg, spec.get("config", {}))
    return cfg, spec


def spec_rel(spec_path, rel):
    """Paths inside a spec are relative to the folder holding the spec."""
    if rel is None:
        return None
    if os.path.isabs(rel):
        return rel
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(spec_path)), rel))


def file_sha256(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(name, status, value=None, threshold=None, note=None):
    """status: pass | fail | info | not_checked"""
    d = {"check": name, "status": status}
    if value is not None:
        d["value"] = value
    if threshold is not None:
        d["threshold"] = threshold
    if note:
        d["note"] = note
    return d


def write_result(path, tool, checks=None, metrics=None, warnings=None, artifacts=None,
                 data=None, overall=None, source=None, spec_path=None):
    checks = checks or []
    statuses = [c["status"] for c in checks]
    if overall is None:
        overall = "fail" if "fail" in statuses else ("pass" if "pass" in statuses else "info")
    result = {
        "tool": tool,
        "tool_version": TOOL_VERSION,
        "run_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file": source,
        "source_sha256": file_sha256(source),
        "spec": os.path.abspath(spec_path) if spec_path else None,
        "spec_sha256": file_sha256(spec_path),
        "overall": overall,
        "summary": {s: statuses.count(s) for s in ("pass", "fail", "info", "not_checked")},
        "checks": checks,
        "metrics": metrics or {},
        "warnings": warnings or [],
        "artifacts": artifacts or {},
        "data": data or {},
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"[{tool}] overall={overall} {result['summary']} -> {path}")
    return result


def write_error(path, tool, exc, source=None):
    import traceback
    return write_result(path, tool, overall="error", source=source,
                        data={"error": repr(exc), "traceback": traceback.format_exc()})


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if hasattr(o, "__iter__"):
        return list(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


def r(x, n=4):
    return round(float(x), n)
