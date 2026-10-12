"""An FNV quest's conversations as FO4 scenes, for the cell spike.

FNV's StartConversation opens the speaker's GREETING (or a named topic): the
first passing line plays, then its Follow Ups (more of the speaker's lines,
first passing) or its Choices (topics the player picks from). On FO4 a script
starts the topic's scene (`TES4Talk_<topic>`; TES4Polyfill.StartConversation
puts the speaker in the quest's Speaker alias). Each step is a scene phase:
lines a Dialogue action saying a topic of them, Choices an XDI menu (one
option per topic and prompt, gated by its line when it has one, its lines
the answers behind padding so the first passing one answers). The topic list
(the Hub) ends in `[Leave]`, FNV's Tab; a Choices menu has none and its scene
prevents the player's exit (Prevent Player Exit Dialogue, as 84 vanilla
scenes), so leaving mid-conversation cannot strand a quest whose next line
is Say Once. While every line of a step leads to the same
next step, the scene runs on into it; lines leading apart start their own
scene by TSCE once said, as vanilla lines do. A line with several
responses and a result script is split into one FO4 line per response, each
a step (Fallout 4 runs a line's Begin fragment once per response, and 94% of
vanilla lines have one response), so its results run once. A Goodbye line ends
the conversation; a line followed by nothing else returns to the topic list
(the Hub), as FNV's does. An FO4 Greeting topic's silent line starts the
GREETING scene when the player activates the speaker or a converted force
greet runs; the GREETING lines are every cell quest's, highest quest priority
first, in one quest's scene. A line of another quest than the scene's needs
that quest running.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from dataclasses import dataclass, field

from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import LEAVE, menu_action
from fo4_import.spike.quest import SPEAKER_ALIAS
from fo4_import.spike.say_topics import CONVERSATION, PART, PARTS, conditions_of
from script_convert.constants import FALLOUT4_TALK_PREFIX

#: FNV INFO DATA flags.
GOODBYE, SAY_ONCE = 0x01, 0x04
#: FNV's GREETING topic.
GREETING = '000000C8'
#: FNV DIAL: the Topic type, and the Top-level flag (listed without an AddTopic).
TOPIC, TOP_LEVEL = '0', 0x02
#: CTDA OR-with-next bit; FO4 GetPlayerActivated, GetIsCurrentPackage, GetIsID, GetQuestRunning, GetGlobalValue.
OR, PLAYER_ACTIVATED, CURRENT_PACKAGE = 0x01, C.FO4.index('GetPlayerActivated'), C.FO4.index('GetIsCurrentPackage')
SPEAKER_TEST = 'GetIsID'
IS_ID, QUEST_RUNNING, GLOBAL_VALUE = C.FO4.index(SPEAKER_TEST), C.FO4.index('GetQuestRunning'), C.FO4.index(
    'GetGlobalValue')
#: _joined's answer when a step's lines lead to different steps.
MIXED = ('mixed',)


@dataclass
class Hub:
    """What every cell quest's conversations share: their lines, the topic list and its gates.

    `lines` {FNV INFO: record} of all cell quests, `topics` the FNV topics the
    list shows (top-level or added), `gates` {topic: FO4 global its AddTopic
    sets}, `quests` {FNV quest: (FO4 quest, FNV priority)}.
    """

    lines: dict = field(default_factory=dict)
    topics: tuple = ()
    gates: dict = field(default_factory=dict)
    quests: dict = field(default_factory=dict)


def hub(say, quests: list, quest_fids: dict, added: set) -> Hub:
    """The Hub of FNV quests `quests` (FO4 ids in `quest_fids` by EditorID), its gates not yet set; `added` the
    FNV topics (low 24 bits) anything AddTopics."""
    lines = {r['FormID'].upper(): r for q in quests for r in say.infos.get(q['FormID'].upper(), [])}
    topics = []
    for rec in lines.values():
        dial, info = rec['ParentDIAL'].upper(), say.dials.get(rec['ParentDIAL'], {})
        listed = int(info.get('DATA.Flags', 0) or 0) & TOP_LEVEL or int(dial, 16) & 0xFFFFFF in added
        if dial != GREETING and info.get('DATA.Type') == TOPIC and listed and dial not in topics:
            topics.append(dial)
    owners = {q['FormID'].upper(): (quest_fids[q['EditorID']], int(q.get('DATA.Priority', 0) or 0)) for q in quests}
    return Hub(lines, tuple(topics), {}, owners)


def _fids(rec: dict, key: str) -> list:
    """A Key[i] FormID list, as the export's upper-case hex."""
    return [rec[f'{key}[{i}]'].upper() for i in range(int(rec.get(f'{key}Count', 0) or 0))]


class Conversations:
    """The scenes and scene topics of one FNV quest's conversations; `topics` and `scenes` hold the records."""

    def __init__(self, say, quest: dict, quest_fid: int, form_map: dict, keyword: int, shared: Hub):
        """FNV `quest` (FO4 `quest_fid`) in `say`; steps draw on `shared`'s lines."""
        self.say, self.quest, self.fid, self.form_map, self.keyword = say, quest, quest_fid, form_map, keyword
        self.lines = {r['FormID'].upper(): r for r in say.infos.get(quest['FormID'].upper(), [])}
        self.hub, self.topics, self.scenes, self.placed, self.labels = shared, [], [], {}, {}

    def has_lines(self) -> bool:
        """True when the quest has lines outside its scripted Conversation topics."""
        return any(self.say.dials[r['ParentDIAL']].get('DATA.Type') != CONVERSATION for r in self.lines.values())

    def talk(self, prop: str, fid: int) -> bool:
        """Build scene `fid` that `prop` (`TES4Talk_<topic>`) starts, if the topic has lines in this quest; the
        GREETING one is the greeting scene (greeting())."""
        topic = prop[len(FALLOUT4_TALK_PREFIX):].lower()
        if topic == 'greeting':
            infos = self._greetings()
        else:
            infos = [i for i, r in self.lines.items() if self.say.dials[r['ParentDIAL']]['EditorID'].lower() == topic]
        if infos:
            self.labels[('line', tuple(infos))] = f'talk {topic}'
            self.scene(('line', tuple(infos)), fid)
        return bool(infos)

    def _greetings(self) -> list:
        """Every Hub quest's GREETING lines, highest quest priority first."""
        order = list(self.hub.lines)
        return sorted((i for i, r in self.hub.lines.items() if r['ParentDIAL'].upper() == GREETING),
                      key=lambda i: (-self._priority(self.hub.lines[i]), order.index(i)))

    def scene(self, step: tuple, fid: int = 0) -> tuple:
        """(scene, phase name, phase index) where `step` plays: ('line', FNV lines) said first passing, or
        ('menu', FNV topics).

        A new scene starts at `step` and runs on, a phase per step, while every
        line of a step leads to the same next step not yet placed.
        """
        if step in self.placed:
            return self.placed[step]
        fid, first = fid or self.say.builder.new_id(f'SCEN {self.quest["FormID"]} {self._key(step)}'), step
        edid, phases, actions, menu = f'FNV_{self.quest["EditorID"]}_Scene{len(self.placed)}', [], [], False
        locked = False
        while step is not None and step not in self.placed:
            self.placed[step] = (fid, f'Phase{len(phases)}', len(phases))
            phases.append(self.placed[step][1])
            nxt = self._joined(step)
            continues = nxt not in (None, MIXED) and nxt not in self.placed
            actions.append(self._action(step, (len(actions) + 1, len(phases) - 1), edid, continues))
            menu |= step[0] == 'menu'
            locked |= step[0] == 'menu' and step[1] != self.hub.topics
            step = nxt if continues else None
        self.scenes.append(R.pack_scen(fid, edid, self.fid, SPEAKER_ALIAS, actions, self.keyword if menu else 0,
                                       tuple(phases), R.SCENE_NO_EXIT if locked else 0))
        return self.placed[first]

    def _key(self, step: tuple) -> str:
        """The FormID key of `step`: what FNV authored, not the lines found today (the Hub's topic list and a
        script's topic grow as more converts), so ids stay put as content arrives.
        See: docs/fork/fo4_pipeline.md#npcs
        """
        if step[0] == 'menu' and step[1] == self.hub.topics:
            return 'menu hub'
        return self.labels.get(step, repr(step))

    def _members(self, step: tuple) -> list:
        """The FNV lines of `step` (a split line's first part): its lines, every line of its menu's topics, or
        a split line's later part."""
        if step[0] == 'part':
            return [part(self.hub.lines[step[1]], step[2])]
        if step[0] == 'line':
            return [part(self.hub.lines[i], 1) for i in step[1] if i in self.hub.lines]
        return [part(r, 1) for r in self.hub.lines.values() if r['ParentDIAL'].upper() in step[1]]

    def _next(self, rec: dict):
        """The step after FNV line `rec`: a split line's next part; its Follow Ups or Choices; the Hub's
        topic list after a line with neither (FNV lists the topics again); None after a Goodbye."""
        if rec.get(PART, 1) < rec.get(PARTS, 1):
            return 'part', rec['FormID'].upper(), rec[PART] + 1
        nxt = _next(rec)
        if nxt is None and self.hub.topics and not int(rec.get('DATA.Flags', 0)) & GOODBYE:
            return 'menu', self.hub.topics
        return nxt

    def _joined(self, step: tuple):
        """The step all of `step`'s lines lead to: None if they end, MIXED if they differ."""
        nexts = {self._next(r) for r in self._members(step)}
        return nexts.pop() if len(nexts) == 1 else (MIXED if nexts else None)

    def _action(self, step: tuple, place: tuple, edid: str, continues: bool) -> bytes:
        """The scene action playing `step` at `place` (index, phase); its lines run on when `continues`."""
        name, owner = f'{edid}_{place[1]}', f'{self.quest["FormID"]} {self._key(step)}'
        take = self.say.builder.new_id
        if step[0] == 'menu':
            player, npc = [], []
            for dial in step[1]:
                self._option(dial, player, npc, continues)
            if step[1] == self.hub.topics:
                player.append(R.pack_info(take(f'INFO leave {owner}'), 0, (LEAVE,), prompt=LEAVE))
                npc.append(R.pack_info(take(f'INFO exit {owner}'), R.INFO_END_SCENE, ('...',), notes='FNV Tab exit'))
            topics, action = menu_action(lambda: take(f'DIAL {owner}'), (name, self.fid, SPEAKER_ALIAS), player, npc,
                                         place)
            self.topics += topics
            return action
        lines = [line for line in (self._line(r, continues) for r in self._members(step)) if line]
        topic = take(f'DIAL {owner}')
        self.topics.append(pack_topic(R.pack_dial(topic, name, self.fid, R.TOPIC_SCENE, len(lines)), topic, lines))
        return R.pack_dialogue_action(place[0], SPEAKER_ALIAS, topic, place[1])

    def _option(self, dial: str, player: list, npc: list, continues: bool) -> None:
        """Add FNV topic `dial` to a menu: an option per prompt among its lines (FNV shows the first passing
        line's), each padded to its answers."""
        prompts = {}
        for rec in self.hub.lines.values():
            if rec['ParentDIAL'].upper() == dial:
                prompts.setdefault(rec.get('Prompt') or self.say.dials[dial].get('FULL', ''), []).append(part(rec, 1))
        added = [self._prompt(dial, text, members, (player, npc), continues) for text, members in prompts.items()]
        if not any(added):
            self.say.builder.counts['choice without a line in the quest'] += 1

    def _prompt(self, dial: str, text: str, members: list, menu: tuple, continues: bool) -> bool:
        """Add one option of FNV topic `dial` with prompt `text` answered by `members` to `menu` (player, npc);
        False when no line of it converts."""
        player, npc = menu
        answers = [a for a in (self._line(r, continues) for r in members) if a]
        if not answers:
            return False
        once = R.INFO_SAY_ONCE if all(int(r.get('DATA.Flags', 0)) & SAY_ONCE for r in members) else 0
        if len(members) == 1:
            shown = conditions_of(members[0], self.form_map, self.say.script_vars, swap=True) or b''
        else:
            shown = self._speakers(members)
        shown += self._running(members[0]) + self._gate(dial)
        owner = f'INFO prompt {dial} {text}'
        player.append(R.pack_info(self.say.builder.new_id(owner), once, (text,), shown, prompt=text))
        player += [R.pack_info(self.say.builder.new_id(owner)) for _ in answers[1:]]
        npc += answers
        return True

    def _speakers(self, members: list) -> bytes:
        """One OR-group of the lines' speakers (GetIsID), run on the player line's target; b'' when a line has
        none (anyone may answer). A line whose speaker is not built is left out with its speaker."""
        tests = []
        for rec in members:
            found = [c['p1'] for c in _conditions(rec) if c['func'] == SPEAKER_TEST and c['value'] == 1.0
                     and not c['op_flags'] & 0xE0]
            if not found:
                return b''
            if found[0] in self.form_map and self.form_map[found[0]] not in tests:
                tests.append(self.form_map[found[0]])
        return b''.join(R.pack_ctda(OR if i < len(tests) - 1 else 0, 1.0, IS_ID, npc, run_on=R.RUN_TARGET)
                        for i, npc in enumerate(tests))

    def _running(self, rec: dict) -> bytes:
        """GetQuestRunning on FNV line `rec`'s quest when it is a Hub quest other than this one."""
        quest = rec.get('QSTI.Quest', '').upper()
        if quest == self.quest['FormID'].upper() or quest not in self.hub.quests:
            return b''
        return R.pack_ctda(0, 1.0, QUEST_RUNNING, self.hub.quests[quest][0])

    def _gate(self, dial: str) -> bytes:
        """GetGlobalValue of the global FNV topic `dial`'s AddTopic sets, when it is gated."""
        return R.pack_ctda(0, 1.0, GLOBAL_VALUE, self.hub.gates[dial]) if dial in self.hub.gates else b''

    def _line(self, rec: dict, continues: bool) -> bytes:
        """FNV line `rec` as the speaker's INFO: the scene runs on (`continues`), or it starts what follows
        once said, or ends."""
        extra = self._running(rec)
        if continues:
            return self.say.info(rec, self.form_map, extra=extra)
        nxt = self._next(rec)
        if nxt is None:
            return self.say.info(rec, self.form_map, flags=R.INFO_END_SCENE, extra=extra)
        return self.say.info(rec, self.form_map, self.scene(nxt), flags=R.INFO_START_ON_END, extra=extra)

    def greeting(self, greets: list) -> None:
        """A Greeting topic whose silent line starts the GREETING talk scene, for activation or force greets `greets`.

        The scene's lines are _greetings(). The line says '...'; it puts its speaker in the
        Speaker alias and needs GetPlayerActivated or a running force greet
        and a speaker the GREETING lines name; the lines stay in the scene, so
        each Say Once line exists once.
        See: docs/fork/fo4_spikes.md#spike-1-force-greet
        """
        infos = self._greetings()
        if not infos:
            return
        speakers = sorted({self.form_map[c['p1']] for i in infos for c in _conditions(self.hub.lines[i])
                           if c['func'] == SPEAKER_TEST and c['p1'] in self.form_map})
        opened = _any([(PLAYER_ACTIVATED, 0)] + [(CURRENT_PACKAGE, p) for p in greets])
        opened += _any([(IS_ID, npc) for npc in speakers])
        scene, phase, index = self.scene(('line', tuple(infos)))
        line = R.pack_info(self.say.builder.new_id(f'INFO greeting {self.quest["FormID"]}'), 0, ('...',), opened, scene=scene, phase=phase, phase_index=index,
                           notes='FNV GREETING', forced_alias=SPEAKER_ALIAS)
        fid = self.say.builder.new_id(f'DIAL greeting {self.quest["FormID"]}')
        dial = R.pack_dial(fid, f'FNV_{self.quest["EditorID"]}_Greeting', self.fid, R.TOPIC_GREETING, 1)
        self.topics.append(pack_topic(dial, fid, [line]))

    def _priority(self, rec: dict) -> int:
        """The FNV priority of line `rec`'s quest."""
        return self.hub.quests.get(rec.get('QSTI.Quest', '').upper(), (0, 0))[1]


def part(rec: dict, number: int) -> dict:
    """FNV line `rec` as part `number` of its split (one response, PART and PARTS set); `rec` itself when it is
    not split (one response, or no result script)."""
    count = int(rec.get('ResponseCount', 0) or 0)
    if count < 2 or not ((rec.get('ResultScript') or '').strip() or (rec.get('ResultScriptEnd') or '').strip()):
        return rec
    prefix = f'Response[{number - 1}].'
    out = {k: v for k, v in rec.items() if not k.startswith('Response[')}
    out.update({'Response[0].' + k[len(prefix):]: v for k, v in rec.items() if k.startswith(prefix)})
    return {**out, 'ResponseCount': '1', PART: number, PARTS: count}


def _next(rec: dict):
    """The step after FNV line `rec`: ('line', Follow Ups) or ('menu', Choices); None after a Goodbye or neither."""
    follow, choices = _fids(rec, 'FollowUp'), _fids(rec, 'Choice')
    if int(rec.get('DATA.Flags', 0)) & GOODBYE or not (follow or choices):
        return None
    return ('line', tuple(follow)) if follow else ('menu', tuple(choices))


def _conditions(rec: dict) -> list:
    """An FNV record's conditions, parsed."""
    return [C.parse(rec[f'Condition[{i}].Raw']) for i in range(int(rec.get('ConditionCount', 0) or 0))]


def _any(tests: list) -> bytes:
    """One OR-group of `tests` [(FO4 function, param 1)], each == 1 on the subject."""
    return b''.join(R.pack_ctda(OR if i < len(tests) - 1 else 0, 1.0, func, p1) for i, (func, p1) in enumerate(tests))
