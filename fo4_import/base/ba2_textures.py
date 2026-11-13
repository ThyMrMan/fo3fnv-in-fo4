"""Write a texture (DX10) BA2 ourselves, laid out as the CK's Archive2 writes it.

Archive2 version 8, one chunk per texture (its `-maxChunkCount=1`): a 24-byte
record per texture (both name hashes, `dds`, the size, mip count, DXGI
format, cube flag, tile mode 8), its 24-byte chunk (offset, zlib size, size,
first and last mip, the `0xBAADF00D` marker), then the DDS bodies without
their headers, zlib level 6 compressed, back to back, then the name table.
Textures unchanged since the last pack are copied out of the previous archive
still compressed.

See: docs/fork/fo4_ck_replacements.md#ba2
"""

import os
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy

from core.build_resources import profile_cores

from fo4_import.base.ba2 import DX10_CHUNK as CHUNK
from fo4_import.base.ba2 import DX10_ENTRY as RECORD
from fo4_import.base.ba2_write import BUFFER, HEADER, MARKER, VERSION, entry_names
from fo4_import.base.pinned_zlib import compress

#: zlib level Archive2 compresses with (its bytes, reproduced), and the record's chunk-header size and tile mode.
LEVEL, CHUNK_SIZE, TILE = 6, 24, 8
#: DDS FourCC codes and their DXGI formats.
FOURCC = {b'DXT1': 71, b'DXT3': 74, b'DXT5': 77, b'ATI1': 80, b'BC4U': 80, b'ATI2': 83, b'BC5U': 83}
#: Raw DDS pixel formats as (bits, R, G, B, A masks) and their DXGI formats; 24-bit BGR goes in as B8G8R8A8 (expand_bgr).
MASKS = {(32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000): 87, (32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000): 28,
         (32, 0xFF0000, 0xFF00, 0xFF, 0): 88, (8, 0xFF, 0, 0, 0): 61, (24, 0xFF0000, 0xFF00, 0xFF, 0): 87}


def dds_info(head: bytes) -> tuple:
    """(height, width, mips, DXGI format, cube flag, header length) of a DDS file starting with `head` (148 bytes)."""
    if head[:4] != b'DDS ':
        raise ValueError('not a DDS file')
    height, width = struct.unpack_from('<II', head, 12)
    mips, fourcc = max(1, struct.unpack_from('<I', head, 28)[0]), head[84:88]
    cube = 1 if struct.unpack_from('<I', head, 112)[0] & 0x200 else 0
    if fourcc == b'DX10':
        return height, width, mips, struct.unpack_from('<I', head, 128)[0], cube, 148
    form = FOURCC.get(fourcc) or MASKS.get(struct.unpack_from('<5I', head, 88))
    if form is None:
        raise ValueError(f'a DDS format the texture archive cannot name ({fourcc!r})')
    return height, width, mips, form, cube, 128


def expand_bgr(body: bytes) -> bytes:
    """24-bit BGR pixels (every mip and face back to back) as B8G8R8A8 with alpha 255."""
    pixels = numpy.frombuffer(body, numpy.uint8).reshape(-1, 3)
    out = numpy.full((len(pixels), 4), 255, numpy.uint8)
    out[:, :3] = pixels
    return out.tobytes()


def _records(f, count: int) -> list:
    """`count` (record fields, chunk fields or None) read from `f`, None for a texture of several chunks."""
    rows = []
    for _ in range(count):
        record = RECORD.unpack(f.read(RECORD.size))
        chunks = f.read(CHUNK.size * record[4])
        rows.append((record, CHUNK.unpack(chunks) if record[4] == 1 else None))
    return rows


def _read_old(archive: Path, kept: set) -> dict:
    """{lowercase name: (record fields, chunk fields)} of the one-chunk `kept` textures in `archive`."""
    if not kept or not archive.exists():
        return {}
    with open(archive, 'rb') as f:
        _, _, kind, count, names_at = HEADER.unpack(f.read(HEADER.size))
        if kind != b'DX10':
            return {}
        rows = _records(f, count)
        f.seek(names_at)
        names = [f.read(struct.unpack('<H', f.read(2))[0]).decode('cp1252').lower() for _ in range(count)]
    return {name: row for name, row in zip(names, rows) if row[1] and name in kept}


def _copied(archive: Path, row: tuple) -> tuple:
    """(record fields, chunk fields, compressed body) of a texture `row` of _read_old(), its bytes read now."""
    record, chunk = row
    with open(archive, 'rb') as f:
        f.seek(chunk[0])
        packed = f.read(chunk[1] or chunk[2])
    if len(packed) != (chunk[1] or chunk[2]):
        raise RuntimeError(f'{archive} ends before its records say')
    return record, chunk, packed


def _texture(name: str, path: Path) -> tuple:
    """(record fields but the offset's chunk, chunk fields with offset 0, compressed body) of texture `path`."""
    data = Path(path).read_bytes()
    try:
        height, width, mips, form, cube, skip = dds_info(data[:148])
    except ValueError as error:
        raise ValueError(f'{path}: {error}') from None
    body = expand_bgr(data[skip:]) if data[84:92] == bytes(4) + struct.pack('<I', 24) else data[skip:]
    packed = compress(body, LEVEL)
    record = (*entry_names(name), 0, 1, CHUNK_SIZE, height, width, mips, form, cube, TILE)
    return record, (0, len(packed), len(body), 0, mips - 1, MARKER), packed


def _one(name: str, named: dict, old: dict, archive: Path) -> tuple:
    """Texture `name` as _texture() makes it, or copied out of `archive` (`old`)."""
    row = old.get(name.lower())
    return _copied(archive, row) if row else _texture(name, named[name])


def _built(names: list, named: dict, old: dict, archive: Path):
    """Each of `names` as _one() gives it, in order, on the resource profile's threads (the pinned zlib's ctypes
    call frees the GIL while it works)."""
    workers = profile_cores()
    with ThreadPoolExecutor(workers) as pool:
        for start in range(0, len(names), workers * 4):
            batch = names[start:start + workers * 4]
            yield from pool.map(lambda n: _one(n, named, old, archive), batch)


def write_textures(named: dict, archive: Path, kept: set = frozenset()) -> None:
    """Write `named` ({archive name, forward slashes: DDS path}) as the texture BA2 `archive`, in lowercase name
    order, through a temporary file replaced at the end; textures whose lowercase names are in `kept` are unchanged
    since `archive` was written and are copied out of it."""
    names = sorted(named, key=str.lower)
    old = _read_old(archive, {k.lower() for k in kept})
    table = HEADER.size + (RECORD.size + CHUNK.size) * len(names)
    rows, offset = [], table
    temporary = archive.with_name(archive.name + '.tmp')
    with open(temporary, 'wb', buffering=BUFFER) as out:
        out.seek(table)
        for record, chunk, packed in _built(names, named, old, archive):
            out.write(packed)
            rows.append(RECORD.pack(*record) + CHUNK.pack(offset, *chunk[1:]))
            offset += len(packed)
        for name in names:
            encoded = name.encode('cp1252')
            out.write(struct.pack('<H', len(encoded)) + encoded)
        out.seek(0)
        out.write(HEADER.pack(b'BTDX', VERSION, b'DX10', len(names), offset))
        out.write(b''.join(rows))
    os.replace(temporary, archive)
