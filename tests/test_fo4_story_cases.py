"""Story case files, the trace reader and the menu steps, without a game."""
import json
from types import SimpleNamespace

import pytest

from tools.live import fo4_story_cases as C
from tools.live import hidden_launch
from tools.live.game_bridge import BridgeError

CASES = """
# a comment
case one
run coc ${CELL}   # trailing comment
hear 30 Dad 1F387
end
case two
expect GetStage FNV_CG00 >= 5
end
"""


def test_parse_reads_cases_steps_and_values():
    """Cases keep their order; ${NAME} is filled and comments dropped."""
    cases = C.parse(CASES, {'CELL': 'QASmoke'})
    assert [c.name for c in cases] == ['one', 'two']
    assert [s[1:] for s in cases[0].steps] == [('run', 'coc QASmoke'), ('hear', '30 Dad 1F387')]


def test_chosen_slices_from_and_to():
    """--from and --to pick a run of cases; an unknown name stops."""
    cases = C.parse(CASES, {'CELL': 'x'})
    assert [c.name for c in C.chosen(cases, 'two', None)] == ['two']
    with pytest.raises(SystemExit):
        C.chosen(cases, 'three', None)


def test_unless_runs_its_step_only_while_the_condition_fails(monkeypatch):
    """`unless GetStageDone ... | check talk ...` runs the check step, not after the stage is done."""
    ran, answers = [], iter([0.0, 1.0])
    monkeypatch.setattr(C, 'query', lambda bridge, text: next(answers))
    game = C.Game(None, None, None, SimpleNamespace(fill=lambda text: text))
    rest = 'GetStageDone FNV_Q 10 == 1 | check talk 30 00051 | FNV_Q stage 10'
    for _ in range(2):
        C.unless(game, rest, lambda g, verb, more: ran.append((verb, more)))
    assert ran == [('check', 'talk 30 00051 | FNV_Q stage 10')]


def test_a_missing_record_in_a_checked_step_fails_only_that_check(monkeypatch):
    """`unless ... | check run player.moveto {X}` with X absent from the build: the check fails, the case goes on."""
    def fill(text):
        """Fails on any source record, as a region build missing it does."""
        if '{' in text:
            raise C.CaseFailed('no form FalloutNV.esm 166134')
        return text

    state = C.sweep.Sweep(None)
    monkeypatch.setattr(C, 'query', lambda bridge, text: 0.0)
    monkeypatch.setattr(C.sweep, 'sweep_of', lambda game: state)
    game = C.Game(None, None, None, SimpleNamespace(fill=fill))
    C.run_step(game, 'unless', 'GetStageDone FNV_Q 100 == 1 | check run player.moveto {FalloutNV.esm:00166134} | note')
    assert len(state.failed) == 1


def test_a_talk_that_breaks_at_a_gate_is_cut_short_alone(monkeypatch):
    """A `choose` that fails after its wait: that talk's next choose is skipped, its heard looks 5 s, its bye runs;
    another talk's steps run in full."""
    ran, state = [], C.sweep.Sweep(None)

    def run_step(game, verb, rest):
        """Fails every choose; records the rest."""
        ran.append((verb, rest))
        if verb == 'choose':
            raise C.CaseFailed('no option')

    monkeypatch.setattr(C.sweep, 'sweep_of', lambda game: state)
    for line in ('choose 20 A | Q: talk 1 with Sunny', 'choose 20 B | Q: talk 1 with Sunny',
                 'heard 60 Sunny 0001 | Q: talk 1 with Sunny', 'bye | Q: talk 1 with Sunny',
                 'heard 60 Trudy 0002 | Q: talk 2 with Trudy'):
        C.sweep.check(None, line, run_step)
    assert ran == [('choose', '20 A'), ('heard', '5 Sunny 0001'), ('bye', ''), ('heard', '60 Trudy 0002')]


@pytest.mark.parametrize('speed, sent', [(1.0, []), (4.0, ['sgtm 4', 'sgtm 1'])])
def test_an_until_waits_at_the_run_speed_and_restores_it(monkeypatch, speed, sent):
    """--speed 4: sgtm 4 for the wait, sgtm 1 after, even when the wait fails; 1: no sgtm at all."""
    lines = []
    monkeypatch.setattr(C.T, 'send', lambda bridge, line: lines.append(line) or '')

    def fails(bridge, rest):
        """The wait times out."""
        raise C.CaseFailed('still 0')

    monkeypatch.setattr(C, 'until', fails)
    with pytest.raises(C.CaseFailed):
        C.paced_until(C.Game(None, None, None, None, speed), '60 GetStageDone FNV_Q 30 == 1')
    assert lines == sent


def test_condition_needs_an_operator():
    """`<query> <op> <value>` splits; a missing operator is a case failure."""
    text, compare, value = C.condition('GetStage FNV_CG02 >= 35')
    assert text == 'GetStage FNV_CG02' and compare(35, value) and not compare(34, value)
    with pytest.raises(C.CaseFailed):
        C.condition('GetStage FNV_CG02')


def test_hear_matches_new_complete_trace_lines(tmp_path):
    """The trace starts at the log's end; `hear` matches speaker and INFO of whole new lines."""
    log = tmp_path / 'Papyrus.0.log'
    log.write_text("TES4TRACE|1.0|line|[S < (08E4E59E)>] 'Old'|00000001|Begin\n", encoding='utf-8')
    trace = C.Trace(log)
    with open(log, 'a', encoding='utf-8') as f:
        f.write("[t] TES4TRACE|2.0|line|[S < (08E4E59E)>] 'Dad'|0001F387|Begin|scene None\n")
        f.write("[t] TES4TRACE|2.1|line|[S < (08E4E59E)>] 'Dad'|0001F387|En")
    C.hear(trace, '1 dad 1F387')
    assert trace.heard == [('Dad', '0001F387', 'Begin')]
    with pytest.raises(C.CaseFailed):
        C.hear(trace, '0.5 Dad 00000001')


def test_hear_takes_a_speaker_name_of_several_words(tmp_path):
    """`hear Doc Mitchell <INFO>` waits the default time for that whole name."""
    log = tmp_path / 'Papyrus.0.log'
    log.write_text('', encoding='utf-8')
    trace = C.Trace(log)
    with open(log, 'a', encoding='utf-8') as f:
        f.write("[t] TES4TRACE|2.0|line|[S < (0A104C0F)>] 'Doc Mitchell'|001074A2|Begin\n")
    C.hear(trace, 'Doc Mitchell 1074A2')
    assert trace.cursor == 1


def test_hear_takes_any_of_several_lines(tmp_path):
    """`hear Sunny Smiles 15D97E,15F8B6`: either line will do."""
    log = tmp_path / 'Papyrus.0.log'
    log.write_text('', encoding='utf-8')
    trace = C.Trace(log)
    with open(log, 'a', encoding='utf-8') as f:
        f.write("[t] TES4TRACE|2.0|line|[S < (0A104E85)>] 'Sunny Smiles'|0015F8B6|Begin\n")
    C.hear(trace, '1 Sunny Smiles 15D97E,15F8B6')
    assert trace.cursor == 1


def test_heard_waits_for_the_line_to_end(tmp_path):
    """`heard` matches the line's end after its begin, an FNV Goodbye's `end goodbye` included."""
    log = tmp_path / 'Papyrus.0.log'
    log.write_text('', encoding='utf-8')
    trace = C.Trace(log)
    with open(log, 'a', encoding='utf-8') as f:
        f.write("[t] TES4TRACE|2.0|line|[S < (0A104C0F)>] 'Doc Mitchell'|001074A2|Begin|scene None\n")
    C.hear(trace, 'Doc Mitchell 1074A2')
    with pytest.raises(C.CaseFailed):
        C.hear(trace, '0.5 Doc Mitchell 1074A2', 'End')
    with open(log, 'a', encoding='utf-8') as f:
        f.write("[t] TES4TRACE|9.0|line|[S < (0A104C0F)>] 'Doc Mitchell'|001074A2|end goodbye|scene None\n")
    C.hear(trace, '1 Doc Mitchell 1074A2', 'End')
    assert trace.heard[-1] == ('Doc Mitchell', '001074A2', 'End')


class Box:
    """A bridge showing a box of `buttons` that closes on key `closes_on` (a scancode)."""

    def __init__(self, closes_on: int, buttons: tuple = ('OK', 'CANCEL')):
        """The box is up until `closes_on` is pressed."""
        self.closes_on, self.pressed, self.buttons = closes_on, [], list(buttons)

    def request(self, cmd: str, text: str = '') -> dict:
        """`button`: the box's state, or E_NOMENU once its key was pressed."""
        if self.closes_on in self.pressed:
            raise BridgeError('E_NOMENU no message box open', 'E_NOMENU')
        if text:
            return {'buttons': self.buttons, 'selected': 0, 'wanted': 0}
        raise BridgeError('E_NOBUTTON no button  in ' + json.dumps(self.buttons, separators=(',', ':'),
                                                                  ensure_ascii=False), 'E_NOBUTTON')


@pytest.mark.parametrize('key', ['enter', 'e'])
def test_answer_presses_enter_then_e_until_the_box_closes(monkeypatch, key):
    """Enter first; E (Fallout 4's other Accept key) when the box is still up; the game in front before each."""
    scan = hidden_launch.SCANCODES[key]
    box, fronts = Box(scan), []
    monkeypatch.setattr(C, 'PRESS_SECONDS', 0.3)
    monkeypatch.setattr(hidden_launch, 'tap_key', box.pressed.append)
    C.answer(box, 'OK', lambda: fronts.append(1))
    assert box.pressed[-1] == scan and len(fronts) == len(box.pressed)


def test_a_lost_key_on_a_box_with_non_ascii_buttons_is_pressed_again(monkeypatch):
    """CG03's G.O.A.T. question 8 ("resident�s"): a box still up after Enter is seen as up, so E follows."""
    scan = hidden_launch.SCANCODES['e']
    box = Box(scan, ('Trade the comic book.', 'Sneak into the resident�s quarters.'))
    monkeypatch.setattr(C, 'PRESS_SECONDS', 0.3)
    monkeypatch.setattr(hidden_launch, 'tap_key', box.pressed.append)
    C.answer(box, 'Trade the comic book.', lambda: None)
    assert box.pressed == [hidden_launch.SCAN_ENTER, scan]


def test_answer_fails_when_no_accept_key_closes_the_box(monkeypatch):
    """A box that takes neither key fails the step, naming both."""
    box = Box(0)
    monkeypatch.setattr(C, 'PRESS_SECONDS', 0.3)
    monkeypatch.setattr(hidden_launch, 'tap_key', box.pressed.append)
    with pytest.raises(C.CaseFailed, match='Enter, E'):
        C.answer(box, 'OK', lambda: None)


def test_a_busy_menu_is_retried(monkeypatch):
    """E_BUSY (LooksMenu's Done while a face loads) waits like a menu not yet open."""
    answers = [BridgeError('E_BUSY busy', 'E_BUSY'), {'confirm': True}]

    class Busy:
        """Busy once, then confirms."""

        def request(self, cmd, text=''):
            """The next answer, raised when an error."""
            got = answers.pop(0)
            if isinstance(got, BridgeError):
                raise got
            return got

    monkeypatch.setattr(C.time, 'sleep', lambda s: None)
    assert C.on_menu(Busy(), 'close', '5 LooksMenu') == {'confirm': True}


def test_a_failure_snapshot_asks_each_quest_the_case_names(monkeypatch, capsys, tmp_path):
    """The snapshot prints the status, `sqs` and `sqo` once per quest the steps name, and the last lines heard."""
    asked = []

    class Game:
        """A bridge answering status and every console line."""

        def status(self):
            """The menus open."""
            return {'menus': ['HUDMenu']}

    monkeypatch.setattr(C.T, 'send', lambda bridge, line: asked.append(line) or 'out')
    log = tmp_path / 'Papyrus.0.log'
    log.write_text('', encoding='utf-8')
    trace = C.Trace(log)
    trace.heard = [('Doc Mitchell', '001074A2', 'Begin')]
    case = C.parse('case v\nuntil 10 GetStage FNV_VCG01 >= 60\nexpect GetStageDone FNV_VCG01 60 == 1\nend\n', {})[0]
    C.snapshot(C.Game(Game(), trace, None, None), case)
    assert asked == ['sqs FNV_VCG01', 'sqo FNV_VCG01']
    printed = capsys.readouterr().out
    assert "{'menus': ['HUDMenu']}" in printed and 'Doc Mitchell 001074A2 Begin' in printed


@pytest.mark.parametrize('keep_going, ran', [(False, ['a']), (True, ['a', 'b', 'c'])])
def test_keep_going_relaunches_after_a_failure_and_carries_the_sweep(monkeypatch, keep_going, ran):
    """A failing case ends the run, or with keep_going relaunches the game for the rest, passing on the sweep state
    and the speed."""
    games, carried = [], []

    def run_game(inst, cases, load, checkpoints, state, speed):
        """Fails the first game's first case; passes every case of a later game."""
        games.append((cases, load, speed))
        carried.append(state)
        return ([(cases[0], 'broke')], 'sweep') if len(games) == 1 else ([(c, '') for c in cases], state)

    monkeypatch.setattr(C, 'run_game', run_game)
    monkeypatch.setattr(C.T, 'stop', lambda inst: None)
    monkeypatch.setattr(C.T, 'launch', lambda inst: None)
    results = C.run_all(None, ['a', 'b', 'c'], 'save', None, keep_going, 4.0)
    assert [name for name, _ in results] == ran
    assert carried == [None, 'sweep'][:len(games)] and all(speed == 4.0 for _c, _l, speed in games)


def test_a_relaunch_resumes_from_the_last_passing_cases_checkpoint(monkeypatch):
    """A passes, B fails: C runs in a new game from A's checkpoint, not at the main menu."""
    loads = []

    def run_game(inst, cases, load, checkpoints, state, speed):
        """Passes A and fails B in the first game; passes the rest."""
        loads.append(load)
        return ([('a', ''), ('b', 'broke')], None) if len(loads) == 1 else ([(c, '') for c in cases], None)

    monkeypatch.setattr(C, 'run_game', run_game)
    monkeypatch.setattr(C.T, 'stop', lambda inst: None)
    monkeypatch.setattr(C.T, 'launch', lambda inst: None)
    C.run_all(None, ['a', 'b', 'c'], 'start', {'SEX': 'male'}, True)
    assert loads == ['start', 'f3nvtest_a_male']
