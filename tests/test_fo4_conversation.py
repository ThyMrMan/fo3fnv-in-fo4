"""The Hub's topic index (each topic's lines in Hub order, the greeting order drawn from it), its menus, their
options and answer topics.

See: docs/fork/fo4_dialogue_menu_plan.md#converter
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike import say_once as SO
from fo4_import.spike import say_topics as SAY
from fo4_import.spike.conversation import GREETING, Conversations, hub, hub_key, opener_forms, outside_lines
from fo4_import.spike.dialogue import LEAVE
from fo4_import.spike.quest import SPEAKER_ALIAS
from fo4_import.spike.say_once import SayOnce

#: FNV NPCs and their FO4 copies; FNV's caps (an engine form, kept as it is).
JASON, DOC, ADA, NASH, CAPS = 0x1428ED, 0x104C0C, 0x0CE88C, 0x0DA729, 0x0F
FORMS = {JASON: 0x0A000001, DOC: 0x0A000002, ADA: 0x0A000003, NASH: 0x0A000004, CAPS: CAPS}
#: FNV's Speech (actor value index) and its FO4 actor value.
SPEECH, FO4_SPEECH = C.FNV_AV_NAMES.index('Speech'), 0x0100081C


def _line(fid: str, dial: str, quest: str) -> dict:
    """An FNV INFO of topic `dial` in `quest`."""
    return {'FormID': fid, 'ParentDIAL': dial, 'QSTI.Quest': quest}


def _test(func: str, p1: int, op: int = 0x00, value: float = 1.0, run_on: int = 0) -> str:
    """One FNV condition as the export's raw hex."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, run_on, 0).hex()


def _said(fid: str, dial: str, prompt: str, tests: list = (), **more) -> dict:
    """An FNV INFO of topic `dial` in Q1: `prompt`, raw `tests`, more keys."""
    rec = {**_line(fid, dial, 'Q1'), 'Prompt': prompt, 'DATA.Flags': '0', 'ConditionCount': str(len(tests)), **more}
    return {**rec, **{f'Condition[{i}].Raw': raw for i, raw in enumerate(tests)}}


def _say(lines: list, dials: dict) -> SimpleNamespace:
    """A SayTopics stand-in over Q1's `lines`: its info() packs each line as an INFO keyed by line and place."""
    ids = {}
    builder = SimpleNamespace(counts=Counter(), readiness=SimpleNamespace(add=lambda *a: None),
                              new_id=lambda owner, key=None: ids.setdefault(key or owner, 0x0A000800 + len(ids)))
    say = SimpleNamespace(infos={'Q1': lines}, dials=dials, script_vars={}, once=SayOnce(), silent=[], links=[],
                          checks=[], builder=builder)

    def info(rec, form_map, scene=(0, ''), flags=0, forced=None, prompt='', place='', **_unused):
        """The line as a packed INFO."""
        fid = builder.new_id(f'INFO {rec["FormID"]} at {place}')
        return R.pack_info(fid, flags, ('x',), prompt=prompt, scene=scene[0], forced_alias=forced)
    say.info = info
    return say


def _quest(say, fid: int = 1, edid: str = 'One') -> Conversations:
    """Q1's conversations over a Hub of Q1."""
    quest = {'FormID': 'Q1', 'EditorID': edid}
    return Conversations(say, quest, fid, {**FORMS, ('av', SPEECH): FO4_SPEECH}, hub(say, [quest], {edid: fid}, set()))


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


def _records(blob: bytes) -> list:
    """[(signature, FormID, {subrecord: data})] of the records in a packed topic blob (its DIAL and INFOs)."""
    out, at = [], 0
    while at < len(blob):
        sig, size = blob[at:at + 4], struct.unpack_from('<I', blob, at + 4)[0]
        if sig == b'GRUP':
            at += 24
            continue
        out.append((sig.decode(), struct.unpack_from('<I', blob, at + 12)[0],
                    {s.type: s.data for s in _subs(blob[at:at + 24 + size])}))
        at += 24 + size
    return out


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
    assert Conversations(say, quests[0], 1, {}, shared)._greetings() == ['B1', 'B2', 'A1']


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


def test_say_once_stages_are_numbered_in_formid_order_before_use(monkeypatch):
    """Two lines hashing alike: reserve() numbers them in FormID order, so the stage a line gets does not depend on
    which copy the build made first."""
    monkeypatch.setattr(SO.zlib, 'crc32', lambda data: 0)
    once = SayOnce()
    once.reserve(['000B', '000A'])
    assert (once.stage('000B'), once.stage('000A')) == (SO.FIRST + 1, SO.FIRST)


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
    talk = Conversations(say, quest, 1, {tabitha: 0x0A000005, (C.TALKING_AS, tabitha): flst},
                         hub(say, [quest], {'One': 1}, set()))
    ctdas = _ctdas_in(talk.greeting([]))
    assert (C.FO4.index('GetIsID'), 0x0A000005) in ctdas and (C.FO4.index('IsInList'), flst) in ctdas


def test_the_greeting_line_opens_its_scene_by_script_not_tsce():
    """A GREETING scene left playing (a talk cut off, a save made mid-talk) made every later TSCE start fail, so
    menus showed nothing; the starter line carries F3NV_Greeting, which stops it and starts it again."""
    line = {**_line('T1', GREETING, 'Q1'), 'ConditionCount': '1', 'Condition[0].Raw': _test('GetIsID', DOC)}
    say = SimpleNamespace(infos={'Q1': [line]}, dials={GREETING: {'DATA.Type': '1'}}, script_vars={}, once=SayOnce(),
                          silent=[], builder=SimpleNamespace(counts=Counter(), new_id=lambda owner, key=None: len(owner),
                                                             scripts=SimpleNamespace(used=[]), writer=WRITER))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, hub(say, [quest], {'One': 1}, set()))
    starter = talk.greeting([])
    assert b'F3NV_Greeting' in starter and b'TSCE' not in starter and b'ALFA' not in starter
    assert talk.say.builder.scripts.used == ['F3NV_Greeting']


def _willow_greeting(skip: frozenset) -> tuple:
    """(opener, conversation) of a mod's greeting for Willow, whose quest tests GetIsID; the game's opener names
    `skip`."""
    willow = 0x01000ADD
    say = SimpleNamespace(infos={'Q1': [SAY.with_quest(_line('W1', GREETING, 'Q1'), [_test('GetIsID', willow)])]},
                          dials={GREETING: {'DATA.Type': '1'}}, script_vars={}, once=SayOnce(), silent=[],
                          builder=SimpleNamespace(counts=Counter(), new_id=lambda owner, key=None: hash(owner) & 0xFFFF,
                                                  scripts=SimpleNamespace(used=[]), writer=WRITER))
    say.info = lambda rec, form_map, *args, **kwargs: b''
    shared = hub(say, [{'FormID': 'Q1', 'EditorID': 'AWillowD'}], {'AWillowD': 1}, set())
    talk = Conversations(say, {'FormID': 'GREETINGS', 'EditorID': 'Greetings'}, 0x03A37DCF, {willow: 0x0A000007},
                         shared)
    return talk.greeting([], home=(0x0A000123, 'GREETINGS NVWillow', 'Greetings_NVWillow', skip)), talk


def test_a_mod_opens_the_greeting_from_its_own_quest():
    """Willow (NVWillow.esp) passed no Greeting line: the mod's opener took the game's id and was dropped. Given a
    home quest, the opener is keyed on it and sits in it, naming the mod's speaker (her quest's GetIsID)."""
    starter, _ = _willow_greeting(frozenset())
    dial = {s.type: s.data for s in _subs(starter[:24 + struct.unpack_from('<I', starter, 4)[0]])}
    assert dial['QNAM'] == struct.pack('<I', 0x0A000123) and dial['EDID'] == b'FNV_Greetings_NVWillow_Greeting\0'
    assert struct.unpack_from('<I', starter, 12)[0] == hash('DIAL greeting GREETINGS NVWillow') & 0xFFFF
    assert (C.FO4.index('GetIsID'), 0x0A000007) in _ctdas_in(starter)


def test_a_mod_opener_leaves_the_games_speakers_to_the_games_opener():
    """A speaker the game's opener names (opener_forms) gets no second opener, but the greeting scene still builds,
    so the mod's lines join it."""
    starter, talk = _willow_greeting(frozenset({0x0A000007}))
    assert starter == b'' and len(talk.scenes) == 1
    opener = R.pack_info(1, 0, (R.SILENT_LINE,), R.pack_ctda(0, 1.0, C.FO4.index('GetIsID'), 0x0A000007))
    assert opener_forms(opener[24:]) == {0x0A000007}


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
    talk = Conversations(say, quest, 1, FORMS, hub(say, [quest], {'One': 1}, set()))
    assert talk.hub.joins == {('line', ('C',))}
    scene = talk.scene(('line', ('A',)))[0]
    assert talk.hub.placed[('line', ('B',))][0] == scene != talk.hub.placed[('line', ('C',))][0]


def test_a_players_prompt_is_written_as_authored():
    """A prompt and its response keep < > & (shown as plain text)."""
    player = {s.type: s.data for s in _subs(R.pack_info(1, 0, ('<Say nothing.>',), prompt='<Say nothing.>'))}
    assert player['RNAM'] == player['NAM1'] == b'<Say nothing.>\0'


def test_each_topic_is_one_option_linked_to_its_answer_topic():
    """A Choices menu of D1 (a skill check and its failure) and D2: one option per topic, prompted by its first
    line and tagged with its check; each option is linked to its topic's answer topic, which holds every line of
    the topic with its own prompt; both answers carry the check (F3NV.dll shows the failing one's as failed). No
    [Leave]: the talk ends after."""
    check = _test('GetActorValue', SPEECH, op=0x60, value=25.0, run_on=1)
    lines = [_said('P1', 'D1', 'Trust me.', [check]), _said('F1', 'D1', 'Trust me.'), _said('L2', 'D2', '')]
    say = _say(lines, {'D1': {'EditorID': 'TopicD1'}, 'D2': {'EditorID': 'TopicD2', 'FULL': 'Ask.'}})
    talk = _quest(say)
    talk.scene(('menu', ('D1', 'D2')))
    found = {fid: (sig, subs) for blob in talk.topics for sig, fid, subs in _records(blob)}
    answers = talk.hub.answers
    assert [answer for _, answer in say.links] == [answers['D1'], answers['D2']]
    assert [found[option][1]['RNAM'] for option, _ in say.links] == [b'[Speech 25] Trust me.\0', b'Ask.\0']
    tagged = [fid for fid, (sig, subs) in found.items() if sig == 'INFO' and fid not in dict(say.links)
              and subs.get('RNAM') == b'[Speech 25] Trust me.\0']
    assert len(tagged) == 2 and say.checks == [(fid, FO4_SPEECH, 25) for fid in tagged]
    assert LEAVE not in answers and talk.say.builder.counts['menu options'] == 2


def test_an_answer_topic_is_built_once_for_every_menu():
    """Two menus offering D1 (and another quest's conversations on the same Hub) share one answer topic."""
    say = _say([_said('L1', 'D1', 'Hi.'), _said('L2', 'D2', 'Bye.')], {'D1': {}, 'D2': {}})
    talk = _quest(say)
    talk.scene(('menu', ('D1',)))
    talk.scene(('menu', ('D1', 'D2')))
    other = Conversations(say, {'FormID': 'Q2', 'EditorID': 'Two'}, 2, FORMS, talk.hub)
    assert other._answers('D1') == talk.hub.answers['D1'] and other.topics == []
    assert sum(1 for blob in talk.topics if b'FNV_Answer_' in blob) == 2


def test_the_topic_list_ends_in_leave_linked_to_the_exit():
    """The Hub's topic list offers [Leave] last, linked to the one silent End Scene answer."""
    say = _say([_said('L1', 'D1', 'Hi.')], {'D1': {'DATA.Type': '0', 'DATA.Flags': '2'}})
    talk = _quest(say)
    assert talk.hub.topics == ('D1',)
    talk.scene(('menu', talk.hub.topics))
    assert say.links[-1][1] == talk.hub.answers[LEAVE] and len(say.links) == 2
    assert say.silent == [(next(f for f, _ in say.silent), False)]


def test_shared_steps_are_built_in_the_hubs_home_and_reached_with_the_speaker_forced():
    """A quest's line leading to a menu starts that menu's scene in Hub.home (the start-game quest), putting its
    speaker in home's Speaker alias (ALFA); the quest itself holds no scene of it."""
    lead = _said('L0', 'D0', 'Hello.', ChoiceCount='1', **{'Choice[0]': 'D1'})
    say = _say([lead, _said('L1', 'D1', 'Hi.')], {'D0': {}, 'D1': {}})
    talk = _quest(say)
    home = talk.hub.home = Conversations(say, {'FormID': 'G', 'EditorID': 'Greetings'}, 9, FORMS, talk.hub)
    line = talk._line(lead, False)
    subs = {s.type: s.data for s in _subs(line)}
    assert talk.scenes == [] and len(home.scenes) == 1
    assert struct.unpack('<i', subs['ALFA'])[0] == SPEAKER_ALIAS and talk.hub.scene_quests[
        struct.unpack('<I', subs['TSCE'])[0]] == 9


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
        talk = Conversations(say, quest, 1, FORMS, shared)
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
    """No line anywhere: only a count. A topic whose lines are all in an unbuilt quest, or whose lines do not
    convert, gets a readiness entry naming why."""
    entries = []
    infos = {'Q1': [_line('A1', 'D1', 'Q1')], 'Q2': [_line('B1', 'D2', 'Q2')]}
    dials = {d: {'EditorID': f'Topic{d}', 'DATA.Type': '0'} for d in ('D1', 'D2', 'D3')}
    say = SimpleNamespace(infos=infos, dials=dials, builder=SimpleNamespace(
        counts=Counter(), readiness=SimpleNamespace(add=lambda kind, owner, detail: entries.append(detail))))
    quest = {'FormID': 'Q1', 'EditorID': 'One'}
    talk = Conversations(say, quest, 1, FORMS, hub(say, [quest], {'One': 1}, set()))
    for dial in ('D3', 'D1', 'D2'):
        talk._unanswered(dial)
    assert say.builder.counts['choice FNV never answers (no line)'] == 1
    assert entries == ['TopicD1 (D1): condition', 'TopicD2 (D2): not built']
