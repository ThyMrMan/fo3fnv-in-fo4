"""Count FO3/FNV exports' records by type and show each type's Fallout 4 route (fo4_import.record_routes).

Prints a markdown table (type, count per export, FO4 target, kind, how the
pipeline makes a placed base of it: pipeline.converters), then
every problem: a type with no route, or a target Fallout 4 does not have
(checked against a Fallout4.esm dump's type files). Exits 1 on a problem.

    python -m tools.esm.fo4_record_census export/FalloutNV.esm export/Fallout3.esm

See: docs/fork/fo4_pipeline.md#census
"""

import argparse
import sys
from pathlib import Path

from fo4_import.pipeline.converters import PLACED, STATIC_STAND_INS
from fo4_import.record_routes import ROUTES

FO4_DUMP = Path(__file__).resolve().parents[2] / 'references' / 'Fallout4.esm'


def counts(export_dir: Path) -> dict:
    """{signature: records} of an export folder (each `<SIG>.txt`'s record markers)."""
    return {path.stem: path.read_bytes().count(b'---RECORD_BEGIN---') for path in sorted(export_dir.glob('*.txt'))
            if len(path.stem) == 4 and path.stem.isupper()}


def problems(types: set, fo4_types: set) -> list:
    """Problems: types with no route, and routes to a type Fallout 4 lacks."""
    out = [f'{sig}: no route' for sig in sorted(types - set(ROUTES))]
    return out + [f'{sig}: target {target} is not a Fallout 4 type' for sig, (target, _) in sorted(ROUTES.items())
                  if target and target not in fo4_types]


def placed(sig: str) -> str:
    """`sig`'s placed-base converter, 'static stand-in', or ''."""
    return 'static stand-in' if sig in STATIC_STAND_INS else PLACED.get(sig, '')


def table(names: list, per_export: list) -> str:
    """The markdown census table over the exports `names` with their counts()."""
    types = sorted(set().union(*per_export))
    lines = ['| Type | ' + ' | '.join(names) + ' | FO4 | Kind | Placed |', '|---' * (len(names) + 4) + '|']
    for sig in types:
        target, kind = ROUTES.get(sig, ('?', '?'))
        lines.append(f'| {sig} | ' + ' | '.join(f'{c.get(sig, 0):,}' for c in per_export)
                     + f' | {target} | {kind} | {placed(sig)} |')
    return '\n'.join(lines)


def main() -> int:
    """Print the census of the exports named on the command line; 1 if it found a problem."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('exports', nargs='+', type=Path, help='Export folders (export/FalloutNV.esm ...)')
    ap.add_argument('--fo4', type=Path, default=FO4_DUMP, help='Fallout4.esm dump (one <SIG>.txt per type)')
    args = ap.parse_args()
    per_export = [counts(e) for e in args.exports]
    print(table([e.name for e in args.exports], per_export))
    found = problems(set().union(*per_export), {p.stem for p in args.fo4.glob('*.txt')})
    print('\n'.join(['', *found]) if found else '\nEvery type routed; every target is a Fallout 4 type.')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
