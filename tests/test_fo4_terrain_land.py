"""Terrain LOD tiles from the land: heights, holes, and a mesh whose edges neighbours share."""

from collections import Counter

import numpy as np
import pytest

from fo4_import.spike import terrain_land as L


def rough(seed: int, cells: list) -> dict:
    """{cell: 33 x 33 heights} of `cells`, one smooth random surface so neighbours share their edges."""
    rng = np.random.default_rng(seed)
    waves = rng.uniform(0.2, 3.0, (12, 4))

    def height(x, y):
        """The surface at world (x, y)."""
        return sum(a * 300 * np.sin(x / (f * 2000) + p) * np.cos(y / (f * 1700) + p) for a, f, p, _ in waves)

    i = np.arange(33) * L.SPACING
    return {(cx, cy): height(cx * L.CELL + i[:, None], cy * L.CELL + i[None, :]) for cx, cy in cells}


def edge_counts(tris: np.ndarray) -> Counter:
    """How many triangles use each edge."""
    return Counter(tuple(sorted(e)) for t in tris.tolist() for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))


@pytest.mark.parametrize('level', [4, 8, 16, 32])
def test_a_tile_is_watertight_and_keeps_only_its_fixed_border_points(level):
    """Every inner edge joins two triangles (no T-junction); the border holds exactly one point every
    level x 128 units, 33 a side; the triangles face up and keep to the budget."""
    span = level * L.CELL
    heights = rough(level, [(x, y) for x in range(level) for y in range(level)])
    pos, tris = L.tile_mesh(L.tile_heights(heights, level, 0, 0), level)
    on_border = (pos[:, :2] == 0) | (pos[:, :2] == span)
    for axis in (0, 1):
        side = pos[on_border[:, 1 - axis], axis]
        assert sorted(set(side.tolist())) == list(range(0, span + 1, level * L.SPACING))
    counts = edge_counts(tris)
    single = [e for e, n in counts.items() if n == 1]
    assert max(counts.values()) == 2 and len(single) == 4 * 32
    assert all(any(pos[a, axis] == pos[b, axis] in (0, span) for axis in (0, 1)) for a, b in single)
    assert len(tris) <= L.BUDGET.get(level, L.DEFAULT_BUDGET) + 8
    a, b, c = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    assert (np.cross(b - a, c - a)[:, 2] > 0).all()


def test_inner_lines_kept_like_an_edge_when_asked():
    """A level listed in CELL_LINES keeps its cell borders as it keeps its edges: no triangle crosses one."""
    heights = rough(1, [(x, y) for x in range(4) for y in range(4)])
    L.CELL_LINES[4] = L.CELL_POINTS
    try:
        pos, tris = L.tile_mesh(L.tile_heights(heights, 4, 0, 0), 4)
    finally:
        del L.CELL_LINES[4]
    corner = (pos[tris].mean(axis=1)[:, None, :2] // L.CELL) * L.CELL
    assert ((pos[tris][:, :, :2] >= corner) & (pos[tris][:, :, :2] <= corner + L.CELL)).all()
    for axis in (0, 1):
        assert (pos[pos[:, axis] % L.CELL == 0, 1 - axis] % 512 == 0).all()


def test_neighbours_of_one_level_share_their_edge():
    """Two level-8 tiles side by side put the same points at the same heights on their shared edge."""
    heights = rough(3, [(x, y) for x in range(16) for y in range(8)])
    west = L.tile_mesh(L.tile_heights(heights, 8, 0, 0), 8)[0]
    east = L.tile_mesh(L.tile_heights(heights, 8, 8, 0), 8)[0]
    edge = west[west[:, 0] == 8 * L.CELL][:, 1:]
    other = east[east[:, 0] == 0][:, 1:]
    assert len(edge) == 33 and sorted(map(tuple, edge)) == sorted(map(tuple, other))


def test_neighbours_agree_where_their_cells_disagree():
    """Where two cells' shared edge rows differ (40 of WastelandNV's 32,515), both tiles take the east cell's."""
    heights = rough(6, [(x, 0) for x in range(8)])
    heights[(3, 0)] = heights[(3, 0)].copy()
    heights[(3, 0)][-1] += 500
    west, east = (L.tile_heights(heights, 4, x, 0) for x in (0, 4))
    assert np.array_equal(west[-1], east[0], equal_nan=True)
    assert np.array_equal(east[0, :33], heights[(4, 0)][0])


def test_a_coarser_neighbour_s_edge_points_are_the_finer_one_s():
    """A level-16 tile's points on its edge are every other point of the level-8 tiles beside it."""
    heights = rough(4, [(x, y) for x in range(32) for y in range(16)])
    coarse = L.tile_mesh(L.tile_heights(heights, 16, 16, 0), 16)[0]
    fine = np.concatenate([L.tile_mesh(L.tile_heights(heights, 8, 8, y), 8)[0] + (0, y * L.CELL, 0)
                           for y in (0, 8)])
    edge = {tuple(p) for p in coarse[coarse[:, 0] == 0][:, 1:]}
    assert edge <= {tuple(p) for p in fine[fine[:, 0] == 8 * L.CELL][:, 1:]} and len(edge) == 33


def test_an_enclosed_cell_without_land_takes_its_neighbours_heights_and_the_outside_stays_empty():
    """A cell ringed by land is filled from it, its edges its neighbours'; cells past the land stay without."""
    ramp = np.repeat(np.arange(33)[:, None] * 100 / 32, 33, axis=1)
    heights = {(x, y): ramp + 100 * x for x in range(3) for y in range(3) if (x, y) != (1, 1)}
    assert L.holes(heights) == {(1, 1)}
    out = L.filled(heights)
    assert set(out) == set(heights) | {(1, 1)} and np.isfinite(out[(1, 1)]).all()
    assert (out[(1, 1)][0] == 100).all() and (out[(1, 1)][-1] == 200).all()
    assert (out[(1, 1)] >= 100).all() and (out[(1, 1)] <= 200).all()
    assert L.holes({(0, 0): heights[(0, 0)], (2, 0): heights[(2, 0)]}) == set()


def test_a_tile_past_the_land_leaves_no_ground():
    """Triangles over cells without land are left out."""
    heights = rough(5, [(x, y) for x in range(2) for y in range(4)])
    pos, tris = L.tile_mesh(L.tile_heights(heights, 4, 0, 0), 4)
    assert len(tris) and pos[np.unique(tris), 0].max() == 2 * L.CELL


def test_normal_map_is_fo4_s_model_space_layout():
    """Land rising east leans R under 128; rising north leans B under 128 (B follows y), G stays up; image row 0
    is the north edge; land missing is flat."""
    ramp = np.repeat(np.arange(65.0)[:, None], 65, axis=1) * 64
    east, north = L.normal_map(ramp, 64), L.normal_map(ramp.T, 64)
    assert (east[..., 0] < 100).all() and (abs(east[..., 2].astype(int) - 128) <= 1).all()
    assert (north[..., 2] < 100).all() and (abs(north[..., 0].astype(int) - 128) <= 1).all()
    assert (east[..., 1] > 200).all() and (east[..., 3] == 255).all()
    ridge = np.zeros((65, 65))
    ridge[:, 60:] = np.arange(5) * 200
    image = L.normal_map(ridge, 64)
    assert (image[:4, :, 2] < 120).all() and (abs(image[-8:, :, 2].astype(int) - 128) <= 1).all()
    missing = np.full((65, 65), np.nan)
    assert (abs(L.normal_map(missing, 8)[..., :3].astype(int) - (128, 255, 128)) <= 1).all()


def test_flat_land_takes_only_its_fixed_points():
    """Flat land adds no point past the fixed ones."""
    flat = {(x, y): np.zeros((33, 33)) for x in range(8) for y in range(8)}
    pos, tris = L.tile_mesh(L.tile_heights(flat, 8, 0, 0), 8)
    assert len(tris) < 1000 and len(pos) < 600
