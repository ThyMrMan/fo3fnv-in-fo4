"""An FNV quest as an FO4 QUST, for the cell spike.

The quest keeps its name, priority, stages (a log entry each, with FNV's
complete flag), objectives and scripts: its quest script attached plainly
and its converted stage results (`FALLOUTNV_QF_<quest>`) as stage fragments,
both filled by attach.ObjectScripts. An objective's targets become forced
reference aliases, one per target. It is not start-game enabled: the spike
starts it by setting its first stage.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from fo4_import.base.ledger import NUMBER
from fo4_import.base.support_records import pack_global
from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.conditions import AUTHORED
from fo4_import.spike.readiness import TARGET_NOT_BUILT
from fo4_import.spike.script import QUEST, prefix, stage_fragments
from tes5_import.base.conditions_falloutnv import OBJECTIVE_FUNCS
from tes5_import.base.objectives_falloutnv import objective_global_name
from script_convert.quest_var_mirrors import quest_var_global_name, tested_quest_vars

#: The alias a quest's conversation scenes play on; TES4Polyfill.StartConversation fills it.
SPEAKER_ALIAS = 0
#: The other NPC's alias in an NPC-to-NPC talk (StartConversation's 1000), past the objective aliases.
LISTENER_ALIAS = 1000
#: derive_formid site of a quest variable's mirror global (key: the global's name).
QVAR_SITE = 'FNV qvar GLOB'
#: Ledger site of a quest's objective target alias ids (with the FNV quest's FormID; key: the target's).
ALIAS_SITE = 'FNV alias'
#: FNV QUST DATA flag Start Game Enabled.
START_GAME = 0x01


def _numbered(rec: dict, prefix: str) -> list:
    """Indices i of an export record's `prefix`[i] entries."""
    out = []
    while f'{prefix}[{len(out)}].Index' in rec:
        out.append(len(out))
    return out


def objectives(rec: dict, ref_ids: dict, first: int = 0, writer=None) -> tuple:
    """(objectives [(index, text, [alias ids])], aliases [(id, name, reference)]) of FNV quest `rec`.

    `ref_ids` is {FNV FormID (hex): FO4 reference}; a target not converted is
    dropped. A target's alias id is the lowest free one from `first`, kept by
    `writer`'s ledger so it stays put as more targets are built.
    See: docs/fork/fo4_pipeline.md#formid-ledger
    """
    aliases, out, site = {}, [], f'{ALIAS_SITE} {rec["FormID"].upper()}'
    taken = set(writer.ledger.values(NUMBER, site)) if writer else set()

    def free() -> int:
        """The lowest alias id from `first` neither kept nor given."""
        return next(n for n in range(first, first + len(taken) + len(aliases) + 1) if n not in taken)
    for i in _numbered(rec, 'Objective'):
        targets, k = [], 0
        while f'Objective[{i}].Target[{k}].FormID' in rec:
            fnv = rec[f'Objective[{i}].Target[{k}].FormID'].upper()
            if fnv in ref_ids and fnv not in aliases:
                aliases[fnv] = writer.stable_number(site, fnv, free) if writer else free()
                taken.add(aliases[fnv])
            targets += [aliases[fnv]] if fnv in aliases else []
            k += 1
        out.append((int(rec[f'Objective[{i}].Index']), rec.get(f'Objective[{i}].Text', ''), targets))
    return out, [(alias, f'Target{fnv}', ref_ids[fnv]) for fnv, alias in aliases.items()]


def missing_targets(rec: dict, ref_ids: dict) -> list:
    """'objective <n>: <FormID>' of `rec`'s objective targets not in `ref_ids`."""
    return [f'objective {rec[f"Objective[{i}].Index"]}: {rec[key].upper()}' for i in _numbered(rec, 'Objective')
            for key in _numbered_keys(rec, f'Objective[{i}].Target', 'FormID') if rec[key].upper() not in ref_ids]


def _numbered_keys(rec: dict, prefix: str, field: str) -> list:
    """The keys `<prefix>[k].<field>` of `rec`, k from 0 while present."""
    keys, k = [], 0
    while f'{prefix}[{k}].{field}' in rec:
        keys.append(f'{prefix}[{k}].{field}')
        k += 1
    return keys


def objective_key(quest: str, index: int, state: str) -> str:
    """new_id key of quest `quest`'s objective `index` mirror global for `state`."""
    return f'GLOB {quest} {index} {state}'


def objective_globals(builder, recs: list) -> dict:
    """Mirror globals of FNV quests `recs`' objective states, written and named for scripts.

    Returns {(FNV quest FormID, objective index, state): global}, the keys conditions_of looks up, and
    {(AUTHORED, FNV quest FormID): its objective indexes}.
    """
    out = {}
    for rec in recs:
        out[(AUTHORED, int(rec['FormID'], 16))] = frozenset(
            int(rec[f'Objective[{i}].Index']) for i in _numbered(rec, 'Objective'))
        for i in _numbered(rec, 'Objective'):
            for state in OBJECTIVE_FUNCS.values():
                index = int(rec[f'Objective[{i}].Index'])
                fid = builder.new_id(objective_key(rec['FormID'], index, state))
                name = objective_global_name(rec['EditorID'], index, state)
                builder.writer.add_record('GLOB', pack_global(fid, name))
                out[(int(rec['FormID'], 16), index, state)] = builder.scripts.named[name] = fid
    builder.counts['GLOB'] += sum(key[0] != AUTHORED for key in out)
    return out


def quest_var_globals(builder, export_dir, recs: list) -> dict:
    """Mirror globals of the variables of FNV quests `recs` that packages test, and of any quest's that their
    lines (builder.say) test, written and named for scripts (builder.script_vars names them);
    {('qvar', quest FormID, variable index): global}. A quest the build leaves out keeps its global at 0.
    See: docs/fork/fo4_pipeline.md#packages
    """
    built = {int(r['FormID'], 16) for r in recs}
    tested = {var for var in tested_quest_vars(export_records(export_dir, 'PACK')) if var[0] in built}
    tested |= tested_quest_vars(line for r in recs for line in builder.say.infos.get(r['FormID'].upper(), []))
    edids, out = {int(r['FormID'], 16): r['EditorID'] for r in export_records(export_dir, 'QUST')}, {}
    for quest, index in sorted(tested):
        variable = builder.script_vars.get(quest, ('', {}))[1].get(index)
        if quest in edids and variable:
            name = quest_var_global_name(edids[quest], variable)
            fid = builder.writer.derive_formid(QVAR_SITE, name)
            builder.writer.add_record('GLOB', pack_global(fid, name))
            out[('qvar', quest, index)] = builder.scripts.named[name] = fid
    builder.counts['quest variable GLOB'] += len(out)
    return out


def quest_record(fid: int, rec: dict, scripts, ref_ids: dict, speaker: bool = False, start: bool = False,
                 more: tuple = (), attach: tuple = ()) -> bytes:
    """The FO4 QUST of FNV quest `rec`; `scripts` an attach.ObjectScripts, `ref_ids` as for objectives().

    `speaker` adds alias 0, empty, for the actor its conversation scenes play
    on, and LISTENER_ALIAS for the other actor of an NPC one; `start` keeps
    FNV's start game enabled flag; `more` aliases (pack_fnv_quest's) follow;
    `attach` scripts [(script, object props, value props)] join its own.
    """
    stages = [(int(rec[f'Stage[{i}].Index']), int(rec.get(f'Stage[{i}].Log[0].Flags', 0)) & 1)
              for i in _numbered(rec, 'Stage')]
    fragments_script = f'{prefix(QUEST)}{rec["EditorID"]}'
    fragments = []
    if scripts.dir and (scripts.dir / f'{fragments_script}.psc').exists():
        fragments = stage_fragments((scripts.dir / f'{fragments_script}.psc').read_text(encoding='utf-8'))
        scripts.used.append(fragments_script)
    quest_script = scripts.name(int(rec['SCRI'], 16)) if 'SCRI' in rec else None
    attached = ([(quest_script, scripts.properties(quest_script), {})] if quest_script else []) + list(attach)
    scripts.used += [quest_script] if quest_script else []
    props = scripts.properties(fragments_script) if fragments else {}
    vmad = quest_fragments(fragments_script if fragments else '', fragments, props, scripts=attached)
    goals, aliases = objectives(rec, ref_ids, int(speaker), scripts.builder.writer)
    for target in missing_targets(rec, ref_ids):
        scripts.builder.readiness.add(TARGET_NOT_BUILT, rec['FormID'], target)
    aliases = [(SPEAKER_ALIAS, 'Speaker', None)] * speaker + aliases + [(LISTENER_ALIAS, 'Listener', None)] * speaker
    aliases += list(more)
    flags = int(rec.get('DATA.Flags', 0))
    return R.pack_fnv_quest(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), int(rec.get('DATA.Priority', 0)),
                            vmad, stages, goals, aliases, start and flags & START_GAME, bool(flags & R.REPEATED_STAGES))
