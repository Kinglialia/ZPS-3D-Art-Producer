# bpy cookbook (Blender 4.2+ / 5.x, headless)

Tested patterns for `self_build`. They avoid `bpy.ops` where possible, because operators depend on UI context and often fail in background mode. Verify against the installed Blender version once when building the skill; if an API changed, fix it here, not in each script.

## Setup

```python
import bpy, bmesh
from mathutils import Vector

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def new_object(name, bm):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj
```

## Primitives with exact dimensions

```python
def make_box(name, size, location=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = new_object(name, bm)
    obj.location = location
    return obj

def make_cylinder(name, radius, height, segments=12, location=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments,
                          radius1=radius, radius2=radius, depth=height)
    obj = new_object(name, bm)
    obj.location = location
    return obj
```
Pitfall: `create_cube` and `create_cone` are centered on the origin; place parts by their center, not their base.

## Apply modifiers without operators

```python
def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(dg)
    new_mesh = bpy.data.meshes.new_from_object(evaluated)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_mesh
    bpy.data.meshes.remove(old)
```

## Bevel (low-poly)

```python
mod = obj.modifiers.new("Bevel", "BEVEL")
mod.width = 0.01          # meters
mod.segments = 1          # 1–2 for mobile
mod.limit_method = "ANGLE"
apply_modifiers(obj)
```
Pitfall: width larger than half the thinnest wall makes the geometry overlap itself.

## Inset and extrude a face region

```python
bm = bmesh.new(); bm.from_mesh(obj.data)
top = [f for f in bm.faces if f.normal.z > 0.99]
res = bmesh.ops.inset_region(bm, faces=top, thickness=0.02, depth=0.0)
ext = bmesh.ops.extrude_face_region(bm, geom=top)
verts = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
bmesh.ops.translate(bm, vec=Vector((0, 0, -0.03)), verts=verts)
bmesh.ops.delete(bm, geom=top, context="FACES")   # remove the original faces left inside
bm.to_mesh(obj.data); bm.free()
```
Pitfall: after `extrude_face_region`, the original faces stay in place and leave interior geometry unless deleted.

## Array and mirror

```python
arr = obj.modifiers.new("Array", "ARRAY")
arr.count = 5
arr.relative_offset_displace = (1.1, 0, 0)

mir = obj.modifiers.new("Mirror", "MIRROR")
mir.use_axis = (True, False, False)
mir.use_clip = True
mir.use_mirror_merge = True
apply_modifiers(obj)
```

## Solidify (thin panels)

```python
sol = obj.modifiers.new("Solidify", "SOLIDIFY")
sol.thickness = 0.02
apply_modifiers(obj)
```

## Boolean and union: use manifold3d, not Blender's Boolean

Blender's Boolean modifier often fails on coplanar or touching faces. The skill unions parts with `manifold3d`, which guarantees a closed manifold result. Pattern (outside or inside Blender, via trimesh arrays):

```python
import numpy as np
import manifold3d as m3d

def to_manifold(verts, tris):
    mesh = m3d.Mesh(vert_properties=np.asarray(verts, dtype=np.float32),
                    tri_verts=np.asarray(tris, dtype=np.uint32))
    return m3d.Manifold(mesh)

def union_all(parts):            # parts: list of (verts, tris)
    result = to_manifold(*parts[0])
    for v, t in parts[1:]:
        result = result + to_manifold(v, t)   # '+' is union, '-' difference, '^' intersection
    out = result.to_mesh()
    return out.vert_properties[:, :3], out.tri_verts

def intersection_volume(a, b):   # used by the penetration gate
    return (to_manifold(*a) ^ to_manifold(*b)).volume()
```
Pitfalls: each input must itself be closed; check the exact API names against the installed manifold3d version once when building the skill.

## Join parts

```python
def join(objects, name):
    target = objects[0]
    with bpy.context.temp_override(active_object=target, object=target,
                                   selected_objects=objects,
                                   selected_editable_objects=objects):
        bpy.ops.object.join()
    target.name = name
    return target
```

## Finish: normals, origin at bottom center, apply transform

```python
def finish(obj):
    obj.data.transform(obj.matrix_world)
    obj.matrix_world.identity()
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]; zs = [v.co.z for v in bm.verts]
    offset = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))
    bmesh.ops.translate(bm, vec=-offset, verts=bm.verts)
    bm.to_mesh(obj.data); bm.free()
```

## Health check (run after every step)

```python
def health(obj, eps=1e-8):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    report = {
        "faces": len(bm.faces),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
        "zero_area_faces": sum(1 for f in bm.faces if f.calc_area() < eps),
        "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
        "dimensions": tuple(round(d, 4) for d in obj.dimensions),
    }
    bm.free()
    print(report)
    return report
```
A single part that is open by design (for example a panel before solidify) will report non-manifold edges; the check that must pass is the one on the joined final object.

## Export

```python
bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=False)
```
