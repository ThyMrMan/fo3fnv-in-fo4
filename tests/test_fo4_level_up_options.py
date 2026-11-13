"""The level-up options' MCM page: the files the game build installs, and the script properties MCM writes.

See: docs/fork/fo4_level_up_plan.md#options
"""

import json
import re
from pathlib import Path

import pytest

from fo4_import import cleanroom
from fo4_import.level_up import options as O
from fo4_import.spike.character import RATES

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
#: MCM's property source types and the Papyrus type each writes.
TYPES = {'PropertyValueInt': 'Int', 'PropertyValueFloat': 'Float', 'PropertyValueBool': 'Bool'}


def _script(name: str) -> str:
    """Papyrus script `name`'s source: Cleanroom UI's for its scripts (skipped without a checkout), else ours."""
    if name not in cleanroom.SCRIPTS:
        return (STATIC / f'{name}.psc').read_text(encoding='utf-8')
    if cleanroom.checkout() is None:
        pytest.skip('no Cleanroom UI checkout')
    return cleanroom.scripts()[f'{name}.psc'].read_text(encoding='utf-8')


def _controls(plugin: str = 'FalloutNV.esm', quest: int = 0x01000801) -> list:
    """The filled page's controls."""
    return O.filled('config.json', plugin, quest)['content']


def test_install_writes_the_page_for_the_game_plugin(tmp_path):
    """config.json and keybinds.json go under MCM/Config/F3NV_<plugin>, naming the rules quest by plugin and object
    id, no placeholder left."""
    assert O.install(tmp_path, 'FalloutNV.esm', 0x00012345) == 2
    folder = tmp_path / 'MCM' / 'Config' / 'F3NV_FalloutNV'
    for name in ('config.json', 'keybinds.json'):
        text = (folder / name).read_text(encoding='utf-8')
        assert '{' + 'form}' not in text and '{' + 'mod}' not in text and 'FalloutNV.esm|12345' in text
    page = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    assert page['modName'] == 'F3NV_FalloutNV' and page['displayName'] == 'F3NV: Fallout New Vegas'


def test_each_option_is_a_settable_property_of_its_script():
    """Every property the page sets is declared, not Const, with the type its source writes, on the script named."""
    for control in _controls():
        source = control.get('valueOptions', {})
        if 'propertyName' not in source:
            continue
        script = _script(source['scriptName'])
        declared = re.search(rf'^(\w+) Property {source["propertyName"]}\b[^\n]*$', script, re.M)
        assert declared and declared.group(1) == TYPES[source['sourceType']], source['propertyName']
        assert 'Const' not in declared.group(0) and 'AutoReadOnly' not in declared.group(0), source['propertyName']


def test_each_slider_holds_both_games_values():
    """Each game's levels per perk and skill points per Intelligence (RATES), the base 10 and the cap 100 are
    values the sliders reach."""
    sliders = {c['valueOptions']['propertyName']: c['valueOptions'] for c in _controls() if c['type'] == 'slider'}
    wanted = {'LevelsPerPerk': [p for _, p in RATES.values()], 'SkillPointsPerIntelligence': [i for i, _ in
                                                                                            RATES.values()],
              'SkillPointsBase': [10], 'SkillCap': [100]}
    for name, values in wanted.items():
        slider = sliders[name]
        for value in values:
            steps = (value - slider['min']) / slider['step']
            assert slider['min'] <= value <= slider['max'] and steps == int(steps), (name, value)


def test_the_hotkey_calls_the_rules_quests_level_up_opener():
    """The keybind shares the hotkey control's id and calls a function the named script has."""
    bind = O.filled('keybinds.json', 'FalloutNV.esm', 0x801)['keybinds'][0]
    assert bind['id'] in {c.get('id') for c in _controls() if c['type'] == 'hotkey'}
    script = (STATIC / f'{bind["action"]["scriptName"]}.psc').read_text(encoding='utf-8')
    assert f'Function {bind["action"]["function"]}()' in script and bind['action']['form'] == 'FalloutNV.esm|801'
