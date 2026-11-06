"""The properties audit: one finding per unfilled script property, an error when a timed pass or a converter
helper needs it.

See: docs/fork/fo4_preflight.md#script-properties
"""

from tools.validate.preflight import script_props as P

QUEST = '''ScriptName FALLOUTNV_Quest extends Quest
ActorBase Property TunnelerBrute Auto
Sound Property Stinger Auto
Faction Property TES4ConfidenceFaction Auto

Event OnTimer(int aiTimerID)
  If (TunnelerBrute.GetDeadCount() == 2)
    StartTimer(TES4_Delay)
  EndIf
EndEvent

Function Ending()
  Stinger.Play(Game.GetPlayer())
EndFunction
'''


def test_a_timed_pass_or_a_helper_is_an_error_the_rest_a_review(tmp_path):
    """Used in OnTimer: timer; a TES4 name: helper; else by whether FNV has the name."""
    (tmp_path / 'FALLOUTNV_Quest.psc').write_text(QUEST, encoding='utf-8')
    unfilled = [('QuestA', 'FALLOUTNV_Quest', p) for p in ('TunnelerBrute', 'Stinger', 'TES4ConfidenceFaction')]
    unfilled += [('QuestB', 'FALLOUTNV_Quest', 'TunnelerBrute'), ('Quest', 'F3NV_Lock', 'Password')]
    found = {f.key.split('|', 2)[2]: f for f in P.unfilled_findings('Test.esm', unfilled, tmp_path, {'stinger'})}
    assert set(found) == {'timer|FALLOUTNV_Quest.TunnelerBrute', 'fnv-form|FALLOUTNV_Quest.Stinger',
                          'helper|FALLOUTNV_Quest.TES4ConfidenceFaction', 'helper|F3NV_Lock.Password'}
    timer = found['timer|FALLOUTNV_Quest.TunnelerBrute']
    assert timer.severity == 'error' and '(ActorBase)' in timer.summary and 'on 2 records' in timer.summary
    assert found['fnv-form|FALLOUTNV_Quest.Stinger'].severity == 'review'


def test_a_name_outside_the_timer_does_not_count_as_used_there():
    """timer_uses reads only the OnTimer event, as a whole word."""
    assert P.timer_uses(QUEST, 'tunnelerbrute') and not P.timer_uses(QUEST, 'Stinger')
    assert not P.timer_uses(QUEST, 'Tunneler')
