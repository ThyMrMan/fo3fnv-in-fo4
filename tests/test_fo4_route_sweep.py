"""The layer 2 route sweep without a game: routes from the source model, and the case lines they become.

See: docs/fork/fo4_test_layers_plan.md#l2
"""
import struct
from types import SimpleNamespace

from tools.live import fo4_quest_routes as R
from tools.live import fo4_route_steps as S
from tools.live import fo4_stage_sweep as W
from tools.live import fo4_story_cases as C
from tools.validate.preflight.quest_source import (Setter, SourceInfo, decode_condition, find_fighting,
                                                    find_objectives, find_says, find_variables, line_needs)

#: Topics: greeting, a choice of it, top-level, the greeting's follow-up's, its choice, a choice followed by greeting.
GREET, ASK, TOP, MORE, END, PICK = 0x100, 0x200, 0x300, 0x400, 0x500, 0x600
#: The speaker's base and its placed reference.
SUNNY, SUNNY_REF = 0x50, 0x51


def is_sunny() -> tuple:
    """A decoded `GetIsID Sunny == 1` condition on the speaker."""
    return decode_condition(struct.pack('<B3xfH2xIII', 0, 1.0, 72, SUNNY, 0, 0))


#: `GetObjectiveCompleted Q 10 == 1` (quest Q is 0x90), as a CTDA.
OBJECTIVE_10 = struct.pack('<B3xfH2xIII', 0, 1.0, 420, 0x90, 10, 0)


def routes(monkeypatch) -> R.Routes:
    """Routes over a source where Sunny's greeting (once objective 10 is done) offers ASK, whose line sets a
    stage, beside a top-level line."""
    infos = {1: SourceInfo(1, GREET, 0, [is_sunny(), decode_condition(OBJECTIVE_10)], [ASK, PICK], [],
                           raw=(b'', OBJECTIVE_10), follow_ups=(4,)),
             8: SourceInfo(8, TOP, 0, [is_sunny()], [GREET], []),
             6: SourceInfo(6, GREET, 0, [is_sunny()], [], []),
             7: SourceInfo(7, PICK, 0, [is_sunny()], [], [], follow_ups=(6,)),
             2: SourceInfo(2, ASK, 0, [is_sunny()], [], []),
             3: SourceInfo(3, TOP, 0, [is_sunny()], [], []),
             4: SourceInfo(4, MORE, 0, [is_sunny()], [END], []),
             5: SourceInfo(5, END, 0, [is_sunny()], [], [])}
    source = SimpleNamespace(
        infos=infos, dials={GREET: ('GREETING', 0, 0), ASK: ('Ask', 0, 0), TOP: ('Top', 0, R.TOP_LEVEL),
                            MORE: ('More', 0, 0), END: ('End', 0, 0), PICK: ('Pick', 0, 0)},
        external_topics=set(), disabled={0x72}, prompts={2: 'Teach me.', 5: 'Sure.', 7: 'Enough.'},
        topic_names={TOP: 'Anything new?'},
        display_names={SUNNY: 'Sunny Smiles'}, placed={SUNNY: [SUNNY_REF], 0x70: [0x71], 0x74: [0x75]},
        quest_fids={0x90: 'Q'}, places={0x71: (0x80, 0x81, -68198.0, 5050.9, False),
                                         0x75: (0x80, 0x82, -68000.0, 5900.0, False)},
        space_ids={0x80: 'WastelandNV'}, parents={0x71: 0x72}, script_fids={'triggerscript': 0x60, 'targetscript': 0x61},
        fighting_sites=[Setter('script', 'TriggerScript', 'OnTriggerEnter player', '', 'fighting')], variables={})
    monkeypatch.setattr(R, 'script_bases', lambda export_dir: {0x60: [0x70], 0x61: [0x74]})
    return R.Routes(source, 'export')


def test_a_line_is_reached_by_its_speaker_and_the_prompts_from_the_greeting(monkeypatch):
    """A greeting line needs only the talk; a line its greeting offers, that line's prompt; a top-level line,
    its topic's name; each with the speaker its GetIsID allows."""
    found = routes(monkeypatch)
    assert found.line('00000001') == {'refs': ['00000051'], 'disabled': False, 'name': 'Sunny Smiles',
                                      'prompts': [], 'needs': [('completed', 'q', 10)], 'more': []}
    assert found.line('00000002')['prompts'] == ['Teach me.']
    assert found.line('00000003')['prompts'] == ['Anything new?']


def test_a_way_needs_the_objectives_its_lines_test(monkeypatch):
    """The greeting's choice wants its objective; a top-level line, none."""
    found = routes(monkeypatch)
    assert (found.line('00000002')['needs'], found.line('00000003')['needs']) == ([('completed', 'q', 10)], [])


def test_an_objective_is_set_by_a_setobjective_without_a_zero_flag():
    """`SetObjectiveCompleted VCG02 10 1` sets it, block and all; a 0 flag clears one."""
    text = 'Begin OnHitWith\r\nSetObjectiveCompleted VCG02 10 1\r\nSetObjectiveDisplayed VCG02 20 0\r\nEnd'
    assert [(need, block) for need, _raw, block in find_objectives(text)] == [(('completed', 'vcg02', 10),
                                                                               'OnHitWith')]


def test_a_quest_variable_a_line_tests_is_a_need_set_by_its_set_lines():
    """Ringo's Powder Gangers line wants `GetQuestVariable VFreeformGoodsprings 17 == 1` (bKnowRingoHiding); Trudy's
    `set VFreeformGoodsprings.bKnowRingoHiding to 1` sets it; the case checks the mirror global, else sets it."""
    raw = struct.pack('<B3xfH2xIII', 0, 1.0, 79, 0x90, 17, 0)
    info = SourceInfo(9, TOP, 0, [decode_condition(raw)], [], [], raw=(raw,))
    need = ('variable', 'q', 'bknowringohiding', 1.0)
    assert line_needs(info, {0x90: 'Q'}, {('q', 17): 'bKnowRingoHiding'}) == [need]
    text = 'set Q.bKnowRingoHiding to 1 ; Trudy told the player\r\nset Q.nCount to nCount + 1'
    assert [found for found, _raw, _block in find_variables(text)] == [need]
    talk = dict(TALK, live=True, route=dict(TALK['route'], needs=[{'need': 'variable Q bKnowRingoHiding 1',
                                                                   'by': []}]))
    done = 'GetGlobalValue TES4QVar_Q_bKnowRingoHiding == 1'
    assert S.need_steps([('talk', talk)]) == ['until 10 ' + done,
                                              'unless %s | check run set TES4QVar_Q_bKnowRingoHiding to 1' % done]


def test_a_scripts_say_sites_keep_their_block():
    """A SayTo in OnTriggerEnter player is a site; a commented one isn't."""
    text = 'BEGIN OnTriggerEnter player\r\n\tSunnyREF.SayTo Player VCG02SunnyBark\r\n;\tSunnyREF.Say VCG02Other\r\nEND'
    assert [(words, block) for words, _raw, block in find_says(text)] == [(('player', 'vcg02sunnybark'),
                                                                          'OnTriggerEnter player')]


def test_an_objective_a_talk_needs_is_set_first_by_its_site_else_from_the_console():
    """The bottles shot until objective 10 is done (VCG02TargetSCRIPT's OnHitWith, at 3 hits); its mirror global
    checked, the objective and global set when still 0; then Sunny's talk."""
    bottles = {'kind': 'object script', 'script': 'TargetScript', 'live': True,
               'route': {'step': 'shoot', 'refs': ['00000071', '00000072']}}
    talk = dict(TALK, live=True, route=dict(TALK['route'], needs=[{'need': 'completed Q 10', 'by': [bottles]}]))
    lines = S.stage_lines('FalloutNV.esm', quest({25: [talk]}), quest({25: [talk]})['stages'][0], set())
    steps = [line.split(' | ', 1)[1].rsplit(' | ', 1)[0].removeprefix('check ') for line in lines
             if line.startswith('unless')]
    unset = 'unless GetGlobalValue TES4ObjDone_Q_10 == 1 | check run '
    done = 'unless GetGlobalValue TES4ObjDone_Q_10 == 1 | check '
    assert steps[:7] == [done + 'walk 30 {FalloutNV.esm:00000071} 600', done + 'shoot 1 {FalloutNV.esm:00000071}',
                         done + 'shoot 1 {FalloutNV.esm:00000072}', 'until 10 GetGlobalValue TES4ObjDone_Q_10 == 1',
                         unset + 'setobjectivecompleted FNV_Q 10 1', unset + 'set TES4ObjDone_Q_10 to 1',
                         'run player.moveto {FalloutNV.esm:00000051}']


def test_a_line_an_objective_needs_is_said_in_a_talk_of_its_own_first():
    """Sunny's "Enough." sets the objective her "Teach me." greeting wants: two talks, "Enough." first, skipped
    once the objective is done."""
    first = dict(TALK, info='00000007', live=True, route=dict(TALK['route'], prompts=['Enough.']))
    talk = dict(TALK, live=True, route=dict(TALK['route'], needs=[{'need': 'completed Q 10', 'by': [first]}]))
    guard = 'unless GetGlobalValue TES4ObjDone_Q_10 == 1 | check '
    steps = [s.removeprefix(guard) for s in talk_steps([talk])]
    assert [s for s in steps if s.startswith('choose')] == ['choose 20 Enough.', 'choose 20 Teach me.']
    assert steps.count('bye') == 2 and guard + 'choose 20 Enough.' in talk_steps([talk])


def test_a_follow_up_is_said_on_from_the_line_it_follows(monkeypatch):
    """A follow-up needs no pick; its choice needs its prompt."""
    found = routes(monkeypatch)
    assert (found.line('00000004')['prompts'], found.line('00000005')['prompts']) == ([], ['Sure.'])


def test_a_greeting_line_said_as_a_follow_up_is_reached_both_ways(monkeypatch):
    """A greeting line some line follows up: greeted, else that line picked."""
    route = routes(monkeypatch).line('00000006')
    assert (route['prompts'], route['more']) == ([], [['Enough.']])


def test_a_first_meeting_greeting_is_got_through_before_the_topic_list(monkeypatch):
    """Ringo's Say Once greeting offers only its own choices; its answer with none brings back the topic list."""
    infos = {1: SourceInfo(1, GREET, 0, [is_sunny()], [ASK], [], flags=R.SAY_ONCE),
             2: SourceInfo(2, ASK, 0, [is_sunny()], [], []), 3: SourceInfo(3, TOP, 0, [is_sunny()], [], [])}
    source = SimpleNamespace(
        infos=infos, dials={GREET: ('GREETING', 0, 0), ASK: ('Ask', 0, 0), TOP: ('Top', 0, R.TOP_LEVEL)},
        external_topics=set(), disabled=set(), prompts={2: 'Not an enemy.'}, topic_names={TOP: 'Anything new?'},
        display_names={}, placed={SUNNY: [SUNNY_REF]}, quest_fids={}, script_fids={}, variables={})
    monkeypatch.setattr(R, 'script_bases', lambda export_dir: {})
    route = R.Routes(source, 'export').line('00000003')
    assert (route['prompts'], route['more']) == (['Anything new?'], [['Not an enemy.', 'Anything new?']])


def test_a_talk_takes_whichever_way_is_listed_in_one_conversation():
    """Three ways, one talk: each depth's choose lists every way's prompt there, and `-` (nothing to pick) once a
    shorter way has ended (the greeting's before any pick)."""
    setter = dict(TALK, route=dict(TALK['route'], prompts=[], more=[['Enough.'], ['Sure.', 'Okay.']]))
    steps = S.route_steps('FalloutNV.esm', 'talk', setter)
    assert steps.count('bye') == 1
    assert [s for s in steps if s.startswith('choose')] == ['choose 20 Enough. || Sure. || -',
                                                            'choose 20 Okay. || -']


def test_an_object_scripts_route_is_the_players_part_only(monkeypatch):
    """A trigger the player walks into gets the trigger step, the placed references, the cell to load (not
    persistent) and the disabled enable parent to enable; one another actor must enter gets no step, its actor."""
    found = routes(monkeypatch)
    assert found.script('TriggerScript', 'OnTriggerEnter player') == {
        'step': 'trigger', 'refs': ['00000071'], 'bases': ['00000070'],
        'goto': {'world': 'FNV_WastelandNV', 'x': -17, 'y': 1}, 'enable': '00000072'}
    assert found.script('TriggerScript', 'OnTrigger SunnyREF') == {'step': None, 'refs': ['00000071'],
                                                                  'bases': ['00000070'], 'actor': 'SunnyREF'}


def test_the_bottles_wait_for_their_enabler_said_in_a_trigger():
    """Stage 25's talk needs objective 10, set by shooting the bottles, whose enable parent Sunny's bark enables,
    a bark only her trigger says: walk into the trigger, shoot, then talk; a trigger Sunny enters is waited for."""
    trigger = {'kind': 'object script', 'script': 'PatrolTrigger', 'live': True,
               'route': {'step': 'trigger', 'refs': ['00000073']}}
    bark = {'kind': 'info', 'info': '00000008', 'live': True, 'route': {'refs': ['00000051'], 'prompts': None,
                                                                         'said_by': [trigger]}}
    bottles = {'kind': 'object script', 'script': 'TargetScript', 'live': True,
               'route': {'step': 'shoot', 'refs': ['00000071'], 'enable': '00000072', 'enabled_by': [bark]}}
    talk = dict(TALK, live=True, route=dict(TALK['route'], needs=[{'need': 'completed Q 10', 'by': [bottles]}]))
    steps = talk_steps([talk])
    done = 'unless GetGlobalValue TES4ObjDone_Q_10 == 1 | check '
    assert steps[:4] == [done + 'run player.moveto {FalloutNV.esm:00000073}', done + 'walk 30 {FalloutNV.esm:00000073}',
                         done + 'walk 30 {FalloutNV.esm:00000071} 600', done + 'shoot 1 {FalloutNV.esm:00000071}']
    patrol = {'kind': 'object script', 'script': 'PatrolTrigger', 'live': True,
              'route': {'step': None, 'refs': ['00000073'], 'actor': 'SunnyREF'}}
    assert S.candidates(quest({}), [patrol, bark], set()) == [('trigger', trigger), ('wait', patrol)]


def test_fighting_is_turned_on_by_enableplayercontrols_unless_its_third_flag_is_0():
    """All 1s and a bare call enable fighting; `0 0 0 0 1` doesn't."""
    text = ('Begin OnTriggerEnter player\r\nEnablePlayerControls 1 1 1 1 1 1\r\nEnablePlayerControls\r\n'
            'EnablePlayerControls 0 0 0 0 1\r\n;EnablePlayerControls\r\nEnd')
    assert [block for _raw, block in find_fighting(text)] == ['OnTriggerEnter player'] * 2


def test_a_shot_needs_the_nearest_trigger_turning_fighting_on(monkeypatch):
    """The bottles' route keeps the route of the trigger enabling fighting in their world; another world's is
    none."""
    controls = routes(monkeypatch).script('TargetScript', 'OnHitWith')['controls']
    assert controls == {'step': 'trigger', 'refs': ['00000071'], 'bases': ['00000070'],
                        'goto': {'world': 'FNV_WastelandNV', 'x': -17, 'y': 1}, 'enable': '00000072',
                        'script': 'TriggerScript', 'block': 'OnTriggerEnter player'}
    assert R.gap((0x80, 1, 0.0, 0.0, False), (0x83, 1, 0.0, 0.0, False)) == float('inf')


def test_a_chain_turns_fighting_on_once_right_after_its_load(tmp_path):
    """A later quest's shot needs the trigger: the first case walks into it after `load`, before any quest."""
    trigger = {'step': 'trigger', 'refs': ['00000071'], 'goto': {'world': 'FNV_WastelandNV', 'x': -17, 'y': 1},
               'script': 'TriggerScript', 'block': 'OnTriggerEnter player'}
    shot = {'kind': 'object script', 'script': 'TargetScript',
            'route': {'step': 'shoot', 'refs': ['00000075'], 'controls': trigger}}
    first, second = quest({10: []}) | {'source': 'A', 'fo4': 'FNV_A'}, quest({5: [shot]}) | {'source': 'B'}
    W.write_sweep({'game': 'FalloutNV.esm', 'quests': [first, second]}, tmp_path, 'f3nvtest_start', ['a', 'b'],
                  False, True, True)
    lines = (tmp_path / 'q_01_A.f4test').read_text(encoding='utf-8').splitlines()
    assert lines[2:8] == ['load f3nvtest_start', '# controls: TriggerScript OnTriggerEnter player',
                          'check run cow FNV_WastelandNV -17 1 | controls: TriggerScript',
                          'check wait 2 | controls: TriggerScript', 'check ready 120 | controls: TriggerScript',
                          'check run player.moveto {FalloutNV.esm:00000071} | controls: TriggerScript']
    assert '# controls' not in (tmp_path / 'q_02_B.f4test').read_text(encoding='utf-8')


def test_a_temporary_targets_cell_is_loaded_before_its_step():
    """The bottles (not persistent, cell -17,1 of WastelandNV): cow there, wait for the load, walk near, shoot."""
    route = {'step': 'shoot', 'refs': ['00000071'], 'goto': {'world': 'FNV_WastelandNV', 'x': -17, 'y': 1}}
    assert S.route_steps('FalloutNV.esm', 'shoot', {'route': route}) == [
        'run cow FNV_WastelandNV -17 1', 'wait 2', 'ready 120', 'walk 30 {FalloutNV.esm:00000071} 600',
        'shoot 1 {FalloutNV.esm:00000071}']


def quest(setters_by_stage: dict, starts=()) -> dict:
    """A plan quest Q (FO4 FNV_Q) whose stages have these setters, all live."""
    return {'source': 'Q', 'fo4': 'FNV_Q', 'built': True, 'starts': list(starts), 'start_enabled': False,
            'started': bool(starts),
            'stages': [{'stage': n, 'reached': True, 'built': True,
                        'setters': [dict(s, live=True) for s in setters]} for n, setters in setters_by_stage.items()]}


TALK = {'kind': 'info', 'info': '00000002',
        'route': {'refs': ['00000051'], 'name': 'Sunny Smiles', 'prompts': ['Teach me.']}}


def test_a_stage_set_by_a_line_is_talked_to_then_checked_with_setstage_after():
    """A line's stage: moveto, look, talk, choose, hear, bye (each soft, skipped once the stage is done), the
    stage checked, a setstage that keeps the case going; the same line setting a later stage is waited for, a
    stage with no route is a gap."""
    q = quest({10: [TALK], 20: [TALK], 30: [{'kind': 'object script', 'script': 'X', 'route': {'step': None}}]})
    lines = C.parse('\n'.join(['case Q'] + [line for e in q['stages'] for line in
                                            S.stage_lines('FalloutNV.esm', q, e, set())] + ['end']), {})
    guarded = [rest.split(' | ') for _n, verb, rest in lines[0].steps if verb == 'unless']
    assert {g[0] for g in guarded[:7]} == {'GetStageDone FNV_Q 10 == 1'}
    steps = [g[1].removeprefix('check ') for g in guarded]
    assert steps[:7] == ['run player.moveto {FalloutNV.esm:00000051}', 'look {FalloutNV.esm:00000051}',
                         'talk 30 {FalloutNV.esm:00000051}', 'look {FalloutNV.esm:00000051}', 'choose 20 Teach me.',
                         'heard 60 Sunny Smiles 00000002', 'bye']
    before = set()
    kinds = [S.ROUTE.match(S.stage_lines('FalloutNV.esm', q, e, before)[0]).group(1) for e in q['stages']]
    assert kinds == ['talk', 'wait', 'gap']


TRUDY = {'kind': 'info', 'info': '00000003', 'live': True,
         'route': {'refs': ['00000061'], 'disabled': True, 'name': 'Trudy', 'prompts': [],
                   'enabled_by': [dict(TALK, live=True)]}}


def test_a_line_whose_speaker_starts_disabled_is_tried_last():
    """Trudy (disabled until VCG02 ends) after Sunny, for VCG02's end."""
    sunny = dict(TALK, live=True)
    assert S.candidates(quest({}), [TRUDY, sunny], set()) == [('talk', sunny), ('talk', TRUDY)]


def talk_steps(completes: list) -> list:
    """The checked steps of quest Q's completion block over `completes`."""
    lines = S.complete_lines('FalloutNV.esm', quest({}) | {'completes': completes}, set())
    return [line.split(' | ', 1)[1].rsplit(' | ', 1)[0].removeprefix('check ') for line in lines
            if line.startswith('unless')][:-1]


def test_a_disabled_speaker_is_enabled_first_by_the_line_that_enables_her():
    """Sunny's line enables Trudy: talk to Sunny (unless Trudy is enabled already), wait for Trudy, then talk to
    her."""
    steps = talk_steps([TRUDY, dict(TRUDY, info='00000009')])
    enabled = 'unless {FalloutNV.esm:00000061}.GetDisabled == 0 | check '
    assert steps[4:7] == [enabled + 'choose 20 Teach me.', enabled + 'heard 60 Sunny Smiles 00000002', enabled + 'bye']
    assert steps[7:9] == ['until 60 {FalloutNV.esm:00000061}.GetDisabled == 0',
                          'run player.moveto {FalloutNV.esm:00000061}']
    assert steps[-3:] == ['heard 60 Trudy 00000003,00000009', 'bye', 'until 10 GetQuestCompleted FNV_Q == 1']


def test_lines_of_one_speaker_share_one_conversation():
    """Two of Sunny's lines: one talk, either prompt, either line heard."""
    other = dict(TALK, info='00000004', live=True, route=dict(TALK['route'], prompts=['Enough.']))
    steps = talk_steps([dict(TALK, live=True), other])
    assert steps.count('bye') == 1 and 'choose 20 Teach me. || Enough.' in steps
    assert 'heard 60 Sunny Smiles 00000002,00000004' in steps


def test_a_kill_route_kills_every_carrier():
    """A death count (VCG02's three geckos) wants every carrier dead."""
    setter = {'kind': 'object script', 'route': {'step': 'kill', 'refs': ['00000071', '00000072']}}
    assert S.route_steps('FalloutNV.esm', 'kill', setter) == ['run {FalloutNV.esm:00000071}.kill',
                                                              'run {FalloutNV.esm:00000072}.kill']


def test_a_chain_runs_its_quests_in_story_order_in_one_game(tmp_path):
    """--chain: files numbered in the given order, only the first loads the save, a stage that fails its quest is
    left out, a quest ends by its completing line, and a stage an earlier quest's stage sets is waited for."""
    first = quest({10: [], 20: []}) | {'source': 'A', 'fo4': 'FNV_A', 'completes': [dict(TALK, live=True)]}
    first['stages'][1]['ends'] = 'fail'
    second = quest({5: [{'kind': 'stage', 'quest': 'A', 'stage': 10}]}) | {'source': 'B', 'fo4': 'FNV_B'}
    plan = {'game': 'FalloutNV.esm', 'quests': [second, first]}
    assert W.write_sweep(plan, tmp_path, 'f3nvtest_start', ['a', 'b'], False, True, True)[:2] == (2, 2)
    cases = C.parse(C.case_text([tmp_path]), {})
    assert [c.name for c in cases] == ['A', 'B', 'zz_report']
    verbs = [[(verb, rest.split(' | ')[0]) for _n, verb, rest in c.steps] for c in cases[:2]]
    assert verbs[0][0] == ('load', 'f3nvtest_start') and all(verb != 'load' for verb, _ in verbs[1])
    assert not any('FNV_A 20' in rest for _, rest in verbs[0])
    first_case = (tmp_path / 'q_01_A.f4test').read_text(encoding='utf-8')
    assert '# complete route talk' in first_case and 'unless GetQuestCompleted FNV_A == 1 | run completequest FNV_A' \
        in first_case
    assert (tmp_path / 'q_02_B.f4test').read_text(encoding='utf-8').count('# stage 5 route wait') == 1


def test_a_quest_a_line_starts_is_started_by_its_route():
    """The start runs the starting line's route; startquest after."""
    lines = S.start_lines('FalloutNV.esm', quest({}, starts=[dict(TALK, live=True)]), set())
    assert lines[0].startswith('# start route talk')
    assert 'unless GetQuestRunning FNV_Q == 1 | run startquest FNV_Q' in lines
    assert any(line.startswith('check until 10 GetQuestRunning FNV_Q == 1') for line in lines)
