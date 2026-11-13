"""Lists as Elric writes them: the compound's tree, its instances' packed words, its bounds and its box mass.

See: docs/fork/fo4_hknp_writer.md#compound
"""

import math
import struct

import numpy as np
import pytest

from fo4_import.havok import packfile
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_compound, hknp_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_write import MASS, MOTION
from tools.nif import hknp_compare

#: Our list's material CRC, and a quarter turn about z.
LIST_CRC = 0xDF02F237
QUARTER = (0.0, 1.0, 0, 0, -1.0, 0.0, 0, 0, 0, 0, 1.0, 0)


def _bits(value: float) -> int:
    """The bits of float32 `value`."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def test_tree_has_a_leaf_per_box_under_parents_written_first():
    """Node 0 empty, root 1, 2n - 1 used nodes then one free; every node's children lie inside it and name it."""
    boxes = [(np.array([x, 0, 0], np.float32), np.array([x + 1, 1, 1], np.float32)) for x in (0.0, 4.0, 2.0)]
    fields, leaf = hknp_compound.tree(boxes)
    nodes = fields['nodes']
    assert len(nodes) == 7 and fields['root'] == 1 and fields['firstFree'] == 6 and fields['numLeaves'] == 3
    assert nodes[0] == nodes[6] == {'aabb': {'min': (0.0,) * 4, 'max': (0.0,) * 4}}
    assert hknp_compare.leaves(fields) == [(*map(float, lo), *map(float, hi)) for lo, hi in boxes]
    for i in range(1, 6):
        children = _bits(nodes[i]['aabb']['max'][3])
        for child in (children & 0xFFFF, children >> 16) if children & 0xFFFF else ():
            assert child > i and _bits(nodes[child]['aabb']['min'][3]) == hknp_compound.PACKED | i
            assert all(a >= b for a, b in zip(nodes[child]['aabb']['min'][:3], nodes[i]['aabb']['min'][:3]))
    assert [_bits(nodes[k]['aabb']['max'][3]) >> 16 for k in leaf] == [0, 1, 2]


def test_box_mass_is_the_solid_box_with_scaled_inertia_and_no_turn():
    """A 1×2×3 box: volume 6, centered, inertia 1.5 × V/12 (b² + c²) per axis."""
    mass = hknp_compound.box_mass(np.zeros(3), np.array([1.0, 2.0, 3.0]))
    assert mass.volume == 6 and np.allclose(mass.com, [0.5, 1, 1.5]) and mass.frame == (0.0, 0.0, 0.0, 1.0)
    assert np.allclose(mass.inertia, 1.5 * 6 / 12 * np.array([13, 10, 5]))


def _list_nif() -> NifFile:
    """A pre-Elric NIF: a dynamic body of mass 3 on a list of a turned, moved 1×2×3 box and a plain unit box."""
    nif = NifFile()
    root = {'name': nif.string('Root'), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': 1, 'children': []}
    body = bytearray(250)
    struct.pack_into('<i', body, 0, 3)
    struct.pack_into('<f', body, MASS, 3.0)
    body[MOTION] = 3
    box = lambda *half: ('bhkBoxShape', struct.pack('<If8x3f4x', 5, 0.0, *half))
    nif.blocks = [('NiNode', root), ('bhkCollisionObject', struct.pack('<iHi', 0, 0, 2)),
                  ('bhkRigidBody', bytes(body)), ('bhkListShape', struct.pack('<I2iI', 2, 4, 6, LIST_CRC)),
                  ('bhkConvexTransformShape', struct.pack('<iIf8x16f', 5, 5, 0.0, *QUARTER, 5.0, 0.0, 0.0, 1.0)),
                  box(0.5, 1.0, 1.5), box(0.5, 0.5, 0.5)]
    return nif_file.read(nif_file.write(nif))


def _written() -> tuple:
    """(objects by name, the compound's fields, the motion) of _list_nif's physics after a packfile round trip."""
    block, _ = hknp_write.physics(_list_nif())
    objects = packfile.read(block[4:]).objects
    root = next(o['fields'] for o in objects if o['class'] == 'hknpPhysicsSystemData')
    named = {o['#']: o for o in objects}
    return named, named[root['bodyCinfos'][0]['shape']]['fields'], root['motionCinfos'][0]


def test_a_transformed_child_keeps_its_frame_and_the_instance_takes_the_transform():
    """Instance 0 holds the quarter turn and move; its box stays at ±half; w words pack flags, size, leaf."""
    named, shape, _ = _written()
    first, second = shape['instances']['elements']
    assert first['transform'][:3] == (0.0, 1.0, 0.0) and first['transform'][12:15] == (5.0, 0.0, 0.0)
    child = named[first['shape']]
    assert np.allclose(np.abs(hknp_compare.hull(child['fields'])['points']), [0.5, 1.0, 1.5])
    size = -(-(packfile.classes().size(child['class']) + len(child['fields']['__tail__'])) // 16) * 16
    assert [_bits(first['transform'][k]) for k in (3, 7, 11)] == [hknp_compound.INSTANCE_WORD, 0,
                                                                  hknp_compound.PACKED | size]
    cells = np.array(second['transform']).reshape(4, 4)
    assert np.array_equal(cells[:, :3], np.eye(4)[:, :3])
    assert shape['userData'] == LIST_CRC and shape['numShapeKeyBits'] == 2 and shape['properties'] is None


def test_compound_bounds_and_mass_are_its_leaves_box():
    """The turned box spans x 4–6, y ±0.5; the unit box ±0.5: bounds x -0.5–6; the motion a box of mass 3."""
    named, shape, motion = _written()
    lo, hi = shape['aabb']['min'][:3], shape['aabb']['max'][:3]
    assert lo == pytest.approx((-0.5, -0.5, -1.5)) and hi == pytest.approx((6.0, 0.5, 1.5))
    assert _bits(shape['aabb']['min'][3]) == hknp_compound.PACKED | 1 and shape['aabb']['max'][3] == 0
    volume = 6.5 * 1 * 3
    assert motion['massFactor'] == pytest.approx(3 / volume)
    assert motion['centerOfMassWorld'][:3] == pytest.approx((2.75, 0.0, 0.0))
    assert motion['orientation'] == (0.0, 0.0, 0.0, 1.0)
    inertia = 1.5 * volume / 12 * np.array([1 + 9, 6.5 ** 2 + 9, 6.5 ** 2 + 1]) * motion['massFactor']
    assert np.allclose(1 / np.array(motion['inverseInertiaLocal'][:3]), inertia, rtol=1e-5)
    tree = named[shape['boundingVolumeData']]['fields']['aabbTree']
    assert hknp_compare.leaves(tree)[0] == pytest.approx((4.0, -0.5, -1.5, 6.0, 0.5, 1.5))
    assert not math.isnan(sum(hknp_compare.leaves(tree)[1]))
