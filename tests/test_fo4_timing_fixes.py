"""Converter fixes the progress timing audit found: Complete Quest flags, OnFire and OnActorEquip, topic unlocks.

See: docs/fork/fo4_timing_audit.md#fixes
"""
import struct

from script_convert import target
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.quest_fragments import stage_fragments
from tes5_import.dialogue.quest import quest_stage_fragments
from tes5_import.dialogue.unlocks import build_unlock_plan
from tes5_import.dialogue.unlock_prerequisites_falloutnv import waits_longer


def test_a_stage_whose_only_content_is_complete_quest_gets_a_fragment():
    """A log entry with no text and no script but the Complete Quest flag still completes the quest."""
    rec = {'StageCount': '2', 'Stage[0].Index': '10', 'Stage[0].LogCount': '1', 'Stage[0].Log[0].Flags': '0',
           'Stage[1].Index': '130', 'Stage[1].LogCount': '1', 'Stage[1].Log[0].Flags': '1'}
    assert [f[:2] + (f[4],) for f in stage_fragments(rec)] == [(130, 0, True)]
    assert quest_stage_fragments(rec) == [(130, 0)]


def fo4(monkeypatch, src: str, extends: str) -> str:
    """`src` converted for Fallout 4."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    return ScriptConverter(CrossRefGraph()).convert_standalone('T', src, extends, 'T')


def test_onfire_runs_on_the_wielders_weapon_fire(monkeypatch):
    """OnFire becomes the weaponFire animation event, registered on the wielder when equipped."""
    out = fo4(monkeypatch, 'scn T\nshort b\nbegin OnFire\n  set b to 1\nend\n', 'ObjectReference')
    assert 'Event OnAnimationEvent(ObjectReference akSource, string asEventName)' in out
    assert 'If asEventName == "weaponFire"' in out
    assert 'RegisterForAnimationEvent(akActor, "weaponFire")' in out
    assert 'UnregisterForAnimationEvent(akActor, "weaponFire")' in out


def test_an_actors_onactorequip_runs_on_item_equipped(monkeypatch):
    """An actor's OnActorEquip is OnItemEquipped, not the item's OnEquipped."""
    out = fo4(monkeypatch, 'scn T\nshort b\nbegin OnActorEquip\n  set b to 1\nend\n', 'Actor')
    assert 'Event OnItemEquipped(Form akBaseObject, ObjectReference akReference)' in out
    assert 'Event OnEquipped(' not in out


def condition(func: int, value: float, quest: int = 0x10, p2: int = 0) -> str:
    """An FNV CTDA's hex: `func` on quest `quest` (parameter 2 `p2`) == `value`."""
    return struct.pack('<B3xfH2xIIII', 0, value, func, quest, p2, 0, 0).hex()


def info(fid: str, dial: str, conds=(), adds=()) -> dict:
    """An FNV INFO export record."""
    rec = {'FormID': fid, 'ParentDIAL': dial, 'ConditionCount': str(len(conds))}
    rec.update({f'Condition[{i}].Raw': c for i, c in enumerate(conds)})
    rec.update({f'AddTopic[{i}]': a for i, a in enumerate(adds)})
    return rec


def plan(greeting_conds, top_level=False) -> set:
    """The gated topics when a GREETING line with `greeting_conds` adds topic T, whose line needs nothing."""
    dials = [{'FormID': '00000100', 'EditorID': 'GREETING', 'DATA.Type': '0', 'DATA.Flags': '0'},
             {'FormID': '00000200', 'EditorID': 'T', 'FULL': 'Ask', 'DATA.Type': '0',
              'DATA.Flags': '2' if top_level else '0'}]
    infos = [info('00001000', '00000100', greeting_conds, ['00000200']), info('00002000', '00000200')]
    return set(build_unlock_plan({'DIAL': dials, 'INFO': infos, 'QUST': [], 'SCPT': []})['gated'].values())


def test_a_topic_a_greeting_reveals_only_after_an_objective_stays_gated():
    """The VMS49 vagrant: his greeting needs objective 50 shown, so the topic waits for it; a plain greeting
    reveals on first talk, so its topic is ungated; a Top-level topic is never gated."""
    shown = condition(421, 1.0, p2=50)
    assert plan([shown]) == {'TES4Unlock_T'}
    assert plan([]) == set()
    assert plan([shown], top_level=True) == set()
    assert not waits_longer([info('1', '2', [shown])], [info('3', '4', [shown])])
