"""How far points lie off a triangle surface, within a limit, in bounded memory on any mesh: groups of nearby
points are tested only against the triangles whose box, grown by the limit, reaches the group, a block of
GAP_PAIRS point-triangle pairs at a time. A triangle counts for a point whose projection falls inside it (with
the edge tolerance EDGE_SLACK).

See: docs/fork/fo4_pipeline.md#overlay-layers
"""

from typing import NamedTuple

import numpy as np

#: Points tested together: each group is split from its parent across its widest axis.
GAP_GROUP = 256
#: Point-triangle pairs tested at once; each temporary is GAP_PAIRS x 3 float64 (6 MB).
GAP_PAIRS = 1 << 18
#: How far outside an edge a projection may fall and still count, over the triangle's doubled area.
EDGE_SLACK = 1e-6
#: Triangles whose doubled area is at most this are skipped (no normal).
FLAT = 1e-9
#: Game units added to each triangle's reach for rounding; a looser reach only costs time.
MARGIN = 1e-3


class Surface(NamedTuple):
    """Triangles prepared for gaps(): corners, unit normals, and the box each can count a point in."""
    a: np.ndarray
    b: np.ndarray
    c: np.ndarray
    normal: np.ndarray
    low: np.ndarray
    high: np.ndarray
    limit: float


def surface(tris: np.ndarray, limit: float) -> Surface:
    """Triangles `tris` (n, 3, 3) prepared for gaps() within `limit`; flat ones dropped.

    A projection counts while each barycentric coordinate is at least -EDGE_SLACK / doubled area, so inside the
    triangle scaled by 1 + 3 * that about its centre; a point within `limit` of it lies in that box grown by
    `limit`.
    """
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    normal = np.cross(b - a, c - a)
    size = np.linalg.norm(normal, axis=1)
    keep = size > FLAT
    a, b, c, normal, size = a[keep], b[keep], c[keep], normal[keep] / size[keep, None], size[keep]
    centre = (a + b + c) / 3
    grow = 1 + 3 * EDGE_SLACK / size[:, None]
    corners = [centre + (v - centre) * grow for v in (a, b, c)]
    reach = limit + MARGIN
    low = np.minimum(np.minimum(corners[0], corners[1]), corners[2]) - reach
    high = np.maximum(np.maximum(corners[0], corners[1]), corners[2]) + reach
    return Surface(a, b, c, normal, low, high, limit)


def gaps(points: np.ndarray, tris: Surface) -> np.ndarray:
    """Per point, its distance to the nearest triangle of `tris` its projection falls inside, if at most the
    surface's limit; inf otherwise."""
    out = np.full(len(points), np.inf)
    if not len(points) or not len(tris.a):
        return out
    for group in point_groups(points, np.arange(len(points))):
        p = points[group]
        near = np.flatnonzero(np.all(tris.low <= p.max(axis=0), axis=1) & np.all(tris.high >= p.min(axis=0), axis=1))
        step = max(1, GAP_PAIRS // len(group))
        for start in range(0, len(near), step):
            t = near[start:start + step]
            out[group] = np.minimum(out[group], pair_gaps(p, tris.a[t], tris.b[t], tris.c[t], tris.normal[t]))
    return np.where(out <= tris.limit, out, np.inf)


def point_groups(points: np.ndarray, index: np.ndarray) -> list:
    """`index` (into `points`) split in halves across the widest axis until each holds at most GAP_GROUP."""
    if len(index) <= GAP_GROUP:
        return [index]
    p = points[index]
    order = index[np.argsort(p[:, np.argmax(p.max(axis=0) - p.min(axis=0))], kind='stable')]
    half = len(order) // 2
    return point_groups(points, order[:half]) + point_groups(points, order[half:])


def pair_gaps(points: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Per point, its distance to the nearest of triangles (a, b, c) with unit `normal` its projection falls
    inside; inf for none."""
    p = points[:, None, :]
    depth = np.einsum('pij,ij->pi', p - a, normal)
    q = p - depth[..., None] * normal
    inside = np.ones(depth.shape, bool)
    for u, v in ((a, b), (b, c), (c, a)):
        inside &= np.einsum('pij,ij->pi', np.cross(v - u, q - u), normal) >= -EDGE_SLACK
    return np.where(inside, np.abs(depth), np.inf).min(axis=1)
