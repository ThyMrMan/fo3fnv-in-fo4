"""FO3/FNV topic unlocks: the Top-level flag, and what a revealing greeting needs that its topic does not.

FO3/FNV list a Top-level topic from the start, so it is never gated. A topic
only greetings add is known once one of them plays; when every such greeting
needs a stage or objective that some line of the topic does not, ungating it
would show it before FNV does (the Freeside vagrant's VMS49 topics), so it
stays gated.

See: docs/fork/fo4_timing_audit.md#fixes
"""

import struct

#: FO3/FNV DIAL flag: listed from the start.
TOP_LEVEL = 0x02

#: Condition functions whose required value, once reached, stays: GetStage, GetStageDone, objective completed, shown.
GET_STAGE, ONCE_TRUE = 58, frozenset({59, 420, 421})

#: Comparison bits (the top three of the type) that require at least the value: ==, >, >=; and the OR flag.
_AT_LEAST, OR_NEXT = {0x00: 0, 0x40: 1, 0x60: 0}, 0x01


def is_fallout(dials: list) -> bool:
    """Whether DIAL export records are FO3/FNV's (only theirs carry flags)."""
    return any('DATA.Flags' in d for d in dials)


def is_top_level(dial: dict) -> bool:
    """Whether an FO3/FNV topic is listed from the start."""
    return bool(int(dial.get('DATA.Flags', 0) or 0) & TOP_LEVEL)


def _conditions(rec: dict) -> list:
    """(type, value, function, parameter 1 low 24 bits, parameter 2) of an INFO's conditions."""
    out = []
    for i in range(int(rec.get('ConditionCount', 0) or 0)):
        data = bytes.fromhex(rec.get(f'Condition[{i}].Raw', '') or '') + bytes(20)
        ctype, value = data[0], struct.unpack_from('<f', data, 4)[0]
        func, p1, p2 = struct.unpack_from('<HxxII', data, 8)
        out.append((ctype, value, func, p1 & 0xFFFFFF, p2))
    return out


def prerequisites(rec: dict) -> frozenset:
    """The (function, quest, parameter, at least) facts an INFO requires that stay true once true."""
    out, chain = set(), []
    for cond in _conditions(rec):
        chain.append(cond)
        if cond[0] & OR_NEXT:
            continue
        if len(chain) == 1:
            ctype, value, func, p1, p2 = cond
            op = ctype & 0xE0
            if func == GET_STAGE and op in _AT_LEAST and value + _AT_LEAST[op] > 0:
                out.add((GET_STAGE, p1, 0, value + _AT_LEAST[op]))
            elif func in ONCE_TRUE and op == 0x00 and value == 1.0:
                out.add((func, p1, p2, 1.0))
        chain = []
    return frozenset(out)


def implied(need: tuple, have: frozenset) -> bool:
    """Whether `have` implies `need` (a higher stage covers a lower one)."""
    func, quest, param, least = need
    return need in have or (func == GET_STAGE and any(
        q == quest and ((f == GET_STAGE and v >= least) or (f == 59 and p >= least)) for f, q, p, v in have))


def waits_longer(revealers: list, lines: list) -> bool:
    """Whether every revealer needs a fact some line of the topic does not: knowing the topic waits for it."""
    sets = [prerequisites(r) for r in revealers]
    if not sets:
        return False
    common = [n for n in sets[0] if all(implied(n, s) for s in sets[1:])]
    needs = [prerequisites(r) for r in lines]
    return any(not implied(n, line) for n in common for line in needs)
