"""What a source stage setter needs that the layer 1 stage sweep cannot give it: the conditions around its SetStage.

The sweep sets stages and waits; the lines and scenes that follow play, but
it moves, fights and opens no menu itself. A condition holds for it when it
tests a stage or a quest (GetStage, GetStageDone, GetQuestRunning), a timer
the script counts, a variable at 0 or at a value a stage result, a line or
the setter's own script sets it to, or a function at the 0 it returns
before anything happens (GetSitting == 0 holds, GetDead == 1 does not). The
rest is a need, as is a MenuMode block naming a menu; the sweep reports a
wait on such a setter as unmet, not failed.

See: docs/fork/fo4_test_layers_plan.md#setter-needs
"""
import operator
import re

from tools.dialog.tes4_ctda_dump import xedit_table
from tools.validate.preflight.quest_source import coded_lines, or_groups

#: Script words and condition functions the sweep's own setstage and waiting satisfy.
SWEPT = frozenset({'getstage', 'getstagedone', 'getquestrunning', 'getsecondspassed'})
#: The opener of an `if` frame, its other branches, and its close, on a code line.
IF, ELSEIF, ELSE, ENDIF = (re.compile(r'if\b', re.I), re.compile(r'elseif\b', re.I), re.compile(r'else\b', re.I),
                           re.compile(r'endif\b', re.I))
#: A timer: `set t to t - GetSecondsPassed` (a countdown) or `+` (a count up): (variable, sign).
COUNTED = re.compile(r'\bset\s+(\w+)\s+to\s+\(?\s*\1\s*([-+])\s*getsecondspassed', re.I)
#: A number set to a variable on a code line, `set [quest.]var to 2.5`: (quest or '', var, number).
NUMBER_SET = re.compile(r'\bset\s+(?:(\w+)\.)?(\w+)\s+to\s+(-?\d+(?:\.\d+)?|-?\.\d+)\s*$', re.I)
#: A test, `[ref.]name [arguments] [<op> n]`: (ref or None, name, arguments, op or None, number or None).
TEST = re.compile(r'^(?:(\w+)\.)?(\w+)\b(.*?)(?:\s*(==|!=|<=|>=|<|>)\s*(-?\d+(?:\.\d+)?|-?\.\d+))?$')
#: Comparison operators by name.
OPS = {'==': operator.eq, '!=': operator.ne, '<=': operator.le, '>=': operator.ge, '<': operator.lt, '>': operator.gt}
#: A CTDA's comparison by its type byte's top three bits.
CTDA_OPS = ('==', '!=', '>', '>=', '<', '<=')
#: The xEdit function table of each source game, by its export folder's plugin stem.
GAMES = {'fallout3': 'fo3'}
#: A script block that runs only while one menu is open: `MenuMode 1056`.
MENU_MODE = re.compile(r'menumode\s+\d', re.I)


def framed(frames: list, code: str) -> None:
    """Updates the open `if` frames (each the taken branch's condition, '' for an `else`) for code line `code`."""
    if ELSEIF.match(code) and frames:
        frames[-1] = code[6:].strip()
    elif ELSE.match(code) and frames:
        frames[-1] = ''
    elif IF.match(code):
        frames.append(code[2:].strip())
    elif ENDIF.match(code) and frames:
        frames.pop()


def branch(text: str, raw: str) -> list:
    """The conditions line `raw` of script `text` runs under: each enclosing `if`'s taken branch, outermost first
    (an `else`, which this does not negate, adds none)."""
    frames = []
    for code, line, _block in coded_lines(text):
        framed(frames, code.strip())
        if line == raw:
            return [f for f in frames if f]
    return []


def split_top(cond: str, sep: str) -> list:
    """`cond` split at each `sep` outside parentheses."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(cond):
        depth += {'(': 1, ')': -1}.get(cond[i], 0)
        if depth == 0 and cond.startswith(sep, i):
            parts.append(cond[start:i])
            start = i = i + len(sep)
            continue
        i += 1
    return parts + [cond[start:]]


def balanced(text: str) -> bool:
    """Whether every parenthesis in `text` closes inside it, in order."""
    depth = 0
    for ch in text:
        depth += {'(': 1, ')': -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def unwrap(cond: str) -> str:
    """`cond` without the parentheses around all of it."""
    cond = cond.strip()
    while cond.startswith('(') and cond.endswith(')') and balanced(cond[1:-1]):
        cond = cond[1:-1].strip()
    return cond


def numbers_set(text: str, owner: str, into: dict) -> None:
    """Adds to `into` each number `text` sets a variable to, keyed (owner, var)."""
    for code, _line, _block in coded_lines(text):
        for quest, var, number in NUMBER_SET.findall(code.strip()):
            into.setdefault(((quest or owner).lower(), var.lower()), set()).add(float(number))


class Needs:
    """One game's source, read for the variables stage results and lines set and the condition function names."""

    def __init__(self, source, texts: dict, game: str):
        """`source` is quest_source.SourceGame, `texts` {script lower: text}, `game` the export folder's name."""
        self.source, self.texts = source, texts
        self.funcs = xedit_table(GAMES.get(game.split('.')[0].lower(), 'fnv'))
        self.functions = {name.lower() for name in self.funcs.names.values()}
        self.sets = {}
        for (owner, _log), (text, _conditions) in source.stage_logs.items():
            numbers_set(text, owner.split('|')[0], self.sets)
        for info in source.infos.values():
            numbers_set(info.result, source.quest_fids.get(info.quest, ''), self.sets)

    def of(self, site) -> list:
        """What setter `site` (quest_source.Setter) needs that the sweep cannot give, in words; [] for nothing."""
        if site.kind == 'stage':
            text, conditions = self.source.stage_logs.get((site.owner, site.part), ('', []))
            logged = [] if all(any(self._logged(c) for c in g) for g in or_groups(conditions)) else [
                'the log entry\'s %s' % ' and '.join(self._words(c) for c in conditions)]
            return logged + self._script(text, site.raw, site.owner.split('|')[0].lower())
        if site.kind == 'script':
            text = self.texts.get(site.owner.lower(), '')
            menu = ['the menu of %s open' % site.part] if MENU_MODE.match(site.part) else []
            return menu + self._script(text, site.raw, self.source.quest_script_of.get(site.owner.lower()))
        return []

    def _logged(self, condition: tuple) -> bool:
        """Whether CTDA `condition` tests a stage or a quest, or holds at its function's 0."""
        name = self.funcs.name(condition[2]).lower()
        return name in SWEPT or OPS[CTDA_OPS[min(condition[0] >> 5, 5)]](0.0, condition[1])

    def _words(self, condition: tuple) -> str:
        """CTDA `condition` as `GetDead == 1`."""
        return '%s %s %g' % (self.funcs.name(condition[2]), CTDA_OPS[min(condition[0] >> 5, 5)], condition[1])

    def _script(self, text: str, raw: str, quest: 'str | None') -> list:
        """The conditions around line `raw` of `text` that the sweep cannot meet."""
        timers = {v.lower() for code, _line, _block in coded_lines(text) for v, _sign in COUNTED.findall(code)}
        own = {}
        numbers_set(text, quest or '', own)
        return [cond for cond in branch(text, raw) if not self._holds(cond, quest, timers, own)]

    def _holds(self, cond: str, quest: 'str | None', timers: set, own: dict) -> bool:
        """Whether script condition `cond` (in `quest`'s script, lower; None: an object's) can hold for the sweep
        (module notes); `own` holds the numbers the script itself sets (numbers_set())."""
        cond = unwrap(cond)
        alternatives = split_top(cond, '||')
        if len(alternatives) > 1:
            return any(self._holds(c, quest, timers, own) for c in alternatives)
        parts = split_top(cond, '&&')
        if len(parts) > 1:
            return all(self._holds(c, quest, timers, own) for c in parts)
        words = {w.lower() for w in re.findall(r'\w+', cond)}
        test = TEST.match(cond)
        if words & SWEPT or words & timers:
            return True
        if not test:
            return False
        owner, name, arguments, op, number = test.groups()
        if name.lower() not in self.functions and arguments.strip():
            return False
        key = ((owner or quest or '').lower(), name.lower())
        values = {0.0} if name.lower() in self.functions else {0.0} | self.sets.get(key, set()) | own.get(key, set())
        return any(OPS[op](v, float(number)) if op else v != 0 for v in values)
