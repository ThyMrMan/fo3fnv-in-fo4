"""Story Manager quest nodes, and the quests they start on an event.

A node hangs under an event node (PNAM) after a previous sibling (SNAM, 0
for first) and starts the first of its quests not already running; Shares
Event lets the other quests on that event still run.

See: docs/commentary/character_rules.md#the-rules-plugin
"""

import struct

from .writer import pack_formid_subrecord, pack_record, pack_string_subrecord, pack_subrecord, pack_uint32_subrecord

#: SMQN DNAM: Shares event, so the vanilla quests on the same event still run.
SHARES_EVENT = 0x00020000


def story_quest(fid: int, edid: str, event: bytes, vmad: bytes) -> bytes:
    """A quest the Story Manager starts on `event` (b'KILL', b'ASSU', ...), running the scripts in `vmad`."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('VMAD', vmad)
    subs += pack_subrecord('DNAM', struct.pack('<HBBII', 0, 0, 0, 0, 0))
    subs += pack_subrecord('ENAM', event) + pack_subrecord('NEXT', b'')
    return pack_record('QUST', fid, 0, subs + pack_uint32_subrecord('ANAM', 0))


def story_node(fid: int, edid: str, place: tuple, quests: list, conditions: tuple = ()) -> bytes:
    """A quest node at `place` (event node, previous sibling or 0), sharing the event, starting the
    first of `quests` not already running while every CTDA subrecord of `conditions` holds."""
    subs = pack_string_subrecord('EDID', edid)
    subs += pack_formid_subrecord('PNAM', place[0]) + pack_formid_subrecord('SNAM', place[1])
    subs += pack_uint32_subrecord('CITC', len(conditions)) + b''.join(conditions)
    subs += pack_uint32_subrecord('DNAM', SHARES_EVENT) + pack_uint32_subrecord('XNAM', 0)
    subs += pack_uint32_subrecord('QNAM', len(quests))
    subs += b''.join(pack_formid_subrecord('NNAM', quest) for quest in quests)
    return pack_record('SMQN', fid, 0, subs)
