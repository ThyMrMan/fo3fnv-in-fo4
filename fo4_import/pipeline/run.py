"""Build an FNV interior cell (and a rectangle of a worldspace's cells) for Fallout 4: the scope's meshes converted in
worker processes into the mesh cache, then the spike's records and assets (spike.cell.build).

    py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FNVCellSpike.esp
        --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV --region -19 -1 -17 1
        GSDocMitchellHouse

See: docs/fork/fo4_pipeline.md#skeleton
"""

import argparse
import time
from pathlib import Path

from core.process_job import create_pool_job
from core.subprocess_flags import configure_multiprocessing
from fo4_import.pipeline.converters import placed_types
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.mesh_cache import warm
from fo4_import.spike import replacements
from fo4_import.spike.cell import build, find_cell, placed_bases, world_model
from fo4_import.spike.exterior import Exterior
from fo4_import.spike.interiors import scope


def scope_models(export_dir: Path, cell_edid: str, exteriors: tuple) -> list:
    """The FNV mesh files of the bases placed in cell `cell_edid`, the `exteriors` (build()'s) and the interiors
    their doors reach, as build() makes them first (convert() with its defaults)."""
    all_refs = export_records(export_dir, 'REFR')
    outside = [r for spec in exteriors for r in Exterior(export_dir, all_refs, *spec).refs]
    used = {int(r['NAME'], 16) for r in scope(export_dir, all_refs, find_cell(export_dir, cell_edid), outside)[1]
            + outside}
    recs = [rec for sig, rec in placed_bases(export_dir, used).values()
            if sig in placed_types('record', 'pickup', 'readable')]
    recs += [r for sig in placed_types('item') for r in export_records(export_dir, sig) if int(r['FormID'], 16) in used]
    paths = {export_dir / 'meshes' / world_model(r).replace('/', '\\').lower() for r in recs if world_model(r)}
    return sorted(p for p in paths if p.exists())


def scope_cells(args: argparse.Namespace) -> tuple:
    """(low (x, y), high (x, y)) grid corners of the first worldspace's cells to build: --region, else --around
    and --radius; (None, None) with --whole."""
    if args.whole:
        return None, None
    if args.region:
        x0, y0, x1, y1 = args.region
        return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))
    (x, y), r = args.around, args.radius
    return (x - r, y - r), (x + r, y + r)


def world_names(export_dir: Path, names: list) -> list:
    """`names` with `all` standing for every FNV worldspace that has grid cells, in the export's order."""
    if 'all' not in names:
        return list(names)
    grids = {c.get('ParentWRLD') for c in export_records(export_dir, 'CELL') if 'XCLC.X' in c}
    return [w['EditorID'] for w in export_records(export_dir, 'WRLD') if w['FormID'] in grids and w.get('EditorID')]


def exteriors(args: argparse.Namespace) -> tuple:
    """build()'s worldspaces: the first in scope_cells(), the others whole."""
    names = world_names(args.export, args.world)
    return tuple([(name, *scope_cells(args)) for name in names[:1]] + [(name, None, None) for name in names[1:]])


def arguments() -> argparse.Namespace:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, type=Path, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, type=Path, help='Plugin to write')
    ap.add_argument('--data', required=True, type=Path, help='Data folder for meshes, materials and textures')
    ap.add_argument('--scripts', type=Path, help='Converted FNV scripts (script_convert.pipeline --target fallout4)')
    ap.add_argument('--world', nargs='*', default=[],
                    help='FNV worldspace editor IDs to build (all: every one); the first takes --region or --around, '
                         'the rest are built whole')
    ap.add_argument('--whole', action='store_true', help='Build the first --world whole too')
    ap.add_argument('--no-test-cell', dest='test_cell', action='store_false',
                    help="Leave out QASmoke's test chest and stand-in doors (doors leading out of the build are "
                         'counted instead)')
    ap.add_argument('--region', type=int, nargs=4, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='The rectangle of grid cells to build, corners included')
    ap.add_argument('--around', type=int, nargs=2, default=(0, 0), metavar=('X', 'Y'),
                    help='Without --region: the center cell of a square block')
    ap.add_argument('--radius', type=int, default=1, help='Without --region: cells around the center (1: 3x3)')
    ap.add_argument('--replacements', type=Path, help='A replacement table laid over the defaults (JSON)')
    ap.add_argument('--plugin-dirs', nargs='*', default=(), help='Folders holding plugins the table names')
    ap.add_argument('--workers', type=int, default=0, help='Mesh conversion processes (default: all CPUs but one)')
    ap.add_argument('cell', help='FNV interior cell editor ID')
    return ap.parse_args()


def main():
    """Build the plugin and assets; print the counts and each stage's time."""
    args = arguments()
    configure_multiprocessing()
    create_pool_job()
    worlds = exteriors(args)
    started = time.time()
    models = scope_models(args.export, args.cell, worlds)
    warm(models, args.export, args.workers)
    print(f'mesh cache: {len(models)} meshes ready in {time.time() - started:.1f}s')
    counts = build(args.export, args.out, args.data, args.cell, args.scripts, worlds,
                   replacements.load(args.replacements), tuple(args.plugin_dirs), args.test_cell)
    for key, count in sorted(counts.items()):
        print(f'{key}: {count}')
    print(f'built in {time.time() - started:.1f}s')


if __name__ == '__main__':
    main()
