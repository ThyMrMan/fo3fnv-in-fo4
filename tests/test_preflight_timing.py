"""The progress timing audit: prerequisites, topic known, writers on their triggers, dropped blocks.

See: docs/fork/fo4_timing_audit.md#design
"""
import struct
from collections import Counter
from types import SimpleNamespace

from tests.test_preflight_audits import export_file, zs
from tests.test_preflight_fo4 import OWN, fo4_index, rec
from tools.validate.preflight import timing
from tools.validate.preflight import timing_prereqs as P
from tools.validate.preflight import timing_writers as W
from tools.validate.preflight.quest_converted import parse_script

#: Fallout 4's GetGlobalValue function index.
GET_GLOBAL = 74


def cond(name, quest, value, op=0x00, or_next=False, number=0):
    """A decoded condition whose fact the test's reader names `name` on `quest` with parameter `number`."""
    return {'type': op | int(or_next), 'value': value, 'name': name, 'quest': quest, 'number': number}


def read(c):
    """The condition_diff-style fact of a test condition."""
    if c['name'] in ('objshown', 'objdone'):
        return (c['name'], c['quest'], c['number']), None
    return (c['name'], 0, (c['quest'], c['number'])), None


def test_only_required_conditions_on_facts_that_stay_true_are_prerequisites():
    """Stage at least 20 is one; an OR chain, a `not yet` test and a stage below are not."""
    q = ('form', 'q')
    conds = [cond('GetStage', q, 20.0, 0x60), cond('objshown', q, 1.0, number=50),
             cond('GetStageDone', q, 1.0, or_next=True, number=5), cond('GetStageDone', q, 1.0, number=6),
             cond('objdone', q, 0.0, number=60), cond('GetStage', q, 10.0, 0x80)]
    assert P.prerequisites(conds, read) == {('stage', q, 20.0), ('objshown', q, 50)}


def test_a_higher_stage_covers_a_lower_one_and_writers_share_only_common_needs():
    """Stage 50 reached implies stage 30; two revealers needing different stages share neither."""
    q = ('form', 'q')
    assert P.implied(('stage', q, 30.0), frozenset({('done', q, 50)}))
    assert P.common([frozenset({('stage', q, 30.0)}), frozenset({('stage', q, 50.0)})]) == {('stage', q, 30.0)}
    assert P.common([frozenset({('objshown', q, 1)}), frozenset({('objshown', q, 2)})]) == frozenset()


class Known:
    """A TopicKnown stand-in: one topic, its lines' needs, and each side's needs for knowing it."""

    def __init__(self, fnv, built, lines):
        """Each side's needs for the topic, and each line's needs."""
        infos = {i: SimpleNamespace(fid=i, dial=1) for i in range(len(lines))}
        self.ctx = SimpleNamespace(game='P.esp', source=SimpleNamespace(dials={1: ('T', 0, 0)}, infos=infos))
        self.fnv, self.built, self.lines, self.adders, self.revealers = fnv, built, lines, {}, {}
        self.gated = set() if built == frozenset() else {1}

    def fnv_known(self, _topic):
        """FNV's needs."""
        return self.fnv

    def built_known(self, _topic):
        """The build's needs."""
        return self.built

    def line_needs(self, fid):
        """Line `fid`'s needs."""
        return self.lines[fid]


def test_a_topic_ungated_in_the_build_shows_before_its_fnv_greeting_could_add_it():
    """The VMS49 vagrant: FNV adds the topic in a greeting that needs objective 50 shown; the lines do not."""
    shown = ('objshown', ('form', 'vms49'), 50)
    found = timing.judge_topic(Known(frozenset({shown}), frozenset(), [frozenset()]), 1, Counter())
    assert [f.key for f in found] == ['timing|P.esp|topic T|too-soon']
    assert timing.judge_topic(Known(frozenset({shown}), frozenset(), [frozenset({shown})]), 1,
                              Counter()) == []


def test_a_gate_no_script_sets_never_unlocks_and_a_tighter_reveal_is_late():
    """A gated topic with no unlock write never shows; one whose reveal needs more than FNV's shows late."""
    late = ('stage', ('form', 'q'), 20.0)
    counts = Counter()
    assert timing.judge_topic(Known(frozenset(), 'never', [frozenset()]), 1, counts)[0].key.endswith('|never')
    assert timing.judge_topic(Known(frozenset(), frozenset({late}), [frozenset()]), 1, counts)[0].key \
        .endswith('|too-late')


def test_hub_options_and_their_unlock_gates_are_read_from_the_build(tmp_path):
    """A hub option testing an unlock global is gated by it; a pad and a Choice menu option are not hub options."""
    gate = struct.pack('<B3xfH2xIIIIi', 0, 1.0, GET_GLOBAL, OWN | 0x50, 0, 0, 0, -1)
    index = fo4_index([rec('GLOB', OWN | 0x50, [('EDID', zs('TES4Unlock_T'))]),
                       rec('INFO', OWN | 0x60, [('CTDA', gate)]), rec('INFO', OWN | 0x61)])
    ledger = tmp_path / 'P.formids.tsv'
    ledger.write_text('\n'.join([
        'id\tFNV made\t"INFO prompt 00001234 Hi. at 00000001 menu hub 00001234 for 00000002"\t000060',
        'id\tFNV made\t"INFO prompt 00001234 Hi. at 00000001 menu hub 00001234 for 00000002 pad 1"\t000061',
        "id\tFNV made\t\"INFO prompt 00001234 Hi. at 00000001 ('menu', ('00000003',)) 00001234 for 0002\"\t000061"]),
        encoding='utf-8')
    options = timing.hub_options(index, ledger)
    assert options == {0x1234: [OWN | 0x60]} and timing.unlock_gates(index, index.by_fid[OWN | 0x60]) == {OWN | 0x50}


def test_fnv_writes_keep_their_block_and_skip_computed_stages():
    """Each command gives its fact and Begin block; a SetStage on a variable stage is left out."""
    text = ('scn S\\r\\nbegin OnFire\\r\\n  StartQuest VQ\\r\\n  SetObjectiveDisplayed VQ 10 1\\r\\nend\\r\\n'
            'begin GameMode\\r\\n  setstage VQ n\\r\\n  AddTopic Rumors ; hint\\r\\n  StopQuest VQ\\r\\nend')
    found = W.find_writes(text, {'vq': 'VQ'}, {'rumors'})
    assert [(f, b) for f, b, _r in found] == [(('start', 'vq'), 'onfire'), (('objshown', 'vq', 10, True), 'onfire'),
                                              (('topic', 'rumors'), 'gamemode'), (('stop', 'vq'), 'gamemode')]


def test_build_writes_resolve_quests_and_unlock_globals_through_properties():
    """Stop, CompleteQuest, objectives and an unlock global's SetValue read as facts in their functions."""
    text = ('Event OnTimer(int aiTimerID)\n  VQ.Stop()\n  CompleteQuest()\n  VQ.SetObjectiveDisplayed(10, 0)\n'
            '  TES4Unlock_T.SetValue(1)\nEndEvent\n')
    ctx = SimpleNamespace(scripts={'s': parse_script('s', text, True)},
                          resolve=lambda expr, _s: 'vq' if expr in ('vq', '') else None,
                          index=SimpleNamespace(script_props={'s': {'tes4unlock_t': 0x50}}))
    assert W.built_writes(text, 's', ctx, {0x50: {'t'}}) == [
        (('stop', 'vq'), 'ontimer'), (('complete', 'vq'), 'ontimer'), (('objshown', 'vq', 10, False), 'ontimer'),
        (('topic', 't'), 'ontimer')]


def test_a_block_with_code_and_no_handler_is_dropped_but_a_plain_activate_is_not():
    """OnFire with code has no converted event; OnActivate passing activation on needs none."""
    fnv = 'scn S\\r\\nBEGIN OnFire\\r\\n  StartQuest VQ\\r\\nEND\\r\\nbegin OnActivate\\r\\n  Activate\\r\\nend'
    assert W.blocks(fnv) == [('onfire', True), ('onactivate', False)]
    built = 'ScriptName X extends ObjectReference\n; --- TES4 `Begin MenuMode` ---\n'
    assert W.block_state('onfire', built) == '' and W.block_state('menumode', built) == 'comment'
    assert W.block_state('gamemode', 'Event OnTimer(int aiTimerID)\nEndEvent\n') == 'handler'


def test_a_stage_flagged_complete_quest_writes_the_quest_complete(tmp_path):
    """FNV's Complete Quest log flag is a write of its stage; the quest's authored objectives are kept."""
    export_file(tmp_path, 'QUST', [{'FormID': '00001000', 'EditorID': 'VQ', 'Objective[0].Index': 10,
                                    'Stage[0].Index': 100, 'Stage[0].LogCount': 1, 'Stage[0].Log[0].Flags': 1}])
    source = SimpleNamespace(quests={'vq': 'VQ'}, dials={})
    writes = W.SourceWrites(tmp_path, source, 'X_')
    assert [(w.fact, w.owner) for w in writes.writes] == [(('complete', 'vq'), 'VQ|100')]
    assert writes.objectives == {'vq': {10}} and writes.script(writes.writes[0]) == 'x_qf_vq'


def test_a_line_write_must_stay_in_its_half():
    """An FNV begin-script write belongs in Fragment_1; one in Fragment_0 has moved."""
    begin = W.expected(W.Write(('stage', 'q', 10), 'info', '00000001', 'begin'), None)
    assert begin('fragment_1') and not begin('fragment_0')
    terminal = W.expected(W.Write(('stage', 'q', 10), 'terminal', '00000001', '2'), None)
    assert terminal('fragment_terminal_03')
