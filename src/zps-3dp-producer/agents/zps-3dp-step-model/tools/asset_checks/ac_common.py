"""Shared helpers for asset_checks. Measurement only: scripts report numbers and
pass/fail against thresholds given in the spec; they never judge art quality.

Run inside Blender:
  blender -b scene.blend --python <script>.py -- --spec spec.json --out result.json
or with the bpy module:
  python <script>.py --input scene.blend --spec spec.json --out result.json
"""
import argparse
import math
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import bpy  # noqa: E402
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

TOOL_VERSION = "0.3.0"
INPUT = None   # --input, recorded as source_file (a GLB leaves bpy.data.filepath empty); finalize matches on it


def parse_args(extra=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True, help="checks spec JSON (thresholds come from the task)")
    p.add_argument("--out", required=True, help="result JSON path")
    p.add_argument("--input", help=".blend/.glb/.gltf to open (optional when blender already opened it)")
    for args, kwargs in (extra or []):
        p.add_argument(*args, **kwargs)
    a = p.parse_args(argv)
    if a.input:
        global INPUT
        INPUT = os.path.abspath(a.input)
        load_input(a.input)
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    return a, spec


def load_input(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(path))
    elif ext in (".glb", ".gltf"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
        # glTF splits vertices at every UV seam and hard edge; weld exact duplicates back so
        # closed/loose-part/duplicate-vertex checks see the real topology. Corner normals and
        # UVs are corner data and survive the weld.
        import bmesh
        for ob in bpy.context.scene.objects:
            if ob.type == "MESH":
                bm = bmesh.new()
                bm.from_mesh(ob.data)
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
                bm.to_mesh(ob.data)
                bm.free()
    else:
        raise ValueError(f"Unsupported input: {path}")


def file_sha256(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# How target_objects() resolved spec.objects. write_result() turns it into an "objects" check.
#   mode "joined": none of the spec objects exist and the scene holds exactly one mesh (the
#   optimize path joins every mesh into one object named after the asset); that mesh is checked.
#   mode "missing": some spec objects are absent; the others are checked and "objects" fails.
TARGETS = {}


class TargetError(Exception):
    """No object to check. run_main writes a fail result (not an error) for it."""


def target_objects(spec):
    names = spec.get("objects")
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]
    TARGETS.clear()
    if not names:
        return meshes
    missing = [n for n in names if n not in bpy.data.objects]
    found = [n for n in names if n in bpy.data.objects]
    if not missing:
        return [bpy.data.objects[n] for n in names]
    if not found and len(meshes) == 1:
        y = meshes[0].name
        TARGETS.update(mode="joined", spec_objects=list(names), missing=missing, object=y,
                       reason=f"spec objects {missing} not found; checking the single mesh {y} "
                              "(optimize joins objects)")
        print(f"[ac_common] warning: {TARGETS['reason']}")
        return meshes
    TARGETS.update(mode="missing", spec_objects=list(names), missing=missing, found=found,
                   scene_meshes=[o.name for o in meshes],
                   reason=f"spec objects {missing} not in the scene (scene meshes: "
                          f"{[o.name for o in meshes]})")
    if not found:
        raise TargetError(TARGETS["reason"])
    return [bpy.data.objects[n] for n in found]


def spec_object_check(check_name, name, what="per-object spec key"):
    """Check for a spec key about an object that is not in the scene: not_checked when the
    optimize path joined it (TARGETS mode joined), else fail."""
    if TARGETS.get("mode") == "joined":
        return check(check_name, "not_checked",
                     note=f"{what}: {TARGETS['reason']}; '{name}' no longer exists as an object. "
                          "Check it on the input model")
    return check(check_name, "fail", note=f"{what}: object '{name}' not in the scene")


def _targets_check():
    if TARGETS.get("mode") == "joined":
        return check("objects", "info", {"spec": TARGETS["spec_objects"], "checked": [TARGETS["object"]]},
                     note=TARGETS["reason"])
    if TARGETS.get("mode") == "missing":
        return check("objects", "fail", {"missing": TARGETS["missing"], "found": TARGETS["found"]},
                     note=TARGETS["reason"] + "; only the found objects were checked")
    return None


def camera_target_object(cam_cfg, objs):
    """camera.target_object, or the first target object. Under TARGETS mode joined a missing
    target maps to the joined mesh, and so does a missing target when there is exactly one
    target mesh (returns a note saying so)."""
    tname = cam_cfg.get("target_object")
    if not tname:
        return objs[0], None
    if tname in bpy.data.objects:
        return bpy.data.objects[tname], None
    if TARGETS.get("mode") == "joined":
        return objs[0], (f"camera.target_object '{tname}' not found ({TARGETS['reason']}); calibrating "
                         f"on the whole joined mesh {objs[0].name}, so the target height covers every part")
    if len(objs) == 1:  # same fallback as target_objects: optimize joins objects into one mesh
        return objs[0], (f"camera.target_object '{tname}' not found; using the single mesh {objs[0].name} "
                         "(optimize joins objects), so the target height covers the whole asset")
    raise TargetError(f"camera.target_object '{tname}' not in the scene")


def evaluated_mesh(obj):
    """Mesh after modifiers, in world space, as a temporary copy."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, depsgraph=dg)
    me.transform(obj.matrix_world)
    return me


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


def write_result(path, script, spec_path, checks, data=None, source=None, overall=None):
    src = source or bpy.data.filepath or INPUT
    tc = _targets_check()
    if tc and not any(c.get("check") == "objects" for c in checks):
        checks = [tc] + list(checks)
        data = dict(data or {})
        data.setdefault("warnings", []).append(tc["note"])
        data["target_objects"] = dict(TARGETS)
    statuses = [c["status"] for c in checks]
    if overall is None:
        overall = "fail" if "fail" in statuses else ("pass" if "pass" in statuses else "info")
    result = {
        "tool": f"asset_checks/{script}",
        "tool_version": TOOL_VERSION,
        "blender_version": bpy.app.version_string,
        "run_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file": src,
        "source_sha256": file_sha256(src),
        "spec": os.path.abspath(spec_path) if spec_path else None,
        "spec_sha256": file_sha256(spec_path),
        "summary": {s: statuses.count(s) for s in ("pass", "fail", "info", "not_checked", "error")},
        "overall": overall,
        "checks": checks,
        "data": data or {},
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{script}] overall={result['overall']} {result['summary']} -> {path}")
    return result


def _argv_value(flag):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(flag)
    known, _ = p.parse_known_args(argv)
    return getattr(known, flag.lstrip("-").replace("-", "_"))


def run_main(main, script):
    """Run a check's main() so every outcome leaves a result JSON at --out:
    - TargetError (no spec object in the scene): overall fail with the "objects" check, exit 0;
    - any other exception, or SystemExit with a message / non-zero code: overall error, the
      traceback in data, exit 1 (Blender: run with --python-exit-code 1 so the code survives).
    Without a parsable --out nothing can be written; the exception propagates (exit != 0)."""
    import traceback
    try:
        main()
        return
    except TargetError as exc:
        out, spec = _argv_value("--out"), _argv_value("--spec")
        if not out:
            raise
        checks = [check("objects", "fail", {"missing": TARGETS.get("missing")}, note=str(exc))]
        TARGETS.clear()
        write_result(out, script, spec, checks, {"error": str(exc)})
        return
    except SystemExit as exc:
        if exc.code in (None, 0):
            raise
        err, tb = f"SystemExit({exc.code!r})", traceback.format_exc()
    except Exception as exc:  # noqa: BLE001  never leave the gate without a JSON
        err, tb = repr(exc), traceback.format_exc()
    out, spec = _argv_value("--out"), _argv_value("--spec")
    print(tb, file=sys.stderr)
    if out:
        TARGETS.clear()
        write_result(out, script, spec, [check("run", "error", note=err)],
                     {"error": err, "traceback": tb}, overall="error")
    sys.exit(1)


def r(x, n=4):
    return round(float(x), n)


# ---------------------------------------------------------------- v0.2 helpers
def spec_path(spec_file, rel):
    """Paths inside a spec are relative to the folder holding the spec."""
    if rel is None:
        return None
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(spec_file)), rel))


def world_verts(objs):
    out = []
    for o in objs:
        me = evaluated_mesh(o)
        out += [v.co.copy() for v in me.vertices]
        bpy.data.meshes.remove(me)
    return out


def bbox(pts):
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def place_camera(cam, center, az, el, dist):
    """az 0 = camera on -Y looking +Y; el = angle above the horizon."""
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = center + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()


def projected_box(scene, cam, pts):
    ps = [world_to_camera_view(scene, cam, p) for p in pts]
    xs, ys = [p.x for p in ps], [p.y for p in ps]
    return min(xs), max(xs), min(ys), max(ys)


def game_camera(scene, cam_cfg, name="ac_game_cam"):
    """The game camera from spec.camera, shared by every script.

    Keys: type ("persp" | "ortho"), fov_v_deg (vertical FOV, as engines give it) or lens_mm,
    ortho_scale, distance_m, look_at [x,y,z], azimuth_deg, elevation_deg, screen [w,h].
    Fixed (a real game camera) when perspective has distance_m or ortho has ortho_scale;
    otherwise the caller frames/calibrates and must report numbers as info only.
    Returns (camera object, fixed: bool).
    """
    data = bpy.data.cameras.new(name)
    ortho = cam_cfg.get("type") == "ortho"
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = cam_cfg.get("ortho_scale", 5.0)
    if "fov_v_deg" in cam_cfg:
        data.sensor_fit = "VERTICAL"
        data.angle_y = math.radians(cam_cfg["fov_v_deg"])
    else:
        data.sensor_fit = "HORIZONTAL"
        data.lens = cam_cfg.get("lens_mm", 50)
    data.clip_end = 1000
    cam = bpy.data.objects.new(name, data)
    scene.collection.objects.link(cam)
    sw, sh = cam_cfg.get("screen", [1920, 1080])
    scene.render.resolution_x, scene.render.resolution_y = sw, sh
    scene.render.resolution_percentage = 100
    fixed = ("ortho_scale" in cam_cfg) if ortho else ("distance_m" in cam_cfg)
    return cam, fixed


def camera_target(cam_cfg, pts):
    lo, hi = bbox(pts)
    return Vector(cam_cfg["look_at"]) if "look_at" in cam_cfg else (lo + hi) / 2


def _read_image(path):
    import cv2
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError(f"cannot read image: {path}")
    if im.ndim == 2:  # single channel (grey)
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.dtype != np.uint8:
        im = (im / 257).astype(np.uint8)
    return im


def concept_mask(path, background=None):
    """Foreground mask of a concept image (uint8 0/1), width, height.

    Alpha channel when present. Otherwise a pixel is background when it is bright and grey:
    min channel > background.max_min_channel (default 225) and saturation <
    background.min_saturation (default 0.12). Holes are filled; specks < 0.2 % are dropped.
    """
    import cv2
    im = _read_image(path)
    h, w = im.shape[:2]
    if im.shape[2] == 4 and im[:, :, 3].min() < 250:
        m = (im[:, :, 3] > 127).astype(np.uint8)
    else:
        bg = background or {}
        rgb = im[:, :, :3].astype(np.float32)
        mn, mx = rgb.min(axis=2), rgb.max(axis=2)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        is_bg = (mn > bg.get("max_min_channel", 225)) & (sat < bg.get("min_saturation", 0.12))
        m = (~is_bg).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 0.002 * w * h:
            keep[lab == i] = 1
    cnts, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(keep)
    cv2.drawContours(filled, cnts, -1, 1, thickness=-1)
    return filled, w, h


def render_alpha(scene, path, objs, w, h):
    """Silhouette of objs from scene.camera at w x h: bool array (top row first).
    Other objects are hidden for the render and restored afterwards."""
    import cv2
    keep = {o.name: o.hide_render for o in scene.objects}
    eng, ft = scene.render.engine, scene.render.film_transparent
    rx, ry, rp = scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage
    for o in scene.objects:
        o.hide_render = o not in objs
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "SINGLE"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = w, h, 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in scene.objects:
        if o.name in keep:
            o.hide_render = keep[o.name]
    scene.render.engine, scene.render.film_transparent = eng, ft
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = rx, ry, rp
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    return im[:, :, 3] > 127



# ---------------------------------------------------------------- v0.3 helpers
_CONFIG = None


def config_value(dotted):
    """A default from the skill's config.yaml (via tools/lib/common.load_config), or None.

    Use only when the spec omits a key, and label the check note with
    `source: config_default` so the reader knows the task did not set it."""
    global _CONFIG
    if _CONFIG is None:
        try:
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from lib import common as lib_common
            _CONFIG = lib_common.load_config() or {}
        except Exception as exc:  # no yaml / no config: behave as if the key were absent
            print(f"[ac_common] config.yaml not readable: {exc!r}")
            _CONFIG = {}
    cur = _CONFIG
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def threshold(spec_block, key, config_key=None):
    """(value, source) for a threshold: the spec first, then config.yaml, else (None, None).
    source is "spec" or "config_default"."""
    if spec_block and spec_block.get(key) is not None:
        return spec_block[key], "spec"
    if config_key:
        v = config_value(config_key)
        if v is not None:
            return v, "config_default"
    return None, None


def source_note(source, config_key=None, extra=None):
    """Check note naming where a threshold came from."""
    if source == "config_default":
        s = f"source: config_default ({config_key}); the task spec did not set it"
    elif source:
        s = f"source: {source}"
    else:
        s = None
    if extra:
        s = f"{s}; {extra}" if s else extra
    return s


def fibonacci_dirs(n):
    """n unit vectors spread evenly over the sphere."""
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(max(0.0, 1 - z * z))
        out.append(Vector((rad * math.cos(golden * i), rad * math.sin(golden * i), z)))
    return out


def calibrate_distance(scene, cam, center, az, el, dist, pts, target_px, screen_h):
    """Solve the camera distance (or ortho_scale) so pts are target_px tall on screen.
    Same loop as render_rig's calibration mode. Returns the distance."""
    ortho = cam.data.type == "ORTHO"
    place_camera(cam, center, az, el, dist)
    for _ in range(8):
        _x0, _x1, y0, y1 = projected_box(scene, cam, pts)
        m = (y1 - y0) * screen_h
        if m <= 0:
            break
        if ortho:
            cam.data.ortho_scale *= m / target_px
        else:
            dist *= m / target_px
        place_camera(cam, center, az, el, dist)
    return dist
