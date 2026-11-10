"""xNVSE `Break` and `Continue` in a While or ForEach body, lowered to flags (Papyrus has neither).

A jump sets the pass's skip flag (and, for Break, the loop's break flag, which the While tests), and
every statement after a statement that may jump is guarded by `If !skip`, at each nesting level up to
the loop. A jump inside a nested loop belongs to that loop.
See: docs/fork/nvse_script_language.md#loops
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from script_convert.tes4 import nodes as N

#: Loops a jump never crosses.
_LOOPS = (N.While, N.ForEach)


@dataclass
class Jumps:
    """How one loop's jumps lower: its flag locals, and the rewritten body."""
    body: list
    skip: str = ''
    brk: str = ''
    declare: list = field(default_factory=list)

    def condition(self, cond):
        """The While condition node, also ending the loop once a Break ran."""
        if not self.brk:
            return cond
        return N.BinOp('&&', dataclasses.replace(cond, parenthesised=True), N.Raw(f'!{self.brk}', line=cond.line),
                       line=cond.line)


def _jumps_in(body) -> set:
    """The jump kinds (Break, Continue) in `body` that belong to its loop."""
    found = set()
    for st in body or ():
        if isinstance(st, (N.Break, N.Continue)):
            found.add(type(st))
        elif not isinstance(st, _LOOPS):
            for attr in ('body', 'orelse'):
                found |= _jumps_in(getattr(st, attr, None))
            for entry in getattr(st, 'elifs', None) or ():
                found |= _jumps_in(entry[1])
    return found


def _line(text: str, line: int) -> N.Stmt:
    """A finished Papyrus statement."""
    return N.ExprStmt(expr=N.Raw(text, line=line), line=line)


def lower(conv, body: list) -> Jumps:
    """`body` of a loop with its jumps as flags; unchanged (no flags) when it has none."""
    kinds = _jumps_in(body)
    if not kinds:
        return Jumps(body)
    conv.sc.loop_locals += 1
    n = conv.sc.loop_locals
    jumps = Jumps(body, skip=f'TES4_Skip{n}', brk=f'TES4_Break{n}' if N.Break in kinds else '')
    jumps.declare = [f'Bool {name} = False' for name in (jumps.skip, jumps.brk) if name]
    line = body[0].line if body else 0
    jumps.body = [_line(f'{jumps.skip} = False', line)] + _guard(body, jumps)
    return jumps


def _guard(body: list, jumps: Jumps) -> list:
    """`body` with each jump as flag writes and the statements after a possible jump under `If !skip`."""
    out = []
    for i, st in enumerate(body):
        if isinstance(st, (N.Break, N.Continue)):
            sets = [jumps.brk] if isinstance(st, N.Break) else []
            return out + [_line(f'{flag} = True', st.line) for flag in sets + [jumps.skip]]
        if isinstance(st, _LOOPS) or not _jumps_in([st]):
            out.append(st)
            continue
        out.append(_guard_nested(st, jumps))
        rest = _guard(body[i + 1:], jumps)
        if rest:
            out.append(N.If(cond=N.Raw(f'!{jumps.skip}', line=st.line), body=rest, line=st.line))
        return out
    return out


def _guard_nested(st, jumps: Jumps):
    """A guarded copy of an If holding a jump (a body may be emitted twice)."""
    return dataclasses.replace(st, body=_guard(st.body, jumps), orelse=_guard(st.orelse, jumps),
                               elifs=[(c, _guard(b, jumps), n) for c, b, n in st.elifs])
