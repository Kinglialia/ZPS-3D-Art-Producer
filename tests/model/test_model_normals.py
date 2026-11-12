"""The smooth normals join_mesh writes: a flat face beside a bevel stays flat, only the bevel strip blends."""
import sys

import numpy as np

from modelkit import TOOLS

V = np.array([(0, 0, 0), (1, 0, 0), (1, 0, 0.9), (0.1, 0, 0.9), (0, 0, 0.9), (0, 0, 0.8),
              (0, 0.1, 1), (1, 0.1, 1), (1, 1, 1), (0, 1, 1)], float)
FRONT = [(0, 1, 2), (0, 2, 3), (0, 3, 5), (5, 3, 4)]
CHAMFER = [(4, 3, 6), (3, 2, 7), (3, 7, 6)]
TOP = [(6, 7, 8), (6, 8, 9)]


def normals():
    sys.path.insert(0, str(TOOLS))
    import join_mesh
    return join_mesh.weighted_normals(V, np.array(FRONT + CHAMFER + TOP))


def angles(n, face, axis):
    return np.degrees(np.arccos(np.clip(n[np.unique(face)] @ axis, -1, 1)))


def test_a_flat_face_keeps_its_own_normal_beside_a_chamfer_even_where_a_small_triangle_holds_its_corner():
    """A box whose top front edge is a 45 deg chamfer. Averaged normals tilt the front and top faces towards the
    chamfer by up to 22.5 deg: the owner saw that as a light gradient across a face that should read flat. The front
    corner at (0, 0, 0.9) sits in a 0.005 m2 triangle, smaller than the chamfer triangle there, so the whole flat
    face, not the triangle at the corner, must outweigh the chamfer."""
    n = normals()
    assert angles(n, FRONT, (0, -1, 0)).max() < 2
    assert angles(n, TOP, (0, 0, 1)).max() < 2


def test_the_chamfer_strip_carries_the_blend_from_one_face_to_the_other():
    """The strip still shades round: its corners point like the face beside them, so its normals turn about 90 deg."""
    n = normals()[np.unique(CHAMFER)]
    assert np.degrees(np.arccos(np.clip(n @ n.T, -1, 1))).max() > 80


def uv_sphere(nu, nv):
    """Unit sphere: two poles, nv - 1 rings of nu vertices, quads cut in two triangles, triangle fans at the poles."""
    th, ph = np.pi * np.arange(1, nv) / nv, 2 * np.pi * np.arange(nu) / nu
    v = np.concatenate([[(0, 0, 1)], np.stack([np.outer(np.sin(th), np.cos(ph)), np.outer(np.sin(th), np.sin(ph)),
                                               np.repeat(np.cos(th)[:, None], nu, 1)], -1).reshape(-1, 3), [(0, 0, -1)]])
    ring = lambda i, j: 1 + i * nu + j % nu  # noqa: E731
    f = [(0, ring(0, j), ring(0, j + 1)) for j in range(nu)]
    for i in range(nv - 2):
        for j in range(nu):
            f += [(ring(i, j), ring(i + 1, j), ring(i + 1, j + 1)), (ring(i, j), ring(i + 1, j + 1), ring(i, j + 1))]
    f += [(ring(nv - 2, j), len(v) - 1, ring(nv - 2, j + 1)) for j in range(nu)]
    return v, np.array(f)


def corner_angle_normals(v, f):
    t = v[f]
    cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a, b = t[:, [1, 2, 0]] - t, t[:, [2, 0, 1]] - t
    w = np.arctan2(np.linalg.norm(np.cross(a, b), axis=2), np.einsum("mkj,mkj->mk", a, b))
    n = np.zeros_like(v)
    np.add.at(n, f.ravel(), (w[:, :, None] * (cr / np.linalg.norm(cr, axis=1, keepdims=True))[:, None]).reshape(-1, 3))
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def weighted(v, f):
    sys.path.insert(0, str(TOOLS))
    import join_mesh
    return join_mesh.weighted_normals(v, f)


def test_a_uv_sphere_keeps_the_normals_of_a_sphere():
    """Each quad of a UV sphere is flat, and the quads of two rings differ in size: squared-area weights tilted the
    normals 12.8 deg on an 8 x 6 sphere. A round part must shade round."""
    v, f = uv_sphere(16, 12)
    assert np.degrees(np.arccos(np.clip(np.sum(weighted(v, f) * v, 1), -1, 1))).max() < 2


def test_a_rock_with_no_flat_face_gets_corner_angle_normals():
    """A low-poly rock has no flat face of more than one triangle; squared-area weights moved its normals up to 42 deg."""
    v, f = uv_sphere(10, 7)
    v = v * (1 + 0.25 * np.random.default_rng(1).standard_normal((len(v), 1)))
    got, want = weighted(v, f), corner_angle_normals(v, f)
    assert np.degrees(np.arccos(np.clip(np.sum(got * want, 1), -1, 1))).max() < 1
