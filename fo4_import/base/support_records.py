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


def pack_global(fid: int, edid: str, kind: str = 's', value: float = 0.0, flags: int = 0) -> bytes:
    """A global (type s, l or f), as GameDaysPassed 00000039; `flags`: record flags."""
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('FNAM', kind.encode('ascii'))
    return pack_fo4_record('GLOB', fid, flags, subs + pack_subrecord('FLTV', struct.pack('<f', value)))
