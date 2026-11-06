"""Dialogue trace points: Goodbye line ends, menu choice lines and each dialogue scene's steps.

See: docs/fork/fo4_pipeline.md#dialogue-trace
"""

import struct

from fo4_import.spike import records as R
from fo4_import.spike.dialogue_trace import CHOICE_SCRIPT, SCENE_SCRIPT, TRACED_PHASES, scene_vmad
from script_convert import trace_points
from script_convert.target import FALLOUT4, TARGET_ENV
from tes5_import.base.tes5_reader import subrecords


def _wstring(data: bytes, pos: int) -> tuple:
    """(text, position after) of a u16-length string."""
    n = struct.unpack_from('<H', data, pos)[0]
    return data[pos + 2:pos + 2 + n].decode(), pos + 2 + n


def _scene_fragments(vmad: bytes) -> tuple:
    """(flags, [(script, fragment)], [(phase flag, index, unknown, script, fragment)]) of a scene VMAD with no
    plain scripts and a property-less fragment script, read as Fallout4.esm's scene VMADs are."""
    assert struct.unpack_from('<HHH', vmad, 0) == (6, 2, 0)
    flags, pos = vmad[7], 8
    _, pos = _wstring(vmad, pos)
    pos += 3
    fragments = []
    for _ in range(bin(flags).count('1')):
        script, pos = _wstring(vmad, pos + 1)
        name, pos = _wstring(vmad, pos)
        fragments.append((script, name))
    count, pos, phases = struct.unpack_from('<H', vmad, pos)[0], pos + 2, []
    for _ in range(count):
        flag, index, unknown = struct.unpack_from('<BIb', vmad, pos)
        script, pos = _wstring(vmad, pos + 6)
        name, pos = _wstring(vmad, pos)
        phases.append((flag, index, unknown, script, name))
    assert pos == len(vmad)
    return flags, fragments, phases


def test_a_dialogue_scene_traces_begin_end_and_each_phase():
    """Begin and End, then each phase's start and completion, indexes from 0 and names from 01, as vanilla's."""
    flags, fragments, phases = _scene_fragments(scene_vmad(2))
    assert flags == 3 and fragments == [(SCENE_SCRIPT, 'Fragment_Begin'), (SCENE_SCRIPT, 'Fragment_End')]
    assert phases == [(1, 0, 1, SCENE_SCRIPT, 'Fragment_Phase_01_Begin'), (2, 0, 1, SCENE_SCRIPT, 'Fragment_Phase_01_End'),
                      (1, 1, 1, SCENE_SCRIPT, 'Fragment_Phase_02_Begin'), (2, 1, 1, SCENE_SCRIPT, 'Fragment_Phase_02_End')]
    assert len(_scene_fragments(scene_vmad(60))[2]) == 2 * TRACED_PHASES


def test_the_scene_carries_its_vmad_after_its_editor_id():
    """FO4 SCEN order: EDID, VMAD, FNAM."""
    scene = R.pack_scen(0x800, 'S', 0x801, 0, [], 0, ('A', 'B'), vmad=scene_vmad(2))
    assert [tag for tag, _ in subrecords(scene[24:])][:3] == [b'EDID', b'VMAD', b'FNAM']


def test_a_goodbye_line_ends_marked(monkeypatch):
    """An FNV Goodbye line's end fragment traces `end goodbye`; its begin and other lines stay plain."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    lines = ['Function Fragment_1(ObjectReference akSpeakerRef)', 'EndFunction',
             'Function Fragment_0(ObjectReference akSpeakerRef)', 'EndFunction']
    traced = trace_points.info(lines, '000E501C', trace_points.goodbye({'DATA.Flags': '1'}))
    assert '  TES4Polyfill.TraceLine(akSpeakerRef, "000E501C", "begin")' in traced
    assert '  TES4Polyfill.TraceLine(akSpeakerRef, "000E501C", "end goodbye")' in traced
    assert not trace_points.goodbye({'DATA.Flags': '4'}) and CHOICE_SCRIPT == 'F3NV_TraceTopicInfo'
