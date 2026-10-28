"""Each built line's conditions against its FNV line's, evaluated over sampled game states.

Both sides are read into one vocabulary: a condition is a fact (a function,
whom it runs on, its parameters), a comparison and a value. Functions pair by
xEdit's names, forms by EditorID (or FormID when the build kept it), and the
build's mirror globals by their authored names (`TES4QVar_<quest>_<variable>`,
`TES4ObjDone_`, `TES4ObjShown_`), never through the converter's tables. A line
says only while its quest runs, so each side gets that test too. A form the
build left out reads 0. The build's own state (topic unlocks, follow-up and
Say Once marks) counts as true. A pair holding a function the evaluator cannot
pair, or a Fallout 4 form standing in for an FNV one, is counted, not judged.

See: docs/fork/fo4_preflight.md#condition-diff
"""

import random
import re
import struct
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from tools.dialog.tes4_ctda_dump import xedit_table
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.fo4_dialogue import scene_actions
from tools.validate.preflight.plugin_index import first, u32, zstring

FNV, FO4 = xedit_table('fnv'), xedit_table('fo4')

#: FNV functions under another Fallout 4 name, and the one that tests the player rather than the run-on.
SAME_AS = {'GetPCIsSex': 'GetIsSex'}
ON_PLAYER = frozenset({'GetPCIsSex'})

#: Functions true for exactly one value of their first parameter: who or what the run-on is.
IDENTITY = frozenset({'GetIsID', 'GetIsVoiceType', 'GetIsReference', 'GetIsRace', 'GetIsClass', 'GetIsCreature'})

#: Facts that read only 0 or 1: these functions and mirror kinds, and functions named Is*, GetIs*, Has*.
YES_NO = frozenset({'GetInFaction', 'GetDead', 'GetQuestRunning', 'GetQuestCompleted', 'GetStageDone', 'GetTalkedToPC',
                    'GetLocked', 'GetDisabled', 'GetInCell', 'GetInWorldspace', 'GetEquipped', 'GetMapMarkerVisible',
                    'GetPlayerTeammate', 'GetInSameCell', 'objdone', 'objshown'})
YES_NO_PREFIXES = ('Is', 'GetIs', 'Has')

#: Facts that never read below 0.
NOT_NEGATIVE = frozenset({'GetItemCount', 'GetDeadCount', 'GetLevel', 'GetStage', 'GetHealthPercentage',
                          'GetCurrentTime', 'GetRandomPercent', 'GetDistance', 'GetFactionRank'})

#: Functions the evaluator cannot pair: actor values, script variables by index, reputation, packages, regions.
UNPAIRED = frozenset({'GetActorValue', 'GetPermanentActorValue', 'GetValue', 'GetPermanentValue',
                      'GetScriptVariable', 'GetVMScriptVariable', 'GetReputationThreshold', 'GetReputation',
                      'GetIsCurrentPackage', 'GetCurrentAIPackage', 'PlayerInRegion', 'GetInCurrentLocation',
                      'GetHasNote', 'GetSitting'})

#: Mirror global names: (prefix, fact kind); the rest of the name is `<quest>_<variable or objective>`.
MIRRORS = (('TES4QVar_', 'qvar'), ('TES4ObjDone_', 'objdone'), ('TES4ObjShown_', 'objshown'))

#: Global prefixes of the build's own state, true for a line about to be said; reputation mirrors are not paired.
BUILD_STATE, REPUTATION = ('TES4Unlock_', 'TES4FollowUpFrom_', 'TES4FollowUpSaid_'), 'TES4Rep'

#: The quest holding the build's Say Once marks, whose GetStageDone tests are build state.
SAY_ONCE_QUEST = 'tes4sayonce'

#: FNV objective tests and the mirror fact each becomes.
OBJECTIVES = {'GetObjectiveCompleted': 'objdone', 'GetObjectiveDisplayed': 'objshown'}

#: FNV base record types whose EditorIDs name condition parameters.
NAMED_TYPES = ('QUST', 'NPC_', 'CREA', 'FACT', 'GLOB', 'VTYP', 'CELL', 'WRLD', 'PERK', 'MISC', 'ARMO', 'WEAP', 'ALCH',
               'BOOK', 'NOTE', 'KEYM', 'AMMO', 'CLAS', 'RACE', 'FLST', 'CHAL', 'LVLN', 'LVLC', 'SPEL', 'MGEF', 'CONT',
               'DOOR', 'ACTI', 'FURN', 'TACT', 'IMOD', 'CSTY', 'TERM', 'LIGH', 'IDLE', 'MESG')

#: A ledger key of a placed reference the build gave a new FormID.
_MOVED_KEY = re.compile(r"^'(?:ACHR|ACRE|REFR) ([0-9A-Fa-f]{8})\b")

#: Condition flags (both games): OR with the next, and compare against a global's value.
OR_NEXT, USE_GLOBAL = 0x01, 0x04

#: Comparison operators by the top three bits of the condition type.
_OPS = {0x00: lambda a, b: a == b, 0x20: lambda a, b: a != b, 0x40: lambda a, b: a > b,
        0x60: lambda a, b: a >= b, 0x80: lambda a, b: a < b, 0xA0: lambda a, b: a <= b}

#: Run-on values (both games): subject, target, reference; others are not paired.
SUBJECT, TARGET, REFERENCE = 0, 1, 2

#: The player reference, the same FormID in both games.
PLAYER_REF = 0x14

#: The forms both games share by FormID: the player's base and reference.
ENGINE_FORMS = frozenset({0x07, PLAYER_REF})

#: States sampled per pair when the full product is larger; the product is used when at most this.
SAMPLES = 256

#: Lines listed per finding.
SHOWN = 6

#: Markers a condition reads into instead of a fact: always true, or not pairable.
TRUE, UNJUDGED = 'true', 'unjudged'


class Names:
    """Form identity across the two games: an EditorID both share, a placed reference the ledger moved, the kept
    FormID, else absent."""

    def __init__(self, index, export_dir, ledger):
        """Read the FNV EditorIDs of NAMED_TYPES, the build's own EditorIDs and the ledger's moved references."""
        self.index, self.own = index, len(index.masters)
        self.moved = moved_references(ledger, self.own)
        self.fnv = {int(r['FormID'], 16): r['EditorID'].lower() for sig in NAMED_TYPES
                    for r in export_records(export_dir, sig) if r.get('EditorID')}
        self.fnv_names = set(self.fnv.values())
        self.built = {index.edid(fid).lower() for fid in index.by_fid if index.is_own(fid)} - {''}

    def source(self, fid: int):
        """The identity of FNV form `fid`, or None when the build left it out."""
        if fid in ENGINE_FORMS:
            return ('engine', fid)
        if self.moved.get(fid) in self.index.by_fid:
            return self.built_form(self.moved[fid])
        name = self.fnv.get(fid)
        if name in self.built:
            return ('form', name)
        kept = (self.own << 24) | (fid & 0xFFFFFF)
        return ('id', fid & 0xFFFFFF) if kept in self.index.by_fid else None

    def built_form(self, fid: int):
        """The identity of built form `fid`, or UNJUDGED for a Fallout 4 form standing in for an FNV one."""
        if fid in ENGINE_FORMS:
            return ('engine', fid)
        if not self.index.is_own(fid):
            return UNJUDGED
        name = self.index.edid(fid).lower()
        return ('form', name) if name in self.fnv_names else ('id', fid & 0xFFFFFF)

    def quest(self, name: str):
        """The identity of a quest named in a mirror global."""
        return ('form', name.lower())

    def source_quest(self, fid: int):
        """FNV quest `fid` by name, built or not (mirror globals keep its variables)."""
        name = self.fnv.get(fid)
        return self.quest(name) if name else None


def moved_references(ledger, own: int) -> dict:
    """{FNV placed reference FormID: built FormID} the ledger renumbered (`'ACHR <FormID> ...'`); the ledger keeps
    entries of earlier builds, so a caller checks the built FormID exists."""
    path = Path(ledger)
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    out = {}
    for row in (line.split('\t') for line in lines):
        match = _MOVED_KEY.match(row[2]) if len(row) == 4 else None
        if match:
            out[int(match.group(1), 16)] = (own << 24) | int(row[3], 16)
    return out


def decode(data: bytes) -> dict:
    """The fields of one CTDA (28 bytes in FNV, 32 in Fallout 4)."""
    data = data + bytes(max(0, 28 - len(data)))
    ctype, comp_raw, func, p1, p2, run_on, ref = struct.unpack_from('<B3x4sH2xIIII', data)
    return {'type': ctype, 'value': struct.unpack('<f', comp_raw)[0], 'value_fid': struct.unpack('<I', comp_raw)[0],
            'func': func, 'p1': p1, 'p2': p2, 'run_on': run_on, 'ref': ref, 'text': ''}


def built_conditions(rec) -> list:
    """The decoded CTDAs of a built INFO, each with the CIS2 string that follows it."""
    out = []
    for sub in rec.subrecords:
        if sub.type == 'CTDA':
            out.append(decode(sub.data))
        elif sub.type == 'CIS2' and out:
            out[-1]['text'] = zstring(sub.data)
    return out


def _run_on(cond: dict, ident, on_player: bool):
    """The run-on part of a fact, or UNJUDGED."""
    if on_player:
        return ('ref', ('engine', PLAYER_REF))
    if cond['run_on'] in (SUBJECT, TARGET):
        return cond['run_on']
    if cond['run_on'] == REFERENCE:
        target = ident(cond['ref'])
        return UNJUDGED if target in (UNJUDGED, None) else ('ref', target)
    return UNJUDGED


def _params(table, func: int, cond: dict, ident) -> tuple:
    """Fact parameters: forms by identity (None if left out), others as they are."""
    slots = table.form_slots.get(func, set())
    return tuple(ident(cond[f'p{i}']) if i in slots else cond[f'p{i}'] for i in (1, 2))


def _fact(name: str, run_on, params: tuple):
    """A fact key, or UNJUDGED/None when one of its parts is."""
    if UNJUDGED in params or run_on == UNJUDGED:
        return UNJUDGED
    if None in params:
        return None
    if name in IDENTITY:
        return ('is', name, run_on), params[0]
    return (name, run_on, params), None


def source_fact(cond: dict, names: Names, script_vars: dict):
    """The fact of one FNV condition: (key, identity value or None), None for a left-out form, or a marker."""
    name = FNV.name(cond['func'])
    if name in UNPAIRED:
        return UNJUDGED
    if name == 'GetQuestVariable':
        quest = names.source_quest(cond['p1'])
        var = script_vars.get(cond['p1'], {}).get(cond['p2'])
        return UNJUDGED if var is None else (None if quest is None else (('qvar', quest, var.lower()), None))
    if name in OBJECTIVES:
        quest = names.source_quest(cond['p1'])
        return None if quest is None else ((OBJECTIVES[name], quest, cond['p2']), None)
    if name == 'GetGlobalValue':
        glob = names.source(cond['p1'])
        return None if glob is None else (('glob', glob), None)
    run_on = _run_on(cond, names.source, name in ON_PLAYER)
    return _fact(SAME_AS.get(name, name), run_on, _params(FNV, cond['func'], cond, names.source))


def _mirror(edid: str, names: Names):
    """The fact a mirror global stands for, a marker, or None when the global is an ordinary one."""
    if edid.startswith(BUILD_STATE):
        return TRUE
    if edid.startswith(REPUTATION):
        return UNJUDGED
    for prefix, kind in MIRRORS:
        if edid.startswith(prefix):
            quest, _, rest = edid[len(prefix):].rpartition('_')
            return (kind, names.quest(quest), int(rest) if rest.isdigit() and kind != 'qvar' else rest.lower()), None
    return None


def built_fact(cond: dict, names: Names):
    """The fact of one built condition: (key, identity value or None), or a marker."""
    name = FO4.name(cond['func'])
    if name in UNPAIRED:
        return UNJUDGED
    if name == 'GetGlobalValue':
        glob = names.built_form(cond['p1'])
        mirror = _mirror(names.index.edid(cond['p1']), names) if glob != UNJUDGED else UNJUDGED
        return mirror if mirror is not None else (('glob', glob), None)
    if name == 'GetVMQuestVariable':
        var = re.sub(r'^::|_var$', '', cond['text']).lower()
        quest = names.built_form(cond['p1'])
        return UNJUDGED if quest == UNJUDGED or not var else (('qvar', quest, var), None)
    if name == 'GetStageDone' and names.index.edid(cond['p1']).lower() == SAY_ONCE_QUEST:
        return TRUE
    return _fact(name, _run_on(cond, names.built_form, False), _params(FO4, cond['func'], cond, names.built_form))


def _rhs(cond: dict, ident):
    """The right side of a comparison: a number, or the fact of the global it compares against."""
    if not cond['type'] & USE_GLOBAL:
        return cond['value']
    glob = ident(cond['value_fid'])
    return UNJUDGED if glob == UNJUDGED else (0.0 if glob is None else (('glob', glob), None))


def read_side(conds: list, fact, ident, running) -> object:
    """[(fact or marker, op, right side, or flag)] for one side, the quest-running test first; UNJUDGED if any is."""
    out = [(running, 0x00, 1.0, False)]
    for cond in conds:
        key, rhs = fact(cond), _rhs(cond, ident)
        if UNJUDGED in (key, rhs):
            return UNJUDGED
        out.append((key, cond['type'] & 0xE0, rhs, bool(cond['type'] & OR_NEXT)))
    return out


def _value(term, state: dict) -> float:
    """The value of a fact (or a number) in `state`; a left-out form's fact reads 0."""
    if term is None or isinstance(term, float):
        return term or 0.0
    key, identity = term
    if identity is not None:
        return 1.0 if state.get(key) == identity else 0.0
    return state.get(key, 0.0)


def evaluate(side: list, state: dict) -> bool:
    """Whether one side's conditions pass in `state`: an AND of OR chains."""
    chains, chain = [], []
    for term, op, rhs, or_next in side:
        chain.append(term == TRUE or _OPS.get(op, _OPS[0])(_value(term, state), _value(rhs, state)))
        if not or_next:
            chains.append(any(chain))
            chain = []
    return all(chains + ([any(chain)] if chain else []))


def numeric_domain(kind: str, values: set) -> list:
    """The values a numeric fact of `kind` can take: 0 and 1 for a yes/no one, never below 0 for a count."""
    if kind in YES_NO or kind.startswith(YES_NO_PREFIXES):
        return [0.0, 1.0]
    values = values | {0.0, 1.0, -1.0}
    return sorted(v for v in values if v >= 0 or kind not in NOT_NEGATIVE)


def domains(sides: list) -> dict:
    """{fact key: values to try}: identities seen and none, or the compared constants and their neighbors."""
    found = defaultdict(set)
    for side in sides:
        for term, _op, rhs, _or in side:
            for t in (term, rhs):
                if isinstance(t, tuple):
                    found[t[0]].add(t[1])
            if isinstance(term, tuple) and term[1] is None and isinstance(rhs, float):
                found[term[0]] |= {rhs - 1, rhs, rhs + 1}
    return {key: sorted(v - {None} | {None}, key=repr) if any(x is not None and not isinstance(x, float) for x in v)
            else numeric_domain(key[0], v - {None}) for key, v in found.items()}


def states(doms: dict, seed: int, forced: dict):
    """Every state of `doms` when few, else SAMPLES random ones (seeded by the pair); `forced` facts are fixed."""
    doms = {**doms, **{k: [v] for k, v in forced.items()}}
    keys = sorted(doms, key=repr)
    total = 1
    for k in keys:
        total *= len(doms[k])
    if total <= SAMPLES:
        return [dict(zip(keys, combo)) for combo in product(*(doms[k] for k in keys))]
    rng = random.Random(seed)
    return [{k: rng.choice(doms[k]) for k in keys} for _ in range(SAMPLES)]


def disagreement(fnv_side: list, fo4_side: list, seed: int, forced: dict):
    """(state, FNV result) of a state where the two sides differ, or None; `forced` facts hold in every state."""
    for state in states(domains([fnv_side, fo4_side]), seed, forced):
        said = evaluate(fnv_side, state)
        if said != evaluate(fo4_side, state):
            return state, said
    return None


def describe_state(state: dict) -> str:
    """The non-default facts of a state, short."""
    shown = [f'{k}={v}' for k, v in sorted(state.items(), key=repr) if v not in (None, 0.0)]
    return ', '.join(shown[:SHOWN]) or 'every fact 0'


class Pairs:
    """Judge every FNV line against the first-response copies the build wrote of it."""

    def __init__(self, ctx, parts: dict, export_dir, ledger):
        """The source game and built plugin of `ctx`, line_parts' `parts`, the export for names and variables, and
        the build's FormID ledger."""
        self.ctx, self.parts = ctx, parts
        self.names = Names(ctx.index, export_dir, ledger)
        self.script_vars = quest_variables(export_dir)
        self.holotape_topics = holotape_topics(ctx.index)
        self.counts = Counter()

    def fnv_running(self, info):
        """The FNV line's quest-running test: its fact, TRUE for a game-start quest the build lacks, or UNJUDGED."""
        quest = self.names.source(info.quest)
        if quest is not None:
            return running_fact(quest)
        name = self.ctx.source.quest_fids.get(info.quest, '').lower()
        return TRUE if name in self.ctx.source.start_enabled else UNJUDGED

    def fnv_side(self, info):
        """The FNV line's side, or UNJUDGED."""
        running = self.fnv_running(info)
        if running == UNJUDGED:
            return UNJUDGED
        quest = [decode(d) for d in self.ctx.source.quest_conditions.get(info.quest, ())]
        if quest:
            quest[-1]['type'] &= ~OR_NEXT
        return read_side(quest + [decode(d) for d in info.raw],
                         lambda c: source_fact(c, self.names, self.script_vars), self.names.source, running)

    def fo4_side(self, rec) -> tuple:
        """(one built copy's side or UNJUDGED, {its scene quest's running fact: 1}: the scene plays).

        A copy a holotape plays is played by its item, not its conditions, so it is not judged.
        """
        quest = self.names.built_form(u32(first(self.ctx.index.by_fid[rec.parent_dial], 'QNAM')))
        if quest == UNJUDGED or rec.parent_dial in self.holotape_topics:
            return UNJUDGED, {}
        running = running_fact(quest)
        return read_side(built_conditions(rec), lambda c: built_fact(c, self.names), self.names.built_form,
                         running), {running[0]: 1.0}

    def judge(self, fid: int) -> list:
        """[(built FormID, state, FNV result)] for the copies of FNV line `fid` that disagree with it."""
        info, copies = self.ctx.source.infos.get(fid), self.parts.get(fid, {}).get(1, [])
        fnv = self.fnv_side(info) if info and copies else UNJUDGED
        if fnv == UNJUDGED:
            self.counts['FNV line not paired' if copies else 'no first response built'] += 1
            return []
        out = []
        for built in copies:
            side, forced = self.fo4_side(self.ctx.index.by_fid[built])
            if side == UNJUDGED:
                self.counts['copy not paired'] += 1
                continue
            self.counts['copies judged'] += 1
            found = disagreement(fnv, side, built, forced)
            if found:
                out.append((built, *found))
        return out


def holotape_topics(index) -> set:
    """The topics of the scenes a holotape (NOTE) plays."""
    scenes = {r.form_id: r for r in index.by_type['SCEN']}
    played = {u32(s.data) for note in index.by_type['NOTE'] for s in note.subrecords
              if len(s.data) == 4 and u32(s.data) in scenes}
    return set().union(*(scene_actions(scenes[s])[0] for s in played))


def running_fact(quest) -> tuple:
    """The fact that `quest` (an identity) is running, as GetQuestRunning reads it."""
    return ('GetQuestRunning', SUBJECT, (quest, 0)), None


def variables(rec: dict) -> dict:
    """{variable index: name} of one exported script."""
    out, i = {}, 0
    while f'Variable[{i}].Index' in rec:
        out[int(rec[f'Variable[{i}].Index'])] = rec[f'Variable[{i}].Name']
        i += 1
    return out


def quest_variables(export_dir) -> dict:
    """{FNV quest FormID: {variable index: name}} from each quest's script."""
    names = {rec['FormID'].upper(): variables(rec) for rec in export_records(export_dir, 'SCPT')}
    return {int(q['FormID'], 16): names.get(q.get('SCRI', '').upper(), {})
            for q in export_records(export_dir, 'QUST')}


def _finding(ctx, fid: int, rows: list) -> Finding:
    """The finding for one FNV line whose copies disagree with it."""
    info = ctx.source.infos[fid]
    topic = ctx.source.dials.get(info.dial, ('?',))[0]
    quest = ctx.source.quest_fids.get(info.quest, '?')
    built, state, said = rows[0]
    how = 'FNV says it and the build cannot' if said else 'the build says it where FNV cannot'
    return Finding('conditions', f'conditions|{ctx.game}|{fid:08X}', 'review',
                   f'line {fid:08X} ({quest}, topic {topic}): {how}',
                   (f'{len(rows)} built copies disagree, first {built:08X} in topic '
                    f'{ctx.index.edid(ctx.index.by_fid[built].parent_dial)}', f'when {describe_state(state)}'))


def audit(ctx, parts: dict, export_dir, ledger) -> list:
    """One review per FNV line whose built conditions disagree with its own; prints what was judged."""
    pairs = Pairs(ctx, parts, export_dir, ledger)
    out = [_finding(ctx, fid, rows) for fid in sorted(parts) if (rows := pairs.judge(fid))]
    print('  conditions: ' + ', '.join(f'{n} {what}' for what, n in pairs.counts.most_common()))
    return out
