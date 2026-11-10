"""A Fallout 4 NIF file: header, string table, blocks and footer, read and written.

The header keeps everything the game ignores (author, export script) so a
read file writes back byte for byte; `NifFile.new` makes a file for our own
blocks.

See: docs/fork/fo4_spikes.md#spike-2-nif
"""

import struct
from dataclasses import dataclass, field

from fo4_import.nif.anim_blocks import ANIM_BLOCKS
from fo4_import.nif.blocks import BLOCKS as STATIC_BLOCKS, Reader
from fo4_import.nif.particle_blocks import PARTICLE_BLOCKS

#: Every block type this package reads and writes.
BLOCKS = {**STATIC_BLOCKS, **ANIM_BLOCKS, **PARTICLE_BLOCKS}

HEADER_TEXT = b'Gamebryo File Format, Version 20.2.0.7\n'
VERSION, USER_VERSION, BS_VERSION = 0x14020007, 12, 130


@dataclass
class NifFile:
    """A NIF as its header strings, its blocks [(type, dict or raw bytes)] and its roots."""
    author: bytes = b'\x00'
    process: bytes = b'\x00'
    export: bytes = b'\x00'
    max_filepath: bytes = b'\x00'
    strings: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    roots: list = field(default_factory=lambda: [0])

    def string(self, text: str) -> int:
        """The string table index of `text`, added when new; -1 for ''."""
        if not text:
            return -1
        if text not in self.strings:
            self.strings.append(text)
        return self.strings.index(text)

    def empty_string(self) -> int:
        """The string table index of '' itself (added when new), where -1 will not do."""
        if '' not in self.strings:
            self.strings.append('')
        return self.strings.index('')


def _short(data: bytes, pos: int) -> tuple:
    """(a u8-length export string with its terminator, next position)."""
    n = data[pos]
    return data[pos + 1:pos + 1 + n], pos + 1 + n


def read_header(data: bytes) -> tuple:
    """(NifFile with its header strings, [(type, size)], first block position)."""
    pos = len(HEADER_TEXT)
    version, _, user, n_blocks, bs = struct.unpack_from('<IBIII', data, pos)
    if (version, user, bs) != (VERSION, USER_VERSION, BS_VERSION):
        raise ValueError(f'not a Fallout 4 NIF: {version:#x} {user} {bs}')
    pos += 17
    nif = NifFile()
    nif.author, pos = _short(data, pos)
    nif.process, pos = _short(data, pos)
    nif.export, pos = _short(data, pos)
    nif.max_filepath, pos = _short(data, pos)
    n_types = struct.unpack_from('<H', data, pos)[0]
    pos += 2
    types = []
    for _ in range(n_types):
        n = struct.unpack_from('<I', data, pos)[0]
        types.append(data[pos + 4:pos + 4 + n].decode('ascii'))
        pos += 4 + n
    index = struct.unpack_from(f'<{n_blocks}H', data, pos)
    sizes = struct.unpack_from(f'<{n_blocks}I', data, pos + 2 * n_blocks)
    pos += 6 * n_blocks
    n_strings = struct.unpack_from('<I', data, pos)[0]
    pos += 8
    for _ in range(n_strings):
        n = struct.unpack_from('<I', data, pos)[0]
        nif.strings.append(data[pos + 4:pos + 4 + n].decode('cp1252'))
        pos += 4 + n
    n_groups = struct.unpack_from('<I', data, pos)[0]
    return nif, [(types[i & 0x7FFF], s) for i, s in zip(index, sizes)], pos + 4 + 4 * n_groups


def _parsed(kind: str, raw: bytes):
    """A block's dict, or its raw bytes when its type or variant has no reader."""
    reader = BLOCKS.get(kind, (None, None))[0]
    if reader is None:
        return raw
    try:
        return reader(Reader(raw))
    except ValueError:
        return raw


def read(data: bytes) -> NifFile:
    """A NifFile from bytes; block types (and variants, such as skinned shapes) this module does not know stay raw."""
    nif, entries, pos = read_header(data)
    for kind, size in entries:
        raw = data[pos:pos + size]
        nif.blocks.append((kind, _parsed(kind, raw)))
        pos += size
    n_roots = struct.unpack_from('<I', data, pos)[0]
    nif.roots = list(struct.unpack_from(f'<{n_roots}i', data, pos + 4))
    return nif


def _sized(text: str) -> bytes:
    """A u32-length string."""
    raw = text.encode('cp1252')
    return struct.pack('<I', len(raw)) + raw


def write(nif: NifFile) -> bytes:
    """The file's bytes."""
    bodies = [b if isinstance(b, bytes) else BLOCKS[kind][1](b) for kind, b in nif.blocks]
    types = list(dict.fromkeys(kind for kind, _ in nif.blocks))
    out = HEADER_TEXT + struct.pack('<IBIII', VERSION, 1, USER_VERSION, len(nif.blocks), BS_VERSION)
    for text in (nif.author, nif.process, nif.export, nif.max_filepath):
        out += bytes([len(text)]) + text
    out += struct.pack('<H', len(types)) + b''.join(_sized(t) for t in types)
    out += struct.pack(f'<{len(nif.blocks)}H', *(types.index(kind) for kind, _ in nif.blocks))
    out += struct.pack(f'<{len(bodies)}I', *(len(b) for b in bodies))
    longest = max((len(s.encode('cp1252')) for s in nif.strings), default=0)
    out += struct.pack('<II', len(nif.strings), longest) + b''.join(_sized(s) for s in nif.strings)
    out += struct.pack('<I', 0) + b''.join(bodies)
    return out + struct.pack(f'<I{len(nif.roots)}i', len(nif.roots), *nif.roots)


def hang_from(nif: NifFile, bone: str) -> None:
    """Hang the NIF from `bone`: `Prn` string extra data, first on the root."""
    nif.blocks.append(('NiStringExtraData', struct.pack('<ii', nif.string('Prn'), nif.string(bone))))
    root = nif.blocks[0][1]
    root['extra'] = [len(nif.blocks) - 1] + root['extra']

