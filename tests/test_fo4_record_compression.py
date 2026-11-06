"""Land and navmesh records stored compressed as Fallout4.esm stores them, groups resized, other records untouched.

See: docs/fork/fo4_pipeline.md#record-compression
"""

import struct

from fo4_import.base.record_compression import FLAG_COMPRESSED, compress_group
from tes5_import.base.tes5_reader import walk
from tes5_import.base.writer import pack_group, pack_record, pack_subrecord


def _world() -> bytes:
    """A WRLD top group: a cell's children holding a LAND and a REFR."""
    land = pack_record('LAND', 0x100, 0, pack_subrecord('VHGT', bytes(range(256)) * 8), 131)
    refr = pack_record('REFR', 0x101, 0, pack_subrecord('NAME', struct.pack('<I', 7)), 131)
    inner = pack_group(9, struct.pack('<I', 0x50), land + refr)
    return pack_group(0, b'WRLD', inner)


def test_land_is_deflated_with_its_length_and_reads_back_the_same():
    """The LAND carries the flag, its body's length and level-9 zlib; the REFR and every record body are unchanged."""
    blob = _world()
    out = compress_group(blob)
    assert len(out) < len(blob) and struct.unpack_from('<I', out, 4)[0] == len(out)
    before = {r.form_id: r.body for r, _ in walk(blob, span=(0, len(blob)))}
    after = {r.form_id: (r.body, r.flags) for r, _ in walk(out, span=(0, len(out)))}
    assert {k: v[0] for k, v in after.items()} == before
    assert after[0x100][1] & FLAG_COMPRESSED and not after[0x101][1] & FLAG_COMPRESSED
    land = out.index(b'LAND')
    assert out[land + 28:land + 30] == b'\x78\xda'


def test_other_groups_and_already_compressed_records_are_left():
    """A STAT group passes through, and compressing twice changes nothing more."""
    stat = pack_group(0, b'STAT', pack_record('STAT', 0x200, 0, pack_subrecord('EDID', b'X\x00'), 131))
    assert compress_group(stat) == stat
    once = compress_group(_world())
    assert compress_group(once) == once
