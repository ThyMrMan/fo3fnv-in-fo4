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
from tes5_import.base.conditions_falloutnv import OBJECTIVE_FUNCS
from tools.dialog.tes4_ctda_dump import xedit_table

FNV = xedit_table('fnv')
FO4 = xedit_table('fo4')
FNV_DEFS = Path(__file__).resolve().parents[2] / 'references' / 'xEdit' / 'Core' / 'wbDefinitionsFNV.pas'
_AV_ENUM = re.search(r"wbActorValueEnum\s*:=\s*wbEnum\(\[(.*?)\]", FNV_DEFS.read_text(errors='replace'), re.S)
#: FNV actor value names by index; position, not xEdit's printed number (its Variable08 reads {79}).
FNV_AV_NAMES = re.findall(r"\}\s*'([^']*)'", _AV_ENUM.group(1))
#: xEdit's FNV actor value labels that are not the game's own name with the spaces dropped (GECK, scripts).
FNV_AV_GAME_NAMES = {'Critical Chance': 'CritChance', 'Damage Resistance': 'DamageResist',
                     'Poison Resistance': 'PoisonResist', 'Rad Resistance': 'RadResist',
                     'Speed Multiplier': 'SpeedMult', 'Rad Level': 'RadiationRads', 'Fire Resistance': 'FireResist',
                     'Electric Resistance': 'ElectricResist', 'Frost Resistance': 'FrostResist',
                     'Energy Resistance': 'EnergyResist', 'EMP Resistance': 'EmpResist'}
#: FNV name -> FO4's function doing the same: renamed, a note (an inventory item) counted, a map region's location.
RENAMED = {'GetActorValue': 'GetValue', 'GetPermanentActorValue': 'GetPermanentValue', 'GetPCIsSex': 'GetIsSex', 'GetHasNote': 'GetItemCount',
           'PlayerInRegion': 'GetInCurrentLocation', 'GetBaseActorValue': 'GetBaseValue'}
#: FNV functions reading one actor value, as FO4's GetValue of it: {function: FNV actor value index}.
AS_VALUE = {'GetRadiationLevel': FNV_AV_NAMES.index('Rad Level')}
#: FNV functions that test the player; FO4's counterpart runs on the player reference.
ON_PLAYER = {'GetPCIsSex', 'GetHasNote', 'PlayerInRegion'}
PLAYER_REF = 0x14
#: FNV functions with no parameter that FO4 asks of the player reference: the subject's faction hates the player.
TOWARD_PLAYER = {'GetActorFactionPlayerEnemy': 'IsHostileToActor'}
#: The player's base and reference: forms FNV and FO4 both own at these FormIDs, so a condition names them as is.
PLAYER_FORMS = frozenset({0x7, PLAYER_REF})
#: FNV functions reading 0 for a form the build leaves out (fo4_pipeline.md#dialogue-conditions).
ABSENT_ZERO = frozenset({'GetIsID', 'GetIsReference', 'GetIsVoiceType', 'GetInCell', 'GetInWorldspace',
                         'GetDeadCount', 'HasPerk', 'GetQuestCompleted', 'GetQuestRunning', 'GetStage',
                         'GetStageDone', 'GetObjectiveCompleted', 'GetObjectiveDisplayed', 'GetQuestVariable',
                         'GetScriptVariable', 'GetCasinoWinningStage', 'GetIsCurrentPackage'})
#: FNV functions fixed in an FO4 build: talking through an activator, Exists (fo4_pipeline.md#exists).
FIXED = {'IsActorTalkingThroughActivator': 0.0, 'Exists': 1.0}
#: FNV's test of a talker speaking as the line's actor, and the form map key head of an actor's talking-as list.
THROUGH, TALKING_AS = 'IsActorTalkingThroughActivator', 'talking_as'
#: FormIDs below this are the engine's own forms, the same in both games (the player's base 0x7 and reference 0x14).
ENGINE_FORMS = 0x800
#: Condition flag (both games): OR with the next condition.
OR_NEXT = 0x01
#: The objective states a mirror global keeps (form map key: (quest, objective, state)).
OBJECTIVE_STATES = tuple(OBJECTIVE_FUNCS.values())
#: Form map key head of a built quest's authored objective indexes: (AUTHORED, quest) -> frozenset.
AUTHORED = 'objectives'
#: Condition flag (both games): compare against a global's value; the value field holds the global's FormID.
USE_GLOBAL = 0x04
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
    return {'op_flags': op_flags, 'value': value, 'func': FNV.name(func), 'p1': p1, 'p2': p2, 'run_on': run_on,
            'ref': ref, 'global': struct.unpack_from('<I', raw, 4)[0]}


def fo4_value(cond: dict, form_map: dict) -> 'tuple | None':
    """(USE_GLOBAL or 0, comparison value) for FO4; a global's FormID maps through `form_map`, None without one."""
    if not cond['op_flags'] & USE_GLOBAL:
        return 0, cond['value']
    fo4 = form_map.get(cond.get('global'))
    return None if fo4 is None else (USE_GLOBAL, struct.unpack('<f', struct.pack('<I', fo4))[0])


def _is_or(cond: dict) -> bool:
    """True when this condition ORs with the next."""
    return bool(cond['op_flags'] & 0x01)


def compare(cond: dict, result: float) -> bool:
    """The condition's outcome when its function returns result."""
    return _OPS[cond['op_flags'] & 0xE0](result, cond['value'])


def speaker_settle(known: dict):
    """A settle() for simplify(): the outcome of a Subject test of one speaker's fixed facts, `known` {GetIsID or
    GetIsVoiceType: FormID, GetInFaction: frozenset of factions, 'unfixed': forms never settled}; None for any
    other test or fact."""
    def settle(cond: dict) -> 'bool | None':
        """The outcome of `cond` on the speaker, or None."""
        fact = known.get(cond['func'])
        if cond['run_on'] != RUN_SUBJECT or cond['op_flags'] & USE_GLOBAL or fact is None \
                or cond['p1'] in known.get('unfixed', ()):
            return None
        return compare(cond, float(cond['p1'] in fact if isinstance(fact, frozenset) else cond['p1'] == fact))
    return settle


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


def absent(cond: dict, form_map: dict) -> 'bool | None':
    """Outcome of a FIXED function's test, of an ABSENT_ZERO test of a form the build lacks, of an objective its
    quest does not author, or of any test run on a reference it lacks (all read 0); else None.
    See: docs/fork/fo4_pipeline.md#dialogue-conditions"""
    if cond['op_flags'] & USE_GLOBAL:
        return None
    if cond['func'] in FIXED:
        return compare(cond, FIXED[cond['func']])
    if unbuilt_reference(cond, form_map):
        return compare(cond, 0.0)
    if cond['func'] not in ABSENT_ZERO or 0 < cond['p1'] < ENGINE_FORMS:
        return None
    if _unauthored(cond, form_map):
        return compare(cond, 0.0)
    return None if cond['p1'] in form_map or _mirrored(cond, form_map) else compare(cond, 0.0)


def _unauthored(cond: dict, form_map: dict) -> bool:
    """True for an objective test of one its built quest lacks (reads 0)."""
    authored = form_map.get((AUTHORED, cond['p1']))
    return FNV.index(cond['func']) in OBJECTIVE_FUNCS and authored is not None and cond['p2'] not in authored


def unmapped_form(cond: dict, form_map: dict) -> bool:
    """True when a form parameter is neither in `form_map` nor the player's."""
    slots = FNV.form_slots.get(FNV.index(cond['func']), set())
    return any(s in slots and p not in form_map and p not in PLAYER_FORMS
               for s, p in ((1, cond['p1']), (2, cond['p2'])))


def unbuilt_reference(cond: dict, form_map: dict) -> bool:
    """True when a condition runs on a reference the build does not write."""
    return (cond['run_on'] == RUN_REFERENCE and cond['func'] not in ON_PLAYER and cond['ref'] >= ENGINE_FORMS
            and cond['ref'] not in form_map)


def _mirrored(cond: dict, form_map: dict) -> bool:
    """True when a quest variable or objective test has a mirror global."""
    p1, p2 = cond['p1'], cond['p2']
    return ('qvar', p1, p2) in form_map or any((p1, p2, state) in form_map for state in OBJECTIVE_STATES)


def _talked(cond: dict, form_map: dict) -> bool:
    """True for a Subject `GetIsID(actor) == 1` whose actor has a talking-as list in `form_map`."""
    return (cond['func'] == 'GetIsID' and cond['run_on'] == RUN_SUBJECT and not cond['op_flags'] & 0xE4
            and cond['value'] == 1.0 and (TALKING_AS, cond['p1']) in form_map)


def talking_list(cond: dict, form_map: dict) -> 'int | None':
    """The talking-as list a talked-through GetIsID also passes for, or None."""
    return form_map[(TALKING_AS, cond['p1'])] if _talked(cond, form_map) else None


def _through(cond: dict, actor: int) -> dict:
    """IsActorTalkingThroughActivator `== v` on a line that `actor` or its talker passes: GetIsID(actor) `== 1 - v`."""
    return {**cond, 'func': 'GetIsID', 'p1': actor, 'p2': 0, 'value': 1.0 - cond['value']}


def talking_through(conds: list, form_map: dict) -> list:
    """`conds` with each talked-through GetIsID OR'd with IsInList of its actor's talking-as list, and
    IsActorTalkingThroughActivator (== or != 0 or 1) as that actor's GetIsID negated.
    See: docs/fork/fo4_pipeline.md#talking-activators
    """
    actors = [cond['p1'] for cond in conds if _talked(cond, form_map)]
    out = []
    for cond in conds:
        if _talked(cond, form_map):
            out += [{**cond, 'op_flags': cond['op_flags'] | OR_NEXT},
                    {**cond, 'func': 'IsInList', 'p1': (TALKING_AS, cond['p1']), 'p2': 0}]
        elif (cond['func'] == THROUGH and actors and cond['run_on'] == RUN_SUBJECT
              and not cond['op_flags'] & 0xC4 and cond['value'] in (0.0, 1.0)):
            out.append(_through(cond, actors[0]))
        else:
            out.append(cond)
    return out


def without_absent(conds: list, form_map: dict) -> 'list | None':
    """`conds` less those absent() fixes, OR flags set again within each group; None when they never pass.
    See: docs/fork/fo4_pipeline.md#dialogue-conditions
    """
    kept = simplify(conds, lambda cond: absent(cond, form_map))
    if kept is None:
        return None
    return [{**cond, 'op_flags': cond['op_flags'] & ~OR_NEXT | (OR_NEXT if i < len(group) - 1 else 0)}
            for group in kept for i, cond in enumerate(group)]


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
            flag, value = fo4_value(cond, form_map)
            out += pack_ctda((cond['op_flags'] & 0xE0) | flag | or_flag, value, func, p1, p2, run_on, ref)
    return out
