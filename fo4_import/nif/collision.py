"""FNV collision as the Havok blocks Fallout 4's Elric turns into its own physics.

FNV's bhk blocks are written in FO4's pre-Elric layout (nif.xml at stream
130): the same shape blocks, a bhkRigidBody with the 2014 body info, and
FO4's materials and layers. Every length goes from FNV's Havok unit (game
units / 7) to FO4's (game units / 69.99), a factor of 0.1. A body on a child
node goes on a new NiNode under the root carrying that node's transform.

See: docs/fork/fo4_spikes.md#spike-2-collision
"""

import struct
from bisect import bisect_right
from itertools import accumulate
from types import SimpleNamespace

import numpy as np
from scipy.spatial import ConvexHull

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from fo4_import.base.source_fault import SourceFault
from fo4_import.nif import fnv_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile
from fo4_import.nif.stairs import stairs

apply_patches()
from asset_convert.collision.collision import mesh_soup, repaired_mesh_soup, visual_tri_soup_in
from pyffi.formats.nif import NifFormat

SCALE = 0.1
#: Game units per FO4 Havok unit: NiTriStripsData collision geometry is stored in game units.
GAME_PER_HAVOK = 7.0 / SCALE
#: Convex radius of a mesh shape (FNV's 0.1, scaled).
MESH_RADIUS = 0.01
#: FNV mesh collision shapes, which go through asset_convert's winding repair.
MESH_SHAPES = frozenset({'bhkMoppBvTreeShape', 'bhkPackedNiTriStripsShape', 'bhkNiTriStripsShape'})
#: Convex FNV shapes a bhkRigidBodyT's transform is moved onto, as a bhkConvexTransformShape.
CONVEX_SHAPES = frozenset({'bhkBoxShape', 'bhkSphereShape', 'bhkCapsuleShape', 'bhkConvexVerticesShape'})
#: bhkNiCollisionObject flags every post-FO3 game adds: SYNC_ON_UPDATE.
SYNC_ON_UPDATE = 0x80
#: FNV collision layers past 28 whose FO4 number differs (same names; 0-28 match).
LAYERS = {29: 32, 31: 34, 32: 35, 33: 36, 34: 37, 35: 39, 36: 40, 37: 41, 38: 42, 39: 43, 41: 45, 42: 46, 43: 0}
#: A moving body's layer where FO4's use differs: props (10) is for small knock-about props, clutter (4) the rest.
MOVING_LAYERS = {10: 4}
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
#: FO4 stairs material of each FO4 base material that has one (FNV's stairs pairs).
STAIRS_OF = {MATERIALS[base]: pair for base, pair in STAIRS.items()}
#: FNV motion systems as Havok 2014's, which Elric reads; keyframed is fixed unless its node keeps its animation.
MOTIONS = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 5, 7: 5, 8: 6, 9: 7}
#: FNV's keyframed motion system and Havok 2014's, for a body on a node that keeps its animation.
FNV_KEYFRAMED, KEYFRAMED = 6, 4
#: Havok 2014's fixed motion; FNV's collision layer that collides with nothing (NONCOLLIDABLE).
FIXED, NONCOLLIDABLE = 5, 15
#: FNV constraint -> (descriptor, body A's vectors then pivot, body B's, then angles), in FO4's (Havok 2010) order.
JOINT_FIELDS = {
    'bhkRagdollConstraint': ('ragdoll', ('twist_a', 'plane_a', 'motor_a', 'pivot_a'),
                             ('twist_b', 'plane_b', 'motor_b', 'pivot_b'),
                             ('cone_max_angle', 'plane_min_angle', 'plane_max_angle', 'twist_min_angle',
                              'twist_max_angle', 'max_friction')),
    'bhkLimitedHingeConstraint': ('limited_hinge', ('axle_a', 'perp_2_axle_in_a_1', 'perp_2_axle_in_a_2', 'pivot_a'),
                                  ('axle_b', 'perp_2_axle_in_b_1', 'perp_2_axle_in_b_2', 'pivot_b'),
                                  ('min_angle', 'max_angle', 'max_friction')),
}
#: A joint's friction torque scales with length like a lever, so FNV's units to FO4's (see fo4_spikes own-rig-ragdoll).
FRICTION_SCALE = SCALE
#: FNV motion systems of bodies that never move under physics (keyframed, fixed): their meshes get both sides.
STILL_MOTIONS = frozenset({6, 7})
#: FO4's stair-helper layer (31, Skyrim's numbering), met only by the character controller: vanilla's stair ramps.
STAIR_HELPER = struct.pack('<BBH', 31, 0, 0)
#: The name of the NiNode carrying a stair-helper ramp body, and an identity rotation as a NiNode stores it.
STAIR_HELPER_NODE, IDENTITY = 'StairHelper', (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
#: FO4's character controller layer (vanilla creature skeletons' CharacterController and CharacterBumper).
CHARCONTROLLER = 30
#: A creature skeleton's controller nodes and their capsules' radius, as a share of its bound's half width.
CONTROLLER_RADII = (('CharacterController', 0.8), ('CharacterBumper', 1.2))
#: An empty hkWorldObjectCinfo::Property (data, size, capacity and flags).
EMPTY_PROPERTY = struct.pack('<3I', 0, 0, 0x80000000)
#: A phantom's identity transform (its shape carries any offset).
IDENTITY_44 = struct.pack('<16f', 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
#: FNV's water collision layer: placeable water's phantoms, converted on their own (fo4_pipeline.md#placeable-water).
FNV_WATER = 11


def is_mesh(shape) -> bool:
    """Whether FNV `shape` is a triangle mesh or a MOPP tree over one.

    See: docs/fork/fo4_pipeline.md#mixed-collision
    """
    kind = type(shape).__name__
    return kind in MESH_SHAPES and (kind != 'bhkMoppBvTreeShape' or is_mesh(shape.shape))


def material(fnv: int) -> int:
    """An FO4 Havok material CRC for an FNV material index (platform bits ignored)."""
    base = fnv & 31
    return STAIRS.get(base, MATERIALS[base]) if fnv & 64 else MATERIALS[base]


def stairs_material(crc: int) -> int:
    """The FO4 stairs material for base material `crc` (default: stone stairs)."""
    return crc if crc in STAIRS_OF.values() else STAIRS_OF.get(crc, STAIRS[0])


def triangle_materials(shape, n: int) -> list:
    """FO4 material of each of an FNV mesh shape's `n` non-degenerate triangles, in the repair's soup order.

    A packed shape's triangle belongs to the sub-shape (on its data at
    20.2.0.7) whose vertex range holds its first vertex.
    """
    parts = list(shape.data.sub_shapes) if type(shape).__name__ == 'bhkPackedNiTriStripsShape' else []
    if not parts:
        return [material(shape.material.material if hasattr(shape, 'material') else 0)] * n
    ends = list(accumulate(p.num_vertices for p in parts))
    owners = [min(bisect_right(ends, t.triangle.v_1), len(parts) - 1) for t in shape.data.triangles
              if len({t.triangle.v_1, t.triangle.v_2, t.triangle.v_3}) == 3]
    return [material(parts[o].material.material) for o in owners]


def moves(body) -> bool:
    """Whether FNV body `body` moves: not still; collidable or constrained.
    See: docs/fork/fo4_pipeline.md#still-bodies
    """
    held = body.havok_col_filter.layer != NONCOLLIDABLE or body.num_constraints > 0
    return body.motion_system not in STILL_MOTIONS and held


def havok_filter(f, moving: bool = False) -> bytes:
    """An FNV HavokColFilter as FO4's: layer remapped (MOVING_LAYERS too when `moving`), flags and group kept.
    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    layer = LAYERS.get(f.layer, f.layer)
    layer = MOVING_LAYERS.get(layer, layer) if moving else layer
    return struct.pack('<BBH', layer, f.flags_and_part_number, f.unknown_short)


def _vec(v, n: int = 4, scale: float = SCALE) -> tuple:
    """The first `n` of x, y, z, w of a pyffi vector, x/y/z scaled (w kept)."""
    values = [v.x * scale, v.y * scale, v.z * scale, getattr(v, 'w', 0.0)]
    return tuple(values[:n])


class _Blocks:
    """Appends collision blocks to a NifFile, each as (type, bytes)."""

    def __init__(self, nif: NifFile, scale: float = 1.0, root=None, animated: bool = False, body=None,
                 soups: dict = None):
        """Write into `nif`; lengths grown by `scale`; `root` is the FNV mesh root; `animated`: the node moves;
        `body` is (FNV rigid body, its node), for meshes inside a list; `soups` {id(body): _mesh_soup()} made
        already."""
        self.nif = nif
        self.unit = SCALE * scale
        self.root = root
        self.animated = animated
        self.body = body
        self.soups = soups or {}

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
        verts = b''.join(struct.pack('<4f', *_vec(v, 4, self.unit)) for v in s.vertices)
        normals = b''.join(struct.pack('<4f', n.x, n.y, n.z, n.w * self.unit) for n in s.normals)
        body = struct.pack('<If', material(s.material.material), s.radius * self.unit) + EMPTY_PROPERTY * 2
        body += struct.pack('<I', len(s.vertices)) + verts + struct.pack('<I', len(s.normals)) + normals
        return self.add('bhkConvexVerticesShape', body)

    def convex(self, points: np.ndarray, crc: int) -> int:
        """A bhkConvexVerticesShape of material `crc` around `points` (FO4 Havok units), its planes their hull's."""
        planes = np.unique(ConvexHull(points).equations.round(6), axis=0)
        body = struct.pack('<If', crc, MESH_RADIUS) + EMPTY_PROPERTY * 2
        body += struct.pack('<I', len(points)) + b''.join(struct.pack('<4f', *p, 0.0) for p in points)
        body += struct.pack('<I', len(planes)) + b''.join(struct.pack('<4f', *e) for e in planes)
        return self.add('bhkConvexVerticesShape', body)

    def _bhkBoxShape(self, s) -> int:
        """Half extents."""
        return self.add('bhkBoxShape', struct.pack('<If8x3ff', material(s.material.material), s.radius * self.unit,
                                                   *_vec(s.dimensions, 3, self.unit), 0.0))

    def _bhkSphereShape(self, s) -> int:
        """A radius."""
        return self.add('bhkSphereShape', struct.pack('<If', material(s.material.material), s.radius * self.unit))

    def _bhkCapsuleShape(self, s) -> int:
        """Two points and their radii."""
        return self.add('bhkCapsuleShape', struct.pack(
            '<If8x3ff3ff', material(s.material.material), s.radius * self.unit, *_vec(s.first_point, 3, self.unit),
            s.radius_1 * self.unit, *_vec(s.second_point, 3, self.unit), s.radius_2 * self.unit))

    def _bhkConvexTransformShape(self, s) -> int:
        """A convex shape under a transform (column-major, translation at 12-14 scaled)."""
        child = self.shape(s.shape)
        m = s.transform
        cells = [m.m_11, m.m_21, m.m_31, m.m_41, m.m_12, m.m_22, m.m_32, m.m_42,
                 m.m_13, m.m_23, m.m_33, m.m_43, m.m_14 * self.unit, m.m_24 * self.unit, m.m_34 * self.unit, m.m_44]
        return self.add('bhkConvexTransformShape', struct.pack('<iIf8x16f', child, material(s.material.material),
                                                               s.unknown_float_1 * self.unit, *cells))

    def transformed(self, child: int, s, body) -> int:
        """`child` (FNV shape `s`) under bhkRigidBodyT `body`'s rotation and translation: a bhkConvexTransformShape."""
        q, (tx, ty, tz) = body.rotation, _vec(body.translation, 3, self.unit)
        x, y, z, w = q.x, q.y, q.z, q.w
        cells = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0.0,
                 2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0.0,
                 2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0.0, tx, ty, tz, 1.0]
        return self.add('bhkConvexTransformShape', struct.pack('<iIf8x16f', child, material(s.material.material),
                                                               s.radius * self.unit, *cells))

    def _bhkMoppBvTreeShape(self, s) -> int:
        """A MOPP over a list: the list; one inside a list: its repaired mesh."""
        return self.shape(s.shape) if not is_mesh(s) else self._nested_mesh(s, None)

    def _bhkTransformShape(self, s) -> int:
        """A transform inside a list: over a convex shape a bhkConvexTransformShape, over a mesh baked into it."""
        if not is_mesh(s.shape):
            return self._bhkConvexTransformShape(s)
        m = s.transform
        rows = np.array([[m.m_11, m.m_12, m.m_13], [m.m_21, m.m_22, m.m_23], [m.m_31, m.m_32, m.m_33]])
        return self._nested_mesh(s.shape, (rows, np.array([m.m_14, m.m_24, m.m_34]) * self.unit))

    def _nested_mesh(self, s, transform: 'tuple | None') -> int:
        """Mesh shape `s` inside a list, through the winding repair as a whole body's, moved by `transform`
        (rotation rows, translation)."""
        body, node = self.body
        soup = _mesh_soup(SimpleNamespace(shape=s), node, self.root, self.unit / SCALE, not two_sided(body))
        if soup is None:
            raise ValueError(f'no triangles in nested {type(s).__name__}')
        tris, materials, _ = soup
        if transform is not None:
            tris = [tuple(tuple(float(c) for c in transform[0] @ v + transform[1]) for v in tri) for tri in tris]
        return self.mesh(*both_sides((tris, materials), body), havok_filter(body.havok_col_filter))

    def _bhkListShape(self, s) -> int:
        """Sub-shapes, zeroed filters."""
        subs = [self.shape(c) for c in s.sub_shapes]
        return self.add('bhkListShape', struct.pack(f'<I{len(subs)}iI', len(subs), *subs,
                                                    material(s.material.material))
                        + EMPTY_PROPERTY * 2 + struct.pack(f'<I{len(subs)}I', len(subs), *[0] * len(subs)))

    def _bhkConvexListShape(self, s) -> int:
        """FO3's list of convex shapes, as a bhkListShape of them."""
        return self._bhkListShape(s)

    def mesh(self, tris: list, materials: list, filt: bytes) -> int:
        """A repaired triangle soup (FO4 Havok units) as a bhkNiTriStripsShape: one NiTriStripsData per material."""
        groups = {}
        for tri, crc in zip(tris, materials):
            groups.setdefault(crc, []).append(tri)
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

    A bhkRigidBodyT's transform moves into the shape (the body becomes an
    identity one, see _baked): the repair bakes it into a mesh, its
    translation scaled to FO4 units first; a convex shape goes under a
    bhkConvexTransformShape. A mesh's steps take stairs materials and risers (stairs.py).
    """
    kind = type(body.shape).__name__
    if not is_mesh(body.shape):
        shape = blocks.shape(body.shape)
        return blocks.transformed(shape, body.shape, body) if _baked(body) and kind in CONVEX_SHAPES else shape
    soup = (blocks.soups[id(body)] if id(body) in blocks.soups
            else _mesh_soup(body, node, blocks.root, blocks.unit / SCALE, not two_sided(body)))
    return None if soup is None else blocks.mesh(*both_sides(soup[:2], body), havok_filter(body.havok_col_filter))


def both_sides(soup: tuple, body) -> tuple:
    """(triangles, materials) with a reversed copy of each triangle not already present, for a fixed or keyframed
    `body`: FNV collides with both sides of a triangle, FO4's character only with its front.

    See: docs/fork/fo4_pipeline.md#two-sided-collision
    """
    tris, materials = soup
    if not two_sided(body):
        return soup
    have = {_tri_key(t) for t in tris}
    extra = [(i, (t[0], t[2], t[1])) for i, t in enumerate(tris) if _tri_key((t[0], t[2], t[1])) not in have]
    return list(tris) + [t for _, t in extra], list(materials) + [materials[i] for i, _ in extra]


def two_sided(body) -> bool:
    """Whether FNV `body` is fixed or keyframed: its mesh gets both sides."""
    return getattr(body, 'motion_system', None) in STILL_MOTIONS


def _tri_key(tri) -> tuple:
    """A triangle's rounded corners from its smallest (same winding, same key)."""
    corners = [tuple(round(c, 4) for c in v) for v in tri]
    first = corners.index(min(corners))
    return tuple(corners[first:] + corners[:first])


def _mesh_soup(body, node, root, grow: float, repair: bool) -> 'tuple | None':
    """(triangles in FO4 Havok units, materials, stair ramps) of FNV mesh `body` on `node`: winding repaired when
    `repair` (not for a mesh both_sides doubles), grown by `grow`, through the stairs pass. None: drop it. A
    bhkRigidBodyT's translation is scaled in place first (call once per body).

    See: docs/fork/fo4_pipeline.md#two-sided-collision
    """
    if type(body).__name__ == 'bhkRigidBodyT':
        t = body.translation
        t.x, t.y, t.z = t.x * SCALE, t.y * SCALE, t.z * SCALE
    soup = (repaired_mesh_soup(body, node, triangle_materials, repair_oracle(root, node)) if repair
            else mesh_soup(body, triangle_materials))
    if soup is None or soup == 'drop':
        return None
    tris = [tuple(tuple(c * grow for c in v) for v in tri) for tri in soup[0]]
    return stairs(tris, soup[1], GAME_PER_HAVOK, stairs_material)


def mesh_triangles(path: str) -> tuple:
    """(triangles in game units, FO4 materials) of the FNV NIF at `path`'s root mesh collision, as converted."""
    data = fnv_file.read(path)
    root = data.roots[0]
    tris, materials, _ = _mesh_soup(root.collision_object.body, root, root, 1.0, True)
    return [tuple(tuple(c * GAME_PER_HAVOK for c in v) for v in tri) for tri in tris], materials


def repair_oracle(root, node) -> 'list | None':
    """A collision-only node's repair oracle: the mesh's render triangles, or None.

    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    if root is None or node is root or any(isinstance(b, NifFormat.NiTriBasedGeom) for b in node.tree()):
        return None
    return visual_tri_soup_in(root, node)


def _baked(body) -> bool:
    """Whether bhkRigidBodyT `body`'s transform moves into its shape."""
    return type(body).__name__ == 'bhkRigidBodyT' and (is_mesh(body.shape) or type(body.shape).__name__ in CONVEX_SHAPES)


def _rigid_body(blocks: _Blocks, body, node) -> 'int | None':
    """FNV's bhkRigidBody(T) with its converted shape (_body_block); None: no shape."""
    baked = _baked(body)
    shape = _body_shape(blocks, body, node)
    return None if shape is None else _body_block(blocks, shape, body, baked)


def _motion(fnv: int) -> int:
    """MOTIONS[`fnv`]; SourceFault for one Havok does not define."""
    if fnv not in MOTIONS:
        raise SourceFault(None, f'Havok motion system {fnv} is not defined')
    return MOTIONS[fnv]


def _body_block(blocks: _Blocks, shape: int, body, baked: bool, filt: bytes = None) -> int:
    """FNV `body` around block `shape` with the 2014 body info; lengths scaled, inertia by the square; its
    filter, or `filt`.

    A body whose transform its shape carries (`baked`) is written as an identity bhkRigidBody.
    """
    filt = filt or havok_filter(body.havok_col_filter, moves(body))
    head = struct.pack('<i', shape) + filt + struct.pack('<4xB3x', 1) + EMPTY_PROPERTY
    head += struct.pack('<BBH', body.collision_response, 0, body.process_contact_callback_delay)
    inertia = body.inertia
    tensor = [inertia.m_11, inertia.m_12, inertia.m_13, inertia.m_14, inertia.m_21, inertia.m_22, inertia.m_23,
              inertia.m_24, inertia.m_31, inertia.m_32, inertia.m_33, inertia.m_34]
    rot = body.rotation
    place = (0.0,) * 4 + (0.0, 0.0, 0.0, 1.0) if baked else (*_vec(body.translation, 4, blocks.unit), rot.x, rot.y,
                                                              rot.z, rot.w)
    info = struct.pack('<4x', ) + filt + bytes(12) + struct.pack('<8f', *place)
    info += struct.pack('<4f', *_vec(body.linear_velocity))
    info += struct.pack('<4f', body.angular_velocity.x, body.angular_velocity.y, body.angular_velocity.z, 0.0)
    info += struct.pack('<12f', *(t * SCALE * SCALE for t in tensor)) + struct.pack('<4f', *_vec(body.center))
    info += struct.pack('<9f', body.mass, body.linear_damping, body.angular_damping, 1.0, body.friction, 0.0,
                        body.restitution, body.max_linear_velocity, body.max_angular_velocity)
    motion = KEYFRAMED if blocks.animated and body.motion_system == FNV_KEYFRAMED else _motion(body.motion_system)
    motion = motion if moves(body) or motion == KEYFRAMED else FIXED
    info += struct.pack('<4Bff4xBBHBBBBB3x', motion, body.deactivator_type, body.solver_deactivation, 0,
                        body.penetration_depth * SCALE, 1.0, body.collision_response, 0,
                        body.process_contact_callback_delay, body.quality_type, 0, 0, 3, 0)
    return blocks.add('bhkRigidBody' if baked else type(body).__name__, head + info + struct.pack('<IH', 0, 0))


def collision_object(nif: NifFile, co, target: int, node, scale: float = 1.0, root=None,
                     animated: bool = False, soups: dict = None) -> int:
    """Write `co` of FNV `node` for block `target`, its shapes grown by `scale`, children first as Elric needs;
    keyframed when `animated` (the node keeps its animation); a mesh soup from `soups` when made already.

    Its index (NONE: dropped).
    """
    blocks = _Blocks(nif, scale, root, animated, (co.body, node), soups)
    body = _rigid_body(blocks, co.body, node)
    if body is None:
        return NONE
    return blocks.add('bhkCollisionObject', struct.pack('<iHi', target, co.flags | SYNC_ON_UPDATE, body))


def mesh_collision(nif: NifFile, target: int, tris: list, materials: list, template) -> int:
    """A collision object for block `target`: triangles `tris` (game units, wound outward) with FO4 material CRCs
    `materials`, as is (no repair, no stairs pass), on FNV collision object `template`'s body settings; its index."""
    blocks = _Blocks(nif)
    soup = [tuple(tuple(c / GAME_PER_HAVOK for c in v) for v in tri) for tri in tris]
    shape = blocks.mesh(soup, materials, havok_filter(template.body.havok_col_filter))
    body = _body_block(blocks, shape, template.body, True)
    return blocks.add('bhkCollisionObject', struct.pack('<iHi', target, template.flags | SYNC_ON_UPDATE, body))


def node_transform(node, root) -> tuple:
    """(translation, rotation as Elric reads it, scale) of an FNV node in root space.

    See: docs/fork/fo4_spikes.md#spike-2-collision
    """
    scale, rot, trans = node.get_transform(root).get_scale_rotation_translation()
    cells = (rot.m_11, rot.m_21, rot.m_31, rot.m_12, rot.m_22, rot.m_32, rot.m_13, rot.m_23, rot.m_33)
    return (trans.x, trans.y, trans.z), tuple(float(r) for r in cells), float(scale)


def collision_nodes(nif: NifFile, fnv_root, root_index: int, node_flags: int, kept: dict = None) -> None:
    """Give the FO4 root FNV's collision: the root's own, and a NiNode per child node that has one; a `kept`
    node ({id(FNV node): FO4 index}, an animated one) carries its own.

    NiNodes first, every Havok block after them (elric.graft swaps that tail).
    Elric ignores a node's scale, so the node gets 1.0 and its shapes the scale. Rigid bodies and trigger
    phantoms (a trap's volume) convert; water phantoms are left out.
    See: docs/fork/fo4_spikes.md#spike-4-exterior
    See: docs/fork/fo4_pipeline.md#trap-triggers
    """
    owners, phantoms = [], []
    for node in fnv_root.tree():
        co = getattr(node, 'collision_object', None)
        kind = type(co.body).__name__ if co is not None and co.body is not None else ''
        trigger = kind == 'bhkSimpleShapePhantom' and int(co.body.havok_col_filter.layer) != FNV_WATER
        if not trigger and not kind.startswith('bhkRigidBody'):
            continue
        index, scale = _collision_node(nif, node, fnv_root, root_index, node_flags, kept or {})
        (phantoms if trigger else owners).append((index, co, node, scale))
    soups, ramps = _stair_ramps(nif, owners, root_index, node_flags, fnv_root, kept or {})
    for index, co, _, scale in phantoms:
        blocks = _Blocks(nif, scale)
        nif.blocks[index][1]['collision'] = _phantom(blocks, index, blocks.shape(co.body.shape),
                                                     havok_filter(co.body.havok_col_filter))
    bodies = {}
    for index, co, node, scale in owners:
        nif.blocks[index][1]['collision'] = collision_object(nif, co, index, node, scale, fnv_root,
                                                             id(node) in (kept or {}), soups)
        if nif.blocks[index][1]['collision'] != NONE:
            body = struct.unpack_from('<iHi', nif.blocks[nif.blocks[index][1]['collision']][1])[2]
            bodies[id(co.body)] = (co.body, body, scale)
    for index, ramp, co in ramps:
        nif.blocks[index][1]['collision'] = _ramp_object(nif, index, ramp, co)
    joints(nif, bodies)


def _collision_node(nif: NifFile, node, fnv_root, root_index: int, node_flags: int, kept: dict) -> tuple:
    """(FO4 block index, scale) carrying FNV `node`'s collision: the root, a `kept` node, or a new NiNode under
    the root at the node's place."""
    if node is fnv_root or id(node) in kept:
        return kept.get(id(node), root_index), 1.0
    translation, rotation, scale = node_transform(node, fnv_root)
    nif.blocks.append(('NiNode', {
        'name': nif.string(node.name.decode('cp1252')), 'extra': [], 'controller': NONE,
        'flags': node_flags, 'translation': translation, 'rotation': rotation, 'scale': 1.0,
        'collision': NONE, 'children': []}))
    nif.blocks[root_index][1]['children'].append(len(nif.blocks) - 1)
    return len(nif.blocks) - 1, scale


def _phantom(blocks: '_Blocks', node: int, shape: int, filt: bytes) -> int:
    """A bhkSPCollisionObject on `node` holding a phantom of `shape`, filter `filt`."""
    head = struct.pack('<i', shape) + filt + struct.pack('<4xB3x', 1) + EMPTY_PROPERTY
    phantom = blocks.add('bhkSimpleShapePhantom', head + bytes(8) + IDENTITY_44)
    return blocks.add('bhkSPCollisionObject', struct.pack('<iHi', node, 1 | SYNC_ON_UPDATE, phantom))


def _stair_ramps(nif: NifFile, owners: list, root_index: int, node_flags: int, fnv_root, kept: dict) -> tuple:
    """({id(body): _mesh_soup()} of each still mesh body in `owners` (index, co, node, scale): fixed, or keyframed
    on a node not `kept` animated; [(NiNode index, stair ramp, its owner's co)]): a NiNode under the root per
    ramp, at its owner's place.

    See: docs/fork/fo4_spikes.md#stair-ramps
    """
    soups, ramps = {}, []
    for index, co, node, scale in owners:
        motion = co.body.motion_system
        if not is_mesh(co.body.shape) or motion not in STILL_MOTIONS or (motion == FNV_KEYFRAMED and id(node) in kept):
            continue
        soups[id(co.body)] = soup = _mesh_soup(co.body, node, fnv_root, scale, False)
        owner = nif.blocks[index][1]
        for ramp in soup[2] if soup else ():
            nif.blocks.append(('NiNode', {
                'name': nif.string(STAIR_HELPER_NODE), 'extra': [], 'controller': NONE, 'flags': node_flags,
                'translation': owner['translation'] if index != root_index else (0.0, 0.0, 0.0),
                'rotation': owner['rotation'] if index != root_index else IDENTITY, 'scale': 1.0,
                'collision': NONE, 'children': []}))
            nif.blocks[root_index][1]['children'].append(len(nif.blocks) - 1)
            ramps.append((len(nif.blocks) - 1, ramp, co))
    return soups, ramps


def _ramp_object(nif: NifFile, target: int, ramp: tuple, co) -> int:
    """Block `target`'s collision object: stair-helper `ramp` on `co`'s body settings."""
    blocks = _Blocks(nif)
    body = _body_block(blocks, blocks.convex(*ramp), co.body, True, STAIR_HELPER)
    return blocks.add('bhkCollisionObject', struct.pack('<iHi', target, co.flags | SYNC_ON_UPDATE, body))


def joints(nif: NifFile, bodies: dict) -> None:
    """Write each FNV body's constraints between converted bodies and list them on it (its record's tail).

    `bodies` is {id(FNV body): (FNV body, FO4 block, scale)}.
    See: docs/fork/fo4_pipeline.md#ragdolls
    """
    for fnv, index, _ in bodies.values():
        refs = []
        for c in fnv.constraints:
            packed = _joint(c, bodies)
            if packed:
                nif.blocks.append((type(c).__name__, packed))
                refs.append(len(nif.blocks) - 1)
        if refs:
            kind, raw = nif.blocks[index]
            nif.blocks[index] = (kind, raw[:-6] + struct.pack(f'<I{len(refs)}iH', len(refs), *refs, 0))


def _joint(c, bodies: dict) -> 'bytes | None':
    """FNV constraint `c` in FO4's pre-Elric layout (twist/axis vectors before each pivot); None when it is
    not a ragdoll or limited hinge or joins a body not converted."""
    ends = [bodies.get(id(e() if callable(e) else e)) for e in c.entities]
    kind = type(c).__name__
    if None in ends or kind not in JOINT_FIELDS:
        return None
    desc = getattr(c, JOINT_FIELDS[kind][0])
    side = [(ends[0], JOINT_FIELDS[kind][1]), (ends[1], JOINT_FIELDS[kind][2])]
    out = struct.pack('<I2iI', 2, ends[0][1], ends[1][1], c.priority)
    for (fnv, _, scale), names in side:
        *axes, pivot = [getattr(desc, n) for n in names]
        out += b''.join(struct.pack('<4f', *_moved(fnv, v, False, scale)) for v in axes)
        out += struct.pack('<4f', *_moved(fnv, pivot, True, scale))
    limits = [getattr(desc, n) * (FRICTION_SCALE if n == 'max_friction' else 1.0) for n in JOINT_FIELDS[kind][3]]
    return out + struct.pack(f'<{len(limits)}fB', *limits, 0)


def _moved(body, v, pivot: bool, scale: float) -> tuple:
    """A constraint vector of `body` in FO4 units: a pivot scaled; both moved by a baked bhkRigidBodyT's transform
    (a mesh body's translation is already in FO4 units: _mesh_soup)."""
    x = np.array([v.x, v.y, v.z]) * (SCALE * scale if pivot else 1.0)
    if _baked(body):
        q = body.rotation
        unit = scale if is_mesh(body.shape) else SCALE * scale
        x = _rotation(q.x, q.y, q.z, q.w) @ x + (np.array(_vec(body.translation, 3, unit)) if pivot else 0)
    return (*map(float, x), 0.0)


def character_controller(nif: NifFile, center: tuple, half: tuple, node_flags: int) -> None:
    """A creature skeleton's CharacterController and CharacterBumper: root children each holding a phantom capsule
    (bhkSimpleShapePhantom, layer CHARCONTROLLER) standing on the floor through `center`, its radius the bound's
    smaller half width (`half`, game units) × CONTROLLER_RADII; Elric makes them vanilla's bhkPhysicsSystem.

    See: docs/fork/fo4_spikes.md#own-rigs
    """
    filt = struct.pack('<BBH', CHARCONTROLLER, 0, 0)
    blocks = _Blocks(nif, animated=True)
    for name, grow in CONTROLLER_RADII:
        nif.blocks.append(('NiNode', {'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': node_flags,
                                      'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0,
                                      'collision': NONE, 'children': []}))
        node = len(nif.blocks) - 1
        nif.blocks[0][1]['children'].append(node)
        shape = blocks._bhkCapsuleShape(_standing_capsule(center, half, grow))
        nif.blocks[node][1]['collision'] = _phantom(blocks, node, shape, filt)


def _standing_capsule(center: tuple, half: tuple, grow: float) -> SimpleNamespace:
    """An FNV-unit bhkCapsuleShape standing on the floor through `center` (game units), radius `grow` × the smaller
    horizontal half size, top at the bound's top."""
    unit = GAME_PER_HAVOK * SCALE
    point = lambda z: SimpleNamespace(x=center[0] / unit, y=center[1] / unit, z=z / unit)
    r = min(half[0], half[1]) * grow
    top = max(center[2] + half[2] - r, r + 1)
    return SimpleNamespace(material=SimpleNamespace(material=0), radius=r / unit, radius_1=r / unit,
                           radius_2=r / unit, first_point=point(r), second_point=point(top))


def _rotation(x: float, y: float, z: float, w: float) -> np.ndarray:
    """The rotation matrix (rows) of quaternion (x, y, z, w), as transformed()'s."""
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
