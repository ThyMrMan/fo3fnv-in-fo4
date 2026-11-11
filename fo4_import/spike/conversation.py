"""An FNV quest's conversations as FO4 scenes, for the cell spike.

FNV's StartConversation opens the speaker's GREETING (or a named topic): the
first passing line plays, then its Follow Ups (more of the speaker's lines,
first passing) or its Choices (topics the player picks from). On FO4 a script
starts the topic's scene (`TES4Talk_<topic>`; TES4Polyfill.StartConversation
puts the speaker in the quest's Speaker alias). Each step is a scene phase:
lines a Dialogue action saying a topic of them, Choices a menu of ours
(F3NV.dll): one option per FNV topic, linked in the plugin's links file to
that topic's answer topic, which holds its lines once for the whole build, so
F3NV.dll lists an option while one of its lines passes and plays the first
that does. The topic list (the Hub) ends in `[Leave]`, FNV's Tab; a Choices
menu has none and its scene prevents the player's exit (Prevent Player Exit
Dialogue, as 84 vanilla scenes), so leaving mid-conversation cannot strand a
quest whose next line is Say Once, unless its conversation can never end (no
step from it ends or returns to the Hub), when it keeps `[Leave]`. A player
conversation's step is built once for the whole build, in the quest that
reaches it first; a line starting a scene of another quest puts its speaker
in that quest's Speaker alias (ALFA). While every line of a step leads to the
same next step (in a chat, those ending it aside), the scene runs on into it;
a menu ends its scene, its answers starting what follows. A line with several
responses and a result script is split into one FO4 line per response, each
a step (Fallout 4 runs a line's Begin fragment once per response, and 94% of
vanilla lines have one response), so its results run once. A Goodbye line ends
the conversation; a line followed by nothing else returns to the topic list
(the Hub), as FNV's does. An FO4 Greeting topic's silent line starts the
GREETING scene when the player activates the speaker or a converted force
greet runs; the GREETING lines are every cell quest's, highest quest priority
first, in one quest's scene. A line of another quest than the scene's needs
that quest running. FNV's StartConversation between two NPCs starts a chat
scene (`TES4Chat_<topic>`): the speaker and listener fill the Speaker and
Listener aliases, each step said by one of them (a line's Choices by the
other unless its Next Speaker is Self), facing the other; a line's Target
tests run on the other's alias.

See: docs/fork/fo4_dialogue_menu_plan.md#converter
"""

import collections
import heapq
import struct
from dataclasses import dataclass, field

from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import LEAVE
from fo4_import.spike.dialogue_trace import CHOICE_VMAD, scene_vmad
from fo4_import.spike.quest import LISTENER_ALIAS, SPEAKER_ALIAS
from fo4_import.spike.readiness import CHOICE_UNANSWERED
from fo4_import.spike.script_packages import quest_id
from fo4_import.spike.skill_tags import tag_check, tagged
from fo4_import.spike.say_topics import GREETING, PART, PARTS, SHARED, conditions_of, parsed, raws
from script_convert.constants import FALLOUT4_CHAT_PREFIX, FALLOUT4_TALK_PREFIX
from tes5_import.base.tes5_reader import subrecords

#: FNV INFO DATA flags.
GOODBYE = 0x01
#: FNV INFO DATA Next Speaker Self (0 Target, 2 Either: the other actor answers).
NEXT_SELF = 1
#: FNV DIAL: the Topic type, and the Top-level flag (listed without an AddTopic).
TOPIC, TOP_LEVEL = '0', 0x02
#: CTDA OR-with-next bit; FO4 GetPlayerActivated, GetIsCurrentPackage, GetIsID, GetQuestRunning, GetGlobalValue.
OR, PLAYER_ACTIVATED, CURRENT_PACKAGE = 0x01, C.FO4.index('GetPlayerActivated'), C.FO4.index('GetIsCurrentPackage')
SPEAKER_TEST = 'GetIsID'
IS_ID, QUEST_RUNNING, GLOBAL_VALUE = C.FO4.index(SPEAKER_TEST), C.FO4.index('GetQuestRunning'), C.FO4.index(
    'GetGlobalValue')
#: FO4 IsInList: a talker in an actor's talking-as list (talking_activators) speaks as that actor.
IN_LIST = C.FO4.index('IsInList')
#: The script the Greeting line carries: it opens the GREETING scene with its speaker, stopping one left playing.
GREETING_SCRIPT = 'F3NV_Greeting'
#: _joined's answer when a step's lines lead to different steps.
MIXED = ('mixed',)
#: The player's base form (NPC_), which vanilla's player Hello lines test with GetIsID.
PLAYER_BASE = 0x7


@dataclass
class Hub:
    """What every cell quest's conversations share: their lines, the topic list and its gates.

    `lines` {FNV INFO: record} of all cell quests, `topics` the FNV topics the
    list shows (top-level or added), `gates` {topic: FO4 global its AddTopic
    sets}, `quests` {FNV quest: (FO4 quest, FNV priority)}, `by_topic` {FNV
    topic: [(position in `lines`, INFO)] in that order}; `joins` the steps more than one FNV line leads to
    (joined_steps); `authored` the FNV topics with a line of their own or shared, in any quest; `outside` and
    `outside_topics` the masters' lines the build does not write, as `lines` and `by_topic` (outside_lines);
    `placed` {player step: (scene, phase, index)} and `scene_quests` {scene: FO4 quest} of the steps built,
    `answers` {FNV topic: its answer topic, 0 for none}, `home` the start-game quest's Conversations that builds
    them all (Conversations).
    """

    lines: dict = field(default_factory=dict)
    topics: tuple = ()
    gates: dict = field(default_factory=dict)
    quests: dict = field(default_factory=dict)
    by_topic: dict = field(default_factory=dict)
    joins: frozenset = frozenset()
    authored: frozenset = frozenset()
    outside: dict = field(default_factory=dict)
    outside_topics: dict = field(default_factory=dict)
    placed: dict = field(default_factory=dict)
    scene_quests: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    home: object = None


def outside_lines(say, lines: dict) -> tuple:
    """({Hub key: line}, {FNV topic: [(position, key)]}) of the lines the game has beside the build's `lines`:
    its masters' (say.outside) and the shared copies they bring (shared_lines); empty for a build without masters.
    Only _leaves reads them: they are never written.
    See: docs/fork/fo4_plugin_layout.md#dlc-dialogue
    """
    if not say.outside:
        return {}, {}
    whole = {**{r['FormID'].upper(): r for r in say.outside}, **lines}
    whole.update(shared_lines(say, whole))
    found, by_topic = {key: rec for key, rec in whole.items() if key not in lines}, {}
    for position, (key, rec) in enumerate(found.items()):
        by_topic.setdefault(rec['ParentDIAL'].upper(), []).append((position, key))
    return found, by_topic


def joined_steps(infos: dict) -> frozenset:
    """The steps (_next) more than one FNV line in `infos` ({quest: lines}, every quest) leads to, by FormID: each
    starts a scene of its own, so a line added on another path never folds it into that path's scene.
    See: docs/fork/fo4_pipeline.md#scene-joins
    """
    leads = collections.defaultdict(set)
    for rec in (r for lines in infos.values() for r in lines):
        step = _next(rec)
        if step:
            leads[step].add(rec['FormID'].upper())
    return frozenset(step for step, lines in leads.items() if len(lines) > 1)


def hub(say, quests: list, quest_fids: dict, added: set) -> Hub:
    """The Hub of FNV quests `quests` (FO4 ids in `quest_fids` by EditorID), its gates not yet set; `added` the
    FNV topics (low 24 bits) anything AddTopics."""
    lines = {r['FormID'].upper(): r for q in quests for r in say.infos.get(q['FormID'].upper(), [])}
    lines.update(shared_lines(say, lines))
    topics, by_topic = [], {}
    for position, (line, rec) in enumerate(lines.items()):
        dial, info = rec['ParentDIAL'].upper(), say.dials.get(rec['ParentDIAL'], {})
        by_topic.setdefault(dial, []).append((position, line))
        listed = int(info.get('DATA.Flags', 0) or 0) & TOP_LEVEL or int(dial, 16) & 0xFFFFFF in added
        if dial != GREETING and info.get('DATA.Type') == TOPIC and listed and dial not in topics:
            topics.append(dial)
    owners = {q['FormID'].upper(): (quest_fids[q['EditorID']], int(q.get('DATA.Priority', 0) or 0)) for q in quests}
    authored = {r['ParentDIAL'].upper() for found in say.infos.values() for r in found}
    authored |= {d.upper() for d, rec in say.dials.items() if int(rec.get('SharedInfoCount', 0) or 0)}
    return Hub(lines, tuple(topics), {}, owners, by_topic, joins=joined_steps(say.infos), authored=frozenset(authored))


def hub_key(rec: dict) -> str:
    """The Hub's key of FNV line `rec`: FormID, plus a shared copy's topic."""
    return rec['FormID'].upper() + (f' via {rec[SHARED]}' if rec.get(SHARED) else '')


def shared_lines(say, lines: dict) -> dict:
    """{Hub key: copy} of the shared infos (DIAL SharedInfo) of `lines` that a player topic borrows for their own
    quest: each a line of that topic (ParentDIAL), marked SHARED, after the topic's own lines. A topic sharing
    its own line takes no copy: the line already answers it, and a copy would answer it twice.
    See: docs/fork/fo4_pipeline.md#shared-infos
    """
    quests, out = {r.get('QSTI.Quest', '').upper() for r in lines.values()}, {}
    for dial, rec in say.dials.items():
        if rec.get('DATA.Type') != TOPIC or dial.upper() == GREETING:
            continue
        for i in range(int(rec.get('SharedInfoCount', 0) or 0)):
            info, quest = rec[f'SharedInfo[{i}].Info'].upper(), rec[f'SharedInfo[{i}].Quest'].upper()
            own = info in lines and lines[info]['ParentDIAL'].upper() == dial.upper()
            copy = {**lines[info], 'ParentDIAL': dial.upper(), SHARED: dial.upper()} if info in lines and not own \
                else None
            out.update({hub_key(copy): copy} if copy and quest in quests else {})
    return out


def _fids(rec: dict, key: str) -> list:
    """A Key[i] FormID list, as the export's upper-case hex."""
    return [rec[f'{key}[{i}]'].upper() for i in range(int(rec.get(f'{key}Count', 0) or 0))]


class Conversations:
    """The scenes and scene topics of one FNV quest's conversations; `topics` and `scenes` hold the records."""

    def __init__(self, say, quest: dict, quest_fid: int, form_map: dict, shared: Hub):
        """FNV `quest` (FO4 `quest_fid`) in `say`; steps draw on `shared`'s lines."""
        self.say, self.quest, self.fid, self.form_map = say, quest, quest_fid, form_map
        self.lines = {r['FormID'].upper(): r for r in say.infos.get(quest['FormID'].upper(), [])}
        self.hub, self.topics, self.scenes, self.own, self.labels = shared, [], [], {}, {}
        self.packaged, self.legacy, self.building = {}, {}, 0

    def has_lines(self) -> bool:
        """True when the quest has lines (said from its Speaker and Listener)."""
        return bool(self.lines)

    def talk(self, prop: str, fid: int) -> bool:
        """Build scene `fid` that `prop` (`TES4Talk_<topic>`, `TES4Chat_<topic>`) starts, if the topic has lines in
        this quest; the GREETING talk is the greeting scene (greeting()), a chat one between two NPCs."""
        chat = prop.startswith(FALLOUT4_CHAT_PREFIX)
        topic = prop[len(FALLOUT4_CHAT_PREFIX if chat else FALLOUT4_TALK_PREFIX):].lower()
        if topic == 'greeting' and not chat:
            infos = self._greetings()
        else:
            infos = [i for i, r in self.lines.items() if self.say.dials[r['ParentDIAL']]['EditorID'].lower() == topic]
        step = ('chat', SPEAKER_ALIAS, ('line', tuple(infos))) if chat else ('line', tuple(infos))
        if infos:
            self.labels[step] = f'{"chat" if chat else "talk"} {topic}'
            self.scene(step, fid)
        return bool(infos)

    def _greetings(self) -> list:
        """The Hub's GREETING lines, highest quest priority first, then in Hub order."""
        return sorted((i for _, i in self.hub.by_topic.get(GREETING, ())),
                      key=lambda i: -self._priority(self.hub.lines[i]))

    def _placed(self, step: tuple) -> dict:
        """The placed steps holding `step`: a chat's or talk's own, else the build's."""
        return self.own if step[0] == 'chat' or step in self.labels else self.hub.placed

    def scene(self, step: tuple, fid: int = 0, flags: int = 0) -> tuple:
        """(scene, phase name, phase index) where `step` plays: ('line', FNV lines) said first passing, or
        ('menu', FNV topics); a new scene gets FNAM `flags` too.

        A scene starts at `step` and runs on, a phase per step, while every line of a step leads to the
        same next step not yet placed and not _starts_own; a menu ends it. A loop back to the step repeats it;
        one to an earlier step ends the scene (_line). A step any quest reaches is built in Hub.home.
        See: docs/fork/fo4_pipeline.md#scene-loops
        """
        shared = self._placed(step) is self.hub.placed
        if shared and self.hub.home not in (None, self):
            return self.hub.home.scene(step, flags=flags)
        if step in self._placed(step):
            return self._placed(step)[step]
        fid, first = fid or self._owned('SCEN', step), step
        owner = 'Shared' if shared else self.quest['EditorID']
        edid, phases, actions = f'FNV_{owner}_Scene{len(self._placed(step))}', [], []
        locked, outer, self.building = False, self.building, fid
        self.hub.scene_quests[fid] = self.fid
        while step is not None and step not in self._placed(step):
            self._placed(step)[step] = (fid, f'Phase{len(phases)}', len(phases))
            phases.append(f'Phase{len(phases)}')
            nxt = None if step[0] == 'menu' else self._joined(step)
            loops = nxt == step
            continues = loops or (nxt not in (None, MIXED) and nxt not in self._placed(nxt) and not self._starts_own(nxt))
            actions.append(self._action(step, (len(actions) + 1, len(phases) - 1), edid, continues, loops))
            locked |= step[0] == 'menu' and not self._leaves(step)
            step = nxt if continues and not loops else None
        self.building = outer
        listener = LISTENER_ALIAS if first[0] == 'chat' else None
        self.scenes.append(R.pack_scen(fid, edid, self.fid, SPEAKER_ALIAS, actions, 0, tuple(phases),
                                       (R.SCENE_NO_EXIT if locked else 0) | flags, listener, scene_vmad(len(phases))))
        return self._placed(first)[first]

    def _starts_own(self, step: tuple) -> bool:
        """Whether `step` (a chat's inner step) is the topic list or a join.
        See: docs/fork/fo4_pipeline.md#scene-joins
        """
        inner = step[2] if step[0] == 'chat' else step
        return inner == ('menu', self.hub.topics) or inner in self.hub.joins

    def _key(self, step: tuple) -> str:
        """The FormID key of `step`, from what FNV authored: the topic list's; a labelled talk's or a chat's under
        this quest; else the step itself (its lines or Choices), the same in whichever quest builds it.
        See: docs/fork/fo4_pipeline.md#npcs
        """
        if step[0] == 'menu' and step[1] == self.hub.topics:
            return 'menu hub'
        if step in self.labels or step[0] == 'chat':
            return f'{self.quest["FormID"]} {self.labels.get(step, repr(step))}'
        return repr(step)

    def _owned(self, kind: str, step: tuple) -> int:
        """The FormID of `step`'s `kind` record (SCEN, DIAL), keyed by _key(); a step relabelled keeps the id its
        old key gave (`legacy`).
        See: docs/fork/fo4_pipeline.md#formid-ledger
        """
        key = f'{kind} {self._key(step)}'
        if step not in self.legacy:
            return self.say.builder.new_id(key)
        return self.say.builder.new_id(f'{kind} {self.quest["FormID"]} {self.legacy[step]}', key=key)

    def _members(self, step: tuple, whole: bool = False) -> list:
        """The FNV lines of `step` (a split line's first part): its lines, every line of its menu's topics, or
        a split line's later part; a chat step's are its inner step's. `whole` adds the masters' lines the build
        does not write (Hub.outside)."""
        if step[0] == 'chat':
            return self._members(step[2], whole)
        lines = collections.ChainMap(self.hub.lines, self.hub.outside) if whole else self.hub.lines
        topics = (self.hub.by_topic, self.hub.outside_topics) if whole else (self.hub.by_topic,)
        if step[0] == 'part':
            return [part(lines[step[1]], step[2])]
        if step[0] == 'line':
            return [part(lines[i], 1) for i in step[1] if i in lines]
        return [part(lines[i], 1) for _, i in heapq.merge(*(found.get(d, ()) for found in topics for d in step[1]))]

    def _next(self, rec: dict, alias: 'int | None' = None):
        """The step after FNV line `rec`: a split line's next part; its Follow Ups or Choices; the Hub's
        topic list after a line with neither (FNV lists the topics again); None after a Goodbye.

        Said by `alias` in a chat, the step is a chat step: the next part
        and Follow Ups by the same actor, Choices by the other unless the
        line names itself next (FNV Next Speaker Self); None after neither.
        """
        if rec.get(PART, 1) < rec.get(PARTS, 1):
            nxt = 'part', hub_key(rec), rec[PART] + 1
            return nxt if alias is None else ('chat', alias, nxt)
        nxt = _next(rec)
        if alias is not None and nxt is not None:
            same = nxt[0] == 'line' or int(rec.get('DATA.NextSpeaker', 0) or 0) == NEXT_SELF
            return 'chat', alias if same else _other(alias), nxt
        if alias is not None:
            return None
        if nxt is None and self.hub.topics and not int(rec.get('DATA.Flags', 0)) & GOODBYE:
            return 'menu', self.hub.topics
        return nxt

    def _leaves(self, step: tuple) -> bool:
        """Whether menu `step` offers `[Leave]` (FNV's Tab): the topic list does, and a Choices menu whose
        conversation can never end (no step reached from it ends or returns to the topic list: Victor's loop);
        any other keeps the player in (SCENE_NO_EXIT), so leaving cannot strand a quest. Judged on the whole
        conversation, the masters' lines included.
        See: docs/fork/fo4_spikes.md#spike-2-vcg01
        """
        if step[1] == self.hub.topics:
            return True
        seen, todo = {step}, [step]
        while todo:
            here = todo.pop()
            for rec in self._members(here, True):
                nxt = self._next(rec, _chat_alias(here))
                if nxt is None or nxt == ('menu', self.hub.topics):
                    return False
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return True

    def _joined(self, step: tuple):
        """The step all of `step`'s lines lead to: None if they end, MIXED if they differ; a chat's lines that end
        it (End Scene) leave the others' step, so a quest stopped at its scene's end keeps its next lines.
        See: docs/fork/fo4_pipeline.md#actor-dialogue
        """
        nexts = {self._next(r, _chat_alias(step)) for r in self._members(step)}
        if step[0] == 'chat' and len(nexts) > 1:
            nexts.discard(None)
        return nexts.pop() if len(nexts) == 1 else (MIXED if nexts else None)

    def _action(self, step: tuple, place: tuple, edid: str, continues: bool, looping: bool = False) -> bytes:
        """The scene action playing `step` at `place` (index, phase); its lines run on when `continues`; a line
        step said again and again when `looping`."""
        name = f'{edid}_{place[1]}'
        if step[0] == 'menu':
            return self._menu(step, place, name)
        alias, owner = _chat_alias(step), self._key(step)
        lines = [line for line in (self._line(r, continues, alias, owner) for r in self._members(step)) if line]
        topic = self._owned('DIAL', step)
        self.topics.append(pack_topic(R.pack_dial(topic, name, self.fid, R.TOPIC_SCENE, len(lines)), topic, lines))
        if alias is None:
            return R.pack_dialogue_action(place[0], SPEAKER_ALIAS, topic, place[1], looping=looping)
        return R.pack_dialogue_action(place[0], alias, topic, place[1], _other(alias), looping)

    def _menu(self, step: tuple, place: tuple, name: str) -> bytes:
        """The Player Dialogue action of menu `step` at `place`: an option per FNV topic it offers (_choice), then
        [Leave] when _leaves(), in one player topic beside an empty NPC one (F3NV.dll answers from the links).
        See: docs/fork/fo4_dialogue_menu_plan.md#converter
        """
        owner, take = self._key(step), self.say.builder.new_id
        options = [option for option in (self._choice(dial, owner) for dial in step[1]) if option]
        if self._leaves(step):
            self.say.builder.counts['[Leave] on a never-ending Choices menu'] += step[1] != self.hub.topics
            options.append(self._option(take(f'INFO leave {owner}'), LEAVE, b'', self._exit()))
        player, npc = take(f'DIAL {owner} options'), take(f'DIAL {owner} answers')
        self.topics += [pack_topic(R.pack_dial(player, f'{name}_P', self.fid, R.TOPIC_SCENE, len(options)), player,
                                   options),
                        pack_topic(R.pack_dial(npc, f'{name}_N', self.fid, R.TOPIC_SCENE, 0), npc, [])]
        self.say.builder.counts['menu options'] += len(options)
        return R.pack_player_dialogue(place[0], SPEAKER_ALIAS, (player,), (npc,), place[1])

    def _option(self, fid: int, text: str, conditions: bytes, answer: int) -> bytes:
        """Option INFO `fid` showing `text` on `conditions`, linked to `answer`."""
        self.say.links.append((fid, answer))
        return R.pack_info(fid, 0, (text,), conditions, prompt=text, vmad=CHOICE_VMAD)

    def _choice(self, dial: str, owner: str) -> bytes:
        """The option of FNV topic `dial` in menu `owner`: its first line's prompt, shown while the topic is known
        (_gate); F3NV.dll lists it while one of its answers passes. b'' when none converts (_unanswered)."""
        answer = self._answers(dial)
        if not answer:
            self._unanswered(dial)
            return b''
        lines = self._members(('menu', (dial,)))
        text = self._prompt(lines[0], dial)
        label = tagged(text, [rec for rec in lines if self._prompt(rec, dial) == text])
        return self._option(self.say.builder.new_id(f'INFO option {owner} {dial}'), label, self._gate(dial), answer)

    def _prompt(self, rec: dict, dial: str) -> str:
        """FNV line `rec`'s prompt: its own, else its topic `dial`'s name."""
        return rec.get('Prompt') or self.say.dials.get(dial, {}).get('FULL', '')

    def _answers(self, dial: str) -> int:
        """FNV topic `dial`'s answer topic, made once for the build: the Hub's lines of it in Hub order, each keyed
        by the line alone and leading where it leads (_answer); 0 when none of them converts.
        See: docs/fork/fo4_dialogue_menu_plan.md#converter
        """
        if dial in self.hub.answers:
            return self.hub.answers[dial]
        lines = [rec for rec in self._members(('menu', (dial,)))
                 if conditions_of(rec, self.form_map, self.say.script_vars) is not None]
        fid = self.hub.answers[dial] = self.say.builder.new_id(f'DIAL answer {dial}') if lines else 0
        infos = [info for info in (self._answer(rec, dial, lines) for rec in lines) if info]
        edid = f'FNV_Answer_{self.say.dials.get(dial, {}).get("EditorID") or dial}'
        if fid:
            self.topics.append(pack_topic(R.pack_dial(fid, edid, self.fid, R.TOPIC_SCENE, len(infos)), fid, infos))
        return fid

    def _answer(self, rec: dict, dial: str, lines: list) -> bytes:
        """FNV line `rec` of topic `dial` as its answer, with its prompt (tagged over `lines` of that prompt); a
        skill-checked prompt's check goes to say.checks."""
        text = self._prompt(rec, dial)
        group = [line for line in lines if self._prompt(line, dial) == text]
        info = self._line(rec, False, place='answer', prompt=tagged(text, group))
        check = tag_check(text, group)
        av = self.form_map.get(('av', check[0])) if check else None
        if info and av:
            self.say.checks.append((struct.unpack_from('<I', info, 12)[0], av, check[1]))
        return info

    def _exit(self) -> int:
        """The answer topic ending the talk ([Leave], FNV's Tab): one silent End Scene line, made once."""
        if LEAVE not in self.hub.answers:
            take = self.say.builder.new_id
            fid, line = take('DIAL answer leave'), take('INFO answer leave')
            self.say.silent.append((line, False))
            info = R.pack_info(line, R.INFO_END_SCENE, (R.SILENT_LINE,), notes='FNV Tab exit', vmad=CHOICE_VMAD)
            self.topics.append(pack_topic(R.pack_dial(fid, 'FNV_Answer_Leave', self.fid, R.TOPIC_SCENE, 1), fid,
                                          [info]))
            self.hub.answers[LEAVE] = fid
        return self.hub.answers[LEAVE]

    def _unanswered(self, dial: str) -> None:
        """Record FNV topic `dial` left with no option: when FNV never answers it either (no line anywhere), only a
        count; else a CHOICE_UNANSWERED entry with its cause (`not built`: its lines' quests are not in the build;
        `condition`: no line converts, see their LINE_LEFT_OUT entries).
        See: docs/fork/fo4_plan_dialogue_reach.md#framework
        """
        counts, has = self.say.builder.counts, bool(self.hub.by_topic.get(dial))
        if not has and dial not in self.hub.authored:
            counts['choice FNV never answers (no line)'] += 1
            return
        counts['choice without a line in the quest'] += 1
        self.say.builder.readiness.add(CHOICE_UNANSWERED, self.quest['FormID'],
                                       f'{self.say.dials[dial].get("EditorID", dial)} ({dial}): '
                                       f'{"condition" if has else "not built"}')

    def speakers(self, members: list, run_on: int = R.RUN_TARGET) -> bytes:
        """One OR-group of the lines' speakers (GetIsID), run on `run_on` (the player line's target); b'' when a
        line has none (anyone may answer). A line whose speaker is not built is left out with its speaker."""
        tests = []
        for rec in members:
            found = [c['p1'] for c in parsed(rec) if c['func'] == SPEAKER_TEST and c['value'] == 1.0
                     and not c['op_flags'] & 0xE0]
            if not found:
                return b''
            if found[0] in self.form_map and self.form_map[found[0]] not in tests:
                tests.append(self.form_map[found[0]])
        return b''.join(R.pack_ctda(OR if i < len(tests) - 1 else 0, 1.0, IS_ID, npc, run_on=run_on)
                        for i, npc in enumerate(tests))

    def _hub_quest(self, rec: dict) -> int:
        """FO4 quest of FNV line `rec` if a Hub quest other than this one, else 0."""
        quest = rec.get('QSTI.Quest', '').upper()
        return self.hub.quests[quest][0] if quest != self.quest['FormID'].upper() and quest in self.hub.quests else 0

    def _running(self, rec: dict) -> bytes:
        """GetQuestRunning on FNV line `rec`'s Hub quest, if not this one."""
        quest = self._hub_quest(rec)
        return R.pack_ctda(0, 1.0, QUEST_RUNNING, quest) if quest else b''

    def _gate(self, dial: str) -> bytes:
        """GetGlobalValue of the global FNV topic `dial`'s AddTopic sets, when it is gated."""
        return R.pack_ctda(0, 1.0, GLOBAL_VALUE, self.hub.gates[dial]) if dial in self.hub.gates else b''

    def _line(self, rec: dict, continues: bool, alias: 'int | None' = None, place: str = '', prompt: str = '') -> bytes:
        """FNV line `rec` as the speaker's INFO (said by chat `alias`, its Target tests on the other actor) at
        `place` (its step): the scene runs on (`continues`), or it starts what follows once said, or ends. An
        answer (`prompt`, played from any menu) always starts what follows, its speaker forced into the Speaker
        alias, as is a line starting another quest's scene."""
        extra, target = self._running(rec), None if alias is None else _other(alias)
        package = self.packaged.get(hub_key(rec)) if rec.get(PART, 1) == 1 and not prompt else None
        extra += R.pack_ctda(0, 1.0, CURRENT_PACKAGE, package) if package else b''
        said = {'extra': extra, 'target': target, 'owner': self.fid, 'place': place, 'prompt': prompt}
        nxt = self._next(rec, alias)
        if continues and nxt is not None:
            return self.say.info(rec, self.form_map, **said)
        if nxt is None or (not prompt and self._back(nxt)):
            return self.say.info(rec, self.form_map, flags=R.INFO_END_SCENE, **said)
        scene = self.scene(nxt)
        moves = alias is None and (prompt or self.hub.scene_quests.get(scene[0]) != self.fid)
        return self.say.info(rec, self.form_map, scene, flags=R.INFO_START_ON_END,
                             forced=SPEAKER_ALIAS if moves else None, **said)

    def _back(self, step: tuple) -> bool:
        """Whether non-menu `step` is already a phase of the scene being built.
        See: docs/fork/fo4_pipeline.md#scene-loops
        """
        return step[0] != 'menu' and self._placed(step).get(step, (None,))[0] == self.building

    def greeting(self, greets: list, topics: 'dict | None' = None, greet_list: int = 0,
                 home: 'tuple | None' = None) -> bytes:
        """The Greeting topic (b'' with no lines or speakers) of quest `home` (FormID, key, EditorID, forms a
        master's opener names; default this one) whose silent line starts the GREETING scene on activation or force
        greets `greets`. The scene's lines: the topics force greets name (`topics`, {FNV topic: FO4 package}), then
        _greetings(). The silent line needs a speaker the lines name or a talker in its talking-as list.
        See: docs/fork/fo4_pipeline.md#greeting-scene
        """
        quest, key, edid, skip = home or (self.fid, self.quest['FormID'], self.quest['EditorID'], frozenset())
        self.packaged = {i: (topics or {})[r['ParentDIAL'].upper()] for i, r in self.hub.lines.items()
                         if r['ParentDIAL'].upper() in (topics or {})}
        infos = list(self.packaged) + self._greetings()
        if not infos:
            return b''
        step = ('line', tuple(infos))
        if step not in self.labels:
            self.labels[step], self.legacy[step] = 'greeting', repr(step)
        scene, phase, index = self.scene(step)
        named = {c['p1'] for i in infos for c in parsed(self.hub.lines[i]) if c['func'] == SPEAKER_TEST}
        speakers = sorted({self.form_map[p] for p in named if p in self.form_map} - skip)
        talkers = sorted({self.form_map[(C.TALKING_AS, p)] for p in named if (C.TALKING_AS, p) in self.form_map} - skip)
        if not speakers + talkers:
            return b''
        opened = _any([(PLAYER_ACTIVATED, 0)] + [(CURRENT_PACKAGE, p) for p in greets])
        opened += _any([(IS_ID, npc) for npc in speakers] + [(IN_LIST, flst) for flst in talkers])
        greet = self.say.builder.new_id(f'INFO greeting {key}')
        self.say.silent.append((greet, False))
        if index:
            line = R.pack_info(greet, 0, (R.SILENT_LINE,), opened, scene=scene, phase=phase, phase_index=index,
                               notes='FNV GREETING', forced_alias=SPEAKER_ALIAS)
        else:
            self.say.builder.scripts.used.append(GREETING_SCRIPT)
            line = R.pack_info(greet, 0, (R.SILENT_LINE,), opened, notes='FNV GREETING',
                               vmad=object_scripts([(GREETING_SCRIPT, {'Greeting': scene, 'ScriptPackages': quest_id(self.say.builder), 'Greets': greet_list}, {})]))
        fid = self.say.builder.new_id(f'DIAL greeting {key}')
        return pack_topic(R.pack_dial(fid, f'FNV_{edid}_Greeting', quest, R.TOPIC_GREETING, 1), fid, [line])

    def player_hello(self) -> None:
        """A Hello topic whose one line, said by the player, is SILENT_LINE: it outranks vanilla's player hellos.
        See: docs/fork/fo4_spikes.md#silent-line
        """
        take, key = self.say.builder.new_id, self.quest['FormID']
        hello = take(f'INFO player hello {key}')
        self.say.silent.append((hello, True))
        line = R.pack_info(hello, 0, (R.SILENT_LINE,), _any([(IS_ID, PLAYER_BASE)]), notes='FNV silent player hello')
        fid = take(f'DIAL player hello {key}')
        dial = R.pack_dial(fid, f'FNV_{self.quest["EditorID"]}_PlayerHello', self.fid, R.TOPIC_PLAYER_HELLO, 1)
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
    """The step after FNV line `rec`: ('line', Follow Ups) or ('menu', Choices), each topic once (a topic listed
    twice is offered once); None after a Goodbye or neither."""
    follow, choices = list(dict.fromkeys(_fids(rec, 'FollowUp'))), list(dict.fromkeys(_fids(rec, 'Choice')))
    if int(rec.get('DATA.Flags', 0)) & GOODBYE or not (follow or choices):
        return None
    return ('line', tuple(follow)) if follow else ('menu', tuple(choices))


def _other(alias: int) -> int:
    """The other actor's alias of a chat (Speaker and Listener)."""
    return LISTENER_ALIAS if alias == SPEAKER_ALIAS else SPEAKER_ALIAS


def _chat_alias(step: tuple) -> 'int | None':
    """The alias saying chat step `step`; None for a player conversation's."""
    return step[1] if step[0] == 'chat' else None


def or_groups(rec: dict) -> list:
    """FNV line `rec`'s condition OR-groups, each a tuple of raw hex."""
    out, cur = [], []
    for raw in raws(rec):
        cur.append(raw)
        if not int(raw[:2], 16) & OR:
            out.append(tuple(cur))
            cur = []
    return out + [tuple(cur)] if cur else out


def _any(tests: list) -> bytes:
    """One OR-group of `tests` [(FO4 function, param 1)], each == 1 on the subject."""
    return b''.join(R.pack_ctda(OR if i < len(tests) - 1 else 0, 1.0, func, p1) for i, (func, p1) in enumerate(tests))


def opener_forms(body: bytes) -> frozenset:
    """The forms built opener INFO `body`'s GetIsID and IsInList name."""
    tests = [struct.unpack_from('<H2xI', data, 8) for tag, data in subrecords(body) if tag == b'CTDA']
    return frozenset(p1 for func, p1 in tests if func in (IS_ID, IN_LIST))
