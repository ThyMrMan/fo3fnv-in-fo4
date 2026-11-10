"""The marker census tool: one function per marker, owners from the export.

See: docs/fork/script_markers.md#measuring
"""

import pytest

from tools.audit import script_marker_census as census_tool


def _export(root):
    """A tiny FalloutNV.esm export: one quest script, one object script, one topic info."""
    root.mkdir()
    rec = '---RECORD_BEGIN---\n{}\n---RECORD_END---\n'
    (root / 'SCPT.txt').write_text(rec.format('FormID=00000A01\nEditorID=QuestScript')
                                   + rec.format('FormID=00000A02\nEditorID=DoorScript'))
    (root / 'QUST.txt').write_text(rec.format('FormID=00000B01\nEditorID=VMS01\nSCRI=00000A01'))
    (root / 'INFO.txt').write_text(rec.format('FormID=00000C01\nQSTI.Quest=00000B01'))
    (root / 'ACTI.txt').write_text(rec.format('FormID=00000D01\nEditorID=Gate\nSCRI=00000A02'))
    return root


@pytest.mark.parametrize('text, func', [
    ('IgnoreCrime 1', 'ignorecrime'),
    ('TODO: ref.GetFurnitureMarkerID == 1', 'getfurnituremarkerid'),
    ('&& (GetObjectiveDisplayed VMS01 10)', 'getobjectivedisplayed'),
    ('unreachable after Return', '(note) unreachable after Return'),
    ('Foo is not declared in Bar', '(note) undeclared var'),
    ('123', '(other)'),
])
def test_marker_function(text, func):
    """A marker's text names its function; prose notes are kept apart."""
    assert census_tool.marker_function(text) == func


def test_census_counts_owners_and_conditions(tmp_path):
    """Markers count per function with script kind, owner and condition lines."""
    owners = census_tool.Owners(_export(tmp_path / 'FalloutNV.esm'))
    psc = tmp_path / 'psc'
    psc.mkdir()
    (psc / 'FALLOUTNV_QuestScript.psc').write_text(
        'If 0 ;NE: GetFurnitureMarkerID == 1\n  ;NE: AddAchievement 3\nEndIf\n')
    (psc / 'FALLOUTNV_DoorScript.psc').write_text(';NE: IgnoreCrime 1 ;;NE: AddAchievement 2\n')
    (psc / 'FALLOUTNV_TIF__00000C01.psc').write_text(';NE: TODO: PCB\n')
    rows = {r['func']: r for r in census_tool.census(psc, owners)}
    assert rows['addachievement']['count'] == 2
    assert rows['addachievement']['kinds'] == {'quest-script': 1, 'object-script': 1}
    assert rows['addachievement']['quests'] == ['ACTI:Gate', 'VMS01']
    assert rows['getfurnituremarkerid']['conditions'] == 1
    assert rows['pcb']['kinds'] == {'topic-info': 1}
    assert census_tool.totals(list(rows.values())) == {
        'markers': 5, 'scripts': 3, 'functions': 4, 'note_markers': 0, 'condition_markers': 1}
