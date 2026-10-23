"""FNV voice notes as FO4 holotapes: a line's tests of its own speaker.

See: docs/fork/fo4_pipeline.md#holotapes
"""

import struct

from fo4_import.spike import conditions as C
from fo4_import.spike.holotapes import spoken_by
from fo4_import.spike.say_topics import raws

SPEAKER = {'FormID': '000D7F57', 'VTCK.Voice': '0001E5A8'}


def _raw(func: str, p1: int, value: float = 1.0, op: int = 0, run_on: int = 0) -> str:
    """One FNV condition, raw hex."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, run_on, 0).hex()


def _line(*conds: str) -> dict:
    """An FNV INFO with conditions `conds`."""
    return {'FormID': '001618B7', **{f'Condition[{i}].Raw': c for i, c in enumerate(conds)},
            'ConditionCount': str(len(conds))}


def test_a_holotape_line_drops_its_speakers_identity_tests():
    """Beagle's journal: Subject GetIsID/voice type of its speaker go, a stage test stays."""
    stage = _raw('GetStage', 0xDA115, 10.0, op=0x60)
    line = spoken_by(_line(_raw('GetIsID', 0xD7F57), _raw('GetIsVoiceType', 0x1E5A8), stage), SPEAKER)
    assert raws(line) == [stage] and line['ConditionCount'] == '1'


def test_a_holotape_line_for_another_speaker_never_plays():
    """Subject GetIsID of another NPC never passes; one on a reference is kept."""
    assert spoken_by(_line(_raw('GetIsID', 0x123456)), SPEAKER) is None
    other = _raw('GetIsID', 0x123456, run_on=2)
    assert raws(spoken_by(_line(other), SPEAKER)) == [other]


def test_an_or_group_with_the_speaker_passes_whole():
    """GetIsID other OR GetIsID speaker: the group passes, so neither is written."""
    either = _raw('GetIsID', 0x123456, op=C.OR_NEXT)
    assert raws(spoken_by(_line(either, _raw('GetIsID', 0xD7F57)), SPEAKER)) == []
