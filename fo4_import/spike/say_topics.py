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
from fo4_import.spike.conditions import raws
from fo4_import.spike.cell_families import in_families
from fo4_import.spike import records as R
from fo4_import.helpers_plugin import actor_value_form, form_id
from fo4_import.spike.readiness import LINE, LINE_LEFT_OUT
from fo4_import.spike.region_watch import REGION_KEY
from fo4_import.spike.say_once import SayOnce
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS, translated
from fo4_import.spike.reputation import KARMA_KEY, SLOT_KEY as REPUTATION_KEY
from tes5_import.record_types.reputation_falloutnv import KARMA_AV
from fo4_import.pipeline.export_index import Layered, export_masters, export_records, master_records, own_records
from script_convert.constants import FALLOUT4_HELPER_SAY_TARGET_KEYWORD, papyrus_script_name, safe_property_name
from fo4_import.spike.script import prefix
from tes5_import.base.conditions_falloutnv import OBJECTIVE_FUNCS

#: FNV DIAL type of the topics scripts Say: Conversation; of player topics (Topic).
CONVERSATION, TOPIC_TYPE = '1', '0'
#: FNV's GREETING topic: the greeting scene says it (conversation.greeting), never a quest's scripted topic.
GREETING = '000000C8'
#: FNV's GOODBYE topic: the speaker's line when the player leaves a talk (conversation's [Leave] answer).
GOODBYE_TOPIC = '000000D4'
#: A converted Say: TES4Polyfill.SayWhenFree(speaker, Topic, target).
SAY_FREE = re.compile(r'SayWhenFree\([^,]+,\s*(\w+)\s*,')
#: A converted Say GREETING by a named reference: the reference.
SAY_GREETING = re.compile(r'SayWhenFree\((\w+),\s*greeting\s*,', re.I)
#: Record key, FO4 EditorID and script property of the topic a script's Say GREETING plays (said_greeting).
SAID_GREETING_KEY, SAID_GREETING_EDID, SAID_GREETING_PROPERTY = 'said GREETING', 'FNV_GREETING_Said', 'GREETING'
#: FNV topics the engine plays itself (HELLO, GOODBYE, the barks) -> the FO4 topic kind its engine plays the same way.
ENGINE_TOPICS = {'000000D2': R.TOPIC_HELLO, GOODBYE_TOPIC: R.TOPIC_GOODBYE, **ENGINE_BARKS}
#: FNV INFO key of the line before it in its topic: a DLC inserting lines rewrites it on the master's.
ORDER = 'PNAM.PrevInfo'
#: FNV INFO DATA flag Say Once.
SAY_ONCE = 0x04
#: The script a line whose speaker idle loops forever carries: the loop stops when the speaker's package changes.
LOOP_SCRIPT = 'F3NV_LoopIdle'
#: The script a line carries whose speaker idle replaces a held one (Idles.switch), its idle and bridge properties.
SWITCH_SCRIPT, SWITCH_IDLE, SWITCH_BRIDGE = 'F3NV_SwitchIdle', 'Played', 'Bridge'
#: The script on a line's last part whose speaker plays a counted Special Idle gesture (Idles.gestures): it ends there.
GESTURE_SCRIPT = 'F3NV_GestureIdle'
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
#: FNV tests read as the subject's helper actor value (fo4_pipeline.md#talked-to-pc, #crime-counts, #disposition).
HELPER_AV_TESTS = {'GetTalkedToPC': 'TalkedToPC', 'GetMajorCrimeCount': 'MajorCrimes',
                   'GetMinorCrimeCount': 'MinorCrimes', 'GetDisposition': 'Disposition'}
#: FNV GetDisposition; the parties its helper value is toward (the line's other party, the player).
DISPOSITION, TOWARD = 'GetDisposition', (0, C.PLAYER_REF)
#: FNV HasFriendDisposition, read as GetDisposition against GenericFriendlyDisposition (FO3 and FNV: 0004E613).
FRIENDLY, FRIEND_GLOBAL = 'HasFriendDisposition', 0x4E613
#: CTDA comparisons: at least, less than.
AT_LEAST, BELOW = 0x60, 0x80
#: FO4's test of a script effect's family keyword, for HasMagicEffect (fo4_pipeline.md#effect-tests).
EFFECT_KEYWORD = 'HasMagicEffectKeyword'
#: FNV actor value reads that read Karma as the karma global (FO3's MQ11 tests the base value).
KARMA_READS = ('GetActorValue', 'GetBaseActorValue')
#: FNV PlayerInRegion, read as the region's watch global when watched (region_watch; fo4_regions.md#built).
IN_REGION = 'PlayerInRegion'
#: FNV IsHardcore, read as the Hardcore global (hardcore; fo4_hardcore.md#built): its form map key.
HARDCORE, HARDCORE_KEY = 'IsHardcore', ('hardcore', 'IsHardcore')
#: FNV GetCasinoWinningStage, read as the casino's level global (casino.records): its form map key head.
CASINO_STAGE, CASINO_KEY = 'GetCasinoWinningStage', 'casino level'
#: FNV reputation tests -> the reputation slot of their parameter 2's 0 (reputation.SLOT_KEY form map entries).
REPUTATION_FIRST_SLOT = {'GetReputation': 0, 'GetReputationThreshold': 2}


def script_texts(scripts_dir) -> list:
    """The converted scripts' texts in `scripts_dir` (a folder, a Layered one, or None)."""
    folders = [Path(f).joinpath(*scripts_dir.parts) for f in scripts_dir.folders] if isinstance(
        scripts_dir, Layered) else [Path(scripts_dir)] if scripts_dir else []
    return [path.read_text(encoding='utf-8', errors='replace') for folder in folders if folder.is_dir()
            for path in folder.glob('*.psc')]


def free_said(texts: list) -> set:
    """Topics (lower) the converted script `texts` say with SayWhenFree."""
    return {m.group(1).lower() for text in texts for m in SAY_FREE.finditer(text)}


def said_greetings(export_dir: Path, texts: list, greetings: list) -> list:
    """The `greetings` lines (FNV GREETING, in topic order) whose GetIsID names the base of a reference converted
    script `texts` Say GREETING with: the lines such a Say plays.
    See: docs/fork/fo4_pipeline.md#said-greeting
    """
    names = {m.group(1).lower() for text in texts for m in SAY_GREETING.finditer(text)}
    bases = {int(r['NAME'], 16) for sig in ('REFR', 'ACHR', 'ACRE') for r in export_records(export_dir, sig)
             if (r.get('EditorID') or '').lower() in names}
    return [rec for rec in greetings if any(c['func'] == 'GetIsID' and c['p1'] in bases and c['value'] == 1
                                            and not c['op_flags'] & COMPARE for c in parsed(rec))]


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
        self.silent, self.outside, self.links, self.checks, self.left = [], [], [], [], set()
        self.dials = {r['FormID']: r for r in export_records(export_dir, 'DIAL')}
        quests = {q['FormID'].upper(): raws(q) for q in export_records(export_dir, 'QUST')}
        self.infos, own, by_id, self.by_topic = {}, dlc_lines(export_dir), {}, {}
        for rec in export_records(export_dir, 'INFO'):
            if own is not None and rec['FormID'].upper() not in own:
                self.outside.append(rec)
                continue
            quest = rec.get('QSTI.Quest', '').upper()
            by_id[rec['FormID'].upper()] = line = with_quest(rec, quests.get(quest, []))
            self.infos.setdefault(quest, []).append(line)
            self.by_topic.setdefault(rec['ParentDIAL'].upper(), []).append(rec)
        self.once.reserve(fid for fid, rec in by_id.items() if int(rec.get('DATA.Flags', 0) or 0) & SAY_ONCE)
        self.engine = {**ENGINE_TOPICS, **named_barks(self.dials)}
        self.replies = replies(self.dials, export_records(export_dir, 'INFO'), self.engine)
        self.script_vars = builder.script_vars
        self.say_target = form_id(FALLOUT4_HELPER_SAY_TARGET_KEYWORD, builder.scripts.helper_index)
        texts = script_texts(builder.scripts.dir)
        self.said = script_said(self.dials, free_said(texts)) | status_barks(self.dials)
        self.borrowed = borrowed_lines(self.dials, self.said, by_id)
        self.greeting_said = said_greetings(export_dir, texts, [by_id[r['FormID'].upper()] for r in
                                                                self.by_topic.get(GREETING, ()) if r['FormID'].upper() in by_id])

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
            linked = None if dial in self.engine else self.say_target
            infos = [i for i in (self.info(rec, form_map, owner=quest_fid, place=f'{quest["FormID"]} topic {dial}',
                                           linked=linked) for rec in lines) if i]
            kind = self.engine.get(dial, R.TOPIC_CUSTOM)
            record = R.pack_dial(fid, f'FNV_{self.dials[dial]["EditorID"]}', quest_fid, kind, len(infos),
                                 0 if dial in self.engine else branch)
            blobs.append(pack_topic(record, fid, infos))
        dlbr = R.pack_dlbr(branch, f'FNV_{quest["EditorID"]}Branch', quest_fid, custom[0]) if custom else None
        return dlbr, blobs

    def said_greeting(self, quest_fid: int, form_map: dict) -> tuple:
        """(DLBR, topic blob) of the Custom topic a script's Say GREETING plays (copies of greeting_said), in
        generated quest `quest_fid`; (None, None) without such lines.
        See: docs/fork/fo4_pipeline.md#said-greeting
        """
        if not self.greeting_said:
            return None, None
        fid, branch = (self.builder.new_id(f'{sig} {SAID_GREETING_KEY}') for sig in ('DIAL', 'DLBR'))
        infos = [i for i in (self.info(rec, form_map, owner=quest_fid, place=SAID_GREETING_KEY, linked=self.say_target)
                             for rec in self.greeting_said) if i]
        record = R.pack_dial(fid, SAID_GREETING_EDID, quest_fid, R.TOPIC_CUSTOM, len(infos), branch)
        return R.pack_dlbr(branch, f'{SAID_GREETING_EDID}Branch', quest_fid, fid), pack_topic(record, fid, infos)

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
        scripts, name = self.builder.scripts, line_script(self.builder.scripts, rec)
        scripts.used += [s[0] for s in marked if s[0] not in scripts.used]
        if name and (first or last):
            scripts.used.append(name)
            return info_fragments(name, scripts.properties(name), begin='Fragment_1' if first else None,
                                  end='Fragment_0' if last else None, scripts=marked)
        return object_scripts(marked) if marked else b''

    def _idles(self, rec: dict, first: bool, last: bool) -> tuple:
        """([idle helper scripts], (speaker, listener) idles per response) of FNV line `rec` (part `first`,
        `last`): a held idle (counted or forever loop, Idles.holds) is released (LOOP_SCRIPT), a counted gesture
        (Idles.gestures) as the line ends (GESTURE_SCRIPT); an idle replacing a held one (Idles.switch) is played
        by SWITCH_SCRIPT through its bridge, not by the line.
        See: docs/fork/fo4_idles.md#idle-switch
        """
        idles, made = self.builder.idles, self.builder.idles.line(rec)
        switch, bridge = idles.switch(rec, self.by_topic.get(rec['ParentDIAL'].upper(), [])) if first else (0, 0)
        held = [(LOOP_SCRIPT, {}, {})] if first and idles.holds(rec) else []
        held += [(GESTURE_SCRIPT, {}, {})] if last and idles.gestures(rec) else []
        if not switch:
            return held, made
        return held + [(SWITCH_SCRIPT, {SWITCH_IDLE: switch, SWITCH_BRIDGE: bridge}, {})], ((0, made[0][1]),) + made[1:]

    def left_out(self, rec: dict, form_map: dict) -> bytes:
        """Count FNV line `rec` as left out, the first time, with the condition blocking it (blocker), for its quest;
        b''. A line tried for many speakers or scenes counts once."""
        if rec['FormID'].upper() not in self.left:
            self.left.add(rec['FormID'].upper())
            why = blocker(rec, form_map, self.script_vars)
            self.builder.counts[f'line left out (condition: {why})'] += 1
            self.builder.readiness.add(LINE_LEFT_OUT, rec.get('QSTI.Quest', ''),
                                       f'{rec["FormID"].upper()} (condition: {why})')
        return b''

    def info(self, rec: dict, form_map: dict, scene: tuple = (0, ''), flags: int = 0, extra: bytes = b'',
             target: 'int | None' = None, speaker: int = 0, owner: int = 0, place: str = '', helpers: tuple = (),
             prompt: str = '', forced: 'int | None' = None, linked: 'int | None' = None) -> bytes:
        """One FNV line as an FO4 INFO of quest `owner`; b'' when a condition cannot convert.

        `scene` (scene, phase) it starts, its speaker forced into alias `forced`; `flags` beside Say Once;
        `helpers` more scripts on its first part; `extra` CTDAs join its conditions, Target tests on alias
        `target` (else keyword `linked`'s linked reference); `speaker` its NPC; `place` names this copy;
        `prompt` its menu prompt. A split line's later parts have no conditions or Say Once.
        """
        first, last = rec.get(PART, 1) == 1, rec.get(PART, 1) == rec.get(PARTS, 1)
        conditions = conditions_of(rec, form_map, self.script_vars, target=target, linked=linked) if first else b''
        quest = rec.get('QSTI.Quest', '')
        if conditions is None:
            return self.left_out(rec, form_map)
        self.builder.readiness.add(LINE, quest, rec['FormID'].upper())
        line = f'INFO {rec["FormID"]} {rec.get(PART, 1)}' + (f' via {rec[SHARED]}' if rec.get(SHARED) else '')
        fid = self.builder.new_id(line, key=f'{line} at {place}' if place else None)
        once = first and int(rec.get('DATA.Flags', 0)) & SAY_ONCE
        marked = [self.once.script(rec['FormID'])] if once and owner else []
        held, idles = self._idles(rec, first, last)
        vmad = self._vmad(rec, first, last, marked + held + list(helpers) * first)
        lines = [rec[f'Response[{i}].ResponseText'] for i in range(int(rec.get('ResponseCount', 0) or 0))]
        flags |= R.INFO_SAY_ONCE if once else 0
        flags |= R.INFO_END_SCENE if opens_barter(rec, first, last) else 0
        extra += self.once.unsaid([rec['FormID']]) if marked else b''
        self.voiced.append((fid, rec))
        self.builder.counts['INFO'] += 1
        return R.pack_info(fid, flags, tuple(lines) or (R.SILENT_LINE,), conditions + extra, scene=scene[0], phase=scene[1],
                           phase_index=scene[2] if len(scene) > 2 else 0, stages=(R.NO_STAGE, R.NO_STAGE),
                           notes=f'FNV {rec["FormID"]}', vmad=vmad, idles=idles,
                           speaker=speaker, prompt=prompt, forced_alias=forced)


def line_script(scripts, rec: dict) -> 'str | None':
    """FNV line `rec`'s converted result script (TIF__<FormID>); None when it has none."""
    name = f'{prefix("TIF__")}{rec["FormID"].upper()}'
    return name if scripts.dir and (scripts.dir / f'{name}.psc').exists() else None


def actor_values(helper_index: int) -> dict:
    """{('av', FNV actor value index): FO4 actor value} for a form map; one FO4 lacks is left out."""
    out = {('av', name): actor_value_form(name, helper_index) for name in HELPER_AV_TESTS.values()}
    for index in range(len(C.FNV_AV_NAMES)):
        fid = actor_value_form(C.fnv_av_name(index), helper_index)
        if fid is not None:
            out[('av', index)] = fid
    return out


def script_vars(export_dir: Path) -> dict:
    """{FNV quest or placed reference FormID: (its converted script, {variable index: its converted name})}, for
    GetQuestVariable and GetScriptVariable."""
    scripts = {}
    for rec in export_records(export_dir, 'SCPT'):
        names, i = {}, 0
        while f'Variable[{i}].Index' in rec:
            names[int(rec[f'Variable[{i}].Index'])] = safe_property_name(rec[f'Variable[{i}].Name'], fallout4=True)
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
    a helper actor value (HELPER_AV_TESTS), karma, a casino's level, an objective (`state`) or reputation global,
    the form None when the build lacks it;
    None for any other condition."""
    if func == C.HAS_EFFECT and (C.EFFECT, cond['p1']) in form_map:
        return C.FO4.index(EFFECT_KEYWORD), form_map[(C.EFFECT, cond['p1'])]
    helper = func in HELPER_AV_TESTS and (func != DISPOSITION or cond['p1'] in TOWARD)
    key = ((REGION_KEY, cond['p1']) if func == IN_REGION else ('av', HELPER_AV_TESTS[func]) if helper
           else HARDCORE_KEY if func == HARDCORE else (CASINO_KEY, cond['p1']) if func == CASINO_STAGE
           else KARMA_KEY if func in KARMA_READS and cond['p1'] == KARMA_AV else None)
    if key is not None and key in form_map:
        return C.FO4.index('GetValue' if func in HELPER_AV_TESTS else GLOBAL_VALUE), form_map[key]
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
    """An FNV record's conditions expanded, settled and translated; or None.
    See: docs/fork/fo4_pipeline.md#cell-families
    """
    conds = C.without_absent(C.talking_through(in_families(parsed(rec), form_map), form_map), form_map)
    return None if conds is None else translated([_as_disposition(c) for c in conds], form_map.get(TYPE_KEYWORDS), item)


def _as_disposition(cond: dict) -> dict:
    """HasFriendDisposition `cond` as GetDisposition at least (or below) GenericFriendlyDisposition when it tests
    one outcome; any other condition unchanged.
    See: docs/fork/fo4_pipeline.md#disposition
    """
    if cond['func'] != FRIENDLY or cond['op_flags'] & C.USE_GLOBAL:
        return cond
    friend = C.compare(cond, 1.0)
    if friend == C.compare(cond, 0.0):
        return cond
    op = (AT_LEAST if friend else BELOW) | C.USE_GLOBAL | cond['op_flags'] & OR
    return {**cond, 'func': DISPOSITION, 'p1': 0, 'op_flags': op, 'global': FRIEND_GLOBAL}


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


def _closed(conds: list) -> list:
    """Raw conditions `conds`, the last one's OR-with-next flag cleared."""
    return conds[:-1] + [f'{int(conds[-1][:2], 16) & ~OR:02x}{conds[-1][2:]}'] if conds else []


def parsed(rec: dict) -> list:
    """An FNV record's conditions, parsed, in order."""
    return [C.parse(raw) for raw in raws(rec)]


def conditions_under(rec: dict, prefix: str) -> dict:
    """`rec`'s conditions under `prefix` (`Item[2].`, `Button[1].`) as a record."""
    return {key[len(prefix):]: value for key, value in rec.items() if key.startswith(prefix + 'Condition[')}


def conditions_of(rec: dict, form_map: dict, script_vars: dict, swap: bool = False,
                  target: 'int | None' = None, item: bool = False, linked: 'int | None' = None,
                  reference: 'int | None' = None) -> 'bytes | None':
    """An FNV record's conditions as FO4 CTDAs (and CIS1/CIS2s); None when one cannot convert.

    Variables read the converted property `script_vars` names (`::<name>_var`).
    `swap` flips Subject and Target (a player line); Target tests run on
    quest alias `target`, else keyword `linked`'s linked reference, else
    `reference` (a package's target). Absent forms are settled first
    (conditions.without_absent); type tests are keyword tests, on a weapon when `item`.
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
        run_on, ref, param3 = _target_run_on(run_on, ref, target, linked, reference)
        flag, value = C.fo4_value(cond, form_map)
        out += R.pack_ctda(cond['op_flags'] & (COMPARE | OR) | flag, value, func, p1, p2, run_on, ref, param3)
        out += (R.pack_cis1(cis1) if cis1 else b'') + (R.pack_cis2(cis2) if cis2 else b'')
    return out


def _target_run_on(run_on: int, ref: int, target: 'int | None', linked: 'int | None',
                   reference: 'int | None') -> tuple:
    """(Run On, reference, parameter 3) of a test: a Target test on alias `target`, else on keyword `linked`,
    else on `reference`.
    See: docs/fork/fo4_pipeline.md#say-target
    See: docs/fork/fo4_pipeline.md#package-target
    """
    if run_on != R.RUN_TARGET:
        return run_on, ref, -1
    if target is not None:
        return R.RUN_QUEST_ALIAS, 0, target
    if linked is not None:
        return R.RUN_LINKED_REF, 0, linked
    if reference is not None:
        return R.RUN_REFERENCE, reference, -1
    return run_on, ref, -1
