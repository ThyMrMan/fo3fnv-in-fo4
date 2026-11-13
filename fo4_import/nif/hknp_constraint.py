"""Constraints as Elric writes them: a ragdoll or limited hinge between two bodies as an hknpConstraintCinfo and its
hkpRagdollConstraintData or hkpLimitedHingeConstraintData.

Each side's three axes and pivot (nif/collision.py's pre-Elric layout) become a transform's columns as they are,
column 0's w the third axis's y and column 1's w its x; limits and friction go to their atoms; everything else is
the same on every Elric constraint.

See: docs/fork/fo4_hknp_writer.md#constraints
"""

import struct

#: hkReal's largest value, and Elric's "unbounded" angle.
FLT_MAX, UNBOUNDED = 3.402820018375656e+38, 1.8446726481523507e+19
#: Pre-Elric constraint block: entity count, body A and B blocks, priority; then 8 vectors; then the limits.
HEAD, VECTORS = '<I2iI', 16
#: Per input kind: (data class, limit names in input order).
KINDS = {'bhkRagdollConstraint': ('hkpRagdollConstraintData',
                                  ('cone', 'planeMin', 'planeMax', 'twistMin', 'twistMax', 'friction')),
         'bhkLimitedHingeConstraint': ('hkpLimitedHingeConstraintData', ('min', 'max', 'friction'))}
#: The limit tau Elric writes on a hinge and on a ragdoll's three limits.
HINGE_TAU, RAGDOLL_TAU = 1.0, 0.8
#: A ragdoll cone limit's lower angle (unused) and its offset to the cone's angle.
CONE_MIN, CONE_OFFSET = -100.0, 56
STABILIZATION = {'type': 23, 'enabled': 1, 'maxLinImpulse': FLT_MAX, 'maxAngImpulse': FLT_MAX,
                 'maxAngle': UNBOUNDED}
BALL_SOCKET = {'type': 5, 'solvingMethod': 0, 'bodiesToNotify': 0, 'velocityStabilizationFactor': {'value': 48},
               'enableLinearImpulseLimit': 0, 'breachImpulse': FLT_MAX, 'inertiaStabilizationFactor': 0.0}


def _transform(vectors: tuple) -> list:
    """One side's column-major transform of its three axes and pivot."""
    axes = [v[:3] for v in vectors]
    return [*axes[0], axes[2][1], *axes[1], axes[2][0], *axes[2], 0.0, *axes[3], 0.0]


def _friction(axes: int, torque: float) -> dict:
    """The angular friction atom over `axes` axes."""
    return {'type': 17, 'isEnabled': 1, 'firstFrictionAxis': 0, 'numFrictionAxes': axes, 'maxFrictionTorque': torque}


def _limit(kind: int, low: float, high: float, tau: float, **axes) -> dict:
    """An angular limit atom of atom type `kind` from `low` to `high`."""
    return {'type': kind, 'isEnabled': 1, **axes, 'minAngle': low, 'maxAngle': high, 'angularLimitsTauFactor': tau}


def _ragdoll(lim: dict, motor: 'str | None') -> dict:
    """The ragdoll atoms past the transforms and stabilization, from limits `lim`, motors `motor`."""
    return {'ragdollMotors': {'type': 19, 'isEnabled': 0, 'target_bRca': [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0],
                              'motors': [motor] * 3},
            'angFriction': _friction(3, lim['friction']),
            'twistLimit': _limit(15, lim['twistMin'], lim['twistMax'], RAGDOLL_TAU, twistAxis=0, refAxis=1),
            'coneLimit': _limit(16, CONE_MIN, lim['cone'], RAGDOLL_TAU, twistAxisInA=0, refAxisInB=0,
                                angleMeasurementMode=0, memOffsetToAngleOffset=CONE_OFFSET),
            'planesLimit': _limit(16, lim['planeMin'], lim['planeMax'], RAGDOLL_TAU, twistAxisInA=0, refAxisInB=1,
                                  angleMeasurementMode=1, memOffsetToAngleOffset=0)}


def _hinge(lim: dict, motor: 'str | None') -> dict:
    """The limited hinge atoms past the transforms and stabilization, from limits `lim`, motor `motor`."""
    return {'angMotor': {'type': 18, 'isEnabled': 0, 'motorAxis': 0, 'targetAngle': 0.0, 'motor': motor},
            'angFriction': _friction(1, lim['friction']),
            'angLimit': _limit(14, lim['min'], lim['max'], HINGE_TAU, limitAxis=0),
            '2dAng': {'type': 12, 'freeRotationAxis': 0}}


def constraint(name: str, kind: str, raw: bytes, ids: dict, motor: 'str | None' = None) -> 'tuple | None':
    """(hknpConstraintCinfo, its data object named `name`) of pre-Elric constraint block (`kind`, `raw`), its
    bodies numbered by `ids` {body block: body id}, its (disabled) motors the object named `motor`; None when either
    body is not in `ids`."""
    _, a, b, _ = struct.unpack_from(HEAD, raw)
    if a not in ids or b not in ids:
        return None
    cls, names = KINDS[kind]
    vectors = [struct.unpack_from('<4f', raw, VECTORS + 16 * i) for i in range(8)]
    lim = dict(zip(names, struct.unpack_from(f'<{len(names)}f', raw, VECTORS + 128)))
    atoms = {'transforms': {'type': 2, 'transformA': _transform(vectors[:4]), 'transformB': _transform(vectors[4:])},
             'setupStabilization': dict(STABILIZATION)}
    atoms.update(_ragdoll(lim, motor) if kind == 'bhkRagdollConstraint' else _hinge(lim, motor))
    atoms['ballSocket'] = dict(BALL_SOCKET)
    cinfo = {'constraintData': name, 'bodyA': ids[a], 'bodyB': ids[b], 'flags': 0}
    return cinfo, {'#': name, 'class': cls, 'fields': {'userData': 0, 'atoms': atoms}}


def constraints(blocks: list, ids: dict, motor: 'str | None' = None) -> 'list | None':
    """[(cinfo, data object)] of every constraint block in `blocks`, block order, motors `motor`; None when any is a
    kind we do not write or joins a body outside `ids`."""
    out = []
    for kind, raw in blocks:
        if 'Constraint' not in kind:
            continue
        made = constraint(f'#k{len(out)}', kind, raw, ids, motor) if kind in KINDS else None
        if made is None:
            return None
        out.append(made)
    return out
