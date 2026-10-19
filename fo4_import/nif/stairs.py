"""Steps in FNV mesh collision marked with FO4 stairs materials, as vanilla marks its stairs.

FO4's character sticks on a plain 16-unit step and climbs taller risers on
stairs materials (its stairs mode); FNV climbs them all and marks only its
staircases. Treads are near-horizontal faces. Two treads form a step when
one lies within REACH beyond an edge of the other, more than RISER_MIN
(what FO4 climbs reliably) and at most RISER_MAX below it: FNV builds
steps as stacked blocks or floating plates, often with no riser face
between them, so treads alone decide. Both treads take the stairs variant
of their material (collision.STAIRS), the default stairs material where
FNV's has none, and an upright riser is added from the upper tread's edge
down to the lower: FO4's character snags on a floating plate's bare edge
but steps up a riser, as vanilla's plain stairs are built. The ground is
not in the mesh, so a step up from it is an upright face rising from the
mesh's lowest point to a tread (the saloon porch's skirt); any upright face
under a tread would take every board's front edge. Faces are judged in the
collision node's own frame.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import numpy as np

#: Tallest step (game units) marked, within TOUCH: vanilla's tallest stairs riser is 22; FNV kits use 24.
RISER_MAX = 24.0
#: Steps no taller than this are left plain (curbs, lips): FO4's player climbs them, but not 16 reliably.
RISER_MIN = 8.0
#: How far (game units) beyond a tread's edge the next tread may start: about the player's width.
REACH = 24.0
#: |normal z| at least this is a tread, at most VERTICAL an upright face.
FLAT, VERTICAL = 0.98, 0.17
#: Game units a point may sit off a face and still touch it.
TOUCH = 1.0


def _faces(tris: list, unit: float) -> tuple:
    """(corners (n, 3, 3) in game units, |unit normal z| per face)."""
    corners = np.array(tris, dtype=float).reshape(-1, 3, 3) * unit
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    nz = np.divide(np.abs(normals[:, 2]), lengths, out=np.zeros(len(corners)), where=lengths > 1e-9)
    return corners, nz


def _covers(tris: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Which of `tris` (n, 3, 3) cover XY `point`, within TOUCH of their edges."""
    a, b, c = tris[:, 0, :2], tris[:, 1, :2], tris[:, 2, :2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    sign = np.where(area >= 0, 1.0, -1.0)
    ok = np.abs(area) > 1e-9
    for p, q in ((a, b), (b, c), (c, a)):
        edge = q - p
        cross = sign * (edge[:, 0] * (point[1] - p[:, 1]) - edge[:, 1] * (point[0] - p[:, 0]))
        ok &= cross >= -TOUCH * np.linalg.norm(edge, axis=1)
    return ok


def _beyond(flat: np.ndarray, tops: np.ndarray, top: float, mid: np.ndarray, out: np.ndarray) -> np.ndarray:
    """Mask of the treads one step below `top` beyond an edge (`mid`, outward `out`); none when a tread at `top`
    continues past it or the drop is one FO4 climbs anyway."""
    for reach in (2 * TOUCH, REACH / 2, REACH):
        hit = _covers(flat, mid + out * reach)
        if (hit & (np.abs(tops - top) <= TOUCH)).any():
            break
        lower = hit & (tops < top - TOUCH) & (tops >= top - RISER_MAX - TOUCH)
        if lower.any():
            level = tops[lower].max()
            return lower & (tops >= level - TOUCH) if top - level > RISER_MIN else lower & False
    return np.zeros(len(tops), dtype=bool)


def _edge_steps(corners: np.ndarray, treads: np.ndarray) -> tuple:
    """(treads in a step, risers): each riser is (upper tread, edge start, edge end, lower level, outward)."""
    flat, tops = corners[treads], corners[treads, :, 2].mean(axis=1)
    marked, risers, seen = set(), [], set()
    for k, i in enumerate(treads):
        tri = corners[i]
        centre = tri[:, :2].mean(axis=0)
        for p, q in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            mid, along = (p[:2] + q[:2]) / 2, q[:2] - p[:2]
            out = np.array([along[1], -along[0]]) / (np.linalg.norm(along) or 1.0)
            out = out if np.dot(out, mid - centre) > 0 else -out
            below = _beyond(flat, tops, tops[k], mid, out)
            if not below.any():
                continue
            marked.update([int(i), *(int(j) for j in treads[below])])
            key = (round(tops[k]), *sorted((tuple(np.round(p[:2])), tuple(np.round(q[:2])))))
            if key not in seen:
                seen.add(key)
                risers.append((int(i), p, q, float(tops[below].max()), out))
    return marked, risers


def _ground_steps(corners: np.ndarray, nz: np.ndarray, treads: np.ndarray) -> set:
    """Upright faces rising from the mesh's lowest point to a tread more than RISER_MIN and at most RISER_MAX
    above it (a step up from the ground the mesh stands on), with that tread."""
    base, tops = corners[:, :, 2].min(), corners[treads, :, 2].mean(axis=1)
    marked = set()
    for i in np.nonzero(nz <= VERTICAL)[0]:
        high, low = corners[i, :, 2].max(), corners[i, :, 2].min()
        if low > base + 2 * TOUCH or not RISER_MIN < high - low <= RISER_MAX + TOUCH:
            continue
        edge = corners[i][corners[i, :, 2] >= high - TOUCH].mean(axis=0)
        on = _covers(corners[treads], edge[:2]) & (np.abs(tops - high) <= TOUCH)
        if on.any():
            marked.update([int(i), *(int(j) for j in treads[on])])
    return marked


def _riser_faces(p: np.ndarray, q: np.ndarray, low: float, out: np.ndarray) -> list:
    """Two triangles closing a step from edge p-q down to height `low`, facing `out`."""
    top_p, top_q = p.copy(), q.copy()
    low_p, low_q = np.array([p[0], p[1], low]), np.array([q[0], q[1], low])
    first, second = np.array([top_p, low_p, low_q]), np.array([top_p, low_q, top_q])
    normal = np.cross(first[1] - first[0], first[2] - first[0])[:2]
    if np.dot(normal, out) < 0:
        first, second = first[[0, 2, 1]], second[[0, 2, 1]]
    return [first, second]


def stairs(tris: list, materials: list, unit: float, stairs_of) -> tuple:
    """(tris, materials) with each step's treads on `stairs_of(material)` and its missing riser added.

    `tris` are in units of `unit` game units. FNV's floating step plates
    leave no upright face between treads, and FO4's character snags on the
    bare edge; the riser runs from the upper tread's edge down to the lower.
    """
    if not tris:
        return tris, materials
    corners, nz = _faces(tris, unit)
    treads = np.nonzero(nz >= FLAT)[0]
    marked, risers = _edge_steps(corners, treads)
    marked |= _ground_steps(corners, nz, treads)
    out_mats = [stairs_of(m) if i in marked else m for i, m in enumerate(materials)]
    added = [(tuple(tuple(c / unit) for c in face), stairs_of(materials[i]))
             for i, p, q, low, out in risers for face in _riser_faces(p, q, low, out)]
    return list(tris) + [t for t, _ in added], out_mats + [m for _, m in added]
