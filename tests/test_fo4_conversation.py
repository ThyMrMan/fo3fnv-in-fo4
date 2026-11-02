"""The Hub's topic index (each topic's lines in Hub order, the greeting order drawn from it) and its menu options."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.conversation import GREETING, NEVER, Conversations, hub, named_speaker, negated, one_each
from fo4_import.spike.say_once import STAGE_DONE, SayOnce

#: FNV NPCs and their FO4 copies; FNV's caps (an engine form, kept as it is); a faction.
JASON, DOC, ADA, NASH, CAPS, GOSSIP = 0x1428ED, 0x104C0C, 0x0CE88C, 0x0DA729, 0x0F, 0x13F897
FORMS = {JASON: 0x0A000001, DOC: 0x0A000002, ADA: 0x0A000003, NASH: 0x0A000004, CAPS: CAPS}
#: FNV INFO DATA flags: Goodbye and Say Once.
GOODBYE_SAY_ONCE = 0x05


def _line(fid: str, dial: str, quest: str) -> dict:
    """An FNV INFO of topic `dial` in `quest`."""
    return {'FormID': fid, 'ParentDIAL': dial, 'QSTI.Quest': quest}


def _test(func: str, p1: int, op: int = 0x00, value: float = 1.0, run_on: int = 0) -> str:
    """One FNV condition as the export's raw hex."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, run_on, 0).hex()


def _said(fid: str, prompt: str, tests: list, flags: int = 0) -> dict:
    """An FNV INFO of topic D1 in Q1: `prompt`, raw `tests`, DATA `flags`."""
    rec = {**_line(fid, 'D1', 'Q1'), 'Prompt': prompt, 'DATA.Flags': str(flags), 'ConditionCount': str(len(tests))}
    return {**rec, **{f'Condition[{i}].Raw': raw for i, raw in enumerate(tests)}}


def _earlier(lines: list, actors: dict = None, unfixed: frozenset = frozenset(), forms: dict = None) -> tuple:
    """({prompt: the CTDAs hiding its option behind earlier lines}, the conversation) for one topic's `lines`;
    the Hub's actor records `actors`, script-changed factions `unfixed`, the form map `forms` (FORMS)."""
    say = SimpleNamespace(infos={'Q1': lines}, dials={'D1': {'FULL': 'Topic', 'DATA.Type': '0'}}, script_vars={},
                          once=SayOnce(), builder=SimpleNamespace(counts=Counter()))
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    shared = hub(say, [quest], {'One': 1}, set())
    shared.actors, shared.unfixed = actors or {}, unfixed
    talk = Conversations(say, quest, 1, forms or FORMS, 0, shared)
    order = [((rec['Prompt'], 'Q1'), rec, named_speaker(rec)) for rec in lines]
    return {rec['Prompt']: talk._earlier((rec['Prompt'], 'Q1'), order) for rec in lines}, talk


def _ctdas(data: bytes) -> list:
    """[(op flags, value, function, param 1, param 2, run on)] of packed FO4 CTDAs."""
    return [struct.unpack_from('<B3xfH2xIII', data, at + 6) for at in range(0, len(data), 38)]


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


def test_a_repeat_prompt_waits_until_the_say_once_prompt_is_said():
    """Jason Bright's pair: "Like I said." shows only once "Sorry." is said or cannot pass; "Sorry." needs nothing."""
    first = _said('L1', 'Sorry.', [_test('GetIsID', JASON)], GOODBYE_SAY_ONCE)
    earlier, talk = _earlier([first, _said('L2', 'Like I said.', [_test('GetIsID', JASON)])])
    assert earlier['Sorry.'] == b''
    assert _ctdas(earlier['Like I said.']) == [
        (0x01, 1.0, STAGE_DONE, talk.say.once.quest, talk.say.once.stage('L1'), R.RUN_SUBJECT),
        (0x20, 1.0, C.FO4.index('GetIsID'), FORMS[JASON], 0, R.RUN_TARGET)]


def test_each_speaker_hides_a_prompt_behind_their_own_earlier_line():
    """Doc's caps pair, with Doc's lines after Ada's: "No caps." hides behind each speaker's caps line (GetIsID other
    or under 100 caps); "Fix me." comes first for both speakers, so it needs nothing."""
    caps = _test('GetItemCount', CAPS, op=0x60, value=100.0, run_on=1)
    lines = [_said('A1', 'Fix me.', [_test('GetIsID', ADA), caps]), _said('A2', 'No caps.', [_test('GetIsID', ADA)]),
             _said('B1', 'Fix me.', [_test('GetIsID', DOC), caps]), _said('B2', 'No caps.', [_test('GetIsID', DOC)])]
    earlier, _ = _earlier(lines)
    assert earlier['Fix me.'] == b''
    is_id, count = C.FO4.index('GetIsID'), C.FO4.index('GetItemCount')
    assert _ctdas(earlier['No caps.']) == [
        (0x21, 1.0, is_id, FORMS[ADA], 0, R.RUN_TARGET), (0x80, 100.0, count, CAPS, 0, R.RUN_SUBJECT),
        (0x21, 1.0, is_id, FORMS[DOC], 0, R.RUN_TARGET), (0x80, 100.0, count, CAPS, 0, R.RUN_SUBJECT)]


def test_a_line_between_an_options_lines_hides_it_only_while_its_earlier_lines_fail():
    """Nash's layout: "Rule of law." has lines before and after "Deputy died."; the line between hides it unless its
    earlier line (100 caps) passes, and "Deputy died." hides behind that earlier line."""
    nash, caps = _test('GetIsID', NASH), _test('GetItemCount', CAPS, op=0x60, value=100.0, run_on=1)
    earlier, _ = _earlier([_said('L0', 'Rule of law.', [nash, caps]), _said('L1', 'Deputy died.', [nash]),
                           _said('L2', 'Rule of law.', [nash])])
    is_id, count = C.FO4.index('GetIsID'), C.FO4.index('GetItemCount')
    assert _ctdas(earlier['Rule of law.']) == [
        (0x61, 100.0, count, CAPS, 0, R.RUN_SUBJECT), (0x20, 1.0, is_id, FORMS[NASH], 0, R.RUN_TARGET)]
    assert _ctdas(earlier['Deputy died.']) == [
        (0x21, 1.0, is_id, FORMS[NASH], 0, R.RUN_TARGET), (0x80, 100.0, count, CAPS, 0, R.RUN_SUBJECT)]


def test_a_named_line_hides_a_generic_option_only_from_an_actor_who_can_say_it():
    """Doc's line comes before a line for the gossip faction: it hides that option while Doc can be in the faction
    (no record of him, in it, or a script changes it), not when his record keeps him out."""
    lines = [_said('D1', 'Doc bye.', [_test('GetIsID', DOC)]), _said('G1', 'Gossip bye.', [_test('GetInFaction', GOSSIP)])]
    outside = {'FormID': f'{DOC:08X}'}
    member = {**outside, 'FactionCount': '1', 'Faction[0].FormID': f'{GOSSIP:08X}', 'Faction[0].Rank': '0'}
    hidden = [_ctdas(_earlier(lines, actors, unfixed)[0]['Gossip bye.'])
              for actors, unfixed in (({}, frozenset()), ({DOC: member}, frozenset()), ({DOC: outside}, frozenset({GOSSIP})))]
    assert hidden == [[(0x20, 1.0, C.FO4.index('GetIsID'), FORMS[DOC], 0, R.RUN_TARGET)]] * 3
    assert _earlier(lines, {DOC: outside})[0]['Gossip bye.'] == b''


def test_a_say_once_option_drops_by_its_answers_markers_not_the_prompts_own_say_once():
    """"What are Powder Gangers?", answered once by each of two NPCs: FO4's Say Once on the prompt would hide it
    after the first answer while its pad still passed (a blank "dialogueentry" option); prompt and pad both read
    the answers' markers instead."""
    lines = [_said('L1', 'Gangers?', [_test('GetIsID', DOC)], 0x04), _said('L2', 'Gangers?', [_test('GetIsID', ADA)], 0x04)]
    _, talk = _earlier(lines)
    talk.say.builder.new_id = lambda owner, key=None: len(key or owner)
    talk._line = lambda rec, continues, alias=None, place='': b'answer'
    for name in ('_shared', '_either', '_speakers', '_running', '_gate'):
        setattr(talk, name, lambda *args: b'')
    player, npc = [], []
    assert talk._prompt('D1', 'Gangers?', lines, (player, npc), False, 'place')
    prompt, pad = (dict((s.type, s.data) for s in _subs(info)) for info in player)
    assert struct.unpack('<H', prompt['ENAM'][:2])[0] & R.INFO_SAY_ONCE == 0
    assert prompt['CTDA'] == pad['CTDA'] and struct.unpack_from('<H', prompt['CTDA'], 8)[0] == STAGE_DONE


def test_the_greeting_starts_for_a_talker_in_a_speakers_talking_as_list():
    """Tabitha's dish hut transceiver: activating it opens the Greeting, whose starter line passes for Tabitha
    (GetIsID) or a talker in her talking-as list (IsInList), so her intercom greeting plays."""
    tabitha, flst = 0x0E60F1, 0x0A000099
    line = {**_line('T1', GREETING, 'Q1'), 'ConditionCount': '1', 'Condition[0].Raw': _test('GetIsID', tabitha)}
    say = SimpleNamespace(infos={'Q1': [line]}, dials={GREETING: {'DATA.Type': '1'}}, script_vars={}, once=SayOnce(),
                          silent=[], builder=SimpleNamespace(counts=Counter(), new_id=lambda owner, key=None: len(owner),
                                                             scripts=SimpleNamespace(used=[])))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, {tabitha: 0x0A000005, (C.TALKING_AS, tabitha): flst}, 0,
                         hub(say, [quest], {'One': 1}, set()))
    talk.greeting([])
    ctdas = [c for c in _ctdas_in(talk.topics[-1])]
    assert (C.FO4.index('GetIsID'), 0x0A000005) in ctdas and (C.FO4.index('IsInList'), flst) in ctdas


def test_the_greeting_line_opens_its_scene_by_script_not_tsce():
    """A GREETING scene left playing (a talk cut off, a save made mid-talk) made every later TSCE start fail, so
    menus showed only "dialogueentry"; the starter line carries F3NV_Greeting, which stops it and starts it again."""
    line = {**_line('T1', GREETING, 'Q1'), 'ConditionCount': '1', 'Condition[0].Raw': _test('GetIsID', DOC)}
    say = SimpleNamespace(infos={'Q1': [line]}, dials={GREETING: {'DATA.Type': '1'}}, script_vars={}, once=SayOnce(),
                          silent=[], builder=SimpleNamespace(counts=Counter(), new_id=lambda owner, key=None: len(owner),
                                                             scripts=SimpleNamespace(used=[])))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, 0, hub(say, [quest], {'One': 1}, set()))
    talk.greeting([])
    starter = talk.topics[-1]
    assert b'F3NV_Greeting' in starter and b'TSCE' not in starter and b'ALFA' not in starter
    assert talk.say.builder.scripts.used == ['F3NV_Greeting']


def _ctdas_in(blob: bytes) -> list:
    """(function, param 1) of every CTDA in a packed topic blob."""
    out, at = [], 0
    while (at := blob.find(b'CTDA\x20\x00', at)) >= 0:
        out.append(struct.unpack_from('<H2xI', blob, at + 6 + 8))
        at += 6
    return out


def _subs(record: bytes) -> list:
    """The subrecords of one packed FO4 record."""
    out, at = [], 24
    while at < len(record):
        size = struct.unpack_from('<H', record, at + 4)[0]
        out.append(SimpleNamespace(type=record[at:at + 4].decode(), data=record[at + 6:at + 6 + size]))
        at += 6 + size
    return out


def test_a_later_prompt_hides_behind_an_earlier_line_said_through_an_intercom():
    """Chris Haversam's intercom goodbyes: "Got it." passes for Chris or a talker in his talking-as list, so
    "Sure." shows only while both fail: not Chris, or not in the list, each in its own OR-group."""
    chris, flst = 0x0810E9, 0x0A000099
    lines = [_said('L1', 'Got it.', [_test('GetIsID', chris)]), _said('L2', 'Sure.', [_test('GetIsID', chris)])]
    earlier, _ = _earlier(lines, forms={chris: 0x0A000006, (C.TALKING_AS, chris): flst})
    assert _ctdas(earlier['Sure.']) == [(0x20, 1.0, C.FO4.index('GetIsID'), 0x0A000006, 0, R.RUN_TARGET),
                                        (0x00, 0.0, C.FO4.index('IsInList'), flst, 0, R.RUN_TARGET)]


def test_a_prompt_behind_a_line_that_always_passes_never_shows():
    """A prompt behind an unconditional line gets NEVER; negated() flips a test."""
    earlier, _ = _earlier([_said('L1', 'Hello.', []), _said('L2', 'Hi again.', [])])
    assert earlier == {'Hello.': b'', 'Hi again.': NEVER}
    assert negated('60' + '00' * 27, True)[:2] == '81' and negated('21' + '00' * 27, False)[:2] == '00'
