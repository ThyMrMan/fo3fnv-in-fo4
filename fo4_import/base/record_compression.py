"""Records stored zlib-compressed in a written Fallout 4 plugin, as Fallout4.esm stores them.

Fallout4.esm compresses every LAND (37,019 of 37,020) and every NAVM (7,894) record: the record flag 0x40000, then
the body's length (u32) and the body deflated at level 9 (zlib header 78 DA). The writer packs records raw and
compresses only as it writes the file (FO4PluginWriter._finish_groups), so every step comparing or reading the
built records in memory sees them uncompressed. Bodies go through our pinned zlib, so the plugin is the same bytes
on every machine and Python.

See: docs/fork/fo4_pipeline.md#record-compression
"""

import struct
from concurrent.futures import ThreadPoolExecutor

from core.build_resources import profile_cores
from fo4_import.base.group_walk import HEADER, records, replace_bodies
from fo4_import.base.pinned_zlib import compress

#: Record types Fallout4.esm stores compressed.
COMPRESSED_TYPES = (b'LAND', b'NAVM')
#: The record flag Compressed, and vanilla's zlib level.
FLAG_COMPRESSED, LEVEL = 0x40000, 9
#: Top-level groups holding COMPRESSED_TYPES records.
HOLDERS = (b'WRLD', b'CELL')


def _deflate(body: bytes) -> bytes:
    """A record body stored compressed: its length, then the zlib stream."""
    return struct.pack('<I', len(body)) + compress(body, LEVEL)


def compress_group(blob: bytes) -> bytes:
    """Top-level group `blob` with its COMPRESSED_TYPES records compressed (bodies deflated on threads, as the
    ctypes call releases the GIL); a group of another type unchanged."""
    if blob[8:12] not in HOLDERS:
        return blob
    spans = [(pos, size) for pos, sig, size, flags in records(blob)
             if sig in COMPRESSED_TYPES and not flags & FLAG_COMPRESSED]
    if not spans:
        return blob
    with ThreadPoolExecutor(profile_cores()) as pool:
        bodies = pool.map(_deflate, (blob[p + HEADER:p + HEADER + n] for p, n in spans), chunksize=64)
        packed = dict(zip((p for p, _ in spans), bodies))
    return replace_bodies(blob, packed, FLAG_COMPRESSED)
