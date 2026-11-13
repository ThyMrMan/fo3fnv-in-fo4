"""xNVSE's script language on Fallout 4: operators, arrays and string commands, lowered before emission.

`lower` rewrites the xNVSE parts of an expression into `Raw` nodes holding finished Papyrus, which the
expression emitter passes through, so everything else in the statement converts as before. A read of an
array element is a `Var`, which Papyrus accepts only in `If`, `!`, string concatenation and casts, so
every read is cast to what its position wants.
See: docs/fork/nvse_script_language.md#arrays
"""

from __future__ import annotations

import dataclasses
import re

from script_convert.emit import expr as E
from script_convert.symbols import needs_actor, type_of_expr
from script_convert.target import ARRAY_TYPE, is_fallout4
from script_convert.tes4 import nodes as N

#: The Papyrus script holding the array functions (static_scripts/fallout4/CRUI_Array.psc).
ARRAY = 'CRUI_Array'
#: Arguments CRUI_Array.List takes after its count (xNVSE ar_List takes at most 20); unused ones pass None.
LIST_SLOTS = 20
#: xNVSE's ar_BadNumericIndex (Commands_Array.cpp `s_arrayErrorCodeNum`).
BAD_NUMERIC_INDEX = '-99999'
#: Comparison operators: each side is cast to the other's type.
_COMPARE = frozenset({'==', '!=', '<>', '<', '>', '<=', '>='})
#: Arithmetic operators: an element read is a Float there.
_ARITH = frozenset({'+', '-', '*', '/', '%'})
#: xNVSE's integer operators -> F4SE's Math native.
_BITWISE = {'|': 'LogicalOr', '&': 'LogicalAnd', '<<': 'LeftShift', '>>': 'RightShift'}
#: Unary operators only xNVSE has.
_NVSE_UNARY = frozenset({'*', '&', '#'})
#: Array commands that return an array.
_ARRAY_MAKERS = frozenset({'ar_construct', 'ar_list', 'ar_null', 'ar_copy', 'ar_deepcopy'})
#: Array commands -> (CRUI_Array function, Papyrus result type, which arguments are arrays).
_ARRAY_CALLS = {
    'ar_size': ('Size', 'Int', (0,)), 'ar_haskey': ('HasKey', 'Bool', (0,)),
    'ar_find': ('Find', '', (1,)), 'ar_append': ('Append', 'Bool', (0,)),
    'ar_erase': ('Erase', 'Int', (0,)), 'ar_copy': ('Copy', ARRAY_TYPE, (0,)),
    'ar_deepcopy': ('Copy', ARRAY_TYPE, (0,)),
}
#: Zero-argument array commands, read bare: their Papyrus value and type.
_ARRAY_CONSTANTS = {'ar_null': ('None', ARRAY_TYPE), 'ar_badnumericindex': (BAD_NUMERIC_INDEX, 'Float'),
                    'ar_badstringindex': ('""', 'String')}
#: A printf specifier in an sv_Construct format string.
_FORMAT_SPEC = re.compile(r'%(?:%|[-+ #0]*\d*(?:\.\d*)?[a-zA-Z])')


# ---------------------------------------------------------------------------
# What is xNVSE
# ---------------------------------------------------------------------------

def _name(node) -> str:
    """The lower-cased command a Call or bare Ident names, else ''."""
    return node.name.lower() if isinstance(node, (N.Call, N.Ident)) else ''


def is_array(conv, node) -> bool:
    """Does `node` evaluate to an xNVSE array?"""
    if isinstance(node, N.Ident) and _name(node) not in _ARRAY_CONSTANTS:
        return conv.type_of(node.name) == ARRAY_TYPE
    if isinstance(node, N.Member):
        return conv.remote_type_of(f'{E.emit_bare(conv, node.owner)}.{node.name}') == ARRAY_TYPE
    if isinstance(node, N.Unary):
        return node.op == '&'
    return _name(node) in _ARRAY_MAKERS


def _is_nvse(conv, node) -> bool:
    """Is `node` itself an xNVSE construct the emitter cannot convert?"""
    if isinstance(node, N.Index):
        return True
    if isinstance(node, N.Unary):
        return node.op in _NVSE_UNARY
    if isinstance(node, N.BinOp):
        return node.op == '^' or node.op in _BITWISE
    low = _name(node)
    return low in _ARRAY_CALLS or low in _ARRAY_MAKERS or low in _ARRAY_CONSTANTS or low == 'sv_construct' \
        or is_array(conv, node)


def uses_nvse(conv, node) -> bool:
    """Does any part of expression `node` need lowering? Always False off Fallout 4."""
    return is_fallout4() and any(_is_nvse(conv, n) for n in N.walk_expr(node))


# ---------------------------------------------------------------------------
# Lowering
# ---------------------------------------------------------------------------

def lower(conv, node, extends: str, want: str = ''):
    """`node`, its xNVSE parts Raw Papyrus, for a `want`-typed position."""
    if node is None or not uses_nvse(conv, node):
        return node
    return _lower(conv, node, extends, want)


def _raw(node, text: str) -> N.Raw:
    """`text` as a Raw node standing where `node` stood."""
    return N.Raw(text, line=node.line)


def _cast(text: str, want: str) -> str:
    """An element read (`Var`) as `want`; '' leaves it a Var."""
    if not want or want == 'Var':
        return text
    if want == ARRAY_TYPE:
        return f'Utility.VarToVarArray({text})'
    return f'({text} as {want})'


def _lower(conv, node, extends: str, want: str):
    """`lower` without the fast path."""
    if isinstance(node, N.Index):
        return _raw(node, _cast(f'{ARRAY}.Get({array_text(conv, node.target, extends)}, '
                                f'{value_text(conv, node.index, extends)})', want))
    if isinstance(node, N.Unary):
        return _unary(conv, node, extends, want)
    if isinstance(node, N.BinOp):
        return _binop(conv, node, extends, want)
    if isinstance(node, N.Member) and not is_array(conv, node):
        return dataclasses.replace(node, owner=_lower(conv, node.owner, extends, _receiver_type(node.name)))
    if _name(node) in _ARRAY_CONSTANTS:
        return _raw(node, _ARRAY_CONSTANTS[_name(node)][0])
    if isinstance(node, N.Call):
        return _call(conv, node, extends, want)
    return node


def _unary(conv, node: N.Unary, extends: str, want: str):
    """`*` unbox, `&` box, `#` to number; `!` and the rest keep their operator over a lowered operand."""
    if node.op == '*':
        return _raw(node, _cast(f'{ARRAY}.Unbox({array_text(conv, node.operand, extends)})', want))
    if node.op == '&':
        return _raw(node, f'{ARRAY}.Box({value_text(conv, node.operand, extends)})')
    if node.op == '#':
        return _raw(node, f'({text(conv, node.operand, extends, "String")} as Float)')
    inner = 'Bool' if node.op == '!' else want
    return dataclasses.replace(node, operand=_lower(conv, node.operand, extends, inner))


def _binop(conv, node: N.BinOp, extends: str, want: str):
    """Each side lowered for its operator: compared against the other side's type, Float in arithmetic."""
    if node.op == '^':
        return _raw(node, f'Math.Pow({text(conv, node.left, extends, "Float")}, '
                          f'{text(conv, node.right, extends, "Float")})')
    if node.op in _BITWISE:
        return _raw(node, f'Math.{_BITWISE[node.op]}({text(conv, node.left, extends, "Int")}, '
                          f'{text(conv, node.right, extends, "Int")})')
    if node.op in _COMPARE:
        left, right = _side_type(conv, node.right), _side_type(conv, node.left)
    elif node.op in _ARITH:
        left = right = 'String' if 'String' in (_side_type(conv, node.left), _side_type(conv, node.right)) \
            and node.op == '+' else 'Float'
    else:
        left = right = 'Bool'
    return dataclasses.replace(node, left=_lower(conv, node.left, extends, left),
                               right=_lower(conv, node.right, extends, right))


def _side_type(conv, node) -> str:
    """The type to cast an element read compared with or combined with `node`: its own, else Float."""
    low = _name(node)
    if low in _ARRAY_CONSTANTS:
        return _ARRAY_CONSTANTS[low][1]
    if low in _ARRAY_CALLS:
        return _ARRAY_CALLS[low][1] or 'Float'
    got = type_of_expr(node, conv.type_of) if not _is_nvse(conv, node) else ''
    return 'Float' if got in ('', 'Int', 'Bool', 'GlobalVariable') else got


def _receiver_type(command: str) -> str:
    """The type an element read is cast to when `command` is called on it."""
    return 'Actor' if needs_actor(command) else 'ObjectReference'


def _call(conv, node: N.Call, extends: str, want: str):
    """An array or string command as Papyrus; any other command with its arguments and receiver lowered."""
    low = _name(node)
    if low in _ARRAY_CALLS or low in _ARRAY_MAKERS or low == 'sv_construct':
        return _raw(node, _array_call(conv, node, extends, want))
    receiver = _lower(conv, node.receiver, extends, _receiver_type(low)) if node.receiver is not None else None
    args = tuple(_lower(conv, a, extends, 'Form') for a in node.args)
    return dataclasses.replace(node, receiver=receiver, args=args)


def _array_call(conv, node: N.Call, extends: str, want: str) -> str:
    """Papyrus for one array command, or sv_Construct."""
    low = _name(node)
    if low == 'sv_construct':
        return format_text(conv, node.args, extends)
    if low == 'ar_construct':
        kind = node.args[0].text if node.args and isinstance(node.args[0], N.Literal) else '"Array"'
        return f'{ARRAY}.Construct({kind})'
    if low == 'ar_list':
        items = [value_text(conv, a, extends) for a in node.args[:LIST_SLOTS]]
        return f'{ARRAY}.List({", ".join([str(len(items))] + items + ['None'] * (LIST_SLOTS - len(items)))})'
    func, rtype, arrays = _ARRAY_CALLS[low]
    args = [array_text(conv, a, extends) if i in arrays else value_text(conv, a, extends)
            for i, a in enumerate(node.args)]
    call = f'{ARRAY}.{func}({", ".join(args)})'
    return call if rtype else _cast(call, want or 'Float')


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def text(conv, node, extends: str, want: str = '') -> str:
    """Papyrus for `node` lowered for a `want` position."""
    return E.emit(conv, lower(conv, node, extends, want), extends)


def value_text(conv, node, extends: str) -> str:
    """Papyrus for a value stored as a Var: an array goes through VarArrayToVar."""
    if is_array(conv, node):
        return f'Utility.VarArrayToVar({array_text(conv, node, extends)})'
    return text(conv, node, extends)


def array_text(conv, node, extends: str) -> str:
    """Papyrus for `node` used as an array; anything that is not one (an unconverted command) is a noted None."""
    if isinstance(node, N.Literal) and node.text.strip() == '0':
        return 'None'
    if is_array(conv, node) or isinstance(node, (N.Index, N.Unary)) or _name(node) in _ARRAY_CONSTANTS:
        return text(conv, node, extends, ARRAY_TYPE)
    conv._line_comments.append(f';NE: {E.emit_source(node)} - not an xNVSE array this converter makes')
    return 'None'


def format_text(conv, args, extends: str) -> str:
    """sv_Construct's printf: the format's text with each specifier replaced by its argument as a String."""
    if not args or not (isinstance(args[0], N.Literal) and args[0].is_string):
        return text(conv, args[0], extends, 'String') if args else '""'
    fmt, values = args[0].text[1:-1], list(args[1:])
    pieces, last = [], 0
    for m in _FORMAT_SPEC.finditer(fmt):
        if m.group(0) == '%%' or not values:
            continue
        pieces += [f'"{fmt[last:m.start()]}"'] if m.start() > last else []
        pieces.append(f'({text(conv, values.pop(0), extends, "String")} as String)')
        last = m.end()
    pieces += [f'"{fmt[last:]}"'] if last < len(fmt) or not pieces else []
    return ' + '.join(pieces)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

def target_type(conv, target) -> str:
    """The declared Papyrus type of an assignment target, '' when unknown."""
    if isinstance(target, N.Member):
        return conv.remote_type_of(f'{E.emit_bare(conv, target.owner)}.{target.name}')
    if isinstance(target, N.Ident):
        return conv.type_of(target.name)
    return ''


def assignment(conv, stmt: N.Assign, extends: str):
    """Papyrus text for an array write, else `stmt` with its xNVSE parts lowered for the target's type."""
    if not is_fallout4():
        return stmt
    if isinstance(stmt.target, N.Index):
        return _element_write(conv, stmt, extends)
    want = target_type(conv, stmt.target)
    if want == ARRAY_TYPE:
        return f'{text(conv, stmt.target, extends)} = {array_text(conv, stmt.value, extends)}'
    if stmt.op == '^':
        pow_ = N.BinOp('^', stmt.target, stmt.value, line=stmt.line)
        return dataclasses.replace(stmt, op='', value=_lower(conv, pow_, extends, want))
    if not uses_nvse(conv, stmt.value):
        return stmt
    return dataclasses.replace(stmt, value=_lower(conv, stmt.value, extends, want or 'Float'))


def _element_write(conv, stmt: N.Assign, extends: str) -> str:
    """`arr[k] := v` (and `arr[k] += v`) as CRUI_Array.Set."""
    arr = array_text(conv, stmt.target.target, extends)
    key = value_text(conv, stmt.target.index, extends)
    value = value_text(conv, stmt.value, extends)
    current = _cast(f'{ARRAY}.Get({arr}, {key})', 'Float')
    if stmt.op == '^':
        value = f'Math.Pow({current}, {text(conv, stmt.value, extends, "Float")})'
    elif stmt.op:
        value = f'{current} {stmt.op} {text(conv, stmt.value, extends, "Float")}'
    return f'{ARRAY}.Set({arr}, {key}, {value})'


def foreach_head(conv, st: N.ForEach, extends: str) -> 'tuple | None':
    """(lines before the loop, While condition, first body line, last body line) of an array ForEach.

    The source is captured once, as xNVSE iterates the array it started with; the iterator gets a
    StringMap with `key` and `value` each pass. None when this is not an array loop (a container or a
    string), which the caller keeps commented out.
    """
    if not is_fallout4() or conv.type_of(st.var) != ARRAY_TYPE:
        return None
    conv.sc.loop_locals += 1
    arr, idx = f'TES4_Each{conv.sc.loop_locals}', f'TES4_EachIndex{conv.sc.loop_locals}'
    var = text(conv, N.Ident(st.var, line=st.line), extends)
    return ([f'{ARRAY_TYPE} {arr} = {array_text(conv, st.source, extends)}', f'Int {idx} = 0'],
            f'{idx} < {ARRAY}.Size({arr})', f'{var} = {ARRAY}.Iterator({arr}, {idx})', f'{idx} += 1')
