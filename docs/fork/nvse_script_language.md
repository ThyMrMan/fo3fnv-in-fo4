# xNVSE script language on Fallout 4

**Code:** Cleanroom UI's `papyrus/CRUI_Array.psc` (shipped through `fo4_import/cleanroom.py`),
`script_convert/nvse_falloutnv.py` (expressions and assignments),
`script_convert/loop_jumps.py`, `script_convert/udf_fallout4.py`, and the
parser in `script_convert/tes4/`.

How the legacy xNVSE syntax lowers to Fallout 4 Papyrus. Scope and survey:
[nvse_port.md](research/nvse_port.md#usage-survey). The new C-like syntax,
lambdas, `Label`/`Goto` and event handlers are out of scope.

The lowering (arrays, `^`, bitwise operators, loop flags, Global
functions) is Fallout 4 only: on Skyrim `uses_nvse` is always false and the
old notes stay. The parser changes apply to every game, since they only
read syntax: `let`/`:=`/compound assignment, `eval`, declaration lists,
typed function parameters, hex and binary literals, `sv_Destruct`, and a
`Call` inside a function passing its own caller on. Checked by converting
every script of FalloutNV.esm (2,576), Fallout3.esm (1,257) and
Oblivion.esm (2,393) before and after: the output is byte-identical.

## <a id="assignment"></a>Assignment and `eval`

`let x := e`, `set x to e`, a bare `x = e`, and the compound forms
`+= -= *= /= ^=` all become one assignment; a compound one is spelled out
(`x = x + e`), and `^=` becomes `Math.Pow`. `int a, b` and `int i = 5`
declare every name and keep the value as an assignment where it was.
`if eval e` and `while eval e` drop the `eval`; Papyrus evaluates the whole
expression anyway. A script that declares its own variable `Eval`
(Oblivion's `Dark17FollowingScript`) keeps reading it as that variable.

Papyrus refuses most uses of a `Var` without a cast, so every array element
read is cast by where it sits: to the other side's type in a comparison,
Float in arithmetic (String beside a String `+`), Bool as a condition or
under `!`, Form as a command argument, and Actor or ObjectReference as a
receiver (Actor when the command needs one, the same rule that types a
plain `ref`). xNVSE's hex and binary literals (`0xB7E7`, `0b101`) become
decimal. `sv_Destruct a, b` sets each string to `""`.

## <a id="arrays"></a>Arrays

**Representation:** every `array_var` is a Papyrus `Var[]` whose element 0
holds the array's kind: 1 Array (a list), 2 Map (numeric keys), 3
StringMap. A list's values follow from element 1; a map stores key, value
pairs from element 1, in key order. `None` is xNVSE's null array
(`ar_Null`). Every operation is a global function on `CRUI_Array`.

Why this shape:

- **One type for all three kinds.** Arrays cross scripts
  (`JLM.aItems`, a UDF returning one) and a variable's kind is often unknown
  where it is used. A typed Papyrus array (`Form[]`) would need the kind and
  the element type at every use; `Var[]` with a kind tag needs neither.
- **References, like xNVSE.** Papyrus arrays are passed by reference, so
  `let a := b` aliases and a write through either is seen by both, as in
  xNVSE.
- **Truth matches.** A Papyrus array is true when its length is above 0.
  The kind element keeps a valid but empty array true, as an xNVSE array id
  is; `None` is false.
- **Nested arrays** go through F4SE's `Utility.VarArrayToVar` and
  `VarToVarArray`: a `Var` cannot hold an array directly.

| xNVSE | Papyrus |
|---|---|
| `ar_Construct "StringMap"` | `CRUI_Array.Construct("StringMap")` |
| `ar_List a, b, c` | `CRUI_Array.List(3, a, b, c)` (at most 20, as xNVSE) |
| `arr[k]` (read) | `CRUI_Array.Get(arr, k) as <type>` |
| `let arr[k] := v` | `CRUI_Array.Set(arr, k, v)`; a list grows only by writing one past its end |
| `ar_Size` / `ar_HasKey` / `ar_Find` | `Size` (-1 for null) / `HasKey` / `Find` |
| `ar_BadNumericIndex` | `-99999`, xNVSE's own value (`Commands_Array.cpp`) |
| `ar_Append` / `ar_Erase` / `ar_Copy` | `Append` / `Erase` / `Copy` |
| `*arr` / `&v` | `Unbox` / `Box` |
| `ForEach it <- arr` | an index loop; `it` is set to `Iterator(arr, i)`, a StringMap with `key` and `value` |

`Find` compares with `SameValue`: Papyrus refuses `==` between two `Var`s
("cannot compare var types"), so forms compare by identity, strings
ignoring case and the rest as numbers, using FO4's `is` operator.

**Limits:** FO4 creates arrays of at most 128 elements with `new`;
`CRUI_Array` only ever creates one element and grows with `Add`. Maps are
searched linearly; the surveyed mods hold a few dozen entries at most.

## <a id="loops"></a>Loops, `Break` and `Continue`

`While`/`Loop` is a Papyrus `While`. `ForEach it <- arr` on an array
becomes an index loop over a copy of the array reference
(`TES4_Each<n>`, `TES4_EachIndex<n>`); `it` is set to
`CRUI_Array.Iterator(arr, i)`, a StringMap with `key` and `value` as in
xNVSE. A `ForEach` over anything else (a container, a form list) is kept as
a comment: those iterate engine objects CRUI_Array does not model.

Papyrus has no `break` or `continue`, so a loop that uses them gets two
flags: `TES4_Skip<n>` (cleared at the top of each pass) and `TES4_Break<n>`
(added to the loop's condition). `Continue` sets the skip flag, `Break`
sets both, and every statement after one that may jump is wrapped in
`If !TES4_Skip<n>`. A loop without either is emitted unchanged.

## <a id="functions"></a>User-defined functions

A script whose only block is `Begin Function {a, b}` becomes a script with
one `Global` function, `TES4Call`. xNVSE gives every call fresh variables, so
the script's variables become the function's locals. A Global function reads
no properties, so every form the body names becomes an extra parameter after
the declared ones. Each caller declares the same forms as `Auto Const`
properties under the same names, which the importer fills by name, and
passes them on: `Call Fn x` becomes `TES4_Fn.TES4Call(Self, x, SomeForm)`.
A function calling another passes the callee's forms too, so
`udf_fallout4.finish_calls` closes the set over the call graph after every
script has converted and rewrites the calls and declarations once.

`SetFunctionValue v` sets the result variable; `Return` returns it.
Typed parameters (`Begin Function {ref rItem, int iCount}`) are declared
from the header. A `Call` whose target is an expression
(`Call (GetFormFromMod ...)`) is left as a note: the function is chosen at
run time. A script with more blocks than its Function block keeps the
older instance `TES4Call`, which callers on Fallout 4 cannot reach
statically; the surveyed mods have none.

## <a id="not-converted"></a>Not converted

Left as `;NE:` notes, as the brief scoped them out: lambdas
(`(Begin Function {...} ... End)` as an argument), `Label`/`Goto`,
`SetEventHandler` and the other event-handler commands, the new C-like
syntax, and JIP/MCM/UI commands. An array the converter cannot prove is an
xNVSE array (a cross-script one when the other script was not exported, or
an engine list such as `GetActorsByProcessingLevel`) reads as `None` with a
note.

## <a id="operators"></a>Operators

xNVSE's precedence (`ScriptUtils.cpp`, the operator table):
`||`, `&&`, equality, comparison, `|`, `&`, `<<`/`>>`, `+`/`-`,
`*`/`/`/`%`, `^`, then the unary `!`, `-`, `$` (to string), `#` (to
number), `*` (unbox) and `&` (box). `^` becomes `Math.Pow`; the bitwise
operators become F4SE's `Math.LogicalAnd`/`LogicalOr`/`LeftShift`/`RightShift`.
`::` (pairs) and `->` occur only in event-handler calls, which stay out of
scope; `->` stays Morrowind's member arrow.
