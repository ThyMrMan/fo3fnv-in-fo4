"""The Hub's topic index (each topic's lines in Hub order, the greeting order drawn from it) and its menu options."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike import say_topics as SAY
from fo4_import.spike.conversation import (GREETING, NEVER, Conversations, hub, hub_key, named_speaker, negated,
                                           one_each, outside_lines)
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


def test_a_shared_info_answers_the_player_topic_borrowing_it():
    """Player topic T1 has no lines but borrows Q1's line A2 (DIAL SharedInfo): the Hub lists T1 and holds a copy
    of A2 as T1's line, keyed 'A2 via T1'; a share for a quest outside the build, or into GREETING, is not taken."""
    infos = {'Q1': [_line('A1', GREETING, 'Q1'), _line('A2', '00000001', 'Q1')]}
    borrow = {'SharedInfoCount': '2', 'SharedInfo[0].Quest': 'Q1', 'SharedInfo[0].Info': 'A2',
              'SharedInfo[1].Quest': 'Q9', 'SharedInfo[1].Info': 'A1'}
    dials = {'T1': {'DATA.Type': '0', 'DATA.Flags': '2', **borrow},
             GREETING: {'DATA.Type': '0', 'SharedInfoCount': '1', 'SharedInfo[0].Quest': 'Q1',
                        'SharedInfo[0].Info': 'A2'}}
    shared = hub(SimpleNamespace(infos=infos, dials=dials), [{'FormID': 'Q1', 'EditorID': 'One'}], {'One': 1}, set())
    assert shared.by_topic['T1'] == [(2, 'A2 via T1')] and shared.topics == ('T1',)
    assert shared.lines['A2 via T1']['ParentDIAL'] == 'T1' and shared.by_topic[GREETING] == [(0, 'A1')]
    assert hub_key(shared.lines['A2 via T1']) == 'A2 via T1' and hub_key(infos['Q1'][1]) == 'A2'


def test_a_shared_copy_takes_its_own_formid_owner():
    """A shared info's copy is keyed 'INFO <line> 1 via <topic>', so its count never meets the line's own copies."""
    keys = []
    say = SAY.SayTopics.__new__(SAY.SayTopics)
    say.builder = SimpleNamespace(counts=Counter(), readiness=SimpleNamespace(add=lambda *a: None),
                                  new_id=lambda line, key=None: keys.append((line, key)) or 0x900,
                                  idles=SimpleNamespace(line=lambda rec: b''), scripts=SimpleNamespace(dir=None, used=[]))
    say.script_vars, say.voiced, say.once = {}, [], SayOnce()
    say.info({**_line('00000A02', 'T1', 'Q1'), SAY.SHARED: 'T1'}, {}, place='P')
    assert keys == [('INFO 00000A02 1 via T1', 'INFO 00000A02 1 via T1 at P')]


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


def test_an_option_of_say_once_lines_needs_a_line_that_passes_and_is_unsaid():
    """Vulpes' "lessons": two Say Once answers on opposite tests; once the passing one is said, the option hides,
    where ANDing (either test) with (either unsaid) still showed it with no line to play."""
    rich, poor = _test('GetItemCount', CAPS, op=0x60, value=100.0, run_on=1), _test('GetItemCount', CAPS, op=0x80,
                                                                                       value=100.0, run_on=1)
    lines = [_said('L1', 'Lessons?', [rich], 0x04), _said('L2', 'Lessons?', [poor], 0x04)]
    talk = _earlier(lines)[1]
    count, once = C.FO4.index('GetItemCount'), talk.say.once

    def unsaid(line: str, op: int) -> tuple:
        """The CTDA row of `line`'s unsaid marker."""
        return op, 0.0, STAGE_DONE, once.quest, once.stage(line), R.RUN_SUBJECT
    has, lacks = (0x61, 100.0, count, CAPS, 0, R.RUN_SUBJECT), (0x80, 100.0, count, CAPS, 0, R.RUN_SUBJECT)
    assert _ctdas(talk._either(lines)) == [has, lacks, has, unsaid('L2', 0), (0x81, *lacks[1:]), unsaid('L1', 0),
                                           unsaid('L1', 1), unsaid('L2', 0)]


#: A writer giving every hashed FormID one value (the script-package quest's).
WRITER = SimpleNamespace(derive_formid=lambda site, key: 0x0A00F000, own_index=0x0A)


def test_the_greeting_starts_for_a_talker_in_a_speakers_talking_as_list():
    """Tabitha's dish hut transceiver: activating it opens the Greeting, whose starter line passes for Tabitha
    (GetIsID) or a talker in her talking-as list (IsInList), so her intercom greeting plays."""
    tabitha, flst = 0x0E60F1, 0x0A000099
    line = {**_line('T1', GREETING, 'Q1'), 'ConditionCount': '1', 'Condition[0].Raw': _test('GetIsID', tabitha)}
    say = SimpleNamespace(infos={'Q1': [line]}, dials={GREETING: {'DATA.Type': '1'}}, script_vars={}, once=SayOnce(),
                          silent=[], builder=SimpleNamespace(counts=Counter(), new_id=lambda owner, key=None: len(owner),
                                                             scripts=SimpleNamespace(used=[]), writer=WRITER))
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
                                                             scripts=SimpleNamespace(used=[]), writer=WRITER))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, 0, hub(say, [quest], {'One': 1}, set()))
    talk.greeting([])
    starter = talk.topics[-1]
    assert b'F3NV_Greeting' in starter and b'TSCE' not in starter and b'ALFA' not in starter
    assert talk.say.builder.scripts.used == ['F3NV_Greeting']


def test_a_step_two_lines_lead_to_starts_its_own_scene():
    """A follows up with B, which follows up with C; D (another quest's line) also follows up with C. B runs on in
    A's scene, but C, a join, starts a scene of its own, so building D's path first or last places C the same."""
    follow = lambda fid, nxt: {**_line(fid, '00000001', 'Q1'), 'FollowUpCount': '1', 'FollowUp[0]': nxt}
    infos = {'Q1': [follow('A', 'B'), follow('B', 'C'), _line('C', '00000001', 'Q1')], 'Q2': [follow('D', 'C')]}
    ids = {}
    say = SimpleNamespace(infos=infos, dials={}, script_vars={}, once=SayOnce(), silent=[],
                          builder=SimpleNamespace(counts=Counter(),
                                                  new_id=lambda owner, key=None: ids.setdefault(key or owner, len(ids) + 1)))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, 0, hub(say, [quest], {'One': 1}, set()))
    assert talk.hub.joins == {('line', ('C',))}
    scene = talk.scene(('line', ('A',)))[0]
    assert talk.placed[('line', ('B',))][0] == scene != talk.placed[('line', ('C',))][0]


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


def test_a_player_lines_text_is_html_escaped_and_an_npcs_is_not():
    """XDI lists a player option's response text as HTML (`<Say nothing.>` showed blank, played 2026-11-02): a line
    with a prompt escapes its prompt and its text; an NPC line without one keeps its text."""
    player = {s.type: s.data for s in _subs(R.pack_info(1, 0, ('<Say nothing.>',), prompt='<Say nothing.>'))}
    npc = {s.type: s.data for s in _subs(R.pack_info(2, 0, ('<Sigh> & so on.',)))}
    assert player['RNAM'] == player['NAM1'] == b'&lt;Say nothing.&gt;\0'
    assert npc['NAM1'] == b'<Sigh> & so on.\0' and 'RNAM' not in npc


def test_a_prompt_behind_a_line_that_always_passes_never_shows():
    """A prompt behind an unconditional line gets NEVER; negated() flips a test."""
    earlier, _ = _earlier([_said('L1', 'Hello.', []), _said('L2', 'Hi again.', [])])
    assert earlier == {'Hello.': b'', 'Hi again.': NEVER}
    assert negated('60' + '00' * 27, True)[:2] == '81' and negated('21' + '00' * 27, False)[:2] == '00'


def test_a_menu_keeps_only_the_lines_its_speakers_can_say():
    """Doc's line leads to a menu: its speakers are {Doc}. Ada's line and a faction Doc is not in leave it, a line
    naming no one stays; a menu a generic line leads to keeps everything."""
    lead = {**_said('L1', 'Lead', [_test('GetIsID', DOC)]), 'ParentDIAL': 'D0', 'ChoiceCount': '1', 'Choice[0]': 'D1'}
    generic = {**_said('L2', 'Any', []), 'ParentDIAL': 'D0', 'ChoiceCount': '1', 'Choice[0]': 'D2'}
    options = [_said('A1', 'Ada bye.', [_test('GetIsID', ADA)]), _said('G1', 'Gossip bye.', [_test('GetInFaction', GOSSIP)]),
               _said('X1', 'Bye.', [])]
    say = SimpleNamespace(infos={'Q1': [lead, generic] + options}, dials={'D1': {'FULL': 'Topic', 'DATA.Type': '0'}},
                          script_vars={}, once=SayOnce(), builder=SimpleNamespace(counts=Counter()))
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    shared = hub(say, [quest], {'One': 1}, set())
    shared.actors = {DOC: {'FormID': f'{DOC:08X}'}}
    talk = Conversations(say, quest, 1, FORMS, 0, shared)
    assert shared.speakers[('menu', ('D1',))] == frozenset({DOC}) and shared.speakers[('menu', ('D2',))] is None
    kept = [r['FormID'] for r in talk._sayable('D1', shared.speakers[('menu', ('D1',))])]
    assert kept == ['X1'] and say.builder.counts['menu lines no speaker of the menu can say'] == 2
    assert [r['FormID'] for r in talk._sayable('D1', None)] == ['A1', 'G1', 'X1']


def test_a_masters_line_that_ends_the_talk_takes_the_leave_off_a_mods_menu():
    """A mod's line L1 offers topics D1 and D2, whose lines are its master's: M1 is followed by nothing (the talk
    returns), M2 only offers D2 again. D1's menu gets no [Leave], D2's (never-ending) keeps it; the Hub's own lines
    stay the mod's. Without masters nothing is outside, and both menus leave as before."""
    choice = lambda fid, dial, to: {**_line(fid, dial, 'Q1'), 'ChoiceCount': '1', 'Choice[0]': to}
    masters = [_line('M1', 'D1', 'Q9'), choice('M2', 'D2', 'D2')]
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    found = {}
    for outside in (masters, []):
        say = SimpleNamespace(infos={'Q1': [choice('L1', 'D0', 'D1')]}, dials={}, outside=outside)
        shared = hub(say, [quest], {'One': 1}, set())
        shared.outside, shared.outside_topics = outside_lines(say, shared.lines)
        talk = Conversations(say, quest, 1, FORMS, 0, shared)
        found[len(outside)] = [talk._leaves(('menu', (dial,))) for dial in ('D1', 'D2')], list(shared.lines)
    assert found == {2: ([False, True], ['L1']), 0: ([True, True], ['L1'])}
    assert shared.outside == {} and talk._members(('menu', ('D1',)), True) == []


def test_a_topic_sharing_its_own_line_takes_no_second_copy():
    """T1 lists its own line A1 as a shared info beside Q1's B1 of another topic: only B1 is copied, so A1
    answers T1 once."""
    infos = {'Q1': [_line('A1', 'T1', 'Q1'), _line('B1', '00000001', 'Q1')]}
    shares = {'SharedInfoCount': '2', 'SharedInfo[0].Quest': 'Q1', 'SharedInfo[0].Info': 'A1',
              'SharedInfo[1].Quest': 'Q1', 'SharedInfo[1].Info': 'B1'}
    dials = {'T1': {'DATA.Type': '0', 'DATA.Flags': '2', **shares}}
    shared = hub(SimpleNamespace(infos=infos, dials=dials), [{'FormID': 'Q1', 'EditorID': 'One'}], {'One': 1}, set())
    assert shared.by_topic['T1'] == [(0, 'A1'), (2, 'B1 via T1')]


def test_a_choice_fnv_never_answers_is_counted_and_others_name_their_cause():
    """No line anywhere, or none the menu's speakers can say: only a count. A topic whose lines are all in an
    unbuilt quest, or whose lines do not convert, gets a readiness entry naming why."""
    entries = []
    infos = {'Q1': [_line('A1', 'D1', 'Q1')], 'Q2': [_line('B1', 'D2', 'Q2')]}
    dials = {d: {'EditorID': f'Topic{d}', 'DATA.Type': '0'} for d in ('D1', 'D2', 'D3')}
    say = SimpleNamespace(infos=infos, dials=dials, builder=SimpleNamespace(
        counts=Counter(), readiness=SimpleNamespace(add=lambda kind, owner, detail: entries.append(detail))))
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, 0, hub(say, [quest], {'One': 1}, set()))
    for dial, sayable in (('D3', False), ('D1', False), ('D2', False), ('D1', True)):
        talk._unanswered(dial, sayable)
    assert say.builder.counts['choice FNV never answers (no line)'] == 1
    assert say.builder.counts['choice FNV never answers (speaker-filter)'] == 1
    assert entries == ['TopicD2 (D2): not built', 'TopicD1 (D1): condition']


def test_an_option_two_npcs_answer_needs_an_answer_this_speaker_can_play():
    """Big Sal's "Tell me about the plan.": Nero's answer has no test, Sal's needs iSalInfo; each speaker joins
    its own line's tests, so the option holds for Nero, or for Sal with his test, never for Sal on Nero's line."""
    plan = _test('GetItemCount', CAPS, op=0x60, value=100.0, run_on=1)
    lines = [_said('L1', 'Plan?', [_test('GetIsID', JASON), plan]), _said('L2', 'Plan?', [_test('GetIsID', DOC)])]
    is_id, count = C.FO4.index('GetIsID'), C.FO4.index('GetItemCount')
    sal, nero = (FORMS[JASON], R.RUN_TARGET), (FORMS[DOC], R.RUN_TARGET)
    rows = _ctdas(_earlier(lines)[1]._either(lines))
    assert rows == [(0x01, 1.0, is_id, *sal[:1], 0, sal[1]), (0x00, 1.0, is_id, *nero[:1], 0, nero[1]),
                    (0x61, 100.0, count, CAPS, 0, R.RUN_SUBJECT), (0x00, 1.0, is_id, *nero[:1], 0, nero[1])]
