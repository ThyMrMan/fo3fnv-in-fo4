"""TES4 statement tree -> Papyrus text.

The counterpart to `emit/expr.py`.  `_convert_line_inner` decides what a line
IS by running fourteen regexes in order -- `label <n>`, `goto <n>`, `foreach`,
a variable declaration, an array write, an array read, `set X to Y`,
`let X := Y`, a control keyword, `setfunctionvalue`, `return` -- and the
parser has already answered every one of those as a node type.  So this
module is only the TES4->TES5 SEMANTICS of each statement kind.

Like the expression emitter, it is NOT pure: converting a statement discovers
external references and registers them on the converter's `_property_refs`,
which the importer reads to build VMAD property bindings.

Statements that need converter state the tree does not carry (the OBSE
ref-walk's label set, the chargen-menu sequence, the Say timer) delegate back
to the string path for now; R4 moves the command layer and those follow.
"""

from __future__ import annotations

import dataclasses

from script_convert import nvse_falloutnv as nvse
from script_convert.emit import expr as E
from script_convert.tes4 import nodes as N


def emit(conv, stmt: N.Stmt, extends: str) -> str:
    """Papyrus text for one TES4 statement node.

    Returns the converted line WITHOUT indentation -- the caller owns layout,
    exactly as `_convert_line` did.  A trailing source comment is re-attached
    by the caller too, since it must survive whatever the statement became.
    """
    if isinstance(stmt, N.Comment):
        return stmt.text
    if isinstance(stmt, N.Blank):
        return ''
    handler = _EMITTERS.get(type(stmt))
    return handler(conv, stmt, extends) if handler else ''


def _declaration(conv, stmt: N.VarDecl, extends: str) -> str:
    """Nothing (the script assembler hoists declarations), or xNVSE `int i = 5`'s assignment where it stands."""
    if stmt.value is None:
        return ''
    target = N.Ident(stmt.name, line=stmt.line)
    return _assignment(conv, N.Assign(target=target, value=stmt.value, is_let=True, line=stmt.line), extends)


def _assignment(conv, stmt: N.Assign, extends: str) -> str:
    """`set`/`let`, an xNVSE array write as its own text."""
    got = nvse.assignment(conv, stmt, extends)
    return got if isinstance(got, str) else conv.emit_assignment(got, extends)


def _command(conv, stmt: N.ExprStmt, extends: str) -> str:
    """A bare command; the line wrapper folds a `0` and its notes to a comment."""
    return conv.emit_command_statement(nvse.lower(conv, stmt.expr, extends), extends)


def _function_value(conv, stmt: N.SetFunctionValue, extends: str) -> str:
    """OBSE `SetFunctionValue`, its value's xNVSE parts lowered."""
    return conv.emit_set_function_value(dataclasses.replace(stmt, value=nvse.lower(conv, stmt.value, extends)),
                                        extends)


def _stray_jump(_conv, stmt, _extends: str) -> str:
    """A Break/Continue no loop owns, which xNVSE ignores."""
    return f';{type(stmt).__name__}  ;NE: outside any loop'


#: Statement node -> `(conv, stmt, extends) -> text`.
_EMITTERS = {
    N.Comment: lambda _c, stmt, _e: stmt.text,
    N.Blank: lambda _c, _s, _e: '',
    N.VarDecl: _declaration,
    N.If: lambda conv, stmt, extends: _if(conv, stmt, extends),
    N.While: lambda conv, stmt, extends: f'While {emit_condition(conv, stmt.cond, extends)}',
    N.Assign: _assignment,
    N.ExprStmt: _command,
    N.Return: lambda conv, stmt, extends: conv.emit_return(stmt, extends),
    N.SetFunctionValue: _function_value,
    N.Label: lambda conv, stmt, extends: conv.emit_jump(stmt, extends),
    N.Goto: lambda conv, stmt, extends: conv.emit_jump(stmt, extends),
    N.Break: _stray_jump,
    N.Continue: _stray_jump,
}


def _if(conv, stmt: N.If, extends: str) -> str:
    """`If`/`ElseIf` header text for the node.

    Only the HEADER: the body and the `Else`/`EndIf` closers are emitted by
    the caller walking the block, because Papyrus wants them as separate
    lines and the tree owns the nesting.
    """
    cond = emit_condition(conv, stmt.cond, extends)
    # A condition that converted entirely to a `;TODO:` comment would comment
    # out the keyword itself and take the block structure with it.
    if cond.lstrip().startswith(';TODO:'):
        return f'If True  {cond}'
    return f'If {cond}'


def emit_condition(conv, cond: N.Expr, extends: str) -> str:
    """A condition, keeping the author's own outer parentheses.

    TES4 conditions are conventionally written `if ( x == 1 )` and the
    converter echoes those parens into the output.  The tree drops them as
    redundant, which is correct but makes every such line differ -- and the
    parens are recorded on the node precisely so this is a node question, not
    a re-scan of the source text.
    """
    text = E.emit(conv, nvse.lower(conv, cond, extends, 'Bool'), extends)
    if (getattr(cond, 'parenthesised', False)
            and not text.startswith(('(', ';'))):
        return f'({text})'
    return text
