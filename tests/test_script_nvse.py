"""xNVSE's script language converted for Fallout 4: assignment, eval, operators, loops, arrays and functions.

See: docs/fork/nvse_script_language.md#arrays
"""

import pytest

from script_convert import udf_fallout4
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from script_convert.tes4.parser import parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def fallout4(monkeypatch):
    """Emit Fallout 4 Papyrus for the test."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)


def _lines(src: str) -> list:
    """The converted ObjectReference script's lines, stripped."""
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')
    return [line.strip() for line in out.splitlines()]


def _body(statements: str, decls: str = '') -> list:
    """The lines `statements` convert to inside an OnActivate block, after `decls`."""
    return _lines(f'scn T\n{decls}begin OnActivate\n{statements}end\n')


def _declares(lines: list, ptype: str, name: str) -> bool:
    """Does the script declare property `name` of `ptype`?"""
    return any(line.startswith(f'{ptype} Property {name} ') for line in lines)


# ---------------------------------------------------------------------------
# Assignment, eval and operators
# ---------------------------------------------------------------------------

def test_let_and_compound_assignment(fallout4):
    """`let`, a bare `=` and each compound operator are one assignment."""
    got = _body('  let i := 2\n  let i += 3\n  i -= 1\n  let f := i ^ 2\n  let f *= 2\n', 'int i\nfloat f\n')
    assert ['i = 2', 'i = i + 3', 'i = i - 1', 'f = Math.Pow(i, 2)', 'f = f * 2'] == \
        [line for line in got if line[:4] in ('i = ', 'f = ')]


def test_eval_conditions_and_bitwise_operators(fallout4):
    """`if eval` drops the eval; bitwise operators call F4SE's Math."""
    got = _body('  if eval (i << 1) | 1 && i\n    set i to 0\n  endif\n', 'int i\n')
    assert 'If Math.LogicalOr(Math.LeftShift(i, 1), 1) && i' in got


def test_a_variable_named_eval_is_not_the_keyword():
    """Oblivion's Dark17FollowingScript tests `If Eval == 0` on its own variable."""
    got = _body('  if Eval == 0\n    set Eval to 1\n  endif\n', 'short Eval\n')
    assert 'If Eval == 0' in got


def test_hex_and_binary_literals_are_decimal(fallout4):
    """`0xF` and `0b101` read as 15 and 5."""
    assert 'i = 5 + 15' in _body('  set i to 0b101 + 0xF\n', 'int i\n')


def test_declaration_lists_and_initial_values(fallout4):
    """`int a, b` declares both; `int c = a + 4` stays an assignment."""
    got = _body('  set a to 1\n  int c = a + 4\n', 'int a, b\n')
    assert all(_declares(got, 'Int', name) for name in 'abc')
    assert 'c = a + 4' in got


def test_to_string_and_sv_destruct(fallout4):
    """`$i` casts to String; `sv_Destruct s, t` empties both strings."""
    got = _body('  let s := "n=" + $i\n  sv_Destruct s, t\n', 'int i\nstring_var s\nstring_var t\n')
    assert 's = "n=" + (i as String)' in got
    assert got[got.index('s = ""') + 1] == 't = ""'


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------

def test_while_with_break_and_continue_uses_flags(fallout4):
    """Continue sets the pass's skip flag; Break sets both and ends the loop through its condition."""
    got = _body('  while i < 10\n    let i += 1\n    if i == 3\n      continue\n    endif\n'
                '    if i == 7\n      break\n    endif\n    set j to i\n  loop\n', 'int i\nint j\n')
    start = got.index('While i < 10 && !TES4_Break1')
    assert got[start - 2:start] == ['Bool TES4_Skip1 = False', 'Bool TES4_Break1 = False']
    assert got[start + 1] == 'TES4_Skip1 = False'
    assert got.count('If !TES4_Skip1') == 2 and 'TES4_Break1 = True' in got


def test_a_loop_without_jumps_has_no_flags(fallout4):
    """No flags when nothing jumps."""
    got = _body('  while i < 3\n    let i += 1\n  loop\n', 'int i\n')
    assert 'While i < 3' in got and not any('TES4_Skip' in line for line in got)


def test_foreach_over_an_array_is_an_index_loop(fallout4):
    """`ForEach it <- a` walks the array by index, setting `it` to a key/value StringMap."""
    got = _body('  foreach it <- a\n    let n += it["value"]\n  loop\n', 'array_var a\narray_var it\nint n\n')
    start = got.index('Var[] TES4_Each1 = a')
    assert got[start + 1:start + 6] == [
        'Int TES4_EachIndex1 = 0', 'While TES4_EachIndex1 < F3NV_Array.Size(TES4_Each1)',
        'it = F3NV_Array.Iterator(TES4_Each1, TES4_EachIndex1)',
        'n = n + (F3NV_Array.Get(it, "value") as Int)', 'TES4_EachIndex1 += 1']


# ---------------------------------------------------------------------------
# Arrays and strings
# ---------------------------------------------------------------------------

def test_array_commands_call_f3nv_array(fallout4):
    """ar_List, ar_Construct, writes, ar_Size, ar_HasKey, ar_Find, ar_BadNumericIndex and ar_Null."""
    got = _body('  let a := ar_List 1, 2, 3\n  let m := ar_Construct "StringMap"\n  let m["x"] := 5\n'
                '  let n := ar_Size a\n  if ar_HasKey m "x"\n    let n := m["x"]\n  endif\n'
                '  if ar_Find 2 a == ar_BadNumericIndex\n    let a := ar_Null\n  endif\n',
                'array_var a\narray_var m\nint n\n')
    assert _declares(got, 'Var[]', 'a')
    for want in ('a = F3NV_Array.List(3, 1, 2, 3)', 'm = F3NV_Array.Construct("StringMap")',
                 'F3NV_Array.Set(m, "x", 5)', 'n = F3NV_Array.Size(a)', 'If F3NV_Array.HasKey(m, "x")',
                 'n = (F3NV_Array.Get(m, "x") as Int)', 'If (F3NV_Array.Find(2, a) as Float) == -99999',
                 'a = None'):
        assert want in got


def test_an_element_read_as_a_receiver_is_cast_for_its_command(fallout4):
    """An Actor-only command casts its element to Actor, any other to ObjectReference."""
    got = _body('  if a[0].IsDead\n    a[1].Disable\n  endif\n', 'array_var a\n')
    assert 'If (F3NV_Array.Get(a, 0) as Actor).IsDead()' in got
    assert '(F3NV_Array.Get(a, 1) as ObjectReference).Disable()' in got


def test_skyrim_does_not_lower_arrays(monkeypatch):
    """Off Fallout 4 nothing lowers."""
    monkeypatch.delenv(TARGET_ENV, raising=False)
    got = _body('  let n := ar_Size a\n', 'array_var a\nint n\n')
    assert not any('F3NV_Array' in line for line in got)


# ---------------------------------------------------------------------------
# User-defined functions
# ---------------------------------------------------------------------------

UDF = 'scn TFn\nint x\nbegin Function {ref rItem, int iCount}\n  let x := iCount * 2\n  SetFunctionValue x\nend\n'


def test_a_function_script_is_one_global_function(fallout4):
    """Typed parameters come from the header, variables are locals, and the result is returned."""
    got = _lines(UDF)
    head = got.index('Int Function TES4Call(ObjectReference akCallingRef, Form rItem, Int iCount) Global')
    assert got[head + 1:head + 3] == ['Int x = 0', 'Int TES4_Result = 0']
    assert 'Return TES4_Result' in got and not any(' Property ' in line for line in got)


def test_a_call_names_the_function_script(fallout4):
    """`Call TFn r 3` calls the Global function on its script, declaring no property."""
    got = _body('  let n := Call TFn r 3\n', 'int n\nref r\n')
    assert 'n = TES4_TFn.TES4Call(Self, r, 3)' in got
    assert not _declares(got, 'TES4_TFn', 'TFn')


def test_a_call_to_a_run_time_function_is_a_note(fallout4):
    """`Call (expression)` cannot name a script."""
    got = _body('  Call (GetFormFromMod "x.esp" 0x10)\n')
    assert any('a function chosen at run time' in line for line in got)


def test_typed_parameters_are_declared_from_the_header():
    """`{ref a, int b}` declares both; the filter keeps the names."""
    tree = parse('scn T\nbegin Function {ref a, int b}\nend\n')
    assert [(v.vtype, v.name) for v in tree.variables] == [('ref', 'a'), ('int', 'b')]
    assert tree.blocks[0].filter == '{a, b}'


def test_forms_pass_through_every_caller(tmp_path):
    """A function's forms close over the call graph; each call passes them and each caller declares them."""
    head = 'ScriptName TES4_{0}\n{{Converted from TES4: {0}}}\n'
    (tmp_path / 'TES4_A.psc').write_text(head.format('A') + 'Function TES4Call(ObjectReference akCallingRef, Quest Q) '
                                         'Global\n  TES4_B.TES4Call(akCallingRef)\nEndFunction\n', encoding='utf-8')
    (tmp_path / 'TES4_B.psc').write_text(head.format('B') + 'Function TES4Call(ObjectReference akCallingRef, Sound S) '
                                         'Global\nEndFunction\n', encoding='utf-8')
    (tmp_path / 'TES4_C.psc').write_text(head.format('C') + 'Event OnInit()\n  TES4_A.TES4Call(Self)\nEndEvent\n',
                                         encoding='utf-8')
    forms = {'tes4_a': [('Q', 'Quest')], 'tes4_b': [('S', 'Sound')]}
    callers = {'TES4_A': ([('TES4_B', ('akCallingRef',))], {}), 'TES4_C': ([('TES4_A', ('Self',))], {})}
    assert udf_fallout4.finish_calls(str(tmp_path), forms, callers) == 2
    a = (tmp_path / 'TES4_A.psc').read_text(encoding='utf-8')
    c = (tmp_path / 'TES4_C.psc').read_text(encoding='utf-8')
    assert 'TES4Call(ObjectReference akCallingRef, Quest Q, Sound S) Global' in a
    assert 'TES4_B.TES4Call(akCallingRef, S)' in a
    assert 'TES4_A.TES4Call(Self, Q, S)' in c
    assert _declares(c.splitlines(), 'Quest', 'Q') and _declares(c.splitlines(), 'Sound', 'S')
