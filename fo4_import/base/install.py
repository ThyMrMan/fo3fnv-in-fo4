"""Where Fallout 4 and its Creation Kit tools are installed (detected by core.game_dirs, else Steam's default
Windows folder), and the source plugin a build reads fields its export lacks from (FalloutNV.esm until use_source
names another: Fallout3.esm, a DLC).

See: docs/fork/fo4_gui.md#cross-platform
"""

import functools
from pathlib import Path

from core.game_dirs import find

#: Steam's default Windows library, used when detection finds nothing.
STEAM_COMMON = Path(r'C:\Program Files (x86)\Steam\steamapps\common')
FALLOUT4_DIR = find('fallout4') or STEAM_COMMON / 'Fallout 4'
FALLOUT4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
FALLOUTNV_ESM = (find('falloutnv') or STEAM_COMMON / 'Fallout New Vegas') / 'Data' / 'FalloutNV.esm'
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
