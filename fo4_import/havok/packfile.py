"""Havok 2014 (hk_2014.1.0-r1, 64-bit) packfile reader, driven by the class layouts in data/hk2014_layouts.json.

`read(data)` gives a Packfile whose `objects` are, in file order, `{'#': name, 'class': cls, 'fields': {...}}`:
pointers as object names, strings as str, arrays as lists, structs as dicts; a shape's relative-array contents
past its class size as `fields['__tail__']`. packfile_write writes the same objects back byte for byte.

See: docs/fork/fo4_spikes.md#own-rig-code
"""

import json
import struct
from functools import lru_cache
from pathlib import Path

LAYOUTS = Path(__file__).resolve().parents[1] / 'data' / 'hk2014_layouts.json'
PRIM = {'TYPE_BOOL': ('<B', 1), 'TYPE_CHAR': ('<b', 1), 'TYPE_INT8': ('<b', 1), 'TYPE_UINT8': ('<B', 1),
        'TYPE_INT16': ('<h', 2), 'TYPE_UINT16': ('<H', 2), 'TYPE_HALF': ('<H', 2), 'TYPE_INT32': ('<i', 4),
        'TYPE_UINT32': ('<I', 4), 'TYPE_REAL': ('<f', 4), 'TYPE_INT64': ('<q', 8), 'TYPE_UINT64': ('<Q', 8),
        'TYPE_ULONG': ('<Q', 8)}
FLOATS = {'TYPE_VECTOR4': 4, 'TYPE_QUATERNION': 4, 'TYPE_MATRIX3': 12, 'TYPE_ROTATION': 12,
          'TYPE_QSTRANSFORM': 12, 'TYPE_MATRIX4': 16, 'TYPE_TRANSFORM': 16}
SIZED = {'TYPE_POINTER': (8, 8), 'TYPE_STRINGPTR': (8, 8), 'TYPE_CSTRING': (8, 8), 'TYPE_ARRAY': (16, 8),
         'TYPE_SIMPLEARRAY': (16, 8), 'TYPE_RELARRAY': (4, 2), 'TYPE_VARIANT': (16, 8)}
ARRAYS = ('TYPE_ARRAY', 'TYPE_SIMPLEARRAY')
STRINGS = ('TYPE_STRINGPTR', 'TYPE_CSTRING')


class Member:
    """One class member: name, offset, value type and subtype, struct type, fixed array size, flags."""

    def __init__(self, name, offset, vtype, sub, ctype, arrsize, flags):
        """One row of a class's member list in hk2014_layouts.json."""
        self.name, self.offset, self.vtype, self.sub = name, offset, vtype, sub
        self.ctype, self.arrsize, self.flags = ctype, arrsize, flags
        self.ignored = flags == 'SERIALIZE_IGNORED'

    def single(self):
        """This member as one element of its fixed array."""
        return Member(self.name, self.offset, self.vtype, self.sub, self.ctype, 0, self.flags)


class Classes:
    """Class layouts with parent chains, sizes and alignments."""

    def __init__(self, layouts: dict):
        """Layouts as hk2014_layouts.json holds them: {class: {parent, signature, ...}}."""
        self.raw = layouts
        self._members, self._size = {}, {}

    def signature(self, cls: str) -> int:
        return int(self.raw[cls]['signature'], 16)

    def members(self, cls: str) -> list:
        """All members, parents first."""
        if cls not in self._members:
            entry = self.raw[cls]
            parent = entry['parent']
            own = [Member(*m) for m in entry['members']]
            self._members[cls] = (self.members(parent) if parent else []) + own
        return self._members[cls]

    def element(self, vtype: str, ctype) -> tuple:
        """(size, alignment) of one value of `vtype`."""
        if vtype in PRIM:
            return PRIM[vtype][1], PRIM[vtype][1]
        if vtype in FLOATS:
            return FLOATS[vtype] * 4, 16
        if vtype in SIZED:
            return SIZED[vtype]
        if vtype == 'TYPE_STRUCT':
            return self.size(ctype), self.align(ctype)
        raise KeyError(vtype)

    def member_size(self, m: Member) -> tuple:
        """(size, alignment) of a member; enums by storage, fixed arrays whole."""
        vtype = m.sub if m.vtype in ('TYPE_ENUM', 'TYPE_FLAGS') else m.vtype
        size, align = self.element(vtype, m.ctype)
        return size * max(m.arrsize, 1), 16 if m.flags == 'ALIGN_16' else align

    def align(self, cls: str) -> int:
        return max([8 if self.virtual(cls) else 1] + [self.member_size(m)[1] for m in self.members(cls)])

    def virtual(self, cls: str) -> bool:
        """Whether `cls` derives from hkBaseObject (has a vtable)."""
        while cls:
            if cls == 'hkBaseObject':
                return True
            cls = self.raw[cls]['parent']
        return False

    def size(self, cls: str) -> int:
        """The class's byte size: its members' end, rounded up to its alignment."""
        if cls not in self._size:
            end = max([8 if self.virtual(cls) else 0]
                      + [m.offset + self.member_size(m)[0] for m in self.members(cls)])
            a = self.align(cls)
            self._size[cls] = -(-end // a) * a
        return self._size[cls]


@lru_cache(maxsize=1)
def classes() -> Classes:
    """The shipped layout table, read once."""
    return Classes(json.loads(LAYOUTS.read_text(encoding='utf-8')))


def cstring(data: bytes, at: int) -> str:
    return data[at:data.index(b'\0', at)].decode('latin-1')


class Packfile:
    """A parsed packfile: sections, fixups and decoded objects."""

    def __init__(self, data: bytes, cl: Classes, only: frozenset = None):
        """Parse the header, sections and fixup tables, then decode every object (`only`: just those classes', the
        rest left with no fields, so a file holding classes the layout table lacks can still be read)."""
        self.data, self.cl, self.sections = data, cl, {}
        self.extension = struct.unpack_from('<H', data, 0x3E)[0] > 0
        first = 0x40 + struct.unpack_from('<H', data, 0x3E)[0]
        for i in range(struct.unpack_from('<i', data, 0x14)[0]):
            base = first + i * 0x40
            name = data[base:base + 16].split(b'\0')[0].decode()
            start = struct.unpack_from('<I', data, base + 0x14)[0]
            self.sections[name] = (i, start, [start + o for o in struct.unpack_from('<6I', data, base + 0x18)])
        _, self.base, (lf, gf, vf, ex, _im, _end) = self.sections['__data__']
        self.local = dict(self._table(lf, gf, 2))
        self.glob = {src: dst for src, _, dst in self._table(gf, vf, 3)}
        names = self.sections['__classnames__'][1]
        self.virtual = [(src, cstring(data, names + noff)) for src, _, noff in self._table(vf, ex, 3)]
        self.at = {src: (f'#{i:04d}', cls) for i, (src, cls) in enumerate(self.virtual)}
        self.objects = [self.object(src, cls) if only is None or cls in only else
                        {'#': self.at[src][0], 'class': cls, 'fields': {}} for src, cls in self.virtual]

    def _table(self, start: int, end: int, width: int) -> list:
        """A fixup table's rows of `width` u32s, up to its FF padding."""
        out = []
        for pos in range(start, end - 4 * width + 1, 4 * width):
            row = struct.unpack_from(f'<{width}I', self.data, pos)
            if row[0] == 0xFFFFFFFF:
                break
            out.append(row)
        return out

    def object(self, rel: int, cls: str) -> dict:
        """The object at `rel`: its name, class and fields (with any inline tail)."""
        fields = self.fields(rel, cls)
        tail = self.tail(rel, cls)
        if tail:
            fields['__tail__'] = tail
        return {'#': self.at[rel][0], 'class': cls, 'fields': fields}

    def tail(self, rel: int, cls: str) -> bytes:
        """The bytes an object's relative arrays point into past its class size (shapes keep vertices there)."""
        size = end = self.cl.size(cls)
        for m in self.cl.members(cls):
            if m.vtype == 'TYPE_RELARRAY':
                count, off = struct.unpack_from('<HH', self.data, self.base + rel + m.offset)
                if count:
                    end = max(end, m.offset + off + count * self.cl.element(m.sub, m.ctype)[0])
        return self.data[self.base + rel + size:self.base + rel + end] if end > size else b''

    def fields(self, rel: int, cls: str) -> dict:
        return {m.name: self.value(rel + m.offset, m) for m in self.cl.members(cls) if not m.ignored}

    def value(self, rel: int, m: Member):
        """Member `m`'s value at `rel`."""
        if m.arrsize:
            size = self.cl.member_size(m)[0] // m.arrsize
            return [self.value(rel + i * size, m.single()) for i in range(m.arrsize)]
        if m.vtype in ('TYPE_ENUM', 'TYPE_FLAGS'):
            return struct.unpack_from(PRIM[m.sub][0], self.data, self.base + rel)[0]
        if m.vtype in ARRAYS:
            return self.array(rel, m)
        if m.vtype == 'TYPE_RELARRAY':
            return struct.unpack_from('<HH', self.data, self.base + rel)
        return self.scalar(rel, m.vtype, m.ctype)

    def scalar(self, rel: int, vtype: str, ctype):
        """One value of `vtype` at `rel`: number, floats, object name, string or struct fields."""
        if vtype in PRIM:
            return struct.unpack_from(PRIM[vtype][0], self.data, self.base + rel)[0]
        if vtype in FLOATS:
            return struct.unpack_from(f'<{FLOATS[vtype]}f', self.data, self.base + rel)
        if vtype in ('TYPE_POINTER', 'TYPE_VARIANT'):
            dst = self.glob.get(rel)
            return self.at[dst][0] if dst is not None else None
        if vtype in STRINGS:
            dst = self.local.get(rel)
            return cstring(self.data, self.base + dst) if dst is not None else None
        if vtype == 'TYPE_STRUCT':
            return self.fields(rel, ctype)
        raise KeyError(vtype)

    def array(self, rel: int, m: Member) -> list:
        """An hkArray member's elements."""
        count = struct.unpack_from('<i', self.data, self.base + rel + 8)[0]
        dst = self.local.get(rel)
        if not count or dst is None:
            return []
        size = self.cl.element(m.sub, m.ctype)[0]
        return [self.scalar(dst + i * size, m.sub, m.ctype) for i in range(count)]


def read(data: bytes, cl: Classes = None, only: frozenset = None) -> Packfile:
    """Parse a 64-bit Havok 2014 packfile (`only`: decode just those classes' objects)."""
    return Packfile(data, cl or classes(), only)
