"""An FNV or FO3 NIF read into our own blocks (fnv_schema), without pyffi's per-value objects: vertex, triangle
and other arrays of numbers stay numpy arrays (Values, Records), read and written through as pyffi's; everything
else reads as pyffi names it.

A block type the layouts do not know, or a block that fails to read, is skipped by its header size and listed in
`NifData.skipped`; a block read to a size other than its header's is listed in `NifData.resized` (pyffi skips
the same way). fnv_file reads a file with anything skipped, or another version, with pyffi instead.

See: docs/fork/research/fnv_nif_reader.md#reader
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fo4_import.nif.fnv_schema import (BS_VERSIONS, DTYPES, USER_VERSION, VERSION, columns, copy_row,
                                      fixed_dtype, klass, layouts, plan, row_class, wide)

#: Elements converted to Python values per step while iterating a large array.
CHUNK = 4096
#: The format names a NIF header line starts with.
NAMES = (b'Gamebryo File Format', b'NetImmerse File Format')


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------

class Values:
    """A numpy array of numbers seen as pyffi's array: Python numbers by index and iteration; `.array` is numpy."""

    def __init__(self, array: np.ndarray):
        """The view of `array`."""
        self.array = array

    def __len__(self) -> int:
        """The element count."""
        return len(self.array)

    def __iter__(self):
        """The elements as Python numbers."""
        for start in range(0, len(self.array), CHUNK):
            yield from self.array[start:start + CHUNK].tolist()

    def __getitem__(self, index):
        """One element as a Python number, or a slice as a list."""
        return self.array[index].tolist()

    def __setitem__(self, index, value) -> None:
        """Store `value` at `index`."""
        self.array[index] = value

    def __array__(self, dtype=None, copy=None):
        """The numpy array (np.array(view) needs no iteration)."""
        return self.array if dtype is None else self.array.astype(dtype)


class Records(Values):
    """A numpy structured array of one fixed-layout struct type seen as pyffi's array of structs: each element a
    row of the array, read and written through."""

    def __init__(self, array: np.ndarray, sub: tuple, key: tuple):
        """The view of `array`: structs of (name, template) `sub` at version `key`."""
        super().__init__(array)
        self.row, self.columns = row_class(sub[0], key, sub[1]), columns(array)

    def __iter__(self):
        """The elements, as rows."""
        row, c = self.row, self.columns
        return (row(c, i) for i in range(len(self.array)))

    def __getitem__(self, index):
        """One element as a row, or a slice as a list of them."""
        if isinstance(index, slice):
            return [self.row(self.columns, i) for i in range(len(self.array))[index]]
        return self.row(self.columns, range(len(self.array))[index])

    def __setitem__(self, index, value) -> None:
        """Every field of `value` into element `index`."""
        copy_row(self[index], value)


# ---------------------------------------------------------------------------
# The read file
# ---------------------------------------------------------------------------

@dataclass
class NifData:
    """A read NIF: its versions, header strings, blocks and roots, as pyffi's Data names them, and what was not
    read (`skipped`: (index, type, reason)) or read to another size (`resized`: (index, type, read, size))."""
    version: int
    user_version: int
    user_version_2: int
    strings: list
    blocks: list = field(default_factory=list)
    roots: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    resized: list = field(default_factory=list)


class Unread:
    """A block not read: its type name and bytes."""

    def __init__(self, kind: str, raw: bytes):
        """The block of type `kind` with bytes `raw`."""
        self.kind, self.raw = kind, raw

    def get_refs(self, data=None) -> list:
        """No references (unread)."""
        return []

    def tree(self, *args, **kwargs):
        """Itself only."""
        yield self


class _Cursor:
    """Read position in a file's bytes, the file's version and strings, and the links still to resolve."""

    def __init__(self, raw: bytes, key: tuple, strings: list):
        """A cursor at 0 over `raw`."""
        self.raw, self.pos, self.key, self.strings = raw, 0, key, strings
        self.links = []

    def many(self, fmt: str, count: int) -> tuple:
        """`count` values of struct format `fmt`."""
        values = struct.unpack_from(f'<{count}{fmt}', self.raw, self.pos)
        self.pos += struct.calcsize(f'<{count}{fmt}')
        return values

    def take(self, fmt: str):
        """One value of struct format `fmt`."""
        return self.many(fmt, 1)[0]

    def bytes(self, n: int) -> bytes:
        """The next `n` bytes."""
        if n < 0 or self.pos + n > len(self.raw):
            raise ValueError(f'{n} bytes past the end at {self.pos}')
        self.pos += n
        return self.raw[self.pos - n:self.pos]

    def array(self, dtype, count: int) -> np.ndarray:
        """`count` elements of numpy `dtype` on disk, as a new array with floats widened (fnv_schema.wide)."""
        dtype = np.dtype(dtype)
        out = np.frombuffer(self.raw, dtype, count, self.pos).astype(wide(dtype))
        self.pos += dtype.itemsize * count
        return out


# ---------------------------------------------------------------------------
# Values by kind
# ---------------------------------------------------------------------------

def _string(c: _Cursor) -> bytes:
    """A header string by index; b'' for -1 or past the table."""
    index = c.take('i')
    return b'' if index == -1 or index >= len(c.strings) else c.strings[index]


def _matrix(c: _Cursor) -> list:
    """A ByteMatrix: row size, row count, then the rows."""
    size, rows = c.many('I', 2)
    return [c.bytes(size) for _ in range(rows)]


def _uv_sets(c: _Cursor) -> int:
    """The UV-set byte; bit 0 only in a Bethesda 20.2.0.7 file, as patched pyffi.

    See: docs/commentary/asset_convert_nif.md#bethesda-geometry-data-flags
    """
    value = c.take('B')
    return value & 1 if c.key[0] == 0x14020007 and c.key[2] > 0 else value


#: Readers of each basic kind: (cursor, field) -> value.
_READERS = {
    'num': lambda c, f: c.take(f.fmt),
    'bool': lambda c, f: bool(c.take('B')),
    'uvsets': lambda c, f: _uv_sets(c),
    'ref': lambda c, f: c.take('i'),
    'ptr': lambda c, f: c.take('i'),
    'string': lambda c, f: _string(c),
    'sized': lambda c, f: c.bytes(c.take('I')),
    'short': lambda c, f: c.bytes(c.take('B')).rstrip(b'\x00'),
    'line': lambda c, f: c.bytes(c.raw.index(b'\n', c.pos) + 1 - c.pos).rstrip(b'\n'),
    'bytes': lambda c, f: c.bytes(c.take('I')),
    'matrix': lambda c, f: _matrix(c),
    'char': lambda c, f: c.bytes(1),
    'bits': lambda c, f: f.sub(c.take(f.fmt)),
}


def _one(c: _Cursor, f, arg):
    """One value of field `f` (argument `arg`)."""
    if f.kind == 'struct':
        return read_struct(c, f.sub[0], f.sub[1], arg)
    return _READERS[f.kind](c, f)


def _many(c: _Cursor, f, arg, n: int):
    """`n` values of field `f`: numbers and fixed-layout structs as one numpy array, links and the rest as a list."""
    if n < 0 or n > 0x10000000:
        raise ValueError(f'array of {n} {f.name}')
    if f.kind in ('num', 'bool'):
        return Values(c.array(DTYPES[f.fmt], n))
    dtype = fixed_dtype(f.sub[0], c.key, f.sub[1]) if f.kind == 'struct' else None
    if dtype is not None:
        return Records(c.array(dtype, n), f.sub, c.key)
    return [_one(c, f, arg) for _ in range(n)]


def _value(c: _Cursor, s, f, arg):
    """Field `f` of struct `s`: one value, an array, or rows of an array (one count, or a count per row)."""
    if f.arr1 is None:
        value = _one(c, f, arg)
    elif f.arr2 is None:
        value = _many(c, f, arg, f.arr1(s))
    else:
        rows, per = f.arr1(s), f.arr2(s)
        value = [_many(c, f, arg, per if isinstance(per, int) else int(per[i])) for i in range(rows)]
    if f.kind in ('ref', 'ptr'):
        c.links.append((s, f.name, f.arr1 is not None, f.arr2 is not None))
    return value


def read_struct(c: _Cursor, name: str, template=None, arg=None):
    """Our struct `name` read at the cursor, as pyffi's StructBase.read."""
    out = klass(name)(template, arg)
    fields, dups = plan(name, c.key, template)
    seen = set() if dups else None
    for f in fields:
        if seen is not None and f.name in seen or f.cond is not None and not f.cond(out):
            continue
        if seen is not None:
            seen.add(f.name)
        value_arg = f.arg if f.arg is None or isinstance(f.arg, int) else getattr(out, f.arg)
        out.__dict__[f.name] = _value(c, out, f, value_arg)
    return out


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def header_start(raw: bytes) -> int:
    """Where the format name starts in `raw`'s header line (0: at the start, or none)."""
    line = raw[:raw.find(b'\n')] if b'\n' in raw else raw
    return 0 if line.startswith(NAMES) else max(0, *(line.rfind(name) for name in NAMES))


def read_header(raw: bytes) -> tuple:
    """(NifData, [(block type, size)], position of the first block) of an FO3/FNV NIF (fnv_schema.KEYS);
    ValueError for another version."""
    c = _Cursor(raw, None, [])
    c.pos = raw.index(b'\n') + 1
    version, _, user, n_blocks = c.take('I'), c.take('B'), c.take('I'), c.take('I')
    bsver = c.take('I') if version == VERSION and user == USER_VERSION else None
    if bsver not in BS_VERSIONS:
        raise ValueError(f'not an FO3/FNV NIF: {version:#x} {user} {bsver}')
    for _ in range(3):
        c.bytes(c.take('B'))
    types = [c.bytes(c.take('I')).decode('latin1') for _ in range(c.take('H'))]
    index, sizes = c.many('H', n_blocks), c.many('I', n_blocks)
    strings = [c.bytes(c.take('I')) for _ in range(c.many('I', 2)[0])]
    c.many('I', c.take('I'))
    data = NifData(version, user, bsver, strings)
    return data, [(types[i & 0xFFF], s) for i, s in zip(index, sizes)], c.pos


def _block(c: _Cursor, data: NifData, at: int, kind: str, size: int):
    """Block `at` of type `kind` and `size` bytes read at the cursor (left at its end), or Unread."""
    start = c.pos
    try:
        if kind not in layouts()['structs']:
            raise ValueError('type unknown to the layouts')
        block = read_struct(c, kind)
    except (ValueError, struct.error, IndexError, TypeError, AttributeError) as error:
        data.skipped.append((at, kind, str(error)))
        block = Unread(kind, c.raw[start:start + size])
    if c.pos - start != size and not isinstance(block, Unread):
        data.resized.append((at, kind, c.pos - start, size))
    c.pos = start + size
    return block


def _resolve(c: _Cursor, data: NifData) -> None:
    """Every link read (a block index) as the block, None for -1 or an index past the blocks."""
    blocks = data.blocks
    find = lambda i: blocks[i] if 0 <= i < len(blocks) else None
    for s, name, array, rows in c.links:
        value = s.__dict__[name]
        s.__dict__[name] = [[find(i) for i in row] for row in value] if rows else \
            [find(i) for i in value] if array else find(value)


def read_bytes(raw: bytes) -> NifData:
    """The NifData of an FNV/FO3 NIF's bytes (stray bytes before its header line skipped)."""
    raw = raw[header_start(raw):]
    data, entries, pos = read_header(raw)
    c = _Cursor(raw, (data.version, data.user_version, data.user_version_2), data.strings)
    c.pos = pos
    for at, (kind, size) in enumerate(entries):
        data.blocks.append(_block(c, data, at, kind, size))
    roots = c.many('i', c.take('I'))
    _resolve(c, data)
    data.roots = [data.blocks[i] for i in roots if 0 <= i < len(data.blocks)]
    return data


def read(path) -> NifData:
    """The NifData of the FNV/FO3 NIF at `path`."""
    return read_bytes(Path(path).read_bytes())
