"""Placed guns lie where FNV's did: the reference takes back the turn and offset its mesh was given.

See: docs/fork/fo4_spikes.md#placed-guns
"""

from types import SimpleNamespace

import numpy as np

from fo4_import.nif import gun
from fo4_import.spike import guns as G
from fo4_import.spike.scol import rotation


def _world(position: tuple, angle: tuple, scale: float, point: np.ndarray) -> np.ndarray:
    """Where a reference at `position`, `angle`, `scale` puts model point `point`."""
    return np.array(position) + scale * rotation(angle) @ point


def test_a_mesh_point_stays_where_fnv_put_it():
    """A point of FNV's model, turned and offset into the FO4 mesh, lands on the same world spot."""
    matrix = np.eye(4)
    matrix[:3, :3] = gun.AXES @ gun.TIP[1]
    matrix[3, :3] = (1.5, -4.0, 2.25)
    position, angle, scale = (100.0, -20.0, 5.0), (0.3, -0.7, 2.1), 1.3
    at, turn = G.turned(position, angle, scale, matrix)
    for point in np.array([[10.0, 0.0, 0.0], [0.0, 3.0, -2.0], [-7.0, 1.0, 4.0]]):
        mesh = point @ matrix[:3, :3] + matrix[3, :3]
        assert np.allclose(_world(at, turn, scale, mesh), _world(position, angle, scale, point))


def test_an_fo4_model_gun_takes_fo4_axes_and_no_offset():
    """A gun never built on FNV's mesh turns by gun.AXES alone; a built one by its own placement."""
    guns = G.Guns.__new__(G.Guns)
    guns.turns = {0x1234: np.full((4, 4), 2.0)}
    plain = guns.turn(0x9999)
    assert np.array_equal(plain[:3, :3], gun.AXES) and not plain[3, :3].any()
    assert guns.turn(0x1234)[0, 0] == 2.0


def test_a_gun_part_under_a_child_node_is_found_in_the_guns_frame():
    """_fnv_parts finds a shape under a nested node, moved by that node; a mesh with no shapes lays out as None."""
    node = {'rotation': (1, 0, 0, 0, 1, 0, 0, 0, 1), 'scale': 2.0, 'translation': (0, 0, 5), 'children': [2]}
    shape = {'name': 0, 'rotation': (1, 0, 0, 0, 1, 0, 0, 0, 1), 'scale': 1.0, 'translation': (0, 0, 0),
             'vertices': [{'position': (1, 0, 0)}]}
    root = {'rotation': (1, 0, 0, 0, 1, 0, 0, 0, 1), 'scale': 1.0, 'translation': (0, 0, 0), 'children': [1]}
    src = SimpleNamespace(strings=['Rock'], blocks=[('NiNode', root), ('NiNode', node), ('BSTriShape', shape)])
    name, points = gun._fnv_parts(src, np.eye(3))[2]
    assert name == 'Rock' and points.tolist() == [[2.0, 0.0, 5.0]]
    src.blocks[1][1]['children'] = []
    assert gun._fnv_parts(src) == {}
