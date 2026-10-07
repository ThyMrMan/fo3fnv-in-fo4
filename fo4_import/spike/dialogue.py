"""Spike 1: FNV conversations as XDI scenes in an FO4 plugin, for any number of speakers.

    py -3.14 -m fo4_import.spike.dialogue --export <FalloutNV.esm export> --out <plugin.esp> [--data <Data>]

One quest with one optional, empty alias; every greeting line forces its
speaker into it (INFO ALFA, as vanilla DialogueGenericDoctors does) and starts
the 'Menu' scene, whose options are tested against that speaker. A topic's
NPC variants sit behind padding lines so XDI answers with the first that
passes; Random piles get a GetRandomPercent chain. Choices -> their own scene.
Added topics and said lines -> quest stages. Assumed state and everything
left out go to the report.

See: docs/fork/fo4_spikes.md#spike-1
"""

import argparse
from pathlib import Path

from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest, pack_topic
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike import script as script_spike
from fo4_import.spike import voice
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from tes5_import.base.tes5_reader import walk
from tes5_import.base.text_reader import parse_export_file

#: (label, FNV NPC_ or None for a faction-only speaker, FO4 stand-in base, position, rotation).
SPEAKERS = (
    ('DocMitchell', 0x104C0C, 0x12FCCB, (-1932.0, -1484.0, 0.0), (0.0, 0.0, 0.79)),
    ('DoctorBarrows', 0x0156F0, 0x09A680, (-1827.0, -1591.0, 0.0), (0.0, 0.0, 0.79)),
    ('RoboButler', None, 0x192356, (-2037.0, -1377.0, 0.0), (0.0, 0.0, 0.79)),
)
#: Speaker -> (FNV voice folder, stand-in's FO4 voice type). HD00's robot butler lines have no FNV recordings.
VOICES = {'DocMitchell': ('maleuniquedocmitchell', 'NPCMDocWeathers'),
          'DoctorBarrows': ('malegenericghoul', 'NPCFDoctorAmari'),
          'RoboButler': ('robotmisterhandy', 'MaleEvenToned')}
#: FNV faction -> FO4 faction the stand-in is in at rank >= 0 (HD00RoboButler -> REMerchantBarVendorFaction).
FACTIONS = {0x7F47B: 0x1B2C19}
#: The last option of every menu, standing in for FNV's Tab exit (XDI's menu swallows Tab).
LEAVE = '[Leave]'
GOODBYE_TOPIC = 0xD4
#: Topics whose lines come in whoever they name: GOODBYE, HD00Joke.
GENERIC_TOPICS = {GOODBYE_TOPIC, 0x7F463}
GREETING = 0xC8
#: Fallout4.esm QASmoke, a test cell with no precombines.
CELL_FO4 = 0x0001F7A9
XDI_KEYWORD = 0x01000000 | R.XDI_KEYWORD
#: State just after character creation, for quests the spike does not convert.
ASSUME = {
    ('GetQuestCompleted', 0x104C1C, 0): 1, ('GetQuestVariable', 0x104C1C, 13): 1,
    ('GetStage', 0x104C1C, 0): 200, ('GetObjectiveDisplayed', 0x104C1C, 40): 1,
    ('GetObjectiveCompleted', 0x104C1C, 40): 1, ('GetScriptVariable', 0x104C0F, 4): 0,
    ('GetQuestCompleted', 0x104EAE, 0): 0, ('GetObjectiveCompleted', 0x104EAE, 10): 0,
    ('GetObjectiveDisplayed', 0x15EC5B, 40): 0, ('GetObjectiveCompleted', 0x15EC5B, 40): 0,
    ('GetQuestVariable', 0x117AC4, 7): 0, ('GetQuestVariable', 0x7F47A, 4): 0,
}
#: Quests finished at that point: their lines never play (FNV only speaks lines of running quests).
STOPPED_QUESTS = {0x104C1C}
#: FNV forms with an FO4 twin at the same id: the player, caps.
SAME_IN_FO4 = (0x14, 0x0F)
#: FNV actor value names whose FO4 actor value is named differently.
AV_RENAMED = {'Rad Level': 'Rads'}
#: FNV skills: FO4 has none, so each becomes a plugin actor value.
FNV_SKILLS = range(32, 46)
FNV_VARIABLES = range(62, 72)
MASTERS = ['Fallout4.esm', 'XDI.esm', FALLOUT4_HELPER_PLUGIN]
HELPER_INDEX = MASTERS.index(FALLOUT4_HELPER_PLUGIN)
FO4_AVIF_DUMP = Path(__file__).resolve().parents[2] / 'references' / 'Fallout4.esm' / 'AVIF.txt'
TOP_LEVEL = 0x02
#: Conditions that pick the speaker; one naming nobody in the test world is false.
SPEAKER_TESTS = ('GetIsID', 'GetInFaction', 'GetIsVoiceType')
#: FNV INFO DATA flags.
GOODBYE, RANDOM, SAY_ONCE, RANDOM_END = 0x01, 0x02, 0x04, 0x20
#: CTDA comparison operator -> its negation.
_NEGATE = {0x00: 0x20, 0x20: 0x00, 0x40: 0xA0, 0xA0: 0x40, 0x60: 0x80, 0x80: 0x60}
_OP_LESS = 0x80


class Ids:
    """Sequential FormIDs in the plugin's own index (after MASTERS)."""

    def __init__(self):
        """Start at object id 0x800."""
        self.next = len(MASTERS) << 24 | 0x800

    def take(self) -> int:
        """The next FormID."""
        fid, self.next = self.next, self.next + 1
        return fid


def _int(rec: dict, key: str) -> int:
    """An int field of an export record, 0 when absent."""
    return int(rec.get(key, 0) or 0)


def _fids(rec: dict, key: str) -> list:
    """A Key[i] FormID list as ints."""
    return [int(rec[f'{key}[{i}]'], 16) for i in range(_int(rec, f'{key}Count'))]


def _conds(rec: dict) -> list:
    """An export record's conditions, parsed."""
    return [C.parse(rec[f'Condition[{i}].Raw']) for i in range(_int(rec, 'ConditionCount'))]


def _cond(func: str, op: int, value: float, p1: int = 0, p2: int = 0) -> dict:
    """A synthetic condition in parse()'s shape, run on the subject."""
    return {'op_flags': op, 'value': value, 'func': func, 'p1': p1, 'p2': p2, 'run_on': 0, 'ref': 0}


def _relevant(rec: dict) -> bool:
    """True when an INFO names a spike speaker (GetIsID, GetInFaction) or sits in a generic topic."""
    if int(rec['ParentDIAL'], 16) in GENERIC_TOPICS:
        return True
    npcs = {s[1] for s in SPEAKERS if s[1]}
    return any(c['value'] == 1.0 and ((c['func'] == 'GetIsID' and c['p1'] in npcs)
                                     or (c['func'] == 'GetInFaction' and c['p1'] in FACTIONS))
               for c in _conds(rec))


def speaker_gate(members: list) -> list:
    """One OR-group of the variants' speaker tests, so an option shows only to someone who can answer.

    Empty when a variant has no single speaker test (anyone may answer it).
    """
    tests = []
    for _, kept in members:
        found = [g[0] for g in kept if len(g) == 1 and g[0]['func'] in SPEAKER_TESTS
                 and g[0]['op_flags'] & 0xE0 == 0 and g[0]['value'] == 1.0]
        if not found:
            return []
        if found[0] not in tests:
            tests.append(found[0])
    return [[dict(t, op_flags=0) for t in tests]]


def random_chain(members: list) -> list:
    """Extra OR-groups per member: piles of Random INFOs get GetRandomPercent < 100/remaining.

    Evaluated in order, the first n-1 of a pile pass with 1/n, 1/(n-1)...
    so each is equally likely, as FNV picks one of a pile at random. A pile
    is chained per set of members with the same conditions (sir and madame
    variants), so each set keeps a last member with no roll that always answers.
    See: docs/fork/fo4_spikes.md#spike-3-fragments
    """
    extra, run = [[] for _ in members], []
    for i, (rec, _) in enumerate(members + [(None, None)]):
        flags = _int(rec, 'DATA.Flags') if rec else 0
        if rec and flags & RANDOM:
            run.append(i)
            if not flags & RANDOM_END:
                continue
        sets = {}
        for index in run:
            sets.setdefault(repr(members[index][1]), []).append(index)
        for same in sets.values():
            for k, index in enumerate(same[:-1]):
                extra[index] = [[_cond('GetRandomPercent', _OP_LESS, 100.0 / (len(same) - k))]]
        run = []
    return extra


def menu_records(take, scene: tuple, player: list, npc: list, keyword: int) -> tuple:
    """([topic blobs], SCEN) of an XDI menu scene: four player topics, the first holding `player`, and one NPC topic.

    `scene` is (FormID, EditorID, quest, speaker alias); `take` gives FormIDs.
    """
    fid, edid, quest, alias = scene
    p_ids, n_id, topics = [take() for _ in range(4)], take(), []
    for i, pid in enumerate(p_ids):
        infos = player if i == 0 else []
        topics.append(pack_topic(R.pack_dial(pid, f'{edid}_P{i}', quest, R.TOPIC_SCENE, len(infos)), pid, infos))
    topics.append(pack_topic(R.pack_dial(n_id, f'{edid}_N', quest, R.TOPIC_SCENE, len(npc)), n_id, npc))
    action = R.pack_player_dialogue(1, alias, tuple(p_ids), (n_id,))
    return topics, R.pack_scen(fid, edid, quest, alias, action, keyword)


class Spike:
    """Builds the plugin and its report from the speakers' FNV dialogue."""

    def __init__(self, export_dir: Path):
        """Index the speakers' INFOs by topic and every DIAL by FormID."""
        self.dials = {int(d['FormID'], 16): d for d in parse_export_file(str(export_dir / 'DIAL.txt'))}
        quests = parse_export_file(str(export_dir / 'QUST.txt'))
        self.quest_conds = {int(q['FormID'], 16): _conds(q) for q in quests}
        self.quest_stages = {q['EditorID']: [_int(q, f'Stage[{i}].Index') for i in range(_int(q, 'StageCount'))]
                             for q in quests if q.get('EditorID')}
        self.infos = {}
        for rec in parse_export_file(str(export_dir / 'INFO.txt')):
            if _relevant(rec):
                self.infos.setdefault(int(rec['ParentDIAL'], 16), []).append(rec)
        self.ids, self.report, self.stages, self.avs = Ids(), [], {}, {}
        self.quest, self.main = self.ids.take(), self.ids.take()
        self.fo4_avs = {r.get('EditorID'): int(r['FormID'], 16) for r in parse_export_file(str(FO4_AVIF_DUMP))}
        self.form_map = {**{s[1]: s[2] for s in SPEAKERS if s[1]}, **FACTIONS, **{f: f for f in SAME_IN_FO4}}
        self.scenes, self.topics, self.choice_scenes, self.scene_records = [], [], {}, []
        self.voiced, self.fragments, self.actor_ids, self.trace = [], None, [], ''

    def stage(self, key) -> int:
        """The quest stage for key (added topic or said line); made on first use."""
        if key not in self.stages:
            self.stages[key] = 10 * (len(self.stages) + 1)
        return self.stages[key]

    def av(self, index: int):
        """The FO4 actor value for an FNV actor value index: same-named vanilla, a helper plugin one, or None.

        A skill or variable's first use still takes the FormID the spike's own
        record for it once had, so the lines after it keep theirs.
        """
        name = C.FNV_AV_NAMES[index] if index < len(C.FNV_AV_NAMES) else ''
        fo4 = self.fo4_avs.get(AV_RENAMED.get(name, name.replace(' ', '')))
        if fo4 is not None or (index not in FNV_SKILLS and index not in FNV_VARIABLES):
            return fo4
        if index not in self.avs:
            self.ids.take()
            self.avs[index] = actor_value_form(name.replace(' ', ''), HELPER_INDEX)
        return self.avs[index]

    def unconvertible(self, cond: dict) -> bool:
        """True when a condition has no FO4 function, actor value or form to become."""
        if C.FO4.index(C.RENAMED.get(cond['func'], cond['func'])) < 0 or cond['op_flags'] & 0x04:
            return True
        if cond['func'] == 'GetActorValue':
            return self.av(cond['p1']) is None
        slots = C.FNV.form_slots.get(C.FNV.index(cond['func']), set())
        return any(s in slots and p not in self.form_map for s, p in ((1, cond['p1']), (2, cond['p2'])))

    def settle(self, cond: dict):
        """True/False when the test world fixes a condition, else None.

        Assumed quest state; a speaker test (GetIsID, GetInFaction,
        GetIsVoiceType) naming no spike speaker is false for all of them; a
        null form parameter matches nothing.
        """
        key = (cond['func'], cond['p1'], cond['p2'])
        if key in ASSUME:
            return C.compare(cond, ASSUME[key])
        if cond['func'] in SPEAKER_TESTS and cond['p1'] not in self.form_map:
            return C.compare(cond, 0)
        slots = C.FNV.form_slots.get(C.FNV.index(cond['func']), set())
        if any(s in slots and p == 0 for s, p in ((1, cond['p1']), (2, cond['p2']))):
            return C.compare(cond, 0)
        return None

    def kept(self, rec: dict):
        """The INFO's and its quest's OR-groups after settling, None if it can never pass or can't convert.

        FNV tests a line's quest dialogue conditions before the line's own.
        """
        if int(rec.get('QSTI.Quest', '0'), 16) in STOPPED_QUESTS:
            return None
        quest = int(rec.get('QSTI.Quest', '0'), 16)
        kept = C.simplify(_conds(rec) + self.quest_conds.get(quest, []), self.settle)
        if kept is None:
            return None
        bad = [c for g in kept for c in g if self.unconvertible(c)]
        if bad:
            self.report.append(f"INFO {rec['FormID']}: unconverted {bad[0]['func']}({bad[0]['p1']:X}) - line left out")
            return None
        return kept

    def known(self, dial_fid: int) -> list:
        """Condition groups that hide a non-top-level topic until its AddTopic has played."""
        if _int(self.dials[dial_fid], 'DATA.Flags') & TOP_LEVEL:
            return []
        return [[_cond('GetStageDone', 0, 1.0, self.quest, self.stage(('topic', dial_fid)))]]

    def prompt(self, rec: dict, dial_fid: int) -> str:
        """The player's line: the INFO's own prompt, else the topic name."""
        return rec.get('Prompt') or self.dials[dial_fid].get('FULL', '')

    def option_groups(self, dial_fid: int) -> list:
        """[(prompt, [(info, kept), ...])]: the topic's live INFOs grouped by prompt, in first-seen order.

        FNV shows a topic once, with the first passing INFO's prompt; INFOs
        sharing a prompt are one option however far apart they sit.
        """
        out = {}
        for rec in self.infos.get(dial_fid, []):
            kept = self.kept(rec)
            if kept is not None:
                out.setdefault(self.prompt(rec, dial_fid), []).append((rec, kept))
        return list(out.items())

    def exclusivity(self, earlier: list, where: str) -> list:
        """OR-groups that hold only when no earlier single-INFO prompt group could be chosen."""
        out = []
        for _, members in earlier:
            rec, kept = members[0]
            if len(members) > 1 or any(len(g) > 1 for g in kept):
                self.report.append(f'{where}: earlier prompt with OR/multi-INFO conditions not excluded')
                continue
            group = [dict(g[0], op_flags=_NEGATE[g[0]['op_flags'] & 0xE0]) for g in kept]
            if _int(rec, 'DATA.Flags') & SAY_ONCE:
                group.append(_cond('GetStageDone', 0, 1.0, self.quest, self.stage(('said', rec['FormID']))))
            if group:
                out.append(group)
        return out

    def npc_info(self, rec: dict, kept: list, home: int, forced_alias: bool = False) -> bytes:
        """A FNV INFO as the NPC's line: text, conditions, flags, its next scene and stages."""
        flags, choices, added = _int(rec, 'DATA.Flags'), _fids(rec, 'Choice'), _fids(rec, 'AddTopic')
        scene = 0 if flags & GOODBYE else (self.choice_scene(choices) if choices else home)
        if len(added) > 1:
            self.report.append(f"INFO {rec['FormID']}: {len(added)} AddTopics, only the first kept")
        said = ('said', rec['FormID'])
        begin = self.stages[said] if said in self.stages else R.NO_STAGE
        end = self.stage(('topic', added[0])) if added else R.NO_STAGE
        vmad = self.fragments.vmad(rec['FormID']) if self.fragments else b''
        if (rec.get('ResultScript') or rec.get('ResultScriptEnd')) and not vmad:
            self.report.append(f"INFO {rec['FormID']}: result script not converted")
        lines = [rec[f'Response[{i}].ResponseText'] for i in range(_int(rec, 'ResponseCount'))]
        enam = (R.INFO_SAY_ONCE if flags & SAY_ONCE else 0) | (R.INFO_END_SCENE if flags & GOODBYE else 0)
        fid = self.ids.take()
        self.voiced.append((fid, rec))
        return R.pack_info(fid, enam, tuple(lines) or ('...',),
                           C.convert(kept, self.form_map, self.av, False),
                           scene=scene, phase='Menu' if scene else '', stages=(begin, end),
                           notes=f"FNV {rec['FormID']}", forced_alias=0 if forced_alias else None, vmad=vmad)

    def plan_options(self, dial_fids: list, gated: bool, where: str) -> list:
        """[(prompt, members, player condition groups)] for a menu, in topic order."""
        options = []
        for dial_fid in dial_fids:
            groups = self.option_groups(dial_fid)
            for j, (text, members) in enumerate(groups):
                own = members[0][1] if len(members) == 1 else speaker_gate(members)
                if len(members) > 1 and not own:
                    self.report.append(f'{where}: "{text}" has {len(members)} variants, one for anyone; option ungated')
                known = self.known(dial_fid) if gated else []
                options.append((text, members, known + own + self.exclusivity(groups[:j], where)))
        return options

    def negate(self, groups: list, where: str) -> list:
        """OR-groups for NOT(groups): exact for one OR-group or all single conditions, else [] and a report."""
        def flip(c):
            return dict(c, op_flags=_NEGATE[c['op_flags'] & 0xE0])
        if len(groups) == 1:
            return [[flip(c)] for c in groups[0]]
        if all(len(g) == 1 for g in groups):
            return [[flip(g[0]) for g in groups]]
        self.report.append(f'{where}: Goodbye conditions too complex to negate; [Leave] shown beside it')
        return []

    def leave(self, options: list, where: str) -> tuple:
        """(player INFO, NPC INFO) for LEAVE: it ends the scene and hides while a GOODBYE-topic option shows."""
        hide = []
        for text, members, groups in options:
            if int(members[0][0]['ParentDIAL'], 16) == GOODBYE_TOPIC:
                hide += self.negate(groups, f'{where} "{text}"')
        conds = C.convert(hide, self.form_map, self.av, True)
        return (R.pack_info(self.ids.take(), 0, (LEAVE,), conds, prompt=LEAVE),
                R.pack_info(self.ids.take(), R.INFO_END_SCENE, ('...',), notes='FNV Tab exit'))

    def build_menu(self, edid: str, dial_fids: list, gated: bool, fid: int):
        """One XDI scene: four player topics (the first holds the options, then LEAVE) and one NPC topic."""
        options = self.plan_options(dial_fids, gated, edid)
        player, npc = [], []
        for text, members, groups in options:
            say_once = all(_int(rec, 'DATA.Flags') & SAY_ONCE for rec, _ in members)
            conds = C.convert(groups, self.form_map, self.av, True)
            player.append(R.pack_info(self.ids.take(), R.INFO_SAY_ONCE if say_once else 0, (text,), conds, prompt=text))
            player += [R.pack_info(self.ids.take()) for _ in members[1:]]
            npc += [self.npc_info(rec, kept + extra, self.main)
                    for (rec, kept), extra in zip(members, random_chain(members))]
        exit_player, exit_npc = self.leave(options, edid)
        player.append(exit_player)
        npc.append(exit_npc)
        self.scenes.append((fid, edid, [len(m) for _, m, _ in options], [t for t, _, _ in options]))
        topics, scene = menu_records(self.ids.take, (fid, edid, self.quest, 0), player, npc, XDI_KEYWORD)
        self.topics += topics
        self.scene_records.append(scene)

    def choice_scene(self, choices: list) -> int:
        """The scene listing one INFO's Choices, built on first use."""
        key = tuple(choices)
        if key not in self.choice_scenes:
            self.choice_scenes[key] = fid = self.ids.take()
            self.build_menu(f'FNVSpike_Choice{len(self.choice_scenes)}', list(key), False, fid)
        return self.choice_scenes[key]

    def menu_topics(self) -> list:
        """Top-level conversation topics any speaker answers, plus every topic their lines add."""
        out = [d for d in self.infos if d != GREETING and _int(self.dials[d], 'DATA.Type') in (0, 1)
               and _int(self.dials[d], 'DATA.Flags') & TOP_LEVEL]
        for dial in out:
            for rec in self.infos[dial]:
                out += [t for t in _fids(rec, 'AddTopic') if t in self.infos and t not in out]
        return out

    def greeting(self) -> bytes:
        """The speakers' GREETING lines as one FO4 greeting topic; each forces its speaker into the alias.

        A speaker with no FNV greeting gets a silent one last ('...'): FNV
        opens the topic list without a greeting, FO4 needs a line to start it.
        Every line needs GetPlayerActivated, as 71 vanilla scene greetings do,
        or a speaker idling near the player opens the talk unasked.
        """
        infos, greeted = [], set()
        activated = [[_cond('GetPlayerActivated', 0, 1.0)]]
        for rec in self.infos.get(GREETING, []):
            kept = self.kept(rec)
            if kept is not None:
                infos.append(self.npc_info(rec, kept + activated, self.main, forced_alias=True))
                greeted |= {c['p1'] for g in kept for c in g if c['func'] == 'GetIsID'}
        for label, npc, base, _, _ in SPEAKERS:
            if npc and npc not in greeted:
                self.report.append(f'{label}: no FNV greeting; silent fallback greeting added')
                conds = C.convert([[_cond('GetIsID', 0, 1.0, npc)]] + activated, self.form_map, self.av, False)
                infos.append(R.pack_info(self.ids.take(), 0, ('...',), conds, scene=self.main,
                                         phase='Menu', forced_alias=0))
        fid = self.ids.take()
        return pack_topic(R.pack_dial(fid, 'FNVSpike_Greeting', self.quest, R.TOPIC_GREETING, len(infos)), fid, infos)


def vanilla_cell() -> tuple:
    """(QASmoke's CELL record to override, its body) read from Fallout4.esm."""
    raw = FALLOUT4_ESM.read_bytes()
    for rec, _ in walk(raw, b'CELL'):
        if rec.form_id == CELL_FO4:
            return pack_fo4_record('CELL', CELL_FO4, rec.flags, rec.body), rec.body
    raise SystemExit('QASmoke not found')


def _add_converted_quests(w: FO4PluginWriter, spike: Spike, scripts: Path, forms: dict) -> None:
    """Write each script_spike.QUESTS quest; its stage script joins `spike.fragments.used` for compiling."""
    for edid in script_spike.QUESTS:
        fid = forms['Quest'][edid]
        record, script = script_spike.quest_record(scripts, edid, fid, spike.quest_stages[edid], forms, HELPER_INDEX)
        w.add_record('QUST', pack_quest(record, fid, (), [], []))
        spike.fragments.used.append(script)


def build(export_dir: Path, out: Path, scripts: Path = None, trace: bool = False) -> Spike:
    """Generate the spike plugin and return the Spike (report and menus).

    `scripts`, a folder of Fallout 4 converted scripts, also puts Doc's own
    script on his stand-in, the lines' fragments on their INFOs and the
    converted quests their scripts name (spike 3), their properties filled
    from Fallout4.esm, the helper plugin and those quests. `trace`
    adds a debug quest logging the dialogue state; its source is left on
    `spike.trace` for compiling.
    """
    spike = Spike(export_dir)
    forms = script_spike.spike_forms(HELPER_INDEX, len(MASTERS)) if scripts else {}
    spike.fragments = script_spike.Fragments(scripts, forms, HELPER_INDEX) if scripts else None
    spike.build_menu('FNVSpike_Menu', spike.menu_topics(), True, spike.main)
    greeting = spike.greeting()
    actor_ids = [spike.ids.take() for _ in SPEAKERS]
    doc_vmad = script_spike.attach(scripts, forms, HELPER_INDEX) if scripts else b''
    actors = b''.join(R.pack_achr(fid, base, pos, rot, doc_vmad if label == 'DocMitchell' else b'')
                      for fid, (label, _, base, pos, rot) in zip(actor_ids, SPEAKERS))
    spike.actor_ids = [(label, fid) for fid, (label, *_) in zip(actor_ids, SPEAKERS)]
    w = FO4PluginWriter(masters=MASTERS, is_esm=False, description='FNV dialogue spike')
    if trace:
        fid = spike.ids.take()
        w.add_record('QUST', pack_quest(script_spike.trace_quest(fid, spike.quest), fid, (), [], []))
        spike.trace = script_spike.trace_source(out.name, [(e, f) for f, e, *_ in spike.scenes], spike.actor_ids)
    if scripts:
        _add_converted_quests(w, spike, scripts, forms)
    w.add_raw_group('CELL', R.pack_interior_cells([(vanilla_cell()[0], CELL_FO4, actors, b'')]))
    qust = R.pack_qust(spike.quest, 'FNVSpike_Conversation', 'FNV Spike: conversations', 90,
                       list(spike.stages.values()), 'Speaker', None)
    w.add_record('QUST', pack_quest(qust, spike.quest, (), [greeting] + spike.topics, spike.scene_records))
    w.next_object_id = max([spike.ids.next & 0x00FFFFFF, *(oid + 1 for oid in script_spike.QUESTS.values())])
    out.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(out))
    return spike


def main():
    """Build the plugin and print the menus and the report."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, help='Plugin to write')
    ap.add_argument('--data', help='Also write the voice files (.fuz) under this Data folder')
    ap.add_argument('--trace', action='store_true', help='Add a debug quest logging the dialogue state '
                                                         '(compiled into --data/Scripts)')
    ap.add_argument('--scripts', help="Fallout 4 converted scripts: put Doc's script on his stand-in "
                                      '(compiled into --data/Scripts)')
    args = ap.parse_args()
    scripts = Path(args.scripts) if args.scripts else None
    spike = build(Path(args.export), Path(args.out), scripts, args.trace)
    if args.trace and args.data:
        print(script_spike.compile_source(script_spike.TRACE_SCRIPT, spike.trace, Path(args.data)))
    if scripts and args.data:
        print(script_spike.compile_into(scripts, Path(args.data), spike.fragments.used))
    if args.data:
        folders = Path(args.export) / 'sound' / 'voice' / 'falloutnv.esm'
        voices = [(folders / fnv, fo4) for fnv, fo4 in VOICES.values()]
        todo = voice.jobs(spike.voiced, voices, Path(args.data), Path(args.out).name)
        written = voice.convert(todo, FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator')
        print(f'voice: {written} of {len(todo)} recordings written as .fuz')
    for fid, edid, variants, prompts in spike.scenes:
        print(f'{edid} ({fid:08X}): {len(prompts)} options')
        for text, n in zip(prompts, variants):
            print(f'    [{n}] {text}')
    print(f'stages: {spike.stages}')
    print('report:')
    for line in sorted(set(spike.report)):
        print('   ', line)


if __name__ == '__main__':
    main()
