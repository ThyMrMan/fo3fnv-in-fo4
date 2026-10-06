"""FNV collision as the Havok blocks Fallout 4's Elric turns into its own physics.

FNV's bhk blocks are written in FO4's pre-Elric layout (nif.xml at stream
130): the same shape blocks, a bhkRigidBody with the 2014 body info, and
FO4's materials and layers. Every length goes from FNV's Havok unit (game
units / 7) to FO4's (game units / 69.99), a factor of 0.1. A body on a child
node goes on a new NiNode under the root carrying that node's transform.

See: docs/fork/fo4_spikes.md#spike-2-collision
"""

import struct

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile

apply_patches()
from asset_convert.collision.collision import repaired_mesh_soup
from asset_convert.collision.collision_material import OB_TO_SK_MATERIAL

SCALE = 0.1
#: Game units per FO4 Havok unit: NiTriStripsData collision geometry is stored in game units.
GAME_PER_HAVOK = 7.0 / SCALE
#: Convex radius of a mesh shape (FNV's 0.1, scaled).
MESH_RADIUS = 0.01
#: FNV mesh collision shapes, which go through asset_convert's winding repair.
MESH_SHAPES = frozenset({'bhkMoppBvTreeShape', 'bhkPackedNiTriStripsShape', 'bhkNiTriStripsShape'})
#: bhkNiCollisionObject flags every post-FO3 game adds: SYNC_ON_UPDATE.
SYNC_ON_UPDATE = 0x80
#: FNV collision layers past 28 whose FO4 number differs (same names; 0-28 match).
LAYERS = {29: 32, 31: 34, 32: 35, 33: 36, 34: 37, 35: 39, 36: 40, 37: 41, 38: 42, 39: 43, 41: 45, 42: 46, 43: 0}
#: FNV base Havok materials (index & 31) as FO4 material CRCs.
MATERIALS = {
    0: 3741512247, 1: 3839073443, 2: 3106094762, 3: 3739830338, 4: 1848600814, 5: 104858580, 6: 2974920155,
    7: 591247106, 8: 1024582599, 9: 500811281, 10: 2253994566, 11: 706373264, 12: 3481395209, 13: 1998647255,
    14: 1949124673, 15: 104858580, 16: 2993325253, 17: 104858580, 18: 2168343821, 19: 1413383033,
    20: 2993292432, 21: 706373264, 22: 2993325253, 23: 2050332274, 24: 493553910, 25: 2674265083,
    26: 3639674437, 27: 1201612612, 28: 2963595456, 29: 2993325253, 30: 2113564165, 31: 3114373106,
}
#: FO4 stairs materials for FNV's stairs variants (index & 64); the others keep their base material.
STAIRS = {0: 2519395573, 2: 1340314491, 3: 2534329404, 4: 2926148967, 5: 3236651581, 9: 1879074862,
          10: 2519395573, 19: 1439425931}
#: An empty hkWorldObjectCinfo::Property (data, size, capacity and flags).
EMPTY_PROPERTY = struct.pack('<3I', 0, 0, 0x80000000)


def material(fnv: int) -> int:
    """An FO4 Havok material CRC for an FNV material index (platform bits ignored)."""
    base = fnv & 31
    return STAIRS.get(base, MATERIALS[base]) if fnv & 64 else MATERIALS[base]


def fo4_material(skyrim: int) -> int:
    """An FO4 material CRC for a Skyrim CRC of an FNV material, or a raw FNV index."""
    if skyrim < 128:
        return material(skyrim)
    return next((MATERIALS[i] for i in range(32) if OB_TO_SK_MATERIAL.get(i) == skyrim), MATERIALS[0])


def havok_filter(f) -> bytes:
    """An FNV HavokColFilter as FO4's: layer remapped, flags and group kept."""
    return struct.pack('<BBH', LAYERS.get(f.layer, f.layer), f.flags_and_part_number, f.unknown_short)


def _vec(v, n: int = 4, scale: float = SCALE) -> tuple:
    """The first `n` of x, y, z, w of a pyffi vector, x/y/z scaled (w kept)."""
    values = [v.x * scale, v.y * scale, v.z * scale, getattr(v, 'w', 0.0)]
    return tuple(values[:n])


class _Blocks:
    """Appends collision blocks to a NifFile, each as (type, bytes)."""

    def __init__(self, nif: NifFile):
        self.nif = nif

    def add(self, kind: str, body: bytes) -> int:
        """Append one block; its index."""
        self.nif.blocks.append((kind, body))
        return len(self.nif.blocks) - 1

    def shape(self, s) -> int:
        """Write FNV shape `s` (and its children); the index of its block."""
        kind = type(s).__name__
        packer = getattr(self, '_' + kind, None)
        if packer is None:
            raise ValueError(f'unsupported collision shape {kind}')
        return packer(s)

    def _bhkConvexVerticesShape(self, s) -> int:
        """Vertices and plane normals (their distance in w scaled)."""
        verts = b''.join(struct.pack('<4f', *_vec(v)) for v in s.vertices)
        normals = b''.join(struct.pack('<4f', n.x, n.y, n.z, n.w * SCALE) for n in s.normals)
        body = struct.pack('<If', material(s.material.material), s.radius * SCALE) + EMPTY_PROPERTY * 2
        body += struct.pack('<I', len(s.vertices)) + verts + struct.pack('<I', len(s.normals)) + normals
        return self.add('bhkConvexVerticesShape', body)

    def _bhkBoxShape(self, s) -> int:
        """Half extents."""
        return self.add('bhkBoxShape', struct.pack('<If8x3ff', material(s.material.material), s.radius * SCALE,
                                                   *_vec(s.dimensions, 3), 0.0))

    def _bhkSphereShape(self, s) -> int:
        """A radius."""
        return self.add('bhkSphereShape', struct.pack('<If', material(s.material.material), s.radius * SCALE))

    def _bhkCapsuleShape(self, s) -> int:
        """Two points and their radii."""
        return self.add('bhkCapsuleShape', struct.pack(
            '<If8x3ff3ff', material(s.material.material), s.radius * SCALE, *_vec(s.first_point, 3),
            s.radius_1 * SCALE, *_vec(s.second_point, 3), s.radius_2 * SCALE))

    def _bhkConvexTransformShape(self, s) -> int:
        """A convex shape under a transform (column-major, translation at 12-14 scaled)."""
        child = self.shape(s.shape)
        m = s.transform
        cells = [m.m_11, m.m_21, m.m_31, m.m_41, m.m_12, m.m_22, m.m_32, m.m_42,
                 m.m_13, m.m_23, m.m_33, m.m_43, m.m_14 * SCALE, m.m_24 * SCALE, m.m_34 * SCALE, m.m_44]
        return self.add('bhkConvexTransformShape', struct.pack('<iIf8x16f', child, material(s.material.material),
                                                               s.unknown_float_1 * SCALE, *cells))

    def _bhkListShape(self, s) -> int:
        """Sub-shapes, zeroed filters."""
        subs = [self.shape(c) for c in s.sub_shapes]
        return self.add('bhkListShape', struct.pack(f'<I{len(subs)}iI', len(subs), *subs,
                                                    material(s.material.material))
                        + EMPTY_PROPERTY * 2 + struct.pack(f'<I{len(subs)}I', len(subs), *[0] * len(subs)))

    def mesh(self, tris: list, materials: list, filt: bytes) -> int:
        """A repaired triangle soup (FO4 Havok units) as a bhkNiTriStripsShape: one NiTriStripsData per material."""
        groups = {}
        for tri, sky in zip(tris, materials):
            groups.setdefault(fo4_material(sky), []).append(tri)
        strips = []
        for crc, group in groups.items():
            index = {}
            faces = [tuple(index.setdefault(v, len(index)) for v in tri) for tri in group]
            verts = [tuple(c * GAME_PER_HAVOK for c in v) for v in index]
            strips.append(self.add('NiTriStripsData', tri_strips_data(verts, faces, crc)))
        return self.add('bhkNiTriStripsShape', struct.pack('<If20xI4fI', next(iter(groups)), MESH_RADIUS, 1,
                                                           1.0, 1.0, 1.0, 0.0, len(strips))
                        + struct.pack(f'<{len(strips)}iI', *strips, len(strips)) + filt * len(strips))


def tri_strips_data(verts: list, tris: list, crc: int) -> bytes:
    """NiTriStripsData at stream 130 holding `tris` as one 3-point strip each: positions, bound, material CRC."""
    n = len(verts)
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    center = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = max(sum((v[i] - center[i]) ** 2 for i in range(3)) ** 0.5 for v in verts)
    out = struct.pack('<iHBBB', 0, n, 0, 0, 1) + b''.join(struct.pack('<3f', *v) for v in verts)
    out += struct.pack('<HIB4fBHiH', 0, crc, 0, *center, radius, 0, 0, NONE, len(tris))
    out += struct.pack('<H', len(tris)) + struct.pack(f'<{len(tris)}H', *[3] * len(tris)) + b'\x01'
    return out + b''.join(struct.pack('<3H', *t) for t in tris)


def _body_shape(blocks: _Blocks, body, node) -> 'int | None':
    """The FO4 shape of `body` on FNV `node`; a mesh goes through the winding repair. None: drop it.

    The repair bakes a bhkRigidBodyT's transform into the mesh (the body
    becomes an identity one), so its translation is scaled to FO4 units first.
    """
    filt = havok_filter(body.havok_col_filter)
    if type(body.shape).__name__ not in MESH_SHAPES:
        return blocks.shape(body.shape)
    if type(body).__name__ == 'bhkRigidBodyT':
        t = body.translation
        t.x, t.y, t.z = t.x * SCALE, t.y * SCALE, t.z * SCALE
    soup = repaired_mesh_soup(body, node)
    if soup is None or soup == 'drop':
        return None
    return blocks.mesh(*soup, filt)


def _rigid_body(blocks: _Blocks, body, node) -> 'int | None':
    """FNV's bhkRigidBody(T) with the 2014 body info; lengths scaled, inertia by the square. None: no shape."""
    shape = _body_shape(blocks, body, node)
    if shape is None:
        return None
    filt = havok_filter(body.havok_col_filter)
    head = struct.pack('<i', shape) + filt + struct.pack('<4xB3x', 1) + EMPTY_PROPERTY
    head += struct.pack('<BBH', body.collision_response, 0, body.process_contact_callback_delay)
    inertia = body.inertia
    tensor = [inertia.m_11, inertia.m_12, inertia.m_13, inertia.m_14, inertia.m_21, inertia.m_22, inertia.m_23,
              inertia.m_24, inertia.m_31, inertia.m_32, inertia.m_33, inertia.m_34]
    rot = body.rotation
    info = struct.pack('<4x', ) + filt + bytes(12) + struct.pack('<4f', *_vec(body.translation))
    info += struct.pack('<4f', rot.x, rot.y, rot.z, rot.w) + struct.pack('<4f', *_vec(body.linear_velocity))
    info += struct.pack('<4f', body.angular_velocity.x, body.angular_velocity.y, body.angular_velocity.z, 0.0)
    info += struct.pack('<12f', *(t * SCALE * SCALE for t in tensor)) + struct.pack('<4f', *_vec(body.center))
    info += struct.pack('<9f', body.mass, body.linear_damping, body.angular_damping, 1.0, body.friction, 0.0,
                        body.restitution, body.max_linear_velocity, body.max_angular_velocity)
    info += struct.pack('<4Bff4xBBHBBBBB3x', body.motion_system, body.deactivator_type, body.solver_deactivation, 0,
                        body.penetration_depth * SCALE, 1.0, body.collision_response, 0,
                        body.process_contact_callback_delay, body.quality_type, 0, 0, 3, 0)
    return blocks.add(type(body).__name__, head + info + struct.pack('<IH', 0, 0))


def collision_object(nif: NifFile, co, target: int, node) -> int:
    """Write `co` of FNV `node` for block `target`, children first as Elric needs; its index (NONE: dropped)."""
    blocks = _Blocks(nif)
    body = _rigid_body(blocks, co.body, node)
    if body is None:
        return NONE
    return blocks.add('bhkCollisionObject', struct.pack('<iHi', target, co.flags | SYNC_ON_UPDATE, body))


def node_transform(node, root) -> tuple:
    """(translation, row-major rotation, scale) of an FNV node in root space."""
    scale, rot, trans = node.get_transform(root).get_scale_rotation_translation()
    rows = (rot.m_11, rot.m_12, rot.m_13, rot.m_21, rot.m_22, rot.m_23, rot.m_31, rot.m_32, rot.m_33)
    return (trans.x, trans.y, trans.z), tuple(float(r) for r in rows), float(scale)


def collision_nodes(nif: NifFile, fnv_root, root_index: int, node_flags: int) -> None:
    """Give the FO4 root FNV's collision: the root's own, and a NiNode per child node that has one.

    The NiNodes come first and every Havok block after them, so the Havok
    blocks are the file's tail (elric.graft swaps that tail for FO4's).
    """
    owners = []
    for node in fnv_root.tree():
        co = getattr(node, 'collision_object', None)
        if co is None or co.body is None:
            continue
        index = root_index
        if node is not fnv_root:
            translation, rotation, scale = node_transform(node, fnv_root)
            index = len(nif.blocks)
            nif.blocks.append(('NiNode', {
                'name': nif.string(node.name.decode('cp1252')), 'extra': [], 'controller': NONE,
                'flags': node_flags, 'translation': translation, 'rotation': rotation, 'scale': scale,
                'collision': NONE, 'children': []}))
            nif.blocks[root_index][1]['children'].append(index)
        owners.append((index, co, node))
    for index, co, node in owners:
        nif.blocks[index][1]['collision'] = collision_object(nif, co, index, node)
