"""The casino menu's movie, F3NV_Casino.swf, built from our own AS3 sources (as3/) and installed with the build.

No AS3 compiler ships with the project, so the movie is made in two steps:
skeleton() writes an AS3 SWF whose ABC holds an empty shell of every class
in as3/ (FFDec's script import replaces classes, it cannot add them), then
JPEXS FFDec's `-importScript` compiles the sources over the shells. Both
steps are deterministic, so the same sources give the same bytes. The built
movie is kept under temp/ by the sources' hash and copied to the data
folder's Interface/.

See: docs/fork/fo4_casino_plan.md#toolchain-found
"""

import shutil
import struct
from pathlib import Path

from asset_convert.ui.swf import Swf, Tag
from fo4_import.base.ffdec import FFDEC, REPO, import_scripts, source_digest

SOURCES = Path(__file__).resolve().parent / 'as3'
CACHE = REPO / 'temp' / 'fo4_casino'
MOVIE = 'F3NV_Casino.swf'
#: The document class (the SymbolClass of character 0): the movie's root.
DOCUMENT = 'F3NV_Casino'
#: Stage size in pixels, SWF version, frame rate (8.8 fixed).
STAGE, VERSION, FRAME_RATE = (1280, 720), 15, 30 << 8
#: SWF tag codes the skeleton writes; FileAttributes flag ActionScript 3; DoABC2's lazy-initialize flag.
FILE_ATTRIBUTES, BACKGROUND, DO_ABC2, SYMBOL_CLASS, SHOW_FRAME, END = 69, 9, 82, 76, 1, 0
AS3_FLAG, LAZY = 0x08, 1
#: ABC constant kinds: PackageNamespace, QName; trait kind Class; opcodes of the shells' bodies.
PACKAGE_NS, QNAME, TRAIT_CLASS = 0x16, 0x07, 0x04
INSTANCE_INIT = bytes((0xD0, 0x30, 0xD0, 0x49, 0x00, 0x47))
CLASS_INIT = bytes((0xD0, 0x30, 0x47))


def u30(n: int) -> bytes:
    """An ABC variable-length unsigned integer."""
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


class _Pool:
    """An ABC constant pool's strings, package namespaces and QNames, each kept once, 1-based."""

    def __init__(self):
        self.strings, self.namespaces, self.names = [], [], []

    @staticmethod
    def _index(table: list, key) -> int:
        """`key`'s 1-based index in `table`, added if new."""
        if key not in table:
            table.append(key)
        return table.index(key) + 1

    def qname(self, full: str) -> int:
        """The QName of dotted class name `full`."""
        package, _, name = full.rpartition('.')
        ns = self._index(self.namespaces, self._index(self.strings, package))
        return self._index(self.names, (ns, self._index(self.strings, name)))

    def pack(self) -> bytes:
        """The pool: no ints, uints or doubles; strings, namespaces, no namespace sets, multinames."""
        out = u30(0) + u30(0) + u30(0) + u30(len(self.strings) + 1)
        out += b''.join(u30(len(s.encode())) + s.encode() for s in self.strings)
        out += u30(len(self.namespaces) + 1) + b''.join(bytes((PACKAGE_NS,)) + u30(s) for s in self.namespaces)
        out += u30(0) + u30(len(self.names) + 1)
        return out + b''.join(bytes((QNAME,)) + u30(ns) + u30(name) for ns, name in self.names)


def _body(method: int, stack: int, scope: int, code: bytes) -> bytes:
    """A method body: one local, scope depth 0 to `scope`, no exceptions or traits."""
    return u30(method) + u30(stack) + u30(1) + u30(0) + u30(scope) + u30(len(code)) + code + u30(0) + u30(0)


def abc_shells(classes: list) -> bytes:
    """An ABC file holding an empty Object subclass per dotted name in `classes`, each in its own script."""
    pool = _Pool()
    base = pool.qname('Object')
    instances, statics, scripts, bodies = b'', b'', b'', b''
    for index, full in enumerate(classes):
        name, first = pool.qname(full), index * 3
        instances += u30(name) + u30(base) + b'\x00' + u30(0) + u30(first) + u30(0)
        statics += u30(first + 1) + u30(0)
        scripts += u30(first + 2) + u30(1) + u30(name) + bytes((TRAIT_CLASS,)) + u30(1) + u30(index)
        init = (bytes((0xD0, 0x30, 0x65, 0x00, 0x60)) + u30(base) + bytes((0x30, 0x60)) + u30(base) + b'\x58'
                + u30(index) + bytes((0x1D, 0x68)) + u30(name) + b'\x47')
        bodies += _body(first, 1, 1, INSTANCE_INIT) + _body(first + 1, 1, 1, CLASS_INIT) + _body(first + 2, 2, 2, init)
    methods = len(classes) * 3
    out = struct.pack('<HH', 16, 46) + pool.pack() + u30(methods) + b'\x00\x00\x00\x00' * methods + u30(0)
    return out + u30(len(classes)) + instances + statics + u30(len(classes)) + scripts + u30(methods) + bodies


def _rect(width: int, height: int) -> bytes:
    """A SWF RECT (0, width, 0, height) in twips, 16 bits a field."""
    bits = '10000' + ''.join(format(v * 20, '016b') for v in (0, width, 0, height))
    bits += '0' * (-len(bits) % 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def class_names(sources: Path = SOURCES) -> list:
    """The dotted class name of every .as under `sources`, document class first."""
    names = sorted('.'.join(p.relative_to(sources).with_suffix('').parts) for p in sources.rglob('*.as'))
    return sorted(names, key=lambda name: name != DOCUMENT)


def skeleton(classes: list) -> bytes:
    """An uncompressed AS3 SWF: black stage, the classes' shells, the first class as the document class."""
    tags = [Tag(FILE_ATTRIBUTES, struct.pack('<I', AS3_FLAG)), Tag(BACKGROUND, b'\x00\x00\x00'),
            Tag(DO_ABC2, struct.pack('<I', LAZY) + b'\x00' + abc_shells(classes)),
            Tag(SYMBOL_CLASS, struct.pack('<HH', 1, 0) + classes[0].encode() + b'\x00'),
            Tag(SHOW_FRAME, b''), Tag(END, b'')]
    return Swf(VERSION, _rect(*STAGE), FRAME_RATE, 1, tags).serialize(compress=False)


def source_hash(sources: Path = SOURCES) -> str:
    """A hash over every source's path and bytes, and the skeleton's version."""
    return source_digest(sources, f'{VERSION} {STAGE}'.encode())


def compile_movie(out: Path, sources: Path = SOURCES, ffdec: Path = FFDEC) -> Path:
    """The movie of `sources`, written to `out` (import_scripts)."""
    return import_scripts(skeleton(class_names(sources)), sources, out, ffdec)


def built_movie() -> 'Path | None':
    """The movie of the current sources: cached under CACHE by source_hash, compiled if FFDec is there; None
    when it is neither cached nor buildable."""
    cached = CACHE / source_hash() / MOVIE
    if not cached.is_file() and FFDEC.is_file():
        compile_movie(cached)
    return cached if cached.is_file() else None


def install(data_dir: Path) -> int:
    """Copy the movie to <data_dir>/Interface; 1 if installed, 0 if it could not be built."""
    movie = built_movie()
    if movie is None:
        return 0
    target = Path(data_dir) / 'Interface' / MOVIE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(movie, target)
    return 1
