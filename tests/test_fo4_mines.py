"""Placed FNV mines (PGRE) fly the projectile of the FO4 weapon their weapon becomes, Fallout4.esm's or the build's copy.

See: docs/fork/fo4_pipeline.md#placed-mines
"""

from collections import Counter
from types import SimpleNamespace

from fo4_import.spike.mines import Mines

#: FNV MineFragProjectile, WeapMineFrag, its stats copy in the build, and the copy's FNAM projectile (FragMineProjectile).
FNV_PROJECTILE, FNV_WEAPON, COPY, FO4_PROJECTILE = 0x43FA, 0x43F9, 0x0377D20A, 0x0010A33F


def _mines(fired_by_copy: dict) -> Mines:
    """A Mines over one FNV frag mine whose weapon converts to COPY, the build's copy firing `fired_by_copy`."""
    counts = Counter()
    builder = SimpleNamespace(counts=counts, items=SimpleNamespace(item=lambda fid: COPY if fid == FNV_WEAPON else None),
                              equipment=SimpleNamespace(fired=fired_by_copy))
    mines = Mines.__new__(Mines)
    mines.builder, mines.weapons, mines.fired = builder, {FNV_PROJECTILE: FNV_WEAPON}, {}
    return mines


def test_a_mine_on_a_stats_copy_flies_the_copys_projectile():
    """A mine on the build's copy of fragMine flies the copy's FNAM projectile."""
    mines = _mines({COPY: FO4_PROJECTILE})
    assert mines.projectile(FNV_PROJECTILE) == FO4_PROJECTILE
    assert not mines.builder.counts


def test_a_mine_whose_weapon_does_not_convert_is_left_out_and_counted():
    """No converted weapon: the mine is left out, counted with the reason."""
    mines = _mines({})
    assert mines.projectile(FNV_PROJECTILE) is None
    assert mines.builder.counts['placed mine left out: its weapon is not converted'] == 1
