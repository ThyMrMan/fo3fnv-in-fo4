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
is Say Once, unless its conversation can never end (no step from it ends or
returns to the Hub), when it keeps `[Leave]`. While every line of a step leads to the same
next step (in a chat, those ending it aside), the scene runs on into it; lines leading apart start their own
scene by TSCE once said, as vanilla lines do. A line with several
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

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import collections
import heapq
import itertools
import math
import re
import struct
from dataclasses import dataclass, field

from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import pack_topic
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import LEAVE, NEGATE, menu_action
from fo4_import.spike.dialogue_trace import CHOICE_VMAD, scene_vmad
from fo4_import.spike.npcs import USE_FACTIONS, USE_TRAITS, template_source
from fo4_import.spike.quest import LISTENER_ALIAS, SPEAKER_ALIAS
from fo4_import.spike.readiness import CHOICE_UNANSWERED
from fo4_import.spike.say_once import STAGE_DONE
from fo4_import.spike.script_packages import quest_id
from fo4_import.spike.skill_tags import tagged
from fo4_import.spike.say_topics import (COMPARE, GREETING, PART, PARTS, SHARED, conditions_of, parsed, raws,
                                         settled_on, with_conditions)
from script_convert.constants import FALLOUT4_CHAT_PREFIX, FALLOUT4_TALK_PREFIX

#: FNV INFO DATA flags.
GOODBYE, SAY_ONCE = 0x01, 0x04
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
#: A player line's test that never passes: the NPC it is said to is the player's base.
NEVER = R.pack_ctda(0, 1.0, IS_ID, PLAYER_BASE, run_on=R.RUN_TARGET)
#: Topics an XDI menu takes, in this order (dialogue.menu_action): four player topics, then the NPC's.
MENU_TOPICS = 5
#: Most OR-groups an option's "some answer passes" test is spread into, and most its _earlier test takes.
MAX_CLAUSES = 16
#: FNV record types holding scripts, and a script call adding an actor to a faction or taking it out (the faction).
SCRIPTED = ('SCPT', 'INFO', 'QUST', 'PACK', 'TERM')
FACTION_CHANGE = re.compile(r'\b(?:AddToFaction|RemoveFromFaction|SetFactionRank|ModFactionRank)[\s,]+(\w+)', re.I)


@dataclass
class Hub:
    """What every cell quest's conversations share: their lines, the topic list and its gates.

    `lines` {FNV INFO: record} of all cell quests, `topics` the FNV topics the
    list shows (top-level or added), `gates` {topic: FO4 global its AddTopic
    sets}, `quests` {FNV quest: (FO4 quest, FNV priority)}, `by_topic` {FNV
    topic: [(position in `lines`, INFO)] in that order}, `actors` {FNV actor
    FormID: its NPC_ or CREA record} and `unfixed` the factions scripts change,
    for speakers' fixed facts (speaker_index, speaker_facts); `joins` the steps
    more than one FNV line leads to (joined_steps); `authored` the FNV topics with a line of their own or shared,
    in any quest; `outside` and `outside_topics` the masters' lines the build does not write, as `lines` and
    `by_topic` (outside_lines).
    """

    lines: dict = field(default_factory=dict)
    topics: tuple = ()
    gates: dict = field(default_factory=dict)
    quests: dict = field(default_factory=dict)
    by_topic: dict = field(default_factory=dict)
    actors: dict = field(default_factory=dict)
    unfixed: frozenset = frozenset()
    joins: frozenset = frozenset()
    speakers: dict = field(default_factory=dict)
    authored: frozenset = frozenset()
    outside: dict = field(default_factory=dict)
    outside_topics: dict = field(default_factory=dict)


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


def menu_speakers(infos: dict) -> dict:
    """{Choices menu step (_next): the FNV actors the lines leading to it name (named_speaker)}, of `infos`
    ({quest: lines}, every quest); None for a menu a line naming no one leads to (anyone may speak it).
    See: docs/fork/fo4_pipeline.md#menu-speakers
    """
    leads = collections.defaultdict(set)
    for rec in (r for lines in infos.values() for r in lines):
        step = _next(rec)
        if step and step[0] == 'menu':
            leads[step].add(named_speaker(rec))
    return {step: None if None in found else frozenset(found) for step, found in leads.items()}


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
    return Hub(lines, tuple(topics), {}, owners, by_topic, joins=joined_steps(say.infos),
               speakers=menu_speakers(say.infos), authored=frozenset(authored))


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

    def __init__(self, say, quest: dict, quest_fid: int, form_map: dict, keyword: int, shared: Hub):
        """FNV `quest` (FO4 `quest_fid`) in `say`; steps draw on `shared`'s lines."""
        self.say, self.quest, self.fid, self.form_map, self.keyword = say, quest, quest_fid, form_map, keyword
        self.lines = {r['FormID'].upper(): r for r in say.infos.get(quest['FormID'].upper(), [])}
        self.hub, self.topics, self.scenes, self.placed, self.labels = shared, [], [], {}, {}
        self.packaged, self.legacy, self.memo, self.building = {}, {}, {}, 0

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

    def scene(self, step: tuple, fid: int = 0, flags: int = 0) -> tuple:
        """(scene, phase name, phase index) where `step` plays: ('line', FNV lines) said first passing, or
        ('menu', FNV topics); a new scene gets FNAM `flags` too.

        A new scene starts at `step` and runs on, a phase per step, while every
        line of a step leads to the same next step not yet placed and not
        _starts_own. A step said without the player whose lines lead back to
        it loops; one leading back to an earlier step ends the scene (_line).
        See: docs/fork/fo4_pipeline.md#scene-loops
        """
        if step in self.placed:
            return self.placed[step]
        fid, first = fid or self._owned('SCEN', step), step
        edid, phases, actions, menu = f'FNV_{self.quest["EditorID"]}_Scene{len(self.placed)}', [], [], False
        locked, outer, self.building = False, self.building, fid
        while step is not None and step not in self.placed:
            self.placed[step] = (fid, f'Phase{len(phases)}', len(phases))
            phases.append(self.placed[step][1])
            nxt = self._joined(step)
            loops = nxt == step and step[0] != 'menu'
            continues = loops or (nxt not in (None, MIXED) and nxt not in self.placed and not self._starts_own(nxt))
            actions.append(self._action(step, (len(actions) + 1, len(phases) - 1), edid, continues, loops))
            menu |= step[0] == 'menu'
            locked |= step[0] == 'menu' and not self._leaves(step)
            step = nxt if continues and not loops else None
        self.building = outer
        listener = LISTENER_ALIAS if first[0] == 'chat' else None
        self.scenes.append(R.pack_scen(fid, edid, self.fid, SPEAKER_ALIAS, actions, self.keyword if menu else 0,
                                       tuple(phases), (R.SCENE_NO_EXIT if locked else 0) | flags, listener,
                                       scene_vmad(len(phases))))
        return self.placed[first]

    def _starts_own(self, step: tuple) -> bool:
        """Whether `step` (a chat's inner step) is the topic list or a join.
        See: docs/fork/fo4_pipeline.md#scene-joins
        """
        inner = step[2] if step[0] == 'chat' else step
        return inner == ('menu', self.hub.topics) or inner in self.hub.joins

    def _key(self, step: tuple) -> str:
        """The FormID key of `step`: what FNV authored, not the lines found today (the Hub's topic list and a
        script's topic grow as more converts), so ids stay put as content arrives.
        See: docs/fork/fo4_pipeline.md#npcs
        """
        if step[0] == 'menu' and step[1] == self.hub.topics:
            return 'menu hub'
        return self.labels.get(step, repr(step))

    def _owned(self, kind: str, step: tuple) -> int:
        """The FormID of `step`'s `kind` record (SCEN, DIAL), keyed by _key(); a step relabelled keeps the id its
        old key gave (`legacy`).
        See: docs/fork/fo4_pipeline.md#formid-ledger
        """
        key = f'{kind} {self.quest["FormID"]} {self._key(step)}'
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
        name, owner = f'{edid}_{place[1]}', f'{self.quest["FormID"]} {self._key(step)}'
        take = self.say.builder.new_id
        if step[0] == 'menu':
            player, npc = [], []
            speakers = None if step[1] == self.hub.topics else self.hub.speakers.get(step)
            for dial in step[1]:
                self._option(dial, (player, npc), continues, owner, speakers)
            if self._leaves(step):
                self.say.builder.counts['[Leave] on a never-ending Choices menu'] += step[1] != self.hub.topics
                player.append(R.pack_info(take(f'INFO leave {owner}'), 0, (LEAVE,), prompt=LEAVE, vmad=CHOICE_VMAD))
                exit_fid = take(f'INFO exit {owner}')
                self.say.silent.append((exit_fid, False))
                npc.append(R.pack_info(exit_fid, R.INFO_END_SCENE, (R.SILENT_LINE,), notes='FNV Tab exit',
                                       vmad=CHOICE_VMAD))
            slots = iter(range(MENU_TOPICS))
            topics, action = menu_action(lambda: take(f'DIAL {owner}', key=f'DIAL {owner} slot {next(slots)}'),
                                         (name, self.fid, SPEAKER_ALIAS), player, npc, place)
            self.topics += topics
            return action
        alias = _chat_alias(step)
        lines = [line for line in (self._line(r, continues, alias, owner) for r in self._members(step)) if line]
        topic = self._owned('DIAL', step)
        self.topics.append(pack_topic(R.pack_dial(topic, name, self.fid, R.TOPIC_SCENE, len(lines)), topic, lines))
        if alias is None:
            return R.pack_dialogue_action(place[0], SPEAKER_ALIAS, topic, place[1], looping=looping)
        return R.pack_dialogue_action(place[0], alias, topic, place[1], _other(alias), looping)

    def _option(self, dial: str, menu: tuple, continues: bool, owner: str, speakers: 'frozenset | None' = None) -> None:
        """Add FNV topic `dial` to menu `menu` (player, npc) of step `owner`: an option per prompt and quest among its
        lines (FNV shows the first passing line's; a quest's conditions scope its speakers), each padded to its
        answers and hidden while a line FNV tries first passes (_earlier). Given the menu's `speakers`
        (menu_speakers), a line none of them can say (_can_say) is left out.
        See: docs/fork/fo4_pipeline.md#menu-speakers
        """
        prompts, order = {}, []
        for rec in self._sayable(dial, speakers):
            key = (rec.get('Prompt') or self.say.dials[dial].get('FULL', ''), rec.get('QSTI.Quest', ''))
            prompts.setdefault(key, []).append(part(rec, 1))
            order.append((key, rec, named_speaker(rec)))
        added = [self._prompt(dial, key[0], members, menu, continues, f'{owner} {dial} for {key[1]}',
                              self._earlier(key, order))
                 for key, members in prompts.items()]
        if not any(added):
            self._unanswered(dial, bool(prompts))

    def _unanswered(self, dial: str, sayable: bool) -> None:
        """Record FNV topic `dial` left with no option: when FNV never answers it either (no line at all, or none
        the menu's speakers can say), only a count; else a CHOICE_UNANSWERED entry with its cause (`not built`: its
        lines' quests are not in the build; `condition`: no line converts, see their LINE_LEFT_OUT entries).
        See: docs/fork/fo4_plan_dialogue_reach.md#framework
        """
        counts, has = self.say.builder.counts, bool(self.hub.by_topic.get(dial))
        if not sayable and (has or dial not in self.hub.authored):
            counts[f'choice FNV never answers ({"speaker-filter" if has else "no line"})'] += 1
            return
        counts['choice without a line in the quest'] += 1
        self.say.builder.readiness.add(CHOICE_UNANSWERED, self.quest['FormID'],
                                       f'{self.say.dials[dial].get("EditorID", dial)} ({dial}): '
                                       f'{"condition" if has else "not built"}')

    def _sayable(self, dial: str, speakers: 'frozenset | None') -> list:
        """The Hub's lines of FNV topic `dial` one of `speakers` can say (all when None); those left out counted."""
        lines = [self.hub.lines[i] for _, i in self.hub.by_topic.get(dial, ())]
        if speakers is None:
            return lines
        kept = [rec for rec in lines if any(self._can_say(actor, rec) for actor in speakers)]
        self.say.builder.counts['menu lines no speaker of the menu can say'] += len(lines) - len(kept)
        return kept

    def _prompt(self, dial: str, text: str, members: list, menu: tuple, continues: bool, place: str,
                earlier: bytes = b'') -> bool:
        """Add one option of FNV topic `dial` with prompt `text` answered by `members` to `menu` (player, npc),
        its pads (one per further answer) on the prompt's conditions; False when no line of it converts. All Say
        Once answers hide it by their markers once all are said, never by FO4's Say Once on the prompt, which pads
        outlive (a blank option). `place` keys its FormIDs; `earlier` CTDAs hide it while a line FNV tries first passes.
        See: docs/fork/fo4_pipeline.md#blank-choices
        """
        player, npc = menu
        said = [(r, self._line(r, continues, place=place)) for r in members]
        said = [(r, a) for r, a in said if a]
        if not said:
            return False
        once = R.INFO_SAY_ONCE if all(int(r.get('DATA.Flags', 0)) & SAY_ONCE for r in members) else 0
        if len(members) == 1:
            shown = conditions_of(members[0], self.form_map, self.say.script_vars, swap=True) or b''
        else:
            shown = self._shared(members) + self._either(members) + self.speakers(members)
        shown += earlier + self._running(members[0]) + self._gate(dial)
        shown += self.say.once.unsaid([r['FormID'] for r in members]) if once else b''
        label, take = tagged(text, members), self.say.builder.new_id
        keys = [self._slot(dial, text, rec, i, place) for i, (rec, _) in enumerate(said)]
        player += [R.pack_info(take(owner, key=key), 0, (label,), shown, prompt=label, vmad=CHOICE_VMAD) if not i
                   else R.pack_info(take(owner, key=key), conditions=shown, vmad=CHOICE_VMAD)
                   for i, (owner, key) in enumerate(keys)]
        npc += [a for _, a in said]
        return True

    def _slot(self, dial: str, text: str, rec: dict, index: int, place: str) -> tuple:
        """(owner, key) of the option or pad (`index` 0 or more) of prompt `text` of FNV topic `dial` at `place`
        beside answer `rec`: a master line's own slot (its master prompt's option or pad, by its place among that
        prompt's master lines) while unused, so it overrides the master's in place as its answer does; else by `text`.
        Options and answers pair by position, so a new option or pad beside the master's breaks them.
        See: docs/fork/fo4_plugin_layout.md#dlc-prompts
        """
        fid = rec['FormID'].upper()
        old = None if rec.get(SHARED) else self.say.master_infos.get(fid)
        slots = [(f'INFO prompt {dial} {text}', index)]
        if old and old['ParentDIAL'].upper() == dial.upper():
            prompt, at = self.say.master_prompts[fid]
            slots.insert(0, (f'INFO prompt {dial} {prompt}', at))
        keys = [(owner, f'{owner} at {place}' + (f' pad {at}' if at else '')) for owner, at in slots]
        return next((k for k in keys if k[1] not in self.say.builder.keyed), keys[-1])

    def _shared(self, members: list) -> bytes:
        """CTDAs (from the player's side) of the condition OR-groups every line in `members` has, besides a lone
        speaker test; b'' when one does not convert."""
        each = [or_groups(r) for r in members]
        common = [raw for group in each[0] if all(group in other for other in each[1:])
                  and not (len(group) == 1 and C.parse(group[0])['func'] == SPEAKER_TEST) for raw in group]
        shared = {f'Condition[{i}].Raw': raw for i, raw in enumerate(common)}
        return conditions_of(shared, self.form_map, self.say.script_vars, swap=True) or b''

    def _either(self, members: list) -> bytes:
        """OR-groups (from the player's side) holding when some line in `members` passes what it adds to the groups
        they share, its speaker test and a Say Once line's unsaid marker counted as groups: the groups distributed,
        one OR-group per pick of a group from each line, so the option needs an answer that can play for this
        speaker; past MAX_CLAUSES, one OR-group of a group per line (one_each); b'' when a line adds nothing (it
        always answers).
        See: docs/fork/fo4_pipeline.md#dialogue-conditions
        """
        each = [or_groups(r) for r in members]
        rest = [[g for g in groups if not all(g in other for other in each)]
                + ([((SAY_ONCE, r['FormID']),)] if int(r.get('DATA.Flags', 0)) & SAY_ONCE else [])
                for groups, r in zip(each, members)]
        if not all(rest):
            return b''
        picks = itertools.product(*rest) if math.prod(len(r) for r in rest) <= MAX_CLAUSES else [one_each(rest)]
        clauses = [self._or_group(tests) for tests in dict.fromkeys(
            tuple(dict.fromkeys(t for g in pick for t in g)) for pick in picks)]
        return b'' if None in clauses else b''.join(clauses)

    def _or_group(self, tests: tuple) -> 'bytes | None':
        """One OR-group of FNV raw tests and (SAY_ONCE, line) unsaid markers as FO4 CTDAs from the player's side;
        b'' when it always passes, None when its tests do not convert."""
        found = [t for t in tests if isinstance(t, str)]
        ored = {f'Condition[{i}].Raw': f'{int(raw[:2], 16) & ~OR | (OR if i < len(found) - 1 else 0):02x}{raw[2:]}'
                for i, raw in enumerate(found)}
        fnv = conditions_of(ored, self.form_map, self.say.script_vars, swap=True) if found else NEVER
        lines = [t[1] for t in tests if not isinstance(t, str)]
        return fnv and _any_of([fnv, self.say.once.unsaid(lines) if lines else b''])

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

    def _earlier(self, key: tuple, order: list) -> bytes:
        """CTDAs (player's side) holding while no line of another option of the topic that FNV tries first passes:
        each such line that can pass beside a later line of option `key` (_together) fails, or a line of the
        option before it passes (_unless); `order` [(option, FNV line, speaker)] in Hub order. One that does not
        convert, or would take the option past MAX_CLAUSES OR-groups, is not tested (counted).
        See: docs/fork/fo4_pipeline.md#one-option-per-topic
        """
        own = [(at, rec, speaker) for at, (other, rec, speaker) in enumerate(order) if other == key]
        out, counts = {}, self.say.builder.counts
        for at, (other, rec, speaker) in enumerate(order):
            beside = [(j, mine) for j, mine, by in own if other != key and self._together(rec, speaker, mine, by)]
            if not beside or beside[-1][0] < at:
                continue
            tests = self._unless(self._unpassed(rec), [mine for j, mine in beside if j < at], speaker)
            fits = tests is not None and len(out | dict.fromkeys(tests)) <= MAX_CLAUSES
            counts['earlier line tested' if fits else 'earlier line not tested'] += 1
            out |= dict.fromkeys(tests) if fits else {}
        return b''.join(out)

    def _together(self, rec: dict, speaker, mine: dict, by) -> bool:
        """Whether FNV lines `rec` and `mine`, of speakers `speaker` and `by` (named_speaker), can pass for one
        actor: the same named speaker, or a named one whose fixed facts let the other line pass."""
        if speaker and by:
            return speaker == by
        if speaker or by:
            return self._can_say(speaker or by, mine if speaker else rec)
        return True

    def _can_say(self, actor: int, rec: dict) -> bool:
        """Whether FNV actor `actor`'s fixed facts (speaker_facts) let FNV line `rec` pass."""
        key = ('says', actor, rec['FormID'])
        if key not in self.memo:
            self.memo[key] = settled_on(rec, speaker_facts(self.hub, actor)) is not None
        return self.memo[key]

    def _unless(self, clauses: 'list | None', before: list, speaker) -> 'list | None':
        """`clauses` (OR-groups holding while a line of `speaker` fails), each ORed with one group of every line in
        `before` (one of them passes, _passing), less that speaker's own test; None when one does not convert or
        there would be more than MAX_CLAUSES."""
        if clauses is None or not before:
            return clauses
        own = R.pack_ctda(0, 1.0, IS_ID, self.form_map.get(speaker, 0), run_on=R.RUN_TARGET)
        groups = [None if g is None else [t for t in g if t != own] for g in map(self._passing, before)]
        if None in groups or len(clauses) * math.prod(len(g) for g in groups) > MAX_CLAUSES:
            return None
        return [_any_of(list(pick) + [c]) for c in clauses for pick in itertools.product(*groups)]

    def _unpassed(self, rec: dict) -> 'list | None':
        """OR-groups (player's side) all holding while FNV line `rec` cannot pass in this quest's scenes: a test of
        each of its condition groups fails (one OR-group per pick of a test from each, at most MAX_CLAUSES), or
        it is held back (_held); None when a test does not convert.
        See: docs/fork/fo4_pipeline.md#one-option-per-topic
        """
        key = ('fails', rec['FormID'])
        if key not in self.memo:
            groups = or_groups(rec)
            picks = list(itertools.product(*groups)) if math.prod(len(g) for g in groups) <= MAX_CLAUSES else []
            clauses = [clause for pick in picks for clause in self._clauses(pick)]
            clauses = [self._clause(rec, tests, lists) for tests, lists in clauses]
            self.memo[key] = None if not picks or None in clauses else [c for c in clauses if c]
        return self.memo[key]

    def _clauses(self, pick: tuple) -> list:
        """[(raw tests, talking-as lists)] of `pick`, one per branch of each talked-through speaker test in it: its
        GetIsID, or its actor's talking-as list, so a line an intercom says as that actor fails only when both do.
        See: docs/fork/fo4_pipeline.md#one-option-per-topic
        """
        branches = []
        for raw in pick:
            flst = C.talking_list(C.parse(raw), self.form_map)
            branches.append([(raw, 0)] + ([('', flst)] if flst else []))
        return [(tuple(raw for raw, _ in combo if raw), [flst for _, flst in combo if flst])
                for combo in itertools.product(*branches)]

    def _clause(self, rec: dict, pick: tuple, lists: list) -> 'bytes | None':
        """One OR-group (player's side): a test in `pick` (raw tests of FNV line `rec`) fails, the speaker is in
        none of the talking-as `lists`, or `rec` is held back (_held); b'' when it always holds, None when a test
        does not convert."""
        fnv = self._tests(rec, [negated(raw, i < len(pick) - 1) for i, raw in enumerate(pick)]) if pick else NEVER
        if not fnv:
            return fnv
        off = [R.pack_ctda(0, 0.0, IN_LIST, flst, run_on=R.RUN_TARGET) for flst in lists]
        return _any_of([R.pack_ctda(0, value, func, p1, p2) for func, value, p1, p2 in self._held(rec)] + [fnv] + off)

    def _passing(self, rec: dict) -> 'list | None':
        """OR-groups (player's side) all holding while FNV line `rec` passes here: its condition groups that can
        fail, its Hub quest running and (Say Once) unsaid; [NEVER] when it never passes, None when one does not
        convert."""
        key = ('passes', rec['FormID'])
        if key not in self.memo:
            groups = [self._tests(rec, list(group)) for group in or_groups(rec)]
            held = [R.pack_ctda(0, 1.0 - value, func, p1, p2) for func, value, p1, p2 in self._held(rec)]
            self.memo[key] = None if None in groups else [NEVER] if NEVER in groups else [g for g in groups if g] + held
        return self.memo[key]

    def _tests(self, rec: dict, tests: list) -> 'bytes | None':
        """FNV raw `tests` (one OR-group) of line `rec` from the player's side: b'' when they always hold, NEVER
        when they never can (or are none), None when one does not convert."""
        probe = with_conditions(rec, tests)
        settled = C.without_absent(parsed(probe), self.form_map) if tests else None
        if not settled:
            return NEVER if settled is None else b''
        return conditions_of(probe, self.form_map, self.say.script_vars, swap=True)

    def _held(self, rec: dict) -> list:
        """FO4 tests [(function, value, param 1, param 2)], each true while FNV line `rec`'s copy here cannot play
        whatever its conditions: its Hub quest is stopped, or (Say Once) its marker stage is done."""
        quest = self._hub_quest(rec)
        out = [(QUEST_RUNNING, 0.0, quest, 0)] if quest else []
        if int(rec.get('DATA.Flags', 0)) & SAY_ONCE:
            out.append((STAGE_DONE, 1.0, self.say.once.quest, self.say.once.stage(rec['FormID'])))
        return out

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

    def _line(self, rec: dict, continues: bool, alias: 'int | None' = None, place: str = '') -> bytes:
        """FNV line `rec` as the speaker's INFO (said by chat `alias`, its Target tests on the other actor) at
        `place` (its step): the scene runs on (`continues`), or it starts what follows once said, or ends."""
        extra, target = self._running(rec), None if alias is None else _other(alias)
        package = self.packaged.get(hub_key(rec)) if rec.get(PART, 1) == 1 else None
        extra += R.pack_ctda(0, 1.0, CURRENT_PACKAGE, package) if package else b''
        said = {'extra': extra, 'target': target, 'owner': self.fid, 'place': place}
        nxt = self._next(rec, alias)
        if continues and nxt is not None:
            return self.say.info(rec, self.form_map, **said)
        if nxt is None or self._back(nxt):
            return self.say.info(rec, self.form_map, flags=R.INFO_END_SCENE, **said)
        return self.say.info(rec, self.form_map, self.scene(nxt), flags=R.INFO_START_ON_END, **said)

    def _back(self, step: tuple) -> bool:
        """Whether non-menu `step` is already a phase of the scene being built.
        See: docs/fork/fo4_pipeline.md#scene-loops
        """
        return step[0] != 'menu' and self.placed.get(step, (None,))[0] == self.building

    def greeting(self, greets: list, topics: 'dict | None' = None, greet_list: int = 0) -> None:
        """A Greeting topic whose silent line starts the GREETING talk scene, on activation or force greets `greets`.

        The scene's lines: those of the topics force greets name (`topics`, {FNV topic: FO4 package}), each
        needing its package current, then _greetings(). Its SILENT_LINE needs activation or a running force
        greet, and a speaker the GREETING lines name or a talker in its talking-as list; its GREETING_SCRIPT
        opens the scene and marks a force greet in `greet_list` spoken (greet_once).
        See: docs/fork/fo4_pipeline.md#greeting-scene
        """
        self.packaged = {i: (topics or {})[r['ParentDIAL'].upper()] for i, r in self.hub.lines.items()
                         if r['ParentDIAL'].upper() in (topics or {})}
        infos = list(self.packaged) + self._greetings()
        if not infos:
            return
        named = {c['p1'] for i in infos for c in parsed(self.hub.lines[i]) if c['func'] == SPEAKER_TEST}
        speakers = sorted({self.form_map[p] for p in named if p in self.form_map})
        talkers = sorted({self.form_map[(C.TALKING_AS, p)] for p in named if (C.TALKING_AS, p) in self.form_map})
        opened = _any([(PLAYER_ACTIVATED, 0)] + [(CURRENT_PACKAGE, p) for p in greets])
        opened += _any([(IS_ID, npc) for npc in speakers] + [(IN_LIST, flst) for flst in talkers])
        step = ('line', tuple(infos))
        if step not in self.labels:
            self.labels[step], self.legacy[step] = 'greeting', repr(step)
        scene, phase, index = self.scene(step)
        greet = self.say.builder.new_id(f'INFO greeting {self.quest["FormID"]}')
        self.say.silent.append((greet, False))
        if index:
            line = R.pack_info(greet, 0, (R.SILENT_LINE,), opened, scene=scene, phase=phase, phase_index=index,
                               notes='FNV GREETING', forced_alias=SPEAKER_ALIAS)
        else:
            self.say.builder.scripts.used.append(GREETING_SCRIPT)
            line = R.pack_info(greet, 0, (R.SILENT_LINE,), opened, notes='FNV GREETING',
                               vmad=object_scripts([(GREETING_SCRIPT, {'Greeting': scene, 'ScriptPackages': quest_id(self.say.builder), 'Greets': greet_list}, {})]))
        fid = self.say.builder.new_id(f'DIAL greeting {self.quest["FormID"]}')
        dial = R.pack_dial(fid, f'FNV_{self.quest["EditorID"]}_Greeting', self.fid, R.TOPIC_GREETING, 1)
        self.topics.append(pack_topic(dial, fid, [line]))

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


def one_each(rest: list) -> tuple:
    """Per line in `rest`, its group most lines share.
    See: docs/fork/fo4_pipeline.md#dialogue-conditions
    """
    shared = collections.Counter(g for groups in rest for g in set(groups))
    return tuple(max(groups, key=lambda g: shared[g]) for groups in rest)


def negated(raw: str, or_next: bool) -> str:
    """FNV test `raw` (hex) negated, ORed with the next when `or_next`."""
    op = int(raw[:2], 16)
    return f'{op & ~(COMPARE | OR) | NEGATE[op & COMPARE] | (OR if or_next else 0):02x}{raw[2:]}'


def named_speaker(rec: dict) -> 'int | None':
    """The NPC FNV line `rec` names alone in a condition group (GetIsID == 1 on the subject); None: anyone."""
    for group in or_groups(rec):
        cond = C.parse(group[0])
        if len(group) == 1 and cond['func'] == SPEAKER_TEST and cond['value'] == 1.0 and cond['run_on'] == R.RUN_SUBJECT \
                and not cond['op_flags'] & COMPARE:
            return cond['p1']
    return None


def speaker_index(export_dir) -> tuple:
    """({FNV actor FormID: NPC_ or CREA record}, the FNV factions a script adds actors to or takes them from)."""
    actors = {int(r['FormID'], 16): r for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}
    names = {r['EditorID'].lower(): int(r['FormID'], 16) for r in export_records(export_dir, 'FACT') if r.get('EditorID')}
    changed = {m.lower() for sig in SCRIPTED for r in export_records(export_dir, sig) for v in r.values()
               if isinstance(v, str) for m in FACTION_CHANGE.findall(v)}
    return actors, frozenset(names[n] for n in changed if n in names)


def speaker_facts(shared: Hub, actor: int) -> dict:
    """FNV actor `actor`'s fixed facts for C.speaker_settle: itself, its voice type and its factions, through its
    templates (npcs.template_source); a faction a script changes (`shared.unfixed`) stays unsettled."""
    facts, rec = {'GetIsID': actor, 'unfixed': shared.unfixed}, shared.actors.get(actor)
    if rec is None:
        return facts
    traits, lost = template_source(shared.actors, rec, USE_TRAITS)
    if not lost and traits.get('VTCK.Voice'):
        facts['GetIsVoiceType'] = int(traits['VTCK.Voice'], 16)
    member, gone = template_source(shared.actors, rec, USE_FACTIONS)
    if not gone:
        facts['GetInFaction'] = frozenset(int(member[f'Faction[{i}].FormID'], 16)
                                          for i in range(int(member.get('FactionCount', 0) or 0))
                                          if int(member[f'Faction[{i}].Rank']) >= 0)
    return facts


def _any_of(pieces: list) -> bytes:
    """One OR-group of FO4 condition `pieces`, NEVER ones dropped; NEVER if none."""
    pieces = [p for p in pieces if p and p != NEVER]
    return b''.join(_chained(p) for p in pieces[:-1]) + pieces[-1] if pieces else NEVER


def _chained(tests: bytes) -> bytes:
    """FO4 condition subrecords `tests` (CTDA, CIS1, CIS2), their last CTDA ORed with what follows."""
    at, last = 0, -1
    while at < len(tests):
        last = at if tests[at:at + 4] == b'CTDA' else last
        at += 6 + struct.unpack_from('<H', tests, at + 4)[0]
    return tests[:last + 6] + bytes([tests[last + 6] | OR]) + tests[last + 7:] if last >= 0 else tests


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
