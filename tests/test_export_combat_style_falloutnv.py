"""FO3/FNV combat styles export in their own layout: Oblivion's shared CSTD fields, FNV's tail, CSAD and CSSD.

See: docs/fork/fo4_pipeline.md#combat-style-export
"""

import struct

from tes4_export.record_types.combat_style_falloutnv import emit_combat_style_deltas
from tes4_export.record_types.falloutnv import export_deltas
from tes4_export.tes4_reader import Record, Subrecord


def _coyote() -> Record:
    """FNV's CSCoyote as its bytes lay it out: attack 40, flags 272 (16-bit), rushing 75, ranged only CSSD."""
    cstd = bytearray(92)
    cstd[0], cstd[36], cstd[37] = 75, 30, 40
    struct.pack_into('<H', cstd, 80, 272)
    cstd[85] = 75
    struct.pack_into('<f', cstd, 88, 1.0)
    csad = struct.pack('<21f', *range(21))
    cssd = bytearray(64)
    struct.pack_into('<f', cssd, 0, 2048.0)
    struct.pack_into('<I', cssd, 40, 2)
    subs = [Subrecord('CSTD', bytes(cstd)), Subrecord('CSAD', csad), Subrecord('CSSD', bytes(cssd))]
    return Record('CSTY', 0, 0, 0x14F432, subs)


def test_fnv_fields_export_under_the_converters_keys():
    """The shared fields, FNV's 16-bit flags and rushing chance, CSAD by name and CSSD all come out."""
    lines = []
    emit_combat_style_deltas(lines, _coyote())
    got = dict(line.split('=', 1) for line in lines)
    assert (got['CSTD.AttackChance'], got['CSTD.BlockChance'], got['CSTD.DodgeChance']) == ('40', '30', '75')
    assert (got['CSTD.FalloutFlags'], got['CSTD.RushingAttackChance']) == ('272', '75')
    assert 'CSTD.RangeMultOptimal' not in got and 'CSTD.Flags' not in got
    assert got['CSAD.AttackNotUnderAttackMult'] == '17.0'
    assert (got['CSSD.CoverSearchRadius'], got['CSSD.WeaponRestrictions']) == ('2048.0', '2')


def test_the_deltas_dispatch_combat_styles():
    """export_deltas writes an FO3/FNV combat style's fields."""
    assert any(line.startswith('CSTD.AttackChance=') for line in export_deltas(_coyote()))
