"""Our dialogue menu's movie, Interface/DialogueMenu.swf, built only from our own AS3 sources (as3/).

Compiled by mxmlc with our f3ui library (base.mxmlc), like the casino's:
nothing of the game's is read. Kept under temp/ by the sources' hash and
written to a data or output folder.

See: docs/fork/fo4_dialogue_menu_plan.md#own-movie
"""

import argparse
from pathlib import Path

from fo4_import.base import mxmlc
from fo4_import.base.mxmlc import REPO

SOURCES = Path(__file__).resolve().parent / 'as3'
MOVIE = 'Interface/DialogueMenu.swf'
#: The document class: the movie's root, which holds the menu at root.Menu_mc.
DOCUMENT = 'DialogueMenuRoot'
CACHE = REPO / 'temp' / 'fo4_dialogue_menu'
#: Where `python -m fo4_import.dialogue_menu.movie` writes the test mod by default.
OUTPUT = REPO / 'output' / 'fo4_dialogue_menu'


def compile_movie(out: Path, sources: Path = SOURCES) -> Path:
    """The movie of `sources`, written to `out`."""
    return mxmlc.compile_movie(out, sources, DOCUMENT)


def install(out_dir: Path) -> 'Path | None':
    """Our movie written to <out_dir>/MOVIE; its path, None if not built."""
    return mxmlc.install(out_dir, MOVIE, SOURCES, DOCUMENT, CACHE)


def main():
    """Build the movie into an output folder laid out as a mod."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=OUTPUT, help='the mod folder to write Interface/ under')
    print(install(parser.parse_args().out))


if __name__ == '__main__':
    main()
