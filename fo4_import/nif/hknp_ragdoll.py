"""A creature skeleton's physics as Elric writes it: a bhkRagdollSystem and a bhkPhysicsSystem for its phantoms.

The ragdoll is hknp_write's system of the skeleton's rigid bodies and constraints under an hknpRagdollData root,
every constraint motor one shared, disabled position motor, plus an hkaSkeleton with one bone per body: a bone's
parent is the other body of the constraint in which it is body A, its reference pose the body's place in its
parent bone's frame. The CharacterController and CharacterBumper phantoms become trigger bodies of their own
system.

See: docs/fork/fo4_hknp_writer.md#ragdolls
"""

import struct

import numpy as np
from scipy.spatial import QhullError

from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_write import (MATERIAL, NO_ID, QUALITY, assemble, bodies, compose, convex, joints_of, pack,
                                       replace, rotate, world)

#: The shared motor every ragdoll constraint names (disabled).
MOTOR = {'type': 1, 'minForce': -1000000.0, 'maxForce': 100.0, 'tau': 0.8, 'damping': 1.0,
         'proportionalRecoveryVelocity': 5.0, 'constantRecoveryVelocity': 0.2}
#: A phantom's body flags (a trigger) and its material.
TRIGGER_BODY = 16
TRIGGER_MATERIAL = {**MATERIAL, 'flags': 0x200000, 'triggerType': 2, 'dynamicFriction': 16128,
                    'staticFriction': 16128, 'restitution': 0}
PHANTOM_OBJECT = 'bhkSPCollisionObject'


def _conjugate(q: tuple) -> tuple:
    """Quaternion `q`'s inverse rotation."""
    return -q[0], -q[1], -q[2], q[3]


def parents(count: int, joints: list) -> list:
    """Each of `count` bodies' parent bone: body B of the constraint whose body A it is, else -1."""
    out = [-1] * count
    for cinfo, _ in joints:
        out[cinfo['bodyA']] = cinfo['bodyB']
    return out


def _pose(place: tuple, parent: 'tuple | None') -> list:
    """A bone's reference pose (translation, rotation, scale) for body `place` in its `parent` body's frame."""
    t, q = np.asarray(place[0], float), place[1]
    if parent is not None:
        back = _conjugate(parent[1])
        t, q = rotate(back, t - np.asarray(parent[0], float)), compose(back, q)
    return [*map(float, t), 0.0, *map(float, q), 1.0, 1.0, 1.0, 0.0]


def skeleton(places: list, up: list) -> dict:
    """The hkaSkeleton fields over body `places` (position, orientation) with parent bones `up`."""
    return {'name': None, 'parentIndices': up,
            'bones': [{'name': None, 'lockTranslation': int(p >= 0)} for p in up],
            'referencePose': [_pose(place, places[p] if p >= 0 else None) for place, p in zip(places, up)],
            'referenceFloats': [], 'floatSlots': [], 'localFrames': [], 'partitions': []}


def _ragdoll(nif: NifFile) -> 'tuple | None':
    """(bhkRagdollSystem block, owner blocks) of `nif`'s rigid bodies and constraints; None when not covered."""
    rows = bodies(nif, frozenset({PHANTOM_OBJECT}))
    joints = None if rows is None else joints_of(nif, rows, '#motor')
    if joints is None:
        return None
    root, objects = assemble(rows, joints)
    places = [row[3] for row in rows]
    root.update(skeleton='#skeleton', boneToBodyMap=list(range(len(rows))))
    objects += [{'#': '#skeleton', 'class': 'hkaSkeleton', 'fields': skeleton(places, parents(len(rows), joints))},
                {'#': '#motor', 'class': 'hkpPositionConstraintMotor', 'fields': dict(MOTOR)}]
    return pack('hknpRagdollData', root, objects), [row[0] for row in rows]


def _phantom(nif: NifFile, owner: int, index: int) -> 'tuple | None':
    """(body cinfo, shape objects) of node `owner`'s phantom as body `index`; None when its shape is not convex."""
    phantom = nif.blocks[struct.unpack('<iHi', nif.blocks[nif.blocks[owner][1]['collision']][1])[2]][1]
    shape, filt = struct.unpack_from('<iI', phantom)
    maker = convex(nif.blocks, shape)
    if maker is None:
        return None
    place = world(nif, owner)
    cinfo = {'shape': f'#p{index}', 'reservedBodyId': NO_ID, 'motionId': NO_ID, 'qualityId': QUALITY,
             'materialId': index, 'collisionFilterInfo': filt, 'flags': TRIGGER_BODY,
             'collisionLookAheadDistance': 0.0, 'name': None, 'userData': 0, 'position': (*place[0], 0.0),
             'orientation': place[1], 'spuFlags': 0, 'localFrame': None}
    return cinfo, maker(f'#p{index}')[0]


def _phantoms(nif: NifFile) -> 'tuple | None':
    """(bhkPhysicsSystem block, owner blocks) of `nif`'s phantoms, or (None, []) without any; None when not
    covered."""
    owners = [i for i, (_, b) in enumerate(nif.blocks) if isinstance(b, dict) and b.get('collision', -1) >= 0
              and nif.blocks[b['collision']][0] == PHANTOM_OBJECT]
    made = [_phantom(nif, owner, i) for i, owner in enumerate(owners)]
    if any(m is None for m in made):
        return None
    if not made:
        return None, []
    root = {'name': None, 'materials': [dict(TRIGGER_MATERIAL) for _ in made], 'motionProperties': [],
            'motionCinfos': [], 'bodyCinfos': [cinfo for cinfo, _ in made], 'constraintCinfos': [],
            'referencedObjects': [cinfo['shape'] for cinfo, _ in made]}
    return pack('hknpPhysicsSystemData', root, [o for _, objects in made for o in objects]), owners


def finish(nif: NifFile) -> 'NifFile | None':
    """Skeleton `nif` with our ragdoll and phantom systems for its Havok input; None when not covered."""
    try:
        ragdoll, phantoms = _ragdoll(nif), _phantoms(nif)
    except QhullError:
        return None
    if ragdoll is None or phantoms is None:
        return None
    systems = [('bhkRagdollSystem', *ragdoll)] + ([('bhkPhysicsSystem', *phantoms)] if phantoms[1] else [])
    return replace(nif, systems)
