"""Export GLB, optionally run Khronos glTF-Validator, re-import in an empty scene and
compare with the source: objects, tris, dimensions, bottom z, materials, UV/colour
attributes and image resolutions.

Spec: objects, export.{path (required, .glb, relative to the spec), yup (default true),
  apply_modifiers (default true), skip_export (default false: check an existing GLB at path
  instead of exporting), validator (path to gltf_validator; default: search PATH),
  dim_tolerance_m (default 0.002), expect_unlit (optional bool: materials must / must not
  carry KHR_materials_unlit)}.
v0.2: reports which materials are unlit (KHR_materials_unlit) — an unshaded brief needs it,
unless the engine step sets the material by hand.
v0.3:
- glTF-Validator: `export.validator` (path), else `gltf_validator` on PATH, else
  `node gltf_validate.mjs` (this folder; uses the npm package `gltf-validator`, which is a library,
  not a CLI). Errors fail, warnings and infos are info. Nothing found: not_checked.
- file.size_mb vs validate.max_file_size_mb (else config validate.max_file_size_mb).
- file.vertices: vertices actually in the file (POSITION accessors) per mesh vs
  budget.max_vertices_exported (else config budgets.max_vertices_exported; 16-bit indices).
- Up axis and scale, read back from the file: the re-imported asset (importer: glTF Y-up -> Blender
  Z-up) must be height_m tall within dimensions_tolerance. A Z-up or centimetre export fails here.
- asset.pivot_bottom_center (when spec pivot is bottom_center): the bottom-centre of the
  re-imported asset's bbox lies within 1 cm of the file origin; per-object offsets are info.
Never writes final*.glb (finalize.py owns it, after the QA gate): an export.path whose basename
starts with "final" is redirected to <dirname of --out>/export_check.glb, with a warning.
The source .blend is never saved by this script.
"""
import json
import os
import struct
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import bootstrap  # noqa: E402,F401  (tools/.deps/blender-py<ver> on sys.path; before third-party imports)
import bpy  # noqa: E402

import ac_common as ac  # noqa: E402  (imports bpy first)
import bmesh  # noqa: E402


def snapshot(objs):
    out = {}
    for o in objs:
        me = ac.evaluated_mesh(o)
        bm = bmesh.new()
        bm.from_mesh(me)
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        bm.free()
        zs = [v.co.z for v in me.vertices]
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        imgs = set()
        for s in o.material_slots:
            if s.material and s.material.use_nodes:
                for n in s.material.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        imgs.add((n.image.name, tuple(n.image.size)))
        out[o.name] = {
            "tris": tris,
            "dimensions": [ac.r(max(v) - min(v)) for v in (xs, ys, zs)],
            "min_z": ac.r(min(zs)),
            "materials": sorted(s.material.name for s in o.material_slots if s.material),
            "uv_layers": len(me.uv_layers),
            "color_attributes": [c.name for c in me.color_attributes],
            "images": sorted([f"{n} {w}x{h}" for n, (w, h) in imgs]),
        }
        bpy.data.meshes.remove(me)
    return out


def glb_json(path):
    """The JSON chunk of a GLB."""
    with open(path, "rb") as f:
        b = f.read()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n])


def glb_unlit(path):
    """{material name: has KHR_materials_unlit} read from the GLB JSON chunk."""
    j = glb_json(path)
    return {m.get("name", str(i)): "KHR_materials_unlit" in (m.get("extensions") or {})
            for i, m in enumerate(j.get("materials", []))}


def glb_vertices(path):
    """{mesh name: vertices in the file} = sum of POSITION accessor counts over its primitives."""
    j = glb_json(path)
    acc = j.get("accessors", [])
    out = {}
    for i, m in enumerate(j.get("meshes", [])):
        out[m.get("name", str(i))] = sum(acc[p["attributes"]["POSITION"]]["count"]
                                          for p in m.get("primitives", []) if "POSITION" in p.get("attributes", {}))
    return out


def find_validator(ex):
    """Command prefix to run glTF-Validator, and a label; (None, reason) when none is usable."""
    if ex.get("validator"):
        return [ex["validator"], "-o"], ex["validator"]
    cli = shutil.which("gltf_validator")
    if cli:
        return [cli, "-o"], cli
    node = shutil.which("node")
    wrapper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gltf_validate.mjs")
    if node and os.path.isfile(wrapper):
        return [node, wrapper], "node gltf_validate.mjs (npm gltf-validator)"
    return None, "no gltf_validator on PATH and no node for gltf_validate.mjs"


def run_validator(ex, path, checks):
    cmd, label = find_validator(ex)
    if cmd is None:
        checks.append(ac.check("gltf_validator", "not_checked", note=label))
        return None
    proc = subprocess.run(cmd + [path], capture_output=True, text=True)
    try:
        vdata = json.loads(proc.stdout)
    except ValueError:
        checks.append(ac.check("gltf_validator", "fail", proc.returncode, note=(proc.stderr or proc.stdout)[:300]))
        return None
    if vdata.get("error") == "module_not_found":
        checks.append(ac.check("gltf_validator", "not_checked",
                               note="node found but the npm package gltf-validator is not installed "
                                    "(npm i -g gltf-validator)"))
        return None
    if "error" in vdata:
        checks.append(ac.check("gltf_validator", "fail", note=f"validator rejected the file: {vdata['error'][:300]}"))
        return vdata
    with open(path + ".validator.json", "w") as f:
        json.dump(vdata, f, indent=2)
    issues = vdata.get("issues", {})
    msgs = issues.get("messages", [])
    codes = lambda sev: sorted({m["code"] for m in msgs if m.get("severity") == sev})  # noqa: E731
    ne, nw = issues.get("numErrors", 0), issues.get("numWarnings", 0)
    checks.append(ac.check("gltf_validator.errors", "pass" if ne == 0 else "fail", ne, 0,
                           note=f"{label}; codes: {codes(0)}" if ne else label))
    checks.append(ac.check("gltf_validator.warnings", "info", nw, note=f"codes: {codes(1)}" if nw else None))
    checks.append(ac.check("gltf_validator.infos", "info", issues.get("numInfos", 0),
                           note=f"codes: {codes(2)}" if issues.get("numInfos") else None))
    return vdata


def main():
    a, spec = ac.parse_args()
    ex = spec.get("export", {})
    path = ac.spec_path(a.spec, ex["path"])
    warnings = []
    if not ex.get("skip_export") and os.path.basename(path).lower().startswith("final"):
        # final*.glb is finalize.py's output, written only after the QA gate passes
        redirected = os.path.join(os.path.dirname(os.path.abspath(a.out)), "export_check.glb")
        warnings.append(f"export.path {ex['path']} names a final*.glb; finalize.py owns final*.glb "
                        f"(it writes it only after QA passes), so export_check wrote {redirected} instead. "
                        "Set export.path to ../evidence/qa/export_check.glb")
        print(f"[export_check] warning: {warnings[-1]}")
        path = redirected
    tol = ex.get("dim_tolerance_m", 0.002)
    objs = ac.target_objects(spec)
    before = snapshot(objs)
    checks = []

    if ex.get("skip_export"):
        checks.append(ac.check("export.file", "pass" if os.path.isfile(path) else "fail",
                               os.path.getsize(path) if os.path.isfile(path) else None,
                               note="skip_export: checking the existing GLB"))
        if not os.path.isfile(path):
            ac.write_result(a.out, "export_check", a.spec, checks, {"glb": path})
            return
    else:
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_yup=ex.get("yup", True), export_apply=ex.get("apply_modifiers", True))
        checks.append(ac.check("export.file", "pass" if os.path.isfile(path) else "fail",
                               os.path.getsize(path) if os.path.isfile(path) else None))

    unlit = glb_unlit(path)
    exp_unlit = ex.get("expect_unlit")
    if exp_unlit is None:
        checks.append(ac.check("materials.unlit", "info", unlit))
    else:
        ok = bool(unlit) and all(v == exp_unlit for v in unlit.values())
        checks.append(ac.check("materials.unlit", "pass" if ok else "fail", unlit, exp_unlit))

    vdata = run_validator(ex, path, checks)

    # file size and vertices actually written
    size_mb = os.path.getsize(path) / (1024 * 1024)
    lim, src = ac.threshold(spec.get("validate"), "max_file_size_mb", "validate.max_file_size_mb")
    if lim is None:
        checks.append(ac.check("file.size_mb", "info", ac.r(size_mb, 3), note="no max_file_size_mb in spec or config"))
    else:
        checks.append(ac.check("file.size_mb", "pass" if size_mb <= lim else "fail", ac.r(size_mb, 3), lim,
                               note=ac.source_note(src, "validate.max_file_size_mb")))
    file_vx = glb_vertices(path)
    lim, src = ac.threshold(spec.get("budget"), "max_vertices_exported", "budgets.max_vertices_exported")
    for mname, nv in file_vx.items():
        if lim is None:
            checks.append(ac.check(f"file.vertices.{mname}", "info", nv))
        else:
            checks.append(ac.check(f"file.vertices.{mname}", "pass" if nv <= lim else "fail", nv, lim,
                                   note=ac.source_note(src, "budgets.max_vertices_exported",
                                                       "POSITION accessor counts in the file")))

    src_file = bpy.data.filepath
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except RuntimeError as exc:  # v0.3: a broken file is a result, not a crash
        checks.append(ac.check("file.reimport", "fail", note=f"Blender glTF import failed: {str(exc)[-300:]}"))
        ac.write_result(a.out, "export_check", a.spec, checks,
                        {"glb": path, "glb_sha256": ac.file_sha256(path), "file_vertices": file_vx,
                         "validator_info": (vdata or {}).get("info"), "before": before,
                         **({"warnings": warnings} if warnings else {})}, source=src_file)
        return
    imported = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    after = snapshot(imported)

    for name, b in before.items():
        m = after.get(name)
        if m is None:
            checks.append(ac.check(f"{name}.present_after_import", "fail", note=f"imported: {list(after)}"))
            continue
        checks.append(ac.check(f"{name}.tris", "pass" if m["tris"] == b["tris"] else "fail",
                               m["tris"], b["tris"]))
        dd = max(abs(x - y) for x, y in zip(m["dimensions"], b["dimensions"]))
        checks.append(ac.check(f"{name}.dimensions", "pass" if dd <= tol else "fail", m["dimensions"],
                               {"source": b["dimensions"], "tol_m": tol}))
        checks.append(ac.check(f"{name}.min_z", "pass" if abs(m["min_z"] - b["min_z"]) <= tol else "fail",
                               m["min_z"], b["min_z"]))
        checks.append(ac.check(f"{name}.uv_layers", "pass" if m["uv_layers"] >= min(1, b["uv_layers"]) else "fail",
                               m["uv_layers"], b["uv_layers"]))
        lost = [c for c in b["color_attributes"] if c not in m["color_attributes"]]
        checks.append(ac.check(f"{name}.color_attributes", "info", m["color_attributes"],
                               note=f"missing after import: {lost}; present != used by the engine material" if lost else
                               "present in file; confirm the engine material actually uses them"))
        checks.append(ac.check(f"{name}.images", "info", m["images"], note=f"source: {b['images']}"))
    # up axis / scale / pivot as the file gives them back
    pts = ac.world_verts(imported) if imported else []
    file_geo = None
    if pts:
        lo, hi = ac.bbox(pts)
        height = hi.z - lo.z
        bc = [(lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z]
        file_geo = {"bbox_min": [ac.r(v) for v in lo], "bbox_max": [ac.r(v) for v in hi],
                    "height_m": ac.r(height), "bottom_center": [ac.r(v) for v in bc]}
        hm = spec.get("height_m")
        if hm:
            htol = spec.get("dimensions_tolerance", 0.1)
            err = abs(height - hm) / hm
            checks.append(ac.check("file.height_m", "pass" if err <= htol else "fail", ac.r(height),
                                   {"height_m": hm, "tolerance": htol},
                                   note="re-imported bbox height (glTF Y-up -> Blender Z); a Z-up or cm "
                                        "export shows up here"))
        else:
            checks.append(ac.check("file.height_m", "info", ac.r(height), note="no height_m in spec"))
        per_obj = {}
        for o in imported:
            olo, ohi = ac.bbox(ac.world_verts([o]))
            org = o.matrix_world.translation
            per_obj[o.name] = [ac.r(org.x - (olo.x + ohi.x) / 2), ac.r(org.y - (olo.y + ohi.y) / 2),
                               ac.r(org.z - olo.z)]
        file_geo["object_origin_offset_from_bottom_center"] = per_obj
        if spec.get("pivot") == "bottom_center":
            ok = all(abs(v) <= 0.01 for v in bc)
            checks.append(ac.check("asset.pivot_bottom_center", "pass" if ok else "fail",
                                   [ac.r(v) for v in bc], "abs <= 0.01 m",
                                   note="bottom-centre of the re-imported asset relative to the file origin"))
            checks.append(ac.check("asset.object_pivots", "info", per_obj,
                                   note="per object: origin minus its own bbox bottom-centre"))
    ac.write_result(a.out, "export_check", a.spec, checks,
                    {"glb": path, "glb_sha256": ac.file_sha256(path),
                     "file_vertices": file_vx, "file_geometry": file_geo,
                     "validator_info": (vdata or {}).get("info"),
                     "before": before, "after": after,
                     **({"warnings": warnings} if warnings else {})}, source=src_file)


if __name__ == "__main__":
    ac.run_main(main, "export_check")
