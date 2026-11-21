"""The FO3 stage sweep's error checks, as the converter now answers them: Enable/Disable on an enable child, a 3D
sound at an unloaded source, objectives the source never authored, Say GREETING's lines, the radio band, enable
parents in a holding cell.

See: docs/fork/fo4_pipeline.md#enable-children
"""
import struct
from types import SimpleNamespace

from fo4_import.spike import named_refs as NR
from fo4_import.spike import radio as RA
from fo4_import.spike import say_topics as SAY
from script_convert import target
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.quest_fragments import quest_fragment_psc, stage_fragments


def export_file(folder, sig: str, records: list) -> None:
    """Writes `records` (each its KEY=VALUE lines) as `folder`/`sig`.txt."""
    text = ''.join('---RECORD_BEGIN---\nSignature=%s\n%s\n---RECORD_END---\n' % (sig, '\n'.join(lines))
                   for lines in records)
    (folder / f'{sig}.txt').write_text(text, encoding='utf-8')


def graph(tmp_path) -> CrossRefGraph:
    """An FO3 export (it holds a TERM) placing Child (with an enable parent), Free (without) and Marker."""
    export_file(tmp_path, 'SCPT', [['FormID=00000800', 'EditorID=T', 'SCHR.Type=1']])
    export_file(tmp_path, 'TERM', [['FormID=00000700', 'EditorID=Terminal']])
    export_file(tmp_path, 'SOUN', [['FormID=00000600', 'EditorID=Boom']])
    export_file(tmp_path, 'REFR', [
        ['FormID=00000A00', 'EditorID=Child', 'NAME=0000003B', 'XESP.Reference=00000A02'],
        ['FormID=00000A01', 'EditorID=Free', 'NAME=0000003B'],
        ['FormID=00000A02', 'EditorID=Marker', 'NAME=0000003B']])
    xref = CrossRefGraph()
    xref.load_from_export(str(tmp_path), workers=1)
    return xref


def converted(monkeypatch, tmp_path, body: str) -> str:
    """Quest script T with `body` in a GameMode block, converted for Fallout 4."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    source = f'scn T\nbegin GameMode\n{body}\nend\n'
    return ScriptConverter(graph(tmp_path)).convert_standalone('T', source, 'Quest', 'T')


def test_enable_and_disable_on_an_enable_child_do_nothing(monkeypatch, tmp_path):
    """FO3 ignores both on an enable child (GECK); a free one still switches."""
    out = converted(monkeypatch, tmp_path, '  Child.Enable\n  Child.Disable\n  Free.Enable')
    assert 'Child.Enable()' not in out and 'Child.Disable()' not in out and 'its enable parent sets its state' in out
    assert 'Free.Enable()' in out


def test_a_3d_sound_plays_only_at_a_loaded_source(monkeypatch, tmp_path):
    """PlaySound3D waits on its source's 3D: FO3 played nothing unloaded."""
    out = converted(monkeypatch, tmp_path, '  Marker.PlaySound3D Boom')
    assert 'If Marker.Is3DLoaded()' in out and 'Boom.Play(Marker)' in out


def test_a_bare_3d_sound_in_a_quest_script_has_no_guard(monkeypatch, tmp_path):
    """A quest has no 3D: a bare PlaySound3D (played at None) keeps no Is3DLoaded."""
    out = converted(monkeypatch, tmp_path, '  PlaySound3D Boom')
    assert 'Boom.Play(None)' in out and 'Is3DLoaded' not in out


def test_a_fallout_quest_without_objectives_displays_none(monkeypatch, tmp_path):
    """FO3's stage log text is a designer's note, not an objective: no SetObjectiveDisplayed for Fallout 4."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    rec = {'EditorID': 'MS11Fin', 'StageCount': '1', 'Stage[0].Index': '1', 'Stage[0].LogCount': '1',
           'Stage[0].Log[0].Flags': '0', 'Stage[0].Log[0].Text': 'This repeatable stage adds notes.',
           'Stage[0].Log[0].ResultScript': 'set Q.x to 1'}
    psc = quest_fragment_psc(rec, 'MS11Fin', graph(tmp_path), stage_fragments(rec), {})[1]
    assert 'Function Fragment_Stage_0001_Item_0()' in psc and 'SetObjectiveDisplayed' not in psc


def is_id(base: int, value: float = 1.0) -> str:
    """One raw FNV condition GetIsID(`base`) == `value`."""
    return struct.pack('<B3xfIIIII', 0, value, RA.GET_IS_ID, base, 0, 0, 0).hex()


def test_say_greeting_plays_the_lines_naming_its_speaker(tmp_path):
    """Only GREETING lines whose GetIsID == 1 names a base a script's Say GREETING speaker places are its lines."""
    export_file(tmp_path, 'REFR', [['FormID=00000A00', 'EditorID=AndyREF', 'NAME=00000B00']])
    texts = ['TES4Polyfill.SayWhenFree(AndyREF, Greeting, Player)']
    lines = [{'FormID': f'00000C0{n}', 'Condition[0].Raw': raw}
             for n, raw in enumerate([is_id(0xB00), is_id(0xB00, 0.0), is_id(0xB01)])]
    assert [r['FormID'] for r in SAY.said_greetings(tmp_path, texts, lines)] == ['00000C00']


def test_the_radio_band_opens_once_past_its_top():
    """A station past 110 writes fPipboyRadioMaxFrequency 116 once; one inside the band writes nothing."""
    added = []
    writer = SimpleNamespace(add_record=lambda sig, data: added.append((sig, data)))
    radio = SimpleNamespace(made=set(), builder=SimpleNamespace(writer=writer, new_id=lambda key: 0x123,
                                                                counts={'radio band opened': 0}))
    for frequency in (96.0, 110.5, 112.0):
        RA.Radio._open_band(radio, frequency)
    assert len(added) == 1 and RA.TOP_SETTING.encode() in added[0][1]
    assert struct.pack('<f', RA.OPENED_TOP) in added[0][1]


def test_a_holding_cells_marker_enabling_a_built_reference_is_placed(tmp_path):
    """An XMarker outside the build that enables a built reference goes into the persistent cell, persistent."""
    export_file(tmp_path, 'REFR', [
        ['FormID=00000A02', 'EditorID=CampMarker', 'NAME=0000003B', 'ParentCELL=00000D00', 'RecordFlags=2048'],
        ['FormID=00000A03', 'EditorID=Npc', 'NAME=00000B00', 'ParentCELL=00000D00', 'RecordFlags=0']])
    built = [{'FormID': '00000A00', 'XESP.Reference': '00000A02'}, {'FormID': '00000A01', 'XESP.Reference': '00000A03'}]
    out = NR.enable_parents(tmp_path, built, '00000E00', {'00000A00', '00000A01'})
    assert [(r['FormID'], r['ParentCELL'], int(r['RecordFlags'])) for r in out] == [('00000A02', '00000E00', 0xC00)]
