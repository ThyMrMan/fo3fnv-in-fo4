"""Our own FO4 physics for a pre-Elric NIF, where it covers the input, in place of Elric's.

`physics(nif)` reads the collision blocks nif/collision.py wrote (bhkCollisionObject, bhkRigidBody,
convex shapes flat ones included, spheres and capsules, lists of those or of meshes, triangle meshes on massless
bodies, constraints, phantoms as trigger bodies) and gives the bhkPhysicsSystem block and each collision owner in
body order; None for input it does not cover yet. `finish(nif)` puts them in place of the Havok input as
elric.graft does.

See: docs/fork/fo4_hknp_writer.md#convex
"""

import struct
from collections.abc import Callable

import numpy as np
from scipy.spatial import QhullError

from fo4_import.havok import packfile_write
from fo4_import.nif import hknp_mesh
from fo4_import.nif.blocks import NONE
from fo4_import.nif.hknp_compound import compound
from fo4_import.nif.hknp_constraint import constraints
from fo4_import.nif.elric import without_havok
from fo4_import.nif.file import NifFile
from fo4_import.nif.hknp_convex import box_corners, polytope, quaternion
from fo4_import.nif.hknp_mesh import GAME_PER_HAVOK
from fo4_import.nif.hknp_round import capsule, sphere

#: Pre-Elric bhkRigidBody offsets: filter, mass, damping, friction, restitution, max angular speed, motion.
FILTER, MASS, DAMPING, FRICTION, RESTITUTION, MAX_ANGULAR, MOTION = 4, 180, 184, 196, 204, 212, 216
#: Low float32 bits Elric rounds off a body's max angular speed.
SPEED_BITS = 12
#: Havok 2014 motion systems: the dynamic ones (sphere, box and thin box inertia), keyframed, fixed.
DYNAMIC, KEYFRAMED, FIXED = frozenset({2, 3, 6}), 4, 5
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
CONVEX_KINDS = frozenset({'bhkConvexVerticesShape', 'bhkBoxShape', 'bhkSphereShape', 'bhkCapsuleShape'})
#: No move: a convex shape's own frame.
IDENTITY = np.eye(4)
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
#: A phantom's collision object, its body flags (a trigger) and its material.
PHANTOM_OBJECT, TRIGGER_BODY = 'bhkSPCollisionObject', 16
#: A shape our hull code cannot build (Qhull's failures, NaN from garbage input): not covered.
UNBUILT = (QhullError, ValueError)
TRIGGER_MATERIAL = {**MATERIAL, 'flags': 0x200000, 'triggerType': 2, 'dynamicFriction': 16128,
                    'staticFriction': 16128, 'restitution': 0}


# ---------------------------------------------------------------------------
# Reading our pre-Elric blocks
# ---------------------------------------------------------------------------

def convex(blocks: list, index: int, matrix: np.ndarray = IDENTITY) -> 'Callable | None':
    """The maker (name -> (objects, Mass)) of convex shape block `index` moved by 4×4 `matrix`, Havok units: a
    polytope of a convex shape's own vertices or a box's corners, a sphere, a capsule; None for any other."""
    kind, raw = blocks[index]
    moved = lambda points: np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]
    if kind == 'bhkConvexVerticesShape':
        crc, radius = struct.unpack_from('<If', raw)
        count = struct.unpack_from('<I', raw, 32)[0]
        points = moved(np.array(struct.unpack_from(f'<{4 * count}f', raw, 36)).reshape(-1, 4)[:, :3])
        return lambda name: polytope(name, points, radius, crc)
    if kind == 'bhkBoxShape':
        crc, radius, *half = struct.unpack_from('<If8x3f', raw)
        return lambda name: polytope(name, moved(box_corners(half)), radius, crc)
    if kind == 'bhkSphereShape':
        crc, radius = struct.unpack('<If', raw)
        return lambda name: sphere(name, moved(np.zeros(3)), radius, crc)
    if kind == 'bhkCapsuleShape':
        crc, radius, *ends = struct.unpack('<If8x3f4x3f4x', raw)
        return lambda name: capsule(name, moved(ends[:3]), moved(ends[3:]), radius, crc)
    if kind == 'bhkConvexTransformShape' and blocks[_transform(raw)[0]][0] in CONVEX_KINDS:
        child, cells = _transform(raw)
        return convex(blocks, child, matrix @ cells)
    return None


def _transform(raw: bytes) -> tuple:
    """(child block, 4×4 matrix) of a bhkConvexTransformShape."""
    child, _, _, *cells = struct.unpack('<iIf8x16f', raw)
    return child, np.array(cells).reshape(4, 4).T


def _mesh(mesh: hknp_mesh.Mesh) -> 'Callable | None':
    """The maker of triangle `mesh`; None when it has no triangles."""
    return (lambda name: (hknp_mesh.compressed(name, mesh), None)) if len(mesh.tris) else None


def _child(blocks: list, index: int) -> 'tuple | None':
    """(maker, 4×4 matrix) of list child block `index`: a convex transform's child in its own frame under
    the transform, else the child in place; None when not covered."""
    kind, raw = blocks[index]
    if kind == 'bhkConvexTransformShape':
        child, cells = _transform(raw)
        maker = convex(blocks, child) if blocks[child][0] in CONVEX_KINDS else None
        return None if maker is None else (maker, cells)
    mesh = hknp_mesh.read(blocks, index)
    maker = convex(blocks, index) if mesh is None else _mesh(mesh)
    return None if maker is None else (maker, IDENTITY)


def _list(blocks: list, index: int) -> 'Callable | None':
    """The maker of bhkListShape block `index` as a compound; None when any child is not covered."""
    raw = blocks[index][1]
    count = struct.unpack_from('<I', raw)[0]
    children = [_child(blocks, sub) for sub in struct.unpack_from(f'<{count}i', raw, 4)]
    if not children or any(c is None for c in children):
        return None
    material = struct.unpack_from('<I', raw, 4 + 4 * count)[0]
    return lambda name: compound(name, children, material)


def world(nif: NifFile, index: int) -> tuple:
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


def _shape(blocks: list, index: int, body: bytes) -> 'Callable | None':
    """The maker (name -> (objects, Mass or None)) of `body`'s shape block `index`: a convex shape (convex), a
    list (_list), or a triangle mesh on a body without a full motion; None for anything else."""
    if blocks[index][0] == 'bhkListShape':
        return _list(blocks, index)
    mesh = hknp_mesh.read(blocks, index)
    if mesh is None:
        return convex(blocks, index)
    return None if _massive(body) else _mesh(mesh)


def bodies(nif: NifFile, skip: frozenset = frozenset()) -> 'list | None':
    """[(owner block, rigid body bytes, shape, owner's world place)] per collision owner, block order, owners whose
    collision object is a kind in `skip` left out; None when any of the rest is not a rigid body we cover."""
    out = []
    for i, (_, block) in enumerate(nif.blocks):
        if not isinstance(block, dict) or block.get('collision', NONE) == NONE:
            continue
        kind, raw = nif.blocks[block['collision']]
        if kind in skip:
            continue
        if kind != 'bhkCollisionObject':
            return None
        body_kind, body = nif.blocks[struct.unpack('<iHi', raw)[2]]
        motion = body[MOTION] if body_kind in BODY_KINDS else None
        if not (motion in DYNAMIC or motion in (KEYFRAMED, FIXED)):
            return None
        shape = _shape(nif.blocks, struct.unpack_from('<i', body)[0], body)
        if shape is None:
            return None
        out.append((i, body, shape, world(nif, i)))
    return out


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


def phantoms(nif: NifFile, first: int = 0) -> 'tuple | None':
    """([(trigger body cinfo, shape objects)], [owner]) of `nif`'s phantoms as bodies from `first`, block order;
    None when one is not covered."""
    owners = [i for i, (_, b) in enumerate(nif.blocks) if isinstance(b, dict) and b.get('collision', NONE) != NONE
              and nif.blocks[b['collision']][0] == PHANTOM_OBJECT]
    made = [_phantom(nif, owner, first + i) for i, owner in enumerate(owners)]
    return None if any(m is None for m in made) else (made, owners)


# ---------------------------------------------------------------------------
# The physics system
# ---------------------------------------------------------------------------

def half(value: float) -> int:
    """`value` as hkHalf: its float32's top 16 bits, rounded."""
    return ((struct.unpack('<I', struct.pack('<f', value))[0] + 0x8000) >> 16) & 0xFFFF


def halved(value: float) -> float:
    """`value` rounded to hkHalf precision, as a float."""
    return struct.unpack('<f', struct.pack('<I', half(value) << 16))[0]


def rotate(q: tuple, v: np.ndarray) -> np.ndarray:
    """Vector `v` rotated by quaternion `q` (x, y, z, w)."""
    u, w = np.array(q[:3]), q[3]
    return v + 2 * np.cross(u, np.cross(u, v) + w * v)


def compose(a: tuple, b: tuple) -> tuple:
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
    com = place[0] + rotate(place[1], mass.com)
    return {'motionPropertiesId': props, 'enableDeactivation': 1, 'inverseMass': 1 / weight, 'massFactor': factor,
            'maxLinearAccelerationDistancePerStep': UNBOUNDED, 'maxRotationToPreventTunneling': UNBOUNDED,
            'inverseInertiaLocal': (*(1 / (m * factor) for m in mass.inertia), 1.0),
            'centerOfMassWorld': (*com, 0.0), 'orientation': compose(place[1], mass.frame),
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


def assemble(rows: list, joints: tuple = (), triggers: tuple = ()) -> tuple:
    """(hknpPhysicsSystemData fields, the other packfile objects) for `rows` (bodies()), `joints` [(constraint
    cinfo, its data object)] and phantom `triggers` (phantoms()) after the bodies."""
    shapes, cinfos, motions, props = [], [], [], []
    for index, (_, body, shape, place) in enumerate(rows):
        objects, mass = shape(f'#s{index}')
        if _massive(body) and mass is not None and not mass.solid:
            raise ValueError('a moving body on a flat or thin shape (Elric\'s mass for it is unread)')
        shapes += objects
        motion_id = NO_ID
        if _massive(body):
            motion_id, props = len(motions), props + [_properties(body)]
            motions.append(_motion(body, mass, place, len(props) - 1))
        elif body[MOTION] == KEYFRAMED:
            motion_id = len(motions)
            motions.append(_keyframed(place))
        cinfos.append(_body(index, body, motion_id, place))
    root = {'name': None, 'materials': [_material(b[1]) for b in rows] + [dict(TRIGGER_MATERIAL) for _ in triggers],
            'motionProperties': props, 'motionCinfos': motions, 'bodyCinfos': cinfos + [c for c, _ in triggers],
            'constraintCinfos': [c for c, _ in joints],
            'referencedObjects': [c['shape'] for c in cinfos] + [c['shape'] for c, _ in triggers]}
    return root, shapes + [o for _, objects in triggers for o in objects] + [d for _, d in joints]


def pack(cls: str, root: dict, objects: list) -> bytes:
    """A system block (u32 length, packfile): root class `cls`, `objects`."""
    data = packfile_write.write([{'#': '#root', 'class': cls, 'fields': root}] + objects, '#root')
    return struct.pack('<I', len(data)) + data


def system(rows: list, joints: tuple = (), triggers: tuple = ()) -> bytes:
    """The bhkPhysicsSystem block for `rows`, `joints` and `triggers` (assemble())."""
    return pack('hknpPhysicsSystemData', *assemble(rows, joints, triggers))


def joints_of(nif: NifFile, rows: list, motor: 'str | None' = None) -> 'list | None':
    """constraints() between the bodies of `rows`, motor slots on `motor`."""
    ids = {struct.unpack('<iHi', nif.blocks[nif.blocks[b[0]][1]['collision']][1])[2]: n for n, b in enumerate(rows)}
    return constraints(nif.blocks, ids, motor)


def physics(nif: NifFile) -> 'tuple | None':
    """(bhkPhysicsSystem block, [owner per body]) for `nif`; None when not covered, a flat shape (no 3-D hull)
    included.
    See: docs/fork/fo4_hknp_writer.md#flat
    """
    rows = bodies(nif, frozenset({PHANTOM_OBJECT}))
    joints = None if rows is None else joints_of(nif, rows)
    try:
        made = None if joints is None else phantoms(nif, len(rows))
        if made is None or not rows + made[1]:
            return None
        return system(rows, joints, made[0]), [b[0] for b in rows] + made[1]
    except UNBUILT:
        return None


def replace(nif: NifFile, systems: list) -> NifFile:
    """`nif` without its Havok input, then each of `systems` [(block kind, block, owner blocks in body order)]
    appended with a bhkNPCollisionObject on each owner (found again after the input's removal renumbers them)."""
    held = [[id(nif.blocks[o][1]) for o in owners] for _, _, owners in systems]
    without_havok(nif)
    at = {id(block): i for i, (_, block) in enumerate(nif.blocks)}
    for (kind, block, _), owners in zip(systems, held):
        nif.blocks.append((kind, block))
        system_at = len(nif.blocks) - 1
        for body, owner in enumerate(at[o] for o in owners):
            nif.blocks.append(('bhkNPCollisionObject', struct.pack('<iHiI', owner, NP_FLAGS, system_at, body)))
            nif.blocks[owner][1]['collision'] = len(nif.blocks) - 1
    return nif


def finish(nif: NifFile) -> 'NifFile | None':
    """`nif` with our physics for its Havok input; None when not covered."""
    made = physics(nif)
    return None if made is None else replace(nif, [('bhkPhysicsSystem', *made)])
