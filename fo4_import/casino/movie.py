"""The casino menu's movie, F3NV_Casino.swf, built from our own AS3 sources (as3/) and installed with the build.

Built as a skeleton movie with FFDec compiling the sources over it
(base.swf_skeleton); kept under temp/ by the sources' hash and copied to the
data folder's Interface/.

See: docs/fork/fo4_casino_plan.md#toolchain-found
"""

import shutil
from pathlib import Path

from fo4_import.base import swf_skeleton
from fo4_import.base.ffdec import FFDEC, REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
CACHE = REPO / 'temp' / 'fo4_casino'
MOVIE = 'F3NV_Casino.swf'
#: The document class (the SymbolClass of character 0): the movie's root.
DOCUMENT = 'F3NV_Casino'


def class_names(sources: Path = SOURCES) -> list:
    """The dotted class name of every .as under `sources`, document class first."""
    return swf_skeleton.class_names(sources, DOCUMENT)


def source_hash(sources: Path = SOURCES) -> str:
    """A hash over every source's path and bytes, and the skeleton's version."""
    return swf_skeleton.source_hash(sources)


def compile_movie(out: Path, sources: Path = SOURCES, ffdec: Path = FFDEC) -> Path:
    """The movie of `sources`, written to `out`."""
    return swf_skeleton.compile_movie(out, sources, DOCUMENT, ffdec)


def install(data_dir: Path) -> int:
    """Copy the movie to <data_dir>/Interface; 1 if installed, 0 if it could not be built."""
    movie = swf_skeleton.built_movie(SOURCES, DOCUMENT, CACHE, MOVIE)
    if movie is None:
        return 0
    target = Path(data_dir) / 'Interface' / MOVIE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(movie, target)
    return 1
