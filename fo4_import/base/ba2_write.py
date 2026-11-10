"""Write an uncompressed general (GNRL) BA2 ourselves, at disk speed.

Archive2 spends about 56 minutes on the 248,000 sound files of a whole-map
build (per-file overhead, about 1 MB/s). An uncompressed general archive is
simple: the header, one 36-byte entry per file, the files' bytes back to back,
then the name table. Every field is laid out as Archive2 writes it (version 8,
flags 0x00100100, the 0xBAADF00D marker), and both name hashes are CRC-32 with
no starting or final inversion over the lowercase backslashed stem and folder.
Files unchanged since the last pack are copied out of the previous archive;
only the rest are opened, several at a time.

See: docs/fork/fo4_pipeline.md#sound-archive
"""

import os
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

HEADER = struct.Struct('<4sI4sIQ')
ENTRY = struct.Struct('<I4sIIQIII')
#: The BA2 version, entry flags and entry marker Archive2 writes for a general archive.
VERSION, FLAGS, MARKER = 8, 0x00100100, 0xBAADF00D
#: Bytes buffered per write to the archive.
BUFFER = 16 << 20
#: Loose files read at once, and how many are read ahead of the writer.
READERS, AHEAD = 16, 256


def name_hash(text: str) -> int:
    """BA2's CRC-32 of `text` (no starting or final inversion)."""
    return zlib.crc32(text.encode('cp1252'), 0xFFFFFFFF) ^ 0xFFFFFFFF


def entry_names(name: str) -> tuple:
    """(file hash, extension field, folder hash) of archive path `name`."""
    folder, _, file = name.lower().replace('/', '\\').rpartition('\\')
    stem, dot, ext = file.rpartition('.')
    stem, ext = (stem, ext) if dot else (file, '')
    return name_hash(stem), ext.encode('cp1252')[:4].ljust(4, b'\0'), name_hash(folder)


def entries(archive: Path) -> dict:
    """{lowercase name: (offset, size)} of the uncompressed general archive `archive`."""
    with open(archive, 'rb') as f:
        _, _, kind, count, names_at = HEADER.unpack(f.read(HEADER.size))
        if kind != b'GNRL':
            return {}
        rows = [ENTRY.unpack(f.read(ENTRY.size)) for _ in range(count)]
        f.seek(names_at)
        names = [f.read(struct.unpack('<H', f.read(2))[0]).decode('cp1252').lower() for _ in range(count)]
    return {name: (row[4], row[6]) for name, row in zip(names, rows) if not row[5]}


def _loose(paths: list):
    """Each of `paths`' bytes in order, READERS at a time, AHEAD ahead."""
    with ThreadPoolExecutor(READERS) as pool:
        for start in range(0, len(paths), AHEAD):
            yield from pool.map(Path.read_bytes, map(Path, paths[start:start + AHEAD]))


def _runs(names: list, sizes: list, old: dict) -> list:
    """`names` (with `sizes`) in order as runs: (offset, length) of consecutive files lying back to back in the old
    archive (`old`: {lowercase name: (offset, size)}), or (None, index) of a file read from disk."""
    runs = []
    for i, (name, size) in enumerate(zip(names, sizes)):
        at = old.get(name.lower())
        if at is None or at[1] != size:
            runs.append((None, i))
        elif runs and runs[-1][0] is not None and sum(runs[-1]) == at[0]:
            runs[-1] = (runs[-1][0], runs[-1][1] + size)
        else:
            runs.append(at)
    return runs


def _contents(files: list, names: list, sizes: list, archive: Path, kept: set):
    """The bytes of `files` (archive `names`, `sizes`) in order, in pieces: unchanged files (lowercase names in
    `kept`) copied in blocks out of `archive`, the rest read from disk."""
    old = {n: at for n, at in entries(archive).items() if n in kept} if kept and archive.exists() else {}
    runs = _runs(names, sizes, old)
    loose = _loose([files[i] for start, i in runs if start is None])
    with open(archive, 'rb') if old else nullcontext() as previous:
        for start, length in runs:
            if start is None:
                data = next(loose)
                if len(data) != sizes[length]:
                    raise RuntimeError(f'{names[length]} changed while it was packed')
                yield data
                continue
            previous.seek(start)
            for done in range(0, length, BUFFER):
                block = previous.read(min(BUFFER, length - done))
                if len(block) != min(BUFFER, length - done):
                    raise RuntimeError(f'{archive} ends before its entries say')
                yield block


def write_general(named: dict, archive: Path, kept: set = frozenset()) -> None:
    """Write `named` ({archive name, forward slashes: path}) as the uncompressed general BA2 `archive`, in
    lowercase name order, through a temporary file replaced at the end; files whose lowercase names are in `kept`
    are unchanged since `archive` was written and are copied out of it."""
    names = sorted(named, key=str.lower)
    files = [named[name] for name in names]
    sizes = [Path(p).stat().st_size for p in files]
    offset = HEADER.size + ENTRY.size * len(files)
    temporary = archive.with_name(archive.name + '.tmp')
    with open(temporary, 'wb', buffering=BUFFER) as out:
        out.write(HEADER.pack(b'BTDX', VERSION, b'GNRL', len(files), offset + sum(sizes)))
        for name, size in zip(names, sizes):
            out.write(ENTRY.pack(*entry_names(name), FLAGS, offset, 0, size, MARKER))
            offset += size
        for data in _contents(files, names, sizes, archive, kept):
            out.write(data)
        for name in names:
            encoded = name.encode('cp1252')
            out.write(struct.pack('<H', len(encoded)) + encoded)
    os.replace(temporary, archive)
