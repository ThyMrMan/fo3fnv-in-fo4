"""FNV patrol points run by FO4's patrol arrival topic: the PDTO, the arrival topics and their lines.

See: docs/fork/fo4_pipeline.md#patrol-points
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import patrol_topics as PT
from fo4_import.spike import placement as PL
from tes5_import.base.tes5_reader import subrecords


def test_a_patrol_point_names_its_arrival_topic_in_pdto_and_others_write_none(monkeypatch):
    """XPRD is followed by XPPA, INAM 0 and a Topic Ref PDTO: the point's arrival topic, else 0."""
    monkeypatch.setattr(PL, 'fields', lambda: {0x900: [(b'XPRD', struct.pack('<f', 4.0))],
                                               0x901: [(b'XPRD', struct.pack('<f', 1.0))]})
    kept = list(subrecords(PL.placement(0x900, {}, arrivals={0x900: 0x0300ABCD})))
    assert [t for t, _ in kept] == [b'XPRD', b'XPPA', b'INAM', b'PDTO']
    assert dict(kept)[b'PDTO'] == struct.pack('<II', 0, 0x0300ABCD)
    assert dict(subrecords(PL.placement(0x901, {})))[b'PDTO'] == bytes(8)


def _patrols(tmp_path, points: dict, placed: set, named: dict) -> tuple:
    """(PatrolTopics over `points` {FormID: export record}, [(signature, record) written]) with the points
    in `placed` built and the topics `named` {EditorID lower: FO4} known; a PM script for 0x900 only."""
    (tmp_path / 'FALLOUTNV_PM__00000900.psc').write_text('Topic Property Jokes Auto\n', encoding='utf-8')
    written = []
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x03000000 | (hash((site, key)) & 0xFFFFFF),
                             add_record=lambda sig, blob: written.append((sig, blob)))
    scripts = SimpleNamespace(dir=tmp_path, used=[], properties=lambda name: {'Jokes': 0x03000777},
                              named_lower=lambda: named)
    builder = SimpleNamespace(writer=writer, scripts=scripts, counts=Counter(),
                              ref_ids={f'{fid:08X}': fid for fid in placed},
                              say=SimpleNamespace(dials={'000005EE': {'EditorID': 'EscortHome05'}}))
    patrols = object.__new__(PT.PatrolTopics)
    patrols.builder, patrols.quest, patrols.points = builder, 0x03000100, points
    patrols.arrivals = {fid: 0x03000200 + fid for fid in points}
    return patrols, written


def test_each_built_patrol_point_gets_an_arrival_topic_running_its_script_or_saying_its_topic(tmp_path):
    """A scripted point's line runs its PM script, a topic-only point's says the topic with F3NV_PatrolSay, an
    unbuilt topic leaves a line running nothing, and a point the build does not place gets no topic."""
    points = {0x900: {'FormID': '00000900', 'Patrol.Script': 'Say Jokes'},
              0x901: {'FormID': '00000901', 'Patrol.Topic': '000005EE'},
              0x902: {'FormID': '00000902', 'Patrol.Topic': '000005EF'},
              0x903: {'FormID': '00000903', 'Patrol.Script': 'Disable'}}
    patrols, written = _patrols(tmp_path, points, {0x900, 0x901, 0x902}, {'escorthome05': 0x03000555})
    patrols.write()
    (sig, blob), = written
    assert sig == 'QUST' and b'FNV_TES4PatrolTopics\0' in blob
    for fid in (0x900, 0x901, 0x902):
        assert f'FNV_TES4PatrolTopic_{fid:08X}\0'.encode() in blob
    assert b'FNV_TES4PatrolTopic_00000903' not in blob
    assert b'FALLOUTNV_PM__00000900' in blob and b'F3NV_PatrolSay' in blob
    assert struct.pack('<I', 0x03000555) in blob and struct.pack('<I', 0x03000777) in blob
    assert patrols.builder.scripts.used == ['FALLOUTNV_PM__00000900']
    assert patrols.builder.counts['patrol arrival topics'] == 3
    assert patrols.builder.counts['patrol point with nothing to run'] == 1


def test_only_a_patrol_point_with_a_script_or_topic_acts():
    """A point whose script is only comments and that names no topic runs nothing."""
    assert PT._acts({'Patrol.IdleTime': '1.0', 'Patrol.Script': 'Say X'})
    assert PT._acts({'Patrol.IdleTime': '1.0', 'Patrol.Topic': '001517EF'})
    assert not PT._acts({'Patrol.IdleTime': '1.0', 'Patrol.Script': '; ShowWarning "done"'})
    assert not PT._acts({'Patrol.Script': 'Say X'})
