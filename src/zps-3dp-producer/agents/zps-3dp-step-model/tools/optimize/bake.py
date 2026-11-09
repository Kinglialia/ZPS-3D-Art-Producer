"""UV and texture for the chosen level, then a textured SSIM check (optimize.md §7).

Usage:
  $BLENDER -b --python tools/optimize/bake.py -- --work <w> --low <w>/selected_auto.glb --spec task/spec.json
  python3 tools/optimize/bake.py --work <w> --low <w>/selected_auto.glb [--spec task/spec.json]
         [--mode auto|keep_uv|rebake] [--name auto] [--out <w>/bake_<name>.json]

Mode (auto): rebake when cleanup.json says rebake (remeshed, or UVs unusable), else keep_uv.
texture.mode keep_uv cannot keep UVs that do not exist: it falls back to rebake with a warning.

keep_uv: the low mesh must have a UV layer; its textures are written to <w>/bake/<name>/ as PNG
  and the GLB is copied to <w>/baked_<name>.glb. asset_checks/uv_check.py runs on it when the
  spec has a "uv" block (bounds, overlap, padding); its overall becomes the check uv_check.
rebake:
  - xatlas unwrap of the low mesh (deterministic). Pure Python: in-process when xatlas imports,
    else a system python3 subprocess; Blender Smart UV Project only as a last resort (warning).
    Resolution = next power of two of sqrt(low surface area m2) x texture.texel_density_px_per_m
    / sqrt(UV occupancy), clamped to [texture.min_res, texture.max_res]; padding from
    texture.padding_px_by_res (nearest listed resolution, scaled). Occupancy comes from the
    unwrap, so the unwrap repeats while the resolution changes; data.uv_occupancy, data.res_steps.
  - Cycles CPU bake, selected-to-active, from cleanup's bake_source (pre_remesh.glb when
    remeshed, else ref_high.glb): DIFFUSE with pass_filter COLOR (albedo, no lighting);
    max_ray_distance = texture.max_ray_distance_ratio x diagonal, cage_extrusion = half of it
    (rays cover +-half around the low surface); margin texture.bake_margin_px. Adds a tangent
    NORMAL bake (OpenGL: +X +Y +Z) when texture.mode is albedo_normal or spec style is pbr.
  - One material "baked", PNGs in <w>/bake/<name>/, export <w>/baked_<name>.glb. Spec style
    hand_painted: the material is rebuilt unlit (Light Path trick + Emission, which the glTF
    exporter writes as KHR_materials_unlit); pbr and unset stay Principled.
check: low (baked) and high (bake source, or ref_high for keep_uv) rendered with Cycles, every
  material replaced by an emission of its base colour (unlit albedo), orthographic cameras from
  bake.ssim_views (raster.VIEW_DIRS) with one framing for both; SSIM (7x7 window, per channel,
  sample covariance, as skimage) averaged over the union of both alpha masks; min over views
  against texture.ssim_min. A fail sets data.next_action: step up one sweep level and redo.

Exit 0 on pass/fail; 1 on error (error JSON written first).
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import numpy as np  # noqa: E402

import optlib  # noqa: E402
import optbpy  # noqa: E402
from optlib import common  # noqa: E402
import bpy  # noqa: E402
import raster  # noqa: E402
from mathutils import Vector  # noqa: E402

TOOL = "optimize/bake"


def parse():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True)
    p.add_argument("--low", required=True)
    p.add_argument("--spec")
    p.add_argument("--mode", default="auto", choices=["auto", "keep_uv", "rebake"])
    p.add_argument("--name")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    if not a.name:
        stem = os.path.splitext(os.path.basename(a.low))[0]
        a.name = stem[len("selected_"):] if stem.startswith("selected_") else stem
    a.out = a.out or os.path.join(a.work, f"bake_{a.name}.json")
    return a


# ------------------------------------------------------------------ helpers
def texture_resolution(area_m2, tcfg, occupancy=1.0):
    """Next power of two of sqrt(area) x density / sqrt(UV occupancy), clamped to [min_res, max_res].
    Occupancy (share of the 0-1 UV square covered by islands) < 1 means fewer texels land on the
    surface, so the texture must grow to keep the density."""
    raw = math.sqrt(max(area_m2, 1e-12)) * tcfg["texel_density_px_per_m"] / math.sqrt(max(occupancy, 1e-3))
    res = 2 ** int(math.ceil(math.log2(max(raw, 1)) - 1e-9))
    return int(min(max(res, tcfg["min_res"]), tcfg["max_res"])), raw


def uv_occupancy(uvt):
    """Sum of UV triangle areas (islands do not overlap after xatlas): share of the 0-1 square used."""
    e1, e2 = uvt[:, 1] - uvt[:, 0], uvt[:, 2] - uvt[:, 0]
    return float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2)


def padding_for(res, table):
    table = {int(k): int(v) for k, v in table.items()}
    if res in table:
        return table[res]
    k = min(table, key=lambda x: abs(math.log2(x) - math.log2(res)))
    return max(2, int(round(table[k] * res / k)))


XATLAS_CODE = """
import sys, numpy as np, xatlas
d = np.load(sys.argv[1]); res, pad = int(sys.argv[3]), int(sys.argv[4])
atlas = xatlas.Atlas(); atlas.add_mesh(d["V"].astype(np.float32), d["F"].astype(np.uint32))
po = xatlas.PackOptions(); po.resolution = res; po.padding = pad; po.bilinear = True
atlas.generate(xatlas.ChartOptions(), po)
vm, idx, uv = atlas[0]
np.savez(sys.argv[2], vm=vm, idx=idx, uv=uv)
"""


def xatlas_unwrap(v, f, res, pad, warnings):
    """UV per triangle corner (m,3,2), faces in input order. In-process xatlas, else a system
    python3 with xatlas. Returns (uvt, how) or (None, reason)."""
    try:
        import xatlas
        atlas = xatlas.Atlas()
        atlas.add_mesh(v.astype(np.float32), f.astype(np.uint32))
        po = xatlas.PackOptions()
        po.resolution = res
        po.padding = pad
        po.bilinear = True
        atlas.generate(xatlas.ChartOptions(), po)
        vm, idx, uv = atlas[0]
        how = "xatlas (in-process)"
    except ImportError:
        py = shutil.which("python3") or shutil.which("python")
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "in.npz"), os.path.join(tmp, "out.npz")
            np.savez(src, V=v, F=f)
            r = subprocess.run([py, "-c", XATLAS_CODE, src, dst, str(res), str(pad)],
                               capture_output=True, text=True) if py else None
            if r is None or r.returncode != 0:
                return None, f"xatlas unavailable ({(r.stderr[-300:] if r else 'no python3')})"
            d = np.load(dst)
            vm, idx, uv = d["vm"], d["idx"], d["uv"]
        how = "xatlas (system python3)"
        warnings.append("xatlas not importable inside Blender; ran it with the system python3")
    if not np.allclose(v[vm[idx]], v[f], atol=1e-5):
        return None, "xatlas changed the face order; cannot map UVs back"
    return uv[idx].astype(np.float64), how


def smart_project(obj, warnings):
    warnings.append("xatlas unavailable: Blender Smart UV Project used (not deterministic)")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")


def set_uv_layer(obj, uvt, name="bake"):
    me = obj.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    layer = me.uv_layers.new(name=name)
    start = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", start)
    flat = np.zeros((len(me.loops), 2))
    for k in range(3):
        flat[start + k] = uvt[:, k]
    layer.data.foreach_set("uv", flat.reshape(-1))
    layer.active = True
    layer.active_render = True
    me.update()


def new_image(name, res, non_color=False):
    img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=False)
    img.generated_color = (0.5, 0.5, 1.0, 1.0) if non_color else (0.5, 0.5, 0.5, 1.0)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def save_png(img, path):
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()


def bake_material(obj, albedo, normal=None):
    mat = bpy.data.materials.new("baked")
    _use_nodes(mat)
    mat.use_backface_culling = True     # exported as doubleSided: false (closed props, mobile)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "bake"
    ta = nt.nodes.new("ShaderNodeTexImage")
    ta.image = albedo
    nt.links.new(uvn.outputs["UV"], ta.inputs["Vector"])
    nt.links.new(ta.outputs["Color"], bsdf.inputs["Base Color"])
    tn = None
    if normal is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = normal
        nt.links.new(uvn.outputs["UV"], tn.inputs["Vector"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return mat, ta, tn


def _use_nodes(mat):
    """Material.use_nodes is deprecated (always on from Blender 6); set it only when needed."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        if not mat.use_nodes:
            mat.use_nodes = True


def link_normal_map(mat, tn):
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.space = "TANGENT"
    nm.uv_map = "bake"
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def make_unlit(mat, ta):
    """Replace the Principled surface by the node pattern Blender's glTF exporter writes as
    KHR_materials_unlit (io_scene_gltf2 exp/material/unlit.py, the same graph its importer builds):
    [Light Path: Is Camera Ray] -> Mix(Transparent, Emission(albedo)) -> Material Output.
    Cycles shows the emission to camera rays only, so renders stay unlit albedo."""
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]:
        nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(ta.outputs["Color"], em.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def import_joined(path, name, merge=False):
    objs = optbpy.import_model(path, merge_vertices=merge)
    obj = optbpy.join_world(name, objs)
    optbpy.triangulate(obj)
    return obj


def emission_copy(mat):
    """Copy of mat whose surface is an emission of its base colour (unlit albedo)."""
    m = mat.copy() if mat else bpy.data.materials.new("flat")
    _use_nodes(m)
    nt = m.node_tree
    if not any(n.type == "BSDF_PRINCIPLED" for n in nt.nodes) and any(n.type == "EMISSION" for n in nt.nodes):
        return m    # already unlit (make_unlit or an imported KHR_materials_unlit material)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    if bsdf is not None and bsdf.inputs["Base Color"].is_linked:
        nt.links.new(bsdf.inputs["Base Color"].links[0].from_socket, em.inputs["Color"])
    elif bsdf is not None:
        em.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
    else:
        em.inputs["Color"].default_value = tuple(mat.diffuse_color) if mat else (0.8, 0.8, 0.8, 1)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def render_set(scene, obj, cam, views, center, dist, px, outdir, tag, samples):
    """Render obj alone (unlit albedo) from each view; returns {view: RGBA float (px,px,4)}."""
    keep = [s.material for s in obj.material_slots]
    for i, s in enumerate(obj.material_slots):
        s.material = emission_copy(s.material)
    if not obj.material_slots:
        obj.data.materials.append(emission_copy(None))
    for o in scene.objects:
        o.hide_render = o not in (obj, cam)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = px
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    out = {}
    for view in views:
        d = Vector(raster.VIEW_DIRS[view]).normalized()
        cam.location = center - d * dist
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(outdir, f"{tag}_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path, check_existing=False)
        buf = np.empty(px * px * 4, np.float32)
        img.pixels.foreach_get(buf)
        out[view] = buf.reshape(px, px, 4)[::-1]
        bpy.data.images.remove(img)
    for i, s in enumerate(obj.material_slots):
        if i < len(keep):
            s.material = keep[i]
    return out


def _box(x, r):
    """Mean over a (2r+1)^2 window, valid region only, via integral image."""
    c = np.pad(x, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def masked_ssim(a, b, mask, win=7):
    """Mean SSIM over mask (valid window centres), averaged over channels. a, b: (h,w,c) in 0-1."""
    r = win // 2
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    cov = win * win / (win * win - 1)
    m = mask[r:-r, r:-r]
    if not m.any():
        return float("nan")
    vals = []
    for ch in range(a.shape[2]):
        x, y = a[:, :, ch].astype(np.float64), b[:, :, ch].astype(np.float64)
        ux, uy = _box(x, r), _box(y, r)
        vx = cov * (_box(x * x, r) - ux * ux)
        vy = cov * (_box(y * y, r) - uy * uy)
        vxy = cov * (_box(x * y, r) - ux * uy)
        s = ((2 * ux * uy + c1) * (2 * vxy + c2)) / ((ux * ux + uy * uy + c1) * (vx + vy + c2))
        vals.append(s[m].mean())
    return float(np.mean(vals))


def ssim_check(scene, low, high, bcfg, outdir):
    os.makedirs(outdir, exist_ok=True)
    pts = []
    for o in (low, high):
        v, _ = optbpy.mesh_arrays(o)
        pts.append(v)
    allv = np.concatenate(pts)
    lo, hi = allv.min(0), allv.max(0)
    center = Vector(((lo + hi) / 2).tolist())
    diag = float(np.linalg.norm(hi - lo))
    cdata = bpy.data.cameras.new("ssim_cam")
    cdata.type = "ORTHO"
    cdata.ortho_scale = diag * 1.05
    cdata.clip_start = diag * 0.01
    cdata.clip_end = diag * 10
    cam = bpy.data.objects.new("ssim_cam", cdata)
    scene.collection.objects.link(cam)
    scene.camera = cam
    px, views = bcfg["ssim_render_px"], bcfg["ssim_views"]
    rl = render_set(scene, low, cam, views, center, diag * 2, px, outdir, "low", bcfg["render_samples"])
    rh = render_set(scene, high, cam, views, center, diag * 2, px, outdir, "high", bcfg["render_samples"])
    per = {}
    for view in views:
        a, b = rl[view], rh[view]
        mask = (a[:, :, 3] > 0.5) | (b[:, :, 3] > 0.5)
        bg = 0.5
        ca = a[:, :, :3] * a[:, :, 3:] + bg * (1 - a[:, :, 3:])
        cb = b[:, :, :3] * b[:, :, 3:] + bg * (1 - b[:, :, 3:])
        per[view] = round(masked_ssim(ca, cb, mask), 4)
    bpy.data.objects.remove(cam, do_unlink=True)
    return per


def main(a):
    cfg, spec = optlib.settings(a.spec)
    tcfg, bcfg = cfg["texture"], cfg["bake"]
    cl_path = os.path.join(a.work, "cleanup.json")
    cl = common.read_json(cl_path)["data"] if os.path.isfile(cl_path) else {}
    ref_high = cl.get("ref_high") or os.path.join(a.work, "ref_high.glb")
    rebake = bool(cl.get("rebake"))
    warnings, checks, artifacts = [], [], {}
    mode = a.mode
    if mode == "auto":
        mode = "rebake" if rebake else "keep_uv"
    if mode == "keep_uv" and rebake:
        warnings.append("keep_uv requested but cleanup marked rebake (UVs removed or unusable); rebaking")
        mode = "rebake"
    want_normal = tcfg["mode"] == "albedo_normal" or spec.get("style") == "pbr"
    unlit = spec.get("style") == "hand_painted"   # baked light in albedo: export KHR_materials_unlit
    bdir = os.path.join(a.work, "bake", a.name)
    os.makedirs(bdir, exist_ok=True)
    baked = os.path.join(a.work, f"baked_{a.name}.glb")

    optbpy.reset_scene()
    scene = bpy.context.scene
    low = import_joined(a.low, optlib.output_object(a.work), merge=True)   # asset name from audit
    v, f = optbpy.mesh_arrays(low)
    area = float(optbpy.face_areas_normals(v, f)[0].sum())
    data = {"mode": mode, "low": os.path.abspath(a.low), "low_tris": len(f), "surface_area_m2": common.r(area)}

    if mode == "keep_uv":
        has_uv = len(low.data.uv_layers) > 0
        checks.append(common.check("uv.present", "pass" if has_uv else "fail", has_uv))
        if not has_uv:
            common.write_result(a.out, TOOL, checks, warnings=warnings, data=data, source=a.low, spec_path=a.spec)
            return
        _, tex = optbpy.materials_and_textures(low)
        copied = []
        for t in tex:
            img = bpy.data.images[t["image"]]
            dst = os.path.join(bdir, f"{bpy.path.clean_name(t['image'])}.png")
            save_png(img, dst)
            copied.append(dst)
        shutil.copyfile(a.low, baked)
        if unlit:
            warnings.append("keep_uv copies the source GLB: its materials are not converted to unlit "
                            "(style hand_painted wants KHR_materials_unlit)")
        data.update({"textures": copied, "texture_res": [t["size"] for t in tex]})
        if spec.get("uv") and a.spec:
            uvc = os.path.join(bdir, "uv_check.json")
            cmd = optlib.blender_cmd(cfg, os.path.join(common.TOOLS_ROOT, "asset_checks", "uv_check.py"),
                                     ["--input", baked, "--spec", a.spec, "--out", uvc])
            res = optlib.run(cmd, 600) if cmd else None
            if res is not None and os.path.isfile(uvc):
                u = common.read_json(uvc)
                checks.append(common.check("uv_check", "pass" if u["overall"] in ("pass", "info") else "fail",
                                           u["overall"], note=f"asset_checks/uv_check: {u['summary']}"))
                artifacts["uv_check"] = uvc
            else:
                checks.append(common.check("uv_check", "not_checked",
                                           note=f"uv_check.py did not run: {optlib.tail(res.stderr if res else 'no Blender', 4)}"))
        else:
            checks.append(common.check("uv_check", "not_checked", note="spec has no uv block"))
        high = import_joined(ref_high, "high")
        data["ssim_reference"] = ref_high
    else:
        source = cl.get("bake_source") or ref_high
        # occupancy depends on the packing, the packing on the resolution: unwrap at the
        # occupancy-free size, then re-unwrap until the resolution stops changing (max 3 passes)
        res, raw = texture_resolution(area, tcfg)
        occ, res_steps = 1.0, []
        for _ in range(3):
            pad = padding_for(res, tcfg["padding_px_by_res"])
            uvt, how = xatlas_unwrap(v, f, res, pad, warnings)
            if uvt is None:
                break
            occ = uv_occupancy(uvt)
            res_steps.append({"res": res, "occupancy": common.r(occ)})
            new_res, raw = texture_resolution(area, tcfg, occ)
            if new_res == res:
                break
            res = new_res
        if uvt is None:
            warnings.append(how)
            smart_project(low, warnings)
            how = "smart_project"
            uvt = optbpy.loop_uvs(low)
            occ = uv_occupancy(uvt)
            res, raw = texture_resolution(area, tcfg, occ)
            pad = padding_for(res, tcfg["padding_px_by_res"])
        set_uv_layer(low, uvt)
        cnt = optbpy.uv_coverage(np.clip(uvt, 0, 1), res)
        overlap = float((cnt > 1).sum() / max((cnt > 0).sum(), 1))
        inside = bool(((uvt >= -1e-6) & (uvt <= 1 + 1e-6)).all())
        checks.append(common.check("uv.inside_0_1", "pass" if inside else "fail", inside))
        checks.append(common.check("uv.overlap_ratio", "pass" if overlap <= cfg["audit"]["uv_overlap_max"] else "fail",
                                   common.r(overlap), cfg["audit"]["uv_overlap_max"]))
        high = import_joined(source, "high")
        # DIFFUSE/COLOR returns black on metallic surfaces, and glTF metallicFactor defaults to 1
        # when a file omits it; the albedo bake wants base colour, so bake the source as dielectric.
        for m in high.data.materials:
            for n in (m.node_tree.nodes if m and m.node_tree else []):
                if n.type == "BSDF_PRINCIPLED":
                    for l in list(n.inputs["Metallic"].links):
                        m.node_tree.links.remove(l)
                    n.inputs["Metallic"].default_value = 0.0
        hv, _ = optbpy.mesh_arrays(high)
        diag = float(np.linalg.norm(hv.max(0) - hv.min(0)))
        mrd = tcfg["max_ray_distance_ratio"] * diag
        albedo = new_image("albedo", res)
        normal = new_image("normal", res, non_color=True) if want_normal else None
        mat, ta, tn = bake_material(low, albedo, normal)
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = bcfg["bake_samples"]
        for o in bpy.data.objects:
            o.select_set(o in (low, high))
        bpy.context.view_layer.objects.active = low
        common_args = dict(use_selected_to_active=True, cage_extrusion=mrd / 2, max_ray_distance=mrd,
                           margin=tcfg["bake_margin_px"], margin_type="EXTEND", use_clear=True,
                           target="IMAGE_TEXTURES", uv_layer="bake")
        mat.node_tree.nodes.active = ta
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, **common_args)
        albedo_png = os.path.join(bdir, "albedo.png")
        save_png(albedo, albedo_png)
        maps = {"albedo": albedo_png}
        if normal is not None:
            mat.node_tree.nodes.active = tn
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y",
                                normal_b="POS_Z", **common_args)
            normal_png = os.path.join(bdir, "normal.png")
            save_png(normal, normal_png)
            maps["normal"] = normal_png
            if unlit:
                warnings.append("style hand_painted exports unlit: the baked normal map is saved but not linked")
            else:
                link_normal_map(mat, tn)
        if unlit:
            make_unlit(mat, ta)
        albedo.reload()
        optbpy.export_glb(baked, [low])
        artifacts.update(maps)
        data.update({"bake_source": source, "unwrap": how, "texture_res": res, "texture_res_raw": round(raw, 1),
                     "uv_occupancy": common.r(occ), "res_steps": res_steps,
                     "padding_px": pad, "max_ray_distance_m": common.r(mrd, 5), "cage_extrusion_m": common.r(mrd / 2, 5),
                     "margin_px": tcfg["bake_margin_px"], "maps": list(maps), "uv_overlap_ratio": common.r(overlap),
                     "material": "unlit (KHR_materials_unlit)" if unlit else "principled"})
        data["ssim_reference"] = source
        # renders use the baked image: make sure the node points at the saved file
        ta.image = bpy.data.images.load(albedo_png, check_existing=False)

    artifacts["baked"] = baked
    per = ssim_check(scene, low, high, bcfg, os.path.join(bdir, "ssim"))
    worst = min(per.values())
    ok = worst >= tcfg["ssim_min"]
    checks.append(common.check("ssim_min", "pass" if ok else "fail", worst, tcfg["ssim_min"],
                               note=None if ok else "below texture.ssim_min: step up one sweep level and redo"))
    data["ssim_views"] = per
    if not ok:
        data["next_action"] = "step up one sweep level (more tris) and rerun bake.py"
    metrics = {"ssim_min": worst, "ssim_mean": common.r(np.mean(list(per.values()))), "low_tris": len(f),
               "texture_res": data.get("texture_res")}
    common.write_result(a.out, TOOL, checks, metrics, warnings, artifacts, data, source=a.low, spec_path=a.spec)


if __name__ == "__main__":
    args = parse()
    try:
        main(args)
    except Exception as exc:  # noqa: BLE001
        common.write_error(args.out, TOOL, exc, source=args.low)
        sys.exit(1)
