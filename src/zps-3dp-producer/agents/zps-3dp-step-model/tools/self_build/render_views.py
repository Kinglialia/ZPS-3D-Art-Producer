"""Review renders for the critic (references/self_build.md, step 6.1). Blender Workbench, headless.

Usage:
  blender -b --python tools/self_build/render_views.py -- --work <w> --spec task/spec.json --mode critic
  python3 tools/self_build/render_views.py --input model.glb [--spec spec.json] --mode clay
Options: --mode critic|parts|clay|normal|overlay (default critic), --views front,34 (override the
  view list of the chosen mode), --outdir (default <w>/renders or <input dir>/renders_<stem>),
  --out (default <outdir>/renders.json).

Input:
  --work   assembled.glb + assembly.json (part names/order) + parts/<name>.glb
  --input  any GLB/glTF; parts = one per mesh/material when there are several, else one per
           connected component
Images (each a separate PNG, long edge <= self_build.critic_max_long_edge, render long edge
self_build.render_size, light neutral background (sRGB 235), orthographic cameras along lib/raster.VIEW_DIRS):
  clay_<view>.png    front, back, left, right, 34: matte mid-grey, studio light, outline
  normal_<view>.png  same views: world-space normal as colour (rgb = n * 0.5 + 0.5), flat
  parts_<view>.png   front, 34: flat colour per part, part number (1-based build order) drawn
                     at the most interior visible pixel of the part, legend in the right margin
  overlay_<view>.png each orthographic view in spec.concept.views: concept-only red, model-only
                     blue, overlap grey (white background, lib/raster.overlay_image), IoU and
                     red/blue % of the concept area printed in the top margin
  prev_34.png        (critic, --work) clay 34 of the newest kept/baseline snapshot (apply_edit)
                     whose code differs from now
critic = all of the above. renders.json (result JSON) lists every file with its label, plus
code_hash = sha256 of part_graph.json + parts_lib.py at render time (apply_edit uses it to
refuse stale renders); the rendered code is copied to <outdir>/code/.
Exit 0 on success, 1 on error.
"""
import colorsys
import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import numpy as np  # noqa: E402

import common  # noqa: E402
import graph as G  # noqa: E402
import raster  # noqa: E402

TOOL = "self_build/render_views"
VIEWS_3D = ["front", "back", "left", "right", "34"]
PARTS_VIEWS = ["front", "34"]
BG_SRGB = 235           # light neutral background: mid-grey clay and normal colours stand out against it
CLAY_SRGB = 0.75        # clay albedo (sRGB); with the default studio light faces land mid-grey, well below the background
MARGIN = 0.06           # empty border around the prop, fraction of its projected size


def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def palette(n):
    out = []
    for i in range(n):
        h = (i * 0.618034) % 1.0
        out.append(colorsys.hsv_to_rgb(h, 0.55 if i % 2 else 0.75, 0.95 if i % 3 else 0.8))
    return out


# ------------------------------------------------------------------ inputs
def load_work(work):
    asm_path = os.path.join(work, "assembly.json")
    asm = common.read_json(asm_path)
    if asm.get("overall") == "error":
        raise RuntimeError(f"assembly.json is an error result: {asm['data'].get('error')}")
    v, t, _ = G.load_glb(os.path.join(work, "assembled.glb"))
    parts = []
    for r in asm["data"]["parts"]:
        gp = r["glb"]
        if not os.path.isfile(gp):  # work dir copied/moved: parts/ sits next to assembled.glb
            gp = os.path.join(work, "parts", os.path.basename(gp))
        pv, pt, _ = G.load_glb(gp)
        parts.append({"index": r["index"], "name": r["name"], "verts": pv, "tris": pt})
    return v, t, parts, asm


def load_input(path):
    v, t, pieces = G.load_glb(path)
    if len(t) == 0:
        raise RuntimeError(f"no triangles in {path}")
    parts = []
    if len(pieces) > 1:
        for i, (name, pv, pt) in enumerate(pieces):
            parts.append({"index": i + 1, "name": str(name), "verts": pv, "tris": pt})
    else:
        wv, wt, comps = G.components(v, t)
        comps.sort(key=len, reverse=True)
        for i, c in enumerate(comps):
            parts.append({"index": i + 1, "name": f"shell_{i + 1}", "verts": wv, "tris": wt[c]})
    return v, t, parts


# ------------------------------------------------------------------ blender scene
def reset_scene(bpy):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("bg")
    scene.world.color = tuple(srgb_to_linear([BG_SRGB / 255] * 3))
    sh = scene.display.shading
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_specular_highlight = False
    sh.show_object_outline = True
    sh.object_outline_color = (0.05, 0.05, 0.05)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    return scene


def add_mesh(bpy, scene, name, v, t):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(v, float).tolist(), [], np.asarray(t, int).tolist())
    me.update()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def set_normal_colors(me):
    """Per-corner byte colour = world normal * 0.5 + 0.5 (as displayed sRGB values)."""
    n = len(me.polygons)
    normals = np.zeros(n * 3)
    me.polygons.foreach_get("normal", normals)
    col = np.clip(normals.reshape(-1, 3) * 0.5 + 0.5, 0, 1)
    attr = me.color_attributes.new("world_normal", "BYTE_COLOR", "CORNER")
    loop_poly = np.zeros(len(me.loops), int)
    for p in me.polygons:
        loop_poly[p.loop_start:p.loop_start + p.loop_total] = p.index
    rgba = np.ones((len(me.loops), 4))
    rgba[:, :3] = col[loop_poly]
    attr.data.foreach_set("color_srgb", rgba.ravel())
    me.color_attributes.active_color = attr


def camera_frame(v, view, long_edge):
    """Orthographic frame for a view: (right, up, d, frame (u0,u1,v0,v1), (w, h))."""
    d = np.asarray(raster.view_dir(view, G._CAMERAS), float)
    d /= np.linalg.norm(d)
    right, up = raster._basis(d)
    pu, pv = v @ right, v @ up
    m = MARGIN * max(pu.max() - pu.min(), pv.max() - pv.min())
    su, sv = pu.max() - pu.min() + 2 * m, pv.max() - pv.min() + 2 * m
    cu, cv = (pu.max() + pu.min()) / 2, (pv.max() + pv.min()) / 2
    if su >= sv:
        w, h = long_edge, max(16, int(round(long_edge * sv / su)))
        hu = su / 2
        hv = hu * h / w
    else:
        h, w = long_edge, max(16, int(round(long_edge * su / sv)))
        hv = sv / 2
        hu = hv * w / h
    return right, up, d, (cu - hu, cu + hu, cv - hv, cv + hv), (w, h)


def render_view(bpy, scene, cam, v, view, long_edge, path):
    from mathutils import Matrix, Vector
    right, up, d, fr, (w, h) = camera_frame(v, view, long_edge)
    c3 = right * (fr[0] + fr[1]) / 2 + up * (fr[2] + fr[3]) / 2
    centre_along = float(((v.min(0) + v.max(0)) / 2) @ d)
    diag = float(np.linalg.norm(v.max(0) - v.min(0))) or 1.0
    loc = c3 + d * centre_along - d * 5 * diag
    rot = Matrix([list(right), list(up), list(-d)]).transposed()
    cam.matrix_world = Matrix.Translation(Vector(loc)) @ rot.to_4x4()
    cam.data.ortho_scale = max(fr[1] - fr[0], fr[3] - fr[2])   # Blender: span of the longer side
    cam.data.clip_start = 0.01 * diag
    cam.data.clip_end = 20 * diag
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return right, up, fr, (w, h)


def set_shading(scene, mode):
    sh = scene.display.shading
    if mode == "clay":
        sh.light = "STUDIO"
        sh.color_type = "SINGLE"
        sh.single_color = tuple(srgb_to_linear([CLAY_SRGB] * 3))
        sh.show_cavity = True            # edge highlight, so corners on dark faces still read
        sh.cavity_type = "WORLD"
    elif mode == "normal":
        sh.show_cavity = False
        sh.light = "FLAT"
        sh.color_type = "VERTEX"
    elif mode == "parts":
        sh.show_cavity = False
        sh.light = "FLAT"
        sh.color_type = "OBJECT"


# ------------------------------------------------------------------ 2D helpers (PIL)
def font(size):
    from PIL import ImageFont
    return ImageFont.load_default(size=size)


def fit_long_edge(img, max_edge):
    from PIL import Image
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    s = max_edge / max(w, h)
    return img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def label_parts(png, parts_colors, legend, max_edge):
    """Draw each part's number at its most interior visible pixel; legend in the right margin."""
    import cv2
    from PIL import Image, ImageDraw
    img = Image.open(png).convert("RGB")
    arr = np.asarray(img).astype(int)
    h, w = arr.shape[:2]
    fs = max(14, w // 40)
    draw_img = img.copy()
    dr = ImageDraw.Draw(draw_img)
    visible = []
    for idx, rgb in parts_colors:
        target = np.round(np.asarray(rgb) * 255).astype(int)
        m = (np.abs(arr - target).max(-1) <= 6).astype(np.uint8)
        if m.sum() < 4:
            continue
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        txt = str(idx)
        dr.text((int(x), int(y)), txt, fill=(255, 255, 255), font=font(fs), anchor="mm",
                stroke_width=max(2, fs // 8), stroke_fill=(0, 0, 0))
        visible.append(idx)
    line = fs + 10
    lw = max(220, int(fs * 9))
    out = Image.new("RGB", (w + lw, max(h, line * (len(legend) + 2))), (BG_SRGB,) * 3)
    out.paste(draw_img, (0, 0))
    d2 = ImageDraw.Draw(out)
    d2.text((w + 12, 8), "parts (n = build order)", fill=(255, 255, 255), font=font(int(fs * 0.8)))
    for k, (idx, name, rgb) in enumerate(legend):
        y = 8 + line * (k + 1)
        d2.rectangle([w + 12, y, w + 12 + fs, y + fs], fill=tuple(int(c * 255) for c in rgb),
                     outline=(0, 0, 0))
        hidden = "" if idx in visible else "  (hidden)"
        d2.text((w + 20 + fs, y), f"{idx} {name}{hidden}", fill=(255, 255, 255), font=font(int(fs * 0.8)))
    fit_long_edge(out, max_edge).save(png)
    return visible


def overlay_png(cm, mm, view, path, max_edge):
    from PIL import Image, ImageDraw
    img, red, blue = raster.overlay_image(cm, mm)
    iou = raster.iou(cm, mm)
    h, w = img.shape[:2]
    fs = max(14, w // 40)
    top = fs * 3 + 16
    out = Image.new("RGB", (w, h + top), (255, 255, 255))
    out.paste(Image.fromarray(img), (0, top))
    d = ImageDraw.Draw(out)
    d.text((10, 6), f"overlay_{view}   IoU {iou:.3f}", fill=(0, 0, 0), font=font(fs))
    d.text((10, 10 + fs), f"red = concept only {red * 100:.1f}%   blue = model only {blue * 100:.1f}%",
           fill=(0, 0, 0), font=font(int(fs * 0.8)))
    d.text((10, 14 + 2 * fs), "(% of concept area; both silhouettes scaled to their bbox)",
           fill=(90, 90, 90), font=font(int(fs * 0.7)))
    fit_long_edge(out, max_edge).save(path)
    return {"iou": round(iou, 4), "red_pct": round(red * 100, 2), "blue_pct": round(blue * 100, 2)}


# ------------------------------------------------------------------ main
def previous_snapshot(work, current_hash):
    snaps = []
    for d in glob.glob(os.path.join(work, "snapshots", "*")):
        name = os.path.basename(d)
        meta = os.path.join(d, "meta.json")
        if name.isdigit() and os.path.isfile(meta) and os.path.isfile(os.path.join(d, "assembled.glb")):
            snaps.append((int(name), d, common.read_json(meta)))
    for n, d, meta in sorted(snaps, reverse=True):
        if meta.get("code_hash") != current_hash and not str(meta.get("status", "")).startswith("reverted"):
            return n, d
    return None, None


def run(a, settings, spec):
    G._CAMERAS = (spec.get("concept") or {}).get("cameras") or {}  # fitted concept cameras
    import bpy
    sb = settings["self_build"]
    long_edge = min(sb["render_size"], sb["critic_max_long_edge"])
    max_edge = sb["critic_max_long_edge"]
    warnings, files, data = [], [], {}
    if a.work:
        v, t, parts, asm = load_work(a.work)
        code_hash = G.code_hash(a.work)
        if asm["data"].get("code_hash") != code_hash:
            warnings.append("assembled.glb is older than part_graph.json/parts_lib.py; run assembly.py first")
        outdir = a.outdir or os.path.join(a.work, "renders")
        data.update({"work": os.path.abspath(a.work), "code_hash": code_hash,
                     "assembly_code_hash": asm["data"].get("code_hash"),
                     "upto": asm["data"].get("upto"), "parts_total": asm["data"].get("parts_total")})
        if asm["data"].get("upto") and asm["data"]["upto"] < asm["data"]["parts_total"]:
            warnings.append(f"assembly is partial (--upto {asm['data']['upto']})")
    else:
        v, t, parts = load_input(a.input)
        outdir = a.outdir or os.path.join(os.path.dirname(os.path.abspath(a.input)),
                                          "renders_" + os.path.splitext(os.path.basename(a.input))[0])
        data.update({"input": os.path.abspath(a.input), "code_hash": None,
                     "input_sha256": common.file_sha256(a.input)})
    os.makedirs(outdir, exist_ok=True)
    if a.mode == "critic":
        for old in glob.glob(os.path.join(outdir, "*.png")):
            os.remove(old)
    if a.work:
        cdir = os.path.join(outdir, "code")
        os.makedirs(cdir, exist_ok=True)
        for name in ("part_graph.json", "parts_lib.py"):
            if os.path.isfile(os.path.join(a.work, name)):
                shutil.copy2(os.path.join(a.work, name), cdir)

    modes = ["clay", "normal", "overlay", "parts"] if a.mode == "critic" else [a.mode]
    user_views = a.views.split(",") if a.views else None

    def add(label, path, mode, view, **extra):
        files.append({"label": label, "path": os.path.abspath(path), "mode": mode, "view": view, **extra})

    scene = reset_scene(bpy)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    scene.collection.objects.link(cam)
    scene.camera = cam

    if "clay" in modes or "normal" in modes:
        ob = add_mesh(bpy, scene, "model", v, t)
        for mode in ("clay", "normal"):
            if mode not in modes:
                continue
            if mode == "normal":
                set_normal_colors(ob.data)
            set_shading(scene, mode)
            for view in user_views or VIEWS_3D:
                path = os.path.join(outdir, f"{mode}_{view}.png")
                render_view(bpy, scene, cam, v, view, long_edge, path)
                add(f"{mode}_{view}", path, mode, view)
        bpy.data.objects.remove(ob)

    if "parts" in modes:
        cols = palette(len(parts))
        legend, pc = [], []
        for p, c in zip(parts, cols):
            ob = add_mesh(bpy, scene, f"part_{p['index']}", p["verts"], p["tris"])
            ob.color = (*srgb_to_linear(c), 1.0)
            legend.append((p["index"], p["name"], c))
            pc.append((p["index"], c))
        set_shading(scene, "parts")
        scene.display.shading.show_object_outline = False
        for view in user_views or PARTS_VIEWS:
            path = os.path.join(outdir, f"parts_{view}.png")
            render_view(bpy, scene, cam, v, view, long_edge, path)
            vis = label_parts(path, pc, legend, max_edge)
            add(f"parts_{view}", path, "parts", view, visible_parts=vis)
        scene.display.shading.show_object_outline = True
        for ob in [o for o in scene.objects if o.name.startswith("part_")]:
            bpy.data.objects.remove(ob)

    if "overlay" in modes:
        cms = G.concept_masks(spec, a.spec, long_edge) if a.spec else {}
        if not cms:
            warnings.append("no orthographic concept.views in the spec: no overlays")
        for view, cm in cms.items():
            if user_views and view not in user_views:
                continue
            mm = G.model_mask(v, t, view, long_edge)
            path = os.path.join(outdir, f"overlay_{view}.png")
            stats = overlay_png(cm, mm, view, path, max_edge)
            add(f"overlay_{view}", path, "overlay", view, **stats)

    if a.mode == "critic" and a.work:
        n, sdir = previous_snapshot(a.work, data["code_hash"])
        if sdir:
            pv, pt, _ = G.load_glb(os.path.join(sdir, "assembled.glb"))
            ob = add_mesh(bpy, scene, "prev", pv, pt)
            set_shading(scene, "clay")
            path = os.path.join(outdir, "prev_34.png")
            render_view(bpy, scene, cam, pv, "34", long_edge, path)
            add("prev_34", path, "clay", "34", snapshot=n)
            bpy.data.objects.remove(ob)

    # clay/normal/parts renders are already <= long_edge <= max_edge; parts and overlays fitted above
    data.update({"outdir": os.path.abspath(outdir), "mode": a.mode, "files": files,
                 "render_long_edge": long_edge, "max_long_edge": max_edge,
                 "view_dirs": {k: raster.VIEW_DIRS[k] for k in VIEWS_3D}})
    artifacts = {f["label"]: f["path"] for f in files}
    checks = [common.check("render.files", "info", value=len(files))]
    return outdir, checks, warnings, artifacts, data


def main():
    p = common.make_parser(__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--work")
    src.add_argument("--input")
    p.add_argument("--spec")
    p.add_argument("--mode", default="critic", choices=["critic", "parts", "clay", "normal", "overlay"])
    p.add_argument("--views")
    p.add_argument("--outdir")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    out = a.out
    try:
        settings, spec = common.load_settings(a.spec)
        outdir, checks, warnings, artifacts, data = run(a, settings, spec)
        out = out or os.path.join(outdir, "renders.json")
    except Exception as e:  # noqa: BLE001
        out = out or os.path.join(a.work or os.path.dirname(os.path.abspath(a.input)), "renders.json")
        common.write_error(out, TOOL, e)
        sys.exit(1)
    common.write_result(out, TOOL, checks, warnings=warnings, artifacts=artifacts, data=data,
                        source=os.path.join(a.work, "assembled.glb") if a.work else a.input,
                        spec_path=a.spec)


if __name__ == "__main__":
    main()
