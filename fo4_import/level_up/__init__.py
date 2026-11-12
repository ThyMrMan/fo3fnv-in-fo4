"""Our level-up menu's movie, Interface/F3NV_LevelUp.swf, built from as3/ with mxmlc and our f3ui library.

F3NV_LevelUp.psc registers it with F4SE and opens it in place of LevelUpMenu
(F3NV_CharacterRules); the data it shows comes from the build's tables on that
script (fo4_import/spike/level_up.py). Cached under temp/ by the sources' hash;
the masterless build installs it.

See: docs/fork/fo4_level_up_plan.md#menu
"""

from pathlib import Path

from fo4_import.base import mxmlc
from fo4_import.base.mxmlc import REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
CACHE = REPO / 'temp' / 'fo4_level_up'
#: The movie's path in a data folder: the menu name F3NV_LevelUp.psc registers, under Interface.
MOVIE = 'Interface/F3NV_LevelUp.swf'
#: The document class: the movie's root.
DOCUMENT = 'F3NV_LevelUp'


def compile_movie(out: Path, sources: Path = SOURCES) -> Path:
    """The movie of `sources`, written to `out`."""
    return mxmlc.compile_movie(out, sources, DOCUMENT)


def install(data_dir: Path) -> int:
    """Copy the movie to <data_dir>/Interface; 1 if installed, 0 if not built."""
    return int(mxmlc.install(data_dir, MOVIE, SOURCES, DOCUMENT, CACHE) is not None)
