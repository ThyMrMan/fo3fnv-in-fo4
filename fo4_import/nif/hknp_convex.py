"""Convex shapes as Elric writes them: an hknpConvexPolytopeShape and its mass properties, as packfile objects.

A shape is the hull of our points as Havok simplifies it (nif/hknp_hull.py), its face planes, one
counter-clockwise index loop per face, and the mass properties of the solid with its faces pushed out by
the convex radius, at density 1.

See: docs/fork/fo4_hknp_writer.md#convex
"""

import math
import struct
from dataclasses import dataclass

import numpy as np
from scipy.spatial import ConvexHull, HalfspaceIntersection

from fo4_import.havok.packfile import classes
from fo4_import.nif import hknp_hull

#: The shape's flags and dispatch type on every Elric polytope.
SHAPE_FLAGS, DISPATCH_CONVEX = 323, 1
#: Most corners a face keeps, and the shape flag Elric clears when a face had to drop some.
MAX_CORNERS, SMALL_FACES = 16, 0x40
#: A vertex's fourth word: this tag or'd with its index.
VERTEX_TAG = 0x3F000000
#: The hkRefCountedProperties key of a shape's mass properties.
MASS_PROPERTIES_KEY = 0xF100
#: Elric's inertia is this many times the physical tensor.
INERTIA_SCALE = 1.5
#: A packed quaternion component: QUAT_ZERO + floor(q * QUAT_SCALE), as u16.
QUAT_ZERO, QUAT_SCALE = 0x8000, 30000
#: Plane intersections closer than this (Havok units) are one corner (where more than three planes meet).
SAME_POINT = 1e-6
#: Havok's Jacobi stops when the off-diagonal terms fall below this share of the matrix, or after JACOBI_STEPS.
JACOBI_EPSILON, JACOBI_STEPS = np.float32(2.0 ** -23), 128
CLASS = 'hknpConvexPolytopeShape'


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class Mass:
    """A shape's mass properties at density 1: volume, centre of mass, principal inertia, its frame (x, y, z, w)."""
    volume: float
    com: np.ndarray
    inertia: np.ndarray
    frame: tuple


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def box_planes(half) -> np.ndarray:
    """A box's six face planes (n, d) from its half extents."""
    return np.array([[*(sign * axis), -h] for axis, h in zip(np.eye(3), half) for sign in (1, -1)])


def box_corners(half) -> np.ndarray:
    """A box's eight corners from its half extents."""
    return np.array([(x, y, z) for x in (-half[0], half[0]) for y in (-half[1], half[1]) for z in (-half[2], half[2])])


def faces(planes: np.ndarray, inside: np.ndarray) -> tuple:
    """(vertices, [index loop per face], planes (n, d) per face) of the solid inside `planes` around point
    `inside`: its corners are where the planes meet, each on the planes that made it; a plane touching it in
    under three corners is no face; loops counter-clockwise seen from outside."""
    meet = HalfspaceIntersection(planes, inside)
    verts, owners = [], []
    for point, made in zip(meet.intersections, meet.dual_facets):
        same = [k for k, kept in enumerate(verts) if np.abs(point - kept).max() <= SAME_POINT]
        if same:
            owners[same[0]] |= set(made)
        else:
            verts.append(point)
            owners.append(set(made))
    verts = np.array(verts)
    loops = [_loop(verts, [k for k, own in enumerate(owners) if i in own], plane) for i, plane in enumerate(planes)]
    keep = [i for i, loop in enumerate(loops) if len(loop) >= 3]
    return verts, [loops[i] for i in keep], planes[keep]


def _loop(verts: np.ndarray, on: list, plane: np.ndarray) -> list:
    """Indices `on` (corners of `plane`), counter-clockwise about its outward normal."""
    if len(on) < 3:
        return on
    on = np.array(on)
    centre = verts[on].mean(0)
    u = verts[on[0]] - centre
    v = np.cross(plane[:3], u)
    angles = np.arctan2((verts[on] - centre) @ v, (verts[on] - centre) @ u)
    return [int(i) for i in on[np.argsort(angles)]]


def _closest(point: np.ndarray, polygon: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """The point of convex `polygon` (counter-clockwise about `normal`) closest to `point`."""
    foot = point - ((point - polygon[0]) @ normal) * normal
    ends = np.roll(polygon, -1, axis=0)
    if all(np.cross(ends - polygon, foot - polygon) @ normal >= 0):
        return foot
    edges = ends - polygon
    t = np.clip(np.einsum('ij,ij->i', point - polygon, edges) / np.einsum('ij,ij->i', edges, edges), 0, 1)
    nearest = polygon + t[:, None] * edges
    return nearest[np.argmin(((nearest - point) ** 2).sum(1))]


def _elevation(verts: np.ndarray, loops: list, face: int, normal: np.ndarray) -> float:
    """The smallest sine (float32, as Havok) over edges with one end on `face` of its far end's rise to the face."""
    on, polygon, low = set(loops[face]), verts[loops[face]], 1.0
    for other, loop in enumerate(loops):
        for a, b in zip(loop[-1:] + loop[:-1], loop) if other != face else ():
            if (a in on) != (b in on):
                rise = _closest(verts[a if b in on else b], polygon, normal) - verts[a if b in on else b]
                length = math.sqrt(rise @ rise)
                low = min(low, float(np.float32(rise @ normal / length))) if length > 0 else low
    return low


def trim(verts: np.ndarray, loop: list) -> list:
    """`loop` cut to MAX_CORNERS by dropping, one at a time, the corner spanning the least area with its
    neighbours (the first on a tie)."""
    loop = list(loop)
    while len(loop) > MAX_CORNERS:
        points = verts[loop]
        spans = np.cross(np.roll(points, 1, axis=0) - points, np.roll(points, -1, axis=0) - points)
        del loop[int(np.argmin((spans ** 2).sum(1)))]
    return loop


def angle_bytes(verts: np.ndarray, loops: list, planes: np.ndarray) -> list:
    """Each face's min half angle byte as Havok computes it: asin of its _elevation, 0-pi as 0-255, rounded."""
    out = []
    for face in range(len(loops)):
        angle = math.asin(max(-1.0, min(1.0, _elevation(verts, loops, face, planes[face, :3]))))
        out.append(min(255, max(0, int(angle * 255 / math.pi + 0.5))))
    return out


# ---------------------------------------------------------------------------
# Mass properties
# ---------------------------------------------------------------------------

def mass_properties(verts: np.ndarray, planes: np.ndarray, radius: float) -> Mass:
    """The mass properties of the hull of `verts` (faces `planes`) grown by `radius`, sharp corners kept."""
    grown = planes.copy()
    grown[:, 3] -= radius
    points = HalfspaceIntersection(grown, verts.mean(0)).intersections
    volume, com, tensor = _solid(points)
    inertia, frame = principal(tensor * INERTIA_SCALE)
    return Mass(volume, com, inertia, frame)


def _solid(points: np.ndarray) -> tuple:
    """(volume, centroid, inertia tensor about the centroid) of the convex hull of `points`, density 1."""
    hull = ConvexHull(points)
    origin = points.mean(0)
    canonical = (np.ones((3, 3)) + np.eye(3)) / 120.0
    volume, moment, second = 0.0, np.zeros(3), np.zeros((3, 3))
    for simplex in hull.simplices:
        tet = points[simplex] - origin
        det = abs(np.linalg.det(tet))
        volume += det / 6
        moment += det / 24 * tet.sum(0)
        second += det * tet.T @ canonical @ tet
    centroid = moment / volume
    second -= volume * np.outer(centroid, centroid)
    return volume, centroid + origin, np.trace(second) * np.eye(3) - second


def _rotation(m: np.ndarray, p: int, q: int) -> np.ndarray:
    """The Jacobi rotation zeroing `m[p, q]` (Havok's tangent form, float32)."""
    c, s, one = np.float32(1), np.float32(0), np.float32(1)
    if m[p, q] != 0:
        theta = (m[q, q] - m[p, p]) / (np.float32(2) * m[p, q])
        root = np.sqrt(theta * theta + one)
        t = one / (theta + root) if theta >= 0 else one / (theta - root)
        c = one / np.sqrt(t * t + one)
        s = t * c
    j = np.eye(3, dtype=np.float32)
    j[p, p] = j[q, q] = c
    j[p, q], j[q, p] = s, -s
    return j


def principal(tensor: np.ndarray) -> tuple:
    """(principal moments in diagonal order, frame quaternion) of `tensor` by Havok's float32 Jacobi: rotate away
    the largest off-diagonal term until all fall under JACOBI_EPSILON of the matrix.

    See: docs/fork/fo4_hknp_writer.md#elric-code
    """
    m, axes = tensor.astype(np.float32), np.eye(3, dtype=np.float32)
    limit = (m ** 2).sum() * JACOBI_EPSILON * JACOBI_EPSILON
    for _ in range(JACOBI_STEPS):
        if not np.float32(2) * (m[0, 1] ** 2 + m[0, 2] ** 2 + m[1, 2] ** 2) > limit:
            break
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda pq: abs(m[pq]))
        j = _rotation(m, p, q)
        m, axes = j.T @ m @ j, axes @ j
    return np.diag(m).astype(float), quaternion(axes.astype(float))


def quaternion(m: np.ndarray) -> tuple:
    """Rotation matrix `m` (columns the rotated axes) as (x, y, z, w), w not negative."""
    w = math.sqrt(max(0.0, 1.0 + m[0, 0] + m[1, 1] + m[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1.0 + m[0, 0] - m[1, 1] - m[2, 2])) / 2, m[2, 1] - m[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1.0 - m[0, 0] + m[1, 1] - m[2, 2])) / 2, m[0, 2] - m[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1.0 - m[0, 0] - m[1, 1] + m[2, 2])) / 2, m[1, 0] - m[0, 1])
    return float(x), float(y), float(z), float(w)


def pack_vector(v) -> list:
    """Three int16 over 2^e, e from the largest component, and (e + 96) << 7 as the fourth."""
    largest = max(abs(float(c)) for c in v)
    exponent = math.frexp(largest)[1] if largest > 0 else -96
    scale = 2.0 ** -exponent * 32768
    return [max(-32768, min(32767, round(float(c) * scale))) for c in v] + [(exponent + 96) << 7]


def pack_quaternion(q) -> list:
    """Each component as u16 QUAT_ZERO + floor(q * QUAT_SCALE), read back as int16."""
    return [(u := (QUAT_ZERO + math.floor(c * QUAT_SCALE)) & 0xFFFF) - (0x10000 if u >= 0x8000 else 0) for c in q]


# ---------------------------------------------------------------------------
# Packfile objects
# ---------------------------------------------------------------------------

def tail(verts: np.ndarray, loops: list, planes: np.ndarray, angles: list, cls: str = CLASS,
         spare: bytes = bytes(16)) -> tuple:
    """(polytope class `cls`'s relative-array bytes past its class, {member: (count, offset)}); plane slots
    past the last face hold `spare`."""
    nv, nf = -(-len(verts) // 4) * 4, len(loops)
    np_ = -(-nf // 4) * 4
    out = bytearray()
    for i in range(nv):
        src = min(i, len(verts) - 1)
        out += struct.pack('<3fI', *verts[src], VERTEX_TAG | src)
    out += b''.join(struct.pack('<4f', *p) for p in planes) + spare * (np_ - nf)
    first, index = 0, bytearray()
    for loop, angle in zip(loops, angles):
        out += struct.pack('<HBB', first, len(loop), angle)
        index += bytes(loop)
        first += len(loop)
    out += bytes(4 * (np_ - nf)) + index
    out += bytes(-len(out) % 16)
    return bytes(out), _relarrays(nv, np_, nf, first, cls)


def _relarrays(nv: int, np_: int, nf: int, ni: int, cls: str) -> dict:
    """The four relative arrays' (count, offset from the member) of class `cls` for those counts."""
    cl = classes()
    at = {m.name: m.offset for m in cl.members(cls)}
    verts = cl.size(cls)
    planes = verts + 16 * nv
    faces_at = planes + 16 * np_
    indices = faces_at + 4 * np_
    return {'vertices': (nv, verts - at['vertices']), 'planes': (np_, planes - at['planes']),
            'faces': (nf, faces_at - at['faces']), 'indices': (ni, indices - at['indices'])}


def corners(points: np.ndarray) -> tuple:
    """(vertices, loops, planes) of the polytope Havok builds from `points`: the simplified hull
    (`hknp_hull.simplify`), cut to MAX_VERTICES, its corners on the grid unless two would meet there."""
    verts, loops, planes = faces(*hknp_hull.simplify(points))
    if len(verts) > hknp_hull.MAX_VERTICES:
        verts, loops, planes = faces(*hknp_hull.capped(verts))
    on = hknp_hull.grid(verts)
    return (on if len(np.unique(on, axis=0)) == len(on) else verts), loops, planes


def polytope(name: str, points: np.ndarray, radius: float, material: int) -> tuple:
    """([shape, its properties, its mass properties] as packfile objects named from `name`, Mass) for the hull
    of `points` (Havok units) as Havok simplifies it, convex radius `radius`, material CRC `material`."""
    verts, loops, planes = corners(points)
    mass = mass_properties(verts, planes, radius)
    kept = [trim(verts, loop) for loop in loops]
    data, arrays = tail(verts, kept, planes, angle_bytes(verts, kept, planes))
    flags = SHAPE_FLAGS & ~SMALL_FACES if kept != loops else SHAPE_FLAGS
    shape = {'flags': flags, 'numShapeKeyBits': 0, 'dispatchType': DISPATCH_CONVEX, 'convexRadius': radius,
             'userData': material, 'properties': f'{name}p', **arrays, '__tail__': data}
    props = {'entries': [{'object': f'{name}m', 'key': MASS_PROPERTIES_KEY, 'flags': 0}]}
    compressed = {'centerOfMass': pack_vector(mass.com), 'inertia': pack_vector(mass.inertia),
                  'majorAxisSpace': pack_quaternion(mass.frame), 'mass': mass.volume, 'volume': mass.volume}
    return [{'#': name, 'class': CLASS, 'fields': shape},
            {'#': f'{name}p', 'class': 'hkRefCountedProperties', 'fields': props},
            {'#': f'{name}m', 'class': 'hknpShapeMassProperties',
             'fields': {'compressedMassProperties': compressed}}], mass
