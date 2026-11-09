"""Mesh data after modifiers: tris/verts/materials vs budget, dimensions, pivot,
loose parts, degenerate faces, non-manifold edges, inverted volume, floor gap.

Spec keys used: objects, budget.{max_tris_total, max_tris_per_object, max_materials_total,
min_tris_ratio}, dimensions_m.{<object>: [x, y, z]}, dimensions_tolerance (fraction, default 0.1),
pivot ("bottom_center" | "any"), floor_z (default 0),
expect_closed (bool: every object must be closed, i.e. no boundary or non-manifold edges),
expected_parts.{<object>: n} (loose parts; catches a failed boolean or stray pieces).

v0.2: total.budget_use = total tris / max_tris_total. With budget.min_tris_ratio set, a value
below it fails: the block-out is too coarse for the budget (rock-moss-01 used 80/1500).

v0.3 (research_notes §4, Arm/Android geometry guidance):
- exported_vertices: what the GPU gets after the glTF exporter splits vertices. Counted the way
  io_scene_gltf2 does it: unique (material, vertex index, corner normal, every UV layer) over the
  loops of the evaluated mesh, so UV seams, sharp/flat edges and material borders all split.
  vs budget.max_vertices_exported (else config budgets.max_vertices_exported, 16-bit indices).
  split_vertex_ratio = exported / raw vertices: info (note above 2x) unless mesh.max_split_vertex_ratio.
- ngons: faces with > 4 corners (the exporter triangulates them; the result is not controlled).
  info unless mesh.max_ngons.
- hidden_face_ratio: share of triangles no ray reaches from outside. Per face, the centre and
  points halfway to each corner (max 4) cast rays along 64 directions on the sphere against all
  target objects (BVH); a face is visible when one ray escapes. Two-sided: a back-facing face
  still counts as visible (flipped faces are a separate check). Estimate: a face visible only
  through a gap smaller than the sampling can read as hidden. info unless mesh.max_hidden_face_ratio.
- duplicate_verts: vertices with another vertex of the same object within
  mesh.duplicate_distance_m (default 1e-4 m). info unless mesh.max_duplicate_verts.
- flipped_faces: on each closed loose part (every edge has exactly 2 faces), a ray from just above
  the face along its normal (and a second, tilted ray) crosses the same part an odd number of times
  => the normal points inwards. Fails above 0 (same rule as inverted_parts); open parts are skipped.
- smooth_edges_over_90: smooth-shaded edges whose face normals differ by more than 90 deg (Arm:
  keep the smoothing angle under 90 deg; mark them sharp). Only when some face is smooth-shaded.
  info unless mesh.max_smooth_edges_over_90.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ac_common as ac  # noqa: E402  (imports bpy first)
import bmesh  # noqa: E402
import math  # noqa: E402
import numpy as np  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

N_DIRS = 64


def exported_vertices(me):
    """Vertices the glTF exporter writes: unique (material, vertex, corner normal, UVs) over loops,
    per material primitive (io_scene_gltf2 primitive_extract keys on vertex_index the same way).
    Returns (exported, raw used vertices)."""
    nl = len(me.loops)
    if nl == 0:
        return 0, 0
    vi = np.empty(nl, np.int64)
    me.loops.foreach_get("vertex_index", vi)
    cn = np.empty(nl * 3, np.float64)
    me.corner_normals.foreach_get("vector", cn)
    tot = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", tot)
    mi = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("material_index", mi)
    cols = [np.repeat(mi, tot).astype(np.float64)[:, None], vi.astype(np.float64)[:, None],
            np.round(cn.reshape(-1, 3), 5)]
    for layer in me.uv_layers:
        uv = np.empty(nl * 2, np.float64)
        layer.data.foreach_get("uv", uv)
        cols.append(np.round(uv.reshape(-1, 2), 6))
    rec = np.ascontiguousarray(np.concatenate(cols, axis=1))
    return int(len(np.unique(rec, axis=0))), int(len(np.unique(vi)))


def duplicate_verts(coords, dist):
    """Vertices with another vertex within dist (grid hash, no scipy needed)."""
    cell = {}
    for i, c in enumerate(coords):
        cell.setdefault((int(math.floor(c[0] / dist)), int(math.floor(c[1] / dist)),
                         int(math.floor(c[2] / dist))), []).append(i)
    dup, pairs = set(), 0
    for (x, y, z), ids in cell.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    other = cell.get((x + dx, y + dy, z + dz))
                    if not other:
                        continue
                    for i in ids:
                        for j in other:
                            if j > i and (coords[i] - coords[j]).length <= dist:
                                dup.update((i, j))
                                pairs += 1
    return len(dup), pairs


def _escapes(tree, origin, d, own, eps):
    """True when a ray from origin along d leaves without hitting a face other than own."""
    o = origin + d * eps
    for _ in range(8):
        loc, _n, idx, _dist = tree.ray_cast(o, d)
        if loc is None:
            return True
        if idx != own:
            return False
        o = loc + d * eps
    return False


def _crossings(tree, origin, d, eps):
    n, o = 0, origin + d * eps
    for _ in range(64):
        loc, _n, _i, _d = tree.ray_cast(o, d)
        if loc is None:
            break
        n += 1
        o = loc + d * eps
    return n


def hidden_faces(per_obj):
    """per_obj: {name: (coords, polys, tris_per_face, areas)} in world space.
    Returns {name: {"hidden_faces", "hidden_tris", "tris", "hidden_area_ratio"}}."""
    verts, polys, owner = [], [], []
    for name, (coords, fpolys, _t, _a) in per_obj.items():
        base = len(verts)
        verts += coords
        for i, p in enumerate(fpolys):
            polys.append([base + k for k in p])
            owner.append((name, i))
    if not polys:
        return {}
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    eps = max(1e-6, 1e-5 * math.dist(lo, hi))
    dirs = ac.fibonacci_dirs(N_DIRS)
    out = {n: {"hidden_faces": 0, "hidden_tris": 0, "tris": 0, "hidden_area": 0.0, "area": 0.0}
           for n in per_obj}
    for gi, p in enumerate(polys):
        name, li = owner[gi]
        _c, _p, tris, areas = per_obj[name]
        pts = [verts[k] for k in p]
        c = sum(pts, ac.Vector()) / len(pts)
        samples = [c] + [(c + q) / 2 for q in pts[:4]]
        vis = any(_escapes(tree, s_, d, gi, eps) for s_ in samples for d in dirs)
        o = out[name]
        o["tris"] += tris[li]
        o["area"] += areas[li]
        if not vis:
            o["hidden_faces"] += 1
            o["hidden_tris"] += tris[li]
            o["hidden_area"] += areas[li]
    for o in out.values():
        o["hidden_area_ratio"] = ac.r(o.pop("hidden_area") / (o.pop("area") or 1), 4)
    return out


def analyze(obj, dup_dist=1e-4):
    me = ac.evaluated_mesh(obj)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    coords = [v.co.copy() for v in bm.verts]
    mn = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
    mx = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)

    # loose parts + signed volume per part (negative volume => normals inverted)
    seen, parts = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        vol = 0.0
        for cf in comp:
            loops = [l.vert.co for l in cf.loops]
            for i in range(1, len(loops) - 1):
                vol += loops[0].dot(loops[i].cross(loops[i + 1])) / 6.0
        closed = all(len(e.link_faces) == 2 for cf in comp for e in cf.edges)
        parts.append({"faces": len(comp), "signed_volume_m3": ac.r(vol, 6), "closed": closed,
                      "_faces": [cf.index for cf in comp]})

    # v0.3: flipped faces by ray parity, per closed part (other parts never count)
    diag = (mx - mn).length or 1.0
    eps = max(1e-6, 1e-5 * diag)
    flipped, faces_tested = 0, 0
    for part in parts:
        ids = part.pop("_faces")
        if not part["closed"]:
            continue
        fl = [bm.faces[i] for i in ids]
        vmap = {}
        pverts, ppolys = [], []
        for f in fl:
            poly = []
            for v in f.verts:
                if v.index not in vmap:
                    vmap[v.index] = len(pverts)
                    pverts.append(v.co.copy())
                poly.append(vmap[v.index])
            ppolys.append(poly)
        tree = BVHTree.FromPolygons(pverts, ppolys, all_triangles=False, epsilon=0.0)
        n_flip = 0
        for f in fl:
            nrm = f.normal
            if nrm.length < 0.5:
                continue
            c = f.calc_center_median()
            tilt = (nrm + nrm.orthogonal().normalized() * 0.15).normalized()
            if _crossings(tree, c, nrm, eps) % 2 == 1 and _crossings(tree, c, tilt, eps) % 2 == 1:
                n_flip += 1
        part["flipped_faces"] = n_flip
        flipped += n_flip
        faces_tested += len(fl)

    # v0.3: n-gons, smooth edges over 90 deg, duplicate verts, data for the hidden-face pass
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    any_smooth = any(f.smooth for f in bm.faces)
    smooth_over_90 = 0
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2 and e.smooth and lf[0].smooth and lf[1].smooth:
            if e.calc_face_angle(0.0) > math.pi / 2:
                smooth_over_90 += 1
    vis_input = ([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces],
                 [len(f.verts) - 2 for f in bm.faces], [f.calc_area() for f in bm.faces])
    bm.free()
    exp_verts, raw_used = exported_vertices(me)
    dup_n, dup_pairs = duplicate_verts(coords, dup_dist)
    mats = [s.material.name for s in obj.material_slots if s.material]
    origin = obj.matrix_world.translation
    result = {
        "tris": tris, "verts": len(coords), "materials": mats,
        "bbox_min": [ac.r(v) for v in mn], "bbox_max": [ac.r(v) for v in mx],
        "dimensions": [ac.r(v) for v in (mx - mn)],
        "origin": [ac.r(v) for v in origin],
        "origin_offset_from_bottom_center": [ac.r(origin.x - (mn.x + mx.x) / 2),
                                             ac.r(origin.y - (mn.y + mx.y) / 2),
                                             ac.r(origin.z - mn.z)],
        "scale": [ac.r(v) for v in obj.scale],
        "degenerate_faces": degenerate, "non_manifold_edges": non_manifold,
        "boundary_edges": boundary, "loose_parts": parts,
        "exported_vertices": exp_verts, "raw_vertices_used": raw_used,
        "split_vertex_ratio": ac.r(exp_verts / raw_used, 3) if raw_used else None,
        "ngons": ngons, "uses_smooth_shading": any_smooth, "smooth_edges_over_90": smooth_over_90,
        "duplicate_verts": dup_n, "duplicate_pairs": dup_pairs,
        "flipped_faces": flipped, "faces_in_closed_parts": faces_tested,
        "materials_used": sorted({obj.material_slots[p.material_index].material.name
                                  for p in me.polygons
                                  if p.material_index < len(obj.material_slots)
                                  and obj.material_slots[p.material_index].material}),
        "_vis": vis_input,
    }
    bpy.data.meshes.remove(me)
    return result


def _limit_check(name, value, limit, note_if_info=None, extra_note=None):
    """pass/fail against an optional spec limit; info without one."""
    if limit is None:
        return ac.check(name, "info", value, note=note_if_info or extra_note)
    return ac.check(name, "pass" if value <= limit else "fail", value, limit,
                    note=ac.source_note("spec", extra=extra_note))


def v03_checks(n, d, mcfg, max_vx, vx_src):
    out = []
    ev = d["exported_vertices"]
    if max_vx is not None:
        out.append(ac.check(f"{n}.exported_vertices", "pass" if ev <= max_vx else "fail", ev, max_vx,
                            note=ac.source_note(vx_src, "budgets.max_vertices_exported",
                                                "unique (material, vertex, corner normal, UVs) as the glTF exporter splits")))
    else:
        out.append(ac.check(f"{n}.exported_vertices", "info", ev, note="no vertex limit in spec or config"))
    ratio = d["split_vertex_ratio"]
    out.append(_limit_check(f"{n}.split_vertex_ratio", ratio, mcfg.get("max_split_vertex_ratio"),
                            note_if_info=("above 2x: many UV seams / hard edges / material borders split "
                                          "vertices; check they are needed") if ratio and ratio > 2 else
                            "exported / raw vertices"))
    out.append(_limit_check(f"{n}.ngons", d["ngons"], mcfg.get("max_ngons"),
                            note_if_info="faces with >4 corners; the exporter triangulates them its own way",
                            extra_note="faces with >4 corners"))
    h = d.get("hidden")
    if h:
        ratio_h = ac.r(h["hidden_tris"] / (h["tris"] or 1), 4)
        lim = mcfg.get("max_hidden_face_ratio")
        val = {"hidden_tri_ratio": ratio_h, "hidden_tris": h["hidden_tris"],
               "hidden_faces": h["hidden_faces"], "hidden_area_ratio": h["hidden_area_ratio"]}
        note = f"ray visibility from {N_DIRS} directions against all target objects; estimate"
        if lim is None:
            out.append(ac.check(f"{n}.hidden_face_ratio", "info", val, note=note))
        else:
            out.append(ac.check(f"{n}.hidden_face_ratio", "pass" if ratio_h <= lim else "fail", val, lim,
                                note=note))
    lim = mcfg.get("max_duplicate_verts")
    note = f"vertices with another vertex within {mcfg.get('duplicate_distance_m', 1e-4)} m"
    out.append(_limit_check(f"{n}.duplicate_verts", d["duplicate_verts"], lim, note_if_info=note,
                            extra_note=note))
    if d["faces_in_closed_parts"]:
        out.append(ac.check(f"{n}.flipped_faces", "pass" if d["flipped_faces"] == 0 else "fail",
                            d["flipped_faces"], 0,
                            note=f"ray parity on closed parts ({d['faces_in_closed_parts']} faces tested)"))
    else:
        out.append(ac.check(f"{n}.flipped_faces", "not_checked", note="no closed part: ray parity needs a closed mesh"))
    if d["uses_smooth_shading"]:
        note = "smooth-shaded edges with dihedral > 90 deg (Arm: keep under 90, mark sharp)"
        out.append(_limit_check(f"{n}.smooth_edges_over_90", d["smooth_edges_over_90"],
                                mcfg.get("max_smooth_edges_over_90"), note_if_info=note, extra_note=note))
    else:
        out.append(ac.check(f"{n}.smooth_edges_over_90", "not_checked", note="all faces flat-shaded"))
    return out


def main():
    a, spec = ac.parse_args()
    budget = spec.get("budget", {})
    floor_z = spec.get("floor_z", 0.0)
    tol = spec.get("dimensions_tolerance", 0.1)
    mcfg = spec.get("mesh", {})
    dup_dist = mcfg.get("duplicate_distance_m", 1e-4)
    max_vx, vx_src = ac.threshold(budget, "max_vertices_exported", "budgets.max_vertices_exported")
    checks, data = [], {}
    all_mats = set()
    total = 0
    objs = ac.target_objects(spec)
    analysed = {o.name: analyze(o, dup_dist) for o in objs}
    vis = hidden_faces({n: d.pop("_vis") for n, d in analysed.items()})
    total_vx = 0
    for obj in objs:
        d = analysed[obj.name]
        d["hidden"] = vis.get(obj.name)
        data[obj.name] = d
        total += d["tris"]
        all_mats.update(d["materials"])
        n = obj.name
        if "max_tris_per_object" in budget:
            lim = budget["max_tris_per_object"]
            checks.append(ac.check(f"{n}.tris", "pass" if d["tris"] <= lim else "fail", d["tris"], lim))
        exp = spec.get("dimensions_m", {}).get(n)
        if exp:
            errs = [abs(g - e) / e for g, e in zip(d["dimensions"], exp) if e]
            checks.append(ac.check(f"{n}.dimensions", "pass" if errs and max(errs) <= tol else ("fail" if errs else "info"),
                                   d["dimensions"], {"expected": exp, "tolerance": tol}))
        else:
            checks.append(ac.check(f"{n}.dimensions", "info", d["dimensions"], note="no expected size in spec"))
        if spec.get("pivot") == "bottom_center":
            off = d["origin_offset_from_bottom_center"]
            ok = all(abs(v) <= 0.01 for v in off)
            checks.append(ac.check(f"{n}.pivot_bottom_center", "pass" if ok else "fail", off, "abs <= 0.01 m"))
        if any(abs(s - 1) > 1e-4 for s in d["scale"]):
            checks.append(ac.check(f"{n}.unapplied_scale", "info", d["scale"],
                                   note="object scale != 1; confirm export applies it"))
        checks.append(ac.check(f"{n}.degenerate_faces", "pass" if d["degenerate_faces"] == 0 else "fail",
                               d["degenerate_faces"], 0))
        if spec.get("expect_closed"):
            closed = d["non_manifold_edges"] == 0 and d["boundary_edges"] == 0
            checks.append(ac.check(f"{n}.closed", "pass" if closed else "fail",
                                   {"non_manifold_edges": d["non_manifold_edges"],
                                    "boundary_edges": d["boundary_edges"]}, "0 / 0"))
        else:
            checks.append(ac.check(f"{n}.non_manifold_edges", "info", d["non_manifold_edges"],
                                   note="open/intentional surfaces are allowed; review if unexpected"))
        inverted = [p for p in d["loose_parts"] if p["signed_volume_m3"] < 0 and d["boundary_edges"] == 0]
        checks.append(ac.check(f"{n}.inverted_parts", "pass" if not inverted else "fail", len(inverted), 0,
                               note="only meaningful for closed parts"))
        exp_parts = spec.get("expected_parts", {}).get(n)
        if exp_parts is not None:
            np_ = len(d["loose_parts"])
            checks.append(ac.check(f"{n}.loose_parts", "pass" if np_ == exp_parts else "fail", np_, exp_parts))
        else:
            checks.append(ac.check(f"{n}.loose_parts", "info", len(d["loose_parts"])))
        checks += v03_checks(n, d, mcfg, max_vx, vx_src)
        total_vx += d["exported_vertices"]
        gap = d["bbox_min"][2] - floor_z
        checks.append(ac.check(f"{n}.floor_gap_m", "info", ac.r(gap),
                               note="positive = floating, negative = below floor; see contact_check for support"))
    for key, suffix in (("dimensions_m", "dimensions"), ("expected_parts", "loose_parts")):
        for n in spec.get(key) or {}:
            if n not in analysed:
                checks.append(ac.spec_object_check(f"{n}.{suffix}", n, key))
    if "max_tris_total" in budget:
        lim = budget["max_tris_total"]
        checks.append(ac.check("total.tris", "pass" if total <= lim else "fail", total, lim))
        use = total / lim if lim else 0.0
        data["budget_use"] = ac.r(use, 3)
        mr = budget.get("min_tris_ratio")
        checks.append(ac.check("total.budget_use", ("pass" if use >= mr else "fail") if mr is not None else "info",
                               ac.r(use, 3), mr,
                               note="below the ratio: geometry too coarse for the budget; "
                                    "explain or refine before review" if mr is not None and use < mr else None))
    if "max_materials_total" in budget:
        lim = budget["max_materials_total"]
        checks.append(ac.check("total.materials", "pass" if len(all_mats) <= lim else "fail",
                               sorted(all_mats), lim))
    else:
        cfg_lim = ac.config_value("budgets.max_materials")
        checks.append(ac.check("total.materials", "info", sorted(all_mats), cfg_lim,
                               note=ac.source_note("config_default", "budgets.max_materials",
                                                   "info only: set budget.max_materials_total in the spec")
                               if cfg_lim is not None else "no budget.max_materials_total in spec"))
    data["total_tris"] = total
    data["total_exported_vertices"] = total_vx
    ac.write_result(a.out, "mesh_check", a.spec, checks, data)


if __name__ == "__main__":
    ac.run_main(main, "mesh_check")
