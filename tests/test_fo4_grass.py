"""FNV grass on Fallout 4: density on FO4's finer grass grid.

See: docs/fork/fo4_look.md#grass-density
"""
from fo4_import.spike import grass as G


def _density(value: int) -> int:
    """The FO4 density pack_data writes for FNV density `value`."""
    return G.DATA.unpack(G.pack_data({'DATA.Density': value}))[0]


def test_density_is_scaled_by_the_two_grids_with_a_floor_of_one():
    """FO4's grid (20) tries 16x FNV's (80) points, so density is 1/16, never 0."""
    assert G.DENSITY_SCALE == 1 / 16
    assert [_density(v) for v in (100, 40, 25, 3)] == [6, 2, 2, 1]

