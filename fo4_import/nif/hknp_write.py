"""Our own FO4 physics for a pre-Elric NIF, where it covers the input (convex bodies), in place of Elric's.

`physics(nif)` reads the collision blocks nif/collision.py wrote (bhkCollisionObject, bhkRigidBody,
convex shapes) and gives the bhkPhysicsSystem block and each collision owner in body order; None for
input it does not cover yet. `finish(nif)` puts them in place of the Havok input as elric.graft does.

See: docs/fork/fo4_hknp_writer.md#convex
"""

import struct

import numpy as np
from scipy.spatial import QhullError

from fo4_import.havok import packfile_write
from fo4_import.nif.blocks import NONE
from fo4_import.nif.elric import without_havok
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_convex import box_corners, polytope, quaternion

#: Pre-Elric bhkRigidBody offsets: filter, mass, damping, friction, restitution, max angular speed, motion.
FILTER, MASS, DAMPING, FRICTION, RESTITUTION, MAX_ANGULAR, MOTION = 4, 180, 184, 196, 204, 212, 216
#: FO4 game units per Havok unit as Elric places a body (its node's world translation over this).
GAME_PER_HAVOK = 69.99125
#: Low float32 bits Elric rounds off a body's max angular speed.
SPEED_BITS = 12
#: Havok 2014 motion systems: the dynamic ones, keyframed, fixed.
DYNAMIC, KEYFRAMED, FIXED = frozenset({2, 3}), 4, 5
#: Body cinfo values: no motion or reserved id, every quality the default, a dynamic body's flags.
NO_ID, QUALITY, DYNAMIC_FLAGS = 0x7FFFFFFF, 255, 128
#: A motion's properties id for the game's own preset (keyframed bodies without mass).
PRESET = 65535
#: Extra body flag Elric sets on a keyframed body that has mass (it gets a full motion).
KEYFRAMED_FLAG = 0x10000
#: A float Elric writes for "unbounded" in a motion.
UNBOUNDED = 1.8446726481523507e+19
#: bhkNPCollisionObject flags on every Elric collision object.
NP_FLAGS = 128
CONVEX_KINDS = frozenset({'bhkConvexVerticesShape', 'bhkBoxShape'})
BODY_KINDS = frozenset({'bhkRigidBody', 'bhkRigidBodyT'})
MATERIAL = {'name': None, 'isExclusive': 0, 'flags': 0, 'triggerType': 0, 'triggerManifoldTolerance': {'value': 255},
            'frictionCombinePolicy': 1, 'restitutionCombinePolicy': 2, 'weldingTolerance': 15692,
            'maxContactImpulse': 3.402820018375656e+38, 'fractionOfClippedImpulseToApply': 1.0,
            'massChangerCategory': 0, 'massChangerHeavyObjectFactor': 16256, 'softContactForceFactor': 0,
            'softContactDampFactor': 0, 'softContactSeperationVelocity': {'value': 0}, 'surfaceVelocity': None,
            'disablingCollisionsBetweenCvxCvxDynamicObjectsDistance': 16544, 'userData': 0, 'isShared': 0}
MOTION_PROPERTIES = {'isExclusive': 0, 'flags': 0, 'gravityFactor': 1.0, 'timeFactor': 1.0, 'maxLinearSpeed': 104.375,
                     'solverStabilizationSpeedThreshold': 0.17000000178813934,
                     'solverStabilizationSpeedReduction': 0.4905000329017639, 'maxDistSqrd': 0.002500000176951289,
                     'maxRotSqrd': 0.002500000176951289, 'invBlockSize': 1.0, 'pathingUpperThreshold': 26623,
                     'pathingLowerThreshold': -26213, 'numDeactivationFrequencyPasses': 4,
                     'deactivationVelocityScaleSquare': 115, 'minimumPathingVelocityScaleSquare': 117,
                     'spikingVelocityScaleThresholdSquared': 6, 'minimumSpikingVelocityScaleSquared': 115}


# ---------------------------------------------------------------------------
# Reading our pre-Elric blocks
# ---------------------------------------------------------------------------

def _convex(blocks: list, index: int) -> 'tuple | None':
    """(points, convex radius, material CRC) of a convex shape block, Havok units: a convex shape's own vertex
    list, a box's corners; None for any other."""
    kind, raw = blocks[index]
    if kind == 'bhkConvexVerticesShape':
        crc, radius = struct.unpack_from('<If', raw)
        count = struct.unpack_from('<I', raw, 32)[0]
        return np.array(struct.unpack_from(f'<{4 * count}f', raw, 36)).reshape(-1, 4)[:, :3], radius, crc
    if kind == 'bhkBoxShape':
        crc, radius, *half = struct.unpack_from('<If8x3f', raw)
        return box_corners(half), radius, crc
    if kind == 'bhkConvexTransformShape':
        child, _, _, *cells = struct.unpack('<iIf8x16f', raw)
        inner = _convex(blocks, child) if blocks[child][0] in CONVEX_KINDS else None
        if inner is None:
            return None
        matrix = np.array(cells).reshape(4, 4).T
        return inner[0] @ matrix[:3, :3].T + matrix[:3, 3], *inner[1:]
    return None


def _world(nif: NifFile, index: int) -> tuple:
    """(translation in Havok units, rotation quaternion) of node `index` in the NIF root's space."""
    parents = {child: i for i, (_, b) in enumerate(nif.blocks) if isinstance(b, dict) for child in b.get('children', ())}
    rotation, translation = np.eye(3), np.zeros(3)
    while index is not None:
        node = nif.blocks[index][1]
        local = np.array(node['rotation']).reshape(3, 3)
        translation = local @ translation * node['scale'] + np.array(node['translation'])
        rotation = local @ rotation
        index = parents.get(index)
    return translation / GAME_PER_HAVOK, quaternion(rotation)


def _bodies(nif: NifFile) -> 'list | None':
    """[(owner block, rigid body bytes, points, radius, material, owner's world place)] per
    collision owner, block order; None when any of it is not a convex rigid body we cover."""
    if any('Constraint' in kind or kind == 'bhkListShape' for kind, _ in nif.blocks):
        return None
    out = []
    for i, (_, block) in enumerate(nif.blocks):
        if not isinstance(block, dict) or block.get('collision', NONE) == NONE:
            continue
        kind, raw = nif.blocks[block['collision']]
        if kind != 'bhkCollisionObject':
            return None
        body_kind, body = nif.blocks[struct.unpack('<iHi', raw)[2]]
        motion = body[MOTION] if body_kind in BODY_KINDS else None
        shape = _convex(nif.blocks, struct.unpack_from('<i', body)[0]) if motion is not None else None
        if shape is None or not (motion in DYNAMIC or motion in (KEYFRAMED, FIXED)):
            return None
        out.append((i, body, *shape, _world(nif, i)))
    return out or None


# ---------------------------------------------------------------------------
# The physics system
# ---------------------------------------------------------------------------

def half(value: float) -> int:
    """`value` as hkHalf: its float32's top 16 bits, rounded."""
    return ((struct.unpack('<I', struct.pack('<f', value))[0] + 0x8000) >> 16) & 0xFFFF


def halved(value: float) -> float:
    """`value` rounded to hkHalf precision, as a float."""
    return struct.unpack('<f', struct.pack('<I', half(value) << 16))[0]


def _rotate(q: tuple, v: np.ndarray) -> np.ndarray:
    """Vector `v` rotated by quaternion `q` (x, y, z, w)."""
    u, w = np.array(q[:3]), q[3]
    return v + 2 * np.cross(u, np.cross(u, v) + w * v)


def _compose(a: tuple, b: tuple) -> tuple:
    """Quaternion product a * b (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _motion(body: bytes, mass, place: tuple, props: int) -> dict:
    """A dynamic body's motion cinfo: mass over its shape's density-1 `mass`, at body `place` (position,
    orientation), using motion properties `props`."""
    weight = struct.unpack_from('<f', body, MASS)[0]
    factor = weight / mass.volume
    com = place[0] + _rotate(place[1], mass.com)
    return {'motionPropertiesId': props, 'enableDeactivation': 1, 'inverseMass': 1 / weight, 'massFactor': factor,
            'maxLinearAccelerationDistancePerStep': UNBOUNDED, 'maxRotationToPreventTunneling': UNBOUNDED,
            'inverseInertiaLocal': (*(1 / (m * factor) for m in mass.inertia), 1.0),
            'centerOfMassWorld': (*com, 0.0), 'orientation': _compose(place[1], mass.frame),
            'linearVelocity': (0.0,) * 4, 'angularVelocity': (0.0,) * 4}


def _keyframed(place: tuple) -> dict:
    """A keyframed body's motion cinfo: no mass, the game's preset properties, at the body's `place`."""
    return {'motionPropertiesId': PRESET, 'enableDeactivation': 1, 'inverseMass': 0.0, 'massFactor': 1.0,
            'maxLinearAccelerationDistancePerStep': UNBOUNDED, 'maxRotationToPreventTunneling': UNBOUNDED,
            'inverseInertiaLocal': (0.0,) * 4, 'centerOfMassWorld': (*place[0], 0.0), 'orientation': place[1],
            'linearVelocity': (0.0,) * 4, 'angularVelocity': (0.0,) * 4}


def _properties(body: bytes) -> dict:
    """A dynamic body's motion properties: our damping at hkHalf precision, our max angular speed with its low
    SPEED_BITS rounded off."""
    linear, angular = struct.unpack_from('<2f', body, DAMPING)
    bits = struct.unpack_from('<I', body, MAX_ANGULAR)[0]
    spin = struct.unpack('<f', struct.pack('<I', (bits + (1 << SPEED_BITS - 1)) >> SPEED_BITS << SPEED_BITS))[0]
    return {**MOTION_PROPERTIES, 'linearDamping': halved(linear), 'angularDamping': halved(angular),
            'maxAngularSpeed': spin}


def _material(body: bytes) -> dict:
    """A body's material: our friction and restitution as hkHalf."""
    friction, restitution = struct.unpack_from('<f', body, FRICTION)[0], struct.unpack_from('<f', body, RESTITUTION)[0]
    return {**MATERIAL, 'dynamicFriction': half(friction), 'staticFriction': half(friction),
            'restitution': half(restitution)}


def _massive(body: bytes) -> bool:
    """Whether Elric gives `body` a full motion: dynamic, or keyframed with mass."""
    return body[MOTION] in DYNAMIC or (body[MOTION] == KEYFRAMED and struct.unpack_from('<f', body, MASS)[0] > 0)


def _flags(body: bytes) -> int:
    """A body cinfo's flags: DYNAMIC_FLAGS on a full motion, plus KEYFRAMED_FLAG."""
    if not _massive(body):
        return 0
    return DYNAMIC_FLAGS | (KEYFRAMED_FLAG if body[MOTION] == KEYFRAMED else 0)


def _body(index: int, body: bytes, motion_id: int, place: tuple) -> dict:
    """Body `index`'s cinfo: its shape, filter, motion, and its owner node's `place` (position, orientation)."""
    return {'shape': f'#s{index}', 'reservedBodyId': NO_ID, 'motionId': motion_id, 'qualityId': QUALITY,
            'materialId': index, 'collisionFilterInfo': struct.unpack_from('<I', body, FILTER)[0],
            'flags': _flags(body), 'collisionLookAheadDistance': 0.0, 'name': None, 'userData': 0,
            'position': (*place[0], 0.0), 'orientation': place[1], 'spuFlags': 0, 'localFrame': None}


def system(bodies: list) -> bytes:
    """The bhkPhysicsSystem block (u32 length, packfile) for `bodies` (_bodies' rows)."""
    shapes, cinfos, motions, props = [], [], [], []
    for index, (_, body, points, radius, crc, place) in enumerate(bodies):
        objects, mass = polytope(f'#s{index}', points, radius, crc)
        shapes += objects
        motion_id = NO_ID
        if _massive(body):
            motion_id, props = len(motions), props + [_properties(body)]
            motions.append(_motion(body, mass, place, len(props) - 1))
        elif body[MOTION] == KEYFRAMED:
            motion_id = len(motions)
            motions.append(_keyframed(place))
        cinfos.append(_body(index, body, motion_id, place))
    root = {'name': None, 'materials': [_material(b[1]) for b in bodies], 'motionProperties': props,
            'motionCinfos': motions, 'bodyCinfos': cinfos, 'constraintCinfos': [],
            'referencedObjects': [f'#s{i}' for i in range(len(bodies))]}
    data = packfile_write.write([{'#': '#root', 'class': 'hknpPhysicsSystemData', 'fields': root}] + shapes, '#root')
    return struct.pack('<I', len(data)) + data


def physics(nif: NifFile) -> 'tuple | None':
    """(bhkPhysicsSystem block, [owner per body]) for `nif`; None when not covered, a flat shape (no 3-D hull)
    included.
    See: docs/fork/fo4_hknp_writer.md#flat
    """
    bodies = _bodies(nif)
    if bodies is None:
        return None
    try:
        return system(bodies), [b[0] for b in bodies]
    except QhullError:
        return None


def finish(nif: NifFile) -> 'NifFile | None':
    """`nif` with its Havok input replaced by our physics; None (`nif` untouched) when not covered."""
    made = physics(nif)
    if made is None:
        return None
    block, owners = made
    without_havok(nif)
    nif.blocks.append(('bhkPhysicsSystem', block))
    at = len(nif.blocks) - 1
    for body, owner in enumerate(owners):
        nif.blocks.append(('bhkNPCollisionObject', struct.pack('<iHiI', owner, NP_FLAGS, at, body)))
        nif.blocks[owner][1]['collision'] = len(nif.blocks) - 1
    return nif
