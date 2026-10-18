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
#: The adder's local holding the value its add made.
SUM = 'TES4_Sum'
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


def _owners(by_type: dict, xref=None) -> tuple:
    """({EditorID lower: script EditorID lower} of quests and scripted references, {script lower: {variable:
    Papyrus type}} from each script's declarations); `xref` (the cross-reference graph) adds every placed
    reference of the plugin and its masters."""
    scripts = {int(r['FormID'], 16): r.get('EditorID', '').lower() for r in by_type.get('SCPT', ())}
    variables = {r.get('EditorID', '').lower(): _types(r) for r in by_type.get('SCPT', ())}
    scripted = {int(r['FormID'], 16): scripts.get(int(r['SCRI'], 16)) for recs in by_type.values()
                for r in recs if r.get('SCRI')}
    owners = {r['EditorID'].lower(): scripted.get(int(r['FormID'], 16)) for r in by_type.get('QUST', ())
              if r.get('EditorID')}
    owners.update(_placed_owners(xref) if xref else {})
    return {k: v for k, v in owners.items() if v}, variables


def _placed_owners(xref) -> dict:
    """{EditorID lower: script EditorID lower} of each placed reference in `xref` whose base (or itself) has a script."""
    out = {}
    for ref, base in xref.record_base.items():
        edid = xref.formid_to_edid.get(ref)
        script = xref.script_formid_to_edid.get(xref.record_scri.get(ref) or xref.record_scri.get(base, ''))
        if edid and script:
            out[edid.lower()] = script.lower()
    return out


def _types(rec: dict) -> dict:
    """{variable lower: 'Int' or 'Float'} of one SCPT's variables, by its source's declarations."""
    names = {rec[f'Variable[{i}].Name'].lower() for i in range(int(rec.get('VariableCount', 0) or 0))}
    text = str(rec.get('SCTX', '')).replace('\\r\\n', '\n')
    declared = {name.lower(): 'Float' if kind.lower() == 'float' else 'Int' for kind, name in _DECLARED.findall(text)}
    return {name: declared.get(name, 'Int') for name in names}


def find_adds(by_type: dict, xref=None) -> tuple:
    """(CALLS, OWNED) of every cross-script increment whose owner (a quest, or a placed reference `xref` knows)
    has a script declaring the variable."""
    owners, variables = _owners(by_type, xref)
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
    """The adder functions script `conv` owns (OWNED), each keeping its mirror global (`mirrors`) in step. The new
    value is kept in a local (SUM): the trace reads the counter before any call out, and the mirror and the
    return take the local, so an add that runs while this one is out cannot change what this one reports."""
    out = []
    edid = (conv.sc.edid or '').lower()
    for var in OWNED.get(edid, ()):
        vtype = conv.sc.var_types.get(var, 'Int')
        out += [f'{vtype} Function {PREFIX}{var}(Float afBy)', f'  {vtype} {SUM} = ({var} + afBy) as {vtype}',
                f'  {var} = {SUM}', value_line(var)]
        mirror = mirrors.get((edid, var))
        if mirror:
            conv.sc.property_refs.setdefault(mirror, 'GlobalVariable')
            out.append(f'  {global_line(mirror, SUM)}')
        out += [f'  Return {SUM}', 'EndFunction', '']
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
            name, counter = f'{RESULT}{m[3]}_{m[4]}', rf'{re.escape(m[3])}\.{re.escape(m[4])}'
            kept[key] = (re.compile(rf'\b{counter}\b(?!\s*=[^=])', re.IGNORECASE),
                         re.compile(rf'^(\s*)({counter})\s*=(?!=)\s*(.+)$', re.IGNORECASE), name)
            if name not in {n for _, n in opened}:
                opened.append((f'  {name} = {m[3]}.{m[4]}', name))
            declared[name] = CALLS[key]
            out.append(f'{m[1]}{name} = {m[2]}')
        else:
            out += _kept_line(line, kept.values())
    return out[:1] + [init for init, _ in opened] + out[1:] if opened else out


def _kept_line(line: str, kept) -> list:
    """`line` reading each kept counter's own value; a direct write of one sets that value first, then the
    counter from it, so the write's mirror and later reads carry the assigned value."""
    for read, _write, name in kept:
        line = read.sub(name, line)
    for _read, write, name in kept:
        m = write.match(line)
        if m:
            return [f'{m[1]}{name} = {m[3]}', f'{m[1]}{m[2]} = {name}']
    return [line]
