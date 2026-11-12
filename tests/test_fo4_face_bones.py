"""Sculpt regions through the face bones: controls per bone, the skeleton's moves, and the skinned part vertices.

See: docs/fork/fo4_facegen_plan.md#sculpt-regions
"""

import numpy as np

from fo4_import.face import face_bones as FB
from fo4_import.nif import blocks as K
from fo4_import.nif import file as F

ZERO = {'x': 0.0, 'y': 0.0, 'z': 0.0}
FB_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _limits(pos=ZERO, rot=ZERO, scale=ZERO) -> dict:
    """One Maxima or Minima entry."""
    return {'Position': pos, 'Rotation': rot, 'Scale': scale}


def _region(rid: int, bone: str, top: dict, bottom: dict) -> dict:
    """A region driving one bone."""
    return {'ID': rid, 'BonesA': [{'Bone': bone, 'Maxima': top, 'Minima': bottom}]}


def test_controls_take_maxima_above_zero_and_minima_below_summed_over_regions():
    """+0.5 of Maxima x 2 and -1 of Minima x -3 add up; scale's one control drives all three axes."""
    top = _limits(pos={'x': 2.0, 'y': 0.0, 'z': 0.0}, scale={'x': 0.1, 'y': 0.2, 'z': 0.0})
    bottom = _limits(pos={'x': -3.0, 'y': 0.0, 'z': 0.0})
    regions = [_region(1, 'bone_Nose', top, bottom), _region(2, 'bone_Nose', top, bottom)]
    out = FB.bone_controls(regions, [(1, (0.5, 0, 0, 0, 0, 0, 1.0)), (2, (-1.0, 0, 0, 0, 0, 0, 0)), (9, (1,) * 7)])
    assert list(out) == ['skin_bone_nose']
    assert np.allclose(out['skin_bone_nose'], [1.0 - 3.0, 0, 0, 0, 0, 0, 0.1, 0.2, 0.0])


def test_a_bone_move_is_translate_then_negated_zyx_rotation_then_scale():
    """A +90 degree z control turns x to -y; translation and scale land as given."""
    m = FB.local_move(np.array([1.0, 2.0, 3.0, 0.0, 0.0, 90.0, 1.0, 0.0, 0.0]))
    assert np.allclose(m[:3, 3], (1, 2, 3)) and np.allclose(m[:3, :3] @ (1, 0, 0), (0, -2, 0))
    assert np.allclose(FB.local_move(np.zeros(9)), np.eye(4))


def _skeleton() -> FB.FaceSkeleton:
    """Root, a parent node 10 up turned a quarter about z, and its child 1 along the parent's x."""
    nif = F.NifFile()
    quarter = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)

    def node(name, pos, rot, children):
        return 'NiNode', {'name': nif.string(name), 'extra': [], 'controller': -1, 'flags': 14, 'translation': pos,
                          'rotation': rot, 'scale': 1.0, 'collision': -1, 'children': children}
    nif.blocks = [node('Root', (0.0, 0.0, 0.0), FB_IDENTITY, [1]), node('Parent', (0.0, 0.0, 10.0), quarter, [2]),
                  node('Child', (1.0, 0.0, 0.0), FB_IDENTITY, [])]
    return FB.FaceSkeleton(nif)


def test_a_parents_move_reaches_its_child_in_the_childs_own_frame():
    """Moving the parent 2 along its x moves the child 2 along its own x too; nothing moved gives no moves."""
    sk = _skeleton()
    moves = FB.bone_moves(sk, {'parent': np.array([2.0, 0, 0, 0, 0, 0, 0, 0, 0])})
    assert set(moves) == {'parent', 'child'} and np.allclose(moves['child'][:3, 3], (2, 0, 0))
    assert FB.bone_moves(sk, {}) == {} and FB.bone_moves(sk, {'other': np.ones(9)}) == {}


def test_vertices_move_with_their_bones_about_the_bind_weighted():
    """A bone's own-frame move, seen through a bind turned a quarter, moves a whole vertex fully and a half one half."""
    bind = np.eye(4)
    bind[:3, :3] = ((0, 1, 0), (-1, 0, 0), (0, 0, 1))
    move = np.eye(4)
    move[:3, 3] = (1.0, 0.0, 0.0)
    points = np.array([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]])
    twin = (points, np.array([[1.0, 0, 0, 0], [0.5, 0.5, 0, 0]]), np.array([[0, 0, 0, 0], [0, 1, 0, 0]]),
            ['Moved', 'Still'], [bind, np.eye(4)])
    out = FB.sculpted(twin, {'moved': move})
    assert np.allclose(out[0], (0, 1, 0)) and np.allclose(out[1], (5.0, 5.5, 5.0))


def test_eye_data_is_read_and_packed_after_the_skin():
    """Two eye-data vertices read back whole: the float after the skin keeps the stride."""
    attrs = K.VA_VERTEX | K.VA_SKINNED | K.VA_EYE_DATA
    verts = [{'position': (1.0, 2.0, 3.0), 'bitangent_x': 0, 'weights': (1.0, 0.0, 0.0, 0.0), 'bones': (1, 0, 0, 0),
              'eye': 0.5 + i} for i in range(2)]
    r = K.Reader(b''.join(K.pack_vertex(v, attrs) for v in verts))
    back = [K.read_vertex(r, attrs) for _ in verts]
    assert [v['eye'] for v in back] == [0.5, 1.5] and back[1]['bones'] == (1, 0, 0, 0)
