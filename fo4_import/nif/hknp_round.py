"""Spheres and capsules as Elric writes them: an hknpSphereShape or hknpCapsuleShape and its Mass at density 1.

Neither gets a mass-properties object; a dynamic body's motion takes the
Mass. A capsule is Havok's: a box around its segment one padding out, the
rest of its radius the convex radius. A capsule's corner i is end a (bit 1)
or b, out along e1 (bit 2) and e2 (bit 4); CAPSULE_LOOPS are its faces.

See: docs/fork/fo4_hknp_writer.md#round
"""

import math
import struct

import numpy as np

from fo4_import.havok.packfile import classes
from fo4_import.nif.hknp_convex import DISPATCH_CONVEX, INERTIA_SCALE, VERTEX_TAG, Mass, principal, tail

#: Shape flags Elric writes on a sphere and on a capsule.
SPHERE_FLAGS, CAPSULE_FLAGS = 273, 451
#: The share Elric takes off a capsule's radius, and Havok again off the rest as the core box's padding.
SHRINK = np.float32(0.01)
#: The angle byte on every capsule face.
CAPSULE_ANGLE = 4
#: A capsule's six faces as corner loops, and each normal's (axis, sign) over the axes u, e1, e2.
CAPSULE_LOOPS = ([7, 6, 2, 3], [3, 2, 0, 1], [7, 5, 4, 6], [1, 0, 4, 5], [1, 5, 7, 3], [2, 6, 4, 0])
CAPSULE_NORMALS = ((1, 1), (2, -1), (2, 1), (1, -1), (0, 1), (0, -1))
#: A capsule's spare plane slot: no direction, an offset no point passes.
SPARE_PLANE = struct.pack('<4f', 0.0, 0.0, 0.0, -3.402820018375656e+38)


# ---------------------------------------------------------------------------
# Spheres
# ---------------------------------------------------------------------------

def sphere(name: str, center, radius: float, material: int) -> tuple:
    """([the shape], Mass) of a sphere of `radius` at `center` (Havok units), material CRC `material`."""
    volume = 4 / 3 * math.pi * radius ** 3
    moment = INERTIA_SCALE * 2 / 5 * radius * radius * volume
    data = struct.pack('<3fI', *center, VERTEX_TAG) * 4
    shape = {'flags': SPHERE_FLAGS, 'numShapeKeyBits': 0, 'dispatchType': DISPATCH_CONVEX, 'convexRadius': radius,
             'userData': material, 'properties': None, 'vertices': (4, _vertices_at('hknpSphereShape')),
             '__tail__': data}
    return [{'#': name, 'class': 'hknpSphereShape', 'fields': shape}], \
        Mass(volume, np.array(center, float), np.full(3, moment), (0.0, 0.0, 0.0, 1.0))


def _vertices_at(cls: str) -> int:
    """Class `cls`'s vertex array offset: its vertices follow the class."""
    cl = classes()
    return cl.size(cls) - next(m.offset for m in cl.members(cls) if m.name == 'vertices')


# ---------------------------------------------------------------------------
# Capsules
# ---------------------------------------------------------------------------

def perpendicular(v: np.ndarray) -> np.ndarray:
    """Havok's perpendicular of `v`: its smallest component (the later on a tie) zeroed, the other two swapped
    and the later one negated."""
    low = 1 if abs(v[1]) <= abs(v[0]) else 0
    low = 2 if abs(v[2]) <= abs(v[low]) else low
    first, second = (k for k in range(3) if k != low)
    out = np.zeros(3, np.float32)
    out[first], out[second] = v[second], -v[first]
    return out


def capsule_radii(radius: float) -> tuple:
    """(convex radius, core padding) of a capsule of `radius`, float32."""
    shrunk = np.float32(radius) - np.float32(radius) * SHRINK
    pad = shrunk * SHRINK
    return float(shrunk - pad), float(pad)


def capsule_mass(a: np.ndarray, b: np.ndarray, radius: float) -> Mass:
    """The Mass of a solid capsule of `radius` over segment a–b, inertia scaled by INERTIA_SCALE."""
    length = float(np.linalg.norm(a - b))
    cylinder, ball = math.pi * radius * radius * length, 4 / 3 * math.pi * radius ** 3
    axial = cylinder * radius * radius / 2 + ball * 2 / 5 * radius * radius
    across = cylinder * (length * length / 12 + radius * radius / 4) \
        + ball * (2 / 5 * radius * radius + length * length / 4 + 3 / 8 * length * radius)
    u = (a - b) / length
    tensor = across * np.eye(3) + (axial - across) * np.outer(u, u)
    inertia, frame = principal(tensor * INERTIA_SCALE)
    return Mass(cylinder + ball, (a + b) / 2, inertia, frame)


def _core(a: np.ndarray, b: np.ndarray, pad: float) -> tuple:
    """(8 corners, face planes (n, d)) of the box one `pad` around segment a–b, float32."""
    a, b = a.astype(np.float32), b.astype(np.float32)
    u = (a - b) / np.linalg.norm(a - b)
    e1 = perpendicular(b - a)
    e1 /= np.linalg.norm(e1)
    axes = np.array([u, e1, np.cross(e1, u)], np.float32) * np.float32(pad)
    corners = np.array([(a if i & 1 else b) + axes[0] * (1 if i & 1 else -1) + axes[1] * (1 if i & 2 else -1)
                        + axes[2] * (1 if i & 4 else -1) for i in range(8)], np.float32)
    normals = [axes[k] / np.float32(pad) * sign for k, sign in CAPSULE_NORMALS]
    planes = [(*n, -float(n @ corners[loop[0]])) for n, loop in zip(normals, CAPSULE_LOOPS)]
    return corners, np.array(planes)


def capsule(name: str, a, b, radius: float, material: int) -> tuple:
    """([the shape], Mass) of a capsule of `radius` over end points `a`, `b` (Havok units), material CRC
    `material`."""
    a, b = np.array(a, float), np.array(b, float)
    convex, pad = capsule_radii(radius)
    corners, planes = _core(a, b, pad)
    data, arrays = tail(corners, list(CAPSULE_LOOPS), planes, [CAPSULE_ANGLE] * 6, 'hknpCapsuleShape', SPARE_PLANE)
    shape = {'flags': CAPSULE_FLAGS, 'numShapeKeyBits': 0, 'dispatchType': DISPATCH_CONVEX, 'convexRadius': convex,
             'userData': material, 'properties': None, **arrays, 'a': (*a, 1.0), 'b': (*b, 1.0), '__tail__': data}
    return [{'#': name, 'class': 'hknpCapsuleShape', 'fields': shape}], capsule_mass(a, b, convex)
