"""FNV's NPC-to-NPC HELLO chats as Fallout 4 Actor Dialogue (ADIA) quests: which lines, their aliases, scene and node."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.base.support_records import NUM_QUESTS_TO_RUN, pack_story_node
from fo4_import.spike import actor_dialogue as A
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.conversation import GOODBYE, hub
from fo4_import.spike.quest import LISTENER_ALIAS, SPEAKER_ALIAS
from fo4_import.spike.say_once import SayOnce
from tes5_import.base.tes5_reader import subrecords, walk

#: FNV forms: Cass, a voice type, the Kings' faction; FNV's GOODBYE topic and Cass's answer topic.
CASS, VOICE, KINGS = 0x133FDD, 0x0717E1, 0x13FB6A
FORMS = {CASS: 0x0A000001, VOICE: 0x0A000002, KINGS: 0x0A000003}
GOODBYE_TOPIC, SASS = '000000D4', '0015A934'
IS_ID, VOICE_TYPE = C.FO4.index('GetIsID'), C.FO4.index('GetIsVoiceType')


def _test(func: str, p1: int, run_on: int = R.RUN_SUBJECT, op: int = 0) -> str:
    """One FNV condition as the export's raw hex."""
    return struct.pack('<B3xfIIIII', op, 1.0, C.FNV.index(func), p1, 0, run_on, 0).hex()


def _line(fid: str, dial: str, quest: str, tests: list = (), choices: list = (), flags: int = 0, **extra) -> dict:
    """An FNV INFO of topic `dial` in `quest` with raw `tests`, `choices` and DATA `flags`."""
    rec = {'FormID': fid, 'ParentDIAL': dial, 'QSTI.Quest': quest, 'DATA.Flags': str(flags),
           'ConditionCount': str(len(tests)), 'ChoiceCount': str(len(choices)), **extra}
    rec.update({f'Condition[{i}].Raw': raw for i, raw in enumerate(tests)})
    return {**rec, **{f'Choice[{i}]': c for i, c in enumerate(choices)}}


def _ctdas(subs: list) -> list:
    """[(op flags, value, function, param 1, run on)] of `subs`' CTDAs."""
    return [struct.unpack_from('<B3xfH2xI4xI', data) for tag, data in subs if tag == b'CTDA']


def _aliases(body: bytes) -> dict:
    """{alias id: its subrecords} of a QUST body."""
    out, alias = {}, None
    for tag, data in subrecords(body):
        alias = struct.unpack('<I', data)[0] if tag == b'ALST' else alias
        if alias is not None:
            out.setdefault(alias, []).append((tag, data))
    return out


def _build(lines: list) -> tuple:
    """(records by signature [(FormID, body)], counts) ActorDialogue writes for Hub `lines` (quests K, C)."""
    ids, written, counts = {}, [], Counter()
    builder = SimpleNamespace(counts=counts, new_id=lambda line, key=None: ids.setdefault(key or line, 0x0A001000 + len(ids)))
    builder.writer = SimpleNamespace(add_record=lambda sig, blob: written.append(blob))
    vanilla = b''.join(pack_story_node(fid, 'V', A.EVENT_NODE, prev, (1,)) for fid, prev in ((0x51, 0), (0x52, 0x51)))
    builder.fo4 = b'TES4' + bytes(20) + vanilla

    def info(rec, form_map, scene=(0, ''), flags=0, **said):
        """A stand-in for SayTopics.info: one response, the line's FormID in its notes."""
        return R.pack_info(builder.new_id(f'INFO {rec["FormID"]} {said.get("place")}'), flags, ('x',),
                           notes=rec['FormID'])
    quests = [{'FormID': 'K', 'EditorID': 'Kings', 'DATA.Priority': '40'}, {'FormID': 'C', 'EditorID': 'Cass'}]
    say = SimpleNamespace(infos={q: [r for r in lines if r['QSTI.Quest'] == q] for q in 'KC'}, dials={},
                          script_vars={}, once=SayOnce(), builder=builder, info=info)
    shared = hub(say, quests, {'Kings': 0x0A000100, 'Cass': 0x0A000200}, set())
    A.ActorDialogue(builder, say, FORMS, shared).write()
    out = {}
    for blob in written:
        for rec, _ in walk(blob, span=(0, len(blob))):
            out.setdefault(rec.sig.decode(), []).append((rec.form_id, rec.body))
    return out, counts


def _cass_hello(**extra) -> dict:
    """Cass's Freeside HELLO: a voice greets Cass, who answers SASS (or GOODBYE)."""
    tests = [_test('GetIsID', CASS, R.RUN_TARGET), _test('GetIsVoiceType', VOICE)]
    return _line('00156407', A.HELLO, 'K', tests, [SASS, GOODBYE_TOPIC], 3, **extra)


def test_chat_lines_are_hellos_offering_conversation_choices_and_keep_going_past_goodbye():
    """A HELLO with Link From blank whose Choices reach a topic with lines opens a chat: its engine Choices and
    Goodbye flag go; one with a Link From, or only engine Choices, does not."""
    answer = _line('A1', SASS, 'C', [_test('GetIsID', CASS)])
    lines = [_cass_hello(), _line('H2', A.HELLO, 'K', choices=[SASS], LinkFromCount='1'),
             _line('H3', A.HELLO, 'K', choices=[GOODBYE_TOPIC]), answer]
    say = SimpleNamespace(infos={'K': lines[:3], 'C': [answer]}, dials={})
    shared = hub(say, [{'FormID': 'K', 'EditorID': 'Kings'}, {'FormID': 'C', 'EditorID': 'Cass'}], {'Kings': 1, 'Cass': 2},
                 set())
    found = A.chat_lines(shared)
    assert list(found) == ['00156407']
    assert A.choices(found['00156407']) == [SASS] and not int(found['00156407']['DATA.Flags']) & GOODBYE


def test_sides_split_condition_groups_by_the_actor_they_test():
    """Groups testing no Target go to the speaker, groups testing only the Target to the listener, and a group
    testing both to neither."""
    subject, target = _test('GetIsVoiceType', VOICE), _test('GetIsID', CASS, R.RUN_TARGET)
    either = [_test('GetIsID', CASS, op=C.OR_NEXT), _test('GetInFaction', KINGS, R.RUN_TARGET)]
    rec = _line('H', A.HELLO, 'K', [subject, target] + either)
    assert A.sides(rec) == ([subject], [target])


def test_a_hello_chat_builds_an_adia_quest_its_scene_and_a_story_node_after_vanillas():
    """Cass's HELLO: aliases filled from the ADIA event (Speaker on the voice test, Listener on Cass as Subject and
    as the answer's speaker, neither the player), a scene beginning on quest start and stopping it with the HELLO
    then Cass's answer, and one quest node after the event's last child starting one quest a day."""
    out, counts = _build([_cass_hello(), _line('A1', SASS, 'C', [_test('GetIsID', CASS)])])
    assert counts['actor dialogue quests'] == 1 and counts['actor dialogue in several scenes'] == 0
    (quest, body), = out['QUST']
    subs = dict(subrecords(body))
    assert subs[b'ENAM'] == A.ADIA and subs[b'DNAM'][2] == 40 and struct.unpack('<I', subs[b'ANAM'])[0] == 1001
    aliases = _aliases(body)
    for alias in (SPEAKER_ALIAS, LISTENER_ALIAS):
        fill = dict(aliases[alias])
        assert fill[b'ALFE'] == A.ADIA and struct.unpack('<I', fill[b'ALFD'])[0] == 0x7FFFFFFF
    player = (0, 0.0, IS_ID, A.PLAYER_BASE, R.RUN_SUBJECT)
    assert _ctdas(aliases[SPEAKER_ALIAS]) == [player, (0, 1.0, VOICE_TYPE, FORMS[VOICE], R.RUN_SUBJECT)]
    cass = (0, 1.0, IS_ID, FORMS[CASS], R.RUN_SUBJECT)
    assert _ctdas(aliases[LISTENER_ALIAS]) == [player, cass, cass]
    (_, scene), = out['SCEN']
    scene_subs = subrecords(scene)
    flags = next(struct.unpack('<I', d)[0] for t, d in scene_subs if t == b'FNAM')
    assert flags & A.QUEST_SCENE == A.QUEST_SCENE and sum(t == b'HNAM' for t, _ in scene_subs) == 2 * 2
    assert [struct.unpack('<i', d)[0] for t, d in scene_subs if t == b'ALID'][-2:] == [SPEAKER_ALIAS, LISTENER_ALIAS]
    (_, node), = out['SMQN']
    node_subs = dict(subrecords(node))
    assert struct.unpack('<5I', b''.join(node_subs[t] for t in (b'PNAM', b'SNAM', b'DNAM', b'MNAM', b'NNAM'))) == (
        A.EVENT_NODE, 0x52, NUM_QUESTS_TO_RUN, 1, quest)
    assert struct.unpack('<f', node_subs[b'RNAM'])[0] == A.RESET


def test_answers_ending_the_chat_or_leading_on_keep_one_scene():
    """KingsUpTo: one answer ends the chat, another's Choice leads on; one scene of three phases, the ending answer
    ending it, so stopping the quest at the scene's end never cuts the reply."""
    reply = '00163C6C'
    lines = [_cass_hello(), _line('A1', SASS, 'C', [_test('GetIsID', CASS)]),
             _line('A2', SASS, 'C', [_test('GetIsID', CASS)], [reply]), _line('R1', reply, 'K')]
    out, counts = _build(lines)
    assert counts['actor dialogue in several scenes'] == 0
    (_, scene), = out['SCEN']
    assert sum(t == b'HNAM' for t, _ in subrecords(scene)) == 3 * 2
    ends = {dict(subrecords(b))[b'NAM2'].rstrip(b'\0'): struct.unpack_from('<H', dict(subrecords(b))[b'ENAM'])[0]
            & R.INFO_END_SCENE for _, b in out['INFO']}
    assert ends[b'A1'] and not ends[b'A2']


def test_a_hello_whose_alias_test_cannot_convert_builds_no_quest():
    """A Target test of a form the build lacks: no quest, no node, counted."""
    hello = _line('H', A.HELLO, 'K', [_test('GetIsID', 0x999999, R.RUN_TARGET)], [SASS])
    out, counts = _build([hello, _line('A1', SASS, 'C')])
    assert 'QUST' not in out and 'SMQN' not in out and counts['actor dialogue left out (alias condition)'] == 1
