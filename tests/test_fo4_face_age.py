"""fo4_import.spike.npcs: an NPC of an old race (a younger race and no older) wears Fallout4.esm's old face set.

See: docs/fork/fo4_facegen_plan.md#age-face-set
"""

import collections
import struct
from types import SimpleNamespace

from fo4_import.spike import npcs as N
from tes5_import.base.tes5_reader import first_sub
from tes5_import.base.writer import pack_subrecord


def _npcs() -> N.Npcs:
    """An Npcs knowing FO3's CaucasianOld as an old race."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.old_races = {0x42C3}
    npcs.builder = SimpleNamespace(counts=collections.Counter())
    return npcs


def test_an_old_race_npc_gets_the_old_face_set_of_its_sex():
    """CaucasianOld's man and woman name SkinHeadOldMale and SkinHeadFemaleOld before QNAM; Caucasian's none."""
    npcs, subs = _npcs(), pack_subrecord('EDID', b'x\0') + pack_subrecord('QNAM', bytes(12))
    man = npcs._aged({'RNAM.Race': '000042C3'}, False)(subs)
    woman = npcs._aged({'RNAM.Race': '000042C3'}, True)(subs)
    assert struct.unpack('<I', first_sub(man, b'FTST'))[0] == 0x128C59
    assert struct.unpack('<I', first_sub(woman, b'FTST'))[0] == 0x03C655
    assert man.index(b'FTST') < man.index(b'QNAM')
    assert npcs._aged({'RNAM.Race': '00000019'}, False) is None
    assert npcs.builder.counts['faces on an old face set'] == 2


def test_old_races_are_those_with_only_a_younger_race():
    """Adult races link both ways and children only to an older race; Old and OldAged only to a younger one."""
    races = ({'FormID': '00000019', 'ONAM.Older': '000042C3', 'YNAM.Younger': '000042C2'},
             {'FormID': '000042C2', 'ONAM.Older': '00000019'},
             {'FormID': '000042C3', 'YNAM.Younger': '00000019'}, {'FormID': '00000020'})
    assert N.old_races(races) == {0x42C3}
