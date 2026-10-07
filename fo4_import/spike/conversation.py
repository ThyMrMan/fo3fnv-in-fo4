"""An FNV quest's conversations as FO4 scenes, for the cell spike.

FNV's StartConversation opens the speaker's GREETING (or a named topic): the
first passing line plays, then its Follow Ups (more of the speaker's lines,
first passing) or its Choices (topics the player picks from). On FO4 a script
starts the topic's scene (`TES4Talk_<topic>`; TES4Polyfill.StartConversation
puts the speaker in the quest's Speaker alias). A line scene is one Dialogue
action saying a topic of lines; each line starts what follows it (INFO TSCE,
as 382 vanilla Dialogue-action lines do). Follow Ups are a line scene, Choices
an XDI menu scene: one option per topic, its lines the answers behind padding
so the first passing one answers, and `[Leave]`. A Goodbye line, or one
followed by nothing, ends the conversation.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from fo4_import.base.writer import pack_topic
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import LEAVE, menu_records
from fo4_import.spike.quest import SPEAKER_ALIAS
from fo4_import.spike.say_topics import CONVERSATION, conditions_of
from script_convert.constants import FALLOUT4_TALK_PREFIX

#: FNV INFO DATA flags.
GOODBYE, SAY_ONCE = 0x01, 0x04
LINE_PHASE, MENU_PHASE = 'Line', 'Menu'


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
        self.topics, self.scenes, self.built = [], [], {}

    def has_lines(self) -> bool:
        """True when the quest has lines outside its scripted Conversation topics."""
        return any(self.say.dials[r['ParentDIAL']].get('DATA.Type') != CONVERSATION for r in self.lines.values())

    def talk(self, prop: str, fid: int) -> bool:
        """Build scene `fid` that `prop` (`TES4Talk_<topic>`) starts, if the topic has lines in this quest."""
        topic = prop[len(FALLOUT4_TALK_PREFIX):].lower()
        infos = [i for i, r in self.lines.items() if self.say.dials[r['ParentDIAL']]['EditorID'].lower() == topic]
        if infos:
            self.line_scene(infos, fid)
        return bool(infos)

    def _edid(self, kind: str) -> str:
        """An EditorID for the quest's next scene of `kind`."""
        return f'FNV_{self.quest["EditorID"]}_{kind}{len(self.built)}'

    def line_scene(self, infos: list, fid: int = 0) -> int:
        """The scene (made once) where the speaker says the first passing of FNV lines `infos`."""
        key = ('line', *infos)
        if key not in self.built:
            self.built[key] = fid = fid or self.say.builder.new_id()
            edid, topic = self._edid('Line'), self.say.builder.new_id()
            lines = [line for line in (self.npc_line(self.lines[i]) for i in infos if i in self.lines) if line]
            self.topics.append(pack_topic(R.pack_dial(topic, edid, self.fid, R.TOPIC_SCENE, len(lines)), topic, lines))
            action = R.pack_dialogue_action(1, SPEAKER_ALIAS, topic)
            self.scenes.append(R.pack_scen(fid, edid, self.fid, SPEAKER_ALIAS, action, 0, LINE_PHASE))
        return self.built[key]

    def menu(self, choices: list) -> int:
        """The XDI menu scene (made once) offering FNV topics `choices`."""
        key = ('menu', *choices)
        if key not in self.built:
            self.built[key] = fid = self.say.builder.new_id()
            edid, player, npc = self._edid('Menu'), [], []
            for dial in choices:
                self._option(dial, player, npc)
            player.append(R.pack_info(self.say.builder.new_id(), 0, (LEAVE,), prompt=LEAVE))
            npc.append(R.pack_info(self.say.builder.new_id(), R.INFO_END_SCENE, ('...',), notes='FNV Tab exit'))
            topics, scene = menu_records(self.say.builder.new_id, (fid, edid, self.fid, SPEAKER_ALIAS), player, npc,
                                         self.keyword)
            self.topics += topics
            self.scenes.append(scene)
        return self.built[key]

    def _option(self, dial: str, player: list, npc: list) -> None:
        """Add FNV topic `dial` to a menu: one player line, padded to its answers, the quest's lines in it."""
        members = [r for r in self.lines.values() if r['ParentDIAL'].upper() == dial]
        answers = [a for a in (self.npc_line(r) for r in members) if a]
        if not answers:
            self.say.builder.counts['choice without a line in the quest'] += 1
            return
        text = members[0].get('Prompt') or self.say.dials[dial].get('FULL', '')
        once = R.INFO_SAY_ONCE if all(int(r.get('DATA.Flags', 0)) & SAY_ONCE for r in members) else 0
        shown = conditions_of(members[0], self.form_map, self.quest_vars, swap=True) if len(members) == 1 else b''
        player.append(R.pack_info(self.say.builder.new_id(), once, (text,), shown or b'', prompt=text))
        player += [R.pack_info(self.say.builder.new_id()) for _ in answers[1:]]
        npc += answers

    def npc_line(self, rec: dict) -> bytes:
        """FNV line `rec` as the speaker's INFO, starting its Follow Ups' or Choices' scene, else ending the talk."""
        follow, choices = _fids(rec, 'FollowUp'), _fids(rec, 'Choice')
        if int(rec.get('DATA.Flags', 0)) & GOODBYE or not (follow or choices):
            return self.say.info(rec, self.form_map, self.quest_vars, flags=R.INFO_END_SCENE)
        scene = (self.line_scene(follow), LINE_PHASE) if follow else (self.menu(choices), MENU_PHASE)
        return self.say.info(rec, self.form_map, self.quest_vars, scene)
