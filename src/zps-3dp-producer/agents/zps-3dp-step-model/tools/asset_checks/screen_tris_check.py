"""Triangle size on screen at the game camera: micro triangles and slivers.

Small and thin triangles cost GPU time out of proportion to what they show (quad overdraw);
Arm/Android guidance: keep triangles above ~10 px on screen (research_notes §4). The script
projects every triangle of the evaluated meshes with the game camera from spec.camera (the same
ac_common.game_camera / place_camera as render_rig, no render needed) and counts, among the
front-facing triangles inside the frame:
  small: screen area < min_px_area
  thin:  height over the longest edge < thin_max_px while the longest edge > thin_min_long_px.
         (The task-level rule "min edge < 1 px while max > 50 px" is included: a short edge
         implies a short height; the height test also catches needles whose 3 edges are long.)
Back-facing triangles are left out (culled before raster); occluded ones stay in (they still
rasterize without a depth pre-pass). Grazing triangles (normal more than grazing_deg from the
direction to the camera) are left out of "small" and "thin": every curved surface has them on its silhouette
and no density change removes them; their count is reported as info.

Only meaningful with a fixed camera (perspective + distance_m, or ortho + ortho_scale). Without
one the script calibrates to camera.target_px_height like render_rig and reports info only.

Spec: objects, camera.{type, fov_v_deg | lens_mm, ortho_scale, distance_m, look_at, azimuth_deg,
  elevation_deg, screen, target_object, target_px_height},
  screen_tris.{min_px_area (else validate.sliver_min_px_area in the spec, else config
  validate.sliver_min_px_area), max_small_ratio (optional), max_thin (optional),
  thin_max_px (default 1.0), thin_min_long_px (default 50), grazing_deg (default 75)}.
Outputs: result JSON and screen_tris.png next to --out (asset crop at 1:1: grey = triangle edges,
red = small, yellow = thin).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import ac_common as ac  # noqa: E402


def project(scene, cam, co):
    """World coords (n,3) -> pixel coords (n,2, y up) and clip w (n,)."""
    dg = bpy.context.evaluated_depsgraph_get()
    sw, sh = scene.render.resolution_x, scene.render.resolution_y
    P = np.array(cam.calc_matrix_camera(dg, x=sw, y=sh))
    V = np.array(cam.matrix_world.inverted())
    h = np.c_[co, np.ones(len(co))] @ (P @ V).T
    w = h[:, 3]
    safe = np.where(np.abs(w) < 1e-12, 1e-12, w)
    px = np.c_[(h[:, 0] / safe * 0.5 + 0.5) * sw, (h[:, 1] / safe * 0.5 + 0.5) * sh]
    return px, w


def mesh_tris(obj):
    me = ac.evaluated_mesh(obj)
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    tri = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    poly = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", poly)
    bpy.data.meshes.remove(me)
    return co.reshape(-1, 3), tri.reshape(-1, 3), poly


def main():
    a, spec = ac.parse_args()
    scene = bpy.context.scene
    objs = ac.target_objects(spec)
    cam_cfg = spec.get("camera", {})
    st = spec.get("screen_tris", {})
    sw, sh = cam_cfg.get("screen", [1920, 1080])
    az = math.radians(cam_cfg.get("azimuth_deg", 0))
    el = math.radians(cam_cfg.get("elevation_deg", 40))

    min_area, src = ac.threshold(st, "min_px_area")
    src_key = None
    if min_area is None:
        min_area, src = ac.threshold(spec.get("validate"), "sliver_min_px_area", "validate.sliver_min_px_area")
        src_key = "validate.sliver_min_px_area"
        if src == "spec":
            src = "spec validate.sliver_min_px_area"
    thin_px = st.get("thin_max_px", 1.0)
    thin_long = st.get("thin_min_long_px", 50.0)
    graze_cos = math.cos(math.radians(st.get("grazing_deg", 75.0)))

    cam, fixed = ac.game_camera(scene, cam_cfg, "ac_tri_cam")
    scene.camera = cam
    pts = ac.world_verts(objs)
    lo, hi = ac.bbox(pts)
    center = ac.camera_target(cam_cfg, pts)
    radius = (hi - lo).length / 2
    ortho = cam.data.type == "ORTHO"
    dist = cam_cfg.get("distance_m", radius * 4 + (10 if ortho else 0))
    target_px = cam_cfg.get("target_px_height")
    target_note = None
    if not fixed and target_px:
        tobj, target_note = ac.camera_target_object(cam_cfg, objs)
        dist = ac.calibrate_distance(scene, cam, center, az, el, dist,
                                     ac.world_verts([tobj]), target_px, sh)
    else:
        ac.place_camera(cam, center, az, el, dist)

    rows, data = [], {}
    for o in objs:
        co, tri, poly = mesh_tris(o)
        px, w = project(scene, cam, co)
        a_, b_, c_ = px[tri[:, 0]], px[tri[:, 1]], px[tri[:, 2]]
        in_front = (w[tri] > 0).all(axis=1)
        signed = 0.5 * ((b_[:, 0] - a_[:, 0]) * (c_[:, 1] - a_[:, 1]) - (b_[:, 1] - a_[:, 1]) * (c_[:, 0] - a_[:, 0]))
        xs = np.stack([a_[:, 0], b_[:, 0], c_[:, 0]], 1)
        ys = np.stack([a_[:, 1], b_[:, 1], c_[:, 1]], 1)
        on_screen = (xs.max(1) >= 0) & (xs.min(1) <= sw) & (ys.max(1) >= 0) & (ys.min(1) <= sh)
        front = in_front & on_screen & (signed > 0)
        area = np.abs(signed)
        e = np.stack([np.linalg.norm(b_ - a_, axis=1), np.linalg.norm(c_ - b_, axis=1),
                      np.linalg.norm(a_ - c_, axis=1)], 1)
        longest = e.max(1)
        height = np.where(longest > 0, 2 * area / np.maximum(longest, 1e-12), 0)
        w0, w1, w2 = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
        nrm = np.cross(w1 - w0, w2 - w0)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        if ortho:
            to_cam = np.tile(np.array(cam.matrix_world.to_quaternion() @ ac.Vector((0, 0, 1))), (len(tri), 1))
        else:
            to_cam = np.array(cam.matrix_world.translation) - (w0 + w1 + w2) / 3
        to_cam /= np.maximum(np.linalg.norm(to_cam, axis=1, keepdims=True), 1e-12)
        grazing = np.abs((nrm * to_cam).sum(1)) < graze_cos
        tiny = front & (area < min_area) if min_area is not None else np.zeros_like(front)
        small = tiny & ~grazing
        thin_all = front & (height < thin_px) & (longest > thin_long)
        thin = thin_all & ~grazing   # edge-on faces on a silhouette are thin by projection, like small
        data[o.name] = {"tris": int(len(tri)), "front_facing_on_screen": int(front.sum()),
                        "small": int(small.sum()), "small_grazing_excluded": int((tiny & grazing).sum()),
                        "thin": int(thin.sum()), "thin_grazing_excluded": int((thin_all & grazing).sum()),
                        "area_px_p5": ac.r(np.percentile(area[front], 5), 2) if front.any() else None,
                        "area_px_median": ac.r(np.median(area[front]), 2) if front.any() else None,
                        "small_faces": sorted({int(p) for p in poly[small]})[:30],
                        "thin_faces": sorted({int(p) for p in poly[thin]})[:30]}
        rows.append((a_, b_, c_, front, small, thin))

    n_front = sum(d["front_facing_on_screen"] for d in data.values())
    n_small = sum(d["small"] for d in data.values())
    n_thin = sum(d["thin"] for d in data.values())
    n_graze = sum(d["small_grazing_excluded"] for d in data.values())
    ratio = n_small / n_front if n_front else 0.0
    checks = []
    cam_note = None if fixed else "camera not fixed (calibration mode): info only"
    small_val = {"small": n_small, "front_facing": n_front, "ratio": ac.r(ratio, 4), "min_px_area": min_area,
                 "small_grazing_excluded": n_graze}
    lim = st.get("max_small_ratio")
    if min_area is None:
        checks.append(ac.check("screen.small_tri_ratio", "not_checked", note="no min_px_area in spec or config"))
    elif fixed and lim is not None:
        checks.append(ac.check("screen.small_tri_ratio", "pass" if ratio <= lim else "fail", small_val, lim,
                               note=ac.source_note(src, src_key, "min_px_area")))
    else:
        checks.append(ac.check("screen.small_tri_ratio", "info", small_val,
                               note=cam_note or "no screen_tris.max_small_ratio in spec"))
    thin_val = {"thin": n_thin, "thin_max_px": thin_px, "thin_min_long_px": thin_long,
                "thin_grazing_excluded": sum(d["thin_grazing_excluded"] for d in data.values())}
    lim = st.get("max_thin")
    if fixed and lim is not None:
        checks.append(ac.check("screen.thin_tris", "pass" if n_thin <= lim else "fail", thin_val, lim))
    else:
        checks.append(ac.check("screen.thin_tris", "info", thin_val,
                               note=cam_note or "no screen_tris.max_thin in spec"))

    # overlay: the asset crop at 1:1, grey edges, red small, yellow thin
    import cv2
    x0, x1, y0, y1 = ac.projected_box(scene, cam, pts)
    pad = 12
    cx0, cx1 = max(0, int(x0 * sw) - pad), min(sw, int(math.ceil(x1 * sw)) + pad)
    cy0, cy1 = max(0, int(y0 * sh) - pad), min(sh, int(math.ceil(y1 * sh)) + pad)
    img = np.full((max(1, cy1 - cy0), max(1, cx1 - cx0), 3), 24, np.uint8)
    S = 16  # cv2 sub-pixel shift 4

    def pix(p):
        return np.stack([(p[:, 0] - cx0) * S, ((sh - p[:, 1]) - (sh - cy1)) * S], 1).astype(np.int32)

    for a_, b_, c_, front, small, thin in rows:
        polys = np.stack([pix(a_), pix(b_), pix(c_)], 1)
        for i in np.nonzero(front)[0]:
            cv2.polylines(img, [polys[i]], True, (110, 110, 110), 1, cv2.LINE_AA, shift=4)
        for i in np.nonzero(small)[0]:
            cv2.fillPoly(img, [polys[i]], (40, 40, 255), cv2.LINE_AA, shift=4)
            cv2.polylines(img, [polys[i]], True, (40, 40, 255), 1, cv2.LINE_AA, shift=4)
        for i in np.nonzero(thin)[0]:
            cv2.polylines(img, [polys[i]], True, (0, 230, 255), 1, cv2.LINE_AA, shift=4)
    op = os.path.join(os.path.dirname(os.path.abspath(a.out)), "screen_tris.png")
    cv2.imwrite(op, img)

    data["camera"] = {"mode": "fixed" if fixed else "calibration", "distance_m": ac.r(dist),
                      "look_at": [ac.r(v) for v in center], "screen": [sw, sh],
                      "asset_px_height": ac.r((y1 - y0) * sh, 1)}
    data["overlay"] = op
    if target_note:
        data["camera"]["target_note"] = target_note
        data.setdefault("warnings", []).append(target_note)
    ac.write_result(a.out, "screen_tris_check", a.spec, checks, data)


if __name__ == "__main__":
    ac.run_main(main, "screen_tris_check")
