"""FNV's V.A.T.S. AP cost and critical data: exported from WEAP, written onto the FO4 weapon copy."""

import struct
from types import SimpleNamespace

from fo4_import.spike.weapon_vats import CRDT, DNAM_AP, WeaponVats, ap_cost, critical_data
from tes4_export.record_types.falloutnv import _emit_weap_crit
from tes4_export.tes4_reader import Record, Subrecord

SETTINGS = {'fActionPointsAttackPistol': 20.0, 'fActionPointsAttackRifle': 25.0}


def test_the_export_carries_the_ap_override_and_critical_data():
    """DNAM 56 Flags2 and 68 the AP cost; CRDT damage, chance multiplier, flags and effect."""
    dnam = bytearray(72)
    struct.pack_into('<If', dnam, 56, 0x8, 0.0)
    struct.pack_into('<f', dnam, 68, 17.0)
    crdt = struct.pack('<HxxfB3xI', 16, 1.5, 1, 0xBDA30)
    rec = Record('WEAP', 0, 0, 0x1, [Subrecord('DNAM', bytes(dnam)), Subrecord('CRDT', crdt)])
    lines = []
    _emit_weap_crit(lines, rec, rec.subrecords[0])
    assert lines == ['DNAM.Flags2=8', 'DNAM.ActionPoints=17.0', 'CRDT.Damage=16', 'CRDT.ChanceMult=1.5',
                     'CRDT.Flags=1', 'CRDT.Effect=000BDA30']


def test_ap_cost_is_the_override_else_the_weapon_class_setting():
    """The flagged override, else fActionPointsAttack<class>; None unknown."""
    assert ap_cost({'DNAM.Flags2': '8', 'DNAM.ActionPoints': '17.0', 'DNAM.FalloutAnimType': '3'}, SETTINGS) == 17.0
    assert ap_cost({'DNAM.Flags2': '0', 'DNAM.ActionPoints': '17.0', 'DNAM.FalloutAnimType': '5'}, SETTINGS) == 25.0
    assert ap_cost({'DNAM.FalloutAnimType': '9'}, SETTINGS) is None


def test_critical_damage_becomes_a_multiplier_and_the_effect_follows_fnv():
    """(damage + critical damage) / damage; FNV's chance multiplier as the charge bonus; the FO4 effect kept only
    when FNV has one; no base damage keeps the multiplier; no CRDT leaves it as it was."""
    laser = CRDT.pack(2.0, 1.0, 0x1234)
    assert CRDT.unpack(critical_data({'DATA.Damage': '16', 'CRDT.Damage': '8', 'CRDT.ChanceMult': '3.0',
                                      'CRDT.Effect': '000BDA30'}, laser)) == (1.5, 3.0, 0x1234)
    assert CRDT.unpack(critical_data({'DATA.Damage': '0', 'CRDT.Damage': '0', 'CRDT.ChanceMult': '0.0',
                                      'CRDT.Effect': '00000000'}, laser)) == (2.0, 0.0, 0)
    assert critical_data({'DATA.Damage': '16'}, laser) == laser


def test_a_weapon_whose_fo4_copy_has_no_critical_effect_takes_fnvs_converted_spell():
    """No FO4 effect: FNV's converted spell (Lily's knockdown), else none."""
    rec, plain = {'DATA.Damage': '10', 'CRDT.Damage': '0', 'CRDT.Effect': '0001DEA8'}, CRDT.pack(2.0, 1.0, 0)
    assert CRDT.unpack(critical_data(rec, plain, {0x1DEA8: 0x0B000300}.get))[2] == 0x0B000300
    assert CRDT.unpack(critical_data(rec, plain))[2] == 0


def test_apply_writes_the_ap_cost_into_dnam_and_returns_the_copy_crdt(monkeypatch):
    """WeaponVats.apply fills DNAM's Action Point Cost and gives the template's CRDT with FNV's data."""
    monkeypatch.setattr('fo4_import.spike.weapon_vats.fnv_settings', lambda _: SETTINGS)
    dnam = bytearray(132)
    builder = SimpleNamespace(export_dir=None, scripts=SimpleNamespace(effects=SimpleNamespace(spell_of=dict().get)))
    crdt = WeaponVats(builder).apply({'DNAM.FalloutAnimType': '3', 'DATA.Damage': '10', 'CRDT.Damage': '10',
                                   'CRDT.ChanceMult': '1.0', 'CRDT.Effect': '00000000'}, dnam,
                                  {b'CRDT': CRDT.pack(2.0, 1.0, 0)})
    assert struct.unpack_from('<f', dnam, DNAM_AP)[0] == 20.0 and CRDT.unpack(crdt) == (2.0, 1.0, 0)
