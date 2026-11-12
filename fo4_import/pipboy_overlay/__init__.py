"""Our movie inside the Pip-Boy, Interface/F3NV_Pipboy.swf, built from as3/ with mxmlc and our f3ui library.

F3NV.dll loads it into the open Pip-Boy menu with a Loader (pipboy.cpp
LoadOverlay); no Pip-Boy movie of the game's is shipped or read. Cached
under temp/ by the sources' hash; the masterless build installs it.

See: docs/fork/swf_framework.md#pipboy
"""

import shutil
from pathlib import Path

from fo4_import.base import mxmlc
from fo4_import.base.mxmlc import REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
CACHE = REPO / 'temp' / 'fo4_pipboy_overlay'
#: The movie's path in a data folder: the name pipboy.cpp's OVERLAY loads, under Interface.
MOVIE = 'Interface/F3NV_Pipboy.swf'
#: The document class: the movie's root.
DOCUMENT = 'F3NV_Pipboy'


def compile_movie(out: Path, sources: Path = SOURCES) -> Path:
    """The movie of `sources`, written to `out`."""
    return mxmlc.compile_movie(out, sources, DOCUMENT)


def install(data_dir: Path) -> int:
    """Copy the movie to <data_dir>/Interface; 1 if installed, 0 if it could not be built."""
    movie = mxmlc.built_movie(SOURCES, DOCUMENT, CACHE, Path(MOVIE).name)
    if movie is None:
        return 0
    target = Path(data_dir) / MOVIE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(movie, target)
    return 1
