"""Our dialogue menu's movie: the game's own Interface/DialogueMenu.swf with its DialogueMenu class compiled from
as3/ (F3NV.dll's option list).

The game's movie is read from the user's `Fallout4 - Interface.ba2` at
install, so nothing of Bethesda's is committed or shipped; FFDec compiles
our class over the game's (base.ffdec). The result is cached under temp/ by
the game movie's and the sources' hash, and written only to an output folder.

See: docs/fork/fo4_dialogue_menu_plan.md#test-build
"""

import argparse
import hashlib
import shutil
from pathlib import Path

from fo4_import.base.ba2 import Archive
from fo4_import.base.ffdec import FFDEC, REPO, import_scripts, source_digest
from fo4_import.base.install import FALLOUT4_DIR

SOURCES = Path(__file__).resolve().parent / 'as3'
MOVIE = 'Interface/DialogueMenu.swf'
ARCHIVE = 'Fallout4 - Interface.ba2'
CACHE = REPO / 'temp' / 'fo4_dialogue_menu'
#: Where `python -m fo4_import.dialogue_menu.movie` writes the test mod by default.
OUTPUT = REPO / 'output' / 'fo4_dialogue_menu'


def game_movie(game_data: Path = FALLOUT4_DIR / 'Data') -> bytes:
    """The game's DialogueMenu.swf, from its Interface archive in `game_data`."""
    return Archive(Path(game_data) / ARCHIVE).read(MOVIE)


def built_movie(game_data: Path = FALLOUT4_DIR / 'Data', ffdec: Path = FFDEC) -> Path:
    """Our movie for `game_data`'s game movie: cached by both hashes, compiled with FFDec when not cached."""
    vanilla = game_movie(game_data)
    cached = CACHE / source_digest(SOURCES, hashlib.sha1(vanilla).digest()) / 'DialogueMenu.swf'
    if not cached.is_file():
        import_scripts(vanilla, SOURCES, cached, ffdec)
    return cached


def install(out_dir: Path, game_data: Path = FALLOUT4_DIR / 'Data') -> Path:
    """Write our movie to <out_dir>/Interface/DialogueMenu.swf; its path."""
    target = Path(out_dir) / MOVIE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built_movie(game_data), target)
    return target


def main():
    """Build the movie into an output folder laid out as a mod."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--game-data', type=Path, default=FALLOUT4_DIR / 'Data', help="Fallout 4's Data folder")
    parser.add_argument('--out', type=Path, default=OUTPUT, help='the mod folder to write Interface/ under')
    args = parser.parse_args()
    print(install(args.out, args.game_data))


if __name__ == '__main__':
    main()
