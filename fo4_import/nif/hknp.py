"""Read Fallout 4's Elric physics (a bhkPhysicsSystem's Havok 2014 packfile): each body's vertices.

The block is a u32 length and a binary packfile: a 0x40 header, 0x40-byte
section headers (tag, then data start and the local, global and virtual
fixup tables, relative to it), and the `__data__` section. Pointers are
zero in the file; the fixups say where each points. Layouts (64-bit) were
read off Elric output: a hknpPhysicsSystemData's body infos (0x60 each:
shape, then position and orientation at 0x30), a convex polytope's vertex
hkRelArray, and a compressed mesh's sections (vertices packed 11/11/10 bits
on the section's offset and scale) and shared vertices (21/21/22 bits over
the tree's box). Lengths are FO4 Havok units.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import struct

import numpy as np

#: Byte offsets inside the data section's objects (64-bit hk_2014 layout).
BODY_INFOS, BODY_SIZE, BODY_PLACE = 0x40, 0x60, 0x30
CONVEX_VERTICES = 0x30
CMS_DATA = 0x60
TREE_DOMAIN, TREE_SECTIONS, TREE_PACKED, TREE_SHARED = 0x20, 0x50, 0x80, 0x90
SECTION_SIZE, SECTION_CODEC, SECTION_FIRST, SECTION_COUNT = 0x60, 0x30, 0x48, 0x58


def _table(raw: bytes, start: int, end: int, fmt: str) -> list:
    """A fixup table's entries (its 0xFF padding dropped)."""
    size = struct.calcsize(fmt)
    return [e for e in struct.iter_unpack(fmt, raw[start:start + (end - start) // size * size]) if e[0] != -1]


class PhysicsSystem:
    """One bhkPhysicsSystem block's packfile; `bodies()` gives each body's vertices."""

    def __init__(self, block: bytes):
        """Read the packfile's data section, its fixups and each object's class."""
        raw = block[4:]
        count = struct.unpack_from('<i', raw, 0x14)[0]
        sections = {raw[0x40 + i * 0x40:0x53 + i * 0x40].split(b'\0')[0]: struct.unpack_from('<7i', raw, 0x54 + i * 0x40)
                    for i in range(count)}
        start, local, glob, virt, *_ = sections[b'__data__']
        self.data = raw[start:start + local]
        self.local = dict(_table(raw, start + local, start + glob, '<ii'))
        self.glob = {src: dst for src, _, dst in _table(raw, start + glob, start + virt, '<iii')}
        names = sections[b'__classnames__']
        table = raw[names[0]:names[0] + names[1]]
        self.classes = {src: table[name:table.index(b'\0', name)].decode()
                        for src, _, name in _table(raw, start + virt, start + sections[b'__data__'][4], '<iii')}

    def _array(self, at: int, fmt: str, size: int) -> list:
        """An hkArray's elements at offset `at`, each `size` bytes unpacked with `fmt`."""
        n = struct.unpack_from('<i', self.data, at + 8)[0]
        base = self.local.get(at, 0)
        return [struct.unpack_from(fmt, self.data, base + i * size) for i in range(n)]

    def bodies(self) -> list:
        """[(position, orientation xyzw, local vertices as an (n, 3) array)] in body order."""
        root = next(o for o, c in self.classes.items() if c == 'hknpPhysicsSystemData')
        n = struct.unpack_from('<i', self.data, root + BODY_INFOS + 8)[0]
        base = self.local[root + BODY_INFOS]
        out = []
        for i in range(n):
            info = base + i * BODY_SIZE
            place = struct.unpack_from('<8f', self.data, info + BODY_PLACE)
            out.append((place[:3], place[4:], self.vertices(self.glob[info])))
        return out

    def vertices(self, shape: int) -> np.ndarray:
        """A shape's vertices in its own frame."""
        kind = self.classes[shape]
        if kind == 'hknpConvexPolytopeShape':
            size, offset = struct.unpack_from('<HH', self.data, shape + CONVEX_VERTICES)
            start = shape + CONVEX_VERTICES + offset
            return np.frombuffer(self.data, '<f4', size * 4, start).reshape(size, 4)[:, :3]
        if kind == 'hknpCompressedMeshShape':
            return self._mesh(self.glob[shape + CMS_DATA])
        raise ValueError(f'unhandled hknp shape {kind}')

    def _mesh(self, tree: int) -> np.ndarray:
        """A compressed mesh's packed and shared vertices."""
        lo, hi = (np.array(struct.unpack_from('<3f', self.data, tree + TREE_DOMAIN + k)) for k in (0, 16))
        packed = [v for (v,) in self._array(tree + TREE_PACKED, '<I', 4)]
        pts = []
        sections = self.local.get(tree + TREE_SECTIONS, 0)
        for i in range(struct.unpack_from('<i', self.data, tree + TREE_SECTIONS + 8)[0]):
            at = sections + i * SECTION_SIZE
            codec = struct.unpack_from('<6f', self.data, at + SECTION_CODEC)
            first = struct.unpack_from('<I', self.data, at + SECTION_FIRST)[0]
            count = self.data[at + SECTION_COUNT]
            q = np.array([(v & 0x7FF, (v >> 11) & 0x7FF, v >> 22) for v in packed[first:first + count]], float)
            pts.append(np.array(codec[:3]) + q.reshape(-1, 3) * np.array(codec[3:]))
        shared = [v for (v,) in self._array(tree + TREE_SHARED, '<Q', 8)]
        if shared:
            q = np.array([(v & 0x1FFFFF, (v >> 21) & 0x1FFFFF, v >> 42) for v in shared], float)
            pts.append(lo + q * (hi - lo) / np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF]))
        return np.vstack(pts) if pts else np.empty((0, 3))
