"""Fallout 4 BA2 archives: read the game's own meshes, materials and textures.

A BA2 is `BTDX`, a version, a type (`GNRL` files or `DX10` textures), the
file count and the offset of the name table (per file a u16 length and the
path). A GNRL entry is one zlib blob; a DX10 entry is a texture header and
chunks of mips. Textures come back as a DDS of the top mip only (DX10 header),
which is what analysis needs.

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

import struct
import zlib
from pathlib import Path

#: Bytes per 4x4 block of the block-compressed DXGI formats; others are 4 bytes per pixel.
BLOCK_BYTES = {70: 8, 71: 8, 72: 8, 80: 8, 81: 8, 73: 16, 74: 16, 75: 16, 76: 16, 77: 16, 78: 16,
               82: 16, 83: 16, 84: 16, 94: 16, 95: 16, 96: 16, 97: 16, 98: 16, 99: 16}
GNRL_ENTRY, DX10_ENTRY, DX10_CHUNK = struct.Struct('<I4sIIQIII'), struct.Struct('<I4sIBBHHHBBBB'), \
    struct.Struct('<QIIHHI')


def _blob(raw, offset: int, packed: int, size: int) -> bytes:
    """One stored or zlib-packed blob."""
    data = raw[offset:offset + (packed or size)]
    return zlib.decompress(data) if packed else bytes(data)


def _mip0_size(fmt: int, width: int, height: int) -> int:
    """Bytes of a texture's top mip."""
    if fmt in BLOCK_BYTES:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * BLOCK_BYTES[fmt]
    return width * height * 4


def dds(fmt: int, width: int, height: int, pixels: bytes) -> bytes:
    """A one-mip DDS with a DX10 header around `pixels`."""
    header = struct.pack('<4sIIIIIII44sII4s5I', b'DDS ', 124, 0x1007, height, width, 0, 1, 0, b'\0' * 44,
                         32, 4, b'DX10', 0, 0, 0, 0, 0)
    header += struct.pack('<IIIII', 0x1000, 0, 0, 0, 0)
    return header + struct.pack('<IIIII', fmt, 3, 0, 1, 0) + pixels


class Archive:
    """One BA2: its paths (lowercase, backslashes) and their bytes."""

    def __init__(self, path: Path):
        """Index the archive at `path`."""
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            magic, _, self.kind, count, names_at = struct.unpack('<4sI4sIQ', f.read(24))
            assert magic == b'BTDX', self.path
            entries = [self._entry(f) for _ in range(count)]
            f.seek(names_at)
            names = [f.read(struct.unpack('<H', f.read(2))[0]).decode('cp1252').lower() for _ in range(count)]
        self.entries = dict(zip(names, entries))

    def _entry(self, f) -> tuple:
        """One file's entry: (offset, packed, size) for GNRL; (format, width, height, first chunk) for DX10."""
        if self.kind == b'GNRL':
            _, _, _, _, offset, packed, size, _ = GNRL_ENTRY.unpack(f.read(GNRL_ENTRY.size))
            return offset, packed, size
        e = DX10_ENTRY.unpack(f.read(DX10_ENTRY.size))
        chunks = [DX10_CHUNK.unpack(f.read(DX10_CHUNK.size)) for _ in range(e[4])]
        return e[9], e[7], e[6], chunks[0][:3]

    def read(self, name: str) -> bytes:
        """The file's bytes; a texture as a one-mip DDS."""
        entry = self.entries[name.lower().replace('/', chr(92))]
        with open(self.path, 'rb') as f:
            if self.kind == b'GNRL':
                f.seek(entry[0])
                return _blob(f.read(entry[1] or entry[2]), 0, entry[1], entry[2])
            fmt, width, height, (offset, packed, size) = entry
            f.seek(offset)
            pixels = _blob(f.read(packed or size), 0, packed, size)
        return dds(fmt, width, height, pixels[:_mip0_size(fmt, width, height)])


class Archives:
    """Every BA2 in a Data folder, later archives winning, read by path."""

    def __init__(self, data_dir: Path, pattern: str = 'Fallout4 - *.ba2'):
        """Index the archives in `data_dir` matching `pattern`."""
        self.by_name = {}
        for path in sorted(Path(data_dir).glob(pattern)):
            archive = Archive(path)
            self.by_name.update(dict.fromkeys(archive.entries, archive))

    def names(self, prefix: str = '') -> list:
        """Paths starting with `prefix` (any case, either slash)."""
        prefix = prefix.lower().replace('/', chr(92))
        return sorted(n for n in self.by_name if n.startswith(prefix))

    def read(self, name: str) -> bytes:
        """The file at `name` from the archive that has it."""
        key = name.lower().replace('/', chr(92))
        return self.by_name[key].read(key)
