"""FO3/FNV hit points, fists and bites on converted FO4 actors: with_health, with_fists, with_stats."""

import struct

from fo4_import.spike.actor_data import (AUTO_CALC, HEALTH, PC_LEVEL_MULT, UNARMED_DAMAGE, StatTables, added_health,
                                         fist_damage)
from fo4_import.spike.creatures import BASE_DAMAGE_AT, _base_damage, with_stats
from fo4_import.spike.npcs import with_fists, with_health
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: FO3's NPC health settings (Fallout3.exe's offset and Endurance mult, Fallout3.esm's level mult).
SETTINGS = {'fAVDNPCHealthEnduranceOffset': -1.0, 'fAVDNPCHealthEnduranceMult': 5.0, 'fAVDNPCHealthLevelMult': 5.0}
HUMAN_RACE, ROACH_RACE, CITIZEN = 0x13746, 0x4716C, 0x1326B
#: HumanRace's and Citizen's Health 40 and 60, RadRoachRace's 3; UnarmedRadRoach's base damage 2.
TABLES = StatTables({HUMAN_RACE: 40.0, CITIZEN: 60.0, ROACH_RACE: 3.0}, {ROACH_RACE: 2})
#: FO3's Officer Kendall in CG04: Base Health 10, Endurance 6, level 2.
KENDALL = {'DATA.BaseHealth': '10', 'DATA.Endurance': '6', 'ACBS.Level': '2', 'ACBS.Flags': '0'}
#: FO3's radroach: Health 10, AttackDamage 3, Endurance 1.
ROACH = {'DATA.Health': '10', 'DATA.AttackDamage': '3', 'DATA.Endurance': '1'}
#: Fallout3.esm's unarmed GMSTs over FalloutNV.exe's fUnarmedDamageMult.
FISTS = {'fAVDUnarmedDamageBase': 0.5, 'fAVDUnarmedDamageMult': 0.05, 'fUnarmedDamageMult': 0.5,
         'fDamageSkillMult': 0.5}


def npc(race: int, level: int = 1, prps: dict = None, flags: int = 0, cls: int = 0) -> bytes:
    """NPC_ subrecords on `race` (and class `cls`) at `level` with ACBS `flags`, PRPS `prps` when given, AIDT."""
    out = pack_subrecord('ACBS', struct.pack('<IhH', flags, 0, level) + bytes(12))
    out += pack_subrecord('RNAM', struct.pack('<I', race))
    if prps is not None:
        out += pack_subrecord('PRPS', b''.join(struct.pack('<If', av, v) for av, v in prps.items()))
    out += pack_subrecord('AIDT', bytes(24))
    return out + (pack_subrecord('CNAM', struct.pack('<I', cls)) if cls else b'')


def prps(subs: bytes) -> dict:
    """The PRPS pairs of subrecords `subs`."""
    data = dict(subrecords(subs))[b'PRPS']
    return dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8))


def test_fo4_adds_race_and_class_to_a_fixed_npc():
    """Fixed level: race + class (Kendall's clone: 40 + 60, the 100 the harness saw)."""
    assert added_health(npc(HUMAN_RACE, 2, cls=CITIZEN), TABLES) == 100.0


def test_fo4_adds_race_and_level_to_an_auto_calc_npc():
    """Auto-calc: race + 5 a level past 1; none at PC Level Mult."""
    assert added_health(npc(HUMAN_RACE, 6, flags=AUTO_CALC, cls=CITIZEN), TABLES) == 65.0
    assert added_health(npc(HUMAN_RACE, 1000, flags=AUTO_CALC | PC_LEVEL_MULT), TABLES) == 40.0


def test_kendall_has_fo3_health():
    """FO3's 40 hit points less HumanRace's 40 and Citizen's 60; other values kept."""
    body = npc(HUMAN_RACE, 2, {0x2C2: 0.0, HEALTH: 100.0}, cls=CITIZEN)
    assert prps(with_health(KENDALL, SETTINGS, TABLES)(body)) == {0x2C2: 0.0, HEALTH: -60.0}


def test_health_adds_prps_before_aidt_when_the_body_has_none():
    """Base Health 100 gives 130 - 40 (no class); PRPS goes before AIDT."""
    out = with_health({**KENDALL, 'DATA.BaseHealth': '100'}, SETTINGS, TABLES)(npc(HUMAN_RACE, 2))
    assert prps(out) == {HEALTH: 90.0}
    assert [tag for tag, _ in subrecords(out)] == [b'ACBS', b'RNAM', b'PRPS', b'AIDT']


def test_a_corpse_has_no_health():
    """Base Health 0 (a corpse) cancels the race's health."""
    out = with_health({**KENDALL, 'DATA.BaseHealth': '0'}, SETTINGS, TABLES)(npc(HUMAN_RACE, 2, {}))
    assert prps(out) == {HEALTH: -40.0}


def test_radroach_bites_for_fo3_damage():
    """Auto-calc RadRoachRace adds Health 3 and its weapon's damage 2."""
    out = with_stats(ROACH, TABLES)(npc(ROACH_RACE, 1, {0x2C4: 8.0}, AUTO_CALC))
    assert prps(out) == {0x2C4: 1.0, HEALTH: 7.0, UNARMED_DAMAGE: 1.0}


def test_a_fixed_stand_in_gets_no_level_bonus():
    """A fixed level 3 stand-in: race only; no weapon, FO3's bite."""
    rec = {'DATA.Health': '60', 'DATA.AttackDamage': '10'}
    out = with_stats(rec, StatTables({ROACH_RACE: 30.0}, {}))(npc(ROACH_RACE, 3, {}))
    assert prps(out) == {HEALTH: 30.0, UNARMED_DAMAGE: 10.0}


def test_weapon_base_damage_offset():
    """Damage - Base is the u16 at WEAP DNAM offset 67 (xEdit)."""
    dnam = bytearray(132)
    struct.pack_into('<H', dnam, BASE_DAMAGE_AT, 2)
    assert _base_damage(pack_subrecord('DNAM', bytes(dnam))) == 2
    assert _base_damage(b'') == 0


def test_fo3_fist_damage():
    """0.25 + 0.03 x Unarmed: 0.73 for the Vault 101 officers (16), 3.25 at 100."""
    assert round(fist_damage(16, FISTS), 4) == 0.73
    assert round(fist_damage(100, FISTS), 4) == 3.25


def test_npc_fists_hit_as_fo3():
    """Own UnarmedDamage: the FO3 hit less UnarmedHuman's base 8; Health kept."""
    out = with_fists(16, FISTS, StatTables({}, {HUMAN_RACE: 8}))(npc(HUMAN_RACE, 2, {HEALTH: -60.0}))
    assert {av: round(v, 4) for av, v in prps(out).items()} == {HEALTH: -60.0, UNARMED_DAMAGE: -7.27}
