"""Walk a serialized top-level group's records, and rebuild it with some record bodies replaced.

Shared by the passes FO4PluginWriter runs on each group as it writes the file (record_compression, text_encoding).
"""

import struct

#: Record and group header size.
HEADER = 24


def records(blob: bytes, start: int = HEADER, end: int = None):
    """Yield (offset, signature, body size, flags) of every record between `start` and `end`, at any depth."""
    pos, end = start, len(blob) if end is None else end
    while pos < end:
        sig, size = blob[pos:pos + 4], struct.unpack_from('<I', blob, pos + 4)[0]
        if sig == b'GRUP':
            yield from records(blob, pos + HEADER, pos + size)
            pos += size
            continue
        yield pos, sig, size, struct.unpack_from('<I', blob, pos + 8)[0]
        pos += HEADER + size


def _rebuild(blob: bytes, start: int, end: int, bodies: dict, flags: int) -> bytes:
    """The bytes between `start` and `end` with each record in `bodies` ({offset: body}) replaced, `flags` set on
    it, and every group around one resized."""
    parts, pos = [], start
    while pos < end:
        sig, size = blob[pos:pos + 4], struct.unpack_from('<I', blob, pos + 4)[0]
        if sig == b'GRUP':
            inner = _rebuild(blob, pos + HEADER, pos + size, bodies, flags)
            parts.append(blob[pos:pos + 4] + struct.pack('<I', HEADER + len(inner)) + blob[pos + 8:pos + HEADER] + inner)
            pos += size
        elif pos in bodies:
            body = bodies[pos]
            got = struct.unpack_from('<I', blob, pos + 8)[0] | flags
            parts.append(sig + struct.pack('<II', len(body), got) + blob[pos + 12:pos + HEADER] + body)
            pos += HEADER + size
        else:
            parts.append(blob[pos:pos + HEADER + size])
            pos += HEADER + size
    return b''.join(parts)


def replace_bodies(blob: bytes, bodies: dict, flags: int = 0) -> bytes:
    """Top-level group `blob` with each record in `bodies` ({offset: body}) replaced and `flags` set on it."""
    if not bodies:
        return blob
    inner = _rebuild(blob, HEADER, len(blob), bodies, flags)
    return blob[:4] + struct.pack('<I', HEADER + len(inner)) + blob[8:HEADER] + inner
