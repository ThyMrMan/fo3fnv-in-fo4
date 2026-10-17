"""FNV Say Once across a line's copies: one quest stage per Say Once line, which every copy checks.

FNV's Say Once belongs to the NPC's line: once said, every topic offering
it drops it. The build makes a copy of a line for each menu or step it plays
in, and FO4's own Say Once (ENAM) hides only the copy said; FO4 has no
condition reading whether an INFO was said. So a Say Once line gets a stage
of the quest its copies sit in: each copy sets it as it begins (TIQS) and
plays only while it is not done (GetStageDone), and a player option whose
answers are all Say Once shows while one of them is unsaid. The stage is
hashed from the FNV line into a range clear of authored stages, so stages
stay put as content arrives.

See: docs/fork/fo4_pipeline.md#say-once
"""

import zlib

from fo4_import.spike import conditions as C
from fo4_import.spike import records as R

#: The marker stages' range: FO4 stage indexes are 16 bits; FNV's authored stages sit far below.
FIRST, COUNT = 10000, 55000
STAGE_DONE = C.FO4.index('GetStageDone')
#: CTDA flag: OR with the next condition.
OR = 0x01


class SayOnce:
    """Each quest's Say Once marker stages, {FO4 quest: {FNV line: stage}}, made on first use."""

    def __init__(self):
        """No markers yet."""
        self.stages = {}

    def stage(self, quest: int, line: str) -> int:
        """The marker stage of FNV line `line` (FormID hex) in FO4 quest `quest`; a taken hash moves up one."""
        taken = self.stages.setdefault(quest, {})
        if line.upper() not in taken:
            stage, used = FIRST + zlib.crc32(line.upper().encode()) % COUNT, set(taken.values())
            while stage in used:
                stage = FIRST + (stage - FIRST + 1) % COUNT
            taken[line.upper()] = stage
        return taken[line.upper()]

    def unsaid(self, quest: int, lines: list) -> bytes:
        """CTDAs: one OR-group, true while one of FNV `lines` is unsaid."""
        stages = [self.stage(quest, line) for line in lines]
        return b''.join(R.pack_ctda(OR if i < len(stages) - 1 else 0, 0.0, STAGE_DONE, quest, stage)
                        for i, stage in enumerate(stages))

    def of(self, quest: int) -> list:
        """[(stage, log flags 0)] of FO4 quest `quest`'s markers, for its stage list."""
        return [(stage, 0) for stage in sorted(self.stages.get(quest, {}).values())]
