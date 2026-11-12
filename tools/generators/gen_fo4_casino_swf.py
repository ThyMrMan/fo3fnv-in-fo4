"""Build the Fallout 4 casino menu's movie (F3NV_Casino.swf) from fo4_import/casino/as3 with mxmlc.

The build installs it by itself (fo4_import.casino.movie.install); this
writes it anywhere, for a look in FFDec or to ship with the app.

    python -m tools.generators.gen_fo4_casino_swf --out temp/F3NV_Casino.swf

See: docs/fork/swf_framework.md#spikes
"""

import argparse
from pathlib import Path

from fo4_import.base import mxmlc
from fo4_import.casino import movie


def main() -> None:
    """Compile the movie to --out and print its size and source hash."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=Path(movie.MOVIE), help='where to write the movie')
    parser.add_argument('--sources', type=Path, default=movie.SOURCES, help='folder of .as sources')
    args = parser.parse_args()
    out = movie.compile_movie(args.out, args.sources)
    print(f'{out}: {out.stat().st_size} bytes, sources {mxmlc.source_hash(args.sources)}')


if __name__ == '__main__':
    main()
