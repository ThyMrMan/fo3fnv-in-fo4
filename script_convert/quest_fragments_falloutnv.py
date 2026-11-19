"""FO3/FNV quest stage items for Fallout 4: every item whose conditions pass runs.

FO3/FNV run each stage item whose conditions pass; a Fallout 4 quest keeps
one log entry per stage, whose fragment is the stage's first item. That
fragment calls the stage's later items, and a conditioned item runs its
result script only under its conditions, written back as FO3 script text
(`if GetStageDone CG02 20 == 1 && ...`) for the converter.

See: docs/fork/fo4_pipeline.md#stage-items
"""

import re
import struct
from functools import cache

from tools.dialog.tes4_ctda_dump import xedit_table

#: Comparison operators by a condition's type byte (>> 5).
OPS = ('==', '!=', '>', '>=', '<', '<=')
#: Condition type bits: OR with the next, compare with a global.
OR, USE_GLOBAL = 0x01, 0x04
#: Run On Reference (the condition's own reference).
RUN_REFERENCE = 2
#: Functions written as a variable: a quest's or reference's script variable (owner, index), a global's value.
VARIABLES, GLOBAL_VALUE = frozenset({'GetQuestVariable', 'GetScriptVariable'}), 'GetGlobalValue'
#: The player reference's FormID (no export record names it) and its FO3 script name.
PLAYER_REF, PLAYER = 0x14, 'player'
#: The guard of an item whose conditions cannot be written: it never runs.
NEVER = '0'
#: A line opening or closing an FO3 script block.
BLOCK = re.compile(r'(if|elseif|else|endif|begin|end)\b')


@cache
def _table():
    """FNV's condition functions (FO3's share their indices)."""
    return xedit_table('fnv')


def _form(fid: int, xref) -> 'str | None':
    """The EditorID of form `fid` (the player reference: `player`), or None."""
    return PLAYER if fid == PLAYER_REF else xref.formid_to_edid.get(f'{fid:08X}')


def _variable(owner: int, index: int, xref) -> 'str | None':
    """`Owner.variable` of variable `index` in quest or reference `owner`'s script (a reference's: its base's)."""
    key = f'{owner:08X}'
    script = xref.record_scri.get(key) or xref.record_scri.get(xref.record_base.get(key, ''), '')
    name, var = _form(owner, xref), xref.script_vars.get(script, {}).get(index)
    return f'{name}.{var}' if name and var else None


def _call(func: int, p1: int, p2: int, xref) -> 'str | None':
    """FO3 script text of condition function `func` on params `p1`, `p2`; None when it cannot be written."""
    table = _table()
    name = table.name(func)
    if name in VARIABLES:
        return _variable(p1, p2, xref)
    if name == GLOBAL_VALUE:
        return _form(p1, xref)
    if name.startswith('Func') or table.av_slots.get(func):
        return None
    forms = table.form_slots.get(func, set())
    args = [_form(p, xref) if slot in forms else str(p) for slot, p in ((1, p1), (2, p2))
            if slot in table.slots.get(func, ())]
    return None if None in args else ' '.join([name, *args])


def _condition(raw_hex: str, xref) -> 'str | None':
    """FO3 script text of one stage-item condition; None when it cannot be written."""
    data = bytes.fromhex(raw_hex) + bytes(28)
    kind, func, p1, p2, run_on, ref = data[0], *struct.unpack_from('<H2xIIII', data, 8)
    call = _call(func, p1, p2, xref)
    owner = _form(ref, xref) if run_on == RUN_REFERENCE else ''
    compared = _form(struct.unpack_from('<I', data, 4)[0], xref) if kind & USE_GLOBAL \
        else f'{struct.unpack_from("<f", data, 4)[0]:g}'
    if call is None or owner is None or compared is None or run_on not in (0, RUN_REFERENCE):
        return None
    return f'{owner + "." if owner else ""}{call} {OPS[kind >> 5]} {compared}'


def item_guard(rec: dict, prefix: str, xref) -> str:
    """FO3 script text of stage item `prefix`'s conditions ('' with none: it always runs), OR groups in
    parentheses; NEVER when one cannot be written."""
    groups, group = [], []
    for k in range(int(rec.get(prefix + 'ConditionCount', 0) or 0)):
        raw = rec[f'{prefix}Condition[{k}].Raw']
        text = _condition(raw, xref)
        if text is None:
            return NEVER
        group.append(text)
        if not int(raw[:2], 16) & OR:
            groups.append(group)
            group = []
    groups += [group] if group else []
    return ' && '.join(g[0] if len(g) == 1 else f'({" || ".join(g)})' for g in groups)


def guarded(script: str, guard: str) -> str:
    """FO3 result `script` run only when `guard` holds ('' : always)."""
    return f'if {guard}\n{script}\nendif' if guard and script.strip() else script


def aged_first(script: str) -> str:
    """FO3 `script` with each AgeRace line moved ahead of the EquipItem lines before it in its block: FO3 equips
    whatever the race, FO4 only what the actor's race can wear (CG02's adult suit, equipped on the child).
    See: docs/fork/fo4_fo3_child_player.md#age-then-equip
    """
    out, equips = [], []
    for line in script.splitlines():
        code = line.split(';', 1)[0].strip().lower()
        if BLOCK.match(code):
            equips = []
        elif 'agerace' in code and equips:
            out.insert(equips[0], line)
            equips = [k + 1 for k in equips]
            continue
        elif 'equipitem' in code and 'unequipitem' not in code:
            equips.append(len(out))
        out.append(line)
    return '\n'.join(out)


def stage_calls(fragments: list) -> dict:
    """{(stage, first item): [later items]} of `fragments` [(stage, item, ...)] in order."""
    calls = {}
    for frag in fragments:
        first = next(f[1] for f in fragments if f[0] == frag[0])
        if frag[1] != first:
            calls.setdefault((frag[0], first), []).append(frag[1])
    return calls
