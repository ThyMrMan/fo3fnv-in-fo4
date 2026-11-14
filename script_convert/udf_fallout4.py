"""xNVSE user-defined functions on Fallout 4: `TES4Call` is a Global function on the function's own script.

A Global function reads no properties, so the forms its body names (its property table) become trailing
parameters, and each caller passes its own same-named properties, which the importer fills by name like
any other. The script's variables are the function's locals: xNVSE gives every call fresh ones. A function
calling another passes the callee's forms on, so `finish_calls` closes the set over the call graph once
every script has converted, then appends the forms to every call and declares them on each caller.
See: docs/fork/nvse_script_language.md#functions
"""

from __future__ import annotations

import os
import re

from script_convert.target import is_fallout4

#: A local's starting value by Papyrus type; any object type starts as None.
_INITIAL = {'Float': '0.0', 'Int': '0', 'Bool': 'False', 'String': '""'}
#: The `{Converted from ...}` line every converted script carries under its ScriptName.
_DOC_LINE = re.compile(r'^\{Converted from[^\n]*\}$', re.M)


# ---------------------------------------------------------------------------
# The function
# ---------------------------------------------------------------------------

def is_global(tree) -> bool:
    """Fallout 4, and the Function block is the script's only block."""
    return is_fallout4() and bool(tree) and [b.btype.lower() for b in tree.blocks] == ['function']


def function(conv, variables: list, lines: list) -> list:
    """`lines`, a TES4Call, made Global: `variables` [(name, type)] its locals, the body's forms its last parameters."""
    names = {name.lower() for name, _t in variables} | conv.sc.udf_params
    unique = {p.lower(): (p, t) for p, t in sorted(conv.sc.property_refs.items(), reverse=True)}
    forms = sorted(form for low, form in unique.items() if form[0].isidentifier() and low not in names)
    conv.sc.udf_forms = forms
    head = lines[0][:-1] + ''.join(f', {t} {p}' for p, t in forms) + ') Global'
    return [head] + [f'  {t} {n} = {_INITIAL.get(t, "None")}' for n, t in variables] + lines[1:]


# ---------------------------------------------------------------------------
# After every script converted
# ---------------------------------------------------------------------------

def called_scripts(calls: list) -> dict:
    """{script (lower): script} each Fallout 4 `calls` entry names."""
    return {prop.lower(): prop for prop, _args in calls} if is_fallout4() else {}


def needed_forms(forms: dict, callers: dict) -> dict:
    """{function script (lower): [(form, type)]} its own forms, in its header's order, then sorted those it calls need."""
    need = {name: {p.lower(): (p, t) for p, t in own} for name, own in forms.items()}
    changed = True
    while changed:
        changed = False
        for script, (calls, _types) in callers.items():
            mine = need.get(script.lower())
            for callee, _args in calls if mine is not None else ():
                extra = {k: v for k, v in need.get(callee.lower(), {}).items() if k not in mine}
                mine.update(extra)
                changed |= bool(extra)
    return {name: list(forms[name]) + sorted(got[k] for k in got.keys() - {p.lower() for p, _t in forms[name]})
            for name, got in need.items()}


def _append_args(text: str, callee: str, names: list) -> str:
    """`text` with `, <names>` added to every `<callee>.TES4Call(...)`, matched by its own parenthesis."""
    out, start, opener = [], 0, f'{callee}.TES4Call('
    lower, find = text.lower(), opener.lower()
    while (at := lower.find(find, start)) >= 0:
        i, depth = at + len(opener), 1
        while i < len(text) and depth:
            depth += {'(': 1, ')': -1}.get(text[i], 0)
            i += 1
        out += [text[start:i - 1], ', ' + ', '.join(names), ')']
        start = i
    return ''.join(out) + text[start:]


def _called_live(text: str, callee: str) -> bool:
    """Whether `text` calls `callee` outside a comment line.
    See: docs/fork/nvse_script_language.md#functions
    """
    return bool(re.search(rf'^[ \t]*(?!;).*?\b{re.escape(callee)}\.TES4Call\(', text, re.I | re.M))


def _declare(text: str, forms: list, is_function: bool) -> str:
    """`text` declaring `forms` it does not: a function's TES4Call gains parameters, any other script properties."""
    missing = [(p, t) for p, t in forms if not re.search(rf'\b\w+(?:\[\])?\s+(?:Property\s+)?{p}\b', text, re.I)]
    if not missing:
        return text
    if is_function:
        return re.sub(r'(Function TES4Call\(.*)\) Global', lambda m: m.group(1) + ''.join(
            f', {t} {p}' for p, t in missing) + ') Global', text, count=1)
    block = '\n'.join(f'{t} Property {p} Auto Const' for p, t in missing)
    return _DOC_LINE.sub(lambda m: f'{m.group(0)}\n\n{block}', text, count=1)


def finish_calls(output_dir: str, forms: dict, callers: dict) -> int:
    """Pass each function's forms at every call and declare them on its callers; how many files changed.

    `forms` is {function script (lower): [(form, type)]}; `callers` the pipeline's {script: (calls, types)},
    each call `(callee script, args)`.
    """
    need = needed_forms(forms, callers)
    changed = 0
    for script in sorted(set(callers) | set(need)):
        path = os.path.join(output_dir, script + '.psc')
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        calls = callers.get(script, ((), {}))[0]
        new = _declare(text, need.get(script.lower(), []), script.lower() in need)
        for callee in sorted({c for c, _a in calls if need.get(c.lower()) and _called_live(text, c)}):
            new = _declare(_append_args(new, callee, [p for p, _t in need[callee.lower()]]),
                           need[callee.lower()], script.lower() in need)
        if new != text:
            with open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(new)
            changed += 1
    return changed
