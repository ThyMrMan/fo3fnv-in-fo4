"""Our dialogue menu's movie, Interface/DialogueMenu.swf, built only from our own AS3 sources (as3/).

Built as a skeleton movie with FFDec compiling the sources over it
(base.swf_skeleton), like the casino's: nothing of the game's is read. Kept
under temp/ by the sources' hash and written to a data or output folder.

See: docs/fork/fo4_dialogue_menu_plan.md#own-movie
"""

import argparse
import shutil
from pathlib import Path

from fo4_import.base import swf_skeleton
from fo4_import.base.ffdec import FFDEC, REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
MOVIE = 'Interface/DialogueMenu.swf'
#: The document class: the movie's root, which holds the menu at root.Menu_mc.
DOCUMENT = 'DialogueMenuRoot'
CACHE = REPO / 'temp' / 'fo4_dialogue_menu'
#: Where `python -m fo4_import.dialogue_menu.movie` writes the test mod by default.
OUTPUT = REPO / 'output' / 'fo4_dialogue_menu'


def compile_movie(out: Path, sources: Path = SOURCES, ffdec: Path = FFDEC) -> Path:
    """The movie of `sources`, written to `out`."""
    return swf_skeleton.compile_movie(out, sources, DOCUMENT, ffdec)


def built_movie() -> 'Path | None':
    """The movie of the current sources, cached; None if it can't be built."""
    return swf_skeleton.built_movie(SOURCES, DOCUMENT, CACHE, Path(MOVIE).name)


def install(out_dir: Path) -> 'Path | None':
    """Write our movie to <out_dir>/Interface/DialogueMenu.swf; its path, or None if it could not be built."""
    movie = built_movie()
    if movie is None:
        return None
    target = Path(out_dir) / MOVIE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(movie, target)
    return target


def main():
    """Build the movie into an output folder laid out as a mod."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=OUTPUT, help='the mod folder to write Interface/ under')
    print(install(parser.parse_args().out))


if __name__ == '__main__':
    main()
