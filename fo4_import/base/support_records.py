"""FO4 records the conversion makes with no source record: actor values, script-only quests, globals.

Laid out from vanilla Fallout4.esm records named in each docstring.

See: docs/fork/fo4_spikes.md#spike-3-helper-plugin
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord


#: A notification's default seconds on screen (MESG TNAM).
MESSAGE_TIME = 2


def pack_mesg(fid: int, edid: str, title: str, text: str, flags: int, buttons: list) -> bytes:
    """A message: text, title, DNAM flags (1: message box), button texts."""
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('DESC', text)
    subs += pack_string_subrecord('FULL', title) + pack_subrecord('INAM', struct.pack('<I', 0))
    subs += pack_subrecord('DNAM', struct.pack('<I', flags))
    subs += b'' if flags & 1 else pack_subrecord('TNAM', struct.pack('<I', MESSAGE_TIME))
    return pack_fo4_record('MESG', fid, 0, subs + b''.join(pack_string_subrecord('ITXT', b) for b in buttons))


def pack_avif(fid: int, edid: str, name: str, desc: str = '') -> bytes:
    """A plugin actor value, shaped like vanilla CA_Affinity 000A1B80 (default 0)."""
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', name)
    subs += pack_string_subrecord('DESC', desc) + pack_subrecord('NAM0', struct.pack('<f', 0.0))
    subs += pack_subrecord('AVFL', struct.pack('<I', 0x400)) + pack_subrecord('NAM1', struct.pack('<I', 8))
    return pack_fo4_record('AVIF', fid, 0, subs)


def pack_script_quest(fid: int, edid: str, vmad: bytes, stages: tuple = ()) -> bytes:
    """A start-game-enabled quest carrying scripts, with `stages` each holding one log entry for its fragment."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('VMAD', vmad)
    subs += pack_subrecord('DNAM', struct.pack('<HBxfB3x', 0x0011, 0, 0.0, 0)) + pack_subrecord('NEXT', b'')
    for stage in sorted(stages):
        subs += pack_subrecord('INDX', struct.pack('<HBB', stage, 0, 0)) + pack_subrecord('QSDT', b'\x00')
    return pack_fo4_record('QUST', fid, 0, subs + pack_subrecord('ANAM', struct.pack('<I', 0)))


def pack_event_quest(fid: int, edid: str, event: bytes, vmad: bytes = b'', priority: int = 0,
                     aliases: tuple = ()) -> bytes:
    """A quest the Story Manager starts on `event` (ENAM), as CA_PossibleMurder; `aliases` [(id, packed alias)]."""
    subs = pack_string_subrecord('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('DNAM', struct.pack('<HBxfB3x', 0, priority, 0.0, 0)) + pack_subrecord('ENAM', event)
    subs += pack_subrecord('NEXT', b'') + pack_subrecord('ANAM', struct.pack('<I', max((a for a, _ in aliases), default=-1) + 1))
    return pack_fo4_record('QUST', fid, 0, subs + b''.join(packed for _, packed in aliases))


#: Quest alias flag Allow Reserved, and ALFD All: any reference of the event (vanilla's ADIA quests' aliases).
ALLOW_RESERVED, EVENT_ALL = 0x200, 0x7FFFFFFF


def pack_event_alias(alias: int, name: str, event: bytes, conditions: bytes) -> bytes:
    """A reference alias filled from a reference of Story Manager `event` passing `conditions`, as vanilla
    ConvDiamondCityGenericNPC03's EvenToned."""
    subs = pack_subrecord('ALST', struct.pack('<I', alias)) + pack_string_subrecord('ALID', name)
    subs += pack_subrecord('FNAM', struct.pack('<I', ALLOW_RESERVED)) + pack_subrecord('ALFE', event)
    subs += pack_subrecord('ALFD', struct.pack('<I', EVENT_ALL)) + conditions
    return subs + pack_subrecord('VTCK', struct.pack('<I', 0)) + pack_subrecord('ALED', b'')


#: Story Manager quest node flags: Shares Event (later nodes still get the event), Num Quests To Run (MNAM).
SHARES_EVENT, NUM_QUESTS_TO_RUN = 0x20000, 0x40000


def pack_story_node(fid: int, edid: str, parent: int, previous: int, quests: tuple, flags: int = SHARES_EVENT,
                    reset: float = 0.0) -> bytes:
    """A Story Manager quest node under `parent` after sibling `previous` (0: first), trying `quests` in order with
    DNAM `flags` (NUM_QUESTS_TO_RUN starts one, as AO_LightsNode), each waiting raw RNAM `reset` to run again;
    as vanilla's CA_PossibleMurder_QuestNode 00239BE4."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('PNAM', struct.pack('<I', parent))
    subs += pack_subrecord('SNAM', struct.pack('<I', previous)) + pack_subrecord('CITC', struct.pack('<I', 0))
    subs += pack_subrecord('DNAM', struct.pack('<I', flags)) + pack_subrecord('XNAM', struct.pack('<I', 0))
    subs += pack_subrecord('MNAM', struct.pack('<I', 1)) if flags & NUM_QUESTS_TO_RUN else b''
    subs += pack_subrecord('QNAM', struct.pack('<I', len(quests)))
    for quest in quests:
        subs += pack_subrecord('NNAM', struct.pack('<I', quest))
        subs += pack_subrecord('RNAM', struct.pack('<f', reset)) if reset else b''
    return pack_fo4_record('SMQN', fid, 0, subs)


#: Game setting EditorID prefix -> its DATA format: unsigned, int, float.
GMST_FORMATS = {'u': '<I', 'i': '<i', 'f': '<f'}


def pack_gmst(fid: int, edid: str, value: float) -> bytes:
    """A game setting, DATA by its EditorID's prefix (GMST_FORMATS)."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('DATA', struct.pack(GMST_FORMATS[edid[0]], value))
    return pack_fo4_record('GMST', fid, 0, subs)


def pack_global(fid: int, edid: str, kind: str = 's', value: float = 0.0, flags: int = 0) -> bytes:
    """A global (type s, l or f), as GameDaysPassed 00000039; `flags`: record flags."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('FNAM', kind.encode('ascii'))
    return pack_fo4_record('GLOB', fid, flags, subs + pack_subrecord('FLTV', struct.pack('<f', value)))
