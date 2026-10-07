"""An FNV quest as an FO4 QUST, for the cell spike.

The quest keeps its name, priority, stages (a log entry each, with FNV's
complete flag), objectives and scripts: its quest script attached plainly
and its converted stage results (`FALLOUTNV_QF_<quest>`) as stage fragments,
both filled by attach.ObjectScripts. An objective's targets become forced
reference aliases, one per target. It is not start-game enabled: the spike
starts it by setting its first stage.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from fo4_import.base.vmad import quest_fragments
from fo4_import.spike import records as R
from fo4_import.spike.script import QUEST_PREFIX, stage_fragments

#: The alias a quest's conversation scenes play on; TES4Polyfill.StartConversation fills it.
SPEAKER_ALIAS = 0
#: FNV QUST DATA flag Start Game Enabled.
START_GAME = 0x01


def _numbered(rec: dict, prefix: str) -> list:
    """Indices i of an export record's `prefix`[i] entries."""
    out = []
    while f'{prefix}[{len(out)}].Index' in rec:
        out.append(len(out))
    return out


def objectives(rec: dict, ref_ids: dict, first: int = 0) -> tuple:
    """(objectives [(index, text, [alias ids])], aliases [(id, name, reference)]) of FNV quest `rec`.

    `ref_ids` is {FNV FormID (hex): FO4 reference}; a target not converted is
    dropped. Alias ids start at `first`.
    """
    aliases, out = {}, []
    for i in _numbered(rec, 'Objective'):
        targets, k = [], 0
        while f'Objective[{i}].Target[{k}].FormID' in rec:
            fnv = rec[f'Objective[{i}].Target[{k}].FormID'].upper()
            if fnv in ref_ids:
                targets.append(aliases.setdefault(fnv, first + len(aliases)))
            k += 1
        out.append((int(rec[f'Objective[{i}].Index']), rec.get(f'Objective[{i}].Text', ''), targets))
    return out, [(alias, f'Target{fnv}', ref_ids[fnv]) for fnv, alias in aliases.items()]


def quest_record(fid: int, rec: dict, scripts, ref_ids: dict, speaker: bool = False, start: bool = False) -> bytes:
    """The FO4 QUST of FNV quest `rec`; `scripts` an attach.ObjectScripts, `ref_ids` as for objectives().

    `speaker` adds alias 0, empty, for the actor its conversation scenes play
    on; `start` keeps FNV's start game enabled flag.
    """
    stages = [(int(rec[f'Stage[{i}].Index']), int(rec.get(f'Stage[{i}].Log[0].Flags', 0)) & 1)
              for i in _numbered(rec, 'Stage')]
    fragments_script = f'{QUEST_PREFIX}{rec["EditorID"]}'
    fragments = []
    if scripts.dir and (scripts.dir / f'{fragments_script}.psc').exists():
        fragments = stage_fragments((scripts.dir / f'{fragments_script}.psc').read_text(encoding='utf-8'))
        scripts.used.append(fragments_script)
    quest_script = scripts.name(int(rec['SCRI'], 16)) if 'SCRI' in rec else None
    attached = [(quest_script, scripts.properties(quest_script), {})] if quest_script else []
    scripts.used += [quest_script] if quest_script else []
    props = scripts.properties(fragments_script) if fragments else {}
    vmad = quest_fragments(fragments_script if fragments else '', fragments, props, scripts=attached)
    goals, aliases = objectives(rec, ref_ids, int(speaker))
    aliases = [(SPEAKER_ALIAS, 'Speaker', None)] * speaker + aliases
    return R.pack_fnv_quest(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), int(rec.get('DATA.Priority', 0)),
                            vmad, stages, goals, aliases, start and int(rec.get('DATA.Flags', 0)) & START_GAME)
