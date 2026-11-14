"""A creature skeleton's physics as Elric writes it: a bhkRagdollSystem and a bhkPhysicsSystem for its phantoms.

The ragdoll is hknp_write's system of the skeleton's rigid bodies and constraints under an hknpRagdollData root,
every constraint motor one shared, disabled position motor, plus an hkaSkeleton with one bone per body: a bone's
parent is the other body of the constraint in which it is body A, its reference pose the body's place in its
parent bone's frame. The CharacterController and CharacterBumper phantoms become trigger bodies of their own
system.

See: docs/fork/fo4_hknp_writer.md#ragdolls
"""

import numpy as np

from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_write import (PHANTOM_OBJECT, UNBUILT, assemble, bodies, compose, joints_of, pack, phantoms,
                                       replace, rotate, system)

#: The shared motor every ragdoll constraint names (disabled).
MOTOR = {'type': 1, 'minForce': -1000000.0, 'maxForce': 100.0, 'tau': 0.8, 'damping': 1.0,
         'proportionalRecoveryVelocity': 5.0, 'constantRecoveryVelocity': 0.2}


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
    joints = joints_of(nif, rows, '#motor') if rows else None
    if joints is None:
        return None
    root, objects = assemble(rows, joints)
    places = [row[3] for row in rows]
    root.update(skeleton='#skeleton', boneToBodyMap=list(range(len(rows))))
    objects += [{'#': '#skeleton', 'class': 'hkaSkeleton', 'fields': skeleton(places, parents(len(rows), joints))},
                {'#': '#motor', 'class': 'hkpPositionConstraintMotor', 'fields': dict(MOTOR)}]
    return pack('hknpRagdollData', root, objects), [row[0] for row in rows]


def _phantoms(nif: NifFile) -> 'tuple | None':
    """(bhkPhysicsSystem block of `nif`'s phantoms or None without any, their owner blocks); None when not
    covered."""
    made = phantoms(nif)
    if made is None:
        return None
    return (system([], (), made[0]) if made[1] else None), made[1]


def finish(nif: NifFile) -> 'NifFile | None':
    """Skeleton `nif` with our ragdoll and phantom systems for its Havok input; None when not covered."""
    try:
        ragdoll, triggers = _ragdoll(nif), _phantoms(nif)
    except UNBUILT:
        return None
    if ragdoll is None or triggers is None:
        return None
    systems = [('bhkRagdollSystem', *ragdoll)] + ([('bhkPhysicsSystem', *triggers)] if triggers[1] else [])
    return replace(nif, systems)
