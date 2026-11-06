"""FO3/FNV combat styles (CSTY): CSTD, CSAD and CSSD in their own layout, under the keys the Oblivion export uses.

The Oblivion export's CSTD lines are dropped for FO3/FNV (export_falloutnv.superseded_keys): the first 80 bytes
match Oblivion's, but from there FNV keeps a 16-bit flags field, its acrobatic dodge and rushing attack chances
and the rushing distance where Oblivion keeps its range and standoff fields. CSAD is laid out alike. CSSD is FO3/
FNV's own (xEdit wbDefinitionsFNV).

See: docs/fork/fo4_pipeline.md#combat-style-export
"""

from ..tes4_reader import Record, get_subrecord
from .actors import CSAD_FIELDS, CSTD_FIELDS, emit_fields

#: Where FO3/FNV's CSTD stops matching Oblivion's.
SHARED_END = 80
#: FO3/FNV CSTD from SHARED_END on, as (offset, struct format, key).
CSTD_TAIL = ((80, 'H', 'FalloutFlags'), (84, 'B', 'AcrobaticDodgeChance'), (85, 'B', 'RushingAttackChance'),
             (88, 'f', 'RushingAttackDistanceMult'))
#: FO3/FNV CSSD (Simple) fields, as (offset, struct format, key).
CSSD_FIELDS = ((0, 'f', 'CoverSearchRadius'), (4, 'f', 'TakeCoverChance'), (8, 'f', 'WaitTimerMin'),
               (12, 'f', 'WaitTimerMax'), (16, 'f', 'WaitToFireTimerMin'), (20, 'f', 'WaitToFireTimerMax'),
               (24, 'f', 'FireTimerMin'), (28, 'f', 'FireTimerMax'), (32, 'f', 'RangedWeaponRangeMultMin'),
               (40, 'I', 'WeaponRestrictions'), (44, 'f', 'RangedWeaponRangeMultMax'), (48, 'f', 'MaxTargetingFOV'),
               (52, 'f', 'CombatRadius'), (56, 'f', 'SemiAutoFiringDelayMultMin'),
               (60, 'f', 'SemiAutoFiringDelayMultMax'))


def emit_combat_style_deltas(lines: list, rec: Record) -> None:
    """A combat style's CSTD, CSAD and CSSD fields, each present one in FO3/FNV's layout."""
    cstd, csad, cssd = (get_subrecord(rec, sig) for sig in ('CSTD', 'CSAD', 'CSSD'))
    if cstd:
        emit_fields(lines, 'CSTD', cstd.data, [f for f in CSTD_FIELDS if f[0] < SHARED_END] + list(CSTD_TAIL))
    if csad:
        emit_fields(lines, 'CSAD', csad.data, [(4 * i, 'f', key) for i, key in enumerate(CSAD_FIELDS)])
    if cssd:
        emit_fields(lines, 'CSSD', cssd.data, CSSD_FIELDS)
