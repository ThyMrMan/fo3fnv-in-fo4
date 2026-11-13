"""Havok's convex hull simplification as Elric runs it before building a polytope, re-implemented from its
reading of ElricInterop.dll: the integer grid, the degenerate-hull skip, the quadric vertex pass and the
plane-merging pass. `simplify(points)` gives the face planes (n, d), the points they came from, and whether
Havok keeps those points' hull as it is.

See: docs/fork/fo4_hknp_writer.md#elric-code
"""

from types import SimpleNamespace

import numpy as np
from scipy.spatial import ConvexHull, QhullError

#: Elric's simplification tolerance (build config +0x00), Havok units.
TOLERANCE = 0.01
#: Grid steps each way from an axis' centre, and the least half size of an axis.
GRID_STEPS, GRID_LEAST_HALF = np.float32(8191), np.float32(1e-5)
#: A hull triangle whose squared cross product is under this is degenerate (both passes are skipped).
DEGENERATE = np.float32(1e-7)
#: Vertex pass: planes this close on their normals are one plane in a vertex's quadric.
QUADRIC_SAME = float(np.sqrt(np.float32(2.0 ** -23)))
#: Hull triangles whose plane equations agree this closely lie on one face.
SAME_FACE = 1e-5
#: Plane pass: normals whose dot product is under this never merge; NEVER is such a pair's score.
LEAST_DOT, NEVER = 2.0 ** -23, 2.0 ** 64
#: Sphericity is SPHERE * V^(2/3) / A.
SPHERE = (36 * np.pi) ** (1 / 3)
#: Under this many planes after the plane pass, Havok keeps the hull it had instead of rebuilding from them.
KEPT_UNDER = 4
#: Most vertices a polytope keeps, and the tolerance of the pass that enforces it.
MAX_VERTICES, CAP_TOLERANCE = 252, float(np.float32(2.0 ** -23))


# ---------------------------------------------------------------------------
# Grid and checks
# ---------------------------------------------------------------------------

def _steps(points: np.ndarray) -> tuple:
    """(grid steps, axis centres, axis half sizes) of `points` on Havok's hull grid: per axis, its box's centre
    and half size (at least GRID_LEAST_HALF) split into GRID_STEPS each way, rounded half away from zero."""
    p = np.asarray(points, np.float32)
    low = p.min(0)
    half = np.maximum(p.max(0) - low, GRID_LEAST_HALF * 2) * np.float32(0.5)
    centre = low + half
    x = (p - centre) * (GRID_STEPS / half)
    return np.trunc(np.where(x < 0, x - np.float32(0.5), x + np.float32(0.5))), centre, half


def grid(points: np.ndarray) -> np.ndarray:
    """`points` snapped to Havok's hull grid, read back in float32."""
    steps, centre, half = _steps(points)
    return (steps * (half / GRID_STEPS) + centre).astype(np.float32).astype(float)


def planar(points: np.ndarray) -> bool:
    """Whether `points` lie in one plane on Havok's hull grid (exact integer test): its hull is 2-D.

    See: docs/fork/fo4_hknp_writer.md#flat
    """
    rel = _steps(points)[0].astype(np.int64)
    rel = rel - rel[0]
    edge = next((r for r in rel if r.any()), np.zeros(3, np.int64))
    normal = next((n for n in np.cross(edge, rel) if n.any()), None)
    return normal is None or not (rel @ normal).any()


def convex_hull(points: np.ndarray):
    """The hull of `points`; for a hull too thin for Qhull's float test, its triangles found on Havok's integer
    grid (as Havok builds it) with their planes and measures taken from `points`.

    See: docs/fork/fo4_hknp_writer.md#flat
    """
    try:
        return ConvexHull(points)
    except QhullError:
        steps = ConvexHull(_steps(points)[0])
    points = np.asarray(points, float)
    a, b, c = (points[steps.simplices[:, k]] for k in range(3))
    normals = np.cross(b - a, c - a)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    normals *= np.where(np.einsum('ij,ij->i', normals, points.mean(0) - a) > 0, -1, 1)[:, None]
    equations = np.column_stack([normals, -np.einsum('ij,ij->i', normals, a)])
    area = float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2)
    volume = float(abs(np.einsum('ij,ij->i', np.cross(b - a, c - a), a - points.mean(0))).sum() / 6)
    return SimpleNamespace(points=points, simplices=steps.simplices, neighbors=steps.neighbors,
                           vertices=steps.vertices, equations=equations, area=area, volume=volume)


def snap(points: np.ndarray) -> np.ndarray:
    """`points` on the grid, duplicates dropped (first kept)."""
    on = grid(points)
    return on[np.sort(np.unique(on, axis=0, return_index=True)[1])]


def degenerate(points: np.ndarray) -> bool:
    """Whether a hull triangle of `points` is degenerate as Havok tests it in float32: a squared cross product
    under DEGENERATE at either of two corners, or |u|²|v|² - (u·v)² exactly 0."""
    p = np.asarray(points, np.float32)
    a, b, c = (p[convex_hull(points).simplices[:, k]] for k in range(3))
    first = (np.cross(a - c, a - b) ** 2).sum(1, dtype=np.float32)
    second = (np.cross(b - a, b - c) ** 2).sum(1, dtype=np.float32)
    u, v = a - b, a - c
    lengths = (u * u).sum(1, dtype=np.float32) * (v * v).sum(1, dtype=np.float32)
    lagrange = lengths - (u * v).sum(1, dtype=np.float32) ** 2
    return bool(np.any(first < DEGENERATE) or np.any(second < DEGENERATE) or np.any(lagrange == 0))


def face_planes(hull: ConvexHull) -> tuple:
    """([face id per hull triangle], [plane (n, d) per face]): triangles whose equations agree within SAME_FACE
    share a face."""
    ids, planes = [], []
    for equation in hull.equations:
        same = [k for k, p in enumerate(planes) if np.abs(p - equation).max() < SAME_FACE]
        ids.append(same[0] if same else len(planes))
        if not same:
            planes.append(equation)
    return ids, np.array(planes)


def least_half(hull: ConvexHull, planes: np.ndarray) -> float:
    """Half the hull's least width across a face normal (for Havok's oriented box)."""
    pts = hull.points[hull.vertices] @ planes[:, :3].T
    return 0.5 * float((pts.max(0) - pts.min(0)).min())


# ---------------------------------------------------------------------------
# Vertex pass: quadric edge collapse
# ---------------------------------------------------------------------------

def _quadrics(hull: ConvexHull, ids: list, planes: np.ndarray) -> list:
    """Each point's quadric: the sum of p·pᵀ over the distinct face planes it touches."""
    quadrics = [np.zeros((4, 4)) for _ in hull.points]
    seen = [[] for _ in hull.points]
    for t, triangle in enumerate(hull.simplices):
        plane = planes[ids[t]]
        for v in triangle:
            if all(np.abs(s[:3] - plane[:3]).max() > QUADRIC_SAME for s in seen[v]):
                seen[v].append(plane)
                quadrics[v] += np.outer(plane, plane)
    return quadrics


def _feature_edges(hull: ConvexHull, ids: list) -> list:
    """Hull edges between triangles on different faces, as (low, high) point indices, first-seen order."""
    edges = {}
    for t, triangle in enumerate(hull.simplices):
        for k in range(3):
            if ids[hull.neighbors[t][(k + 2) % 3]] != ids[t]:
                a, b = int(triangle[k]), int(triangle[(k + 1) % 3])
                edges.setdefault((min(a, b), max(a, b)), None)
    return list(edges)


def _candidate(quadric: np.ndarray, ends: np.ndarray, planes: np.ndarray, tolerance: float) -> tuple:
    """(new point, error) for collapsing an edge with summed `quadric` and end points `ends`: the quadric's optimum
    when it inverts cleanly and lies within `tolerance` of every face plane, else the midpoint; the error in
    float32, as Havok's."""
    system = quadric.copy()
    system[3] = (0, 0, 0, 1)
    point = (ends[0] + ends[1]) / 2
    if abs(np.linalg.det(system)) > 0:
        inverse = np.linalg.inv(system)
        optimum = inverse[:3, 3] / inverse[3, 3]
        clean = np.abs(system @ inverse - np.eye(4)).max() < QUADRIC_SAME
        if clean and np.all(planes[:, :3] @ optimum + planes[:, 3] <= tolerance):
            point = optimum
    h = np.append(point, 1.0).astype(np.float32)
    return point, max(0.0, float(h @ quadric.astype(np.float32) @ h))


def collapse(points: np.ndarray, tolerance: float, cap: int = 0xFFFF) -> np.ndarray:
    """Havok's vertex pass (0x10396c40): collapse the cheapest feature edge (the larger index goes, the smaller
    moves to the new point, quadrics add) while more than `cap` points live, or while the cost is under
    tolerance² and more than 6 edges remain. Tolerance is capped at half the least half width."""
    hull = convex_hull(points)
    pos = np.array(points, dtype=float)
    ids, planes = face_planes(hull)
    tolerance = min(tolerance, 0.5 * least_half(hull, planes))
    quadrics = _quadrics(hull, ids, planes)
    edges = _feature_edges(hull, ids)
    costs = [_candidate(quadrics[a] + quadrics[b], pos[[a, b]], planes, tolerance) for a, b in edges]
    dead = set(range(len(pos))) - {v for edge in edges for v in edge}
    while edges:
        best = min(range(len(edges)), key=lambda i: costs[i][1])
        if len(pos) - len(dead) <= cap and (costs[best][1] >= tolerance ** 2 or len(edges) <= 6):
            break
        keep, gone = edges[best]
        pos[keep] = costs[best][0]
        dead.add(gone)
        quadrics[keep] = quadrics[keep] + quadrics[gone]
        edges, costs = _renamed(edges, costs, best, keep, gone)
        costs = [_candidate(quadrics[a] + quadrics[b], pos[[a, b]], planes, tolerance) if keep in (a, b) else c
                 for (a, b), c in zip(edges, costs)]
    return pos[[i for i in range(len(pos)) if i not in dead]]


def _renamed(edges: list, costs: list, best: int, keep: int, gone: int) -> tuple:
    """`edges` and `costs` without `best` (the last moved into its place), `gone` renamed `keep`, duplicates and
    loops dropped."""
    edges, costs = list(edges), list(costs)
    edges[best], costs[best] = edges[-1], costs[-1]
    edges.pop(), costs.pop()
    out_edges, out_costs = [], []
    for (a, b), cost in zip(edges, costs):
        a, b = (keep if a == gone else a), (keep if b == gone else b)
        edge = (min(a, b), max(a, b))
        if a != b and edge not in out_edges:
            out_edges.append(edge)
            out_costs.append(cost)
    return out_edges, out_costs


# ---------------------------------------------------------------------------
# Plane pass: merging adjacent faces
# ---------------------------------------------------------------------------

def _score(cost: float, planes: np.ndarray, pair: tuple, size: float) -> float:
    """Cost over the normals' cosine; NEVER past `size` or near perpendicular."""
    dot = float(planes[pair[0], :3] @ planes[pair[1], :3])
    return NEVER if cost > size or dot <= LEAST_DOT else cost / dot


def _pairs(hull: ConvexHull, ids: list, planes: np.ndarray) -> tuple:
    """([directed pair (a, b) of faces sharing a hull edge], [cost per pair]): the deepest any corner of face a
    sits below plane b, at least 0."""
    corners = {}
    for t, triangle in enumerate(hull.simplices):
        corners.setdefault(ids[t], set()).update(int(v) for v in triangle)
    pairs = {}
    for t in range(len(hull.simplices)):
        for neighbour in hull.neighbors[t]:
            if ids[neighbour] != ids[t]:
                pairs.setdefault((ids[t], ids[neighbour]), None)
    pairs = list(pairs)
    depth = [float(-(hull.points[sorted(corners[a])] @ planes[b, :3] + planes[b, 3]).min()) for a, b in pairs]
    return pairs, [max(0.0, d) for d in depth]


def _blend(planes: np.ndarray, a: int, b: int, w: float, corners: np.ndarray) -> np.ndarray:
    """w·plane a + (1-w)·plane b, normalized on its normal, its offset pulled in to the farthest corner."""
    plane = w * planes[a] + (1 - w) * planes[b]
    length = np.linalg.norm(plane[:3])
    plane = plane / length if length > 0 else plane
    plane[3] = -min(float((corners @ plane[:3]).max()), -plane[3])
    return plane


def _merged(pairs: list, costs: list, scores: list, a: int, b: int, bump: float) -> None:
    """After face b merged into a: pairs naming b name a, duplicates go (the later kept), and each pair touching
    a adds `bump` to its cost (scores are refreshed by the caller)."""
    for i in range(len(pairs) - 1, -1, -1):
        h, l = pairs[i]
        if a not in (h, l):
            if b not in (h, l):
                continue
            pairs[i] = (a, l) if h == b else (h, a)
        if max(k for k, p in enumerate(pairs) if p == pairs[i]) == i:
            costs[i] += bump
            scores[i] = None
            continue
        pairs[i], costs[i], scores[i] = pairs[-1], costs[-1], scores[-1]
        pairs.pop(), costs.pop(), scores.pop()


def merge(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Havok's plane pass (0x10398870) on the hull of `points`: merge the lowest-scoring face pair (first on a
    tie) until that score reaches min(2 × tolerance, size), size being sphericity × least half width; the
    surviving planes."""
    hull = convex_hull(points)
    ids, planes = face_planes(hull)
    corners = hull.points[hull.vertices]
    size = SPHERE * hull.volume ** (2 / 3) / hull.area * least_half(hull, planes)
    pairs, costs = _pairs(hull, ids, planes)
    scores = [_score(c, planes, p, size) for c, p in zip(costs, pairs)]
    dead = set()
    while pairs:
        best = int(np.argmin(scores))
        if scores[best] >= min(2 * tolerance, size):
            break
        a, b = pairs[best]
        back = pairs.index((b, a)) if (b, a) in pairs else None
        total = costs[best] + (costs[back] if back is not None else 0.0)
        planes[a] = _blend(planes, a, b, costs[best] / total if total else 0.0, corners)
        dead.add(b)
        bump = scores[best]
        for retired in (best, back):
            if retired is not None:
                costs[retired] = np.inf
        _merged(pairs, costs, scores, a, b, bump)
        scores = [_score(c, planes, p, size) if s is None else s for c, p, s in zip(costs, pairs, scores)]
    return planes[[p for p in range(len(planes)) if p not in dead]]


# ---------------------------------------------------------------------------
# The whole simplification
# ---------------------------------------------------------------------------

def simplify(points: np.ndarray) -> tuple:
    """(face planes (n, d), the points they were taken from, whether Havok keeps those points' hull as it is) of
    `points` as Havok simplifies them before a polytope: snapped to the grid; then, unless the hull is
    degenerate (kept), the vertex pass, the grid again and the plane pass (under 4 planes left: kept)."""
    pts = snap(points)
    if degenerate(pts):
        return face_planes(convex_hull(pts))[1], pts, True
    pts = snap(collapse(pts, TOLERANCE))
    planes = merge(pts, TOLERANCE)
    return planes, pts, len(planes) < KEPT_UNDER


def capped(points: np.ndarray) -> tuple:
    """(planes, their points, False) of `points` cut to MAX_VERTICES by a vertex pass."""
    pts = snap(collapse(points, CAP_TOLERANCE, MAX_VERTICES))
    return face_planes(convex_hull(pts))[1], pts, False
