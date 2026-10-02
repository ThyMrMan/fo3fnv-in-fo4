"""tools/live/session_report: CTDA decoding, mark parsing, result-script follow-ups and package schedules."""

import json

from tools.live.session_report import Source, _follow_ups, parse_marks, schedule_fits


def _source(tmp_path) -> Source:
    """A Source over a one-quest, one-ref export."""
    (tmp_path / 'QUST.txt').write_text('---RECORD_BEGIN---\nSignature=QUST\nFormID=00014E9E\nEditorID=MS11\n',
                                       encoding='utf-8')
    (tmp_path / 'ACHR.txt').write_text('---RECORD_BEGIN---\nSignature=ACHR\nFormID=00014F77\nEditorID=MisterBurkeRef\n',
                                       encoding='utf-8')
    return Source(tmp_path, fallout=True)


def test_condition_decodes_both_ctda_sizes(tmp_path):
    """A 28-byte GetStage names its quest and session stage; a 28-byte GetDead names its reference."""
    src = _source(tmp_path)
    get_stage = '80000000000020423a0000009e4e0100000000000000000000000000'
    assert src.condition(get_stage, {0x14E9E: [10]}) == 'GetStage MS11 < 40 (this session: MS11 reached 10)'
    get_dead = '000000000000803f2e000000000000000000000002000000774f0100'
    assert src.condition(get_dead) == 'MisterBurkeRef.GetDead == 1'
    assert src.condition('000000000000803f3a0000009e4e010000000000') == 'GetStage MS11 == 1'


def test_parse_marks_groups_one_burst(tmp_path):
    """Player, aim and actor lines of one mark land in one entry; a stray line of another mark is ignored."""
    lines = ['1 player pos=1,2,3 days=2.5', '1 aim ref=20 base=7', '2 actor ref=99 base=1',
             '1 actor ref=-16777216 base=5 dist=10.0', '1 end actors=1']
    events = [{'t': '00:00:00.000', 'ms': k, 'ev': 'mark', 'text': t} for k, t in enumerate(lines)]
    events.insert(2, json.loads('{"ev": "package", "actor": "00000014"}'))
    marks = parse_marks(events)
    assert len(marks) == 1
    assert marks[0]['player']['days'] == '2.5' and marks[0]['aim']['ref'] == '20'
    assert [a['ref'] for a in marks[0]['actors']] == ['-16777216']


def test_follow_ups_marks_calls_inside_an_if():
    """SetStage and StartQuest calls are found, with whether an If encloses them."""
    script = 'setStage MSObjectives 11\\r\\nif MegatonBombRef.explodeMe == 0\\r\\n  StartQuest MS12\\r\\nendif\\r\\nMS11.setstage MS11 50'
    assert _follow_ups(script) == [('stage', 'msobjectives', 11, False), ('start', 'ms12', None, True),
                                   ('stage', 'ms11', 50, False)]


def test_schedule_fits_wraps_midnight():
    """A 22:00+4h window holds 1 a.m., not noon; an any-time package always fits."""
    night = {'PSDT.Time': '22', 'PSDT.Duration': '4'}
    assert schedule_fits(night, 1.0) and not schedule_fits(night, 12.0)
    assert schedule_fits({'PSDT.Time': '-1'}, 12.0)
