"""Detail pass numbers (docs/agents/3d-artist.md §4, D7.8). Plain Python on the GLB files.

Usage: python3 tools/check_detail.py --final F --blockout B --pilot <dir|none> [--before-join]
  detail.more_tris   tris of the part build F/parts/*.glb > tris of B/parts/*.glb (parts of assembly.json); else fail.
                     Part builds on both sides: the blockout union retriangulates every contact and the join drops
                     hidden faces, so neither is a fair count of what the detail pass added
  detail.bbox        every axis of the union bbox of F/assembly.json within spec dimensions_tolerance (2 %) of the
                     one of B/assembly.json: the detail pass stays inside the approved blockout
  detail.fixed_params  every name of B/part_graph.json fixed_params is still in F/part_graph.json fixed_params with
                     the same value; value lists each change
  detail.cap         tris of F/<id>-untextured.glb <= spec budget.max_tris_total (the tier cap of make_spec.py)
  detail.density     tris of the GLB per m2 of its surface: info, for check-clay
  detail.vs_pilot    density / density of the first GLB under --pilot (brief line PILOT): info, the reviewer judges
                     a ratio outside 0.5-2; PILOT none or no GLB there: not_checked (D21.7)
--before-join: right after a build, before join_mesh.py: only the three part checks, to
F/review/checks/detail_build.json, so the full run after unwrap still writes detail.json with every check.
Writes F/review/checks/detail.json. Exit 0 pass, 1 fail, 2 error.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import cli  # noqa: E402
import common  # noqa: E402
import glbread  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/check_detail"


def args(p):
    p.add_argument("--blockout", required=True)
    p.add_argument("--pilot", required=True)
    p.add_argument("--before-join", action="store_true")


def density(path):
    g = glbread.load(path)
    a = glbread.area(g["v"], g["f"])
    return len(g["f"]), a, len(g["f"]) / a


def assembly(d):
    return common.read_json(os.path.join(d, "assembly.json"))["data"]


def part_tris(d):
    return sum(len(glbread.load(os.path.join(d, "parts", f"{r['name']}.glb"))["f"]) for r in assembly(d)["parts"])


def fixed_changes(blockout, final):
    b, f = (common.read_json(os.path.join(d, "part_graph.json")) for d in (blockout, final))
    out = []
    for k in b.get("fixed_params", []):
        if k not in f.get("fixed_params", []):
            out.append(f"{k}: bỏ khỏi fixed_params")
        elif f["params"].get(k) != b["params"].get(k):
            out.append(f"{k}: {b['params'].get(k)} → {f['params'].get(k)}")
    return out


def part_checks(a, spec):
    before, built = part_tris(a.blockout), part_tris(a.final)
    tol = spec["dimensions_tolerance"]
    bb, fb = (assembly(d)["union"]["extents"] for d in (a.blockout, a.final))
    ratio = [common.r(x / y, 4) for x, y in zip(fb, bb)]
    moved = fixed_changes(a.blockout, a.final)
    checks = [common.check("detail.more_tris", "pass" if built > before else "fail", built, before,
                           note="tris part build phải lớn hơn tris part blockout"),
              common.check("detail.bbox", "pass" if all(abs(x - 1) <= tol + 1e-9 for x in ratio) else "fail",
                           [common.r(x, 4) for x in fb], [common.r(x, 4) for x in bb],
                           note=f"bbox x, y, z so với blockout: tỉ lệ {ratio}, cho phép ±{tol:.0%}"),
              common.check("detail.fixed_params", "fail" if moved else "pass", moved,
                           note="fixed_params của blockout không được đổi")]
    return checks, {"blockout_part_tris": before, "part_tris": built, "bbox_ratio": ratio}


def check(a):
    spec = common.read_json(os.path.join(a.final, "spec.json"))
    checks, data = part_checks(a, spec)
    if a.before_join:
        return checks, data
    tris, area, dens = density(os.path.join(a.final, f"{spec['asset']}-untextured.glb"))
    cap = spec["budget"]["max_tris_total"]
    data |= {"tris": tris, "cap": cap, "area_m2": common.r(area, 2), "tris_per_m2": common.r(dens, 2),
             "cap_source": spec.get("sources", {}).get("tris_cap")}
    checks += [common.check("detail.cap", "pass" if tris <= cap else "fail", tris, cap),
               common.check("detail.density", "info", common.r(dens, 2), note="tris/m² bề mặt")]
    pilot = sorted(glob.glob(os.path.join(a.pilot, "**", "*.glb"), recursive=True)) if a.pilot != "none" else []
    if pilot:
        _, _, pd = density(pilot[0])
        data["pilot"] = {"glb": pilot[0], "tris_per_m2": common.r(pd, 2), "ratio": common.r(dens / pd, 3)}
        checks.append(common.check("detail.vs_pilot", "info", data["pilot"]["ratio"],
                                   note="tris/m² so với pilot; lệch quá 2 lần cần lý do"))
    else:
        checks.append(common.check("detail.vs_pilot", "not_checked",
                                   note="chưa có pilot" if a.pilot == "none" else f"không có GLB trong {a.pilot}"))
    return checks, data


if __name__ == "__main__":
    require_root()
    cli.run(TOOL, "detail", __doc__, args, check, glb=True)
