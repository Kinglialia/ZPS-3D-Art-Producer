"""UV checks on the evaluated mesh: islands, out-of-bounds, overlap, padding between
islands at the texture resolution, and texel density per view region.

Regions are classified by face normal relative to the game camera azimuth:
top (n.z >= 0.6), bottom (n.z <= -0.6), else front / side / back by the horizontal
normal dotted with the direction toward the camera (>= 0.3 front, <= -0.3 back).

Spec keys used: objects, camera.azimuth_deg (0 = camera on -Y looking +Y),
uv.{resolution, min_padding_px, allow_overlap, allow_out_of_bounds,
    density_min_px_per_m: {region: value}, density_ratio_min: {region: ratio vs whole asset}}.
Raster measurements are accurate to about 1 px.
Resolution: the largest image-texture node on the object's materials when there is one, else
uv.resolution; data.<obj>.resolution_source and the padding/density notes say which.

v0.3:
- min_padding_px: when the spec omits it, the threshold comes from config
  texture.padding_px_by_res at uv.resolution (scaled from the nearest entry when the resolution
  is not listed) and the check note says `source: config_default`.
- texel density in px/m: global (sqrt(UV px area / world area)) and per UV island (min, max,
  max/min). With uv.texel_density_px_per_m and uv.density_tolerance (fraction, e.g. 0.2 = ±20 %)
  the global value and every island holding >= 0.5 % of the world area must be inside the band.
  Without them: info.
- hard_edges_without_uv_split: a hard edge (sharp-marked or next to a flat-shaded face, with the
  face normals more than 1 deg apart) whose two faces share UVs. A normal map baked across it
  shows a seam/gradient (Arm/Android: split UVs at hard edges). style "pbr": fails above 0;
  "hand_painted" or no style: info. UV split is read from the UV coordinates, not the seam flag.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import numpy as np  # noqa: E402

import ac_common as ac  # noqa: E402  (imports bpy first)
import bmesh  # noqa: E402

REGIONS = ("top", "front", "side", "back", "bottom")


def region_of(n, cam_dir):
    if n.z >= 0.6:
        return "top"
    if n.z <= -0.6:
        return "bottom"
    h = math.hypot(n.x, n.y) or 1.0
    d = (n.x * cam_dir[0] + n.y * cam_dir[1]) / h
    return "front" if d >= 0.3 else ("back" if d <= -0.3 else "side")


def islands(bm, uv):
    """Island id per face (1-based) and the set of edge indices where the UVs split."""
    parent = list(range(len(bm.faces)))
    split = set()

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:
            continue
        uvs = []
        for f in lf:
            m = {l.vert.index: l[uv].uv.copy() for l in f.loops}
            uvs.append((m[e.verts[0].index], m[e.verts[1].index]))
        if (uvs[0][0] - uvs[1][0]).length < 1e-5 and (uvs[0][1] - uvs[1][1]).length < 1e-5:
            parent[find(lf[0].index)] = find(lf[1].index)
        else:
            split.add(e.index)
    roots = {}
    return [roots.setdefault(find(f.index), len(roots) + 1) for f in bm.faces], split


def hard_edges(bm, min_angle=math.radians(1.0)):
    """Manifold edges where the shading normal breaks: sharp-marked or a flat face, and the
    faces are not coplanar."""
    out = []
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:
            continue
        if e.smooth and lf[0].smooth and lf[1].smooth:
            continue
        if e.calc_face_angle(0.0) > min_angle:
            out.append(e.index)
    return out


def padding_threshold(cfg, res):
    """(min_padding_px, source, note) from the spec, else config texture.padding_px_by_res."""
    if cfg.get("min_padding_px") is not None:
        return cfg["min_padding_px"], "spec", None
    table = ac.config_value("texture.padding_px_by_res") or {}
    table = {int(k): v for k, v in table.items()}
    if not table:
        return None, None, None
    if res in table:
        return table[res], "config_default", f"texture.padding_px_by_res[{res}]"
    k = min(table, key=lambda t: abs(math.log2(t / res)))
    return max(1, round(table[k] * res / k)), "config_default", \
        f"texture.padding_px_by_res scaled from {k} px ({table[k]} px) to {res} px"


def texture_resolution(obj, spec_res):
    """(resolution, source): the largest image-texture node on the object's materials, else the
    spec uv.resolution. Texel density and padding are only meaningful at the real texture size."""
    best, names = 0, []
    for slot in obj.material_slots:
        m = slot.material
        if not (m and m.node_tree):
            continue
        for nd in m.node_tree.nodes:
            if nd.type == "TEX_IMAGE" and nd.image is not None:
                w, h = nd.image.size[:]
                if max(w, h) > best:
                    best = max(w, h)
                if max(w, h) > 0:
                    names.append(f"{nd.image.name} {w}x{h}")
    if best > 0:
        return best, f"image texture ({', '.join(sorted(set(names)))}; largest {best} px)"
    return spec_res, f"spec uv.resolution {spec_res} px (no image texture on the material)"


def raster(tris, res):
    """tris: list of (island_id, face_id, [(u,v)x3]). Returns island label map and overlap counts."""
    lab = np.zeros((res, res), np.int32)
    fid = np.full((res, res), -1, np.int32)
    cross = self_ov = 0
    for isl, face, pts in tris:
        p = np.array(pts) * res - 0.5
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        (ax, ay), (bx, by), (cx, cy) = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        w1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        inside = (w0 > 0) & (w1 > 0) & (1 - w0 - w1 > 0)
        if not inside.any():
            continue
        sub_l = lab[y0:y1 + 1, x0:x1 + 1]
        sub_f = fid[y0:y1 + 1, x0:x1 + 1]
        cross += int(((sub_l != 0) & (sub_l != isl) & inside).sum())
        self_ov += int(((sub_l == isl) & (sub_f != face) & (sub_f >= 0) & inside).sum())
        sub_l[inside & (sub_l == 0)] = isl
        sub_f[inside & (sub_f == -1)] = face
    return lab, cross, self_ov


def min_island_gap(lab, radius):
    res = lab.shape[0]
    best = None
    offs = sorted({(dx, dy) for dx in range(0, radius + 1) for dy in range(-radius, radius + 1)
                   if (dx, dy) != (0, 0) and not (dx == 0 and dy < 0) and dx * dx + dy * dy <= radius * radius},
                  key=lambda o: o[0] ** 2 + o[1] ** 2)
    for dx, dy in offs:
        d = math.hypot(dx, dy)
        if best is not None and d >= best:
            break
        y0, y1 = max(0, -dy), res - max(0, dy)
        a = lab[y0:y1, 0:res - dx]
        b = lab[y0 + dy:y1 + dy, dx:res]
        if ((a > 0) & (b > 0) & (a != b)).any():
            best = d
    return best  # pixels between centres of nearest different-island pixels; None = > radius


def main():
    a, spec = ac.parse_args()
    cfg = spec.get("uv", {})
    spec_res = int(cfg.get("resolution", 1024))
    az = math.radians(spec.get("camera", {}).get("azimuth_deg", 0.0))
    cam_dir = (math.sin(az), -math.cos(az))
    style = spec.get("style")
    td_target, td_tol = cfg.get("texel_density_px_per_m"), cfg.get("density_tolerance")
    checks, data = [], {}
    for obj in ac.target_objects(spec):
        n = obj.name
        res, res_src = texture_resolution(obj, spec_res)
        min_pad, pad_src, pad_key = padding_threshold(cfg, res)
        me = ac.evaluated_mesh(obj)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        uv = bm.loops.layers.uv.active
        if uv is None:
            checks.append(ac.check(f"{n}.uv_layer", "fail", 0, ">=1"))
            bm.free()
            continue
        isl, uv_split = islands(bm, uv)
        hard = hard_edges(bm)
        hard_unsplit = [i for i in hard if i not in uv_split]
        isl_world, isl_px = {}, {}
        reg_world = dict.fromkeys(REGIONS, 0.0)
        reg_uvpx = dict.fromkeys(REGIONS, 0.0)
        oob, tris = 0, []
        for f in bm.faces:
            uvs = [l[uv].uv.copy() for l in f.loops]
            if any(c < -1e-5 or c > 1 + 1e-5 for p in uvs for c in p):
                oob += 1
            uv_area = 0.0
            for i in range(1, len(uvs) - 1):
                tri = [uvs[0], uvs[i], uvs[i + 1]]
                uv_area += abs((tri[1] - tri[0]).cross(tri[2] - tri[0])) / 2
                tris.append((isl[f.index], f.index, [tuple(t) for t in tri]))
            rg = region_of(f.normal, cam_dir)
            fa = f.calc_area()
            isl_world[isl[f.index]] = isl_world.get(isl[f.index], 0.0) + fa
            isl_px[isl[f.index]] = isl_px.get(isl[f.index], 0.0) + uv_area * res * res
            reg_world[rg] += fa
            reg_uvpx[rg] += uv_area * res * res
        lab, cross, self_ov = raster(tris, res)
        occupancy = float((lab > 0).mean())
        gap = min_island_gap(lab, int(max(16, (min_pad or 0) + 2)))
        tot_w, tot_px = sum(reg_world.values()), sum(reg_uvpx.values())
        overall = math.sqrt(tot_px / tot_w) if tot_w else 0
        dens = {g: ac.r(math.sqrt(reg_uvpx[g] / reg_world[g]), 1) for g in REGIONS if reg_world[g] > 1e-9}
        data[n] = {
            "uv_layers": len(obj.data.uv_layers), "islands": max(isl) if isl else 0,
            "faces_out_of_bounds": oob, "cross_island_overlap_px": cross, "self_overlap_px": self_ov,
            "occupancy": ac.r(occupancy), "min_island_gap_px": gap,
            "density_px_per_m": {"overall": ac.r(overall, 1), **dens},
            "region_world_area_m2": {g: ac.r(v) for g, v in reg_world.items() if v},
            "resolution": res, "resolution_source": res_src, "spec_resolution": spec_res,
            "hard_edges": len(hard), "hard_edges_without_uv_split": len(hard_unsplit),
            "uv_split_edges": len(uv_split),
        }
        # per-island texel density (islands under 0.5 % of the world area are listed, not checked)
        isl_d = {i: math.sqrt(isl_px[i] / w) for i, w in isl_world.items() if w > 1e-12}
        big = {i: d for i, d in isl_d.items() if isl_world[i] >= 0.005 * tot_w}
        data[n]["island_density_px_per_m"] = {
            "min": ac.r(min(big.values()), 1) if big else None,
            "max": ac.r(max(big.values()), 1) if big else None,
            "max_over_min": ac.r(max(big.values()) / min(big.values()), 3) if big and min(big.values()) > 0 else None,
            "islands_checked": len(big), "islands_small": len(isl_d) - len(big),
            "per_island": {str(i): {"px_per_m": ac.r(d, 1), "world_m2": ac.r(isl_world[i], 5)}
                           for i, d in sorted(isl_d.items())[:200]},
        }
        bm.free()
        ac.bpy.data.meshes.remove(me)
        allow_oob = cfg.get("allow_out_of_bounds", False)
        checks.append(ac.check(f"{n}.out_of_bounds_faces", "info" if allow_oob else ("pass" if oob == 0 else "fail"),
                               oob, None if allow_oob else 0))
        allow_ov = cfg.get("allow_overlap", False)
        ov = cross + self_ov
        checks.append(ac.check(f"{n}.overlap_px", "info" if allow_ov else ("pass" if ov == 0 else "fail"), ov,
                               None if allow_ov else 0, note="mirror/stack is fine only if intended"))
        if min_pad is not None:
            ok = gap is None or gap >= min_pad
            checks.append(ac.check(f"{n}.min_island_gap_px", "pass" if ok else "fail",
                                   gap if gap is not None else f">{max(16, min_pad + 2)}", min_pad,
                                   note=ac.source_note(pad_src, pad_key, f"at {res_src}")))
        else:
            checks.append(ac.check(f"{n}.min_island_gap_px", "info", gap,
                                   note="no min_padding_px in spec and no config table"))
        # texel density vs target
        idd = data[n]["island_density_px_per_m"]
        dval = {"global": ac.r(overall, 1), "island_min": idd["min"], "island_max": idd["max"],
                "island_max_over_min": idd["max_over_min"]}
        if td_target is not None and td_tol is not None:
            lo_b, hi_b = td_target * (1 - td_tol), td_target * (1 + td_tol)
            band = {"target_px_per_m": td_target, "tolerance": td_tol, "band": [ac.r(lo_b, 1), ac.r(hi_b, 1)]}
            checks.append(ac.check(f"{n}.texel_density.global", "pass" if lo_b <= overall <= hi_b else "fail",
                                   ac.r(overall, 1), band, note=f"measured at {res_src}"))
            outside = sorted(int(i) for i, d in big.items() if not lo_b <= d <= hi_b)
            checks.append(ac.check(f"{n}.texel_density.islands", "pass" if not outside else "fail",
                                   {**dval, "islands_outside": len(outside), "outside_ids": outside[:20]}, band,
                                   note=f"{idd['islands_checked']} islands >= 0.5 % of the area checked; "
                                        f"measured at {res_src}"))
        else:
            ref = ac.config_value("texture.texel_density_px_per_m")
            checks.append(ac.check(f"{n}.texel_density", "info", dval,
                                   note=f"measured at {res_src}; "
                                        "no uv.texel_density_px_per_m + uv.density_tolerance in spec"
                                        + (f"; config texture.texel_density_px_per_m = {ref} (reference only)"
                                           if ref is not None else "")))
        # hard edges must be UV splits (normal-map bake)
        hv = {"hard_edges": len(hard), "without_uv_split": len(hard_unsplit)}
        if style == "pbr":
            checks.append(ac.check(f"{n}.hard_edges_without_uv_split", "pass" if not hard_unsplit else "fail",
                                   hv, 0, note="style pbr: every hard edge must be a UV split"))
        else:
            checks.append(ac.check(f"{n}.hard_edges_without_uv_split", "info", hv,
                                   note=f"style {style or 'not set'}: rule applies to pbr (normal-map bake)"))
        checks.append(ac.check(f"{n}.occupancy", "info", ac.r(occupancy)))
        for g, mn in cfg.get("density_min_px_per_m", {}).items():
            if g in dens:
                checks.append(ac.check(f"{n}.density.{g}", "pass" if dens[g] >= mn else "fail", dens[g], mn))
            else:
                checks.append(ac.check(f"{n}.density.{g}", "not_checked", note="region has no faces"))
        for g, ratio in cfg.get("density_ratio_min", {}).items():
            if g in dens and overall:
                rv = ac.r(dens[g] / overall, 3)
                checks.append(ac.check(f"{n}.density_ratio.{g}", "pass" if rv >= ratio else "fail", rv, ratio))
        checks.append(ac.check(f"{n}.density", "info", data[n]["density_px_per_m"]))
    ac.write_result(a.out, "uv_check", a.spec, checks, data)


if __name__ == "__main__":
    ac.run_main(main, "uv_check")
