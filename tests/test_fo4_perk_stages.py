"""Perk quest stage effects handed to the character rules, which run any the engine left undone.

See: docs/fork/fo4_pipeline.md#intense-training
"""

import re
from pathlib import Path
from types import SimpleNamespace

from fo4_import.spike import character as CH
from fo4_import.spike.perks import Perks

#: Intense Training's first two ranks as the FNV export has them (stage 0xCD65: Generic's 101).
INTENSE = {'EditorID': 'IntenseTraining', 'EffectCount': '3',
           'Effect[0].Type': 'QuestStage', 'Effect[0].Rank': '0', 'Effect[0].Quest': '000038B2', 'Effect[0].Stage': '52581',
           'Effect[1].Type': 'QuestStage', 'Effect[1].Rank': '1', 'Effect[1].Quest': '000038B2', 'Effect[1].Stage': '52582',
           'Effect[2].Type': 'QuestStage', 'Effect[2].Rank': '1', 'Effect[2].Quest': '00ABCDEF', 'Effect[2].Stage': '10'}
GENERIC = 0x030038B2
RULES = Path(__file__).resolve().parents[1] / 'script_convert/static_scripts/fallout4/F3NV_CharacterRules.psc'


def _function(name: str) -> str:
    """The body of Papyrus function `name` in the character rules."""
    return re.search(rf'Function {name}\(.*?EndFunction', RULES.read_text(encoding='utf-8'), re.S).group(0)


def test_each_box_waits_until_the_pip_boy_has_closed():
    """The level-up menu lives in the Pip-Boy; a box shown while it closes never appears, so each Show() waits."""
    body = _function('AddSpecialPoints')
    assert body.index('WaitOutOfMenus()') < body.index('box.Show()') and 'While aiPoints' in body[:body.index(
        'WaitOutOfMenus()')]
    assert 'UI.IsMenuOpen("PipboyMenu")' in _function('WaitOutOfMenus')


def _perks() -> Perks:
    """Perks whose form map built only Generic."""
    perks = object.__new__(Perks)
    perks.forms, perks.stage_effects, perks.quest_names = {0x38B2: GENERIC}, [], {0x38B2: "Generic"}
    return perks


def test_each_rank_lists_its_own_stage_on_a_built_quest():
    """Rank 1 gets stage 101, rank 2 stage 102; the effect on a quest the build left out is not listed."""
    perks = _perks()
    perks._stages(INTENSE, 0, 0x100)
    perks._stages(INTENSE, 1, 0x200)
    assert perks.stage_effects == [(0x100, GENERIC, 101, "FALLOUTNV_QF_Generic"), (0x200, GENERIC, 102, "FALLOUTNV_QF_Generic")]


def test_rules_properties_are_parallel_arrays():
    """StagePerks, StageQuests and StageIndexes line up by index; none is written when no perk has a stage."""
    props = CH.stage_properties(SimpleNamespace(stage_effects=[(0x100, GENERIC, 101, "FALLOUTNV_QF_Generic"), (0x200, GENERIC, 102, "FALLOUTNV_QF_Generic")]))
    assert props == {'StagePerks': ('objects', [0x100, 0x200]), 'StageQuests': ('objects', [GENERIC, GENERIC]),
                     'StageIndexes': ('ints', [101, 102]),
                     'StageScripts': ('strings', ['FALLOUTNV_QF_Generic'] * 2)}
    assert all(not value for _, value in CH.stage_properties(SimpleNamespace(stage_effects=[])).values())
