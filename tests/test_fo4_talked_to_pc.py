"""FNV GetTalkedToPC on Fallout 4: the helper actor value a GREETING line's begin sets.

See: docs/fork/fo4_pipeline.md#talked-to-pc
"""

import struct

from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike.say_topics import actor_values, conditions_of
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.talked_to_pc import greeted
from script_convert.target import FALLOUT4, TARGET_ENV

#: FNV `GetTalkedToPC == 0` run on the subject (28-byte CTDA).
FIRST_MEETING = struct.pack('<B3xfIIIII', 0, 0.0, C.FNV.index('GetTalkedToPC'), 0, 0, 0, 0).hex()


def test_get_talked_to_pc_reads_the_helper_actor_value():
    """The condition becomes GetValue TalkedToPC == 0 on the same subject, not the engine's flag."""
    rec = {'ConditionCount': '1', 'Condition[0].Raw': FIRST_MEETING}
    ctda = conditions_of(rec, actor_values(1), {})
    op, value, func, p1, _, run_on = struct.unpack_from('<B3xfH2xIIi', ctda, 6)
    assert (op, value, func, run_on) == (0, 0.0, C.FO4.index('GetValue'), 0)
    assert p1 == actor_value_form('TalkedToPC', 1)


def test_a_script_reads_talked_to_pc_from_the_helper_value(monkeypatch):
    """`GetTalkedToPC == 1` in a script's guard reads TalkedToPC on the actor, not an inert term dropped from it."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = 'scn T\nshort x\nbegin GameMode\n  if AndersRef.GetTalkedToPC == 1 && x == 0\n    set x to 1\n  endif\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Quest', 'T')
    assert 'GetValue(TES4AV_TalkedToPC) != 0.0' in out and ';NE:' not in out


def test_only_a_greeting_line_marks_its_speaker(monkeypatch):
    """A GREETING line's begin calls TES4Polyfill.Greeted; another topic's line does not."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    assert greeted({'ParentDIAL': '000000C8'}) == ['  TES4Polyfill.Greeted(akSpeakerRef)']
    assert greeted({'ParentDIAL': '000000D2'}) == []
