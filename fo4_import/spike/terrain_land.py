"""Fallout 4 terrain LOD tiles built from the land (each cell's LAND VHGT), not from FNV's prebuilt tiles.

A tile of level L at south-west cell (x, y) covers L x L cells. Its heights are the cells' 33 x 33 VHGT points
(neighbours sharing their edge rows), every point at levels 4 and 8 and every 2nd or 4th above, so a tile side
has at most MAX_SIDE points. The mesh is a right-triangle hierarchy (as Martini's RTIN) simplified by height
error to the level's triangle budget. Every tile edge keeps the same fixed points at its level, one every
L x 128 units and no others, so same-level neighbours share their edges and a coarser one's points are a
subset of a finer one's; level 4 keeps its cell borders the same way. Skirts hang as terrain_lod's.

See: docs/fork/fo4_terrain_lod_plan.md#p2
"""

from collections import deque

import numpy as np

from fo4_import.base.dds_encode import resized
from tes5_import.navmesh.world import decode_vhgt

#: World units a cell spans, and land points per cell side less one.
CELL, CELL_POINTS = 4096, 32
#: World units between two land points.
SPACING = CELL // CELL_POINTS
#: Most points across a tile side (2^8 + 1): levels 16 and 32 take every 2nd and 4th land point.
MAX_SIDE = 257
#: Lowest LOD level (cells across its tiles), built cell by cell.
MIN_LEVEL = 4
#: Triangle budget of a level-4 tile and of a tile above (vanilla spends about 2,050 at every level).
BUDGET = {MIN_LEVEL: 4000}
DEFAULT_BUDGET = 3000
#: {level: land points between the inner lines kept like a tile edge}; a level not listed keeps only its edges.
CELL_LINES = {}
#: Height error (world units) under which no point is added.
MIN_ERROR = 1.0
#: Side in pixels of a tile's normal map at every level (vanilla's).
NORMAL_SIZE = 512
#: The four grid neighbours of a cell.
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def cell_heights(cells: dict, land: dict) -> dict:
    """{(x, y): 33 x 33 heights, [x index][y index]} of grid cells `cells` ({grid: CELL}) whose LAND in `land`
    ({CELL FormID: LAND}) has readable VHGT."""
    out = {}
    for grid, cell in cells.items():
        vhgt = land.get(cell['FormID'], {}).get('VHGT')
        heights = decode_vhgt(vhgt) if vhgt else None
        if heights is not None:
            out[grid] = heights.T
    return out


def holes(heights: dict) -> set:
    """The cells without land that land encloses: those no path through land-less cells joins to the outside of
    `heights`' bounding box."""
    if not heights:
        return set()
    xs, ys = zip(*heights)
    lo, hi = (min(xs) - 1, min(ys) - 1), (max(xs) + 1, max(ys) + 1)
    seen, queue = {lo}, deque([lo])
    while queue:
        x, y = queue.popleft()
        for dx, dy in STEPS:
            nxt = (x + dx, y + dy)
            inside = lo[0] <= nxt[0] <= hi[0] and lo[1] <= nxt[1] <= hi[1]
            if inside and nxt not in seen and nxt not in heights:
                seen.add(nxt)
                queue.append(nxt)
    every = {(x, y) for x in range(lo[0], hi[0] + 1) for y in range(lo[1], hi[1] + 1)}
    return every - set(heights) - seen


def _patch(heights: dict, cell: tuple) -> np.ndarray:
    """The heights of `cell` and the ring of cells around it, NaN where none."""
    out = np.full((3 * CELL_POINTS + 1,) * 2, np.nan)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (cell[0] + dx, cell[1] + dy) in heights:
                i, j = (dx + 1) * CELL_POINTS, (dy + 1) * CELL_POINTS
                out[i:i + CELL_POINTS + 1, j:j + CELL_POINTS + 1] = heights[(cell[0] + dx, cell[1] + dy)]
    return out


def spread(grid: np.ndarray) -> np.ndarray:
    """`grid` with every NaN point that touches a known one set to their mean, repeated until none is left (or
    none touches one)."""
    grid = grid.copy()
    while np.isnan(grid).any():
        padded = np.pad(grid, 1, constant_values=np.nan)
        near = np.stack([padded[1 + dx:padded.shape[0] - 1 + dx, 1 + dy:padded.shape[1] - 1 + dy]
                         for dx, dy in STEPS])
        count = np.isfinite(near).sum(axis=0)
        if not (count[np.isnan(grid)] > 0).any():
            break
        mean = np.nansum(near, axis=0) / np.maximum(count, 1)
        grid = np.where(np.isnan(grid) & (count > 0), mean, grid)
    return grid


def filled(heights: dict) -> dict:
    """`heights` with every hole (holes()) given land spread in from the cells around it, in cell order, so every
    tile sees the same heights.
    See: docs/fork/fo4_terrain_lod_plan.md#p1
    """
    out = dict(heights)
    for cell in sorted(holes(heights)):
        out[cell] = spread(_patch(out, cell))[CELL_POINTS:2 * CELL_POINTS + 1, CELL_POINTS:2 * CELL_POINTS + 1]
    return out


def stride(level: int) -> int:
    """Land points between two of a level-`level` tile's grid points."""
    return max(1, level * CELL_POINTS // (MAX_SIDE - 1))


def tile_heights(heights: dict, level: int, x: int, y: int, step: int = 0) -> np.ndarray:
    """The heights of the level-`level` tile at south-west cell (x, y), [x index][y index] every `step` (stride()
    by default) land points, NaN where no cell has land. A point cells share takes the east, then north, cell's
    height, the cells past the tile's east and north edges included, so neighbouring tiles agree.
    See: docs/fork/fo4_terrain_lod_plan.md#p1
    """
    side = level * CELL_POINTS + 1
    full = np.full((side + CELL_POINTS,) * 2, np.nan)
    for cx in range(x, x + level + 1):
        for cy in range(y, y + level + 1):
            if (cx, cy) in heights:
                i, j = (cx - x) * CELL_POINTS, (cy - y) * CELL_POINTS
                full[i:i + CELL_POINTS + 1, j:j + CELL_POINTS + 1] = heights[(cx, cy)]
    step = step or stride(level)
    return full[:side:step, :side:step]


def normal_map(full: np.ndarray, size: int = NORMAL_SIZE) -> np.ndarray:
    """The (size, size, 4) uint8 model-space normal map of land grid `full` ([x][y], SPACING apart) in FO4's
    layout: R x, G up, B y; image column along x, row 0 at the north edge; flat where land is missing.
    See: docs/fork/fo4_terrain_lod_plan.md#p3
    """
    gx, gy = np.gradient(full, SPACING)
    normal = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    normal[~np.isfinite(normal).all(axis=-1)] = (0.0, 0.0, 1.0)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    image = normal.transpose(1, 0, 2)[::-1][..., [0, 2, 1]]
    rgb = np.round((image * 0.5 + 0.5) * 255)
    rgba = np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 255.0)], axis=-1).astype(np.uint8)
    return resized(rgba, (size, size))


def _roots(n: int) -> tuple:
    """(a, b, c) of the two triangles halving an n x n grid along its diagonal."""
    m = n - 1
    return np.array([[0, 0], [m, m]]), np.array([[m, m], [0, 0]]), np.array([[m, 0], [0, m]])


def _splits(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Whether each hypotenuse a to b has a grid midpoint."""
    return (np.abs(a - b).max(axis=1) > 1) | (a == b).any(axis=1)


def levels(n: int) -> list:
    """[(a, b, c)] point arrays of every level of the right-triangle hierarchy on an n x n grid (n = 2^k + 1),
    coarsest first: hypotenuse a to b, right angle c; a triangle's children are (c, a, m) and (b, c, m)."""
    a, b, c = _roots(n)
    out = []
    while _splits(a[:1], b[:1])[0]:
        out.append((a, b, c))
        mid = (a + b) // 2
        a, b, c = np.concatenate([c, b]), np.concatenate([a, c]), np.concatenate([mid, mid])
    return out


def fixed_points(n: int, border: int, lines: int) -> tuple:
    """(forced, forbidden) masks of an n x n grid: the points on a fixed line (every `lines` points) at every
    `border` points along it are kept, the others on it never added."""
    i = np.arange(n)
    on_x, on_y = (i % lines == 0)[:, None], (i % lines == 0)[None, :]
    every_x, every_y = (i % border == 0)[:, None], (i % border == 0)[None, :]
    forced = (on_x & every_y) | (on_y & every_x)
    return forced, (on_x | on_y) & ~forced


def _at(grid: np.ndarray, points: np.ndarray) -> np.ndarray:
    """`grid`'s values at `points` ([(i, j)])."""
    return grid[points[:, 0], points[:, 1]]


def forbidden_cone(tree: list, forbidden: np.ndarray) -> np.ndarray:
    """`forbidden` and every point whose adding needs one of them: a triangle whose hypotenuse midpoint is never
    added never adds its legs' midpoints."""
    forbidden = forbidden.copy()
    for a, b, c in tree[:-1]:
        bad = _at(forbidden, (a + b) // 2)
        for leg in ((c + a) // 2, (b + c) // 2):
            forbidden[leg[bad, 0], leg[bad, 1]] = True
    return forbidden


def errors(heights: np.ndarray, tree: list, forced: np.ndarray, forbidden: np.ndarray) -> np.ndarray:
    """Each point's height error: how far it lies off its triangle's hypotenuse, at least its descendants'; inf
    where `forced`, -1 where `forbidden` (forbidden_cone()'s). A point is added when its error passes a threshold.
    See: docs/fork/fo4_terrain_lod_plan.md#p2
    """
    out = np.zeros(heights.shape)
    for depth, (a, b, c) in reversed(list(enumerate(tree))):
        mid = (a + b) // 2
        own = np.nan_to_num(np.abs(_at(heights, mid) - (_at(heights, a) + _at(heights, b)) / 2))
        np.maximum.at(out, (mid[:, 0], mid[:, 1]), own)
        if depth < len(tree) - 1:
            for leg in ((c + a) // 2, (b + c) // 2):
                np.maximum.at(out, (mid[:, 0], mid[:, 1]), _at(out, leg))
        out[forbidden], out[forced] = -1.0, np.inf
    return out


def threshold(error: np.ndarray, border_points: int, budget: int) -> float:
    """The error over which added points fit `budget` triangles, at least MIN_ERROR."""
    added = max(0, (budget + border_points + 2) // 2 - 4)
    ranked = np.sort(error.ravel())[::-1]
    return max(MIN_ERROR, float(ranked[added]) if added < len(ranked) else MIN_ERROR)


def triangles(n: int, chosen: np.ndarray) -> np.ndarray:
    """[(a, b, c)] grid points of the hierarchy's triangles on an n x n grid, split where `chosen` holds their
    hypotenuse midpoint."""
    a, b, c = _roots(n)
    out = []
    while len(a):
        mid = (a + b) // 2
        split = _splits(a, b) & _at(chosen, mid)
        out.append(np.stack([a[~split], b[~split], c[~split]], axis=1))
        a, b, c, mid = a[split], b[split], c[split], mid[split]
        a, b, c = np.concatenate([c, b]), np.concatenate([a, c]), np.concatenate([mid, mid])
    return np.concatenate(out)


def facing_up(pos: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """`tris` each wound counter-clockwise seen from above."""
    a, b, c = pos[tris[:, 0], :2], pos[tris[:, 1], :2], pos[tris[:, 2], :2]
    down = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]) < 0
    out = tris.copy()
    out[down] = tris[down][:, [0, 2, 1]]
    return out


def tile_mesh(heights: np.ndarray, level: int) -> tuple:
    """(positions in world units from the tile's south-west corner, triangles facing up) of the level-`level`
    tile with grid `heights` (tile_heights()), simplified to its budget; triangles over a point without land
    are left out.
    See: docs/fork/fo4_terrain_lod_plan.md#p2
    """
    n, step = len(heights), stride(level)
    border = level // step
    tree = levels(n)
    forced, forbidden = fixed_points(n, border, CELL_LINES.get(level, (n - 1) * step) // step)
    error = errors(heights, tree, forced, forbidden_cone(tree, forbidden))
    chosen = error > threshold(error, 4 * (n - 1) // border, BUDGET.get(level, DEFAULT_BUDGET))
    tris = triangles(n, chosen)
    used, index = np.unique(tris[:, :, 0] * n + tris[:, :, 1], return_inverse=True)
    i, j = used // n, used % n
    pos = np.stack([i * step * SPACING, j * step * SPACING, heights[i, j]], axis=1).astype(float)
    tris = index.reshape(-1, 3)
    tris = facing_up(pos, tris[np.isfinite(pos[tris, 2]).all(axis=1)])
    kept, tris = np.unique(tris, return_inverse=True)
    return pos[kept], tris.reshape(-1, 3)
