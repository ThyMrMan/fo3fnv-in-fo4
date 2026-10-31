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
from tes5_import.base.tes5_reader import subrecords, walk

#: Steam's default Windows library, used when detection finds nothing.
STEAM_COMMON = Path(r'C:\Program Files (x86)\Steam\steamapps\common')
FALLOUT4_DIR = find('fallout4') or STEAM_COMMON / 'Fallout 4'
FALLOUT4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
FALLOUTNV_ESM = (find('falloutnv') or STEAM_COMMON / 'Fallout New Vegas') / 'Data' / 'FalloutNV.esm'
#: A plugin file's header: its record header size.
HEADER = 24
#: The plugin the running build converts (use_source).
_SOURCE = {'plugin': FALLOUTNV_ESM}


def use_source(plugin: Path) -> None:
    """Make `plugin` (the build's source plugin) the one source_esm() reads."""
    _SOURCE['plugin'] = Path(plugin)


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
    """The bytes of the source plugin, then of its master (found beside it): one master with none of its own,
    so its FormIDs already read as the source's; anything deeper raises.
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    plugin = _SOURCE['plugin']
    names = masters_of(_read(plugin))
    if len(names) > 1:
        raise SystemExit(f'{plugin.name}: sources with more than one master ({names}) are not supported yet')
    stack = [_read(plugin)] + [_read(plugin.parent / name) for name in names]
    if any(masters_of(raw) for raw in stack[1:]):
        raise SystemExit(f'{plugin.name}: a master with masters of its own is not supported yet')
    return stack


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
