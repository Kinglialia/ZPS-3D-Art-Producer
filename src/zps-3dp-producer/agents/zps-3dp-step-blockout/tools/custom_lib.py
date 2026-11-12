"""Shared `custom` part functions: generic and parametrized, usable for many kinds of object (D32).
A function that only one asset needs goes into that project's production/assets/<id>/custom_parts.py instead.
FUNCTIONS is the set of shared names a `custom` part may use.
bmesh loads inside Blender or with the bpy module; without it this file still imports, so check_schema.py can read FUNCTIONS."""

try:
    import bmesh
except ImportError:
    bmesh = None


def _bevel(bm, edges, r, seg):
    """Round toon edges: `seg` segments, radius r. No-op when r <= 0 or no edges."""
    if r <= 0 or not edges:
        return
    bmesh.ops.bevel(bm, geom=list(edges), offset=r, offset_type="OFFSET", segments=int(seg), profile=0.5,
                    affect="EDGES", clamp_overlap=True)


_BOX_EDGES = [("-X", "-Y"), ("-X", "+Y"), ("+X", "-Y"), ("+X", "+Y"), ("-X", "-Z"), ("-X", "+Z"),
              ("+X", "-Z"), ("+X", "+Z"), ("-Y", "-Z"), ("-Y", "+Z"), ("+Y", "-Z"), ("+Y", "+Z")]


def bevel_box(w, d, h, r, seg, mask):
    """Box with rounded edges. mask: bit k rounds the edge between the two faces _BOX_EDGES[k].
    Edges against another part stay sharp, so the joint has no notch."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    bm.normal_update()
    want = {frozenset(pair) for k, pair in enumerate(_BOX_EDGES) if int(mask) >> k & 1}

    def side(f):
        n = f.normal
        a = max(range(3), key=lambda i: abs(n[i]))
        return ("+" if n[a] > 0 else "-") + "XYZ"[a]
    _bevel(bm, [e for e in bm.edges if frozenset(side(f) for f in e.link_faces) in want], r, seg)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


FUNCTIONS = {f.__name__: f for f in (bevel_box,)}
