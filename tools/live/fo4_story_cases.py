"""Story cases on the hidden Fallout 4 test instance: scripted runs that check lines and stages.

    python -m tools.live.fo4_story_cases tests/story/fo4_creation.f4test tests/story/fo3_opening
        [--set SEX=male] [--from CASE] [--to CASE] [--checkpoints] [--keep | --keep-on-fail] [--repeat N]
        [--speed X] [--slot N]

A case file holds cases in order; each passing case can be checkpointed
(a sandbox save), and `--from` starts from the save before that case:

    case cg02_intercom
    until 1200 GetStage FNV_CG02 >= 35     # poll a console query until it holds
    alone 30 GetStageDone FNV_CG04 141 == 1   # ... leaving any talk that opens meanwhile
    hear Dad 00031D43                      # the trace logs Dad beginning that source INFO
    heard Dad 00031D43                     # ... and ending it, its result script run
    expect GetStage FNV_CG02 < 40          # one console query, now
    unless GetStageDone FNV_CG02 40 == 1 | run setstage FNV_CG02 40    # a step only when it doesn't hold
    run player.moveto 00012345             # one console line
    answer ${SEX=male:Boy,female:Girl}     # press that button on the next message box
    close LooksMenu                        # hide that menu once it opens
    call LooksMenu 1                       # run that menu's code function 1 (ChangeSex), as its button does
    press 1 W                              # hold a key in the game window (seconds, default a tap)
    walk {Fallout3.esm:02EA54}             # face that source ref and walk to it ([seconds] ref [radius])
    activate {Fallout3.esm:047803}         # the player activates that source ref
    look {FalloutNV.esm:104C0F}            # turn the player toward it: FO4 lists a talk's choices only then
    talk 60 {Fallout3.esm:0309A8}          # ... again until its dialogue menu opens
    choose 60 Yes, ma'am.                  # press the number key of the listed line holding those words
    bye                                    # leave the talk (Tab) until the dialogue menu closes
    ready 120                              # in a cell, nothing loading
    wait 5                                 # real seconds
    end

`hear [seconds] <speaker> <INFO>` reads the trace's `line` entries (speaker
name, source INFO FormID). `${NAME}` takes `--set NAME=value`. `{Plugin.esm:id}`
in any step is that source record's FormID in the running game (fo4_story_moves).

See: docs/fork/fo4_story_tests.md#cases
"""
import argparse
import dataclasses
import json
import operator
import re
import sys
import time
from pathlib import Path

from tools.live import fo4_story_talk as talk
from tools.live import fo4_sweep_steps as sweep
from tools.live import fo4_test_instance as T
from tools.live import hidden_launch
from tools.live.fo4_story_moves import CaseFailed, Refs, activate, aim, shoot, walk
from tools.live.game_bridge import Bridge, BridgeError

OPS = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge,
       '==': operator.eq, '!=': operator.ne}
#: Seconds a `hear` waits when the case names none.
HEAR_SECONDS = 300
#: The console's reply to a command it ignores while the player is in no cell; seconds `run` retries it.
IGNORED, RUN_SECONDS = 'please start the game or go into a cell first', 30
#: Seconds a message box has to close after each key `answer` presses.
PRESS_SECONDS = 3
#: The keys `answer` accepts a box with, in turn: Fallout 4's Accept is Enter and E.
ACCEPT_KEYS = (('Enter', hidden_launch.SCAN_ENTER), ('E', hidden_launch.SCANCODES['e']))
#: A quest a step names (`GetStage FNV_CG01 >= 80`), for the failure snapshot.
QUEST = re.compile(r'GetStage(?:Done)?\s+(\w+)', re.IGNORECASE)
#: Lines of the trace a failure snapshot repeats.
SNAPSHOT_LINES = 12
#: Steps that run another step, which fills in its own source records: a record missing fails only that step.
WRAPPERS = ('unless', 'check')
#: `${NAME}`, or `${NAME=a:x,b:y}` choosing x or y by NAME's value.
FILL = re.compile(r'\$\{(\w+)(?:=([^}]*))?\}')

#: `TES4TRACE|time|line|[script < (ref)>] 'Name'|INFO|Begin|...` -> name, INFO, phase (an FNV Goodbye ends `end goodbye`).
LINE = re.compile(r"TES4TRACE\|[^|]*\|line\|[^|]*'([^'|]*)'\|([0-9A-Fa-f]{8})\|(Begin|End|end goodbye)")


# ---------------------------------------------------------------------------
#  Case files
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Case:
    """One case: its name and its (line number, verb, rest) steps."""

    name: str
    steps: list


def case_text(paths: list) -> str:
    """Each case file, or each folder's `*.f4test` by name, in turn, joined."""
    files = [f for path in paths for f in ([path] if path.is_file() else sorted(path.glob('*.f4test')))]
    return '\n'.join(f.read_text(encoding='utf-8') for f in files)


def fill(match: re.Match, values: dict) -> str:
    """`${NAME}` -> NAME's value; `${NAME=a:x,b:y}` -> the text listed for that value."""
    name, choices = match.groups()
    if name not in values:
        raise SystemExit('the cases need --set %s=...' % name)
    return dict(pair.split(':', 1) for pair in choices.split(','))[values[name]] if choices else values[name]


def parse(text: str, values: dict) -> list:
    """The cases in case-file `text`, `${...}` filled from `values`."""
    cases, current = [], None
    for number, raw in enumerate(text.splitlines(), 1):
        line = FILL.sub(lambda m: fill(m, values), raw.split('#', 1)[0]).strip()
        if not line:
            continue
        verb, _, rest = line.partition(' ')
        if verb == 'case':
            current = Case(rest.strip(), [])
            cases.append(current)
        elif verb == 'end':
            current = None
        elif current is None:
            raise SystemExit('line %d: %r outside a case' % (number, line))
        else:
            current.steps.append((number, verb, rest.strip()))
    return cases


def chosen(cases: list, first: str, last: str) -> list:
    """`cases` from `first` (else the start) through `last` (else the end)."""
    names = [c.name for c in cases]
    for name in (first, last):
        if name and name not in names:
            raise SystemExit('no case %r' % name)
    start = names.index(first) if first else 0
    stop = names.index(last) + 1 if last else len(cases)
    return cases[start:stop]


# ---------------------------------------------------------------------------
#  The trace
# ---------------------------------------------------------------------------

class Trace:
    """The sandbox's Papyrus log, read forward from where the run began."""

    def __init__(self, path: Path):
        """Starts at the log's current end, so only this run's lines count."""
        self.path = path
        self.offset = path.stat().st_size if path.is_file() else 0
        self.heard = []
        self.cursor = 0

    def read(self) -> list:
        """The (name, INFO, phase) line entries written since the last read, also kept in `heard`."""
        if not self.path.is_file():
            return []
        if self.path.stat().st_size < self.offset:
            self.offset = 0
        with open(self.path, 'rb') as f:
            f.seek(self.offset)
            chunk = f.read()
        complete = chunk.rfind(b'\n') + 1
        self.offset += complete
        found = [(name, info, 'Begin' if phase == 'Begin' else 'End')
                 for name, info, phase in LINE.findall(chunk[:complete].decode('utf-8', 'replace'))]
        self.heard += found
        return found


# ---------------------------------------------------------------------------
#  Steps
# ---------------------------------------------------------------------------

def query(bridge: Bridge, text: str) -> float:
    """The number a console query printed after its last `>>`."""
    output = T.send(bridge, text)
    if '>>' not in output:
        raise CaseFailed('%r printed no value: %r' % (text, output.strip()))
    return float(output.rsplit('>>', 1)[1].split()[0])


def condition(rest: str) -> tuple:
    """(console query, compare, value) of `<query...> <op> <value>`."""
    words = rest.split()
    if len(words) < 3 or words[-2] not in OPS:
        raise CaseFailed('expected "<query> <op> <value>", got %r' % rest)
    return ' '.join(words[:-2]), OPS[words[-2]], float(words[-1])


def until(bridge: Bridge, rest: str, each=None) -> None:
    """Polls `<seconds> <query> <op> <value>` once a second until it holds, calling `each` (when given) first."""
    seconds, _, rest = rest.partition(' ')
    text, compare, value = condition(rest)
    deadline, last = time.time() + float(seconds), None
    while time.time() < deadline:
        if each:
            each()
        try:
            last = query(bridge, text)
        except CaseFailed as err:
            last = str(err)
        if isinstance(last, float) and compare(last, value):
            return
        time.sleep(1)
    raise CaseFailed('%s still %s after %s s' % (text, last, seconds))


def expect(bridge: Bridge, rest: str) -> None:
    """Checks `<query> <op> <value>` once."""
    text, compare, value = condition(rest)
    got = query(bridge, text)
    if not compare(got, value):
        raise CaseFailed('%s is %s' % (text, got))


def unless(game, rest: str, step) -> None:
    """`<query> <op> <value> | <step>`: runs the case step (`run <console line>`, `check talk ...`) with `step`
    (run_step) only when the condition does not hold now."""
    held, _, line = (part.strip() for part in rest.partition(' | '))
    text, compare, value = condition(game.refs.fill(held))
    if not compare(query(game.bridge, text), value):
        verb, _, more = line.partition(' ')
        step(game, verb, more)


def hear(trace: Trace, rest: str, when: str = 'Begin') -> None:
    """Waits for `[seconds] <speaker name> <INFO>[,<INFO>...]` (any of them) to reach `when` (Begin or End) in the
    trace after the last line heard; a line's End is after its result script ran."""
    seconds, text = timed(rest)
    speaker, _, info = text.rpartition(' ')
    speaker, infos = speaker.lower(), {i.upper().zfill(8) for i in info.split(',')}
    deadline = time.time() + seconds
    while time.time() < deadline:
        trace.read()
        for k in range(trace.cursor, len(trace.heard)):
            name, line, phase = trace.heard[k]
            if name.lower() == speaker and line.upper() in infos and phase == when:
                trace.cursor = k + 1
                return
        time.sleep(0.5)
    seen = ['%s %s %s' % entry for entry in trace.heard[-8:]]
    raise CaseFailed('%s never reached %s of %s in %g s; last lines: %s' % (speaker, when, info, seconds, seen))


def timed(rest: str) -> tuple:
    """(seconds, text) of `[seconds] <text>`, seconds HEAR_SECONDS when not given."""
    first, _, text = rest.partition(' ')
    return (float(first), text) if text and first.replace('.', '', 1).isdigit() else (HEAR_SECONDS, rest)


def menu(bridge: Bridge, rest: str) -> None:
    """Waits `[seconds] <menu>` for that menu to be open, through status alone (no console line)."""
    seconds, name = timed(rest)
    try:
        T.wait_status(bridge, lambda s: name in s['menus'], seconds)
    except BridgeError as err:
        raise CaseFailed(str(err)) from err


def closed(bridge: Bridge, rest: str) -> None:
    """Waits `[seconds] <menu>` for that menu to be closed, through status alone."""
    seconds, name = timed(rest)
    try:
        T.wait_status(bridge, lambda s: name not in s['menus'], seconds)
    except BridgeError as err:
        raise CaseFailed(str(err)) from err


def on_menu(bridge: Bridge, cmd: str, rest: str) -> dict:
    """Runs bridge `cmd` on `[seconds] <text>` once its menu is open and not busy, waiting up to seconds (default
    HEAR_SECONDS)."""
    seconds, text = timed(rest)
    deadline = time.time() + seconds
    while True:
        try:
            result = bridge.request(cmd, text=text)
            print('    %s %s -> %s' % (cmd, text, result), flush=True)
            return result
        except BridgeError as err:
            if err.code not in ('E_NOMENU', 'E_LOADING', 'E_BUSY') or time.time() > deadline:
                raise CaseFailed(str(err)) from err
        time.sleep(0.5)


def answer(bridge: Bridge, rest: str, front) -> None:
    """Selects button `[seconds] <label>` on the next message box and accepts it as a player does: Enter, then E
    (Fallout 4's other Accept key) if the box is still up. The game is brought to the front first (`front`).
    Holds when the box is gone or shows other buttons.
    """
    shown = on_menu(bridge, 'button', rest)
    if shown['selected'] != shown['wanted']:
        raise CaseFailed('the box selected %s, not %s' % (shown['selected'], shown['wanted']))
    for name, scan in ACCEPT_KEYS:
        front()
        hidden_launch.tap_key(scan)
        if box_gone(bridge, shown['buttons']):
            print('    the box took %s' % name, flush=True)
            return
    raise CaseFailed('the box %s took none of %s' % (shown['buttons'], ', '.join(n for n, _ in ACCEPT_KEYS)))


def box_gone(bridge: Bridge, buttons: list) -> bool:
    """Whether the message box showing `buttons` closes within PRESS_SECONDS."""
    deadline = time.time() + PRESS_SECONDS
    while time.time() < deadline:
        try:
            bridge.request('button', text='')
        except BridgeError as err:
            if err.code == 'E_NOMENU' or json.dumps(buttons, separators=(',', ':'), ensure_ascii=False) not in str(err):
                return True
        time.sleep(0.25)
    return False


def press(rest: str, front) -> None:
    """Holds key `[seconds] <name>` (hidden_launch.SCANCODES) in the game window, brought to the front first
    (`front`); a tap when no seconds."""
    *held, name = rest.split()
    scan = hidden_launch.SCANCODES.get(name.lower())
    if scan is None:
        raise CaseFailed('no key %r; known: %s' % (name, ', '.join(hidden_launch.SCANCODES)))
    front()
    hidden_launch.tap_key(scan, float(held[0]) if held else hidden_launch.TAP_SECONDS)


def run(bridge: Bridge, rest: str) -> None:
    """Sends console command `rest` and prints its reply, sending it again each second for up to RUN_SECONDS while
    the console ignores it (`IGNORED`: the player between cells, as a stage moves them).
    See: docs/fork/fo4_test_layers_plan.md#unmet-waits
    """
    end = time.time() + RUN_SECONDS
    reply = T.send(bridge, rest)
    while IGNORED in reply and time.time() < end:
        time.sleep(1)
        reply = T.send(bridge, rest)
    print('    %s -> %r' % (rest, reply.strip()), flush=True)


def ready(bridge: Bridge, rest: str) -> None:
    """Waits up to `[seconds]` (default 180) for a loaded cell with no loading menu."""
    T.wait_status(bridge, lambda s: s['cell'] and 'LoadingMenu' not in s['menus'], float(rest or 180))


@dataclasses.dataclass
class Game:
    """The running game a case drives: its bridge, the trace, a call bringing it to the front, source records."""

    bridge: Bridge
    trace: Trace
    front: object
    refs: Refs
    #: The global time multiplier (`sgtm`) an `until` waits at; 1 leaves the game's own.
    speed: float = 1.0


def paced_until(game: Game, rest: str) -> None:
    """`until`, at the run's game speed while it waits and 1 after: the game's own work (packages, timers,
    fights) runs faster, while talks and picks stay at 1, where a 4x dialogue menu drops number keys.
    See: docs/fork/fo4_test_layers_plan.md#s7
    """
    if game.speed == 1:
        return until(game.bridge, rest)
    T.send(game.bridge, 'sgtm %g' % game.speed)
    try:
        return until(game.bridge, rest)
    finally:
        T.send(game.bridge, 'sgtm 1')


def alone(game: Game, rest: str) -> None:
    """`until`, leaving each talk that opens meanwhile (a force greet), at most one Tab every PRESS_WAIT seconds:
    an open talk holds every quest script's poll as a menu held GameMode.
    See: docs/fork/fo4_test_layers_plan.md#unmet-waits
    """
    last = [0.0]

    def leave():
        """One Tab in an open talk, unless the last was under PRESS_WAIT seconds ago."""
        if time.time() - last[0] >= talk.PRESS_WAIT and talk.leave(game.bridge, game.front):
            last[0] = time.time()

    until(game.bridge, rest, leave)


def run_step(game: Game, verb: str, rest: str) -> None:
    """Runs one step, its source records (`{Plugin.esm:id}`) filled in; raises CaseFailed when it does not hold."""
    bridge, front = game.bridge, game.front
    rest = rest if verb in WRAPPERS else game.refs.fill(rest)
    steps = {'run': lambda: run(bridge, rest),
             'wait': lambda: time.sleep(float(rest)),
             'until': lambda: paced_until(game, rest), 'alone': lambda: alone(game, rest),
             'expect': lambda: expect(bridge, rest),
             'unless': lambda: unless(game, rest, run_step),
             'hear': lambda: hear(game.trace, rest), 'heard': lambda: hear(game.trace, rest, 'End'),
             'ready': lambda: ready(bridge, rest),
             'answer': lambda: answer(bridge, rest, front), 'close': lambda: on_menu(bridge, 'close', rest),
             'call': lambda: on_menu(bridge, 'call', rest), 'invoke': lambda: on_menu(bridge, 'invoke', rest),
             'menu': lambda: menu(bridge, rest), 'closed': lambda: closed(bridge, rest),
             'choose': lambda: talk.choose(bridge, rest, front, timed), 'talk': lambda: talk.talk(bridge, rest, timed, front),
             'bye': lambda: talk.bye(bridge, rest, front),
             'press': lambda: press(rest, front),
             'activate': lambda: activate(bridge, rest, front), 'look': lambda: aim(bridge, rest.split()[0]),
             'walk': lambda: walk(bridge, rest, front), 'shoot': lambda: shoot(bridge, rest, front),
             'errors': lambda: sweep.errors(game, rest), 'check': lambda: sweep.check(game, rest, run_step),
             'load': lambda: sweep.load(game, rest, ready), 'report': lambda: sweep.report(game)}
    if verb not in steps:
        raise CaseFailed('unknown step %r' % verb)
    steps[verb]()


# ---------------------------------------------------------------------------
#  Runs
# ---------------------------------------------------------------------------

def run_case(game: Game, case: Case) -> str:
    """'' when every step of `case` holds, else the failing step and why (a game that stopped answering too)."""
    for number, verb, rest in case.steps:
        try:
            run_step(game, verb, rest)
        except (CaseFailed, BridgeError) as err:
            return 'line %d `%s %s`: %s' % (number, verb, rest, err)
        print('    . %s %s' % (verb, rest), flush=True)
    return ''


def start(inst: T.Instance, bridge: Bridge, load: str) -> None:
    """Waits for the main menu, then loads sandbox save `load` when given: queued as the Load menu does (the
    console's `load` hung the game).
    See: docs/fork/fo4_test_layers_plan.md#s3
    """
    T.wait_status(bridge, T.at_main_menu, 240)
    T.focus(inst)
    if not load:
        return
    if not (inst.my_games / 'Saves' / (load + '.fos')).is_file():
        raise SystemExit('no checkpoint %s in the sandbox; run earlier cases with --checkpoints' % load)
    print('    load -> %s' % bridge.request('load', text=load), flush=True)
    ready(bridge, '')


def snapshot(game: Game, case: Case) -> None:
    """Prints the game's state where `case` failed: the bridge status, each quest its steps name (stages and
    objectives, `sqs` and `sqo`), and the last lines the trace heard.
    See: docs/fork/fo4_test_layers_plan.md#s4
    """
    print('    snapshot:', flush=True)
    quests = dict.fromkeys(q for _, _, rest in case.steps for q in QUEST.findall(rest))
    try:
        print('      status %s' % game.bridge.status())
        for quest in quests:
            for line in ('sqs %s' % quest, 'sqo %s' % quest):
                print('      %s ->\n        %s' % (line, T.send(game.bridge, line).strip().replace('\n', '\n        ')))
    except BridgeError as err:
        print('      the game did not answer: %s' % err)
    for name, info, phase in game.trace.heard[-SNAPSHOT_LINES:]:
        print('      line %s %s %s' % (name, info, phase))


def checkpoint(case: str, values: dict) -> str:
    """The save a passing case leaves: its name and the run's --set values."""
    return '_'.join(['f3nvtest', case, *(values[k] for k in sorted(values))])


def run_all(inst: T.Instance, cases: list, load: str, checkpoints, keep_going: bool = False,
            speed: float = 1.0) -> list:
    """Runs `cases` at game `speed`, saving after each passing case when given the --set values (`checkpoints`);
    a failure ends the run, or with `keep_going` relaunches the game for the rest from the last passing case's
    checkpoint, keeping the sweep's failed checks; [(case, failure or '')].
    See: docs/fork/fo4_test_layers_plan.md#s5
    """
    results, carried = [], None
    while True:
        passed = [name for name, failure in results if not failure]
        resume = checkpoint(passed[-1], checkpoints) if passed and checkpoints is not None else ''
        done, carried = run_game(inst, cases[len(results):], resume if results else load, checkpoints, carried,
                                 speed)
        results += done
        if not keep_going or len(results) >= len(cases):
            return results
        print('    relaunching the game for the %d case(s) left' % (len(cases) - len(results)), flush=True)
        T.stop(inst)
        T.launch(inst)


def run_game(inst: T.Instance, cases: list, load: str, checkpoints, carried, speed: float = 1.0) -> tuple:
    """Runs `cases` in one game at `speed` up to the first failure, the sweep state `carried` from an earlier game
    going on; ([(case, failure or '')], the sweep state)."""
    trace = Trace(inst.my_games / 'Logs' / 'Script' / 'Papyrus.0.log')
    results = []
    with T.connect(inst, 240) as bridge:
        start(inst, bridge, load)
        trace.read()
        game = Game(bridge, trace, lambda: T.focus(inst), Refs(bridge, inst.data), speed)
        if carried:
            game.sweep = sweep.resume(carried, trace)
        for case in cases:
            began = time.time()
            failure = run_case(game, case)
            results.append((case.name, failure))
            print('%s  %s  (%.0f s)%s' % ('FAIL' if failure else 'ok  ', case.name, time.time() - began,
                                          '\n      ' + failure if failure else ''), flush=True)
            if failure:
                snapshot(game, case)
                break
            if checkpoints is not None:
                T.send(bridge, 'save %s' % checkpoint(case.name, checkpoints))
    return results, getattr(game, 'sweep', None)


def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cases', type=Path, nargs='+', help='case files, or folders of *.f4test run by name, in turn')
    ap.add_argument('--set', action='append', default=[], metavar='NAME=VALUE', help='fills ${NAME}')
    ap.add_argument('--from', dest='first', help='start at this case, from the checkpoint before it')
    ap.add_argument('--to', dest='last', help='stop after this case')
    ap.add_argument('--checkpoints', action='store_true', help='save after each passing case')
    ap.add_argument('--keep', action='store_true', help='leave the game running afterwards')
    ap.add_argument('--keep-on-fail', action='store_true', help='leave the game running when a case fails')
    ap.add_argument('--keep-going', action='store_true', help='after a failing case, relaunch and run the rest')
    ap.add_argument('--repeat', type=int, default=1, help='rounds, each in a fresh game; pass only if all pass')
    ap.add_argument('--speed', type=float, default=1.0, help='game speed (sgtm) while an `until` waits')
    ap.add_argument('--slot', type=int, default=1)
    ap.add_argument('--visible', action='store_true', help='run on the desktop, in front (a dedicated machine)')
    return ap.parse_args(argv)


def one_round(args, inst: T.Instance, picked: list, load: str, values: dict) -> bool:
    """One fresh game running `picked`, stopped afterwards unless kept; whether every case passed."""
    T.stop(inst)
    T.launch(inst)
    results = []
    try:
        results = run_all(inst, picked, load, values if args.checkpoints else None, args.keep_going, args.speed)
    finally:
        failed = len(results) < len(picked) or any(failure for _, failure in results)
        if not (args.keep or args.keep_on_fail and failed):
            T.stop(inst)
    print('%d of %d case(s) passed' % (sum(not failure for _, failure in results), len(picked)), flush=True)
    return not failed


def main(argv=None) -> int:
    """Runs the chosen cases --repeat times, each in a fresh game, stopping at a failing round; 0 when all pass.
    See: docs/fork/fo4_test_layers_plan.md#s5
    """
    args = parse_args(argv)
    values = dict(item.split('=', 1) for item in args.set)
    cases = parse(case_text(args.cases), values)
    picked = chosen(cases, args.first, args.last)
    names = [c.name for c in cases]
    load = checkpoint(names[names.index(args.first) - 1], values) if args.first and names.index(args.first) else ''
    inst = T.Instance(args.slot, visible=args.visible)
    for done in range(args.repeat):
        if args.repeat > 1:
            print('round %d of %d' % (done + 1, args.repeat), flush=True)
        if not one_round(args, inst, picked, load, values):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
