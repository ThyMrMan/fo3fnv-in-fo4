"""The casino menu's movie, F3NV_Casino.swf, built from our own AS3 sources (as3/) and installed with the build.

Compiled by mxmlc with our f3ui library (base.mxmlc); kept under temp/ by
the sources' hash and copied to the data folder's Interface/.

See: docs/fork/swf_framework.md#spikes
"""

from pathlib import Path

from fo4_import.base import mxmlc
from fo4_import.base.mxmlc import REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
CACHE = REPO / 'temp' / 'fo4_casino'
MOVIE = 'F3NV_Casino.swf'
#: The document class: the movie's root.
DOCUMENT = 'F3NV_Casino'


def compile_movie(out: Path, sources: Path = SOURCES) -> Path:
    """The movie of `sources`, written to `out`."""
    return mxmlc.compile_movie(out, sources, DOCUMENT)


def install(data_dir: Path) -> int:
    """Copy the movie to <data_dir>/Interface; 1 if installed, 0 if not built."""
    return int(mxmlc.install(data_dir, f'Interface/{MOVIE}', SOURCES, DOCUMENT, CACHE) is not None)
