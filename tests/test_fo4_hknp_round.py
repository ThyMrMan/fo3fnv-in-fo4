"""Spheres and capsules as Elric writes them: radii, the capsule's core box and frame, mass, and a written system.

See: docs/fork/fo4_hknp_writer.md#round
"""

import math
import struct

import numpy as np
import pytest

from fo4_import.havok import packfile, packfile_write
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_round, hknp_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_write import MASS, MOTION
from tools.nif import hknp_compare


def test_capsule_radius_loses_one_percent_twice():
    """R 1 gives convex radius 0.9801 and padding 0.0099, in float32."""
    convex, pad = hknp_round.capsule_radii(1.0)
    assert convex == float(np.float32(0.99) - np.float32(0.99) * np.float32(0.01))
    assert pad == pytest.approx(0.0099) and convex == pytest.approx(0.9801)


@pytest.mark.parametrize('v, expected', [((0, 0, -1), (-1, 0, 0)), ((-1, 0, 0), (0, 1, 0)),
                                         ((0.0422, -0.1286, 1e-8), (-0.1286, -0.0422, 0)),
                                         ((-0.99, 0.084, -0.0988), (-0.0988, 0, 0.99))])
def test_perpendicular_zeroes_the_smallest_later_on_a_tie(v, expected):
    """Frames read off Elric's capsules: ties to the later axis."""
    assert np.allclose(hknp_round.perpendicular(np.array(v, np.float32)), expected, atol=1e-6)


def _capsule_fields(a=(0.0, 0.0, 1.0), b=(0.0, 0.0, 0.0), radius=0.5) -> dict:
    """A capsule's fields after a packfile write and read."""
    objects, _ = hknp_round.capsule('#c', a, b, radius, 7)
    return packfile.read(packfile_write.write(objects, '#c')).objects[0]['fields']


def test_capsule_core_is_a_box_one_padding_around_its_segment():
    """Eight corners one padding out from the segment on every side and past each end; six faces of four."""
    fields = _capsule_fields()
    _, pad = hknp_round.capsule_radii(0.5)
    shape = hknp_compare.hull(fields, 'hknpCapsuleShape')
    assert shape['points'].shape == (8, 3) and set(shape['faces'][:, 5]) == {4} and len(shape['faces']) == 6
    assert np.allclose(np.abs(shape['points']).max(0), [pad, pad, 1 + pad], atol=1e-7)
    assert np.allclose(shape['points'].min(0)[2], -pad, atol=1e-7)
    for normal_offset in shape['faces'][:, :4]:
        assert np.max(shape['points'] @ normal_offset[:3] + normal_offset[3]) == pytest.approx(0, abs=1e-6)
    assert fields['flags'] == hknp_round.CAPSULE_FLAGS and fields['properties'] is None


def test_capsule_mass_has_its_small_moment_on_the_axis():
    """A capsule along x: volume πr²L + 4/3πr³, the axial moment 1.5 × the solid's, centered mid-segment."""
    a, b = np.array([2.0, 0, 0]), np.zeros(3)
    mass = hknp_round.capsule_mass(a, b, 0.5)
    assert mass.volume == pytest.approx(math.pi * 0.25 * 2 + 4 / 3 * math.pi * 0.125)
    axial = 1.5 * (math.pi * 0.25 * 2 * 0.25 / 2 + 4 / 3 * math.pi * 0.125 * 0.4 * 0.25)
    assert min(mass.inertia) == pytest.approx(axial, rel=1e-5)
    assert np.allclose(mass.com, [1.0, 0, 0])


def test_sphere_is_four_copies_of_its_center():
    """Every vertex the center, tagged index 0; mass a solid sphere's with 1.5 × its inertia."""
    objects, mass = hknp_round.sphere('#s', (1.0, 2.0, 3.0), 0.5, 9)
    fields = packfile.read(packfile_write.write(objects, '#s')).objects[0]['fields']
    assert fields['__tail__'][:64] == struct.pack('<3fI', 1.0, 2.0, 3.0, 0x3F000000) * 4
    assert fields['convexRadius'] == 0.5 and fields['flags'] == hknp_round.SPHERE_FLAGS
    assert mass.volume == pytest.approx(4 / 3 * math.pi * 0.125)
    assert np.allclose(mass.inertia, 1.5 * 0.4 * 0.25 * mass.volume)


def _sphere_nif(translation: tuple) -> NifFile:
    """A pre-Elric NIF: a root node owning one dynamic body of mass 2 on a sphere under a translation."""
    nif = NifFile()
    root = {'name': nif.string('Root'), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': 1, 'children': []}
    body = bytearray(250)
    struct.pack_into('<i', body, 0, 3)
    struct.pack_into('<f', body, MASS, 2.0)
    body[MOTION] = 3
    cells = (1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, *translation, 1.0)
    nif.blocks = [('NiNode', root), ('bhkCollisionObject', struct.pack('<iHi', 0, 0, 2)),
                  ('bhkRigidBody', bytes(body)), ('bhkConvexTransformShape', struct.pack('<iIf8x16f', 4, 5, 0.5, *cells)),
                  ('bhkSphereShape', struct.pack('<If', 5, 0.5))]
    return nif_file.read(nif_file.write(nif))


def test_a_dynamic_sphere_moves_its_center_and_mass_with_the_transform():
    """The transform's translation is the sphere's center and the motion's center of mass."""
    block, _ = hknp_write.physics(_sphere_nif((0.25, 0.0, 1.0)))
    objects = packfile.read(block[4:]).objects
    root = next(o['fields'] for o in objects if o['class'] == 'hknpPhysicsSystemData')
    shape = next(o['fields'] for o in objects if o['class'] == 'hknpSphereShape')
    assert struct.unpack_from('<3f', shape['__tail__']) == (0.25, 0.0, 1.0)
    motion = root['motionCinfos'][0]
    assert motion['centerOfMassWorld'][:3] == pytest.approx((0.25, 0.0, 1.0))
    assert motion['inverseMass'] == pytest.approx(0.5)
