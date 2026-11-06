"""FNV weapon on-hit scripts on Fallout 4: converted as effect scripts, run by the weapon's enchantment.

See: docs/fork/fo4_pipeline.md#weapon-hits
"""

from types import SimpleNamespace

from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from script_convert.weapon_hits import EFFECT, as_effect

#: FNV's BoxingTapeFatigueOnHitScript, as the export has it.
TAPE = ('scn BoxingTapeFatigueOnHitScript\nBegin OnHit\n\tRef BoxingTapeTarget\n\tSet BoxingTapeTarget to '
        'GetOwnerLastTarget\n\tIf (BoxingTapeTarget != PlayerRef)\n\t\tBoxingTapeTarget.damageav Fatigue 20\n'
        '\tElse\n\t\tBoxingTapeTarget.damageav Health 5\n\tEndIf\nEnd\n')


def _xref(sigs: set):
    """A cross-reference graph whose script is attached to records of `sigs`."""
    return SimpleNamespace(attached_signatures=lambda formid: sigs)


def test_a_weapons_on_hit_script_becomes_an_effect_on_what_it_hits(monkeypatch):
    """OnHit is the effect's start, GetOwnerLastTarget its target; the Fatigue damage lands on that target."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    extends, src = as_effect(_xref({'WEAP'}), '001489CF', TAPE, 'ObjectReference')
    assert extends == EFFECT and 'Begin ScriptEffectStart' in src and 'GetOwnerLastTarget' not in src
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, extends, 'T')
    assert 'extends ActiveMagicEffect' in out and 'Event OnEffectStart(Actor akTarget, Actor akCaster)' in out
    assert 'BoxingTapeTarget = akTarget' in out or 'BoxingTapeTarget = GetTargetActor()' in out
    assert 'RegisterForHitEvent' not in out


def test_other_scripts_and_targets_are_left_alone(monkeypatch):
    """A script also on non-weapons, one without OnHit, and any script off Fallout 4 keep their base and text."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    assert as_effect(_xref({'WEAP', 'ACTI'}), 'x', TAPE, 'ObjectReference') == ('ObjectReference', TAPE)
    plain = 'scn T\nBegin OnEquip\nEnd\n'
    assert as_effect(_xref({'WEAP'}), 'x', plain, 'ObjectReference') == ('ObjectReference', plain)
    monkeypatch.delenv(TARGET_ENV)
    assert as_effect(_xref({'WEAP'}), 'x', TAPE, 'ObjectReference') == ('ObjectReference', TAPE)
