"""Havok 2014 64-bit packfile writer: objects as packfile.read gives them -> bytes.

Layout as the game's files have it: the top-level object first, then a depth-first walk over pointers in member
order; each object followed by its own array contents and strings. Reproduces vanilla behaviour, character and
project files byte for byte.

See: docs/fork/fo4_spikes.md#own-rig-code
"""

import struct

from fo4_import.havok.packfile import ARRAYS, FLOATS, PRIM, STRINGS, Classes, classes

BASE_CLASSES = ((0x33d42383, 'hkClass'), (0xb0efa719, 'hkClassMember'), (0x8a3609cf, 'hkClassEnum'),
                (0xce6f8a6c, 'hkClassEnumItem'))
DATA_SECTION = 2
MAGIC = bytes.fromhex('57e0e05710c0c010')
#: The header extension vanilla animation and skeleton files carry after the 64-byte header (behaviours have none).
EXTENSION = struct.pack('<I', 0x14) + bytes(12)


def pad16(buf: bytearray, fill: int = 0) -> None:
    buf.extend(bytes([fill]) * (-len(buf) % 16))


def flatten(entries):
    """Pointer fixups in member order, an array's element pointers where the array member sits."""
    for e in entries:
        if isinstance(e, list):
            yield from flatten(e)
        else:
            yield e


class Writer:
    """Lays out and serializes one object graph."""

    def __init__(self, objects: list, top: str, cl: Classes, keep_order: bool):
        """Order the objects reached from `top`: depth first, or in list order with `keep_order`."""
        self.cl, self.by = cl, {o['#']: o for o in objects}
        self.buf, self.local, self.glob, self.virtual, self.pos = bytearray(), [], [], [], {}
        self.order, self.sink, self.pending = [], self.glob, {}
        self._walk(top)
        for name in self.order:
            o = self.by[name]
            for ref in self._fixed_refs(o['class'], o['fields']):
                self._walk(ref)
        if keep_order:
            reached = set(self.order)
            self.order = [o['#'] for o in objects if o['#'] in reached]

    def _walk(self, name) -> None:
        """Append `name` and, depth first, every object it points to."""
        if name is None or name in self.order:
            return
        self.order.append(name)
        o = self.by[name]
        for ref in self._refs(o['class'], o['fields']):
            self._walk(ref)

    def _refs(self, cls: str, fields: dict) -> list:
        """The object names a `cls` value points to, in member order."""
        return [ref for m in self.cl.members(cls) if not m.ignored and not m.arrsize
                for ref in self._value_refs(m, fields[m.name])]

    def _fixed_refs(self, cls: str, fields: dict) -> list:
        """The object names a `cls` value points to from inside fixed-size arrays (a ragdoll constraint's motors),
        which _refs leaves out; walked after it, so files without them keep their order."""
        out = []
        for m in (m for m in self.cl.members(cls) if not m.ignored):
            value = fields[m.name]
            if m.arrsize:
                out += [ref for v in value for ref in self._value_refs(m.single(), v)]
            if m.vtype == 'TYPE_STRUCT':
                out += [ref for v in (value if m.arrsize else [value]) for ref in self._fixed_refs(m.ctype, v)]
            elif m.vtype in ARRAYS and m.sub == 'TYPE_STRUCT':
                out += [ref for v in value for ref in self._fixed_refs(m.ctype, v)]
        return out

    def _value_refs(self, m, value) -> list:
        """The object names one member value points to."""
        if m.vtype in ('TYPE_POINTER', 'TYPE_VARIANT'):
            return [value]
        if m.vtype == 'TYPE_STRUCT':
            return self._refs(m.ctype, value)
        if m.vtype not in ARRAYS:
            return []
        if m.sub == 'TYPE_POINTER':
            return list(value)
        return [ref for v in value for ref in self._refs(m.ctype, v)] if m.sub == 'TYPE_STRUCT' else []

    def write(self) -> 'Writer':
        """Serialize every object in walk order."""
        for name in self.order:
            o = self.by[name]
            pad16(self.buf)
            at = len(self.buf)
            self.pos[name] = at
            self.virtual.append((at, o['class']))
            tail = o['fields'].get('__tail__', b'')
            size = self.cl.size(o['class']) if tail else -(-self.cl.size(o['class']) // 16) * 16
            self.buf.extend(bytes(size) + tail)
            self._fill(at, o['class'], o['fields'])
            self._deferred(at, o['class'], o['fields'])
        pad16(self.buf)
        return self

    def _fill(self, at: int, cls: str, fields: dict) -> None:
        """Write a `cls` value's members at `at` (arrays get their counts; contents come later)."""
        for m in self.cl.members(cls):
            if not m.ignored:
                self._put(at + m.offset, m, fields[m.name])
            elif m.vtype == 'TYPE_ARRAY' and not m.arrsize:
                struct.pack_into('<I', self.buf, at + m.offset + 12, 0x80000000)

    def _put(self, at: int, m, value) -> None:
        """Write one member's value at `at`."""
        if m.arrsize:
            size = self.cl.member_size(m)[0] // m.arrsize
            for i, v in enumerate(value):
                self._scalar(at + i * size, m.vtype, m.sub, m.ctype, v)
        elif m.vtype in ARRAYS:
            struct.pack_into('<iI', self.buf, at + 8, len(value), len(value) | 0x80000000)
            self.pending[at] = []
            self.sink.append(self.pending[at])
        elif m.vtype == 'TYPE_RELARRAY':
            struct.pack_into('<HH', self.buf, at, *value)
        else:
            self._scalar(at, m.vtype, m.sub, m.ctype, value)

    def _scalar(self, at: int, vtype: str, sub, ctype, value) -> None:
        """Write one value of `vtype`; a pointer becomes a fixup for its target."""
        if vtype in ('TYPE_ENUM', 'TYPE_FLAGS'):
            vtype = sub
        if vtype in PRIM:
            struct.pack_into(PRIM[vtype][0], self.buf, at, value)
            return
        if vtype in FLOATS:
            struct.pack_into(f'<{FLOATS[vtype]}f', self.buf, at, *value)
            return
        if vtype == 'TYPE_STRUCT':
            self._fill(at, ctype, value)
            return
        if vtype in ('TYPE_POINTER', 'TYPE_VARIANT') and value is not None:
            self.sink.append((at, value))

    def _deferred(self, at: int, cls: str, fields: dict) -> None:
        """Write a `cls` value's strings and array contents after it."""
        for m in self.cl.members(cls):
            if not m.ignored and not m.arrsize:
                self._deferred_member(at + m.offset, m, fields[m.name])

    def _deferred_member(self, at: int, m, value) -> None:
        """One member's deferred data: its string, struct contents or array."""
        if m.vtype in STRINGS:
            self._string(at, value)
        elif m.vtype == 'TYPE_STRUCT':
            self._deferred(at, m.ctype, value)
        elif m.vtype in ARRAYS and value:
            self._array(at, m, value)

    def _array(self, at: int, m, value: list) -> None:
        """An array's elements (16-aligned), then their strings and struct contents."""
        pad16(self.buf)
        start = len(self.buf)
        self.local.append((at, start))
        size = self.cl.element(m.sub, m.ctype)[0]
        self.buf.extend(bytes(size * len(value)))
        outer, self.sink = self.sink, self.pending.pop(at)
        for i, v in enumerate(value):
            self._scalar(start + i * size, m.sub, None, m.ctype, v)
        for i, v in enumerate(value):
            if m.sub in STRINGS:
                self._string(start + i * size, v, 2)
            elif m.sub == 'TYPE_STRUCT':
                self._deferred(start + i * size, m.ctype, v)
        self.sink = outer
        if m.sub in STRINGS:
            pad16(self.buf)

    def _string(self, at: int, value, align: int = 16) -> None:
        """A string for the pointer at `at`, padded to `align`."""
        if value is None:
            return
        self.local.append((at, len(self.buf)))
        self.buf.extend(value.encode('latin-1') + b'\0')
        self.buf.extend(bytes(-len(self.buf) % align))

    def classnames(self) -> tuple:
        """(the `__classnames__` section, {class: offset of its name})."""
        names, seen = bytearray(), {}
        for sig, cls in list(BASE_CLASSES) + [(self.cl.signature(c), c) for _, c in self.virtual]:
            if cls not in seen:
                names.extend(struct.pack('<IB', sig, 9))
                seen[cls] = len(names)
                names.extend(cls.encode() + b'\0')
        pad16(names, 0xFF)
        return bytes(names), seen

    def tables(self, offs: dict) -> list:
        """The local, global and virtual fixup tables, each padded with FF."""
        local = b''.join(struct.pack('<II', s, d) for s, d in self.local)
        glob = b''.join(struct.pack('<III', s, DATA_SECTION, self.pos[d]) for s, d in flatten(self.glob))
        virt = b''.join(struct.pack('<III', s, 0, offs[c]) for s, c in self.virtual)
        out = [bytearray(t) for t in (local, glob, virt)]
        for t in out:
            pad16(t, 0xFF)
        return out


def section_header(name: str, start: int, offsets: list) -> bytes:
    """A 64-byte section header: name, marker, start and six offsets."""
    head = name.encode().ljust(16, b'\0') + struct.pack('<II', 0xFF000000, start)
    return head + struct.pack('<6I', *offsets) + b'\xff' * 16


def file_header(top_offset: int, extension: bytes) -> bytearray:
    """The hk_2014.1.0-r1 AMD64 packfile header, with `extension` after its 64 bytes."""
    header = bytearray(64)
    header[0:8] = MAGIC
    struct.pack_into('<4i', header, 0x08, 0, 11, 0x01000108, 3)
    struct.pack_into('<4i', header, 0x18, DATA_SECTION, 0, 0, top_offset)
    header[0x28:0x38] = b'hk_2014.1.0-r1\x00\xff'
    struct.pack_into('<iHH', header, 0x38, 0, 21, len(extension))
    return header + extension


def write(objects: list, top: str, cl: Classes = None, extension: bool = False, keep_order: bool = False) -> bytes:
    """The packfile bytes for `objects` with `top` as the contents object; `extension` for an animation or
    skeleton file; `keep_order` writes the objects reached from `top` in list order (a read file's own order)
    instead of the depth-first order behaviour files use."""
    w = Writer(objects, top, cl or classes(), keep_order).write()
    names, offs = w.classnames()
    tables = w.tables(offs)
    out = file_header(offs[w.by[top]['class']], EXTENSION if extension else b'')
    names_at = len(out) + 3 * 0x40
    data_at = names_at + len(names)
    marks, run = [], len(w.buf)
    for t in tables:
        marks.append(run)
        run += len(t)
    out += section_header('__classnames__', names_at, [len(names)] * 6)
    out += section_header('__types__', data_at, [0] * 6)
    out += section_header('__data__', data_at, marks + [run, run, run])
    return bytes(out + names + w.buf + b''.join(tables))
