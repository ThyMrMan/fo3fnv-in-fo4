"""An FNV quest's conversations as FO4 scenes, for the cell spike.

FNV's StartConversation opens the speaker's GREETING (or a named topic): the
first passing line plays, then its Follow Ups (more of the speaker's lines,
first passing) or its Choices (topics the player picks from). On FO4 a script
starts the topic's scene (`TES4Talk_<topic>`; TES4Polyfill.StartConversation
puts the speaker in the quest's Speaker alias). Each step is a scene phase:
lines a Dialogue action saying a topic of them, Choices an XDI menu (one
option per topic, its lines the answers behind padding so the first passing
one answers, and `[Leave]`). While every line of a step leads to the same
next step, the scene runs on into it; lines leading apart start their own
scene by TSCE, as 382 vanilla Dialogue-action lines do. A Goodbye line, or
one followed by nothing, ends the conversation. An FO4 Greeting topic's
silent line starts the GREETING scene when the player activates the
speaker or a converted force greet runs.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import LEAVE, menu_action
from fo4_import.spike.quest import SPEAKER_ALIAS
from fo4_import.spike.say_topics import CONVERSATION, conditions_of
from script_convert.constants import FALLOUT4_TALK_PREFIX

#: FNV INFO DATA flags.
GOODBYE, SAY_ONCE = 0x01, 0x04
#: FNV's GREETING topic.
GREETING = '000000C8'
#: CTDA OR-with-next bit; FO4 GetPlayerActivated, GetIsCurrentPackage, GetIsID.
OR, PLAYER_ACTIVATED, CURRENT_PACKAGE = 0x01, C.FO4.index('GetPlayerActivated'), C.FO4.index('GetIsCurrentPackage')
SPEAKER_TEST = 'GetIsID'
IS_ID = C.FO4.index(SPEAKER_TEST)
#: _joined's answer when a step's lines lead to different steps.
MIXED = ('mixed',)


def _fids(rec: dict, key: str) -> list:
    """A Key[i] FormID list, as the export's upper-case hex."""
    return [rec[f'{key}[{i}]'].upper() for i in range(int(rec.get(f'{key}Count', 0) or 0))]


class Conversations:
    """The scenes and scene topics of one FNV quest's conversations; `topics` and `scenes` hold the records."""

    def __init__(self, say, quest: dict, quest_fid: int, form_map: dict, keyword: int):
        """Lines of FNV `quest` (FO4 `quest_fid`) from `say` (a SayTopics); `keyword` marks XDI menus."""
        self.say, self.quest, self.fid, self.form_map, self.keyword = say, quest, quest_fid, form_map, keyword
        self.lines = {r['FormID'].upper(): r for r in say.infos.get(quest['FormID'].upper(), [])}
        self.quest_vars = say.variables.get(quest.get('SCRI', '').upper(), {})
        self.topics, self.scenes, self.placed = [], [], {}

    def has_lines(self) -> bool:
        """True when the quest has lines outside its scripted Conversation topics."""
        return any(self.say.dials[r['ParentDIAL']].get('DATA.Type') != CONVERSATION for r in self.lines.values())

    def talk(self, prop: str, fid: int) -> bool:
        """Build scene `fid` that `prop` (`TES4Talk_<topic>`) starts, if the topic has lines in this quest."""
        topic = prop[len(FALLOUT4_TALK_PREFIX):].lower()
        infos = [i for i, r in self.lines.items() if self.say.dials[r['ParentDIAL']]['EditorID'].lower() == topic]
        if infos:
            self.scene(('line', tuple(infos)), fid)
        return bool(infos)

    def scene(self, step: tuple, fid: int = 0) -> tuple:
        """(scene, phase) where `step` plays: ('line', FNV lines) said first passing, or ('menu', FNV topics).

        A new scene starts at `step` and runs on, a phase per step, while every
        line of a step leads to the same next step not yet placed.
        """
        if step in self.placed:
            return self.placed[step]
        fid, first = fid or self.say.builder.new_id(), step
        edid, phases, actions, menu = f'FNV_{self.quest["EditorID"]}_Scene{len(self.placed)}', [], [], False
        while step is not None and step not in self.placed:
            self.placed[step] = (fid, f'Phase{len(phases)}')
            phases.append(self.placed[step][1])
            nxt = self._joined(step)
            continues = nxt not in (None, MIXED) and nxt not in self.placed
            actions.append(self._action(step, (len(actions) + 1, len(phases) - 1), edid, continues))
            menu |= step[0] == 'menu'
            step = nxt if continues else None
        self.scenes.append(R.pack_scen(fid, edid, self.fid, SPEAKER_ALIAS, actions, self.keyword if menu else 0,
                                       tuple(phases)))
        return self.placed[first]

    def _members(self, step: tuple) -> list:
        """The FNV lines of `step`: its lines, or every line of its menu's topics."""
        if step[0] == 'line':
            return [self.lines[i] for i in step[1] if i in self.lines]
        return [r for r in self.lines.values() if r['ParentDIAL'].upper() in step[1]]

    def _joined(self, step: tuple):
        """The step all of `step`'s lines lead to: None if they end, MIXED if they differ."""
        nexts = {_next(r) for r in self._members(step)}
        return nexts.pop() if len(nexts) == 1 else (MIXED if nexts else None)

    def _action(self, step: tuple, place: tuple, edid: str, continues: bool) -> bytes:
        """The scene action playing `step` at `place` (index, phase); its lines run on when `continues`."""
        name = f'{edid}_{place[1]}'
        if step[0] == 'menu':
            player, npc = [], []
            for dial in step[1]:
                self._option(dial, player, npc, continues)
            player.append(R.pack_info(self.say.builder.new_id(), 0, (LEAVE,), prompt=LEAVE))
            npc.append(R.pack_info(self.say.builder.new_id(), R.INFO_END_SCENE, ('...',), notes='FNV Tab exit'))
            topics, action = menu_action(self.say.builder.new_id, (name, self.fid, SPEAKER_ALIAS), player, npc, place)
            self.topics += topics
            return action
        lines = [line for line in (self._line(r, continues) for r in self._members(step)) if line]
        topic = self.say.builder.new_id()
        self.topics.append(pack_topic(R.pack_dial(topic, name, self.fid, R.TOPIC_SCENE, len(lines)), topic, lines))
        return R.pack_dialogue_action(place[0], SPEAKER_ALIAS, topic, place[1])

    def _option(self, dial: str, player: list, npc: list, continues: bool) -> None:
        """Add FNV topic `dial` to a menu: one player line, padded to its answers, the quest's lines in it."""
        members = [r for r in self.lines.values() if r['ParentDIAL'].upper() == dial]
        answers = [a for a in (self._line(r, continues) for r in members) if a]
        if not answers:
            self.say.builder.counts['choice without a line in the quest'] += 1
            return
        text = members[0].get('Prompt') or self.say.dials[dial].get('FULL', '')
        once = R.INFO_SAY_ONCE if all(int(r.get('DATA.Flags', 0)) & SAY_ONCE for r in members) else 0
        shown = conditions_of(members[0], self.form_map, self.quest_vars, swap=True) if len(members) == 1 else b''
        player.append(R.pack_info(self.say.builder.new_id(), once, (text,), shown or b'', prompt=text))
        player += [R.pack_info(self.say.builder.new_id()) for _ in answers[1:]]
        npc += answers

    def _line(self, rec: dict, continues: bool) -> bytes:
        """FNV line `rec` as the speaker's INFO: the scene runs on (`continues`), or it starts what follows, or ends."""
        if continues:
            return self.say.info(rec, self.form_map, self.quest_vars)
        nxt = _next(rec)
        if nxt is None:
            return self.say.info(rec, self.form_map, self.quest_vars, flags=R.INFO_END_SCENE)
        return self.say.info(rec, self.form_map, self.quest_vars, self.scene(nxt))

    def greeting(self, greets: list) -> None:
        """A Greeting topic whose silent line starts the GREETING talk scene, for activation or force greets `greets`.

        The line says '...' (one without a response starts nothing). It puts its speaker in the Speaker alias and needs GetPlayerActivated
        or a running force greet (else FO4's hello barks open it unasked) and a
        speaker the GREETING lines name; the lines themselves stay in the scene,
        so each Say Once line exists once.
        See: docs/fork/fo4_spikes.md#spike-1-force-greet
        """
        infos = [i for i, r in self.lines.items() if r['ParentDIAL'].upper() == GREETING]
        if not infos:
            return
        speakers = sorted({self.form_map[c['p1']] for i in infos for c in _conditions(self.lines[i])
                           if c['func'] == SPEAKER_TEST and c['p1'] in self.form_map})
        opened = _any([(PLAYER_ACTIVATED, 0)] + [(CURRENT_PACKAGE, p) for p in greets])
        opened += _any([(IS_ID, npc) for npc in speakers])
        scene, phase = self.scene(('line', tuple(infos)))
        line = R.pack_info(self.say.builder.new_id(), 0, ('...',), opened, scene=scene, phase=phase,
                           notes='FNV GREETING', forced_alias=SPEAKER_ALIAS)
        fid = self.say.builder.new_id()
        dial = R.pack_dial(fid, f'FNV_{self.quest["EditorID"]}_Greeting', self.fid, R.TOPIC_GREETING, 1)
        self.topics.append(pack_topic(dial, fid, [line]))


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
