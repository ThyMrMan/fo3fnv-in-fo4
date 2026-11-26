"""fo4_import.spike.replacements: categories, layers and origins, rules, missing plugins, masters."""

import json
import struct

import pytest

from fo4_import.spike import replacements as RP
from fo4_import.nif import headgear
from fo4_import.spike.equipment import accessory_slots, default_entry


def _layer(path, data: dict):
    """Write a table layer `data` to `path`; the path."""
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_defaults_hold_every_rule():
    """The defaults carry the creature, body, armor and melee rules the converter used to hard-code."""
    table = RP.load()
    for folder in ('creatures\\nvgecko', 'creatures\\nightstalker'):
        assert table.rules.creature[folder] == RP.Replacement(
            RP.BASE, 'EncMolerat01Template', 'rig', (), 'creature', 'default')
    assert table.rules.creature['creatures\\dog'].mode == 'fnv'
    assert table.rules.creature['creatures\\smspinebreaker'] == RP.Replacement(
        RP.BASE, 'EncSuperMutantTemplate', 'fnv', (), 'creature', 'default')
    assert {k: e.edid for k, e in table.rules.body.items()} == {
        'human_male': 'DocWeathers', 'human_female': 'DoctorAmari', 'ghoul_male': 'Jones', 'ghoul_female': 'Holly',
        'child_male': 'DiamondCitySchoolChildM03', 'child_female': 'DiamondCitySchoolChildF01'}
    assert [(bits, e.edid) for bits, e in table.rules.armor] == [
        (0x4, 'ClothesPrewarShortSleeves'), (0x1 | 0x200 | 0x400, 'ClothesMobsterhat'), (0x800, 'ClothesEyeGlasses'),
        (0x4000 | 0x10000, 'Clothes_Raider_SurgicalMask'), (0x100 | 0x8000, 'ClothesEyeGlasses'),
        (0x2, 'ClothesMobsterhat'), (0x80 | 0x40 | 0x20 | 0xE0000 | 0x1000 | 0x2000, 'ClothesEyeGlasses'),
        (0x8 | 0x10, 'Armor_WeddingRing')]
    assert {k: (e.edid, e.mode) for k, e in table.rules.weapon.items()} == {
        0: ('Knuckles', 'stats'), 1: ('TireIron', 'fnv'), 2: ('BaseballBat', 'fnv'), 3: ('10mm', 'stats'),
        4: ('LaserGun', 'stats'), 5: ('HuntingRifle', 'stats'), 6: ('AssaultRifle', 'stats'),
        7: ('LaserGun', 'stats'), 8: ('Flamer', 'stats'), 9: ('MissileLauncher', 'stats'),
        10: ('fragGrenade', 'stats'), 11: ('fragMine', 'stats'), 12: ('fragMine', 'stats'), 13: ('fragGrenade', 'fnv')}
    assert table['Stimpak'].category == 'consumable' and table['WeapKnife'].category == 'weapon'


def test_every_biped_slot_has_an_armor_rule():
    """Each FNV biped slot alone finds a default armor rule (equipment.default_entry)."""
    rules = RP.load().rules
    for name, bit in RP.BIPED.items():
        assert default_entry({'Signature': 'ARMO', 'BMDT.BipedFlags': str(bit)}, rules), name


def test_an_accessory_takes_its_own_fo4_slot():
    """Gloves on the ring slot, Pip-Boy and back items on FO4's unnamed slots, face jewelry on 59; a piece with any
    other slot is no accessory, and headgear does not take face jewelry beside other head slots."""
    assert [accessory_slots(f) for f in (0x8 | 0x10, 0x40, 0x80, 0x100 | 0x80, 0x1000, 0x2000 | 0x20)] == [
        (51,), (55,), (54,), (50, 54), (59,), (58, 59)]
    assert accessory_slots(0) is None and accessory_slots(0x4 | 0x8) is None and accessory_slots(0x400 | 0x1000) is None
    assert headgear.slots(0x1000) is None and headgear.slots(0x4000 | 0x1000) is None


def test_profile_then_user_with_origins(tmp_path):
    """A profile lies over the defaults, the user's file over both; each entry records its layer."""
    profile = _layer(tmp_path / 'look.json', {
        'weapon': {'WeapKnife': {'use': 'Fallout4.esm|CombatKnife', 'as': 'stats'}},
        '_rules': {'creature': {'creatures\\NVGecko': {'use': 'Fallout4.esm|EncMolerat01Template', 'as': 'stats'}}}})
    user = _layer(tmp_path / 'mine.json', {
        'weapon': {'WeapKnife': {'use': 'Fallout4.esm|Knife', 'as': 'fnv'}},
        'creature': {'GeckoGolden': {'use': 'Fallout4.esm|EncMolerat02', 'as': 'item'}}})
    table = RP.load(user, profile)
    assert (table['WeapKnife'].mode, table['WeapKnife'].origin) == ('fnv', 'user')
    assert table.rules.creature['creatures\\nvgecko'].edid == 'EncMolerat01Template'
    assert table.rules.creature['creatures\\nvgecko'].origin == 'profile'
    assert table.creatures['GeckoGolden'].origin == 'user'
    assert table['Stimpak'].origin == 'default'


def test_missing_plugin_falls_back_with_a_warning(tmp_path):
    """An entry naming a plugin that is not installed is dropped, so the layer below applies."""
    user = _layer(tmp_path / 'mine.json', {'weapon': {'WeapKnife': {'use': 'Gone.esp|Knife', 'as': 'item'}}})
    table = RP.load(user)
    assert table['WeapKnife'] == RP.load()['WeapKnife']
    assert len(table.warnings) == 1 and 'Gone.esp' in table.warnings[0]


def test_profile_requirements_warn(tmp_path):
    """A profile's missing required plugin is reported."""
    profile = _layer(tmp_path / 'p.json', {'_profile': {'name': 'P', 'requires': [{'plugin': 'Port.esp',
                                                                                     'nexus_id': 1}]}})
    assert any('Port.esp' in w for w in RP.load(profile=profile).warnings)


def test_unknown_profile_name():
    """A profile name with no file is an error naming the known ones."""
    with pytest.raises(FileNotFoundError):
        RP.load(profile='no-such-profile')


def _plugin(path, *masters):
    """Write a plugin at `path` holding only a file header naming `masters`; the path."""
    body = b''.join(b'MAST' + struct.pack('<H', len(m) + 1) + m.encode() + b'\0' + b'DATA\x08\x00' + bytes(8)
                    for m in masters)
    path.write_bytes(b'TES4' + struct.pack('<I', len(body)) + bytes(16) + body)
    return path


def test_a_plugin_whose_master_is_missing_counts_as_not_installed(tmp_path):
    """NVUMP.esp names a Creation Club file that is not installed: its entries fall back, and it is no master."""
    _plugin(tmp_path / 'Mod.esp', 'Fallout4.esm', 'Gone.esl')
    _plugin(tmp_path / 'Fine.esp', 'Fallout4.esm', 'Base.esl')
    _plugin(tmp_path / 'Base.esl', 'Fallout4.esm')
    user = _layer(tmp_path / 'mine.json', {'weapon': {'WeapKnife': {'use': 'Mod.esp|Knife', 'as': 'item'},
                                                      'Weap10mmPistol': {'use': 'Fine.esp|Gun', 'as': 'item'}}})
    table = RP.load(user, dirs=(tmp_path,))
    assert table['WeapKnife'] == RP.load()['WeapKnife'] and table['Weap10mmPistol'].plugin == 'Fine.esp'
    assert RP.extra_masters(table) == ['Fine.esp'] and len(table.warnings) == 1


def test_dlc_masters_come_first(tmp_path):
    """DLC targets become masters before mods', in the game's order; any case finds the plugin."""
    for name in ('dlccoast.esm', 'DLCRobot.esm', 'Aaa.esp'):
        _plugin(tmp_path / name, 'Fallout4.esm')
    user = _layer(tmp_path / 'mine.json', {
        'weapon': {'A': {'use': 'Aaa.esp|X', 'as': 'item'}, 'B': {'use': 'DLCCoast.esm|Y', 'as': 'item'}},
        'creature': {'C': {'use': 'DLCRobot.esm|Z', 'as': 'item'}}})
    assert RP.extra_masters(RP.load(user, dirs=(tmp_path,))) == ['DLCRobot.esm', 'DLCCoast.esm', 'Aaa.esp']


def test_an_old_melee_rule_is_read_as_a_weapon_rule(tmp_path):
    """An older layer's `_rules.melee` sets the weapon rule, warned DEPRECATED."""
    old = {'_rules': {'melee': {'one_hand': {'use': 'Fallout4.esm|Knife', 'as': 'stats'}}}}
    table = RP.load(_layer(tmp_path / 'mine.json', old))
    assert table.rules.weapon[1].edid == 'Knife' and any('DEPRECATED' in w for w in table.warnings)


def test_bad_rules_refused(tmp_path):
    """Unknown biped slots, weapon keys or body kinds, and a body from another plugin, are refused."""
    for rules in ({'armor': [{'covers': ['Tail'], 'use': 'Fallout4.esm|X', 'as': 'fnv'}]},
                  {'weapon': {'sword': {'use': 'Fallout4.esm|X', 'as': 'stats'}}},
                  {'body': {'robot': {'use': 'Fallout4.esm|X'}}},
                  {'body': {'human_male': {'use': 'Other.esp|X'}}}):
        with pytest.raises(ValueError):
            RP.load(_layer(tmp_path / 'mine.json', {'_rules': rules}))


def test_table_of_keeps_default_rules():
    """Table.of gives exactly the items asked for with the default rules."""
    table = RP.Table.of({'X': RP.Replacement(RP.BASE, 'Knife', 'stats')})
    assert list(table) == ['X'] and table.rules.weapon[0].edid == 'Knuckles'


def test_creature_entry_order():
    """A creature takes the table's entry, else its first ability rule, else its skeleton folder's."""
    table = RP.load()
    glow = {'EditorID': 'GlowX', 'SpellCount': '2', 'Spell[0]': '00000001', 'Spell[1]': '00000002'}
    spells = {1: 'GhoulRadHeal', 2: 'GlowingOneGlowSpell'}
    entry, key, how = RP.creature_entry(table, glow, 'creatures\ghoul', spells)
    assert (entry.edid, key, how) == ('encFeralGhoulGlowing01', 'glowingoneglowspell', 'rule')
    plain = {'EditorID': 'FeralX', 'SpellCount': '1', 'Spell[0]': '00000001'}
    assert RP.creature_entry(table, plain, 'creatures\ghoul', spells)[0].edid == 'encFeralGhoul01Template'
    assert RP.creature_entry(table, plain, 'creatures\spore', spells) == (None, '', 'none')
