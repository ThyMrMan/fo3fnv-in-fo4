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

from fo4_import.base.vmad import info_fragments, object_scripts
from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike.readiness import LINE, LINE_LEFT_OUT
from fo4_import.spike.say_once import SayOnce
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS, translated
from fo4_import.spike.reputation import KARMA_KEY, SLOT_KEY as REPUTATION_KEY
from tes5_import.record_types.reputation_falloutnv import KARMA_AV
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
#: FNV base types a script runs on when placed (SCRI), for GetScriptVariable on their references.
SCRIPTED_BASES = ('NPC_', 'CREA', 'ACTI', 'TACT', 'CONT', 'DOOR', 'FURN', 'MISC', 'BOOK', 'NOTE', 'TERM', 'LIGH',
                  'ARMO', 'WEAP', 'ALCH', 'AMMO', 'KEYM')
#: FNV reputation tests -> the reputation slot of their parameter 2's 0 (reputation.SLOT_KEY form map entries).
REPUTATION_FIRST_SLOT = {'GetReputation': 0, 'GetReputationThreshold': 2}


class SayTopics:
    """FO4 Custom topics for FNV quests' Conversation topics; `voiced` lists [(FO4 INFO, FNV INFO)], `silent`
    [(FO4 INFO, said by the player)] for the silent lines (voice.silent_jobs)."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV topics and lines, each line carrying its quest's dialogue conditions (with_quest); topics are
        written through `builder` (its script_vars() names)."""
        self.builder, self.voiced, self.once = builder, [], SayOnce(builder.writer)
        self.silent = []
        self.dials = {r['FormID']: r for r in export_records(export_dir, 'DIAL')}
        quests = {q['FormID'].upper(): raws(q) for q in export_records(export_dir, 'QUST')}
        self.infos = {}
        for rec in export_records(export_dir, 'INFO'):
            quest = rec.get('QSTI.Quest', '').upper()
            self.infos.setdefault(quest, []).append(with_quest(rec, quests.get(quest, [])))
        self.script_vars = builder.script_vars

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
            infos = [i for i in (self.info(rec, form_map, owner=quest_fid, place=f'{quest["FormID"]} topic {dial}')
                                 for rec in lines) if i]
            record = R.pack_dial(fid, f'FNV_{self.dials[dial]["EditorID"]}', quest_fid, R.TOPIC_CUSTOM, len(infos),
                                 branch)
            blobs.append(pack_topic(record, fid, infos))
        dlbr = R.pack_dlbr(branch, f'FNV_{quest["EditorID"]}Branch', quest_fid, next(iter(topic_ids.values())))
        return dlbr, blobs

    def _vmad(self, rec: dict, first: bool, last: bool, marked: list) -> bytes:
        """FNV line `rec`'s VMAD: the `marked` helper scripts (its Say Once marker), then its
        converted fragments (Begin on its first part, End on its last); b'' with neither."""
        scripts, name = self.builder.scripts, f'{FRAGMENT_PREFIX}{rec["FormID"].upper()}'
        scripts.used += [s[0] for s in marked if s[0] not in scripts.used]
        if scripts.dir and (scripts.dir / f'{name}.psc').exists() and (first or last):
            scripts.used.append(name)
            return info_fragments(name, scripts.properties(name), begin='Fragment_1' if first else None,
                                  end='Fragment_0' if last else None, scripts=marked)
        return object_scripts(marked) if marked else b''

    def info(self, rec: dict, form_map: dict, scene: tuple = (0, ''), flags: int = 0, extra: bytes = b'',
             target: 'int | None' = None, speaker: int = 0, owner: int = 0, place: str = '', helpers: tuple = ()) -> bytes:
        """One FNV line as an FO4 INFO of quest `owner`; b'' when a condition cannot convert.

        `scene` is (scene, phase) the line starts; `flags` ENAM flags beside Say Once (say_once marks it);
        `helpers` more scripts [(script, object props, value props)] on its first part;
        `extra` CTDAs join its conditions, Target tests on alias `target`; `speaker` its NPC; `place` names
        this copy (quest, step) for its FormID. A split line's later parts have no conditions or Say Once;
        the first runs the Begin fragment, the last the End one; the part opening barter ends the scene.
        """
        first, last = rec.get(PART, 1) == 1, rec.get(PART, 1) == rec.get(PARTS, 1)
        conditions = conditions_of(rec, form_map, self.script_vars, target=target) if first else b''
        quest = rec.get('QSTI.Quest', '')
        if conditions is None:
            why = blocker(rec, form_map, self.script_vars)
            self.builder.counts[f'line left out (condition: {why})'] += 1
            self.builder.readiness.add(LINE_LEFT_OUT, quest, f'{rec["FormID"].upper()} (condition: {why})')
            return b''
        self.builder.readiness.add(LINE, quest, rec['FormID'].upper())
        line = f'INFO {rec["FormID"]} {rec.get(PART, 1)}'
        fid = self.builder.new_id(line, key=f'{line} at {place}' if place else None)
        once = first and int(rec.get('DATA.Flags', 0)) & SAY_ONCE
        marked = [self.once.script(rec['FormID'])] if once and owner else []
        vmad = self._vmad(rec, first, last, marked + list(helpers) * first)
        lines = [rec[f'Response[{i}].ResponseText'] for i in range(int(rec.get('ResponseCount', 0) or 0))]
        flags |= R.INFO_SAY_ONCE if once else 0
        flags |= R.INFO_END_SCENE if opens_barter(rec, first, last) else 0
        extra += self.once.unsaid([rec['FormID']]) if marked else b''
        self.voiced.append((fid, rec))
        self.builder.counts['INFO'] += 1
        return R.pack_info(fid, flags, tuple(lines) or (R.SILENT_LINE,), conditions + extra, scene=scene[0], phase=scene[1],
                           phase_index=scene[2] if len(scene) > 2 else 0, stages=(R.NO_STAGE, R.NO_STAGE),
                           notes=f'FNV {rec["FormID"]}', vmad=vmad, idles=self.builder.idles.line(rec),
                           speaker=speaker)


def actor_values(helper_index: int) -> dict:
    """{('av', FNV actor value index): FO4 actor value} for a form map; one FO4 lacks is left out."""
    out = {}
    for index in range(len(C.FNV_AV_NAMES)):
        fid = actor_value_form(C.fnv_av_name(index), helper_index)
        if fid is not None:
            out[('av', index)] = fid
    return out


def script_vars(export_dir: Path) -> dict:
    """{FNV quest or placed reference FormID: (its converted script, {variable index: name})}, for
    GetQuestVariable and GetScriptVariable."""
    scripts = {}
    for rec in export_records(export_dir, 'SCPT'):
        names, i = {}, 0
        while f'Variable[{i}].Index' in rec:
            names[int(rec[f'Variable[{i}].Index'])] = rec[f'Variable[{i}].Name']
            i += 1
        scripts[rec['FormID'].upper()] = (papyrus_script_name(rec.get('EditorID', ''), SCRIPT_PREFIX), names)
    bases = {r['FormID'].upper(): r['SCRI'].upper() for sig in SCRIPTED_BASES for r in export_records(export_dir, sig)
             if r.get('SCRI')}
    out = {int(q['FormID'], 16): scripts.get(q.get('SCRI', '').upper(), ('', {}))
           for q in export_records(export_dir, 'QUST')}
    for ref in (r for sig in ('ACHR', 'ACRE', 'REFR') for r in export_records(export_dir, sig)):
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
    `script_vars` names ({quest or ref: (script, {index: name})}), or a
    mirror global: `form_map[('qvar', quest, index)]` for a mirrored
    variable, `form_map[(quest, index, state)]` for an objective. An actor
    value param is `form_map[('av', index)]`, None without one.
    """
    func, state = cond['func'], OBJECTIVE_FUNCS.get(C.FNV.index(cond['func']))
    if C.fo4_value(cond, form_map) is None or C.unbuilt_reference(cond, form_map):
        return None
    if func == QUEST_VARIABLE and ('qvar', cond['p1'], cond['p2']) in form_map:
        return C.FO4.index(GLOBAL_VALUE), form_map[('qvar', cond['p1'], cond['p2'])], 0, '', ''
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
    if func == 'GetActorValue' and cond['p1'] == KARMA_AV and KARMA_KEY in form_map:
        return C.FO4.index(GLOBAL_VALUE), form_map[KARMA_KEY], 0, '', ''
    if func in REPUTATION_FIRST_SLOT:
        glob = form_map.get((REPUTATION_KEY, cond['p1'], REPUTATION_FIRST_SLOT[func] + cond['p2']))
        return (C.FO4.index(GLOBAL_VALUE), glob, 0, '', '') if glob else None
    index = C.FO4.index(C.RENAMED.get(func, func))
    if index < 0 or _unmapped(cond, form_map):
        return None
    avs = C.FNV.av_slots.get(C.FNV.index(func), set())
    forms = C.FNV.form_slots.get(C.FNV.index(func), set())
    params = [form_map.get(('av', cond[f'p{s}'])) if s in avs
              else form_map.get(cond[f'p{s}'], cond[f'p{s}']) if s in forms else cond[f'p{s}'] for s in (1, 2)]
    return None if None in params else (index, *params, '', '')


def opens_barter(rec: dict, first: bool, last: bool) -> bool:
    """Whether this part of FNV line `rec` runs a script opening barter.
    See: docs/fork/fo4_pipeline.md#npcs
    """
    scripts = (rec.get('ResultScript') if first else '', rec.get('ResultScriptEnd') if last else '')
    return any(BARTER in (text or '').lower() for text in scripts)


def blocker(rec: dict, form_map: dict, script_vars: dict) -> str:
    """The function of an FNV record's first condition that cannot convert, '(global)' marking a global test; for
    one never true in this build (conditions.without_absent), the first form it lacks."""
    conds = _settled(rec, form_map)
    if conds is None:
        first = next((c['func'] for c in parsed(rec) if C.absent(c, form_map) is False), '')
        return f'{first}: never true in this build'
    for cond in conds:
        if _fo4_condition(cond, form_map, script_vars) is None:
            return cond['func'] + (' (global)' if cond['op_flags'] & C.USE_GLOBAL else '')
    return ''


def _settled(rec: dict, form_map: dict, item: bool = False) -> 'list | None':
    """An FNV record's conditions settled (without_absent), translated; or None."""
    conds = C.without_absent(parsed(rec), form_map)
    return None if conds is None else translated(conds, form_map.get(TYPE_KEYWORDS), item)


def with_quest(rec: dict, quest: list) -> dict:
    """FNV line `rec`, or a copy whose conditions also AND in its quest's dialogue conditions `quest` (raw hex).
    See: docs/fork/fo4_pipeline.md#dialogue-conditions
    """
    return with_conditions(rec, _closed(raws(rec)) + _closed(quest)) if quest else rec


def settled_on(rec: dict, known: dict) -> 'dict | None':
    """FNV record `rec` with its tests of one speaker's fixed facts `known` (conditions.speaker_settle) settled, OR
    flags redone; None when its conditions never pass for that speaker."""
    kept = C.simplify([{**C.parse(raw), 'raw': raw} for raw in raws(rec)], C.speaker_settle(known))
    if kept is None:
        return None
    return with_conditions(rec, [f'{int(c["raw"][:2], 16) & ~OR | (OR if i < len(g) - 1 else 0):02x}{c["raw"][2:]}'
                                 for g in kept for i, c in enumerate(g)])


def with_conditions(rec: dict, conds: list) -> dict:
    """A copy of FNV record `rec` whose conditions are `conds` (raw hex)."""
    out = {k: v for k, v in rec.items() if not k.startswith('Condition[')}
    return {**out, **{f'Condition[{i}].Raw': raw for i, raw in enumerate(conds)}, 'ConditionCount': str(len(conds))}


def raws(rec: dict) -> list:
    """An FNV record's top-level conditions, raw hex, in order."""
    return [rec[f'Condition[{i}].Raw'] for i in range(_count(rec))]


def _closed(conds: list) -> list:
    """Raw conditions `conds`, the last one's OR-with-next flag cleared."""
    return conds[:-1] + [f'{int(conds[-1][:2], 16) & ~OR:02x}{conds[-1][2:]}'] if conds else []


def parsed(rec: dict) -> list:
    """An FNV record's conditions, parsed, in order."""
    return [C.parse(raw) for raw in raws(rec)]


def _count(rec: dict) -> int:
    """How many Condition[i] an FNV record has."""
    i = 0
    while f'Condition[{i}].Raw' in rec:
        i += 1
    return i


def conditions_of(rec: dict, form_map: dict, script_vars: dict, swap: bool = False,
                  target: 'int | None' = None, item: bool = False) -> 'bytes | None':
    """An FNV record's conditions as FO4 CTDAs (and CIS1/CIS2s); None when one cannot convert.

    Quest and script variables read the converted property `script_vars`
    names ({quest or reference: (script, {index: name})}, `::<name>_var`).
    `swap` flips Subject and Target (a player line); Target tests run on
    quest alias `target`. Tests of forms the build lacks are settled first
    (conditions.without_absent); type tests are keyword tests, a weapon
    subject when `item`.
    """
    conds = _settled(rec, form_map, item)
    if conds is None:
        return None
    out = b''
    for cond in conds:
        fo4 = _fo4_condition(cond, form_map, script_vars)
        if fo4 is None:
            return None
        func, p1, p2, cis1, cis2 = fo4
        run_on, ref = (R.RUN_REFERENCE, form_map[cond['p1']]) if cis1 else C.run_on_of(cond, swap, form_map)
        alias = target if run_on == R.RUN_TARGET and target is not None else -1
        run_on, ref = (R.RUN_QUEST_ALIAS, 0) if alias >= 0 else (run_on, ref)
        flag, value = C.fo4_value(cond, form_map)
        out += R.pack_ctda(cond['op_flags'] & (COMPARE | OR) | flag, value, func, p1, p2, run_on, ref, alias)
        out += (R.pack_cis1(cis1) if cis1 else b'') + (R.pack_cis2(cis2) if cis2 else b'')
    return out
