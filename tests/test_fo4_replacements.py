"""fo4_import.spike.replacements: categories, layers and origins, rules, missing plugins, masters."""

import json

import pytest

from fo4_import.spike import replacements as RP


def _layer(path, data: dict):
    """Write a table layer `data` to `path`; the path."""
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_defaults_hold_every_rule():
    """The defaults carry the creature, body, armor and melee rules the converter used to hard-code."""
    table = RP.load()
    assert table.rules.creature['creatures\\nvgecko'] == RP.Replacement(
        RP.BASE, 'EncViciousDog01Template', 'stats', (), 'creature', 'default')
    assert table.rules.creature['creatures\\dog'].mode == 'fnv'
    assert {k: e.edid for k, e in table.rules.body.items()} == {
        'human_male': 'DocWeathers', 'human_female': 'DoctorAmari', 'ghoul_male': 'Jones', 'ghoul_female': 'Holly'}
    assert [(bits, e.edid) for bits, e in table.rules.armor] == [
        (0x4, 'ClothesPrewarShortSleeves'), (0x1 | 0x200 | 0x400, 'ClothesMobsterhat'), (0x800, 'ClothesEyeGlasses'),
        (0x4000 | 0x10000, 'Clothes_Raider_SurgicalMask')]
    assert {k: (e.edid, e.mode) for k, e in table.rules.melee.items()} == {
        0: ('Knuckles', 'stats'), 1: ('TireIron', 'fnv'), 2: ('BaseballBat', 'fnv')}
    assert table['Stimpak'].category == 'consumable' and table['WeapKnife'].category == 'weapon'


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


def test_dlc_masters_come_first(tmp_path):
    """DLC targets become masters before mods', in the game's order; any case finds the plugin."""
    for name in ('dlccoast.esm', 'DLCRobot.esm', 'Aaa.esp'):
        (tmp_path / name).write_bytes(b'')
    user = _layer(tmp_path / 'mine.json', {
        'weapon': {'A': {'use': 'Aaa.esp|X', 'as': 'item'}, 'B': {'use': 'DLCCoast.esm|Y', 'as': 'item'}},
        'creature': {'C': {'use': 'DLCRobot.esm|Z', 'as': 'item'}}})
    assert RP.extra_masters(RP.load(user, dirs=(tmp_path,))) == ['DLCRobot.esm', 'DLCCoast.esm', 'Aaa.esp']


def test_bad_rules_refused(tmp_path):
    """Unknown biped slots, melee keys or body kinds, and a body from another plugin, are refused."""
    for rules in ({'armor': [{'covers': ['Tail'], 'use': 'Fallout4.esm|X', 'as': 'fnv'}]},
                  {'melee': {'thrown': {'use': 'Fallout4.esm|X', 'as': 'stats'}}},
                  {'body': {'robot': {'use': 'Fallout4.esm|X'}}},
                  {'body': {'human_male': {'use': 'Other.esp|X'}}}):
        with pytest.raises(ValueError):
            RP.load(_layer(tmp_path / 'mine.json', {'_rules': rules}))


def test_table_of_keeps_default_rules():
    """Table.of gives exactly the items asked for with the default rules."""
    table = RP.Table.of({'X': RP.Replacement(RP.BASE, 'Knife', 'stats')})
    assert list(table) == ['X'] and table.rules.melee[0].edid == 'Knuckles'
