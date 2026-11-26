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


def test_a_crime_count_reads_the_speakers_helper_value():
    """Lucas Simms' `GetMajorCrimeCount > 1` becomes GetValue MajorCrimes > 1 on the subject, the minor count
    MinorCrimes; the line used to be left out.
    See: docs/fork/fo4_pipeline.md#crime-counts
    """
    for func, name in (('GetMajorCrimeCount', 'MajorCrimes'), ('GetMinorCrimeCount', 'MinorCrimes')):
        raw = struct.pack('<B3xfIIIII', 0x40, 1.0, C.FNV.index(func), 0, 0, 0, 0).hex()
        ctda = conditions_of({'ConditionCount': '1', 'Condition[0].Raw': raw}, actor_values(1), {})
        op, value, fo4, p1, _, run_on = struct.unpack_from('<B3xfH2xIIi', ctda, 6)
        assert (op, value, fo4, run_on, p1) == (0x40, 1.0, C.FO4.index('GetValue'), 0, actor_value_form(name, 1))


def _disposition(func: str, op: int, value: float, p1: int = 0, form_map: 'dict | None' = None) -> 'bytes | None':
    """One FNV `func` test on the subject as FO4 CTDAs, with `form_map`."""
    raw = struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, 0, 0).hex()
    return conditions_of({'ConditionCount': '1', 'Condition[0].Raw': raw}, {**actor_values(1), **(form_map or {})}, {})


def test_a_disposition_test_reads_the_speakers_kept_disposition():
    """GetDisposition toward the player or the other party reads GetValue Disposition, a global's value through
    the form map; toward another NPC it stays out. HasFriendDisposition == 1 reads Disposition at least
    GenericFriendlyDisposition (0004E613), == 0 below it.
    See: docs/fork/fo4_pipeline.md#disposition
    """
    disposition, at_least, below, use_global = actor_value_form('Disposition', 1), 0x60, 0x80, C.USE_GLOBAL
    friendly = {0x4E613: 0x0102E613}
    as_float = struct.unpack('<f', struct.pack('<I', 0x0102E613))[0]
    for p1 in (0, C.PLAYER_REF):
        ctda = _disposition('GetDisposition', at_least, 30.0, p1)
        assert struct.unpack_from('<B3xfH2xIIi', ctda, 6) == (at_least, 30.0, C.FO4.index('GetValue'), disposition, 0, 0)
    assert _disposition('GetDisposition', 0x00, 1.0, 0x1234, {0x1234: 0x01001234}) is None
    rows = [_disposition('HasFriendDisposition', 0x00, held, form_map=friendly) for held in (1.0, 0.0)]
    assert [struct.unpack_from('<B3xfH2xI', ctda, 6) for ctda in rows] == [
        (at_least | use_global, as_float, C.FO4.index('GetValue'), disposition),
        (below | use_global, as_float, C.FO4.index('GetValue'), disposition)]
    assert _disposition('HasFriendDisposition', 0x00, 1.0) is None


def test_mod_disposition_toward_the_player_moves_the_kept_disposition(monkeypatch):
    """On Fallout 4 `LucasSimmsRef.ModDisposition player -5` calls the standings quest's ModDisposition; toward
    another actor it is a note.
    See: docs/fork/fo4_pipeline.md#disposition
    """
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = 'scn T\nbegin GameMode\n  LucasSimmsRef.ModDisposition player -5\n  LucasSimmsRef.ModDisposition BobRef 5\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Quest', 'T')
    assert 'TES4Standings.ModDisposition(LucasSimmsRef, -5)' in out
    assert 'F3NV_FalloutStandings Property TES4Standings' in out
    assert out.count('ModDisposition(') == 1


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
