"""The story cases' dialogue step: `choose` picks a line in our dialogue menu (Cleanroom UI's DialogueMenu movie) by
its prompt's words, as a player does, with that row's number key.

See: docs/fork/fo4_story_tests.md#cases
"""

import html
import re
import time

from tools.live import hidden_launch
from tools.live.fo4_story_moves import CaseFailed, activate, aim, walk
from tools.live.fo4_test_instance import send, wait_status
from tools.live.game_bridge import Bridge, BridgeError

#: The menu's list box (in its Question holder) and its rows (crui ScrollList: count, top; fields named 0, 1...).
LIST = 'FadeHolder_mc.Question.0'
ROWS = LIST + '.0'
#: The rows the list shows at once (DialogueMenu.ROWS), each picked by its number key from the top shown.
ROW_KEYS = 5
#: Bridge errors while the menu is closed, loading, or not yet built its list: choose keeps waiting.
NOT_YET = ('E_NOMENU', 'E_LOADING', 'E_NOPATH')
#: Seconds `talk` waits for the dialogue menu before activating the NPC again.
TALK_RETRY = 6
#: Units from an NPC `talk` steps to after someone standing in the way answered E.
TALK_NEAR = 64
#: Half-second checks that the NPC `talk` activated is the one talking before taking it as someone else.
SPEAKER_CHECKS = 4
#: Seconds `choose` waits for its row press to hide the list before pressing again.
PRESS_WAIT = 3
#: Rounds of Enter and E `talk` presses on an open message box before it fails.
BOX_TRIES = 3
#: A `choose` alternative: nothing to pick is fine (another way of the talk already ended at an earlier pick).
NOTHING = '-'


def plain(text: str) -> str:
    """`text` decoded, lower case, single spaces, a [tag] before words dropped."""
    text = re.sub(r'^\[[^\]]*\]\s*(?=\S)', '', html.unescape(text))
    return ' '.join(text.lower().split())


def read(bridge: Bridge, path: str):
    """The dialogue menu movie's value at `path`."""
    return bridge.request('invoke', text='DialogueMenu ' + path).get('result')


def options(bridge: Bridge) -> list:
    """The rows the dialogue menu's list shows now, as drawn ([] while it is hidden)."""
    if not read(bridge, LIST + '.visible'):
        return []
    shown = int(read(bridge, ROWS + '.count')) - int(read(bridge, ROWS + '.top'))
    return [str(read(bridge, '%s.%d.text' % (ROWS, i))) for i in range(min(shown, ROW_KEYS))]


def row_of(listed: list, words: str) -> int:
    """The shown row whose prompt holds `words` (compared plain), or row N for `#N`; with `A || B`, the first
    alternative that is listed; -1 when none."""
    if re.fullmatch(r'#\d+', words.strip()):
        row = int(words.strip()[1:]) - 1
        return row if row < len(listed) else -1
    for wanted in map(plain, words.split(' || ')):
        row = next((i for i, text in enumerate(listed) if wanted in plain(text)), -1) if wanted != NOTHING else -1
        if row >= 0:
            return row
    return -1


def accept_boxes(bridge: Bridge, front) -> None:
    """Accepts any open message box (a notice, such as a reputation change) with Enter, then E, as a player does
    before talking on; fails when neither closes it."""
    for scan in (hidden_launch.SCAN_ENTER, hidden_launch.SCANCODES['e']) * BOX_TRIES:
        if 'MessageBoxMenu' not in bridge.status()['menus']:
            return
        front()
        hidden_launch.tap_key(scan)
        time.sleep(1)
    if 'MessageBoxMenu' in bridge.status()['menus']:
        raise CaseFailed('a message box stayed open')


def in_dialogue(bridge: Bridge, ref: str) -> bool:
    """Whether `ref` is in dialogue with the player now: IsInDialogueWithPlayer's `>> 1`, or its text answer."""
    said = send(bridge, '%s.IsInDialogueWithPlayer' % ref)
    if '>>' in said:
        return float(said.rsplit('>>', 1)[1].split()[0]) == 1
    return ' is in dialogue state' in said


def talk(bridge: Bridge, rest: str, timed, front) -> None:
    """`[seconds] <ref>`: a dialogue the ref opened itself (a force greet) is the talk; else once no dialogue menu
    is open, the player activates the ref until the dialogue menu opens, again every TALK_RETRY seconds (an NPC
    still busy with a bark); a message box meanwhile is accepted first (accept_boxes). The player looks at the
    ref (aim) before each E and once the talk is open: FO4 lists choices only while facing the speaker.
    See: docs/fork/fo4_test_layers_plan.md#objective-fallback
    See: docs/fork/fo4_pipeline.md#psych-test-no-choices
    """
    seconds, target = timed(rest)
    deadline = time.time() + seconds
    if 'DialogueMenu' in bridge.status()['menus'] and in_dialogue(bridge, target):
        aim(bridge, target)
        return
    try:
        wait_status(bridge, lambda s: 'DialogueMenu' not in s['menus'], seconds)
    except BridgeError as err:
        raise CaseFailed('another conversation stayed open: %s' % err) from err
    while True:
        accept_boxes(bridge, front)
        activate(bridge, target, front)
        try:
            wait_status(bridge, lambda s: 'DialogueMenu' in s['menus'], min(TALK_RETRY, deadline - time.time()))
        except BridgeError as err:
            if err.code != 'E_TIMEOUT' or time.time() >= deadline:
                raise CaseFailed('no dialogue menu from %s: %s' % (target, err)) from err
            step_nearer(bridge, target, front)
            continue
        if answered(bridge, target, front):
            aim(bridge, target)
            return
        if time.time() >= deadline:
            raise CaseFailed('E kept opening a talk with someone other than %s' % target)


def step_nearer(bridge: Bridge, target: str, front) -> None:
    """The player walks within TALK_NEAR of `target` (E reaches about 150)."""
    walk(bridge, '%s %d' % (target, TALK_NEAR), front)


def answered(bridge: Bridge, target: str, front) -> bool:
    """Whether the talk that opened is `target`'s; when someone standing in the way answered instead, the player
    leaves that talk (bye) and steps within TALK_NEAR of the target."""
    for _ in range(SPEAKER_CHECKS):
        if in_dialogue(bridge, target):
            return True
        time.sleep(0.5)
    print('    someone else answered E: stepping nearer %s' % target, flush=True)
    bye(bridge, '', front)
    step_nearer(bridge, target, front)
    return False


def choose(bridge: Bridge, rest: str, front, timed) -> None:
    """`[seconds] <words>`: waits for a listed prompt holding the words, scrolling a longer list down a row at a time
    as the Down key does, then presses its row's number key in the game window (brought to the front); fails
    naming what was listed, unless NOTHING is an alternative."""
    seconds, words = timed(rest)
    deadline, listed = time.time() + seconds, []
    while time.time() <= deadline:
        try:
            listed = options(bridge)
            row = row_of(listed, words)
            if row < 0 and listed and int(read(bridge, ROWS + '.count')) > ROW_KEYS:
                read(bridge, ROWS + '.move 1')
        except BridgeError as err:
            if err.code not in NOT_YET:
                raise CaseFailed(str(err)) from err
            row = -1
        if row >= 0 and press(bridge, row, listed, front):
            return
        time.sleep(0.5)
    if NOTHING in words.split(' || '):
        print('    nothing picked: another way already ended', flush=True)
        return
    raise CaseFailed('no option "%s" in %s' % (words, listed))


def bye(bridge: Bridge, rest: str, front) -> None:
    """`[seconds]`: the player leaves the talk with Tab, again every PRESS_WAIT seconds, until no dialogue menu is
    open (default TALK_RETRY seconds)."""
    deadline = time.time() + (float(rest) if rest.strip() else TALK_RETRY)
    while leave(bridge, front):
        if time.time() > deadline:
            raise CaseFailed('the dialogue menu stayed open')
        time.sleep(PRESS_WAIT)


def leave(bridge: Bridge, front) -> bool:
    """Presses Tab once in an open talk, as a player leaving it; whether a dialogue menu was open."""
    if 'DialogueMenu' not in bridge.status()['menus']:
        return False
    front()
    hidden_launch.tap_key(hidden_launch.SCANCODES['tab'])
    return True


def press(bridge: Bridge, row: int, listed: list, front) -> bool:
    """Presses `row`'s number key; True once the list stops showing `listed` (the menu hides on a pick) within
    PRESS_WAIT seconds, else False so `choose` presses again, as a player does when a key press is lost."""
    print('    choose row %d of %s' % (row + 1, listed), flush=True)
    front()
    hidden_launch.tap_key(hidden_launch.SCANCODES[str(row + 1)])
    deadline = time.time() + PRESS_WAIT
    while time.time() < deadline:
        time.sleep(0.25)
        try:
            if options(bridge) != listed:
                return True
        except BridgeError as err:
            if err.code not in NOT_YET:
                raise CaseFailed(str(err)) from err
            return True
    print('    the press was not taken; again', flush=True)
    return False
