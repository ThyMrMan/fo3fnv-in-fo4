"""The Hub's topic index: each topic's lines in Hub order, and the greeting order drawn from it."""

from types import SimpleNamespace

from fo4_import.spike.conversation import GREETING, Conversations, one_each, hub


def _line(fid: str, dial: str, quest: str) -> dict:
    """An FNV INFO of topic `dial` in `quest`."""
    return {'FormID': fid, 'ParentDIAL': dial, 'QSTI.Quest': quest}


def test_topic_index_keeps_hub_order_and_greetings_sort_by_priority():
    """by_topic lists a topic's lines (any case) in Hub order; greetings come highest quest priority first, ties in
    Hub order."""
    infos = {'Q1': [_line('A1', GREETING, 'Q1'), _line('A2', '00000001', 'Q1')],
             'Q2': [_line('B1', GREETING, 'Q2'), _line('B2', GREETING.lower(), 'Q2')]}
    say = SimpleNamespace(infos=infos, dials={})
    quests = [{'FormID': 'Q1', 'EditorID': 'One', 'DATA.Priority': '10'},
              {'FormID': 'Q2', 'EditorID': 'Two', 'DATA.Priority': '50'}]
    shared = hub(say, quests, {'One': 1, 'Two': 2}, set())
    assert shared.by_topic == {GREETING: [(0, 'A1'), (2, 'B1'), (3, 'B2')], '00000001': [(1, 'A2')]}
    assert Conversations(say, quests[0], 1, {}, 0, shared)._greetings() == ['B1', 'B2', 'A1']


def test_one_each_takes_the_group_most_lines_share():
    """Each line gives the group most lines have; a tie keeps its first."""
    stage, var_a, var_b, dead = ('s',), ('a',), ('b',), ('d',)
    rest = [[var_a, stage], [stage, dead], [var_b, dead], [var_b]]
    assert one_each(rest) == (stage, stage, var_b, var_b)
