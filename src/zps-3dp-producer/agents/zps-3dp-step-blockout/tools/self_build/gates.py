"""Per-part hard gates for the self-build loop (references/self_build.md, step 4). Pure Python.

Usage:
  python3 tools/self_build/gates.py --work <w> --part <name> [--rollout k] [--spec task/spec.json]
          [--out <json>]

Run after `assembly.py --upto <n>`; reads <w>/assembly.json and <w>/parts/*.glb (parts up to and
including --part). Thresholds come from config self_build.gates (spec "config" may override):
  contact_min_ratio, penetration_max_ratio, floater_span_ratio, bbox_tolerance;
  optional contact_dist_m (default 0.001, "within 1 mm"), inset_depth_tolerance (default 0.2),
  contact_samples (default 4000).

Gates (check names in the result JSON):
  gate1.runs         assembly ran, the part was built, its mesh is non-empty
  gate2.contact      share of surface samples on the child's attaching face that lie within
                     contact_dist_m of the parent (or inside it) >= contact_min_ratio.
                     through_axis: both ends must stick out of the parent.
                     on_top: when the parent's flat top area is under half the child's
                     footprint over the parent, the note (and a warning) suggests a flat seat.
  gate3.penetration  intersection volume / child volume <= penetration_max_ratio, summed over
                     every earlier part; inset_into: maximum penetration into the parent along
                     the face axis (extent of child ∩ parent; pointed/curved parents work)
                     within inset_depth_tolerance of `depth` (other parts still capped);
                     through_axis: the parent is exempt.
  gate4.floaters     components besides the main one with bbox edge >= floater_span_ratio x
                     object size, on the union before and after this part; fail when it grows
  gate5.health       non-manifold edges, zero-area faces, loose verts on the union (all 0)
  gate6.bbox         built extents vs the extents the dims declare, max relative deviation
                     <= bbox_tolerance (custom parts: `dims` if given, else the first 3 args)
Numbers to act on are in metrics and data (gap to parent, overlapping parts, floater boxes).
Exit 0 on pass/fail, 1 on error.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402

TOOL = "self_build/gates"
AX = "XYZ"


def contact_gate(row, child, parent, cfg):
    v, t = child
    pv, pt = parent
    att = row["attach"] or {}
    if att.get("type") == "through_axis":
        a = G.AXES[att["axis"]]
        lo, hi, plo, phi = v[:, a].min(), v[:, a].max(), pv[:, a].min(), pv[:, a].max()
        stick = float(min(plo - lo, hi - phi))
        ok = stick > cfg["contact_dist"]
        return common.check("gate2.contact", "pass" if ok else "fail", value=round(stick, 5),
                            threshold=cfg["contact_dist"],
                            note="through_axis: smaller protrusion past the parent, m"), {
            "protrusion_m": round(stick, 5)}
    import trimesh
    a, s = row["contact"]["axis"], row["contact"]["sign"]
    plane = v[:, a].min() if s > 0 else v[:, a].max()
    pts, _ = trimesh.sample.sample_surface(trimesh.Trimesh(v, t, process=False),
                                           cfg["samples"], seed=0)
    near = np.abs(pts[:, a] - plane)
    face = pts[near <= cfg["contact_dist"]]
    if len(face) < 30:
        face = pts[np.argsort(near)[:30]]
    d = G.point_mesh_distance(face, pv, pt)
    inside = G.winding_number(face, pv, pt) > 0.5
    touching = (d <= cfg["contact_dist"]) | inside
    ratio = float(touching.mean())
    gap = np.where(inside, 0.0, d)
    face_name = ("-" if s > 0 else "+") + AX[a]
    info = {"attach_face": face_name, "samples": int(len(face)),
            "gap_min_m": round(float(gap.min()), 5), "gap_median_m": round(float(np.median(gap)), 5),
            "gap_max_m": round(float(gap.max()), 5)}
    st = "pass" if ratio >= cfg["contact_min_ratio"] else "fail"
    return common.check("gate2.contact", st, value=round(ratio, 4), threshold=cfg["contact_min_ratio"],
                        note=f"child face {face_name}; median gap {info['gap_median_m']} m"), info


def inset_depth(child, parent, axis):
    """Maximum penetration of the child into the parent along the face-normal axis: the extent of
    child ∩ parent along that axis. Works for pointed or curved parents, where intersection volume
    / child cross-section underestimates the depth. None when a mesh is not a closed manifold."""
    import manifold3d as m3d
    ma, mb = G.to_manifold(*child), G.to_manifold(*parent)
    if ma.status() != m3d.Error.NoError or mb.status() != m3d.Error.NoError:
        return None
    inter = ma ^ mb
    if inter.is_empty():
        return 0.0
    iv, _ = G.from_manifold(inter)
    return float(iv[:, axis].max() - iv[:, axis].min())


def top_seat(child, parent, cfg):
    """on_top on a parent whose top is not flat: flat parent area at its top (normal +Z, within
    contact_dist of the top) vs the child's footprint where it overlaps the parent's."""
    pv, pt = parent
    v, _ = child
    tri = pv[pt]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cr, axis=1) / 2
    nz = cr[:, 2] / np.maximum(2 * area, 1e-30)
    top = pv[:, 2].max()
    flat = (nz > 0.999) & (np.abs(tri[:, :, 2] - top).max(axis=1) <= cfg["contact_dist"])
    # the seat can only be as large as the overlap of the two footprints (a roof wider than its
    # lamp is still seated on a flat top)
    ov = np.minimum(v[:, :2].max(0), pv[:, :2].max(0)) - np.maximum(v[:, :2].min(0), pv[:, :2].min(0))
    foot = float(np.prod(np.clip(ov, 0, None)))
    return float(area[flat].sum()), foot


def penetration_gate(row, child, earlier, rows, cfg):
    att = row["attach"] or {}
    typ = att.get("type")
    cvol = G.volume(*child)
    if cvol <= 0:
        return common.check("gate3.penetration", "fail", note="child volume is 0 or mesh not closed"), {}
    overlaps, total_other, parent_ratio = [], 0.0, 0.0
    for r, mesh in zip(rows, earlier):
        iv = G.intersection_volume(child, mesh)
        if iv is None:
            overlaps.append({"part": r["name"], "ratio": None, "note": "not a closed manifold"})
            continue
        ratio = iv / cvol
        if r["name"] == row["parent"]:
            parent_ratio = ratio
        else:
            total_other += ratio
        if ratio > 1e-6:
            overlaps.append({"part": r["name"], "ratio": round(ratio, 5),
                             "volume_m3": round(iv, 8)})
    info = {"child_volume_m3": round(cvol, 8), "parent_ratio": round(parent_ratio, 5),
            "other_parts_ratio": round(total_other, 5), "overlaps": overlaps}
    lim = cfg["penetration_max_ratio"]
    if typ == "inset_into":
        a = row["contact"]["axis"]
        parent = earlier[[r["name"] for r in rows].index(row["parent"])]
        measured = inset_depth(child, parent, a)
        want = row["depth"]
        if measured is None:
            return common.check("gate3.penetration", "fail", note="inset_into: child or parent not a closed "
                                "manifold; depth not measurable"), info
        dev = abs(measured - want) / want if want else float("inf")
        info.update({"inset_depth_m": round(measured, 5), "declared_depth_m": want,
                     "inset_depth_dev": round(dev, 4)})
        ok = dev <= cfg["inset_tol"] and total_other <= lim
        return common.check("gate3.penetration", "pass" if ok else "fail", value=round(dev, 4),
                            threshold=cfg["inset_tol"],
                            note=f"inset_into: max penetration along {AX[a]} {measured:.4f} m vs {want} m; "
                                 f"other parts ratio {total_other:.4f} (max {lim})"), info
    if typ == "through_axis":
        ratio = total_other
        note = "through_axis: parent exempt; other parts only"
    else:
        ratio = parent_ratio + total_other
        note = None
    info["penetration_ratio"] = round(ratio, 5)
    return common.check("gate3.penetration", "pass" if ratio <= lim else "fail",
                        value=round(ratio, 5), threshold=lim, note=note), info


def bbox_gate(row, tol):
    dec = row.get("declared")
    if not dec:
        return common.check("gate6.bbox", "not_checked",
                            note="no declared extents (custom part without dims and < 3 args)"), {}
    built = np.array(row["extents"])
    dec = np.array(dec, float)
    dev = np.abs(built - dec) / np.maximum(dec, 1e-9)
    info = {"built": built.round(5).tolist(), "declared": dec.round(5).tolist(),
            "deviation_per_axis": dev.round(4).tolist()}
    worst = float(dev.max())
    return common.check("gate6.bbox", "pass" if worst <= tol else "fail", value=round(worst, 4),
                        threshold=tol, note=f"worst axis {AX[int(dev.argmax())]}"), info


def run(gdir, part, settings):
    g = settings["self_build"]["gates"]
    cfg = {"contact_min_ratio": g["contact_min_ratio"], "penetration_max_ratio": g["penetration_max_ratio"],
           "floater_span_ratio": g["floater_span_ratio"], "bbox_tolerance": g["bbox_tolerance"],
           "contact_dist": g.get("contact_dist_m", 0.001), "inset_tol": g.get("inset_depth_tolerance", 0.2),
           "samples": int(g.get("contact_samples", 4000))}
    checks, metrics, warnings, data = [], {}, [], {"part": part, "thresholds": cfg}
    apath = os.path.join(gdir, "assembly.json")
    if not os.path.isfile(apath):
        checks.append(common.check("gate1.runs", "fail", note="no assembly.json; run assembly.py --upto first"))
        return checks, metrics, warnings, data
    asm = common.read_json(apath)
    if asm.get("overall") == "error":
        checks.append(common.check("gate1.runs", "fail", note=asm["data"].get("error")))
        data["traceback"] = asm["data"].get("traceback")
        return checks, metrics, warnings, data
    rows = asm["data"]["parts"]
    names = [r["name"] for r in rows]
    if part not in names:
        checks.append(common.check("gate1.runs", "fail",
                                   note=f"'{part}' not in the last build ({names}); run assembly.py --upto {part}"))
        return checks, metrics, warnings, data
    if asm["data"].get("code_hash") != G.code_hash(gdir):
        warnings.append("part_graph.json/parts_lib.py changed since assembly.json was written; rebuild first")
    i = names.index(part)
    row = rows[i]
    meshes = []
    for r in rows[:i + 1]:
        v, t, _ = G.load_glb(r["glb"])
        v, t = G.weld(v, t)
        meshes.append((v, t))
    child = meshes[i]
    ok = len(child[1]) > 0
    checks.append(common.check("gate1.runs", "pass" if ok else "fail", value=int(len(child[1])),
                               note=None if ok else "empty mesh"))
    if not ok:
        return checks, metrics, warnings, data
    if not row.get("manifold", True):
        warnings.append(f"{part} is not a closed manifold; volume-based gates may be off")
    data["part_index"] = row["index"]
    data["attach"] = row["attach"]

    # gate 2 and 3 need a parent
    if row["parent"] is None:
        checks.append(common.check("gate2.contact", "not_checked", note="root part"))
        checks.append(common.check("gate3.penetration", "not_checked", note="root part"))
    else:
        parent = meshes[names.index(row["parent"])]
        c, info = contact_gate(row, child, parent, cfg)
        if (row["attach"] or {}).get("type") == "on_top":
            flat, foot = top_seat(child, parent, cfg)
            info.update({"parent_top_flat_m2": round(flat, 6), "child_footprint_m2": round(foot, 6)})
            if foot > 0 and flat < 0.5 * foot:
                seat = (f"parent '{row['parent']}' top is not flat: flat area at its top {flat:.5f} m2 vs "
                        f"{foot:.5f} m2 of child footprint over the parent. on_top seats on the parent's bbox top; give the parent a flat "
                        f"seat (e.g. truncate it to a cap >= the child footprint) or use inset_into with a depth")
                c["note"] = f"{c.get('note')}; {seat}" if c.get("note") else seat
                warnings.append(seat)
        checks.append(c)
        data["contact"] = info
        metrics["contact_ratio"] = c.get("value")
        c, info = penetration_gate(row, child, meshes[:i], rows[:i], cfg)
        checks.append(c)
        data["penetration"] = info
        if "inset_depth_dev" in info:
            metrics["inset_depth_dev"] = info["inset_depth_dev"]
            metrics["penetration_ratio_other_parts"] = info["other_parts_ratio"]
        else:
            metrics["penetration_ratio"] = info.get("penetration_ratio")

    # gate 4 floaters before / after, gate 5 health on the union after
    before_n, after_n, after_list, method = 0, 0, [], "manifold3d"
    if i > 0:
        bv, bt, method_b, _ = G.union(meshes[:i])
        before_n, _ = G.floaters(bv, bt, cfg["floater_span_ratio"])
    uv, ut, method, bad = G.union(meshes)
    after_n, after_list = G.floaters(uv, ut, cfg["floater_span_ratio"])
    if bad:
        warnings.append("union fell back to a plain join (non-manifold part): floater count counts parts")
    checks.append(common.check("gate4.floaters", "fail" if after_n > before_n else "pass",
                               value=after_n, threshold=before_n,
                               note=f"before {before_n}, after {after_n}"))
    metrics.update({"floaters_before": before_n, "floaters_after": after_n})
    data["floaters"] = after_list
    h = G.health(uv, ut)
    bad_h = h["non_manifold_edges"] + h["zero_area_faces"] + h["loose_verts"]
    checks.append(common.check("gate5.health", "pass" if bad_h == 0 and method == "manifold3d" else "fail",
                               value=bad_h, threshold=0,
                               note=f"non_manifold_edges {h['non_manifold_edges']}, zero_area {h['zero_area_faces']}, "
                                    f"loose_verts {h['loose_verts']}, union {method}"))
    metrics["non_manifold_edges"] = h["non_manifold_edges"]
    data["health"] = h

    c, info = bbox_gate(row, cfg["bbox_tolerance"])
    checks.append(c)
    data["bbox"] = info
    metrics["bbox_deviation"] = c.get("value")
    return checks, metrics, warnings, data


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--part", required=True)
    p.add_argument("--rollout")
    p.add_argument("--spec")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    gdir = G.graph_dir(a.work, a.rollout)
    out = a.out or os.path.join(gdir, "gates", f"{a.part}.json")
    try:
        settings, _ = common.load_settings(a.spec)
        checks, metrics, warnings, data = run(gdir, a.part, settings)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=os.path.join(gdir, "assembly.json"))
        sys.exit(1)
    common.write_result(out, TOOL, checks, metrics, warnings, data=data,
                        source=os.path.join(gdir, "assembly.json"), spec_path=a.spec)


if __name__ == "__main__":
    main()
