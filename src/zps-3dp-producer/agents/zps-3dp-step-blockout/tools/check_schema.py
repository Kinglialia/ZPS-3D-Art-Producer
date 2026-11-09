"""part_graph.json follows schema blockout-1 (references/part-graph.md), before graph.py reads it. Plain Python.

Usage: python3 tools/check_schema.py --work <dir> [--out <json>]
Checks: header, unique part names, fixed_params (+ _fixed_reason), required fields (a mirror_of part writes its own
material, role and tag, because the kit copies only shape fields), primitive, rotation_deg,
segments, enums, custom_fn (a `custom` part names a function of custom_lib.FUNCTIONS, D27.13), connected (every part reaches the root through attach.to / mirror_of.of:
orphans and cycles), order (parent listed earlier, as graph.py requires), mirror (a mirror_of part whose
source uses inset_into or through_axis, or whose source's parent may sit off the mirror plane: the kit
copies the source's parent, contact and depth, so gates.py crashes or fails on it).
Each check's value lists the offending parts. Writes <dir>/review/checks/schema.json.
Exit 0 pass, 1 fail, 2 error.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import custom_lib  # noqa: E402

TOOL = "blockout/check_schema"
HEADER = {"schema": "blockout-1", "units": "m", "up": "+Z", "front": "-Y"}
PRIMITIVES = {"box", "wedge", "cylinder", "custom"}
ENUMS = {"role": {"mass", "marker"}, "tag": {"base", "roof"}, "axis": {"X", "Y", "Z"}}
AXIS = {"X": 0, "Y": 1, "Z": 2}
IN_PLANE = {0: (1, 2), 1: (0, 2), 2: (0, 1)}
MIRROR_NOTE = "write these parts explicitly (own primitive, dims and attach), not as mirror_of"


def parent(p):
    att = p.get("attach")
    if not att:
        return None
    return att.get("of") if att.get("type") == "mirror_of" else att.get("to")


def is_mirror(p):
    return (p.get("attach") or {}).get("type") == "mirror_of"


def connected(parts):
    names = [p["name"] for p in parts]
    par = {p["name"]: parent(p) for p in parts}
    root = names[0] if names and par[names[0]] is None else None
    orphans, cycles = set(), set()
    for n in names:
        path, cur = [], n
        while cur != root:
            if cur in path:
                cycles.add(tuple(sorted(path[path.index(cur):])))
                break
            if cur not in par or par[cur] is None:
                break
            path.append(cur)
            cur = par[cur]
        if cur != root and not any(n in c for c in cycles):
            orphans.add(n)
    order = sorted(n for i, n in enumerate(names) if par[n] in names and names.index(par[n]) > i)
    return sorted(orphans), [list(c) for c in sorted(cycles)], order


def off_plane(name, ax, by, params, seen=()):
    """Part `name` may sit off the mirror plane on axis ax: some attach on its chain to the root moves it along ax."""
    att = (by.get(name) or {}).get("attach")
    if not att or name in seen:
        return False
    t, seen = att.get("type"), seen + (name,)
    if t == "mirror_of":
        return off_plane(att.get("of"), ax, by, params, seen)
    face, edge = (AXIS.get(str(att.get(k))[-1:]) for k in ("face", "edge"))
    if t == "flush_edge":
        moved = ax in (face, edge)
    elif t in ("center_on_face", "inset_into") and face == ax:
        moved = True
    else:
        plane = (0, 1) if t == "on_top" else IN_PLANE.get(AXIS.get(att.get("axis")) if t == "through_axis" else face, ())
        u = (list(att.get("offset_uv") or []) + [0, 0])[plane.index(ax)] if ax in plane else 0
        moved = params.get(u, u) != 0 if isinstance(u, (str, int, float)) else True
    return moved or off_plane(att.get("to"), ax, by, params, seen)


def origin(p, by, seen=()):
    """The first part on a mirror_of chain that is not a mirror: graph.py copies its parent, contact and depth."""
    if not is_mirror(p) or p.get("name") in seen:
        return p
    return origin(by.get(parent(p)) or {}, by, seen + (p.get("name"),))


def mirror_unsafe(p, by, params):
    att = origin(p, by).get("attach") or {}
    return att.get("type") in ("inset_into", "through_axis") or \
        off_plane(att.get("to"), AXIS.get(p["attach"].get("plane")), by, params)


def fields(p, by):
    if is_mirror(p):
        src = by.get(parent(p), {})
        need = ["material", "role"] + (["tag"] if "tag" in src else [])
    else:
        need = ["primitive", "material", "role"] + (["fn", "args"] if p.get("primitive") == "custom" else ["dims"])
    missing = [k for k in need if p.get(k) is None]
    if "attach" not in p:
        missing.append("attach")
    return [f"{p['name']}: {k}" for k in missing]


def segments_ok(p, params):
    s = p.get("segments")
    s = params.get(s) if isinstance(s, str) else s
    return isinstance(s, int) and 8 <= s <= 24


def run(graph):
    parts, params = graph.get("parts", []), graph.get("params") or {}
    by = {p.get("name"): p for p in parts}
    header = [k for k, v in HEADER.items() if graph.get(k) != v]
    if not re.fullmatch(r"v\d{2,}", str(graph.get("version", ""))):
        header.append("version")
    if not isinstance(params, dict) or not params:
        header.append("params")
    fixed = graph.get("fixed_params")
    fx = [f"{n}: not in params" for n in fixed or [] if n not in params]
    if not isinstance(fixed, list) or not fixed:
        fx.append("fixed_params")
    if not graph.get("_fixed_reason"):
        fx.append("_fixed_reason")
    real = [p for p in parts if not is_mirror(p)]
    names = [p.get("name") for p in parts]
    found = {
        "schema.header": header,
        "schema.names": sorted({str(n) for n in names if names.count(n) > 1}),
        "schema.fixed_params": fx,
        "schema.fields": [m for p in parts for m in fields(p, by)],
        "schema.primitive": [p["name"] for p in real if p.get("primitive") not in PRIMITIVES],
        "schema.rotation": [p["name"] for p in parts if p.get("rotation_deg", 0) not in (0, 90, 180, 270)],
        "schema.segments": [p["name"] for p in parts if "segments" in p and not segments_ok(p, params)],
        "schema.enums": [f"{p['name']}: {k}" for p in parts for k, ok in ENUMS.items() if k in p and p[k] not in ok],
        "schema.custom_fn": [f"{p['name']}: {p.get('fn')}" for p in real
                             if p.get("primitive") == "custom" and p.get("fn") not in custom_lib.FUNCTIONS],
    }
    checks = [common.check(k, "fail" if v else "pass", value=sorted(v)) for k, v in found.items()]
    orphans, cycles, order = connected(parts)
    checks.append(common.check("schema.connected", "fail" if orphans or cycles else "pass",
                               value={"orphans": orphans, "cycles": cycles}))
    checks.append(common.check("schema.order", "fail" if order else "pass", value=order))
    mirror = [p["name"] for p in parts if is_mirror(p) and mirror_unsafe(p, by, params)]
    checks.append(common.check("schema.mirror", "fail" if mirror else "pass", value=mirror,
                               note=MIRROR_NOTE if mirror else None))
    return checks, {"parts": len(parts)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--out")
    a = p.parse_args()
    out = a.out or os.path.join(a.work, "review", "checks", "schema.json")
    src = os.path.join(a.work, "part_graph.json")
    try:
        checks, data = run(common.read_json(src))
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=src)
        sys.exit(2)
    r = common.write_result(out, TOOL, checks, data=data, source=src)
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    main()
