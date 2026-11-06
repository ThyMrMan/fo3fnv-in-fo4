"""FNV engine topics built as Fallout 4 bark topics, one per subtype per quest.

See: docs/fork/fo4_pipeline.md#barks
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import barks as B
from fo4_import.spike import records as R
from fo4_import.spike import say_topics as SAY

FNV_EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
#: SNAM codes FO4 plays as its own Hello and Goodbye (say_topics builds those apart).
GREETING_CODES = {R.TOPIC_HELLO[1], R.TOPIC_GOODBYE[1]}


def _say(dials: dict, lines: list) -> SAY.SayTopics:
    """A SayTopics over FNV `dials` and quest Q's `lines`, each line built as b'I'."""
    say = SAY.SayTopics.__new__(SAY.SayTopics)
    say.dials, say.infos, say.said = dials, {'Q': lines}, set()
    say.engine = {**SAY.ENGINE_TOPICS, **B.named_barks(dials)}
    say.replies = B.replies(dials, lines, say.engine)
    say.builder = SimpleNamespace(new_id=lambda key: 0x900)
    say.info = lambda rec, form_map, owner=0, place='': b'I'
    return say


def test_each_fnv_engine_topic_becomes_its_own_fo4_subtype():
    """No two FNV engine topics share an FO4 subtype, so a quest never owns two topics of one bark subtype."""
    codes = Counter(row[1] for row in B.FNV_BARKS.values())
    assert [c for c, n in codes.items() if n > 1] == []
    assert not {c.encode() for c in codes} & GREETING_CODES
    assert not B.FNV_BARKS.keys() & {'000000D2', '000000D4'}


def test_a_bark_topic_packs_flags_category_and_subtype_as_vanilla_does():
    """DATA is flags, category, u16 subtype (vanilla Hello: 00 07 52 00)."""
    assert B.ENGINE_BARKS['000000D0'] == (struct.pack('<BBH', 0, 7, 109), b'PIRN')
    assert B.ENGINE_BARKS['000000DC'] == (bytes([0, 3, 25, 0]), b'ATCK')
    assert R.TOPIC_HELLO[0][:2] == bytes([0, 7])


def test_a_quests_bark_lines_build_a_bark_topic_in_no_branch():
    """A quest's Attack lines become one ATCK topic with no BNAM; its custom topic keeps the quest's branch."""
    dials = {'000000DC': {'EditorID': 'Attack', 'DATA.Type': '2'}, 'C1': {'EditorID': 'Talk', 'DATA.Type': '1'},
             'P1': {'EditorID': 'Player', 'DATA.Type': '0'}}
    lines = [{'ParentDIAL': d, 'FormID': f'{i:08X}'} for i, d in enumerate(('000000DC', 'C1', 'P1', '000000DC'))]
    say = _say(dials, lines)
    assert say.topics({'FormID': 'q'}) == ['000000DC', 'C1']
    branch, blobs = say.build({'FormID': 'Q', 'EditorID': 'Q'}, 0x800, {'000000DC': 0x801, 'C1': 0x802}, {})
    bark, custom = blobs
    assert b'SNAM\x04\x00ATCK' in bark and b'BNAM' not in bark and bark.count(b'I') >= 2
    assert b'SNAM\x04\x00CUST' in custom and b'BNAM' in custom and branch is not None


def test_a_quest_of_only_barks_writes_no_branch():
    """Engine topics alone need no dialogue branch."""
    say = _say({'000000EF': {'EditorID': 'Death', 'DATA.Type': '2'}},
               [{'ParentDIAL': '000000EF', 'FormID': '00000001'}])
    branch, [blob] = say.build({'FormID': 'Q', 'EditorID': 'Q'}, 0x800, {'000000EF': 0x801}, {})
    assert branch is None and b'SNAM\x04\x00DETH' in blob


def test_a_named_bark_takes_its_fo4_subtype():
    """FNV's DeathResponse, outside the reserved range, becomes the quest's AllyKilled topic (category 3, 36)."""
    dials = {'0001FB51': {'EditorID': 'DeathResponse', 'DATA.Type': '2'}}
    say = _say(dials, [{'ParentDIAL': '0001FB51', 'FormID': '00000001'}])
    assert say.topics({'FormID': 'q'}) == ['0001FB51']
    branch, [blob] = say.build({'FormID': 'Q', 'EditorID': 'Q'}, 0x800, {'0001FB51': 0x801}, {})
    assert branch is None and b'SNAM\x04\x00ALKL' in blob and bytes([0, 3, 36, 0]) in blob
    assert {row[0] for row in B.NAMED_BARKS.values()}.isdisjoint(row[1] for row in B.FNV_BARKS.values())


def test_a_reply_joins_each_bark_that_chooses_it():
    """StartCombatResponse, chosen by NormalToCombat and AlertToCombat lines, has no FO4 subtype: its lines follow
    each trigger's own in that trigger's topic, and it builds no topic of its own."""
    dials = {'000000EE': {'EditorID': 'NormalToCombat', 'DATA.Type': '4'},
             '000000F3': {'EditorID': 'AlertToCombat', 'DATA.Type': '4'},
             '00080D81': {'EditorID': 'StartCombatResponse', 'DATA.Type': '4'}}
    lines = [{'ParentDIAL': '000000EE', 'FormID': '00000001', 'ChoiceCount': '1', 'Choice[0]': '00080D81'},
             {'ParentDIAL': '000000F3', 'FormID': '00000002', 'ChoiceCount': '1', 'Choice[0]': '00080D81'},
             {'ParentDIAL': '00080D81', 'FormID': '00000003'}]
    say = _say(dials, lines)
    assert say.replies == {'00080D81': ('000000EE', '000000F3')}
    assert say.topics({'FormID': 'q'}) == ['000000EE', '000000F3']
    assert [r['FormID'] for r in say._lines({'FormID': 'q'}, '000000EE')] == ['00000001', '00000003']
    only_reply = _say(dials, lines[2:])
    only_reply.replies = say.replies
    assert only_reply.topics({'FormID': 'q'}) == ['000000EE', '000000F3']


@pytest.mark.skipif(not (FNV_EXPORT / 'DIAL.txt').is_file(), reason='no FalloutNV.esm export')
def test_the_bark_table_names_fnvs_own_engine_topics():
    """Each FNV_BARKS FormID is the FNV engine topic its row names."""
    edids = {r['FormID'].upper(): r.get('EditorID') for r in export_records(FNV_EXPORT, 'DIAL')}
    assert {fid: row[0] for fid, row in B.FNV_BARKS.items() if edids.get(fid) != row[0]} == {}
