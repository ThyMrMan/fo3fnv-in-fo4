"""The faces stage: FaceGen for a plugin's NPCs, ours (facegen_own), with FNV's faces carried onto it.

    py -3.14 -m fo4_import.spike.facegen --export <FalloutNV.esm export> --data <mod folder> FalloutNV.esm

Writes a FaceGeom NIF and face textures at vanilla's formats for each NPC
the Creation Kit would export (facegeom.exported), in a worker pool; an NPC
that fails is listed with its error and left without FaceGen. Each fitted
NPC's sliders are refitted to that export's miss (facegen_skin.refine) and
its head written again, then each fitted NPC gets FNV's skin, its rear head
texture and skin tone (facegen_skin_cache.skin). Last, the FaceGeom NIFs go
into the plugin's Main archive and the face textures into its Textures
archive, as vanilla ships both, and the loose copies leave the mod folder
(the build's own come back first, so the Main archive keeps them).

See: docs/fork/fo4_facegen_plan.md#own-stage
"""

import argparse
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

from core.subprocess_flags import configure_multiprocessing
from fo4_import.base.ba2_pack import (archived, drop_packed, pack_main, pack_textures, restore_packed, stashed,
                                      staging_root)
from fo4_import.base.install import FALLOUT4_ESM, masters_of
from fo4_import.classic_look import CLASSIC_FOLDER
from fo4_import.face import calibration, facegeom
from fo4_import.face.tint import skin_tone_layers
from fo4_import.nif import file as nif_file
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.stage_timer import charged, report, sample
from fo4_import.spike import facegen_inherit, facegen_own, facegen_skin, facegen_skin_cache
from fo4_import.spike.imagespace import LUT_FOLDER
from tes5_import.base.tes5_reader import subrecords, walk

#: Folders (under Meshes / Textures) a plugin's FaceGen goes in.
FACEGEN_DIRS = (Path('Meshes/Actors/Character/FaceGenData/FaceGeom'),
                Path('Textures/Actors/Character/FaceCustomization'))
#: The faces stamp beside a plugin's build stamp: which build of the plugin this stage last ran on, and how.
FACES_SUFFIX = '.faces.json'
#: The plugin as its build wrote it, kept beside the faces stamp, and the file naming which build that copy is.
BUILT_SUFFIX, BUILT_OF_SUFFIX = '.built', '.built.txt'
#: The argument running only the overrides step (build_plan, when only a master's faces ran since).
OVERRIDES_ONLY = '--overrides-only'


def fitted(plugin_path: Path) -> bool:
    """Whether the plugin holds an NPC_ with sculpt regions (FMRI)."""
    return any(tag == b'FMRI' for rec, _ in walk(plugin_path.read_bytes(), b'NPC_') for tag, _ in subrecords(rec.body))


def faces_path(plugin_path: Path) -> Path:
    """`plugin_path`'s faces stamp, beside its build stamp."""
    return stamp_path(plugin_path).with_name(plugin_path.name + FACES_SUFFIX)


def base_build(plugin_path: Path) -> 'str | None':
    """Which build of `plugin_path` is on disk ('<started> to <ended>' of its finished stamp), None without one.
    See: docs/fork/fo4_facegen_plan.md#faces-stamp
    """
    try:
        kept = json.loads(stamp_path(plugin_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return f'{kept.get("started")} to {kept.get("ended")}' if kept.get('status') == 'finished' else None


def write_faces_stamp(plugin_path: Path, status: str, argv: list, cwd: Path) -> None:
    """The faces stamp: `status` (running, finished), the plugin build it ran on, and its arguments and folder (so
    build_plan can run it again after a rebuild)."""
    path = faces_path(plugin_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {'status': status, 'base_build': base_build(plugin_path), 'argv': [str(a) for a in argv],
            'cwd': str(cwd), 'ended': None if status == 'running' else time.strftime('%Y-%m-%d %H:%M:%S')}
    path.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')


def faces_stamp(plugin_path: Path) -> 'dict | None':
    """`plugin_path`'s faces stamp, None when this stage never ran on it."""
    try:
        return json.loads(faces_path(plugin_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def faces_stale(plugin_path: Path) -> 'str | None':
    """Why `plugin_path`'s faces must run again: they did not finish, or ran on another build of the plugin than
    the one on disk (a rebuild writes the plugin without them). None when they are current, never ran, or the
    plugin has no finished build to run on.
    See: docs/fork/fo4_facegen_plan.md#faces-stamp
    """
    kept, now = faces_stamp(plugin_path), base_build(plugin_path)
    if kept is None or now is None:
        return None
    if kept.get('status') != 'finished':
        return f'its faces stage did not finish (stamp {faces_path(plugin_path)})'
    if kept.get('base_build') != now:
        return f'its faces ran on build {kept.get("base_build")}, the plugin is now build {now}'
    return None


def as_built(plugin_path: Path) -> str:
    """Put the plugin back as its build wrote it, from the copy kept of this build, before this stage patches it;
    keep that copy when no faces run has patched this build yet. What was done.
    See: docs/fork/fo4_facegen_plan.md#faces-as-built
    """
    now, kept = base_build(plugin_path), faces_path(plugin_path)
    copy, of = kept.with_name(plugin_path.name + BUILT_SUFFIX), kept.with_name(plugin_path.name + BUILT_OF_SUFFIX)
    if now is None:
        return 'no finished build: the plugin as it is'
    if copy.is_file() and of.is_file() and of.read_text(encoding='utf-8') == now:
        shutil.copyfile(copy, plugin_path)
        return 'restored from the copy of its build'
    if (faces_stamp(plugin_path) or {}).get('base_build') == now:
        return 'already patched by a faces run on this build, no copy kept: rebuild it to start from its build'
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(plugin_path, copy)
    of.write_text(now, encoding='utf-8')
    return 'as built, copy kept'


def clear(plugin: str, data_dir: Path, staged: bool = False) -> None:
    """Remove `plugin`'s FaceGen from `data_dir`, with `staged` its face textures staged for the texture archive
    too."""
    for folder in FACEGEN_DIRS:
        shutil.rmtree(data_dir / folder / plugin, ignore_errors=True)
    if staged:
        shutil.rmtree(staging_root(data_dir) / FACEGEN_DIRS[1] / plugin, ignore_errors=True)


def prune(plugin: str, data_dir: Path, npcs) -> int:
    """Delete `plugin`'s FaceGen it no longer uses: a FaceGeom NIF naming no NPC_ in `npcs` (FormIDs), and a face
    texture, loose or staged for the BA2, whose FaceGeom NIF is gone (an export writes both for every face and
    clears the NIFs first); how many files went."""
    names = {f'{fid & 0xFFFFFF:08X}' for fid in npcs}
    nifs = list((data_dir / FACEGEN_DIRS[0] / plugin).glob('*'))
    stale = [p for p in nifs if p.stem.upper() not in names]
    faces = {p.stem.upper() for p in nifs} & names
    for folder in (data_dir / FACEGEN_DIRS[1] / plugin, staging_root(data_dir) / FACEGEN_DIRS[1] / plugin):
        stale += [p for p in folder.glob('*') if p.name[:8].upper() not in faces]
    for path in stale:
        path.unlink()
    return len(stale)


def drawn_parts(nif_bytes: bytes) -> set:
    """A FaceGeom NIF's shape names: the EditorIDs of the head parts drawn."""
    nif = nif_file.read(nif_bytes)
    names = [b['name'] if isinstance(b, dict) else struct.unpack_from('<i', b)[0]
             for kind, b in nif.blocks if kind in facegeom.SHAPES]
    return {nif.strings[i] for i in names}


def outdated(plugin_path: Path, data_dir: Path, master_dirs=()) -> list:
    """`plugin_path`'s FaceGeom NIFs in `data_dir` drawing other head parts than their NPC_ now has, or whose
    NPC_ the plugin no longer has (masters and their files from `data_dir`, then `master_dirs`).
    See: docs/fork/fo4_spikes.md#stale-facegen
    """
    nifs, plugin = sorted((data_dir / FACEGEN_DIRS[0] / plugin_path.name).glob('*')), plugin_path.name
    src = facegeom.Sources(plugin_path, [data_dir, *master_dirs]) if nifs else None
    stale = []
    for path in nifs:
        if src.record(plugin.lower(), int(path.stem, 16) & 0xFFFFFF) is None:
            stale.append(path)
            continue
        npc, race, female, _ = facegeom.npc_face(src, plugin, int(path.stem, 16))
        parts = {facegeom.zstr(p.first(b'EDID')) for p in facegeom.head_parts(src, npc, race, female)}
        stale += [path] if parts != drawn_parts(path.read_bytes()) else []
    return stale


def own_export(job: tuple, forms: list, textures: bool = True, redrawn: frozenset = frozenset()) -> list:
    """Write our own FaceGen for `forms` (facegen_own.export_own; face textures only with `textures`, no _d for
    `redrawn`); report lines, each failure (left without FaceGen) with its error.
    See: docs/fork/fo4_facegen_plan.md#own-stage
    """
    written, kept, skipped, failed, misses = facegen_own.export_own(job, forms, textures, redrawn)
    lines = [f'own FaceGen written: {written + kept} ({kept} from the work cache), not exported (as the CK): '
             f'{skipped}, failed: {len(failed)}']
    lines += [f'  work cache missed {count}: {why}' for why, count in misses.most_common()]
    return lines + [f'  {form_id:08X} {error}' for form_id, error in sorted(failed.items())]


def override_faces(job: tuple, export_dir: Path) -> list:
    """FaceGen of their own for the faces the plugin's overrides change (facegen_inherit.changed), under their
    master's folder name, each master's old one cleared first; report lines.
    See: docs/fork/fo4_facegen_plan.md#override-faces
    """
    data_dir, plugin, lines = job[1], job[2], []
    for owner in masters_of((data_dir / plugin).read_bytes()):
        clear(owner, data_dir, staged=True)
    for owner, forms in facegen_inherit.changed(data_dir, plugin, export_dir).items():
        lines += owner_faces((*job[:2], owner, job[3], plugin), forms)
    return lines


def owner_faces(job: tuple, forms: list) -> list:
    """Heads, refit, heads of the refitted and skin of master job[2]'s NPCs `forms` as the plugin job[4] overrides
    them, patched into its records. A failed face's files go, so it keeps its master's FaceGen and values. Report
    lines."""
    data_dir, owner, plugin = job[1], job[2], job[4]
    redrawn = frozenset(f.form_id for f in facegen_skin.fitted_npcs(data_dir / plugin, job[0], owner) if not f.own)
    written, kept, skipped, failed, _ = facegen_own.export_own(job, forms, True, redrawn)
    for form_id in failed:
        for folder in FACEGEN_DIRS:
            for path in (data_dir / folder / owner).glob(f'{form_id:08X}*'):
                path.unlink()
    lines = [f'{owner} faces the overrides change: {written + kept} drawn ({kept} from the work cache), '
             f'not exported (as the CK): {skipped}, failed: {len(failed)}']
    lines += [f'  {form_id:08X} {error}' for form_id, error in sorted(failed.items())]
    faces = facegen_skin.fitted_faces(data_dir, owner, job[0], plugin)
    lines += facegen_skin.refine(job, faces)
    facegen_own.export_own(job, [f.form_id for f in faces], False, redrawn)
    return lines + facegen_skin_cache.skin(job, faces)


def geometry(data_dir: Path, plugin: str) -> tuple:
    """Archive prefixes of the plugin's and its masters' FaceGeom folders."""
    names = [plugin, *masters_of((data_dir / plugin).read_bytes())]
    return tuple((FACEGEN_DIRS[0] / name).as_posix().lower() + '/' for name in names)


def restore(data_dir: Path, plugin: str) -> int:
    """restore_packed() if stashed() or Main has no current record; the count.
    See: docs/fork/fo4_pipeline.md#loose-stash
    """
    main = data_dir / f'{Path(plugin).stem} - Main.ba2'
    return restore_packed(data_dir, plugin) if stashed(data_dir, plugin) or archived(main) is None else 0


def pack(data_dir: Path, plugin: str, keep_loose: bool) -> None:
    """The plugin's archives packed again with its FaceGen (pack_textures pruning nothing: this run staged no
    texture; Main keeping its other entries as packed), then the loose copies they hold dropped unless
    `keep_loose`; printed.
    See: docs/fork/fo4_pipeline.md#main-archive
    See: docs/fork/fo4_pipeline.md#faces-repack
    """
    print('textures packed:', charged('faces pack textures', pack_textures, data_dir, plugin,
                                      (LUT_FOLDER, CLASSIC_FOLDER), False))
    print('files packed into the Main and voices archives:',
          charged('faces pack main', pack_main, data_dir, plugin, geometry(data_dir, plugin)))
    if not keep_loose:
        print('loose files the archives hold, removed:', charged('faces drop loose', drop_packed, data_dir, plugin))


def heads(job: tuple, forms: list = None) -> None:
    """Write the plugin's FaceGen heads (own_export) for every NPC, the old ones cleared first, without the _d the
    skin step draws again (a fitted NPC without its own face set), or only the FaceGeom NIFs of refitted `forms`
    (the refit changes sliders, which no face texture reads); printed.
    See: docs/fork/fo4_facegen_plan.md#second-pass
    """
    data_dir, plugin = job[1], job[2]
    if forms is None:
        clear(plugin, data_dir)
    redrawn = frozenset(f.form_id for f in facegen_skin.fitted_npcs(data_dir / plugin, job[0]) if not f.own)
    lines = own_export(job, facegen_own.own_npcs(data_dir / plugin) if forms is None else forms, forms is None,
                       redrawn)
    for line in lines:
        print(line, flush=True)


def steps(args, data_dir: Path, export_dir: Path) -> None:
    """Restore, heads, refit, heads of the refitted, skin, overrides' faces (facegen_inherit) and pack, each charged
    to its stage (stage_timer).
    See: docs/fork/fo4_facegen_plan.md#stage-times
    """
    print('loose files restored from the Main archive:', charged('faces restore', restore, data_dir, args.plugin))
    job = (export_dir, data_dir, args.plugin, skin_tone_layers(FALLOUT4_ESM.read_bytes()))
    charged('faces heads', heads, job)
    faces = charged('faces fitted list', facegen_skin.fitted_faces, data_dir, args.plugin, export_dir)
    for line in charged('faces refit', facegen_skin.refine, job, faces):
        print(line)
    if faces:
        charged('faces heads refitted', heads, job, [f.form_id for f in faces])
    for line in charged('faces skin', facegen_skin_cache.skin, job, faces):
        print(line)
    for line in charged('faces override heads', override_faces, job, export_dir):
        print(line)
    overrides(args, data_dir, export_dir)
    charged('faces pack', pack, data_dir, args.plugin, args.keep_loose)


def overrides(args, data_dir: Path, export_dir: Path) -> None:
    """The overrides step (facegen_inherit.inherit), printed."""
    for line in charged('faces overrides', facegen_inherit.inherit, data_dir, args.plugin, export_dir,
                        args.overrides_only):
        print(line)


def main():
    """Heads, refine, heads again, skin and pack, in workers on one BLAS thread each (configure_multiprocessing);
    print what was done. The faces stamp records the plugin build this ran on (faces_stale).
    See: docs/commentary/performance.md#blas-threads-commit
    """
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('--keep-loose', action='store_true',
                    help="Keep the loose copies of what the plugin's archives hold (a build folder fo4_deploy copies)")
    ap.add_argument('--own-facegen', action='store_true',
                    help='DEPRECATED, no effect: the heads are always ours (faces stamps of older builds pass it)')
    ap.add_argument(OVERRIDES_ONLY, action='store_true',
                    help="Only give the faces this plugin overrides its master's values again (a master's ran since)")
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    configure_multiprocessing()
    data_dir, export_dir = Path(args.data), Path(args.export)
    plugin_path, argv = data_dir / args.plugin, [a for a in sys.argv[1:] if a != OVERRIDES_ONLY]
    if not args.overrides_only:
        print('plugin:', as_built(plugin_path), flush=True)
    write_faces_stamp(plugin_path, 'running', argv, Path(os.getcwd()))
    charged('faces calibration', calibration.ensure)
    stop = sample()
    (overrides if args.overrides_only else steps)(args, data_dir, export_dir)
    stop()
    for line in report():
        print(line)
    write_faces_stamp(plugin_path, 'finished', argv, Path(os.getcwd()))


if __name__ == '__main__':
    main()
