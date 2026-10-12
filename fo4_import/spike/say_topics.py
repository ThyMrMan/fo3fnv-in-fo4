"""An FNV quest's scripted lines as FO4 Custom topics, for the cell spike.

FNV's Say/SayTo plays a topic's first line whose conditions pass, and Say
Once lines step through a chain. FO4's Say does the same with a Custom topic
(DATA 0, SNAM CUST) in a branch of its quest, as vanilla's MS09Branch. The
quest's Conversation-type topics (FNV DIAL type 1) become such topics; each
line keeps its responses, Say Once flag, conditions (forms through the cell;
GetQuestVariable as GetVMQuestVariable on the converted property) and its
converted result fragments. Lines with a condition that cannot convert are
left out and counted.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from pathlib import Path

from fo4_import.base.vmad import info_fragments
from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike.poses import line_idle
from fo4_import.pipeline.export_index import export_records
from script_convert.constants import papyrus_script_name
from tes5_import.base.conditions_falloutnv import OBJECTIVE_FUNCS

#: FNV DIAL type of the topics scripts Say: Conversation.
CONVERSATION = '1'
#: FNV INFO DATA flag Say Once.
SAY_ONCE = 0x04
#: Keys of a split line's part (conversation.part): its number and the line's count of parts.
PART, PARTS = '_part', '_parts'
FRAGMENT_PREFIX = 'FALLOUTNV_TIF__'
#: CTDA operator bits: the comparison, OR with the next, use a global as the value.
COMPARE, OR = 0xE0, 0x01
#: The FNV command opening a vendor's barter menu (lower case).
BARTER = 'showbartermenu'
#: FNV GetQuestVariable and FO4's GetVMQuestVariable, which names the Papyrus property in its CIS2.
QUEST_VARIABLE, VM_QUEST_VARIABLE = 'GetQuestVariable', 'GetVMQuestVariable'
#: FNV GetScriptVariable (reference, variable) and FO4's GetVMScriptVariable (run on it; CIS1 script, CIS2 variable).
SCRIPT_VARIABLE, VM_SCRIPT_VARIABLE = 'GetScriptVariable', 'GetVMScriptVariable'
SCRIPT_PREFIX = 'FALLOUTNV_'
#: FO4 has no objective condition; an objective test reads its mirror global (objectives_falloutnv).
GLOBAL_VALUE = 'GetGlobalValue'


class SayTopics:
    """FO4 Custom topics for FNV quests' Conversation topics; `voiced` lists [(FO4 INFO, FNV INFO)]."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV topics, lines and quest script variables; topics are written through `builder`."""
        self.builder, self.voiced = builder, []
        self.dials = {r['FormID']: r for r in export_records(export_dir, 'DIAL')}
        self.infos = {}
        for rec in export_records(export_dir, 'INFO'):
            self.infos.setdefault(rec.get('QSTI.Quest', '').upper(), []).append(rec)
        self.script_vars = _script_vars(export_dir)

    def topics(self, quest: dict) -> list:
        """FNV FormIDs of `quest`'s Conversation topics, in first-line order."""
        seen = {}
        for rec in self.infos.get(quest['FormID'].upper(), []):
            if self.dials.get(rec['ParentDIAL'], {}).get('DATA.Type') == CONVERSATION:
                seen.setdefault(rec['ParentDIAL'], None)
        return list(seen)

    def build(self, quest: dict, quest_fid: int, topic_ids: dict, form_map: dict) -> tuple:
        """(DLBR record, [topic blobs]) of `quest`'s topics `topic_ids` ({FNV DIAL: FO4 FormID}, not empty).

        `form_map` maps the FNV forms conditions name to FO4 ones.
        """
        branch, blobs = self.builder.new_id(f'DLBR {quest["FormID"]}'), []
        for dial, fid in topic_ids.items():
            lines = [rec for rec in self.infos[quest['FormID'].upper()] if rec['ParentDIAL'] == dial]
            infos = [i for i in (self.info(rec, form_map) for rec in lines) if i]
            record = R.pack_dial(fid, f'FNV_{self.dials[dial]["EditorID"]}', quest_fid, R.TOPIC_CUSTOM, len(infos),
                                 branch)
            blobs.append(pack_topic(record, fid, infos))
        dlbr = R.pack_dlbr(branch, f'FNV_{quest["EditorID"]}Branch', quest_fid, next(iter(topic_ids.values())))
        return dlbr, blobs

    def info(self, rec: dict, form_map: dict, scene: tuple = (0, ''), flags: int = 0, extra: bytes = b'') -> bytes:
        """One FNV line as an FO4 INFO; b'' when a condition cannot convert.

        `scene` is (scene, phase) the line starts; `flags` are ENAM flags added to its Say Once; `extra` CTDAs
        are added to its conditions. A part of a split line (conversation.part) after the first has no
        conditions or Say Once; the first part runs the Begin fragment, the last the End one. The part that opens
        barter ends the conversation scene, as vanilla's vendor lines do, so the menu does not stay behind it.
        """
        first, last = rec.get(PART, 1) == 1, rec.get(PART, 1) == rec.get(PARTS, 1)
        conditions = conditions_of(rec, form_map, self.script_vars) if first else b''
        if conditions is None:
            self.builder.counts[f'line left out (condition: {blocker(rec, form_map, self.script_vars)})'] += 1
            return b''
        fid = self.builder.new_id(f'INFO {rec["FormID"]} {rec.get(PART, 1)}')
        name = f'{FRAGMENT_PREFIX}{rec["FormID"].upper()}'
        scripts, vmad = self.builder.scripts, b''
        if scripts.dir and (scripts.dir / f'{name}.psc').exists() and (first or last):
            vmad = info_fragments(name, scripts.properties(name), begin='Fragment_1' if first else None,
                                  end='Fragment_0' if last else None)
            scripts.used.append(name)
        lines = [rec[f'Response[{i}].ResponseText'] for i in range(int(rec.get('ResponseCount', 0) or 0))]
        flags |= R.INFO_SAY_ONCE if first and int(rec.get('DATA.Flags', 0)) & SAY_ONCE else 0
        flags |= R.INFO_END_SCENE if opens_barter(rec, first, last) else 0
        self.voiced.append((fid, rec))
        self.builder.counts['INFO'] += 1
        return R.pack_info(fid, flags, tuple(lines) or ('...',), conditions + extra, scene=scene[0], phase=scene[1],
                           phase_index=scene[2] if len(scene) > 2 else 0,
                           notes=f'FNV {rec["FormID"]}', vmad=vmad, idle=line_idle(rec['FormID']) or 0)


def actor_values(helper_index: int) -> dict:
    """{('av', FNV actor value index): FO4 actor value} for a form map; one FO4 lacks is left out."""
    out = {}
    for index in range(len(C.FNV_AV_NAMES)):
        fid = actor_value_form(C.fnv_av_name(index), helper_index)
        if fid is not None:
            out[('av', index)] = fid
    return out


def _script_vars(export_dir: Path) -> dict:
    """{FNV quest or actor reference FormID: (its converted script, {variable index: name})}, for
    GetQuestVariable and GetScriptVariable."""
    scripts = {}
    for rec in export_records(export_dir, 'SCPT'):
        names, i = {}, 0
        while f'Variable[{i}].Index' in rec:
            names[int(rec[f'Variable[{i}].Index'])] = rec[f'Variable[{i}].Name']
            i += 1
        scripts[rec['FormID'].upper()] = (papyrus_script_name(rec.get('EditorID', ''), SCRIPT_PREFIX), names)
    bases = {r['FormID'].upper(): r.get('SCRI', '').upper() for r in export_records(export_dir, 'NPC_')}
    out = {int(q['FormID'], 16): scripts.get(q.get('SCRI', '').upper(), ('', {}))
           for q in export_records(export_dir, 'QUST')}
    for ref in export_records(export_dir, 'ACHR'):
        script = scripts.get(bases.get(ref.get('NAME', '').upper(), ''))
        if script:
            out[int(ref['FormID'], 16)] = script
    return out


def _unmapped(cond: dict, form_map: dict) -> bool:
    """True when a condition names an FNV form or global `form_map` lacks."""
    slots = C.FNV.form_slots.get(C.FNV.index(cond['func']), set())
    return C.fo4_value(cond, form_map) is None or any(
        s in slots and p not in form_map for s, p in ((1, cond['p1']), (2, cond['p2'])))


def _fo4_condition(cond: dict, form_map: dict, script_vars: dict) -> 'tuple | None':
    """(FO4 function, param 1, param 2, CIS1 text, CIS2 text) of an FNV condition; None when it cannot convert.

    GetQuestVariable and GetScriptVariable read the converted property
    (GetVMQuestVariable, GetVMScriptVariable) `script_vars` names ({FNV quest
    or reference: (script, {index: name})}); an objective test reads its
    mirror global, `form_map[(quest, index, state)]`; an actor value param
    is `form_map[('av', index)]` (actor_values()), None without one.
    """
    func, state = cond['func'], OBJECTIVE_FUNCS.get(C.FNV.index(cond['func']))
    if C.fo4_value(cond, form_map) is None:
        return None
    if func in (QUEST_VARIABLE, SCRIPT_VARIABLE):
        script, names = script_vars.get(cond['p1'], ('', {}))
        variable = names.get(cond['p2'])
        if variable is None or cond['p1'] not in form_map:
            return None
        if func == SCRIPT_VARIABLE:
            return C.FO4.index(VM_SCRIPT_VARIABLE), 0, 0, script, f'::{variable}_var'
        return C.FO4.index(VM_QUEST_VARIABLE), form_map[cond['p1']], 0, '', f'::{variable}_var'
    if state:
        glob = form_map.get((cond['p1'], cond['p2'], state))
        return (C.FO4.index(GLOBAL_VALUE), glob, 0, '', '') if glob else None
    index = C.FO4.index(C.RENAMED.get(func, func))
    if index < 0 or _unmapped(cond, form_map):
        return None
    avs = C.FNV.av_slots.get(C.FNV.index(func), set())
    params = [form_map.get(('av', cond[f'p{s}'])) if s in avs else form_map.get(cond[f'p{s}'], cond[f'p{s}'])
              for s in (1, 2)]
    return None if None in params else (index, *params, '', '')


def opens_barter(rec: dict, first: bool, last: bool) -> bool:
    """Whether this part of FNV line `rec` runs a script opening barter.
    See: docs/fork/fo4_pipeline.md#npcs
    """
    scripts = (rec.get('ResultScript') if first else '', rec.get('ResultScriptEnd') if last else '')
    return any(BARTER in (text or '').lower() for text in scripts)


def blocker(rec: dict, form_map: dict, script_vars: dict) -> str:
    """The function of an FNV record's first condition that cannot convert, '(global)' marking a global test."""
    i = 0
    while f'Condition[{i}].Raw' in rec:
        cond = C.parse(rec[f'Condition[{i}].Raw'])
        i += 1
        if _fo4_condition(cond, form_map, script_vars) is None:
            return cond['func'] + (' (global)' if cond['op_flags'] & C.USE_GLOBAL else '')
    return ''


def conditions_of(rec: dict, form_map: dict, script_vars: dict, swap: bool = False) -> 'bytes | None':
    """An FNV record's conditions as FO4 CTDAs (and CIS1/CIS2s); None when one cannot convert.

    GetQuestVariable and GetScriptVariable become GetVMQuestVariable and
    GetVMScriptVariable (run on the reference) on the name `script_vars`
    gives ({FNV quest or reference: (script, {index: name})}; `::<name>_var`,
    the converted property's backing variable). `swap` flips Subject and
    Target, for a player line.
    """
    out, i = b'', 0
    while f'Condition[{i}].Raw' in rec:
        cond = C.parse(rec[f'Condition[{i}].Raw'])
        i += 1
        fo4 = _fo4_condition(cond, form_map, script_vars)
        if fo4 is None:
            return None
        func, p1, p2, cis1, cis2 = fo4
        run_on, ref = (R.RUN_REFERENCE, form_map[cond['p1']]) if cis1 else C.run_on_of(cond, swap, form_map)
        flag, value = C.fo4_value(cond, form_map)
        out += R.pack_ctda(cond['op_flags'] & (COMPARE | OR) | flag, value, func, p1, p2, run_on, ref)
        out += (R.pack_cis1(cis1) if cis1 else b'') + (R.pack_cis2(cis2) if cis2 else b'')
    return out
