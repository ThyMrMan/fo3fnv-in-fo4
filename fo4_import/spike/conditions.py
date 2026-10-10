"""FNV conditions (28-byte CTDA) to FO4 conditions (32 bytes) for the dialogue spike.

Functions map by name through xEdit's two condition tables (GetActorValue is
FO4's GetValue). FormID and actor-value params go through the caller's maps.
A condition on something the spike does not convert is settled up front by
the caller's `assume` table: a fixed truth value replaces it before the
AND-of-OR-groups is simplified. Anything left unconvertible is reported, never
silently dropped.

See: docs/fork/fo4_spikes.md#spike-1
"""

import re
import struct
from pathlib import Path

from fo4_import.spike.records import RUN_REFERENCE, RUN_SUBJECT, RUN_TARGET, pack_ctda
from tools.dialog.tes4_ctda_dump import xedit_table

FNV = xedit_table('fnv')
FO4 = xedit_table('fo4')
_FNV_DEFS = Path(__file__).resolve().parents[2] / 'references' / 'xEdit' / 'Core' / 'wbDefinitionsFNV.pas'
_AV_ENUM = re.search(r"wbActorValueEnum\s*:=\s*wbEnum\(\[(.*?)\]", _FNV_DEFS.read_text(errors='replace'), re.S)
#: FNV actor value names by index; position, not xEdit's printed number (its Variable08 reads {79}).
FNV_AV_NAMES = re.findall(r"\}\s*'([^']*)'", _AV_ENUM.group(1))
#: xEdit's FNV actor value labels that are not the game's own name with the spaces dropped (GECK, scripts).
FNV_AV_GAME_NAMES = {'Critical Chance': 'CritChance', 'Damage Resistance': 'DamageResist',
                     'Poison Resistance': 'PoisonResist', 'Rad Resistance': 'RadResist',
                     'Speed Multiplier': 'SpeedMult', 'Rad Level': 'RadiationRads', 'Fire Resistance': 'FireResist',
                     'Electric Resistance': 'ElectricResist', 'Frost Resistance': 'FrostResist',
                     'Energy Resistance': 'EnergyResist', 'EMP Resistance': 'EmpResist'}
#: FNV name -> FO4 name where FO4 renamed the function.
RENAMED = {'GetActorValue': 'GetValue', 'GetPCIsSex': 'GetIsSex'}
#: FNV functions that test the player; FO4's counterpart runs on the player reference.
ON_PLAYER = {'GetPCIsSex'}
PLAYER_REF = 0x14
_OPS = {0x00: lambda a, b: a == b, 0x20: lambda a, b: a != b, 0x40: lambda a, b: a > b,
        0x60: lambda a, b: a >= b, 0x80: lambda a, b: a < b, 0xA0: lambda a, b: a <= b}


def fnv_av_name(index: int) -> str:
    """The game's name of FNV actor value `index` ('' past the list)."""
    label = FNV_AV_NAMES[index] if index < len(FNV_AV_NAMES) else ''
    return FNV_AV_GAME_NAMES.get(label, label.replace(' ', ''))


def parse(raw_hex: str) -> dict:
    """One FNV condition's fields: op_flags, value, func name, p1, p2, run_on, ref."""
    raw = bytes.fromhex(raw_hex) + b'\0' * 28
    op_flags, value, func, p1, p2, run_on, ref = struct.unpack_from('<B3xfIIIII', raw)
    return {'op_flags': op_flags, 'value': value, 'func': FNV.name(func),
            'p1': p1, 'p2': p2, 'run_on': run_on, 'ref': ref}


def _is_or(cond: dict) -> bool:
    """True when this condition ORs with the next."""
    return bool(cond['op_flags'] & 0x01)


def compare(cond: dict, result: float) -> bool:
    """The condition's outcome when its function returns result."""
    return _OPS[cond['op_flags'] & 0xE0](result, cond['value'])


def groups(conds: list) -> list:
    """Split a condition list into OR-groups (the engine ANDs the groups)."""
    out, cur = [], []
    for cond in conds:
        cur.append(cond)
        if not _is_or(cond):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def simplify(conds: list, settle):
    """The OR-groups left after settle(cond) fixes what it can (True/False/None), or None if they never pass."""
    kept = []
    for group in groups(conds):
        live, satisfied = [], False
        for cond in group:
            outcome = settle(cond)
            satisfied |= outcome is True
            if outcome is None:
                live.append(cond)
        if satisfied:
            continue
        if not live:
            return None
        kept.append(live)
    return kept


def _fo4_params(cond: dict, form_map: dict, av) -> tuple:
    """(p1, p2) for FO4: actor values via av(), FormIDs via form_map."""
    if cond['func'] == 'GetActorValue':
        return av(cond['p1']), 0
    return form_map.get(cond['p1'], cond['p1']), form_map.get(cond['p2'], cond['p2'])


def run_on_of(cond: dict, swap: bool, form_map: dict) -> tuple:
    """(Run On, reference): player tests run on the player; swap flips Subject and Target."""
    if cond['func'] in ON_PLAYER:
        return RUN_REFERENCE, PLAYER_REF
    run_on = cond['run_on']
    if swap and run_on in (RUN_SUBJECT, RUN_TARGET):
        run_on = RUN_TARGET if run_on == RUN_SUBJECT else RUN_SUBJECT
    return run_on, form_map.get(cond['ref'], cond['ref'])


def convert(kept: list, form_map: dict, av, swap: bool) -> bytes:
    """Pack simplified, already-validated OR-groups as FO4 CTDAs; swap flips Subject and Target."""
    out = b''
    for group in kept:
        for i, cond in enumerate(group):
            func = FO4.index(RENAMED.get(cond['func'], cond['func']))
            run_on, ref = run_on_of(cond, swap, form_map)
            or_flag = 0x01 if i < len(group) - 1 else 0
            p1, p2 = _fo4_params(cond, form_map, av)
            out += pack_ctda((cond['op_flags'] & 0xE0) | or_flag, cond['value'], func, p1, p2, run_on, ref)
    return out
