"""UV islands keep the padding to the atlas border and the texel minimum (docs/agents/3d-artist.md §6). Plain Python.

Usage: python3 tools/check_uv_edge.py --final F
  uv.present          F/<id>-untextured.glb has TEXCOORD_0 on every primitive
  uv.edge_margin_px   smallest distance of a UV corner to the atlas border, px at spec uv.resolution, >= uv.min_padding_px
  uv.texel_px_per_m   sqrt(UV area in px / surface m2) of the whole mesh >= spec model.texel_min_px_per_m
  uv.texel_islands    the same for every UV piece with >= 0.5 % of the surface (a piece: triangles that share a vertex
                      of the file, so a sharp edge may split an island into two pieces); no such piece (a faceted
                      mesh): every piece
  uv.stretch          share of the surface (world area) whose triangles map UV to the mesh with a ratio of the two
                      singular values of the Jacobian above spec model.uv_stretch.max_ratio: a circle painted in UV
                      becomes an ellipse that much longer than wide. A triangle of zero UV area counts as stretched.
                      Fails above model.uv_stretch.max_share; no limits in the spec: not_checked
The kit uv_check measures the gaps between islands, not the gap to the border.
data.at_<res> and data.at_1024 give the same numbers at the working resolution and at 1024 (scaled).
Writes F/review/checks/uv_edge.json. Exit 0 pass, 1 fail, 2 error.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import cli  # noqa: E402
import common  # noqa: E402
import glbread  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/check_uv_edge"
ISLAND_MIN_SHARE = 0.005


def pieces(f, nv):
    parent = list(range(nv))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in f.tolist():
        for y in (b, c):
            ra, ry = root(a), root(y)
            if ra != ry:
                parent[ry] = ra
    return np.array([root(a) for a in f[:, 0].tolist()])


def numbers(g, res):
    f, uv = g["f"], g["uv"]
    t, tu = g["v"][f], uv[f]
    world = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2
    e1, e2 = tu[:, 1] - tu[:, 0], tu[:, 2] - tu[:, 0]
    uva = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    used = uv[np.unique(f)]
    margin = float(np.minimum(used, 1 - used).min()) * res
    lab = pieces(f, len(uv))
    every = np.unique(lab)
    big = [k for k in every if world[lab == k].sum() >= ISLAND_MIN_SHARE * world.sum()]
    faceted = not big
    isl = [float(np.sqrt(uva[lab == k].sum() / world[lab == k].sum())) * res for k in (every if faceted else big)]
    return {"edge_margin_px": common.r(margin, 2), "texel_px_per_m": common.r(np.sqrt(uva.sum() / world.sum()) * res, 1),
            "island_texel_min": common.r(min(isl), 1), "islands_checked": len(isl), "faceted": faceted}


def stretch(g):
    """Per triangle: (ratio of the singular values of the UV -> world Jacobian, world area); inf for zero UV area."""
    f = g["f"]
    t, tu = g["v"][f], g["uv"][f]
    e = np.stack([t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]], axis=2)
    u = np.stack([tu[:, 1] - tu[:, 0], tu[:, 2] - tu[:, 0]], axis=2)
    world = np.linalg.norm(np.cross(e[:, :, 0], e[:, :, 1]), axis=1) / 2
    det = u[:, 0, 0] * u[:, 1, 1] - u[:, 0, 1] * u[:, 1, 0]
    ok = np.abs(det) > 1e-12
    ratio = np.full(len(f), np.inf)
    s = np.linalg.svd(e[ok] @ np.linalg.inv(u[ok]), compute_uv=False)
    ratio[ok] = s[:, 0] / np.maximum(s[:, 1], 1e-12)
    return ratio, world


def stretch_check(g, lim):
    if not lim:
        return common.check("uv.stretch", "not_checked", note="spec.json chưa có model.uv_stretch: chạy lại make_spec.py")
    ratio, world = stretch(g)
    share = float(world[ratio > lim["max_ratio"]].sum() / world.sum())
    return common.check("uv.stretch", "pass" if share <= lim["max_share"] else "fail", common.r(share, 4),
                        lim["max_share"], note=f"phần diện tích có tỉ lệ kéo giãn > {lim['max_ratio']} (ngưỡng tạm)")


def check(a):
    spec = common.read_json(os.path.join(a.final, "spec.json"))
    g = glbread.load(os.path.join(a.final, f"{spec['asset']}-untextured.glb"))
    if g["uv"] is None:
        return [common.check("uv.present", "fail", note="GLB không có TEXCOORD_0")], {}
    res, pad, tmin = spec["uv"]["resolution"], spec["uv"]["min_padding_px"], spec["model"]["texel_min_px_per_m"]
    at = numbers(g, res)
    scale = 1024 / res
    at1024 = {"edge_margin_px": common.r(at["edge_margin_px"] * scale, 2),
              "texel_px_per_m": common.r(at["texel_px_per_m"] * scale, 1),
              "island_texel_min": common.r(at["island_texel_min"] * scale, 1),
              "min_padding_px": common.r(pad * scale, 1), "texel_min_px_per_m": common.r(tmin * scale, 1)}
    pieces_note = ", không mảnh nào ≥ 0,5 % diện tích: đo mọi mảnh" if at["faceted"] else " ≥ 0,5 % diện tích"
    checks = [common.check("uv.present", "pass", True),
              common.check("uv.edge_margin_px", "pass" if at["edge_margin_px"] >= pad else "fail", at["edge_margin_px"], pad),
              common.check("uv.texel_px_per_m", "pass" if at["texel_px_per_m"] >= tmin else "fail",
                           at["texel_px_per_m"], tmin),
              common.check("uv.texel_islands", "pass" if at["island_texel_min"] >= tmin else "fail",
                           at["island_texel_min"], tmin, note=f"{at['islands_checked']} mảnh" + pieces_note),
              stretch_check(g, spec["model"].get("uv_stretch"))]
    return checks, {f"at_{res}": at, "at_1024": at1024}


if __name__ == "__main__":
    require_root()
    cli.run(TOOL, "uv_edge", __doc__, lambda p: None, check)
