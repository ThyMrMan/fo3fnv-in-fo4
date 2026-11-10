"""The dialogue menu audit (checks 1 and 2) over tiny built menus and their FNV lines."""

import struct

from fo4_import.spike.conditions import FO4
from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import menus as M
from tools.validate.preflight.plugin_index import PluginIndex

#: Built forms: two NPCs, a faction, the Say Once quest, caps, a scene, its player and NPC topics, the next scene.
JASON, ADA, DOCTORS, SAY_ONCE, CAPS = 0x000101, 0x000102, 0x000201, 0x000301, 0x000302
SCENE, NEXT_SCENE, P0, NPC = 0x000401, 0x000402, 0x000501, 0x000505
#: FNV forms: a topic, its quest, a second topic.
TOPIC, QUEST, OTHER = 0x0008D1A0, 0x0008D241, 0x0008D1A1


def rec(sig, fid, subs=(), parent_dial=0):
    """A built record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs], parent_dial=parent_dial)


def ctda(func: str, p1: int, value: float = 1.0, op: int = 0, run_on: int = 0, p2: int = 0) -> tuple:
    """An FO4 CTDA `func`(p1, p2) `op` `value` on `run_on` (0 player, 1 NPC)."""
    return 'CTDA', struct.pack('<B3xfH2xIIIIi', op, value, FO4.index(func), p1, p2, run_on, 0, -1)


def speaker(npc: int) -> tuple:
    """The NPC answering is `npc`."""
    return ctda('GetIsID', npc, run_on=1)


def said_by(npc_id: int) -> tuple:
    """An answer's own speaker test: the NPC saying it (its subject) is `npc_id`."""
    return ctda('GetIsID', npc_id, run_on=0)


def unsaid(stage: int) -> tuple:
    """A Say Once marker not yet done."""
    return ctda('GetStageDone', SAY_ONCE, 0.0, p2=stage)


def option(fid: int, prompt: str, conds=()) -> TES5Record:
    """A player option `prompt` (a pad when empty) on `conds`."""
    said = [('TRDA', bytes(20)), ('NAM1', prompt.encode() + b'\0')] if prompt else []
    tail = [('RNAM', prompt.encode() + b'\0')] if prompt else []
    return rec('INFO', fid, [('ENAM', bytes(4))] + said + list(conds) + tail, parent_dial=P0)


def answer(fid: int, flags: int = 0, tsce: int = 0, conds=()) -> TES5Record:
    """An NPC answer with ENAM `flags` on `conds`, starting scene `tsce` when given."""
    subs = [('ENAM', struct.pack('<HH', flags, 0)), ('TRDA', bytes(20)), ('NAM1', b'Hi.\0')] + list(conds)
    return rec('INFO', fid, subs + ([('TSCE', struct.pack('<I', tsce))] if tsce else []), parent_dial=NPC)


def scene(fid: int, player: int, npc: int) -> TES5Record:
    """A one-phase scene: a menu of topic `player`, answered from `npc`."""
    topics = [('PTOP', struct.pack('<I', player))] + [(s, bytes(4)) for s in ('NTOP', 'NETO', 'QTOP')]
    return rec('SCEN', fid, [('ANAM', struct.pack('<H', 3)), ('SNAM', bytes(4))] + topics
               + [('NPOT', struct.pack('<I', npc)), ('ANAM', b'')])


def npc(fid: int, factions=(), template: bool = False) -> TES5Record:
    """A built NPC in `factions`, templated when `template`."""
    return rec('NPC_', fid, [('SNAM', struct.pack('<I4x', f)) for f in factions]
               + ([('TPLT', bytes(4))] if template else []))


def ledger(tmp_path, options: list, copies: list):
    """A ledger naming `options` [(fid, FNV topic)] and line `copies` [(built fid, FNV line)]."""
    rows = [f'id\tFNV made\t"INFO prompt {t:08X} x at q (\'menu\',) {t:08X} for {QUEST:08X}"\t{f:06X}' for f, t in options]
    rows += [f'id\tFNV made\t"INFO {line:08X} 1 at q"\t{f:06X}' for f, line in copies]
    path = tmp_path / 'ledger.tsv'
    path.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return path


def fnv_line(fid: int, prompt: str, flags: int = 0, topic: int = TOPIC, **more) -> dict:
    """An exported FNV INFO of `topic`."""
    return {'FormID': f'{fid:08X}', 'ParentDIAL': f'{topic:08X}', 'Prompt': prompt, 'DATA.Flags': str(flags), **more}


def run(tmp_path, options: list, answers: list, lines: list, extra=(), unfixed=()) -> dict:
    """{(topic, kind): rows} of the audit over one menu: `options` [(record, FNV topic)], their `answers`
    [(record, FNV line)], FNV `lines`, `extra` built records."""
    index = PluginIndex([scene(SCENE, P0, NPC)] + [o for o, _ in options] + [a for a, _ in answers] + list(extra),
                        fo4=True)
    path = ledger(tmp_path, [(o.form_id, t) for o, t in options], [(a.form_id, line) for a, line in answers])
    source = M.Source(lines, [{'FormID': f'{TOPIC:08X}', 'EditorID': 'VMS01Topic', 'FULL': 'Topic'},
                              {'FormID': f'{OTHER:08X}', 'EditorID': 'VMS01Other', 'FULL': 'Other'}])
    copies = {a.form_id: (line, 1) for a, line in answers}
    audit = M.MenuAudit('Test.esm', index, source, copies, M.Speakers(index, set(unfixed)))
    audit.run(M.read_menus(index, M.prompt_topics(index, path)))
    return {(k[1], k[2]): rows for k, rows in audit.found.items()}


def two(tmp_path, first_conds, second_conds, extra=(), unfixed=()) -> list:
    """The check 2 rows of a topic offering two options on these conditions."""
    found = run(tmp_path, [(option(0x601, 'Sorry. Not interested.', first_conds), TOPIC),
                           (option(0x602, 'Like I said, not interested.', second_conds), TOPIC)],
                [(answer(0x701), 0x8D1AB), (answer(0x702), 0xCD849)],
                [fnv_line(0x8D1AB, 'Sorry. Not interested.', 1), fnv_line(0xCD849, 'Like I said, not interested.', 1)],
                extra, unfixed)
    return found.get(('VMS01Topic', 'two options'), [])


def test_jason_brights_pair_is_found_until_the_later_option_waits_for_the_first_to_be_said(tmp_path):
    """Before the fix both options showed while the Say Once first was unsaid; after it the second waits."""
    first = [speaker(JASON), unsaid(10001)]
    rows = two(tmp_path, first, [speaker(JASON)])
    assert rows and 'GetStageDone(00000301, 10001)=0' in rows[0] and ' for 00000101 when' in rows[0]
    assert two(tmp_path, first, [speaker(JASON), ctda('GetStageDone', SAY_ONCE, 1.0, p2=10001)]) == []


def test_doc_mitchells_caps_pair_is_found_until_the_later_option_needs_fewer_than_100_caps(tmp_path):
    """"Here's 100 caps" and "I don't have 100 caps" showed together to a player holding 100."""
    pay = [ctda('GetItemCount', CAPS, 100.0, op=0x60)]
    rows = two(tmp_path, pay, [])
    assert rows and 'GetItemCount' in rows[0]
    assert two(tmp_path, pay, [ctda('GetItemCount', CAPS, 100.0, op=0x80)]) == []


def test_a_speakers_fixed_factions_settle_the_pair_unless_a_script_changes_them(tmp_path):
    """Ada is not a doctor, so her option never meets the doctors' one; it does once she is, or once a script
    can make her one, or when her record is a template's."""
    ada, doctors = [speaker(ADA)], [ctda('GetInFaction', DOCTORS, run_on=1)]
    assert two(tmp_path, ada, doctors, extra=[npc(ADA)]) == []
    assert two(tmp_path, ada, doctors, extra=[npc(ADA, [DOCTORS])])
    assert two(tmp_path, ada, doctors, extra=[npc(ADA)], unfixed=[DOCTORS])
    assert two(tmp_path, ada, doctors, extra=[npc(ADA, template=True)])


def test_structure_finds_a_loose_pad_a_shared_prompt_a_wrong_prompt_and_an_unmarked_say_once(tmp_path):
    """Cliff Briscoe's pad without its option's conditions; two topics showing one text; a prompt FNV does not
    show; a Say Once answer without its marker script."""
    found = run(tmp_path, [(option(0x601, 'Who are you?', [speaker(JASON)]), TOPIC),
                           (option(0x603, '', []), TOPIC),
                           (option(0x602, 'Who are you?', []), OTHER)],
                [(answer(0x701, conds=[said_by(JASON)]), 0x8D1AB), (answer(0x702, conds=[said_by(JASON)]), 0x8D1AC),
                 (answer(0x703), 0x8D1AD)],
                [fnv_line(0x8D1AB, 'Who are you?', 4), fnv_line(0x8D1AC, 'Who are you?'),
                 fnv_line(0x8D1AD, 'What is this place?', topic=OTHER)])
    assert set(found) == {('VMS01Topic', 'pad gate'), ('VMS01Topic', 'say once unmarked'),
                          ('VMS01Topic', 'duplicate prompt'), ('VMS01Other', 'prompt differs')}


def test_one_prompt_in_two_topics_for_different_speakers_is_not_a_duplicate(tmp_path):
    """Two topics may share a text when no speaker sees both."""
    found = run(tmp_path, [(option(0x601, 'Who are you?', [speaker(JASON)]), TOPIC),
                           (option(0x602, 'Who are you?', [speaker(ADA)]), OTHER)],
                [(answer(0x701, conds=[said_by(JASON)]), 0x8D1AB), (answer(0x702, conds=[said_by(ADA)]), 0x8D1AD)],
                [fnv_line(0x8D1AB, 'Who are you?'), fnv_line(0x8D1AD, 'Who are you?', topic=OTHER)])
    assert found == {}


def test_a_talking_as_list_holds_only_its_actor_so_another_npc_never_sees_its_prompt(tmp_path):
    """Yes Man's "What is this place?" passes for Yes Man or a talker in his talking-as list; Primm Slim (Jason
    here) is not in it, so his own "What is this place?" is no duplicate. Ada, whose list it is, still meets it."""
    talking = rec('FLST', 0x000801, [('EDID', b'TES4TalkingAs_00000102\0'), ('LNAM', struct.pack('<I', ADA))])
    yes_man = [ctda('GetIsID', ADA, op=1, run_on=1), ctda('IsInList', talking.form_id, run_on=1)]
    yes_man_says = [ctda('GetIsID', ADA, op=1, run_on=0), ctda('IsInList', talking.form_id, run_on=0)]

    def found(npc_id: int) -> dict:
        """The audit over Yes Man's option beside `npc_id`'s own one."""
        return run(tmp_path, [(option(0x601, 'What is this place?', [speaker(npc_id)]), TOPIC),
                              (option(0x602, 'What is this place?', yes_man), OTHER)],
                   [(answer(0x701, conds=[said_by(npc_id)]), 0x8D1AB), (answer(0x702, conds=yes_man_says), 0x8D1AD)],
                   [fnv_line(0x8D1AB, 'What is this place?'), fnv_line(0x8D1AD, 'What is this place?', topic=OTHER)],
                   extra=[npc(JASON), npc(ADA), talking])
    assert found(JASON) == {} and ('VMS01Topic', 'duplicate prompt') in found(ADA)


def test_answers_out_of_fnv_order_or_of_another_topic_are_found(tmp_path):
    """An option's answers follow FNV's line order and belong to its topic."""
    pads = [option(0x601, 'Hi.', []), option(0x603, '', [])]
    found = run(tmp_path, [(pads[0], TOPIC), (pads[1], TOPIC)],
                [(answer(0x701), 0x8D1AC), (answer(0x702), 0x8D1AB)],
                [fnv_line(0x8D1AB, 'Hi.'), fnv_line(0x8D1AC, 'Hi.', topic=OTHER)])
    assert set(found) == {('VMS01Topic', 'answers out of order'), ('VMS01Topic', 'answer of another topic')}


def test_one_fnv_line_answering_twice_is_found_and_a_shared_line_keeps_no_order(tmp_path):
    """A line the topic both owns and shares is copied twice; a shared line's place is not FNV's order."""
    line = fnv_line(0x8D1AB, 'Hi.')
    found = run(tmp_path, [(option(0x601, 'Hi.', []), TOPIC), (option(0x603, '', []), TOPIC)],
                [(answer(0x701), 0x8D1AB), (answer(0x702), 0x8D1AB)], [line])
    assert set(found) == {('VMS01Topic', 'answer repeated')}
    source = M.Source([fnv_line(0x8D1AC, 'Hi.', topic=OTHER), line],
                      [{'FormID': f'{TOPIC:08X}', 'SharedInfoCount': '1', 'SharedInfo[0].Info': '0008D1AC'}])
    assert source.shared[TOPIC] == {0x8D1AC}


def test_edges_compare_where_an_answer_leads_with_where_its_fnv_line_leads():
    """Goodbye ends; Choices open a menu of those topics; Follow Ups play lines; a loop's end is review."""
    assert M.edge_kind(('end',), None, set()) == ('', set())
    assert M.edge_kind(('end',), ('menu', 1), set()) == ('goes on where FNV ends', set())
    assert M.edge_kind(('menu', {TOPIC}), None, set()) == ('ends where FNV goes on', set())
    assert M.edge_kind(('menu', {TOPIC}), ('line', 1), set()) == ('next step differs', set())
    assert M.edge_kind(('menu', {TOPIC}), ('menu', 1), {TOPIC, OTHER}) == ('choices differ', {OTHER})
    assert M.edge_kind(('list',), None, set()) == ('', set())
    assert 'ends where FNV goes on' in M.REVIEW


def test_a_goodbye_answer_that_starts_another_scene_is_found(tmp_path):
    """FNV's Goodbye ends the talk; a copy starting another scene does not."""
    found = run(tmp_path, [(option(0x601, 'Bye.', []), TOPIC)], [(answer(0x701, tsce=NEXT_SCENE), 0x8D1AB)],
                [fnv_line(0x8D1AB, 'Bye.', 1)], extra=[scene(NEXT_SCENE, 0x000502, 0x000506)])
    assert ('VMS01Topic', 'goes on where FNV ends') in found


def test_prompt_keys_name_options_and_pads_by_fnv_topic(tmp_path):
    """The ledger's prompt keys give each option and pad its FNV topic and quest; other keys are not prompts."""
    index = PluginIndex([option(0x601, 'Hi.'), option(0x602, '')], fo4=True)
    path = tmp_path / 'ledger.tsv'
    path.write_text(f'id\tFNV made\t"INFO prompt {TOPIC:08X} Hi. at 000E61A4 (\'menu\', (\'{TOPIC:08X}\',)) '
                    f'{TOPIC:08X} for {QUEST:08X}"\t000601\n'
                    f'id\tFNV made\t"INFO prompt {TOPIC:08X} Hi. at 000E61A4 (\'menu\',) {TOPIC:08X} for '
                    f'{QUEST:08X} pad 1"\t000602\n'
                    f'id\tFNV made\t"INFO {TOPIC:08X} 1 at x"\t000603\n', encoding='utf-8')
    assert M.prompt_topics(index, path) == {0x601: (TOPIC, f'{QUEST:08X}'), 0x602: (TOPIC, f'{QUEST:08X}')}


#: A built global standing for FNV's KnowVulpes; the FNV lines of Vulpes's two answers.
KNOW, LESSON0, LESSON1 = 0x000303, 0x0008D1B0, 0x0008D1B1


def vulpes(tmp_path, gate: list) -> dict:
    """Check 3's rows of Vulpes's "What lessons did you teach here?" on `gate`: two Say Once answers, one per
    KnowVulpes value."""
    know = [[ctda('GetGlobalValue', KNOW, float(v)), unsaid(10001 + v)] for v in (0, 1)]
    found = run(tmp_path, [(option(0x601, 'What lessons did you teach here?', gate), TOPIC), (option(0x603, ''), TOPIC)],
                [(answer(0x701, conds=know[0]), LESSON0), (answer(0x702, conds=know[1]), LESSON1)],
                [fnv_line(LESSON0, 'What lessons did you teach here?', 4),
                 fnv_line(LESSON1, 'What lessons did you teach here?', 4)])
    return {kind: rows for (_, kind), rows in found.items() if kind in ('empty', 'hidden', 'wrong prompt')}


def or_next(cond: tuple) -> tuple:
    """`cond` ORed with the condition after it."""
    return cond[0], bytes([cond[1][0] | 1]) + cond[1][1:]


def test_vulpes_option_showing_after_its_answer_was_said_is_empty_until_each_answer_gates_it(tmp_path):
    """The 2026-11-09 bug: "some answer passes" ANDed with "some answer unsaid" held with neither answer able to
    play; distributing the groups per answer leaves no such state."""
    k0, k1 = ctda('GetGlobalValue', KNOW, 0.0), ctda('GetGlobalValue', KNOW, 1.0)
    loose = [or_next(k0), k1, or_next(unsaid(10001)), unsaid(10002)]
    rows = vulpes(tmp_path, loose)
    assert list(rows) == ['empty'] and 'GetStageDone(00000301, 10001)=1' in rows['empty'][0]
    each = [or_next(k0), k1, or_next(k0), unsaid(10002), or_next(unsaid(10001)), k1,
            or_next(unsaid(10001)), unsaid(10002)]
    assert vulpes(tmp_path, each) == {}


def test_an_answer_that_can_play_with_its_option_hidden_is_found(tmp_path):
    """A gate tighter than its answers hides a line FNV would offer."""
    rows = vulpes(tmp_path, [ctda('GetGlobalValue', KNOW, 0.0), unsaid(10001)])
    assert list(rows) == ['hidden'] and '00000702 plays' in rows['hidden'][0]


def test_an_option_showing_while_an_earlier_line_of_another_passes_is_a_wrong_prompt(tmp_path):
    """FNV shows the first passing line's prompt; with the earlier option hidden (a test its line lacks) while its
    line passes, the later one shows in its place."""
    first, later = [ctda('GetGlobalValue', KNOW, 1.0), unsaid(10005)], []
    found = run(tmp_path, [(option(0x601, 'First.', first), TOPIC), (option(0x602, 'Later.', later), TOPIC)],
                [(answer(0x701, conds=[ctda('GetGlobalValue', KNOW, 1.0)]), 0x8D1AB), (answer(0x702), 0x8D1AC)],
                [fnv_line(0x8D1AB, 'First.'), fnv_line(0x8D1AC, 'Later.')])
    assert ('VMS01Topic', 'wrong prompt') in found
    assert '"Later." (00000602), 00000701 of "First." plays' in found[('VMS01Topic', 'wrong prompt')][0]
