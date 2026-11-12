"""Build an FNV interior cell (and a rectangle of a worldspace's cells) for Fallout 4: the scope's meshes converted in
worker processes into the mesh cache, then the spike's records and assets (spike.cell.build).

    py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FalloutNV.esm
        --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV --region -19 -1 -17 1
        GSDocMitchellHouse

See: docs/fork/fo4_pipeline.md#skeleton
"""

import argparse
import os
import sys
import time
from pathlib import Path

from core import build_resources
from core.heavy_lock import hold_heavy_lock
from core.process_job import create_pool_job
from core.subprocess_flags import configure_multiprocessing
from fo4_import.base.ba2_pack import drop_packed, restore_packed
from fo4_import.base.source_fault import report as fault_report, stamp as fault_stamp
from fo4_import.pipeline import build_inputs, eta, eta_inputs
from fo4_import.pipeline.build_steps import convert_scripts, source_state, stamp_path, write_stamp
from fo4_import.pipeline.converters import placed_types
from fo4_import.pipeline.export_index import export_file, export_masters, export_records, own_records
from fo4_import.pipeline.light_choice import STAMP_KEY, choose
from fo4_import.pipeline.master_space import UNCLASSIFIED
from fo4_import.pipeline.mesh_cache import warm
from fo4_import.pipeline.mod_dirs import plugin_dirs
from fo4_import.pipeline.stage_timer import LISTENERS, charged, records, report, sample
from fo4_import.spike import replacements
from tools.script.compile_papyrus import TALLY
from fo4_import.spike.cell import build, find_cell, placed_bases, world_model
from fo4_import.spike.exterior import PERSISTENT, Exterior
from fo4_import.spike.interiors import scope
from fo4_import.spike.object_lod import lod_sources

#: Record types whose scripts name forms (SCRO): scripts, and quests' stage result scripts.
SCRIPTED = ('SCPT', 'QUST')


def scope_models(export_dir: Path, cell_edid: 'str | None', exteriors: tuple) -> list:
    """The FNV mesh files of the bases placed in cell `cell_edid` (None: no named cell), the `exteriors`
    (build()'s) and the interiors their doors reach, and their LOD meshes, as build() makes them first."""
    all_refs = export_records(export_dir, 'REFR')
    outside = [r for spec in exteriors for r in Exterior(export_dir, all_refs, *spec).refs]
    start = find_cell(export_dir, cell_edid) if cell_edid else None
    used = {int(r['NAME'], 16) for r in scope(export_dir, all_refs, start, outside)[1] + outside}
    recs = [rec for sig, rec in placed_bases(export_dir, used).values()
            if sig in placed_types('record', 'pickup', 'readable')]
    recs += [r for sig in placed_types('item') for r in export_records(export_dir, sig) if int(r['FormID'], 16) in used]
    paths = {export_file(export_dir, 'meshes', world_model(r).replace('/', '\\').lower()) for r in recs if world_model(r)}
    return sorted(p for p in paths | lod_sources(export_dir, recs) if p.exists())


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
    """`names` with `all` standing for every FNV worldspace that has grid cells and `reached` for those of them
    reached_worlds() finds, each in the export's order; every name once."""
    if not {'all', 'reached'} & set(names):
        return list(names)
    cells = export_records(export_dir, 'CELL')
    grids = {c.get('ParentWRLD') for c in cells if 'XCLC.X' in c}
    reached = reached_worlds(export_dir, cells) if 'reached' in names else set()
    worlds = [w for w in export_records(export_dir, 'WRLD') if w['FormID'] in grids and w.get('EditorID')]
    out = []
    for name in names:
        add = [w['EditorID'] for w in worlds if name == 'all' or name == 'reached' and w['FormID'] in reached]
        out += [n for n in (add if name in ('all', 'reached') else [name]) if n not in out]
    return out


def reached_worlds(export_dir: Path, cells: list) -> set:
    """FNV worldspace FormIDs a load door leads into or a script (SCRO: scripts, quest stages) names a reference
    in: FFEncounterWorld is reached only by its scripts' MoveTo, TestMap01 by nothing.
    See: docs/fork/fo4_pipeline.md#reached-worlds
    """
    world_of = {c['FormID']: c.get('ParentWRLD') for c in cells}
    refs = {r['FormID']: r for sig in ('REFR', 'ACHR', 'ACRE') for r in export_records(export_dir, sig)}
    named = {v for sig in SCRIPTED for r in export_records(export_dir, sig) for k, v in r.items() if 'SCRO' in k}
    targets = {r['XTEL.Door'] for r in refs.values() if r.get('XTEL.Door')} | named
    return {world_of.get(refs[t].get('ParentCELL')) for t in targets if t in refs} - {None}


def exteriors(args: argparse.Namespace) -> tuple:
    """build()'s worlds: the first in scope_cells() and edited_cells(), the rest whole."""
    names = world_names(args.export, args.world)
    first = [(name, *scope_cells(args), edited_cells(args.export, name)) for name in names[:1]]
    return tuple(first + [(name, None, None) for name in names[1:]])


def edited_cells(export_dir: Path, world: str) -> frozenset:
    """Grid cells of worldspace `world` that a plugin with masters holds itself (its own and its overrides),
    so an add-on build places its edits outside its region too; none for a masterless plugin.
    See: docs/fork/fo4_plugin_layout.md#edited-cells
    """
    if not export_masters(str(export_dir)):
        return frozenset()
    wrld = next((w['FormID'] for w in export_records(export_dir, 'WRLD') if w.get('EditorID') == world), None)
    return frozenset((int(c['XCLC.X']), int(c['XCLC.Y'])) for c in own_records(export_dir, 'CELL')
                     if c.get('ParentWRLD') == wrld and 'XCLC.X' in c and not int(c.get('RecordFlags', 0)) & PERSISTENT)


def arguments() -> argparse.Namespace:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, type=Path, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, type=Path, help='Plugin to write')
    ap.add_argument('--data', required=True, type=Path, help='Data folder for meshes, materials and textures')
    ap.add_argument('--scripts', type=Path,
                    help='Folder for the FNV scripts, converted there first (script_convert.pipeline --target fallout4)')
    ap.add_argument('--world', nargs='*', default=[],
                    help='FNV worldspace editor IDs to build (all: every one; reached: every one a load door or script '
                         'reaches); the first takes --region or --around, the rest are built whole')
    ap.add_argument('--whole', action='store_true', help='Build the first --world whole too')
    ap.add_argument('--no-test-cell', dest='test_cell', action='store_false',
                    help="Leave out QASmoke's test chest and stand-in doors (doors leading out of the build are "
                         'counted instead)')
    ap.add_argument('--region', type=int, nargs=4, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='The rectangle of grid cells to build, corners included')
    ap.add_argument('--around', type=int, nargs=2, default=(0, 0), metavar=('X', 'Y'),
                    help='Without --region: the center cell of a square block')
    ap.add_argument('--radius', type=int, default=1, help='Without --region: cells around the center (1: 3x3)')
    ap.add_argument('--profile', help='A replacement profile laid over the defaults: a name in '
                                      'fo4_import/data/profiles, or a JSON path')
    ap.add_argument('--replacements', type=Path, help='A replacement table laid over the defaults and profile (JSON)')
    ap.add_argument('--plugin-dirs', nargs='*', default=(), help='Folders holding plugins the table names')
    ap.add_argument('--mod-sources', type=Path,
                    help="The app's settings file (fo4_import.app.settings); its mod sources are searched for "
                         'plugins after --plugin-dirs')
    ap.add_argument('--workers', type=int, default=0,
                    help='Mesh conversion processes (default: as many as the resource profile allows)')
    ap.add_argument('--resources', choices=sorted(build_resources.PROFILES),
                    help=f'How much of the machine the build may use (default: ${build_resources.ENV_VAR}, else '
                         f'{build_resources.DEFAULT}); low leaves half the cores and memory free, full uses all')
    ap.add_argument('--keep-loose', action='store_true',
                    help="Keep the loose copies of what the plugin's archives hold (a build folder fo4_deploy copies)")
    ap.add_argument('--light', action='store_true',
                    help="Build a light (ESL-flagged) plugin: the mod's opt-in, chosen before its first build and "
                         'kept after it')
    ap.add_argument('--switch-plugin-type', action='store_true',
                    help='Confirm building an already built plugin as the other type (light or full): every own '
                         'FormID moves, which breaks saves that use it')
    ap.add_argument('cell', nargs='?', help='FNV interior cell editor ID (none: a DLC with no cell of its own)')
    return ap.parse_args()


def main():
    """Build the plugin and assets once any other heavy job on the machine has finished, its stamp saying
    running, then finished or failed; the loose copies of its archives' files are back for the build and gone
    after it (but with --keep-loose).
    See: docs/fork/fo4_pipeline.md#build-stamp
    See: docs/fork/fo4_pipeline.md#main-archive
    """
    args = arguments()
    if args.resources:
        os.environ[build_resources.ENV_VAR] = args.resources
    hold_heavy_lock(' '.join(['fo4_import.pipeline.run'] + sys.argv[1:]))
    configure_multiprocessing()
    create_pool_job()
    args.choice = choose(args.out, args.light, args.switch_plugin_type)
    stop_sampling = sample()
    print(resources_line())
    print(f'loose files restored from the Main archive: {restore_packed(args.data, args.out.name)}')
    LISTENERS.append(estimate(args))
    started = time.time()
    extra = {'command': ' '.join(['fo4_import.pipeline.run'] + sys.argv[1:]), **source_state(),
             STAMP_KEY: args.choice.light}
    write_stamp(args.out, 'running', started, extra)
    build_inputs.start(build_inputs.record_dir(args.out))
    counts = {}
    try:
        counts = build_all(args, started)
        build_inputs.write(args.out, args.data, sys.argv[1:])
        if not args.keep_loose:
            print(f'loose files the archives hold, removed: {drop_packed(args.data, args.out.name)}')
    except BaseException:
        stop_sampling()
        write_stamp(args.out, 'failed', started, {**extra, **profile_stamp(counts)})
        raise
    stop_sampling()
    write_stamp(args.out, 'finished', started, {**extra, **fault_stamp(), **profile_stamp(counts)})


def resources_line() -> str:
    """'resources: <profile> (...)': the profile, the cores and memory it leaves the build's workers."""
    name, box = build_resources.profile_name(), build_resources.machine()
    budget = build_resources.memory_budget(box, name)
    memory = f', {budget / build_resources.GB:.1f} GB for workers now' if budget is not None else ''
    return f'resources: {name} ({build_resources.core_workers(box.cpus, name)} of {box.cpus} cores{memory})'


def estimate(args: argparse.Namespace) -> eta.Live:
    """Print this build's estimated time, cold and cached, from its last finished build's record, else from its
    export; the listener that prints the time left as it runs (from the cached plan when there is a record).
    See: docs/fork/fo4_build_resources.md#eta
    """
    model, bench, profile = eta.load(), eta.benchmark(), build_resources.profile_name()
    found = eta_inputs.record_build(stamp_path(args.out))
    if found:
        feats, source = eta_inputs.features(found[1], found[1].get(eta_inputs.MASTERS_COUNT, 1)), 'its last build'
    else:
        own = eta_inputs.export_counts(args.export, model['per_record'])
        feats = eta_inputs.export_features(own, bool(export_masters(str(args.export))), model)
        source = 'its export, as a whole-plugin build'
    print(f'estimate: {eta.summary(model, feats, bench, profile)} (from {source}; {eta.NOTE})')
    return eta.Live(eta.predict(model, feats, None if found else True, bench, profile)).start()


def profile_stamp(counts: dict) -> dict:
    """The stamp's machine-readable profile of this build: each stage's seconds and peak memory, the counts, the
    resource profile and the machine's cores and memory.
    See: docs/fork/fo4_build_resources.md#stage-memory
    """
    box = build_resources.machine()
    return {'stages': records(), 'counts': dict(sorted(counts.items())),
            'resources': {'profile': build_resources.profile_name(), 'cpus': box.cpus,
                          'memory_gb': round(box.total / build_resources.GB, 1)}}


def build_all(args: argparse.Namespace, started: float) -> dict:
    """The scripts converted (with --scripts), the plugin and assets built; the counts, each stage's time and every
    source fault (source_fault.report) printed; the counts."""
    if args.scripts:
        charged('script conversion', convert_scripts, args.export, args.scripts)
    worlds = exteriors(args)
    models = scope_models(args.export, args.cell, worlds)
    converted = charged('mesh cache', warm, models, args.export, args.workers)
    print(f'mesh cache: {len(models)} meshes ready in {time.time() - started:.1f}s')
    dirs = plugin_dirs(args.plugin_dirs, args.mod_sources)
    table = replacements.load(args.replacements, args.profile, dirs)
    for warning in table.warnings:
        print(f'replacements: {warning}')
    counts = build(args.export, args.out, args.data, args.cell, args.scripts, worlds, table, dirs, args.test_cell,
                   args.choice)
    counts.update({f'master FormIDs not renumbered, left as is ({key})': n for key, n in UNCLASSIFIED.items()})
    counts.update({**TALLY, 'meshes in scope': len(models), 'meshes converted': converted,
                   eta_inputs.MASTERS_COUNT: int(bool(export_masters(str(args.export))))})
    for key, count in sorted(counts.items()):
        print(f'{key}: {count}')
    print('\n'.join(report()))
    print('\n'.join(fault_report()))
    print(f'built in {time.time() - started:.1f}s')
    return counts


if __name__ == '__main__':
    main()
