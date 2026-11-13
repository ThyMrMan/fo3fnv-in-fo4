"""Constraints and ragdolls as Elric writes them: constraint data, the ragdoll's skeleton and phantoms, and Havok's
matrix-to-quaternion rule.

See: docs/fork/fo4_hknp_writer.md#constraints
"""

import struct
from types import SimpleNamespace

import numpy as np
import pytest

from fo4_import.havok import packfile
from fo4_import.nif import collision
from fo4_import.nif import file as nif_file
from fo4_import.nif import hknp_constraint, hknp_ragdoll, hknp_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_convex import quaternion
from fo4_import.nif.hknp_write import GAME_PER_HAVOK, MASS, MOTION

#: A hinge's sides (axle, two perpendiculars, pivot) and limits (min, max, friction).
HINGE_A = ((0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0))
HINGE_B = ((0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.5, 0.0, 0.0, 0.0))
LIMITS = (-0.5, 0.75, 10.0)
BOX = ('bhkBoxShape', struct.pack('<If8x3f4x', 7, 0.0, 0.5, 0.5, 0.5))


def _node(nif: NifFile, name: str, translation: tuple, collision: int, children: list) -> dict:
    """A NiNode named `name`."""
    return {'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': translation,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': collision, 'children': children}


def _body(shape: int) -> bytes:
    """A pre-Elric dynamic rigid body of mass 2 on `shape`."""
    body = bytearray(250)
    struct.pack_into('<i', body, 0, shape)
    struct.pack_into('<f', body, MASS, 2.0)
    body[MOTION] = 3
    return bytes(body)


def _phantom(nif: NifFile) -> None:
    """Add a CharacterController node under the root holding a capsule phantom on filter 30."""
    nif.blocks[0][1]['children'].append(9)
    nif.blocks += [('NiNode', _node(nif, 'CharacterController', (0.0,) * 3, 10, [])),
                   ('bhkSPCollisionObject', struct.pack('<iHi', 9, 1, 11)),
                   ('bhkSimpleShapePhantom', struct.pack('<iI', 12, 30) + bytes(92)),
                   ('bhkCapsuleShape', struct.pack('<If8x3f4x3f4x', 7, 0.2, 0, 0, 0.2, 0, 0, 0.6))]


def _hinged(phantom: bool = False) -> NifFile:
    """A root and a child node, each owning a box body, joined by a limited hinge (child A, root B); with
    `phantom`, also a capsule phantom."""
    nif = NifFile()
    hinge = struct.pack('<I2iI', 2, 5, 2, 1) + b''.join(struct.pack('<4f', *v) for v in HINGE_A + HINGE_B)
    nif.blocks = [('NiNode', _node(nif, 'Root', (0.0,) * 3, 1, [4])), ('bhkCollisionObject', struct.pack('<iHi', 0, 0, 2)),
                  ('bhkRigidBody', _body(3)), BOX,
                  ('NiNode', _node(nif, 'Arm', (70.0, 0.0, 0.0), 6, [])), ('bhkRigidBody', _body(7)),
                  ('bhkCollisionObject', struct.pack('<iHi', 4, 0, 5)), BOX,
                  ('bhkLimitedHingeConstraint', hinge + struct.pack('<3fB', *LIMITS, 0))]
    if phantom:
        _phantom(nif)
    return nif_file.read(nif_file.write(nif))


def _objects(nif: NifFile, kind: str) -> tuple:
    """(root fields, {name: object}) of `nif`'s first `kind` system block."""
    block = next(raw for k, raw in nif.blocks if k == kind)
    objects = packfile.read(block[4:]).objects
    return objects[0]['fields'], {o['#']: o for o in objects}


def test_hinge_copies_its_sides_into_transforms_with_elrics_w_words():
    """Body ids follow the owners; each side's axes and pivot are the transform's columns; limits and friction
    land in their atoms; the motor slot is empty."""
    nif = hknp_write.finish(_hinged())
    root, named = _objects(nif, 'bhkPhysicsSystem')
    (cinfo,) = root['constraintCinfos']
    assert (cinfo['bodyA'], cinfo['bodyB'], cinfo['flags']) == (1, 0, 0)
    atoms = named[cinfo['constraintData']]['fields']['atoms']
    cols = np.array(atoms['transforms']['transformB']).reshape(4, 4)
    assert np.allclose(cols[:, :3], np.array(HINGE_B)[:, :3])
    assert list(cols[:, 3]) == [HINGE_B[2][1], HINGE_B[2][0], 0.0, 0.0]
    assert (atoms['angLimit']['minAngle'], atoms['angLimit']['maxAngle'],
            atoms['angFriction']['maxFrictionTorque']) == pytest.approx(LIMITS)
    assert atoms['angMotor']['motor'] is None and atoms['angFriction']['numFrictionAxes'] == 1


def test_a_constraint_kind_we_do_not_write_leaves_the_mesh_to_elric():
    """A stiff spring between the two bodies: not covered."""
    nif = _hinged()
    nif.blocks[-1] = ('bhkStiffSpringConstraint', nif.blocks[-1][1])
    assert hknp_write.physics(nif) is None


def test_ragdoll_bones_follow_the_constraints_and_pose_each_body_in_its_parent():
    """The arm's bone hangs under the root's; its pose is the arm's place in the root body's frame; every motor
    slot names one shared position motor."""
    nif = hknp_ragdoll.finish(_hinged())
    assert [k for k, _ in nif.blocks if k.startswith('bhk')] == ['bhkRagdollSystem'] + ['bhkNPCollisionObject'] * 2
    root, named = _objects(nif, 'bhkRagdollSystem')
    skeleton = named[root['skeleton']]['fields']
    assert skeleton['parentIndices'] == [-1, 0] and root['boneToBodyMap'] == [0, 1]
    assert [b['lockTranslation'] for b in skeleton['bones']] == [0, 1]
    assert skeleton['referencePose'][1][:3] == pytest.approx((70 / GAME_PER_HAVOK, 0, 0))
    motor = named[root['constraintCinfos'][0]['constraintData']]['fields']['atoms']['angMotor']['motor']
    assert named[motor]['class'] == 'hkpPositionConstraintMotor'


def test_ragdoll_phantoms_become_trigger_bodies_of_their_own_system():
    """The controller's capsule phantom: its own bhkPhysicsSystem, a trigger body on its filter, no motion."""
    nif = hknp_ragdoll.finish(_hinged(phantom=True))
    root, named = _objects(nif, 'bhkPhysicsSystem')
    (body,) = root['bodyCinfos']
    assert (body['flags'], body['collisionFilterInfo'], body['motionId']) == (16, 30, hknp_write.NO_ID)
    assert named[body['shape']]['class'] == 'hknpCapsuleShape' and root['materials'][0]['triggerType'] == 2
    systems = [nif.blocks[struct.unpack_from('<i', raw, 6)[0]][0] for k, raw in nif.blocks
               if k == 'bhkNPCollisionObject']
    assert systems == ['bhkRagdollSystem'] * 2 + ['bhkPhysicsSystem']


def test_a_havok_action_listed_among_a_bodys_constraints_is_left_out():
    """FNV lists actions (bhkLiquidAction, bhkOrientHingedBodyAction: no `entities`) beside constraints; FO4's
    physics has no actions, so joints() writes none and the body keeps its record.

    See: docs/fork/fo4_pipeline.md#ragdolls
    """
    actions = [type(kind, (), {})() for kind in ('bhkLiquidAction', 'bhkOrientHingedBodyAction')]
    body = SimpleNamespace(constraints=actions)
    nif = NifFile()
    nif.blocks = [('bhkRigidBody', bytes(250))]
    collision.joints(nif, {id(body): (body, 0, 1.0)})
    assert nif.blocks == [('bhkRigidBody', bytes(250))]


def test_a_static_meshs_phantom_is_a_trigger_body_after_its_rigid_bodies():
    """Outside a skeleton a phantom joins the one physics system, after the rigid bodies, on a trigger material."""
    nif = hknp_write.finish(_hinged(phantom=True))
    root, named = _objects(nif, 'bhkPhysicsSystem')
    assert [b['flags'] for b in root['bodyCinfos']][2:] == [16] and len(root['bodyCinfos']) == 3
    assert [m['triggerType'] for m in root['materials']] == [0, 0, 2]
    assert named[root['bodyCinfos'][2]['shape']]['class'] == 'hknpCapsuleShape'
    held = [struct.unpack_from('<iHiI', raw)[3] for k, raw in nif.blocks if k == 'bhkNPCollisionObject']
    assert sorted(held) == [0, 1, 2] and [k for k, _ in nif.blocks].count('bhkPhysicsSystem') == 1


@pytest.mark.parametrize('turn, expected', [(np.eye(3), (0.0, 0.0, 0.0, 1.0)),
                                           (np.diag([-1.0, -1.0, 1.0]), (0.0, 0.0, 1.0, 0.0)),
                                           (np.diag([1.0, -1.0, -1.0]), (1.0, 0.0, 0.0, 0.0))])
def test_quaternion_follows_havoks_branches(turn, expected):
    """Positive trace: w > 0; else the largest diagonal's component is."""
    assert quaternion(turn) == pytest.approx(expected)


def test_quaternion_keeps_the_largest_component_positive_when_w_is_negative():
    """A turn with a negative trace: Havok's rule keeps z positive and w negative, as Elric writes."""
    q = np.array([-0.24848585, -0.63783193, 0.66200840, -0.30523780])
    q = q / np.linalg.norm(q)
    x, y, z, w = q
    m = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    assert quaternion(m) == pytest.approx(tuple(q), abs=1e-6)


def test_ragdoll_constraint_atoms_carry_elrics_constants():
    """A ragdoll's three limits carry tau 0.8; its cone limit's lower angle is -100; friction spans 3 axes."""
    raw = struct.pack('<I2iI', 2, 1, 2, 1) + bytes(128) + struct.pack('<6fB', 0.5, -0.2, 0.2, -0.3, 0.3, 4.0, 0)
    _, data = hknp_constraint.constraint('#k', 'bhkRagdollConstraint', raw, {1: 0, 2: 1})
    atoms = data['fields']['atoms']
    assert (atoms['coneLimit']['minAngle'], atoms['coneLimit']['maxAngle']) == (-100.0, pytest.approx(0.5))
    assert {atoms[k]['angularLimitsTauFactor'] for k in ('twistLimit', 'coneLimit', 'planesLimit')} == {0.8}
    assert atoms['angFriction']['numFrictionAxes'] == 3


def test_a_constraint_to_a_body_outside_the_system_is_none():
    """Body B is not one of ours: no constraint."""
    raw = struct.pack('<I2iI', 2, 1, 9, 1) + bytes(128) + struct.pack('<3fB', *LIMITS, 0)
    assert hknp_constraint.constraint('#k', 'bhkLimitedHingeConstraint', raw, {1: 0}) is None
