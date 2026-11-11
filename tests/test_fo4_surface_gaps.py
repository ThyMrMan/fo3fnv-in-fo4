"""surface_gaps finds the same near points as testing every point against every triangle, in bounded memory.

See: docs/fork/fo4_pipeline.md#overlay-layers
"""

import tracemalloc

import numpy as np

from fo4_import.nif import surface_gaps as sg

LIMIT = 4.0


def dense(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Every point against every triangle at once (the old way), cut at LIMIT."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    normal = np.cross(b - a, c - a)
    size = np.linalg.norm(normal, axis=1)
    keep = size > sg.FLAT
    a, b, c, normal = a[keep], b[keep], c[keep], normal[keep] / size[keep, None]
    out = sg.pair_gaps(points, a, b, c, normal)
    return np.where(out <= LIMIT, out, np.inf)


def soup(rng, triangles: int, points: int, spread: float) -> tuple:
    """(points, triangles) on and around a plane `spread` units wide, with a sliver every tenth triangle."""
    base = rng.uniform(0, spread, (triangles, 1, 3)) * (1, 1, 0.01)
    tris = base + rng.normal(0, 1.0, (triangles, 3, 3))
    tris[::10, 2] = tris[::10, 0] + (tris[::10, 1] - tris[::10, 0]) * 0.5 + 1e-6
    pts = rng.uniform(0, spread, (points, 3)) * (1, 1, 0.01) + rng.normal(0, 3.0, (points, 3))
    return pts, tris


def test_gaps_match_testing_every_pair():
    """Distances within the limit, and inf beyond it, equal the dense test's exactly."""
    pts, tris = soup(np.random.default_rng(7), 3000, 1200, 60.0)
    assert np.array_equal(sg.gaps(pts, sg.surface(tris, LIMIT)), dense(pts, tris))


def test_memory_stays_bounded_on_a_huge_surface():
    """100,000 triangles x 2,048 points peak under 64 MB; the old 256-point chunk took 614 MB per temporary."""
    pts, tris = soup(np.random.default_rng(3), 100_000, 2048, 3000.0)
    surface = sg.surface(tris, LIMIT)
    tracemalloc.start()
    found = sg.gaps(pts, surface)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 64 * 2 ** 20 and np.isfinite(found).any()


def test_groups_hold_every_point_once_and_stay_small():
    """point_groups splits the points into groups of at most GAP_GROUP, each point in one."""
    pts = np.random.default_rng(1).uniform(0, 100, (5000, 3))
    groups = sg.point_groups(pts, np.arange(len(pts)))
    assert max(len(g) for g in groups) <= sg.GAP_GROUP
    assert sorted(np.concatenate(groups).tolist()) == list(range(len(pts)))
