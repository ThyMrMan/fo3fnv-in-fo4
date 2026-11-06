"""Trace fragments on the dialogue the build makes: each menu choice line (the player's prompts, their pads, the Tab
exit line) and each dialogue scene's begin, end and phases, logged while tracing is on (TES4Polyfill.TraceTopicInfo,
TraceScene).

See: docs/fork/fo4_pipeline.md#dialogue-trace
"""

from functools import cache

from fo4_import.base.vmad import PHASE_DONE, PHASE_START, info_fragments, scene_fragments

CHOICE_SCRIPT, SCENE_SCRIPT = 'F3NV_TraceTopicInfo', 'F3NV_TraceScene'
#: Phases F3NV_TraceScene has fragments for (the largest built dialogue scene has 42).
TRACED_PHASES = 48
#: The VMAD of a line with no converted script: F3NV_TraceTopicInfo's OnBegin.
CHOICE_VMAD = info_fragments(CHOICE_SCRIPT, end=None)


@cache
def scene_vmad(phases: int) -> bytes:
    """VMAD tracing a scene's begin, end and its first TRACED_PHASES phases."""
    steps = tuple((flag, i, f'Fragment_Phase_{i + 1:02d}_{edge}') for i in range(min(phases, TRACED_PHASES))
                  for flag, edge in ((PHASE_START, 'Begin'), (PHASE_DONE, 'End')))
    return scene_fragments(SCENE_SCRIPT, 'Fragment_End', 'Fragment_Begin', steps)


def register(scripts) -> None:
    """Have the build compile and keep both trace scripts (ObjectScripts.used)."""
    scripts.used += [name for name in (CHOICE_SCRIPT, SCENE_SCRIPT) if name not in scripts.used]
