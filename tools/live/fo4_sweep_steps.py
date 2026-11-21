"""Story-case steps for the layer 1 stage sweep: Papyrus errors per window, soft checks, a load mid-run, the verdict.

    errors [seconds] [script prefix ...]   # fail on errors converted scripts raised since the last errors or load
    check <step> [| note]                  # run any step; a failure is printed and kept, the case goes on
    unmet <step> [| note]                  # check a wait on a setter the sweep cannot satisfy: kept apart, not failed
    load <sandbox save> [seconds]          # load a save mid-run, as the Load menu does
    report                                 # fail listing every check that failed in this run

The error window reads the run's `Papyrus.0.log` forward from where the
case runner's trace stood, and groups each error by cause, script and
function with the preflight's play-test reader (`log_triage.classify`).
An error is charged to the first frame of its stack in a converted script,
so a native call failing inside one of ours still counts; errors whose
stack holds none of ours (vanilla and DLC scripts) are ignored.

See: docs/fork/fo4_test_layers_plan.md#l1
"""
import dataclasses
import re
import time
from collections import Counter
from pathlib import Path

from tools.live import fo4_test_instance as T
from tools.live.fo4_story_moves import CaseFailed
from tools.live.game_bridge import BridgeError
from tools.validate.preflight.log_triage import classify, strip_stamp

#: Script name prefixes of the converted scripts: both games' generated ones, the shared helpers and the polyfill.
CONVERTED = ('FALLOUTNV_', 'FALLOUT3_', 'F3NV_', 'TES4Polyfill', 'TES4_')
#: Seconds `errors` waits by default for the log to catch up before it reads.
SETTLE_SECONDS = 1.0
#: Seconds a `load` has to finish loading the save (the test DLL's `loads` count rises).
LOAD_START_SECONDS = 120
#: Seconds before a `load` the game has not taken is queued again (a script's autosave can drop the queued load).
LOAD_REQUEUE_SECONDS = 30
#: Seconds after a load whose errors are the save's background (start-up, other quests' timers), not the case's.
LOAD_SETTLE_SECONDS = 6.0
#: What separates a `check` step from its note.
NOTE = ' | '
#: Steps whose failure, after their own full wait, breaks the talk their note names.
GATES = ('talk', 'choose')
#: Steps of a broken talk that are skipped; `heard` still looks briefly, and `bye` always runs.
SKIPPED = ('look', 'talk', 'choose')
#: Seconds a broken talk's `heard` looks for a wanted line already said on its own (a greeting line).
BROKEN_HEAR_SECONDS = 5
#: A stack frame: `[owner].Script.Function() - "file" Line N`, giving the script.
FRAME = re.compile(r'\]\.(\w+)\.\w+\(\)')


# ---------------------------------------------------------------------------
#  The error window
# ---------------------------------------------------------------------------

def converted(script: str, prefixes: tuple) -> bool:
    """Whether `script` starts with one of `prefixes` (any case)."""
    return script.lower().startswith(tuple(p.lower() for p in prefixes))


def ours_first(lines: list, prefixes: tuple) -> list:
    """`lines` with each stack's frames reordered so its first frame in a `prefixes` script comes first."""
    out, frames = [], []
    for line in lines + ['']:
        if line.startswith('\t'):
            frames.append(line)
            continue
        found = [f for f in frames if (m := FRAME.search(f)) and converted(m.group(1), prefixes)]
        out += found[:1] + [f for f in frames if f not in found[:1]] + [line]
        frames = []
    return out[:-1]


class ErrorWindow:
    """The Papyrus log, read forward from `offset`: each look sees only what was written since the last."""

    def __init__(self, path: Path, offset: int):
        """Starts at byte `offset` of log `path`."""
        self.path, self.offset = Path(path), offset

    def lines(self) -> list:
        """The whole lines written since the last look, their timestamps stripped; a shorter log starts over."""
        if not self.path.is_file():
            return []
        if self.path.stat().st_size < self.offset:
            self.offset = 0
        with open(self.path, 'rb') as f:
            f.seek(self.offset)
            chunk = f.read()
        complete = chunk.rfind(b'\n') + 1
        self.offset += complete
        return [strip_stamp(line) for line in chunk[:complete].decode('utf-8', 'replace').splitlines()]

    def causes(self, prefixes: tuple) -> Counter:
        """{cause: count} of the errors `prefixes` scripts raised since the last look."""
        return Counter(key for key, script, _detail in classify(ours_first(self.lines(), prefixes))
                       if converted(script, prefixes))


@dataclasses.dataclass
class Sweep:
    """One run's sweep state: its error window, the causes the last load's save raised on its own (background), the
    checks run and those that failed (note, step, why)."""

    errors: ErrorWindow
    failed: list = dataclasses.field(default_factory=list)
    #: `unmet` steps that did not hold (note, step, why): waits on a need the sweep never meets, reported apart.
    unmet: list = dataclasses.field(default_factory=list)
    checked: int = 0
    background: frozenset = frozenset()
    #: Notes whose talk broke at a gate step (GATES): the rest of that talk is cut short.
    broken: set = dataclasses.field(default_factory=set)


def resume(state: Sweep, trace) -> Sweep:
    """`state` in a relaunched game: failed checks kept, a fresh error window."""
    state.errors = ErrorWindow(trace.path, trace.offset)
    return state


def sweep_of(game) -> Sweep:
    """The run's sweep state, kept on `game`; its window starts where the trace stands."""
    if getattr(game, 'sweep', None) is None:
        game.sweep = Sweep(ErrorWindow(game.trace.path, game.trace.offset))
    return game.sweep


# ---------------------------------------------------------------------------
#  Steps
# ---------------------------------------------------------------------------

def errors(game, rest: str) -> None:
    """Fails listing, by cause, the errors converted scripts raised since the last `errors` or `load`, read after
    `[seconds]` (default SETTLE_SECONDS); further words are script prefixes replacing CONVERTED."""
    words = rest.split()
    settle = float(words.pop(0)) if words and words[0].replace('.', '', 1).isdigit() else SETTLE_SECONDS
    time.sleep(settle)
    state = sweep_of(game)
    found = {key: n for key, n in state.errors.causes(tuple(words) or CONVERTED).items() if key not in state.background}
    if found:
        raise CaseFailed('%d Papyrus error(s): %s' % (sum(found.values()),
                                                     '; '.join('%dx %s' % (n, key) for key, n in found.items())))


def check(game, rest: str, run_step, unmet: bool = False) -> None:
    """Runs step `<verb> <rest> [| note]` with `run_step`; a failure is printed and kept for `report` (apart, with
    `unmet`), not raised. Once a gate step (GATES) of a note failed, that note's SKIPPED steps are skipped and its
    `heard` looks only BROKEN_HEAR_SECONDS.
    See: docs/fork/fo4_test_layers_plan.md#fail-fast
    """
    step, _, note = (part.strip() for part in rest.partition(NOTE))
    verb, _, inner = step.partition(' ')
    state = sweep_of(game)
    broken = bool(note) and note in state.broken
    if broken and verb in SKIPPED:
        print('    skipped (the talk broke): %s' % step, flush=True)
        return
    if broken and verb == 'heard':
        inner = re.sub(r'^\d+(\.\d+)?\s', '', inner.strip())
        inner = '%d %s' % (BROKEN_HEAR_SECONDS, inner)
    state.checked += 1
    try:
        run_step(game, verb, inner.strip())
    except CaseFailed as err:
        (state.unmet if unmet else state.failed).append((note, step, str(err)))
        state.broken |= {note} if note and verb in GATES else set()
        print('    %s %s: %s' % ('UNMET' if unmet else 'CHECK FAILED', note or step, err), flush=True)


def load(game, rest: str, ready) -> None:
    """Loads sandbox save `<save> [seconds]` mid-run as the Load menu does, waits until the save has loaded (the
    test DLL's `loads` count rises: a load in the same cell can show no loading menu between polls) and play
    resumes (`ready`, up to seconds), then keeps the causes of LOAD_SETTLE_SECONDS more as the background, which
    `errors` leaves out, and starts the error window afresh.
    See: docs/fork/fo4_test_layers_plan.md#s3
    """
    save, _, seconds = rest.partition(' ')
    try:
        queue_load(game.bridge, save)
        ready(game.bridge, seconds.strip())
    except BridgeError as err:
        raise CaseFailed('load %s: %s' % (save, err)) from err
    time.sleep(LOAD_SETTLE_SECONDS)
    state = sweep_of(game)
    state.background = frozenset(state.errors.causes(CONVERTED))


def queue_load(bridge, save: str) -> None:
    """Queues `save` until the test DLL's `loads` count rises, again every LOAD_REQUEUE_SECONDS the game has not
    taken it, for up to LOAD_START_SECONDS; raises BridgeError E_TIMEOUT after that.
    See: docs/fork/fo4_test_layers_plan.md#s3
    """
    before = bridge.status().get('loads', 0)
    deadline = time.time() + LOAD_START_SECONDS
    while True:
        print('    load -> %s' % bridge.request('load', text=save), flush=True)
        wait = min(LOAD_REQUEUE_SECONDS, max(deadline - time.time(), 0))
        try:
            T.wait_status(bridge, lambda s: s.get('loads', 0) > before, wait)
            return
        except BridgeError as err:
            if err.code != 'E_TIMEOUT' or time.time() >= deadline:
                raise


def report(game) -> None:
    """Lists the `unmet` waits that did not hold, then fails listing every `check` that failed in this run (note,
    step, why); passes when none did."""
    state = sweep_of(game)
    if state.unmet:
        print('    %d waits unmet, each on a need the sweep never meets:\n%s' % (len(state.unmet), '\n'.join(
            '      %s: `%s`: %s' % entry for entry in state.unmet)), flush=True)
    if state.failed:
        raise CaseFailed('%d of %d checks failed:\n%s' % (len(state.failed), state.checked, '\n'.join(
            '      %s: `%s`: %s' % entry for entry in state.failed)))
    print('    all %d checks passed' % state.checked, flush=True)
