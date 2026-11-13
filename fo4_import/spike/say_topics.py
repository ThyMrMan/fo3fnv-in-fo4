"""An FNV quest's scripted lines as FO4 Custom topics, for the cell spike.

FNV's Say/SayTo plays a topic's first line whose conditions pass, and Say
Once lines step through a chain. FO4's Say does the same with a Custom topic
(DATA 0, SNAM CUST) in a branch of its quest, as vanilla's MS09Branch. The
quest's Conversation-type topics (FNV DIAL type 1) become such topics, but
HELLO and GOODBYE, which FNV's engine plays itself, become the quest's FO4
Hello and Goodbye topics, which FO4's engine plays the same way, as its
other engine topics (Attack, AlertIdle, ...) become the quest's FO4 bark
topics (barks.FNV_BARKS); each
line keeps its responses, Say Once flag, conditions (forms through the cell;
GetQuestVariable as GetVMQuestVariable on the converted property) and its
converted result fragments. Lines with a condition that cannot convert are
left out and counted.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import re
from pathlib import Path

from fo4_import.base.vmad import info_fragments, object_scripts
from fo4_import.base.writer import pack_topic
from fo4_import.spike.barks import ENGINE_BARKS, named_barks, replies
from fo4_import.spike.companion_barks import status_barks
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike.readiness import LINE, LINE_LEFT_OUT
from fo4_import.spike.region_watch import REGION_KEY
from fo4_import.spike.say_once import SayOnce
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS, translated
from fo4_import.spike.reputation import KARMA_KEY, SLOT_KEY as REPUTATION_KEY
from tes5_import.record_types.reputation_falloutnv import KARMA_AV
from fo4_import.pipeline.export_index import Layered, export_masters, export_records, master_records, own_records
from script_convert.constants import papyrus_script_name
from fo4_import.spike.script import prefix
from tes5_import.base.conditions_falloutnv import OBJECTIVE_FUNCS

#: FNV DIAL type of the topics scripts Say: Conversation; of player topics (Topic).
CONVERSATION, TOPIC_TYPE = '1', '0'
#: FNV's GREETING topic: the greeting scene says it (conversation.greeting), never a quest's scripted topic.
GREETING = '000000C8'
#: A converted Say: TES4Polyfill.SayWhenFree(speaker, Topic, target).
SAY_FREE = re.compile(r'SayWhenFree\([^,]+,\s*(\w+)\s*,')
#: FNV topics the engine plays itself (HELLO, GOODBYE, the barks) -> the FO4 topic kind its engine plays the same way.
ENGINE_TOPICS = {'000000D2': R.TOPIC_HELLO, '000000D4': R.TOPIC_GOODBYE, **ENGINE_BARKS}
#: FNV INFO key of the line before it in its topic: a DLC inserting lines rewrites it on the master's.
ORDER = 'PNAM.PrevInfo'
#: FNV INFO DATA flag Say Once.
SAY_ONCE = 0x04
#: Keys of a split line's part (conversation.part): its number and the line's count of parts.
PART, PARTS = '_part', '_parts'
#: Key of a shared info's copy naming the topic that borrows it (conversation.shared_lines).
SHARED = '_shared'
#: CTDA operator bits: the comparison, OR with the next, use a global as the value.
COMPARE, OR = 0xE0, 0x01
#: The FNV command opening a vendor's barter menu (lower case).
BARTER = 'showbartermenu'
#: FNV GetQuestVariable and FO4's GetVMQuestVariable, which names the Papyrus property in its CIS2.
QUEST_VARIABLE, VM_QUEST_VARIABLE = 'GetQuestVariable', 'GetVMQuestVariable'
#: FNV GetScriptVariable (reference, variable) and FO4's GetVMScriptVariable (run on it; CIS1 script, CIS2 variable).
SCRIPT_VARIABLE, VM_SCRIPT_VARIABLE = 'GetScriptVariable', 'GetVMScriptVariable'
#: FO4 has no objective condition; an objective test reads its mirror global (objectives_falloutnv).
GLOBAL_VALUE = 'GetGlobalValue'
#: FNV base types a script runs on when placed (SCRI), for GetScriptVariable on their references.
SCRIPTED_BASES = ('NPC_', 'CREA', 'ACTI', 'TACT', 'CONT', 'DOOR', 'FURN', 'MISC', 'BOOK', 'NOTE', 'TERM', 'LIGH',
                  'ARMO', 'WEAP', 'ALCH', 'AMMO', 'KEYM')
#: FNV GetTalkedToPC, read as the helper actor value TES4Polyfill.Greeted sets (fo4_pipeline.md#talked-to-pc).
TALKED, TALKED_AV, TALKED_KEY = 'GetTalkedToPC', 'TalkedToPC', ('av', 'TalkedToPC')
#: FNV PlayerInRegion, read as the region's watch global when watched (region_watch; fo4_regions.md#built).
IN_REGION = 'PlayerInRegion'
#: FNV IsHardcore, read as the Hardcore global (hardcore; fo4_hardcore.md#built): its form map key.
HARDCORE, HARDCORE_KEY = 'IsHardcore', ('hardcore', 'IsHardcore')
#: FNV GetCasinoWinningStage, read as the casino's level global (casino.records): its form map key head.
CASINO_STAGE, CASINO_KEY = 'GetCasinoWinningStage', 'casino level'
#: FNV reputation tests -> the reputation slot of their parameter 2's 0 (reputation.SLOT_KEY form map entries).
REPUTATION_FIRST_SLOT = {'GetReputation': 0, 'GetReputationThreshold': 2}


def free_said(scripts_dir) -> set:
    """Topic names (lower case) a converted script or package fragment in `scripts_dir` (a folder, a Layered one,
    or None) says with TES4Polyfill.SayWhenFree."""
    folders = [Path(f).joinpath(*scripts_dir.parts) for f in scripts_dir.folders] if isinstance(
        scripts_dir, Layered) else [Path(scripts_dir)] if scripts_dir else []
    return {m.group(1).lower() for folder in folders if folder.is_dir() for path in folder.glob('*.psc')
            for m in SAY_FREE.finditer(path.read_text(encoding='utf-8', errors='replace'))}


def masters_own(export_dir, sig: str) -> dict:
    """{FormID (upper): record} of type `sig` in the masters, the last winning."""
    return {r['FormID'].upper(): r for folder in export_masters(str(export_dir))
            for r in master_records(str(export_dir), folder, sig)}


def dlc_lines(export_dir, theirs: 'dict | None' = None) -> 'frozenset | None':
    """FormIDs (upper case) of the INFOs a plugin with masters (a DLC) holds that are its lines: its own, and its
    overrides changing a master's line (`theirs`, masters_own when None) beyond its place in the topic (PNAM);
    None for a plugin without masters.
    See: docs/fork/fo4_plugin_layout.md#dlc-dialogue
    """
    if not export_masters(str(export_dir)):
        return None
    theirs = masters_own(export_dir, 'INFO') if theirs is None else theirs
    return frozenset(r['FormID'].upper() for r in own_records(export_dir, 'INFO')
                     if r['FormID'].upper() not in theirs or _unordered(r) != _unordered(theirs[r['FormID'].upper()]))


def _unordered(rec: dict) -> dict:
    """FNV INFO `rec` without its place in the topic (ORDER)."""
    return {k: v for k, v in rec.items() if k != ORDER}


def script_said(dials: dict, said: set) -> set:
    """FNV topics `said` names (EditorID), not Conversation ones or GREETING.
    See: docs/fork/fo4_pipeline.md#said-topics
    """
    return {fid for fid, d in dials.items() if (d.get('EditorID') or '').lower() in said
            and d.get('DATA.Type') != CONVERSATION and fid.upper() != GREETING}


def borrowed_lines(dials: dict, said: set, lines: dict) -> dict:
    """{FNV quest: [copies]} of the shared infos (DIAL SharedInfo) each `said` topic borrows from another topic,
    of `lines` ({FNV INFO: record}): each copy a line of the borrowing topic, marked SHARED.
    See: docs/fork/fo4_pipeline.md#said-topics
    """
    out = {}
    for dial in sorted(said):
        rec = dials.get(dial, {})
        for i in range(int(rec.get('SharedInfoCount', 0) or 0)):
            line = lines.get(rec[f'SharedInfo[{i}].Info'].upper())
            if line and line['ParentDIAL'].upper() != dial.upper():
                copy = {**line, 'ParentDIAL': dial, SHARED: dial.upper()}
                out.setdefault(line.get('QSTI.Quest', '').upper(), []).append(copy)
    return out


class SayTopics:
    """FO4 Custom topics for FNV quests' Conversation topics; `voiced` lists [(FO4 INFO, FNV INFO)], `silent`
    [(FO4 INFO, said by the player)] for the silent lines (voice.silent_jobs)."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV topics and lines (a DLC's: only dlc_lines, its masters' kept apart in `outside`), each line
        carrying its quest's dialogue conditions (with_quest), their Say Once stages reserved; topics are written
        through `builder` (its script_vars() names). `links` [(option INFO, answer topic)] and `checks` [(answer
        INFO, FO4 actor value, number needed)] are the menus' links file rows (fo4_import.dialogue_menu)."""
        self.builder, self.voiced, self.once = builder, [], SayOnce(builder.writer)
        self.silent, self.outside, self.links, self.checks = [], [], [], []
        self.dials = {r['FormID']: r for r in export_records(export_dir, 'DIAL')}
        quests = {q['FormID'].upper(): raws(q) for q in export_records(export_dir, 'QUST')}
        self.infos, own, by_id = {}, dlc_lines(export_dir), {}
        for rec in export_records(export_dir, 'INFO'):
            if own is not None and rec['FormID'].upper() not in own:
                self.outside.append(rec)
                continue
            quest = rec.get('QSTI.Quest', '').upper()
            by_id[rec['FormID'].upper()] = line = with_quest(rec, quests.get(quest, []))
            self.infos.setdefault(quest, []).append(line)
        self.once.reserve(fid for fid, rec in by_id.items() if int(rec.get('DATA.Flags', 0) or 0) & SAY_ONCE)
        self.engine = {**ENGINE_TOPICS, **named_barks(self.dials)}
        self.replies = replies(self.dials, export_records(export_dir, 'INFO'), self.engine)
        self.script_vars = builder.script_vars
        self.said = script_said(self.dials, free_said(builder.scripts.dir)) | status_barks(self.dials)
        self.borrowed = borrowed_lines(self.dials, self.said, by_id)

    def topics(self, quest: dict) -> list:
        """FNV FormIDs of `quest`'s Conversation topics, engine topics (self.engine), the topics a reply of its
        answers (barks.replies) and the topics a script says (script_said), in first-line order."""
        seen = {}
        for rec in self._quest_lines(quest):
            dial = rec['ParentDIAL']
            if self.dials.get(dial, {}).get('DATA.Type') == CONVERSATION or dial in self.said or dial in self.engine:
                seen.setdefault(dial, None)
            seen.update(dict.fromkeys(t for t in self.replies.get(dial.upper(), ()) if t not in seen))
        return list(seen)

    def build(self, quest: dict, quest_fid: int, topic_ids: dict, form_map: dict) -> tuple:
        """(DLBR record, or None when every topic is the engine's, and [topic blobs]) of `quest`'s topics
        `topic_ids` ({FNV DIAL: FO4 FormID}, not empty); the engine's own (self.engine) sit in no branch, and hold
        the quest's replies to them after their own lines.

        `form_map` maps the FNV forms conditions name to FO4 ones.
        """
        branch, blobs = self.builder.new_id(f'DLBR {quest["FormID"]}'), []
        custom = [fid for dial, fid in topic_ids.items() if dial not in self.engine]
        for dial, fid in topic_ids.items():
            lines = self._lines(quest, dial)
            infos = [i for i in (self.info(rec, form_map, owner=quest_fid, place=f'{quest["FormID"]} topic {dial}')
                                 for rec in lines) if i]
            kind = self.engine.get(dial, R.TOPIC_CUSTOM)
            record = R.pack_dial(fid, f'FNV_{self.dials[dial]["EditorID"]}', quest_fid, kind, len(infos),
                                 0 if dial in self.engine else branch)
            blobs.append(pack_topic(record, fid, infos))
        dlbr = R.pack_dlbr(branch, f'FNV_{quest["EditorID"]}Branch', quest_fid, custom[0]) if custom else None
        return dlbr, blobs

    def _quest_lines(self, quest: dict) -> list:
        """`quest`'s own lines, then the copies its said topics borrow (borrowed_lines)."""
        key = quest['FormID'].upper()
        return self.infos.get(key, []) + self.borrowed.get(key, [])

    def _lines(self, quest: dict, dial: str) -> list:
        """`quest`'s lines of `dial`, then of the replies answering it (barks.replies)."""
        lines = self._quest_lines(quest)
        own = [rec for rec in lines if rec['ParentDIAL'] == dial]
        return own + [rec for rec in lines if dial in self.replies.get(rec['ParentDIAL'].upper(), ())]

    def _vmad(self, rec: dict, first: bool, last: bool, marked: list) -> bytes:
        """FNV line `rec`'s VMAD: the `marked` helper scripts (its Say Once marker), then its
        converted fragments (Begin on its first part, End on its last); b'' with neither."""
        scripts, name = self.builder.scripts, f'{prefix("TIF__")}{rec["FormID"].upper()}'
        scripts.used += [s[0] for s in marked if s[0] not in scripts.used]
        if scripts.dir and (scripts.dir / f'{name}.psc').exists() and (first or last):
            scripts.used.append(name)
            return info_fragments(name, scripts.properties(name), begin='Fragment_1' if first else None,
                                  end='Fragment_0' if last else None, scripts=marked)
        return object_scripts(marked) if marked else b''

    def left_out(self, rec: dict, form_map: dict) -> bytes:
        """Count FNV line `rec` as left out, with the condition blocking it (blocker), for its quest; b''."""
        why = blocker(rec, form_map, self.script_vars)
        self.builder.counts[f'line left out (condition: {why})'] += 1
        self.builder.readiness.add(LINE_LEFT_OUT, rec.get('QSTI.Quest', ''),
                                   f'{rec["FormID"].upper()} (condition: {why})')
        return b''

    def info(self, rec: dict, form_map: dict, scene: tuple = (0, ''), flags: int = 0, extra: bytes = b'',
             target: 'int | None' = None, speaker: int = 0, owner: int = 0, place: str = '', helpers: tuple = (),
             prompt: str = '', forced: 'int | None' = None) -> bytes:
        """One FNV line as an FO4 INFO of quest `owner`; b'' when a condition cannot convert.

        `scene` (scene, phase) it starts, its speaker forced into alias `forced`; `flags` beside Say Once;
        `helpers` more scripts on its first part; `extra` CTDAs join its conditions, Target tests on alias
        `target`; `speaker` its NPC; `place` names this copy for its FormID; `prompt` its menu prompt. A split
        line's later parts have no conditions or Say Once; the part opening barter ends the scene.
        """
        first, last = rec.get(PART, 1) == 1, rec.get(PART, 1) == rec.get(PARTS, 1)
        conditions = conditions_of(rec, form_map, self.script_vars, target=target) if first else b''
        quest = rec.get('QSTI.Quest', '')
        if conditions is None:
            return self.left_out(rec, form_map)
        self.builder.readiness.add(LINE, quest, rec['FormID'].upper())
        line = f'INFO {rec["FormID"]} {rec.get(PART, 1)}' + (f' via {rec[SHARED]}' if rec.get(SHARED) else '')
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
                           speaker=speaker, prompt=prompt, forced_alias=forced)


def actor_values(helper_index: int) -> dict:
    """{('av', FNV actor value index): FO4 actor value} for a form map; one FO4 lacks is left out."""
    out = {TALKED_KEY: actor_value_form(TALKED_AV, helper_index)}
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
        scripts[rec['FormID'].upper()] = (papyrus_script_name(rec.get('EditorID', ''), prefix()), names)
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
    return C.fo4_value(cond, form_map) is None or C.unmapped_form(cond, form_map)


def _form_value(func: str, cond: dict, form_map: dict, state) -> 'tuple | None':
    """(FO4 function, form) of an FNV condition the build answers from a form of its own: a region's watch global,
    the TalkedToPC value, karma, a casino's level, an objective (`state`) or reputation global, the form None when
    the build lacks it;
    None for any other condition."""
    key = ((REGION_KEY, cond['p1']) if func == IN_REGION else TALKED_KEY if func == TALKED
           else HARDCORE_KEY if func == HARDCORE else (CASINO_KEY, cond['p1']) if func == CASINO_STAGE
           else KARMA_KEY if func == 'GetActorValue' and cond['p1'] == KARMA_AV else None)
    if key is not None and key in form_map:
        return C.FO4.index('GetValue' if func == TALKED else GLOBAL_VALUE), form_map[key]
    if state:
        return C.FO4.index(GLOBAL_VALUE), form_map.get((cond['p1'], cond['p2'], state))
    if func in REPUTATION_FIRST_SLOT:
        slot = REPUTATION_FIRST_SLOT[func] + cond['p2']
        return C.FO4.index(GLOBAL_VALUE), form_map.get((REPUTATION_KEY, cond['p1'], slot))
    return None


def _fo4_condition(cond: dict, form_map: dict, script_vars: dict) -> 'tuple | None':
    """(FO4 function, param 1, param 2, CIS1 text, CIS2 text) of an FNV condition; None when it cannot convert.

    GetQuestVariable and GetScriptVariable read the converted property
    `script_vars` names ({quest or ref: (script, {index: name})}), or a
    mirror global: `form_map[('qvar', quest, index)]` for a mirrored
    variable, `form_map[(quest, index, state)]` for an objective. An actor
    value param is `form_map[('av', index)]`, None without one. A
    TOWARD_PLAYER function asks the player.
    """
    cond = {**cond, 'func': 'GetActorValue', 'p1': C.AS_VALUE[cond['func']]} if cond['func'] in C.AS_VALUE else cond
    func, state = cond['func'], OBJECTIVE_FUNCS.get(C.FNV.index(cond['func']))
    if C.fo4_value(cond, form_map) is None or C.unbuilt_reference(cond, form_map):
        return None
    if func in C.TOWARD_PLAYER:
        return C.FO4.index(C.TOWARD_PLAYER[func]), C.PLAYER_REF, 0, '', ''
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
    found = _form_value(func, cond, form_map, state)
    if found:
        return (*found, 0, '', '') if found[1] else None
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
        first = next((c['func'] for c in C.talking_through(parsed(rec), form_map) if C.absent(c, form_map) is False),
                     '')
        return f'{first}: never true in this build'
    for cond in conds:
        if _fo4_condition(cond, form_map, script_vars) is None:
            return cond['func'] + (' (global)' if cond['op_flags'] & C.USE_GLOBAL else '')
    return ''


def _settled(rec: dict, form_map: dict, item: bool = False) -> 'list | None':
    """An FNV record's conditions with talking activators read (talking_through), settled (without_absent),
    translated; or None."""
    conds = C.without_absent(C.talking_through(parsed(rec), form_map), form_map)
    return None if conds is None else translated(conds, form_map.get(TYPE_KEYWORDS), item)


def with_quest(rec: dict, quest: list) -> dict:
    """FNV line `rec`, or a copy whose conditions also AND in its quest's dialogue conditions `quest` (raw hex).
    See: docs/fork/fo4_pipeline.md#dialogue-conditions
    """
    return with_conditions(rec, _closed(raws(rec)) + _closed(quest)) if quest else rec


def settled_on(rec: dict, known: dict) -> 'dict | None':
    """FNV record `rec` with its tests of one speaker's fixed facts `known` (conditions.speaker_settle) settled, OR
    flags redone; None when its conditions never pass for that speaker."""
    return settled_by(rec, C.speaker_settle(known))


def never_true(rec: dict, form_map: dict) -> bool:
    """Whether FNV record `rec`'s conditions never pass in this build (they test forms it lacks: without_absent)."""
    return _settled(rec, form_map) is None


def settled_by(rec: dict, settle) -> 'dict | None':
    """FNV record `rec` with the tests `settle` fixes (True, False, or None to keep) settled, OR flags redone; None
    when its conditions never pass."""
    kept = C.simplify([{**C.parse(raw), 'raw': raw} for raw in raws(rec)], settle)
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


def conditions_under(rec: dict, prefix: str) -> dict:
    """`rec`'s conditions under `prefix` (`Item[2].`, `Button[1].`) as a record."""
    return {key[len(prefix):]: value for key, value in rec.items() if key.startswith(prefix + 'Condition[')}


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
