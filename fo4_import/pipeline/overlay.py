"""Build an asset overlay: a replacer's loose textures and meshes (no plugin) converted for the files built plugins
already ship, into a folder of its own with an empty ESL that loads its archives after theirs.

    py -3.14 -m fo4_import.pipeline.overlay --out "<mods>/F3NV - NVTUP" --name "F3NV - NVTUP"
        --built "<mods>/F3NV - Fallout New Vegas/FalloutNV.esm" --mods "<mods>/FNV Texture Upscale Project (NVTUP) 2.0"

See: docs/fork/fo4_plugin_layout.md#asset-overlays
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from core.heavy_lock import hold_heavy_lock
from core.process_job import create_pool_job
from core.subprocess_flags import configure_multiprocessing
from fo4_import.base.ba2_pack import pack_main, pack_record, pack_textures, write_later
from fo4_import.base.source_fault import FAULTS, report as fault_report, stamp as fault_stamp, without_fault
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.nif.convert_static import smoothness, spec_glossiness, texture_source
from fo4_import.pipeline.build_steps import write_stamp
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.elric_cache import finish
from fo4_import.pipeline.export_index import OVERLAY_ENV, export_file
from fo4_import.pipeline.mesh_cache import warm
from fo4_import.pipeline.stale_files import list_path
from fo4_import.pipeline.work_cache import spec_map
from fo4_import.spike.statics import copy_texture, stage_derived, write_assets

#: A shipped specular map derived from an FNV normal map (spec_map_path): its path before `_s`.
SPEC = re.compile(r'^textures/fnv/(.+)_s(_g[^/]*)?\.dds$')
#: The mesh names a build ships a model under that the overlay converts: (suffix, load door).
VARIANTS = (('', False), ('load', True))


def shipped(plugin: Path) -> set:
    """Lowercase '/'-separated paths `plugin`'s folder ships: its files list and its Textures archive record."""
    folder = plugin.parent
    listed = list_path(plugin).read_text(encoding='utf-8').lower().replace('\\', '/')
    record = pack_record(folder / f'{plugin.stem} - Textures.ba2')
    packed = json.loads(record.read_text(encoding='utf-8'))['manifest'] if record.is_file() else {}
    loose = folder / 'Textures'
    names = [p.relative_to(loose).as_posix().lower() for p in loose.rglob('*.dds')] if loose.is_dir() else []
    return set(listed.splitlines()) | {f'textures/{name}' for name in (*packed, *names)}


def mod_files(mods: list, folder: str, suffix: str) -> set:
    """Lowercase '/'-separated paths under `folder` of the `mods`' files ending in `suffix`."""
    out = set()
    for mod in mods:
        for root in (p for p in Path(mod).iterdir() if p.is_dir() and p.name.lower() == folder):
            out |= {p.relative_to(root).as_posix().lower() for p in root.rglob('*') if p.name.lower().endswith(suffix)}
    return out


def textures(export_dir: Path, data_dir: Path, ships: set, rels: set, workers: int) -> dict:
    """Copy each of texture paths `rels` that `ships` holds (premultiplied ones mended, over `workers` processes),
    and derive again the shipped specular maps of each normal map among them; counts.
    See: docs/fork/fo4_plugin_layout.md#premultiplied-replacers
    """
    specs = {}
    for path in ships:
        match = SPEC.match(path)
        if match:
            specs.setdefault(f'{match[1]}_n.dds', []).append(path)
    copied = derived = 0
    later = []
    for rel in sorted(rels):
        source = texture_source(rel)
        if f'textures/fnv/{rel}' in ships:
            copied += copy_texture(export_dir, data_dir, source, later)
        for spec in specs.get(rel, ()):
            normal = export_file(export_dir, source.replace('\\', '/'))
            target = spec[len('textures/'):].replace('/', '\\')
            derived += stage_derived(data_dir, target, spec_map, (normal,), smoothness(spec_glossiness(target)))
    write_later(later, workers)
    return {'textures copied': copied, 'specular maps derived': derived}


def meshes(export_dir: Path, data_dir: Path, ships: set, rels: set, workers: int) -> list:
    """Convert each of mesh paths `rels` that `ships` holds under a VARIANTS name, with its materials and
    textures; the written meshes' paths. One with a source fault is left out, counted."""
    todo = [(rel, suffix, load) for rel in sorted(rels) for suffix, load in VARIANTS
            if f'meshes/fnv/{rel[:-4]}{suffix}.nif' in ships]
    warm(sorted({export_file(export_dir, 'meshes', rel) for rel, _, _ in todo}), export_dir, workers)
    made = (without_fault(write_assets, export_dir, rel, data_dir, load=load) for rel, _, load in todo)
    return [data_dir / 'Meshes' / files[0] for files in made if files]


def overlay(args: argparse.Namespace) -> dict:
    """Convert the `args.mods` files every `args.built` plugin ships into `args.out`, collision added, and pack
    them behind an empty ESL; counts."""
    textures_in, meshes_in = mod_files(args.mods, 'textures', '.dds'), mod_files(args.mods, 'meshes', '.nif')
    counts, made = {'mod textures': len(textures_in), 'mod meshes': len(meshes_in)}, []
    for plugin in args.built:
        export_dir, ships = args.export_root / plugin.name, shipped(plugin)
        for key, n in textures(export_dir, args.out, ships, textures_in, args.workers).items():
            counts[f'{key} ({plugin.name})'] = n
        built = meshes(export_dir, args.out, ships, meshes_in, args.workers)
        counts[f'meshes converted ({plugin.name})'] = len(built)
        made += built
    counts['meshes left without collision'] = len(finish(made))
    counts['source faults'] = len(FAULTS)
    esl = args.out / f'{args.name}.esl'
    FO4PluginWriter(masters=[p.name for p in args.built], is_esm=False, is_esl=True,
                    description=f'F3NV asset overlay: {args.name}').write(str(esl))
    counts['textures packed'] = pack_textures(args.out, esl.name)
    counts['files packed into the Main and voices archives'] = pack_main(args.out, esl.name)
    return counts


def arguments() -> argparse.Namespace:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True, type=Path, help='The overlay mod folder to write')
    ap.add_argument('--name', required=True, help='The overlay ESL and archive name')
    ap.add_argument('--built', required=True, nargs='+', type=Path, help='Built FO4 plugins the overlay replaces in')
    ap.add_argument('--mods', required=True, nargs='+', type=Path,
                    help='Replacer mod folders, in load order (a later one wins)')
    ap.add_argument('--export-root', type=Path, default=ROOT / 'export', help='Folder of the FNV exports')
    ap.add_argument('--workers', type=int, default=0, help='Mesh conversion processes (default: all CPUs but one)')
    return ap.parse_args()


def main():
    """Build the overlay once any other heavy job has finished, its stamp saying running, then finished or failed."""
    args = arguments()
    command = ' '.join(['fo4_import.pipeline.overlay'] + sys.argv[1:])
    hold_heavy_lock(command)
    configure_multiprocessing()
    create_pool_job()
    os.environ[OVERLAY_ENV] = os.pathsep.join(str(m) for m in reversed(args.mods))
    started, stamp = time.time(), args.out / f'{args.name}.esl'
    write_stamp(stamp, 'running', started, {'command': command})
    try:
        counts = overlay(args)
    except BaseException:
        write_stamp(stamp, 'failed', started, {'command': command})
        raise
    write_stamp(stamp, 'finished', started, {'command': command, **fault_stamp()})
    for key, n in sorted(counts.items()):
        print(f'{key}: {n}')
    print('\n'.join(fault_report()))
    print(f'built in {time.time() - started:.1f}s')


if __name__ == '__main__':
    main()
