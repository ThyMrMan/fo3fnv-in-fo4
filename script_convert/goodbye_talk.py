"""An FNV Goodbye line ends the player's talk when it ends (Fallout 4 only).

Fallout 4 keeps a talk up for about 15 s after a scene of the NPC alone ends, and holds a quest a result script
starts until then. A Goodbye line of an FNV Topic (the player's talks) gets an End fragment whose first call,
F3NV_Talk.EndTalk (F3NV.dll), ends that talk as the game's own end-of-talk does.

See: docs/fork/fo4_pipeline.md#goodbye-ends-talk
"""

from script_convert import target
from script_convert.trace_points import goodbye

#: FNV INFO DATA dialog type Topic: lines of the player's talks (Conversation, Combat, Radio and the rest are not).
FNV_TOPIC = 0
#: The End fragment's first statement on such a line.
END_TALK = '  F3NV_Talk.EndTalk(akSpeakerRef)'


def ends_talk(rec: dict) -> bool:
    """Whether FNV INFO `rec` ends the talk on Fallout 4: a Goodbye of a Topic."""
    return target.is_fallout4() and goodbye(rec) and int(rec.get('DATA.DialogType', 0) or 0) == FNV_TOPIC
