"""FNV's random NPC-to-NPC conversations as Fallout 4 Actor Dialogue (ADIA) quests, for the cell spike.

FNV starts one when an NPC greets another with a HELLO line (Link From blank)
offering Choices: the other NPC answers from those topics, even when the HELLO
is a Goodbye line. Fallout 4's Story Manager runs such chats as ADIA event
quests (297 in Fallout4.esm, e.g. ConvDiamondCityGenericNPC03). Each such HELLO
line of the cell quests becomes one: its Speaker and Listener aliases fill
from the event's actors (ALFD All) on the line's condition groups that test
no Target, and those testing only the Target (as Subject tests) plus the
answers' named speakers; its chat scene (conversation.Conversations) begins on
quest start and stops the quest at its end. One Story Manager quest node after
Fallout4.esm's last Actor Dialogue child starts the first quest that can, each
waiting a day before it runs again, as vanilla's conversations.

See: docs/fork/fo4_pipeline.md#actor-dialogue
"""

import dataclasses

from fo4_import.base.support_records import NUM_QUESTS_TO_RUN, pack_event_alias, pack_event_quest, pack_story_node
from fo4_import.base.writer import pack_quest
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.conversation import GOODBYE, IS_ID, PLAYER_BASE, Conversations, Hub, or_groups
from fo4_import.spike.quest import LISTENER_ALIAS, SPEAKER_ALIAS
from fo4_import.spike.say_topics import ENGINE_TOPICS, conditions_of, with_conditions
from fo4_import.spike.standings import last_child

#: FNV's HELLO topic, and the Story Manager's Actor Dialogue event.
HELLO, ADIA = '000000D2', b'ADIA'
#: Fallout4.esm's Actor Dialogue event node, whose last child our quest node follows.
EVENT_NODE = 0x021E65
#: SCEN FNAM Begin on Quest Start and Stop Quest on End, as ConvDiamondCityGenericNPC03Scene's.
QUEST_SCENE = 0x03
#: Raw RNAM of vanilla's conversation quests (DmndGenericNPCConversations): 24 game hours before one runs again.
RESET = 576.0
#: An alias test the player fails: an FNV chat's speaker and answerer are NPCs.
NOT_PLAYER = R.pack_ctda(0, 0.0, IS_ID, PLAYER_BASE)


def choices(rec: dict) -> list:
    """FNV line `rec`'s Choices, as the export's upper-case hex."""
    return [rec[f'Choice[{i}]'].upper() for i in range(int(rec.get('ChoiceCount', 0) or 0))]


def chat_lines(shared: Hub) -> dict:
    """{FNV HELLO line: its chat opening} for the Hub's HELLO lines with Link From blank offering Choices into
    non-engine topics with lines: the opening keeps only those Choices and drops the Goodbye flag."""
    out = {}
    for _, line in shared.by_topic.get(HELLO, ()):
        rec = shared.lines[line]
        kept = [c for c in choices(rec) if c not in ENGINE_TOPICS and c in shared.by_topic]
        if kept and not int(rec.get('LinkFromCount', 0) or 0):
            out[line] = opening(rec, kept)
    return out


def opening(rec: dict, kept: list) -> dict:
    """FNV line `rec` with Choices `kept` and no Goodbye flag."""
    out = {k: v for k, v in rec.items() if not k.startswith('Choice')}
    out.update({f'Choice[{i}]': c for i, c in enumerate(kept)}, ChoiceCount=str(len(kept)))
    return {**out, 'DATA.Flags': str(int(rec.get('DATA.Flags', 0) or 0) & ~GOODBYE)}


def sides(rec: dict) -> tuple:
    """(speaker, listener) raw tests of FNV line `rec`: its OR-groups testing no Target, and those testing only
    the Target; a group testing both stays on the line alone."""
    speaker, listener = [], []
    for group in or_groups(rec):
        runs = {C.run_on_of(C.parse(raw), False, {})[0] for raw in group}
        if R.RUN_TARGET not in runs:
            speaker += group
        elif runs == {R.RUN_TARGET}:
            listener += group
    return speaker, listener


class ActorDialogue:
    """The ADIA quests of the cell quests' NPC-to-NPC HELLO lines, written through a cell builder."""

    def __init__(self, builder, say, form_map: dict, shared: Hub):
        """Lines from `say` and `shared` (the cell quests' Hub), forms through `form_map`."""
        self.builder, self.say, self.form_map, self.shared = builder, say, form_map, shared

    def write(self) -> None:
        """Write a quest per chat line, highest FNV quest priority first, and the quest node trying them in order."""
        lines = sorted(chat_lines(self.shared).items(), key=lambda kv: -self._priority(kv[1]))
        quests = tuple(fid for fid in (self._quest(line, rec) for line, rec in lines) if fid)
        if not quests:
            return
        node = self.builder.new_id('SMQN actor dialogue')
        self.builder.writer.add_record('SMQN', pack_story_node(
            node, 'FNV_ActorDialogueNode', EVENT_NODE, last_child(self.builder.fo4, EVENT_NODE), quests,
            NUM_QUESTS_TO_RUN, RESET))

    def _priority(self, rec: dict) -> int:
        """The FNV priority of line `rec`'s quest."""
        return self.shared.quests.get(rec.get('QSTI.Quest', '').upper(), (0, 0))[1]

    def _tests(self, rec: dict, raws: list, swap: bool) -> 'bytes | None':
        """`rec`'s tests `raws` as FO4 CTDAs, sides flipped on `swap`; None: unconverted."""
        return conditions_of(with_conditions(rec, raws), self.form_map, self.say.script_vars, swap=swap)

    def _quest(self, line: str, rec: dict) -> int:
        """Write the ADIA quest whose scene opens with FNV HELLO `line` (its chat opening `rec`); its FormID, or 0
        when an alias's tests do not convert."""
        speaker, listener = sides(rec)
        tests = self._tests(rec, speaker, False), self._tests(rec, listener, True)
        counts = self.builder.counts
        if None in tests:
            counts['actor dialogue left out (alias condition)'] += 1
            return 0
        hub = dataclasses.replace(self.shared, lines={**self.shared.lines, line: rec})
        fid = self.builder.new_id(f'QUST ADIA {line}')
        talks = Conversations(self.say, {'FormID': f'ADIA {line}', 'EditorID': f'Chat{line}'}, fid, self.form_map, hub)
        step = ('chat', SPEAKER_ALIAS, ('line', (line,)))
        talks.labels[step] = 'actor dialogue'
        talks.scene(step, flags=QUEST_SCENE)
        answers = [hub.lines[i] for dial in choices(rec) for _, i in hub.by_topic[dial]]
        aliases = ((SPEAKER_ALIAS, pack_event_alias(SPEAKER_ALIAS, 'Speaker', ADIA, NOT_PLAYER + tests[0])),
                   (LISTENER_ALIAS, pack_event_alias(LISTENER_ALIAS, 'Listener', ADIA, NOT_PLAYER + tests[1]
                                                     + talks.speakers(answers, R.RUN_SUBJECT))))
        record = pack_event_quest(fid, f'FNV_Chat{line}', ADIA, priority=self._priority(rec), aliases=aliases)
        self.builder.writer.add_record('QUST', pack_quest(record, fid, [], talks.topics, talks.scenes))
        counts['actor dialogue quests'] += 1
        counts['actor dialogue in several scenes'] += len(talks.scenes) > 1
        counts['SCEN'] += len(talks.scenes)
        return fid
