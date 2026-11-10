"""UV of the joined mesh with the kit's xatlas_unwrap() (D24.4), then the untextured GLB. Runs in Blender.

Usage: BLENDER -b --python tools/unwrap.py -- --final F
Opens F/<id>.blend of join_mesh.py, triangulates, and calls optimize/bake.py xatlas_unwrap at spec uv.resolution
with padding uv.min_padding_px between charts. Never the bake.py main (rebake): no bake, no new unwrap algorithm.
xatlas packs charts to about 0.5 px from the atlas border, so the UVs are scaled into [m, 1 - m],
m = padding / resolution: the border gets the same padding as the gap between charts (check_uv_edge.py).
No xatlas: error, no Smart UV Project fallback, because a non-deterministic unwrap breaks the mesh lock.
Saves F/<id>.blend with the UV (no .blend1 backup; stray ones in F are removed) and exports F/<id>-untextured.glb.
Writes F/review/unwrap.json (data.how: in-process or system python3). Exit 0, 1 on error.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("lib", "optimize"):
    sys.path.insert(0, os.path.join(HERE, sub))
import bootstrap  # noqa: E402,F401

import common  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

TOOL = "model/unwrap"


def run(final):
    import bpy
    import bake
    import optbpy
    spec = common.read_json(os.path.join(final, "spec.json"))
    aid, res, pad = spec["asset"], spec["uv"]["resolution"], spec["uv"]["min_padding_px"]
    blend = os.path.join(os.path.abspath(final), f"{aid}.blend")
    bpy.ops.wm.open_mainfile(filepath=blend)
    ob = bpy.data.objects[aid]
    optbpy.triangulate(ob)
    v, f = optbpy.mesh_arrays(ob)
    warnings = []
    uvt, how = bake.xatlas_unwrap(v, f, res, pad, warnings)
    if uvt is None:
        raise RuntimeError(how)
    m = pad / res
    uvt = m + uvt * (1 - 2 * m)
    bake.set_uv_layer(ob, uvt, name="UVMap")
    fp = bpy.context.preferences.filepaths
    keep, fp.save_version = fp.save_version, 0
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    fp.save_version = keep
    for p in glob.glob(os.path.join(glob.escape(os.path.abspath(final)), "*.blend1")):
        os.remove(p)
    glb = os.path.join(os.path.abspath(final), f"{aid}-untextured.glb")
    optbpy.export_glb(glb, [ob])
    checks = [common.check("unwrap.how", "info", how), common.check("unwrap.border_inset_px", "info", pad),
              common.check("unwrap.occupancy", "info", common.r(bake.uv_occupancy(uvt), 3))]
    return checks, {"how": how, "resolution": res, "padding_px": pad, "tris": len(f), "glb": glb}, warnings


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    a = p.parse_args(common.script_argv())
    out = os.path.join(a.final, "review", "unwrap.json")
    try:
        checks, data, warnings = run(a.final)
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e)
        sys.exit(1)
    common.write_result(out, TOOL, checks, data=data, warnings=warnings)


if __name__ == "__main__":
    require_root()
    main()
