"""The terrain LOD edge-gap tool: gaps between two tiles' edges, and how much of them skirts leave open."""

import numpy as np

from fo4_import.spike import terrain_lod as T
from tools.lod import terrain_lod_edges as E

#: World units across a level-4 tile.
SIZE = 4 * E.CELL


def tile(x: int, lift: float, skirts: bool) -> tuple:
    """A level-4 tile at cell `x`, y 0, as load() gives it: a 3 × 3 flat grid at height `lift`, maybe skirted."""
    xs, ys = np.meshgrid(np.linspace(0, SIZE, 3), np.linspace(0, SIZE, 3), indexing='ij')
    pos = np.stack([xs.ravel(), ys.ravel(), np.full(9, lift)], axis=1)
    at = np.arange(9).reshape(3, 3)
    a, b, c, d = at[:-1, :-1].ravel(), at[1:, :-1].ravel(), at[1:, 1:].ravel(), at[:-1, 1:].ravel()
    tris = np.concatenate([np.stack([a, b, c], axis=1), np.stack([a, c, d], axis=1)])
    if skirts:
        pos, _, tris = T.with_skirts(pos, pos[:, :2], tris, 4)
    return pos + (x * E.CELL, 0, 0), tris


def test_open_length_counts_what_no_span_covers():
    """Overlapping and outside spans are merged and clipped."""
    assert E.open_length(0, 100, []) == 100
    assert E.open_length(0, 100, [(-50, 30), (20, 60), (90, 200)]) == 30


def test_a_step_between_tiles_is_open_without_skirts_and_closed_with_them():
    """Two level-4 tiles 300 units apart at their shared edge: every sample gaps 300; open with no skirts, closed
    by the higher tile's 1,000-unit skirt; a step deeper than the skirt stays open by the difference."""
    for skirts, lift, opened in ((False, 300, 300), (True, 300, 0), (True, 1200, 200)):
        tiles = {(4, 0, 0): tile(0, 0, skirts), (4, 4, 0): tile(4, lift, skirts)}
        (kind, a, b, gaps), = E.measure(tiles, (0, 0, 7, 3), 1024)
        assert kind == 'level 4 beside 4' and (a, b) == ((4, 0, 0), (4, 4, 0)) and len(gaps) == 16
        assert all(gap == lift and open_ == opened for gap, open_ in gaps)


def test_neighbours_pair_each_tile_with_the_next_level_up_across_a_side():
    """A level-4 tile in its parent's east half meets the level-8 tile east."""
    tiles = {(4, 4, 0): None, (8, 8, 0): None, (8, 0, 0): None}
    pairs = {(a, b) for a, b, *_ in E.neighbours(tiles)}
    assert pairs == {((4, 4, 0), (8, 8, 0)), ((8, 0, 0), (8, 8, 0))}
