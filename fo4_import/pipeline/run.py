"""Build an FNV interior cell (and a block of a worldspace) for Fallout 4: the scope's meshes converted in
worker processes into the mesh cache, then the spike's records and assets (spike.cell.build).

    py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FNVCellSpike.esp
        --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV --around -18 0
        --radius 1 GSDocMitchellHouse

See: docs/fork/fo4_pipeline.md#skeleton
"""

import argparse
import time
from pathlib import Path

from core.process_job import create_pool_job
from core.subprocess_flags import configure_multiprocessing
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.mesh_cache import warm
from fo4_import.spike import replacements
from fo4_import.spike.cell import ITEM_BASES, build, find_cell, placed_bases, world_model
from fo4_import.spike.exterior import Exterior

#: Placed base types whose mesh is not convert()'s (generated trees; sound markers have none).
NOT_CONVERTED = ('TREE', 'SOUN')


def scope_models(export_dir: Path, cell_edid: str, exterior: 'tuple | None') -> list:
    """The FNV mesh files of the bases placed in cell `cell_edid` and the `exterior` block, as build() makes
    them first (convert() with its defaults)."""
    all_refs = export_records(export_dir, 'REFR')
    cell = find_cell(export_dir, cell_edid)
    refs = [r for r in all_refs if r.get('ParentCELL') == cell['FormID']]
    refs += Exterior(export_dir, all_refs, *exterior).refs if exterior else []
    used = {int(r['NAME'], 16) for r in refs}
    recs = [rec for sig, rec in placed_bases(export_dir, used).values() if sig not in NOT_CONVERTED]
    recs += [r for sig in ITEM_BASES for r in export_records(export_dir, sig) if int(r['FormID'], 16) in used]
    paths = {export_dir / 'meshes' / world_model(r).replace('/', '\\').lower() for r in recs if world_model(r)}
    return sorted(p for p in paths if p.exists())


def arguments() -> argparse.Namespace:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, type=Path, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, type=Path, help='Plugin to write')
    ap.add_argument('--data', required=True, type=Path, help='Data folder for meshes, materials and textures')
    ap.add_argument('--scripts', type=Path, help='Converted FNV scripts (script_convert.pipeline --target fallout4)')
    ap.add_argument('--world', help='FNV worldspace editor ID to add a block of (with --around)')
    ap.add_argument('--around', type=int, nargs=2, default=(0, 0), metavar=('X', 'Y'), help='The block\'s center cell')
    ap.add_argument('--radius', type=int, default=1, help='Cells around the center (1: a 3x3 block)')
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
    exterior = (args.world, tuple(args.around), args.radius) if args.world else None
    started = time.time()
    models = scope_models(args.export, args.cell, exterior)
    warm(models, args.export, args.workers)
    print(f'mesh cache: {len(models)} meshes ready in {time.time() - started:.1f}s')
    counts = build(args.export, args.out, args.data, args.cell, args.scripts, exterior,
                   replacements.load(args.replacements), tuple(args.plugin_dirs))
    for key, count in sorted(counts.items()):
        print(f'{key}: {count}')
    print(f'built in {time.time() - started:.1f}s')


if __name__ == '__main__':
    main()
