"""Where Fallout 4 and its Creation Kit tools are installed (detected by core.game_dirs, else Steam's default
Windows folder), and the source plugin a build reads fields its export lacks from (FalloutNV.esm until use_source
names another: Fallout3.esm, a DLC). A source with a master (an FNV DLC on FalloutNV.esm) is read with it:
source_walk() yields the source's records, then the master's it does not override.

See: docs/fork/fo4_gui.md#cross-platform
"""

import functools
import struct
from pathlib import Path

from core.game_dirs import find
from fo4_import.pipeline.master_plugin import renumbered
from fo4_import.pipeline.master_space import identity
from tes5_import.base.tes5_reader import subrecords, walk

#: Steam's default Windows library, used when detection finds nothing.
STEAM_COMMON = Path(r'C:\Program Files (x86)\Steam\steamapps\common')
FALLOUT4_DIR = find('fallout4') or STEAM_COMMON / 'Fallout 4'
FALLOUT4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
FALLOUTNV_ESM = (find('falloutnv') or STEAM_COMMON / 'Fallout New Vegas') / 'Data' / 'FalloutNV.esm'
#: A plugin file's header: its record header size.
HEADER = 24
#: The plugin the running build converts (use_source).
_SOURCE = {'plugin': FALLOUTNV_ESM, 'masters': ()}


def use_source(plugin: Path, masters: tuple = ()) -> None:
    """Read `plugin` as the source; `masters`: (file, FormID map, game), newest first."""
    _SOURCE['plugin'], _SOURCE['masters'] = Path(plugin), tuple((Path(f), tuple(m), g) for f, m, g in masters)


def source_esm() -> bytes:
    """The bytes of the plugin the build converts (use_source), read once a run."""
    return _read(_SOURCE['plugin'])


@functools.cache
def _read(path: Path) -> bytes:
    """The bytes of the file at `path`, read once."""
    return path.read_bytes()


def masters_of(data: bytes) -> list:
    """A plugin's master file names, from its file header."""
    size = struct.unpack_from('<I', data, 4)[0]
    return [body.rstrip(b'\0').decode('cp1252') for sig, body in subrecords(data[HEADER:HEADER + size])
            if sig == b'MAST']


def file_masters(path: Path) -> list:
    """A plugin file's master names, read from its header record only."""
    with open(path, 'rb') as f:
        head = f.read(HEADER)
        return masters_of(head + f.read(struct.unpack_from('<I', head, 4)[0]))


def source_stack() -> list:
    """The bytes of the source plugin, then of use_source's masters newest first, each in the source's FormID
    numbering (master_plugin). Without them, the one master beside it, which must have none of its own.
    See: docs/fork/fo4_plugin_layout.md#multi-master
    """
    plugin = _SOURCE['plugin']
    if _SOURCE['masters']:
        return [_read(plugin), *(_master(*source) for source in _SOURCE['masters'])]
    names = masters_of(_read(plugin))
    stack = [_read(plugin)] + [_read(plugin.parent / n) for n in names]
    if len(names) > 1 or any(masters_of(raw) for raw in stack[1:]):
        raise SystemExit(f'{plugin.name}: a source with several masters needs them named (use_source)')
    return stack


@functools.cache
def _master(path: Path, mapping: tuple, game: str) -> bytes:
    """Master file `path`'s bytes through FormID map `mapping`."""
    raw = _read(path)
    return raw if not mapping or identity(mapping) else renumbered(raw, mapping, game)


def plugin_walk(plugin: 'bytes | None', *sigs: bytes, bodies=None):
    """walk() of plugin bytes `plugin`; of the source stack (source_walk) when None."""
    return walk(plugin, *sigs, bodies=bodies) if plugin is not None else source_walk(*sigs, bodies=bodies)


def source_walk(*sigs: bytes, bodies=None):
    """walk() over the source stack (source_stack): each FormID once, the source's version first."""
    seen = set()
    for raw in source_stack():
        for rec, stack in walk(raw, *sigs, bodies=bodies):
            if rec.form_id not in seen:
                seen.add(rec.form_id)
                yield rec, stack
