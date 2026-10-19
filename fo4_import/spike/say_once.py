"""FNV Say Once across a line's copies: one marker stage per Say Once line, in one marker quest every copy checks.

FNV's Say Once belongs to the NPC's line: once said, every topic offering
it drops it. The build makes a copy of a line for each menu or step it plays
in, and FO4's own Say Once (ENAM) hides only the copy said; FO4 has no
condition reading whether an INFO was said. So a Say Once line gets a stage
of the marker quest (FNV_TES4SayOnce): each copy sets it as it begins (the
TES4_SayOnce script's OnBegin) and plays only while it is not done
(GetStageDone), and a player option whose answers are all Say Once shows
while one of them is unsaid. The markers stay out of the lines' own quests:
FO4's GetStage reads a quest's highest done stage, so a marker there stood in
for its story stage (VCG01 read 22583 and its intro stalled). The stage is
hashed from the FNV line, so stages stay put as content arrives.

See: docs/fork/fo4_pipeline.md#say-once
"""

import zlib

from fo4_import.base.ledger import NUMBER
from fo4_import.base.vmad import quest_fragments
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R

#: The marker stages' range: FO4 stage indexes are 16 bits.
FIRST, COUNT = 10000, 55000
STAGE_DONE = C.FO4.index('GetStageDone')
#: CTDA flag: OR with the next condition.
OR = 0x01
#: Ledger site of the marker stages (key: the FNV line) and of the marker quest's FormID.
SITE = 'FNV say once'
#: The marker quest's EditorID and the script each Say Once line carries.
EDID, SCRIPT = 'FNV_TES4SayOnce', 'TES4_SayOnce'


class SayOnce:
    """The Say Once marker stages, {FNV line: stage} of the marker quest, made on first use and kept by `writer`'s
    ledger (None: kept for the build only)."""

    def __init__(self, writer=None):
        """No markers yet."""
        self.stages, self.writer = {}, writer
        self.quest = writer.derive_formid(SITE, EDID) if writer else 0

    def stage(self, line: str) -> int:
        """The marker stage of FNV line `line` (FormID hex): the ledger's, else its hash moved up one while taken.
        See: docs/fork/fo4_pipeline.md#formid-ledger
        """
        line = line.upper()
        if line not in self.stages:
            site = f'{SITE} {self.quest:08X}'
            used = set(self.stages.values()) | set(self.writer.ledger.values(NUMBER, site) if self.writer else ())

            def free() -> int:
                """The line's hashed stage, moved up one while `used` holds it."""
                stage = FIRST + zlib.crc32(line.encode()) % COUNT
                while stage in used:
                    stage = FIRST + (stage - FIRST + 1) % COUNT
                return stage
            self.stages[line] = self.writer.stable_number(site, line, free) if self.writer else free()
        return self.stages[line]

    def unsaid(self, lines: list) -> bytes:
        """CTDAs: one OR-group, true while one of FNV `lines` is unsaid."""
        stages = [self.stage(line) for line in lines]
        return b''.join(R.pack_ctda(OR if i < len(stages) - 1 else 0, 0.0, STAGE_DONE, self.quest, stage)
                        for i, stage in enumerate(stages))

    def script(self, line: str) -> tuple:
        """The TES4_SayOnce script entry setting FNV line `line`'s marker."""
        return SCRIPT, {'Marks': self.quest}, {'Stage': ('int', self.stage(line))}

    def record(self) -> bytes:
        """The marker quest: start game enabled, holding every marker stage made."""
        stages = [(stage, 0) for stage in sorted(self.stages.values())]
        return R.pack_fnv_quest(self.quest, EDID, '', 0, quest_fragments('', []), stages, [], [], True)
