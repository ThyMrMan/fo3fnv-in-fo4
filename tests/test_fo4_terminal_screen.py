"""A converted terminal's screen: the largest unlit shape FNV textures, never a glare pane drawn through WHITE; the
mesh moved so the screen faces -Y over the origin, the placed reference taking the move back.

See: docs/fork/fo4_pipeline.md#terminals
"""

import math
import struct
from types import SimpleNamespace

import numpy as np

from fo4_import.nif import terminal as T
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY, WHITE
from fo4_import.spike.guns import turned
from fo4_import.spike.scol import rotation
from fo4_import.spike.terminals import BELOW, REACH

#: VOverseerTerminal01's screen centre and its shape's corners: about 290 units from the mesh's origin, facing +X.
CENTRE, CORNERS = np.array([-290.0, 32.0, 96.0]), ((-306.0, -24.0, 40.0), (-273.0, 88.0, 151.0))


def _offset_mesh(root_collision: bool) -> SimpleNamespace:
    """A mesh of one shape at CORNERS; the root carries a pre-Elric collision object when `root_collision`."""
    node = {'name': 0, 'flags': 14, 'rotation': IDENTITY, 'translation': (0.0, 0.0, 0.0), 'scale': 1.0,
            'collision': 2 if root_collision else NONE, 'children': [1]}
    shape = {'rotation': IDENTITY, 'translation': (0.0, 0.0, 0.0), 'scale': 1.0,
             'vertices': [{'position': corner} for corner in CORNERS]}
    blocks = [('NiNode', node), ('BSTriShape', shape), ('bhkCollisionObject', struct.pack('<iHi', 0, 1, 7))]
    strings = ['Root']
    return SimpleNamespace(blocks=blocks, strings=strings, string=lambda s: strings.append(s) or len(strings) - 1)


def test_an_off_origin_screen_is_moved_over_the_origin_and_offered_from_its_front():
    """FO4 offers a terminal only within 60 degrees of -Y from the reference's own position (0x9971A4): the screen
    turns to -Y and shifts over the origin, so the user's spot in front of it passes."""
    nif = _offset_mesh(False)
    move = T._moved(nif, -math.pi / 2, CENTRE)
    centre = CENTRE @ move[:3, :3] + move[3, :3]
    assert np.allclose(centre[:2], 0.0) and centre[2] == CENTRE[2]
    facing = np.array([1.0, 0.0, 0.0]) @ move[:3, :3]
    spot = centre + facing * REACH - (0.0, 0.0, BELOW)
    assert -spot[1] / math.hypot(*spot[:2]) >= 0.5
    assert np.allclose(T.placed_bounds(nif), (-56, -17, 40, 56, 16, 151), atol=1)


def test_a_moved_terminal_mesh_lands_where_fnv_placed_it():
    """Every point of the moved mesh, placed through guns.turned (tilted reference included), is where FNV's was."""
    nif = _offset_mesh(False)
    move = T._moved(nif, -math.pi / 2, CENTRE)
    shape = nif.blocks[1][1]
    position, angle, scale = (500.0, -40.0, 12.0), (0.1, -0.2, 1.3), 1.25
    at, turn = turned(position, angle, scale, move)
    for corner in CORNERS:
        mesh = np.array(shape['rotation']).reshape(3, 3) @ corner + shape['translation']
        assert np.allclose(np.array(at) + scale * rotation(turn) @ mesh,
                           np.array(position) + scale * rotation(angle) @ np.array(corner))


def test_a_roots_own_collision_moves_to_a_child_that_turns():
    """A root's collision would not turn with its children: it moves to a new child node, its target with it."""
    nif = _offset_mesh(True)
    T._moved(nif, -math.pi / 2, CENTRE)
    root, (kind, node) = nif.blocks[0][1], nif.blocks[3]
    assert root['collision'] == NONE and root['children'] == [1, 3] and kind == 'NiNode'
    assert node['collision'] == 2 and struct.unpack('<iHi', nif.blocks[2][1]) == (3, 1, 7)
    assert np.allclose(node['translation'], nif.blocks[1][1]['translation'])


def _nif(texture: str) -> SimpleNamespace:
    """A mesh whose block 0 is an unlit effect shader drawing `texture`."""
    return SimpleNamespace(blocks=[('BSEffectShaderProperty', {'name': -1, 'source_texture': texture})])


def test_a_screen_textured_shape_is_a_screen():
    """vcontrolpanel04's glass, textured vcontrolpanelsscreen01, carries the menu."""
    assert T._unlit(_nif(r'textures\fnv\dungeons\vault\vcontrolpanelsscreen01.dds'), {'shader': 0})


def test_an_untextured_glare_pane_is_not_a_screen():
    """Its larger untextured falloff pane, drawn through WHITE, does not."""
    assert not T._unlit(_nif(WHITE), {'shader': 0})
    assert not T._unlit(_nif(''), {'shader': 0})


def _quad(y: float, z: float, size: float) -> tuple:
    """(corners, triangles) of a +X square at (y, z), corner 0 doubled."""
    corners = [(0.0, y, z), (0.0, y + size, z), (0.0, y + size, z + size), (0.0, y, z + size), (0.0, y, z)]
    return corners, [(4, 1, 2), (0, 2, 3)]


def _bank() -> SimpleNamespace:
    """One unlit shape holding a 2x2 bank of 30-unit screens and a small indicator light, as VOverseerTerminal01's
    VMonitorBank:2 (four screens) and Terminal01's T01Screen01:1 (screen plus a side light)."""
    points, tris = [], []
    for y, z, size in ((40.0, 120.0, 30.0), (0.0, 120.0, 30.0), (40.0, 80.0, 30.0), (0.0, 80.0, 30.0),
                       (90.0, 10.0, 3.0)):
        corners, quad = _quad(y, z, size)
        tris += [tuple(i + len(points) for i in t) for t in quad]
        points += corners
    node = {'name': 0, 'rotation': IDENTITY, 'translation': (0.0, 0.0, 0.0), 'scale': 1.0, 'children': [1]}
    shape = {'name': 1, 'rotation': IDENTITY, 'translation': (0.0, 0.0, 0.0), 'scale': 1.0, 'shader': 2,
             'controller': NONE, 'extra': [], 'vertices': [{'position': p} for p in points], 'triangles': tris}
    blocks = [('NiNode', node), ('BSTriShape', shape),
              ('BSEffectShaderProperty', {'name': -1, 'source_texture': 'screen.dds'})]
    return SimpleNamespace(blocks=blocks, strings=['Bank', 'Bank:2'])


def test_islands_are_joined_through_shared_positions():
    """A UV seam's doubled corner still joins its square; separate squares are separate islands."""
    corners, tris = _quad(0.0, 0.0, 1.0)
    assert len(T.islands(np.array(corners), np.array(tris))) == 1
    nif = _bank()
    shape = nif.blocks[1][1]
    masks = T.islands(np.array([v['position'] for v in shape['vertices']]), np.array(shape['triangles']))
    assert sorted(int(m.sum()) for m in masks) == [2] * 5


def test_one_screen_of_a_bank_becomes_the_screen_the_rest_keep_their_shape():
    """FO4 draws its menu on and zooms to all of Screen:0: of four equal screens, only the lowest (then the first
    by position) is split out beside the shape; the others and the light stay in it with their shader."""
    nif = _bank()
    index, mask = T._screen(nif)
    screen = T._split(nif, index, mask)
    kept, split = nif.blocks[1][1], nif.blocks[screen][1]
    assert screen == 3 and nif.blocks[0][1]['children'] == [1, 3]
    assert len(split['triangles']) == 2 and len(kept['triangles']) == 8 and kept['shader'] == split['shader'] == 2
    points = np.array([v['position'] for v in split['vertices']])
    assert np.allclose(points.min(axis=0), (0.0, 0.0, 80.0)) and np.allclose(points.max(axis=0), (0.0, 30.0, 110.0))
    assert np.allclose(split['bound'], (0.0, 15.0, 95.0, math.hypot(15.0, 15.0)))
