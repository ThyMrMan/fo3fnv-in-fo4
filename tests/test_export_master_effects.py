"""FO3/FNV export: a DLC's effects name its master's MGEF by EditorID, read from the master beside it.

See: docs/commentary/tes4_export_falloutnv.md#master-effects
"""

import mmap
import struct

from tes4_export import export_falloutnv as EF
from tes4_export.record_types.falloutnv import MGEF_EDITOR_IDS


def _sub(sig: bytes, data: bytes) -> bytes:
    """One subrecord."""
    return sig + struct.pack('<H', len(data)) + data


def _record(sig: bytes, fid: int, body: bytes) -> bytes:
    """A 24-byte-header record."""
    return sig + struct.pack('<III', len(body), 0, fid) + bytes(8) + body


def _plugin(masters: tuple, mgefs: list) -> bytes:
    """A plugin: its header naming `masters`, then a MGEF group of (FormID, EditorID)."""
    header = _record(b'TES4', 0, b''.join(_sub(b'MAST', m.encode() + b'\0') + _sub(b'DATA', bytes(8)) for m in masters))
    records = b''.join(_record(b'MGEF', fid, _sub(b'EDID', edid.encode() + b'\0')) for fid, edid in mgefs)
    return header + b'GRUP' + struct.pack('<I', 24 + len(records)) + b'MGEF' + bytes(12) + records


def test_a_dlcs_effect_reads_its_masters_mgef_and_its_own_win(tmp_path):
    """FalloutNV.esm's own MGEF (index 00) reads under the DLC's 00; the DLC's own (01) too; a master's record
    from its own master is skipped."""
    (tmp_path / 'FalloutNV.esm').write_bytes(_plugin((), [(0x00000A10, 'RestoreHealth')]))
    dlc = tmp_path / 'ClassicPack.esm'
    dlc.write_bytes(_plugin(('FalloutNV.esm',), [(0x01000B20, 'PackEffect')]))
    EF._INDEXED_SOURCE[0] = None
    with open(dlc, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        EF.prepare_source(mm, len(mm), 24, str(dlc))
    assert MGEF_EDITOR_IDS == {0x00000A10: 'RestoreHealth', 0x01000B20: 'PackEffect'}
    EF._INDEXED_SOURCE[0] = None
