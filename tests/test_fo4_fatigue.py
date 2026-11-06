"""FO3/FNV Fatigue on Fallout 4: a helper actor value whose default is an average NPC's, read as is and written
through TES4Polyfill.ChangeFatigue, which knocks the actor out. Night Eye plays Night Person's night vision; an actor
value Fallout 4 lacks is dropped.

See: docs/fork/fo4_pipeline.md#fatigue
See: docs/fork/fo4_pipeline.md#night-eye
See: docs/fork/fo4_pipeline.md#const-properties
"""

import struct

import pytest

from fo4_import import helpers_plugin as H
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from tes5_import.base.tes5_reader import subrecords

#: Orris's thug getting up (VFSOrrisScript), a gas knockout, and VMQ03a's sniper check, in one script.
SOURCE = ('scn T\nbegin OnLoad\n  forceav fatigue -310\n  setav fatigue 280\n  forceav fatigue -1\n'
          '  damageav fatigue 10000\n  restoreav fatigue 99999\n  if getav fatigue < 5\n    modav fatigue 3\n'
          '  endif\nend\n')


@pytest.fixture
def fallout4(monkeypatch):
    """Emit Fallout 4 Papyrus for the test."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)


def test_fatigue_writes_go_through_the_polyfill_and_reads_stay_plain(fallout4):
    """Each write names its operation (ForceAV 4 keeps the base, SetAV 0 sets it); the read is GetValue."""
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', SOURCE, 'Actor', 'T')
    calls = [line.strip() for line in out.splitlines() if 'Fatigue' in line and 'Property' not in line]
    assert calls == ['TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 4, -310)',
                     'TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 0, 280)',
                     'TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 4, -1)',
                     'TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 2, 10000)',
                     'TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 3, 99999)',
                     'If GetValue(TES4AV_Fatigue) < 5',
                     'TES4Polyfill.ChangeFatigue(Self, TES4AV_Fatigue, 1, 3)']
    assert 'ActorValue Property TES4AV_Fatigue Auto' in out


def test_the_helper_fatigue_defaults_to_an_average_npcs():
    """TES4Fatigue fills by name from the helper plugin and starts at 200; the other helper values start at 0."""
    assert H.actor_value_form('Fatigue', 3) == 3 << 24 | 0x821
    defaults = {}
    for sig, rec in H.records():
        if sig == 'AVIF':
            subs = dict(subrecords(rec[24:]))
            defaults[subs[b'EDID'].rstrip(b'\0').decode()] = struct.unpack('<f', subs[b'NAM0'])[0]
    assert defaults['TES4Fatigue'] == 200.0 and defaults['TES4Variable01'] == 0.0


def test_night_eye_is_night_vision_and_melee_damage_is_dropped(fallout4):
    """Cateye's SetAV NightEye goes to the polyfill; Rex's ModAV MeleeDamage (no Fallout 4 value) is dropped while
    its UnarmedDamage stays; neither leaves an ActorValue property no build fills."""
    src = ('scn T\nfloat x\nbegin OnLoad\n  player.setav nighteye 1\n  modav meleedamage 5\n  modav unarmeddamage 5\n'
           '  set x to getav meleedamage\nend\n')
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Actor', 'T')
    assert 'TES4Polyfill.SetNightEye(Game.GetPlayer(), 1)' in out
    low = out.lower()
    assert 'meleedamage has no fallout 4 equivalent -- write dropped' in low
    assert 'modvalue(tes4av_unarmeddamage, 5)' in low
    assert 'tes4av_meleedamage' not in low and 'tes4av_nighteye' not in low


def test_named_forms_are_const_so_a_later_fill_reaches_old_saves(fallout4):
    """A form the script names (a quest, an actor value) is Auto Const, read from the plugin on every load; the
    script's own variables stay Auto (a float at 0.0, conditional)."""
    src = ('scn T\nfloat timer\nref target\nbegin OnLoad\n  set timer to 1\n  if getav fatigue < 5\n'
           '    set target to player\n  endif\nend\n')
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Actor', 'T')
    assert 'ActorValue Property TES4AV_Fatigue Auto Const' in out
    assert 'Float Property timer = 0.0 Auto Conditional' in out
    assert any(line.startswith(('ObjectReference Property target Auto', 'Actor Property target Auto'))
               and 'Const' not in line for line in out.splitlines())
