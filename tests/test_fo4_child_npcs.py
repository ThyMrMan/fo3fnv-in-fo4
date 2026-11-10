"""fo4_import.spike child NPCs: the child body on HumanChildRace, no face fit, and child clothes.

See: docs/fork/fo4_pipeline.md#child-bodies
"""

import collections
import struct
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.spike import npcs as N
from fo4_import.spike import replacements
from fo4_import.spike.equipment import Equipment
from tes5_import.base.tes5_reader import first_sub
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm HumanChildRace and HumanRace.
CHILD_RACE, HUMAN_RACE = 0x11D83F, 0x13746


def _npcs() -> N.Npcs:
    """An Npcs knowing a Caucasian race, a child one and a ghoul one."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.races = {0x19: 'Caucasian', 0x42C2: 'CaucasianChild', 0x3B3E: 'Ghoul'}
    npcs.child_races = {0x42C2}
    return npcs


def test_a_child_race_npc_gets_the_child_body_and_no_face_fit():
    """A child race's NPC takes child_<sex> and keeps its body's face; an adult human still fits its own."""
    npcs = _npcs()
    kind, female, fitted = npcs._kind({'RNAM.Race': '000042C2', 'ACBS.Flags': '1'})
    assert (kind, female, fitted) == ('child_female', True, False)
    assert npcs._kind({'RNAM.Race': '000042C2', 'ACBS.Flags': '0'})[0] == 'child_male'
    assert npcs._kind({'RNAM.Race': '00003B3E', 'ACBS.Flags': '0'})[0] == 'ghoul_male'
    assert npcs._kind({'RNAM.Race': '00000019', 'ACBS.Flags': '0'})[0] == 'human_male'


def test_the_table_gives_child_bodies_and_kid_outfits_child_clothes():
    """The defaults name a body per child kind and copy FNV's kid outfits from FO4's child clothes."""
    table = replacements.load()
    assert {'child_male', 'child_female'} <= set(table.rules.body)
    assert table['KIDOutfitWastelandChild01'].use == 'Fallout4.esm|ClothesKids02'
    assert table['KIDOutfitWastelandChild04'].mode == 'stats'


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_the_child_bodies_are_on_human_child_race():
    """Both child body templates in Fallout4.esm are HumanChildRace NPCs."""
    rules = replacements.load().rules.body
    found = N.bodies(FALLOUT4_ESM.read_bytes(), {k: rules[k] for k in ('child_male', 'child_female')})
    assert {struct.unpack('<I', first_sub(r.body, b'RNAM'))[0] for r in found.values()} == {CHILD_RACE}


def _equipment() -> Equipment:
    """An Equipment over a kid outfit (on a child addon) and an adult shirt (on a human addon)."""
    eq = Equipment.__new__(Equipment)
    eq.table = replacements.Table.of({
        'KidRags': replacements.Replacement('Fallout4.esm', 'ClothesKids02', 'stats'),
        'Shirt': replacements.Replacement('Fallout4.esm', 'ClothesShirt', 'fnv')})
    eq.vanilla = {'ClothesKids02': [(b'INDX', bytes(2)), (b'MODL', struct.pack('<I', 0xA1))],
                  'ClothesShirt': [(b'INDX', bytes(2)), (b'MODL', struct.pack('<I', 0xA2))]}
    eq.addons = {0xA1: [(b'RNAM', struct.pack('<I', CHILD_RACE))],
                 0xA2: [(b'RNAM', struct.pack('<I', HUMAN_RACE)), (b'MODL', struct.pack('<I', 0x1234))]}
    return eq


def test_draws_on_reads_the_templates_addon_races():
    """A kid outfit's copy draws on HumanChildRace; an adult shirt's, on HumanRace and its additional race only."""
    eq = _equipment()
    assert eq.draws_on({'EditorID': 'KidRags', 'Signature': 'ARMO'}, CHILD_RACE)
    assert not eq.draws_on({'EditorID': 'Shirt', 'Signature': 'ARMO'}, CHILD_RACE)
    assert eq.draws_on({'EditorID': 'Shirt', 'Signature': 'ARMO'}, 0x1234)
    assert not eq.draws_on({'EditorID': 'Unlisted', 'Signature': 'ARMO'}, CHILD_RACE)


def test_a_child_wears_only_child_clothes_else_its_bodys_outfit():
    """Of a kid outfit and a Pip-Boy the child wears the outfit; with only an adult shirt it wears nothing of its
    own, so its body's outfit stays."""
    npcs = N.Npcs.__new__(N.Npcs)
    rec = lambda edid: ('ARMO', {'EditorID': edid, 'Signature': 'ARMO', 'BMDT.BipedFlags': '4'})
    records = {1: rec('KidRags'), 2: rec('Shirt'), 3: ('ARMO', {'EditorID': 'PipBoy', 'BMDT.BipedFlags': '64'})}
    npcs.builder = SimpleNamespace(items=SimpleNamespace(records=records), equipment=_equipment(),
                                   counts=collections.Counter())
    assert npcs._child_worn({1, 3}, CHILD_RACE) == {1}
    assert npcs._child_worn({2, 3}, CHILD_RACE) == set()


def test_with_inventory_keeps_the_bodys_outfit_when_asked():
    """Outfit 0 with keep leaves the body's DOFT; without keep it goes."""
    body = pack_subrecord('DOFT', struct.pack('<I', 9)) + pack_subrecord('AIDT', bytes(24))
    assert first_sub(N.with_inventory(0, [], keep=True)(body), b'DOFT') == struct.pack('<I', 9)
    assert first_sub(N.with_inventory(0, [])(body), b'DOFT') is None
