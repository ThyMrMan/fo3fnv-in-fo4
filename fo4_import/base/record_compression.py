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
from fo4_import.base.pinned_zlib import compress

#: Record types Fallout4.esm stores compressed.
COMPRESSED_TYPES = (b'LAND', b'NAVM')
#: The record flag Compressed, and vanilla's zlib level.
FLAG_COMPRESSED, LEVEL = 0x40000, 9
#: Record and group header size.
HEADER = 24
#: Top-level groups holding COMPRESSED_TYPES records.
HOLDERS = (b'WRLD', b'CELL')


def _deflate(body: bytes) -> bytes:
    """A record body stored compressed: its length, then the zlib stream."""
    return struct.pack('<I', len(body)) + compress(body, LEVEL)


def _spans(blob: bytes, start: int, end: int, out: list) -> None:
    """Append (offset, length) of every COMPRESSED_TYPES record not yet compressed between `start` and `end`."""
    pos = start
    while pos < end:
        sig, size = blob[pos:pos + 4], struct.unpack_from('<I', blob, pos + 4)[0]
        if sig == b'GRUP':
            _spans(blob, pos + HEADER, pos + size, out)
            pos += size
            continue
        flags = struct.unpack_from('<I', blob, pos + 8)[0]
        if sig in COMPRESSED_TYPES and not flags & FLAG_COMPRESSED:
            out.append((pos, size))
        pos += HEADER + size


def _rebuild(blob: bytes, start: int, end: int, packed: dict) -> bytes:
    """The bytes between `start` and `end` with each record in `packed` ({offset: body}) compressed and every group
    around one resized."""
    parts, pos = [], start
    while pos < end:
        sig, size = blob[pos:pos + 4], struct.unpack_from('<I', blob, pos + 4)[0]
        if sig == b'GRUP':
            inner = _rebuild(blob, pos + HEADER, pos + size, packed)
            parts.append(blob[pos:pos + 4] + struct.pack('<I', HEADER + len(inner)) + blob[pos + 8:pos + HEADER] + inner)
            pos += size
        elif pos in packed:
            body = packed[pos]
            flags = struct.unpack_from('<I', blob, pos + 8)[0] | FLAG_COMPRESSED
            parts.append(sig + struct.pack('<II', len(body), flags) + blob[pos + 12:pos + HEADER] + body)
            pos += HEADER + size
        else:
            parts.append(blob[pos:pos + HEADER + size])
            pos += HEADER + size
    return b''.join(parts)


def compress_group(blob: bytes) -> bytes:
    """Top-level group `blob` with its COMPRESSED_TYPES records compressed (bodies deflated on threads, as the
    ctypes call releases the GIL); a group of another type unchanged."""
    if blob[8:12] not in HOLDERS:
        return blob
    spans = []
    _spans(blob, HEADER, len(blob), spans)
    if not spans:
        return blob
    with ThreadPoolExecutor(profile_cores()) as pool:
        bodies = pool.map(_deflate, (blob[p + HEADER:p + HEADER + n] for p, n in spans), chunksize=64)
        packed = dict(zip((p for p, _ in spans), bodies))
    inner = _rebuild(blob, HEADER, len(blob), packed)
    return blob[:4] + struct.pack('<I', HEADER + len(inner)) + blob[8:HEADER] + inner
