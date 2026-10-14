"""FO3/FNV quest variables that packages and lines test, mirrored in globals on Fallout 4.

Fallout 4 reads a quest variable in a condition from the quest's running
script (GetVMQuestVariable), and package conditions are evaluated as actors
load. An actor whose packages read two quests that had not started froze the
load, and a line cannot name a quest the build leaves out. So every quest
variable a package or line condition tests gets a global
(`TES4QVar_<quest>_<variable>`): each converted write of the variable also
sets the global, and the converted condition reads the global. An unset
global reads 0, as FNV reads a variable of a quest that has not run.

See: docs/fork/fo4_pipeline.md#packages
"""

import struct

from script_convert.atomic_adds import rewritten
from script_convert.trace_points import global_line
from script_convert.emit.expr import emit_source
from tes5_import.base.conditions import GET_QUEST_VARIABLE

PREFIX = 'TES4QVar_'
#: (quest or quest script EditorID lower, variable lower) -> mirror global: this worker's quest_var_mirrors().
GLOBALS = {}


def quest_var_global_name(quest_edid: str, variable: str) -> str:
    """The mirror global's EditorID for one quest variable."""
    return f'{PREFIX}{quest_edid}_{variable}'


def mirrored(conv, stmt, target: str, line: str) -> str:
    """`line`, converter `conv`'s write of `target` (from `stmt`), and the SetValue keeping its global in step
    when the variable is mirrored: `Quest.var` from any script, `var` in the quest's own script; a cross-script
    increment is the owner's atomic adder call instead (atomic_adds)."""
    add = rewritten(line, target)
    if add:
        return add
    if not GLOBALS or line.lstrip().startswith(';'):
        return line
    parts = emit_source(stmt.target).lower().split('.')
    key = tuple(parts) if len(parts) == 2 else ((conv.sc.edid or '').lower(), parts[0])
    name = GLOBALS.get(key)
    if not name:
        return line
    conv.sc.property_refs.setdefault(name, 'GlobalVariable')
    return f'{line}\n  {global_line(name, target)}'


def tested_quest_vars(recs) -> set:
    """{(quest FormID low 24, variable index)} the FNV records' (packages, lines) GetQuestVariable conditions test."""
    out = set()
    for rec in recs:
        i = 0
        while f'Condition[{i}].Raw' in rec:
            data = bytes.fromhex(rec[f'Condition[{i}].Raw'])
            i += 1
            if len(data) >= 20 and struct.unpack_from('<H', data, 8)[0] == GET_QUEST_VARIABLE:
                out.add((struct.unpack_from('<I', data, 12)[0] & 0xFFFFFF, struct.unpack_from('<I', data, 16)[0]))
    return out


def quest_var_mirrors(by_type: dict, script_vars: dict) -> dict:
    """{(quest EditorID or its script's, lower; variable lower): global name} of every variable a package or a
    line tests.

    `script_vars` is {quest FormID low 24: {variable index: name}} (pipeline.build_quest_script_vars).
    """
    scripts = {int(r['FormID'], 16) & 0xFFFFFF: r.get('EditorID', '') for r in by_type.get('SCPT', ())}
    quests = {int(q['FormID'], 16) & 0xFFFFFF: q for q in by_type.get('QUST', ()) if q.get('EditorID')}
    out = {}
    for quest, index in sorted(tested_quest_vars([*by_type.get('PACK', ()), *by_type.get('INFO', ())])):
        rec, variable = quests.get(quest), script_vars.get(quest, {}).get(index)
        if rec is None or variable is None:
            continue
        name = quest_var_global_name(rec['EditorID'], variable)
        out[(rec['EditorID'].lower(), variable.lower())] = name
        script = scripts.get(int(rec.get('SCRI', '0'), 16) & 0xFFFFFF)
        if script:
            out[(script.lower(), variable.lower())] = name
    return out
