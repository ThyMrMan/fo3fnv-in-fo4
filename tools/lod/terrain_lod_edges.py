"""Gaps along the shared edges of a world's built Fallout 4 terrain LOD tiles (.btr).

For every edge two tiles share (same level, and a tile beside the next level up), heights are sampled every
--step units along it: the gap is the height between the two surfaces, and the open part of it is what neither
tile's skirt (the walls hanging from its border) covers. A crack you can see through is an open sample.

    python -m tools.lod.terrain_lod_edges <Meshes/Terrain/World folder> [--cells X0 Y0 X1 Y1] [--step 64]

See: docs/fork/fo4_terrain_lod_plan.md#checks
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from fo4_import.nif import file as F
from fo4_import.spike.terrain_lod import seen_area

#: A built tile's file name: level, south-west cell x and y.
NAME_RE = re.compile(r'\.(\d+)\.(-?\d+)\.(-?\d+)\.btr$', re.I)
#: World units across a cell.
CELL = 4096
#: Open gaps up to this many units are half-float rounding, not cracks.
TOLERANCE = 1.0
#: A tile's sides: (axis across them, 1 for the east or north side).
SIDES = ((0, 1), (1, 1), (0, 0), (1, 0))


def load(folder: Path) -> dict:
    """{(level, x, y): (world positions, triangles)} of the land shape of every .btr in `folder`."""
    out = {}
    for path in folder.glob('*.btr'):
        m = NAME_RE.search(path.name)
        if m:
            level, x, y = map(int, m.groups())
            land = F.read(path.read_bytes()).blocks[1][1]
            pos = np.array([v['position'] for v in land['vertices']], float) * land['scale']
            out[(level, x, y)] = (pos + (x * CELL, y * CELL, 0), np.array(land['triangles'], int))
    return out


def _on_line(pos: np.ndarray, tris: np.ndarray, axis: int, value: float) -> tuple:
    """(surface edges [(s0, z0, s1, z1)], walls [3 × (s, z)]) of a tile on the line where `axis` is `value`."""
    area = seen_area(pos, tris)
    on =pos[:, axis] == value
    along = 1 - axis
    edges = np.concatenate([tris[area != 0][:, [i, (i + 1) % 3]] for i in range(3)])
    edges = edges[on[edges].all(axis=1)]
    surface = np.stack([pos[edges[:, 0], along], pos[edges[:, 0], 2], pos[edges[:, 1], along],
                        pos[edges[:, 1], 2]], axis=1)
    walls = tris[(area == 0) & on[tris].all(axis=1)]
    return surface, pos[walls][:, :, [along, 2]]


def _surface_z(surface: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Each of `s`'s surface height on a line's edges (_on_line), the highest where several pass, NaN where none."""
    s0, z0, s1, z1 = (surface[:, i][None] for i in range(4))
    lo, hi = np.minimum(s0, s1), np.maximum(s0, s1)
    inside = (s[:, None] >= lo) & (s[:, None] <= hi) & (hi > lo)
    z = z0 + (z1 - z0) * (s[:, None] - s0) / np.where(hi > lo, s1 - s0, 1)
    best = np.where(inside, z, -np.inf).max(axis=1, initial=-np.inf)
    return np.where(np.isfinite(best), best, np.nan)


def _wall_spans(walls: np.ndarray, s: float) -> list:
    """[(z low, z high)] of each wall triangle's cut at `s` along its line."""
    spans = []
    for tri in walls:
        hits = [tri[i, 1] + (tri[j, 1] - tri[i, 1]) * (s - tri[i, 0]) / (tri[j, 0] - tri[i, 0])
                for i, j in ((0, 1), (1, 2), (2, 0))
                if tri[i, 0] != tri[j, 0] and min(tri[i, 0], tri[j, 0]) <= s <= max(tri[i, 0], tri[j, 0])]
        if hits:
            spans.append((min(hits), max(hits)))
    return spans


def open_length(low: float, high: float, spans: list) -> float:
    """How much of `low` to `high` no span in `spans` covers."""
    covered, reach = 0.0, low
    for a, b in sorted(spans):
        a, b = max(a, reach), min(b, high)
        if b > a:
            covered, reach = covered + b - a, b
    return high - low - covered


def edge_gaps(a: tuple, b: tuple, axis: int, value: float, span: tuple, step: int) -> list:
    """[(gap, open)] at every `step` along `span` of the line where `axis` is `value`, between tiles `a` and `b`
    (load()'s), where both have ground."""
    lines = [_on_line(*tile, axis, value) for tile in (a, b)]
    s = np.arange(span[0] + step / 2, span[1], step)
    za, zb = (_surface_z(surface, s) for surface, _ in lines)
    out = []
    for k in np.nonzero(np.isfinite(za) & np.isfinite(zb))[0]:
        low, high = sorted((za[k], zb[k]))
        spans = _wall_spans(lines[0][1], s[k]) + _wall_spans(lines[1][1], s[k])
        out.append((high - low, open_length(low, high, spans)))
    return out


def neighbours(tiles: dict) -> list:
    """[(tile, its neighbour, axis, value, span)] of every shared edge: same level once, and each tile against the
    next level up's tile across each side."""
    out = []
    for tile in tiles:
        level, corner = tile[0], tile[1:]
        parent = (2 * level, *(c - c % (2 * level) for c in corner))
        for axis, far in SIDES:
            across = list(corner)
            across[axis] += level if far else -1
            line = (corner[axis] + level * far) * CELL
            span = (corner[1 - axis] * CELL, (corner[1 - axis] + level) * CELL)
            up = (2 * level, *(c - c % (2 * level) for c in across))
            found = [(level, *across)] * far + [up] * (up != parent)
            out += [(tile, other, axis, line, span) for other in found if other in tiles]
    return out


def measure(tiles: dict, cells: tuple, step: int) -> list:
    """[(kind, tile, neighbour, gaps)] of every shared edge touching `cells` (x0, y0, x1, y1), edge_gaps()' gaps."""
    x0, y0, x1, y1 = cells
    inside = {t for t in tiles if t[1] <= x1 and t[1] + t[0] > x0 and t[2] <= y1 and t[2] + t[0] > y0}
    out = []
    for a, b, axis, value, span in neighbours(tiles):
        if a in inside or b in inside:
            kind = f'level {a[0]} beside {b[0]}'
            out.append((kind, a, b, edge_gaps(tiles[a], tiles[b], axis, value, span, step)))
    return out


def report(edges: list) -> str:
    """A table per edge kind: edges, samples, worst gap per edge (median, worst), open samples, edges and tiles
    with any, worst open."""
    rows = defaultdict(list)
    for kind, a, b, gaps in edges:
        if gaps:
            rows[kind].append((a, b, np.array(gaps)))
    lines = ['| Edge | Edges | Samples | Worst gap per edge, median | Worst gap | Open samples | Edges open '
             '| Tiles open | Worst open |', '|---|---|---|---|---|---|---|---|---|']
    for kind in sorted(rows, key=lambda k: [int(n) for n in re.findall(r'\d+', k)]):
        found = rows[kind]
        opened = [(a, b, g) for a, b, g in found if (g[:, 1] > TOLERANCE).any()]
        tiles = {t for a, b, _ in opened for t in (a, b)}
        worst = [g[:, 0].max() for _, _, g in found]
        lines.append(f'| {kind} | {len(found)} | {sum(len(g) for *_, g in found)} | {np.median(worst):.0f} '
                     f'| {max(worst):.0f} | {sum(int((g[:, 1] > TOLERANCE).sum()) for *_, g in found)} '
                     f'| {len(opened)} | {len(tiles)} | {max(g[:, 1].max() for *_, g in found):.0f} |')
    return '\n'.join(lines)


def main() -> None:
    """Print the edge table of the tiles in the folder given."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--cells', type=int, nargs=4, default=(-10 ** 6, -10 ** 6, 10 ** 6, 10 ** 6))
    parser.add_argument('--step', type=int, default=64)
    args = parser.parse_args()
    print(report(measure(load(args.folder), tuple(args.cells), args.step)))


if __name__ == '__main__':
    main()
