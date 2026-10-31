"""Prerequisites: facts that stay true once true, read from either plugin's conditions.

A prerequisite is a required condition (alone in its OR chain, compared with a
number) that a stage is reached or done, an objective is shown or completed, a
quest is completed, or a reference is dead. Stage thresholds compare by quest
and number, so stage 50 reached covers stage 30.

See: docs/fork/fo4_timing_audit.md#prereqs
"""

from tools.validate.preflight.condition_diff import OR_NEXT, USE_GLOBAL

#: Comparison bits that require at least the value (==, >, >=), with what a strict > adds.
_AT_LEAST = {0x00: 0, 0x40: 1, 0x60: 0}

#: Comparison bits that read `!= 0`, the other way to require a yes/no fact.
_NOT_ZERO = 0x20

#: Yes/no facts that once true stay true, by the name the condition vocabulary gives them.
_ONCE_TRUE = {'GetStageDone': 'done', 'GetQuestCompleted': 'completed', 'GetDead': 'dead',
              'objdone': 'objdone', 'objshown': 'objshown'}


def _required(conds: list) -> list:
    """The conditions alone in their OR chain."""
    out, chain = [], []
    for cond in conds:
        chain.append(cond)
        if not cond['type'] & OR_NEXT:
            out += chain if len(chain) == 1 else []
            chain = []
    return out


def _yes(op: int, value: float) -> bool:
    """Whether a comparison requires a yes/no fact to be 1."""
    return (op == 0x00 and value == 1.0) or (op == _NOT_ZERO and value == 0.0) or (op == 0x60 and value == 1.0)


def atom(key: tuple, op: int, value: float):
    """The prerequisite one condition's fact `key` (a condition_diff fact key) requires, or None."""
    name = key[0]
    if name == 'GetStage' and op in _AT_LEAST and value + _AT_LEAST[op] > 0:
        return 'stage', key[2][0], value + _AT_LEAST[op]
    if name not in _ONCE_TRUE or not _yes(op, value):
        return None
    if name in ('objdone', 'objshown'):
        return _ONCE_TRUE[name], key[1], key[2]
    if name == 'GetDead':
        return ('dead', key[1], 0) if isinstance(key[1], tuple) else None
    return _ONCE_TRUE[name], key[2][0], key[2][1] if name == 'GetStageDone' else 0


def prerequisites(conds: list, fact) -> frozenset:
    """The prerequisites decoded conditions `conds` require; `fact` reads one into (key, identity) or a marker."""
    out = set()
    for cond in _required(conds):
        read = fact(cond)
        if isinstance(read, tuple) and read[1] is None and not cond['type'] & USE_GLOBAL:
            found = atom(read[0], cond['type'] & 0xE0, cond['value'])
            out |= {found} if found else set()
    return frozenset(out)


def stage_reached(quest, stage: int) -> frozenset:
    """A stage fragment's needs: its stage reached and done."""
    return frozenset({('stage', quest, float(stage)), ('done', quest, stage)})


def implied(need: tuple, have: frozenset) -> bool:
    """Whether the prerequisites `have` imply `need`; a stage reached or done implies every lower stage reached."""
    if need in have:
        return True
    kind, quest, number = need
    return kind == 'stage' and any(k in ('stage', 'done') and q == quest and n >= number for k, q, n in have)


def common(sets: list) -> frozenset:
    """What every one of `sets` implies (any one writer suffices)."""
    if not sets:
        return frozenset()
    return frozenset(need for need in sets[0] if all(implied(need, other) for other in sets[1:]))


def missing(need: frozenset, have: frozenset) -> list:
    """The prerequisites in `need` that `have` does not imply, sorted."""
    return sorted((n for n in need if not implied(n, have)), key=repr)


def describe(need: tuple) -> str:
    """A prerequisite in words."""
    kind, quest, number = need
    name = quest[1] if isinstance(quest, tuple) and len(quest) == 2 else quest
    words = {'stage': 'stage {n} reached', 'done': 'stage {n} done', 'objdone': 'objective {n} completed',
             'objshown': 'objective {n} shown', 'completed': 'completed', 'dead': 'dead'}[kind]
    return f'{name} ' + words.format(n=int(number))
