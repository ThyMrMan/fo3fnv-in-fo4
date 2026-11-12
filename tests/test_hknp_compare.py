"""tools/nif/hknp_compare: physics systems flattened and compared field by field, hulls as sets.

See: docs/fork/fo4_hknp_writer.md#check
"""

import struct

import numpy as np

from fo4_import.havok import packfile
from fo4_import.nif import hknp_convex, hknp_mesh, hknp_write
from fo4_import.nif.hknp_write import MASS, MOTION
from tools.nif import hknp_compare

CORNERS = hknp_convex.box_corners((1.0, 2.0, 3.0))


def _objects(mass: float = 5.0) -> list:
    """The packfile objects of a one-box dynamic system of `mass`."""
    body = bytearray(220)
    struct.pack_into('<f', body, MASS, mass)
    body[MOTION] = 3
    place = (np.zeros(3), (0.0, 0.0, 0.0, 1.0))
    data = hknp_write.system([(0, bytes(body), (CORNERS, 0.01, 7), place)])
    return packfile.read(data[4:]).objects


def _renamed(objects: list) -> list:
    """`objects` with every object name changed (pointers too), as another writer would name them."""
    names = {o['#']: f'#x{i}' for i, o in enumerate(objects)}

    def rename(value):
        """`value` with object names swapped."""
        if isinstance(value, dict):
            return {k: rename(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        return names.get(value, value) if isinstance(value, str) else value
    return [{'#': names[o['#']], 'class': o['class'], 'fields': rename(o['fields'])} for o in objects]


def test_a_system_matches_itself_under_other_object_names():
    """Object names do not count, only what the pointers reach."""
    objects = _objects()
    assert hknp_compare.diff(hknp_compare.flatten(objects), hknp_compare.flatten(_renamed(objects)), 1e-4) == {}


def test_a_shape_reached_twice_is_walked_once():
    """A shape met a second time is a leaf naming where it was first met."""
    flat = hknp_compare.flatten(_objects())
    assert flat['referencedObjects[0]'] == '-> bodyCinfos[0].shape'
    assert not any(p.startswith('referencedObjects[0].') for p in flat)


def test_box_hull_decodes_to_eight_corners_and_six_faces():
    """The polytope's relative arrays come back as its distinct corners and faces of four."""
    flat = hknp_compare.flatten(_objects())
    shape = flat['bodyCinfos[0].shape.hull']
    assert shape['points'].shape == (8, 3) and shape['faces'].shape == (6, 6)
    assert set(shape['faces'][:, 5]) == {4}


def test_a_changed_mass_shows_in_the_motion():
    """A heavier body differs in its motion's mass fields, not its shape."""
    found = hknp_compare.diff(hknp_compare.flatten(_objects(5.0)), hknp_compare.flatten(_objects(10.0)), 1e-4)
    assert {'motionCinfos[0].inverseMass', 'motionCinfos[0].massFactor'} <= found.keys()
    assert not any('.shape' in p for p in found)


def test_hull_rows_pair_by_position_whatever_their_order():
    """Rows in another order match; one moved row is the largest difference."""
    rows = np.array([[0, 0, 0, 1.0], [1, 0, 0, 2.0], [0, 1, 0, 3.0]])
    assert not hknp_compare.matched(rows[::-1], rows).any()
    moved = rows.copy()
    moved[1, 0] += 0.5
    assert hknp_compare.matched(moved, rows)[0] == 0.5


def test_hull_differences_name_counts_and_angles():
    """A face count and an angle byte off by one are reported under the hull's path."""
    points = np.eye(3)
    faces = np.array([[1, 0, 0, -1, 128, 4], [0, 1, 0, -1, 128, 4]], float)
    other = faces.copy()
    other[0, 4] = 127
    found = hknp_compare.diff({'s': {'points': points, 'faces': faces}}, {'s': {'points': points, 'faces': other}}, 1e-4)
    assert found == {'s.faces.angle': (hknp_compare.OFF_BY, 1.0)}
    found = hknp_compare.diff({'s': {'points': points, 'faces': faces}},
                              {'s': {'points': points, 'faces': faces[:1]}}, 1e-4)
    assert found == {'s.faces.len': (2, 1)}


def _mesh_leaf(shift: float, strip: int) -> dict:
    """The compared leaf of a two-triangle square whose second triangle is on `strip`, its far corner raised."""
    points = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, shift]])
    built = hknp_mesh.compressed('#m', hknp_mesh.Mesh(points, np.array([(0, 1, 2), (0, 2, 3)]), np.array([0, strip]),
                                                      [(1, 2), (1, 3)]))
    return hknp_compare.mesh(built[-1]['fields']['meshTree'])


def test_meshes_match_within_a_step_and_report_moves_and_material_swaps():
    """The same square matches; a corner raised 0.5 is off by about that; a triangle on another strip is
    counted per material and has no match of its own material."""
    same = hknp_compare.diff({'m': _mesh_leaf(0.0, 0)}, {'m': _mesh_leaf(0.0, 0)}, 1e-4)
    assert same == {}
    moved = hknp_compare.diff({'m': _mesh_leaf(0.5, 0)}, {'m': _mesh_leaf(0.0, 0)}, 1e-4)
    assert list(moved) == ['m.triangles'] and moved['m.triangles'][1] > 0.4
    swapped = hknp_compare.diff({'m': _mesh_leaf(0.0, 1)}, {'m': _mesh_leaf(0.0, 0)}, 1e-4)
    assert swapped.keys() == {'m.materials[0].len', 'm.materials[1].len', 'm.triangles'}
    assert swapped['m.materials[0].len'] == (1, 2) and swapped['m.materials[1].len'] == (1, 0)


def test_packed_mass_properties_unpack():
    """A packed vector and frame read back within their packing step."""
    v = (0.25, -0.0625, 0.5)
    assert np.allclose(hknp_compare.unpack_vector(hknp_convex.pack_vector(v)), v, atol=1e-4)
    q = (0.0, 0.0, 0.3, 0.9539)
    assert np.allclose(hknp_compare.unpack_quaternion(hknp_convex.pack_quaternion(q)), q, atol=1 / 30000)


def test_summary_folds_bodies_and_counts_matching_pairs():
    """Every body's field counts once per pair; a pair with no difference counts as matching."""
    results = [('a.nif', 'compared', {'b[0].x': (1, 2), 'b[1].x': (1, 3)}), ('c.nif', 'compared', {}),
               ('d.nif', 'not covered', {})]
    lines = hknp_compare.summary(results, 1)
    assert '1 of 2 compared pairs match in every field' in lines
    assert any(line.split() == ['1', 'b[].x'] for line in lines)
