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
