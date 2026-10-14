"""FO3/FNV cross-script increments made atomic on Fallout 4.

`set Q.v to Q.v + 1` in one script, on a variable another script owns, read
the variable and wrote it back in one step: FO3/FNV ran scripts one at a
time. Papyrus runs each event on its own thread, and a property read and its
write are two calls into the owner, so two geckos dying together both read
1 and both wrote 2 (VFreeformGoodsprings counted 2 of 3 well geckos and the
quest stalled). Every such increment instead calls a function on the owner,
`TES4Add_<v>(by)`, which Papyrus runs one at a time per object; it keeps the
variable's mirror global (quest_var_mirrors) in step.

See: docs/fork/fo4_pipeline.md#atomic-adds
"""

import re

from script_convert.trace_points import global_line, value_line

PREFIX, RESULT = 'TES4Add_', 'TES4Added_'
#: This worker's increments: {(owner EditorID lower, variable lower): Papyrus type} the callers rewrite.
CALLS = {}
#: This worker's owners: {script EditorID lower: {variable lower}} each script defines an adder for.
OWNED = {}
_INCREMENT = re.compile(r'\bset\s+(\w+)\.(\w+)\s+to\s+\(?\s*\1\.\2\s*[-+]', re.IGNORECASE)
_DECLARED = re.compile(r'^\s*(short|int|long|float)\s+(\w+)', re.IGNORECASE | re.MULTILINE)
_ADD_CALL = re.compile(rf'^(\s*)((\w+)\.{PREFIX}(\w+)\(.*)$')
_OPENER = re.compile(r'^(\w+\s+)?(Event|Function)\s', re.IGNORECASE)


def _sources(by_type: dict):
    """Every script text of the export: SCPT source, INFO/QUST result scripts, PACK sections."""
    for sig in ('SCPT', 'INFO', 'QUST', 'PACK'):
        for rec in by_type.get(sig, ()):
            for key, value in rec.items():
                if key == 'SCTX' or key.endswith(('Script', 'ScriptEnd')):
                    yield str(value).replace('\\r\\n', '\n').replace('\\t', '\t')


def _owners(by_type: dict) -> tuple:
    """({EditorID lower: script EditorID lower} of quests and scripted references, {script lower: {variable:
    Papyrus type}} from each script's declarations)."""
    scripts = {int(r['FormID'], 16): r.get('EditorID', '').lower() for r in by_type.get('SCPT', ())}
    variables = {r.get('EditorID', '').lower(): _types(r) for r in by_type.get('SCPT', ())}
    scripted = {int(r['FormID'], 16): scripts.get(int(r['SCRI'], 16)) for recs in by_type.values()
                for r in recs if r.get('SCRI')}
    owners = {r['EditorID'].lower(): scripted.get(int(r['FormID'], 16)) for r in by_type.get('QUST', ())
              if r.get('EditorID')}
    owners.update({r['EditorID'].lower(): scripted.get(int(r['NAME'], 16)) for sig in ('REFR', 'ACHR', 'ACRE')
                   for r in by_type.get(sig, ()) if r.get('EditorID') and r.get('NAME')})
    return {k: v for k, v in owners.items() if v}, variables


def _types(rec: dict) -> dict:
    """{variable lower: 'Int' or 'Float'} of one SCPT's variables, by its source's declarations."""
    names = {rec[f'Variable[{i}].Name'].lower() for i in range(int(rec.get('VariableCount', 0) or 0))}
    text = str(rec.get('SCTX', '')).replace('\\r\\n', '\n')
    declared = {name.lower(): 'Float' if kind.lower() == 'float' else 'Int' for kind, name in _DECLARED.findall(text)}
    return {name: declared.get(name, 'Int') for name in names}


def find_adds(by_type: dict) -> tuple:
    """(CALLS, OWNED) of every cross-script increment whose owner's script declares the variable."""
    owners, variables = _owners(by_type)
    calls, owned = {}, {}
    for text in _sources(by_type):
        for owner, var in _INCREMENT.findall(text):
            script = owners.get(owner.lower())
            if script and var.lower() in variables.get(script, ()):
                calls[owner.lower(), var.lower()] = variables[script][var.lower()]
                owned.setdefault(script, set()).add(var.lower())
    return calls, {k: sorted(v) for k, v in owned.items()}


def rewritten(line: str, target: str) -> 'str | None':
    """Converted write `line` of `target` as the owner's adder call when it increments a CALLS variable."""
    owner, _, var = target.rpartition('.')
    if (owner.lower(), var.lower()) not in CALLS:
        return None
    m = re.match(rf'(\s*){re.escape(target)} = {re.escape(target)} ([-+]) (.+?)(\s*;.*)?$', line)
    if not m:
        return None
    sign = '-' if m[2] == '-' else ''
    return f'{m[1]}{owner}.{PREFIX}{var}({sign}({m[3]})){m[4] or ""}'


def adders(conv, mirrors: dict) -> list:
    """The adder functions script `conv` owns (OWNED), each keeping its mirror global (`mirrors`) in step."""
    out = []
    edid = (conv.sc.edid or '').lower()
    for var in OWNED.get(edid, ()):
        vtype = conv.sc.var_types.get(var, 'Int')
        out += [f'{vtype} Function {PREFIX}{var}(Float afBy)', f'  {var} = ({var} + afBy) as {vtype}']
        mirror = mirrors.get((edid, var))
        if mirror:
            conv.sc.property_refs.setdefault(mirror, 'GlobalVariable')
            out.append(f'  {global_line(mirror, var)}')
        out += [value_line(var), f'  Return {var}', 'EndFunction', '']
    return out


def own_reads(lines: list) -> list:
    """A converted script's lines where an add's later reads of its counter, in the same function, read the
    value that add made (FNV ran the whole script before another could add): the call keeps its result in a
    script variable (declared at the end, set from the counter as the function opens)."""
    blocks, declared = [[]], {}
    for line in '\n'.join(lines).split('\n'):
        if _OPENER.match(line):
            blocks.append([])
        blocks[-1].append(line)
    out = []
    for block in blocks:
        out += _own_block(block, declared)
    return out + [f'{vtype} {name}' for name, vtype in declared.items()]


def _own_block(block: list, declared: dict) -> list:
    """One function's lines with own_reads applied; adds `declared` {variable: type} for those it keeps."""
    out, kept, opened = [], {}, []
    for line in block:
        m = _ADD_CALL.match(line)
        key = m and (m[3].lower(), m[4].lower())
        if key in CALLS:
            name = f'{RESULT}{m[3]}_{m[4]}'
            kept[key] = (re.compile(rf'\b{re.escape(m[3])}\.{re.escape(m[4])}\b(?!\s*=[^=])', re.IGNORECASE), name)
            if name not in {n for _, n in opened}:
                opened.append((f'  {name} = {m[3]}.{m[4]}', name))
            declared[name] = CALLS[key]
            line = f'{m[1]}{name} = {m[2]}'
        else:
            for pattern, name in kept.values():
                line = pattern.sub(name, line)
        out.append(line)
    return out[:1] + [init for init, _ in opened] + out[1:] if opened else out
