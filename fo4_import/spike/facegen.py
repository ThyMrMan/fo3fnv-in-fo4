"""The faces stage: FaceGen for a plugin's NPCs, from the Creation Kit, with FNV's faces carried onto it.

    py -3.14 -m fo4_import.spike.facegen --export <FalloutNV.esm export> --data <mod folder> FalloutNV.esm

Runs the CK's `-ExportFaceGenData:<plugin> X64` through MO2 (so it loads the
profile's plugins), moves the FaceGeom NIFs and face tint textures it writes
from where MO2 put them (creation_kit) into the mod folder. Each fitted NPC's
sliders are refitted to that export's miss (facegen_skin.refine) and the CK
exports again. The face textures (2048 square, one mip) are re-encoded at
vanilla's sizes and formats with full mips, then each fitted NPC gets FNV's
skin, its rear head texture and skin tone (facegen_skin.skin). Last, the
FaceGeom NIFs go into the plugin's Main archive and the face textures into
its Textures archive, as vanilla ships both, and the loose copies leave the
mod folder (the build's own come back first, so the Main archive keeps them).

With --own-facegen the heads are ours instead (facegen_own): FaceGeom NIF and
face textures at vanilla's formats for each NPC the CK would export, in a
worker pool; an NPC that fails is listed and gets the CK's export (fallback).
The refit, skin and packing steps run on them unchanged.

The CK's targets are XB1, X64, PS4 and W32. W32 rewrites a hair's cloth
physics (BSClothExtraData's Havok packfile) with 4-byte pointers; the 64-bit
game misreads it and long hair stretches to the floor. X64 keeps 8-byte ones,
as vanilla FaceGen does.

See: docs/fork/fo4_spikes.md#spike-2-facegen
"""

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fo4_import.base.ba2_pack import (archived, drop_packed, pack_main, pack_textures, restore_packed, stashed,
                                      staging_root)
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.classic_look import CLASSIC_FOLDER
from fo4_import.face import facegeom
from fo4_import.face.texture import vanilla_face_texture
from fo4_import.face.tint import skin_tone_layers
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import creation_kit
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.spike import facegen_own, facegen_skin
from fo4_import.spike.imagespace import LUT_FOLDER
from tes5_import.base.tes5_reader import subrecords, walk

#: The CK's export target: X64, since W32 writes hair cloth physics the 64-bit game misreads (see the module doc).
CK_TARGET = 'X64'
#: The game's pointer size, and where a BSClothExtraData block (u32 size, packfile) states its packfile's.
GAME_POINTER_SIZE, CLOTH_POINTER_SIZE_AT = 8, 20
#: Folders (under Meshes / Textures) the CK writes a plugin's FaceGen into.
FACEGEN_DIRS = (Path('Meshes/Actors/Character/FaceGenData/FaceGeom'),
                Path('Textures/Actors/Character/FaceCustomization'))
#: Seconds to wait for the CK at least, and per NPC_ record (the region: 293 in 127 s, 0.43 s each).
CK_TIMEOUT, CK_FACE_SECONDS = 900, 6.0
#: The faces stamp beside a plugin's build stamp: which build of the plugin this stage last ran on, and how.
FACES_SUFFIX = '.faces.json'
#: How a CK fallback that left NPCs without FaceGen starts its report line (the stage then fails).
FALLBACK_FAILED = 'CK fallback failed'


def npc_count(plugin_path: Path) -> int:
    """How many NPC_ records the plugin at `plugin_path` holds."""
    return sum(1 for _ in walk(plugin_path.read_bytes(), b'NPC_', bodies=()))


def ck_timeout(faces: int) -> float:
    """CK seconds for `faces` faces: CK_FACE_SECONDS each, at least CK_TIMEOUT."""
    return max(CK_TIMEOUT, faces * CK_FACE_SECONDS)


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


def expected_faces(plugin: str, data_dir: Path) -> set:
    """FaceGen stems (8 hex digits) of the NPCs the CK exports FaceGen for in `data_dir`'s `plugin`
    (facegeom.exported over the NPC_ records the plugin adds)."""
    plugin_path = data_dir / plugin
    src = facegen_skin.sources(plugin_path, data_dir)
    out = set()
    for form_id in facegen_own.own_npcs(plugin_path):
        npc = src.record(plugin.lower(), form_id)
        race = src.get(npc, npc.first(b'RNAM')) if npc is not None and npc.first(b'RNAM') else None
        if race is not None and facegeom.exported(npc, race):
            out.add(f'{form_id:08X}')
    return out


def missing_faces(plugin: str, data_dir: Path, expected: set) -> list:
    """The `expected` stems with no FaceGeom NIF in `data_dir`, sorted."""
    folder = data_dir / FACEGEN_DIRS[0] / plugin
    have = {p.stem.upper() for p in folder.glob('*.nif')} if folder.is_dir() else set()
    return sorted(expected - have)


def complete(plugin: str, data_dir: Path, only: set = None) -> int:
    """How many FaceGeom NIFs the CK export was to write (`only`: of those stems); raise naming the NPCs it left
    without one (a CK that stalled mid-export is closed after creation_kit.CK_QUIET and exits as if done).
    See: docs/fork/fo4_facegen_plan.md#ck-exit-hang
    """
    want = expected_faces(plugin, data_dir)
    want = want & only if only is not None else want
    missing = missing_faces(plugin, data_dir, want)
    if missing:
        shown = ', '.join(missing[:20]) + (f' and {len(missing) - 20} more' if len(missing) > 20 else '')
        raise SystemExit(f'the Creation Kit export of {plugin} is incomplete: {len(missing)} of {len(want)} NPCs '
                         f'have no FaceGeom NIF ({shown})')
    return len(want)


def run_ck(plugin: str, data_dir: Path = None) -> None:
    """Export `plugin`'s FaceGen with the CK, timed for `data_dir`'s copy's NPCs."""
    timeout = ck_timeout(npc_count(data_dir / plugin) if data_dir else 0)
    creation_kit.run(f'-ExportFaceGenData:{plugin} {CK_TARGET}', timeout, f'exporting {plugin}')


def clear(plugin: str, data_dir: Path) -> None:
    """Remove `plugin`'s FaceGen from `data_dir`, so the CK's lands in overwrite."""
    for folder in FACEGEN_DIRS:
        shutil.rmtree(data_dir / folder / plugin, ignore_errors=True)


def collect(plugin: str, data_dir: Path, only: set = None) -> list:
    """Move `plugin`'s FaceGen files from where MO2 put them (creation_kit.output_dir) into `data_dir`; with `only`
    (FaceGen stems: 8 hex digits), just those NPCs' files, the others deleted. The FaceGeom NIFs moved."""
    nifs = []
    for folder in FACEGEN_DIRS:
        source = creation_kit.output_dir() / folder / plugin
        for path in sorted(source.glob('*')) if source.exists() else []:
            target = data_dir / folder / plugin / path.name
            if only is not None and path.name[:8].upper() not in only:
                path.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if path != target:
                shutil.move(str(path), str(target))
            nifs += [target] if path.suffix.lower() == '.nif' else []
    return nifs


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


def vanilla_textures(plugin: str, data_dir: Path, only: set = None) -> int:
    """How many of `plugin`'s face textures (with `only`, those NPCs' FaceGen stems) vanilla_face_texture
    re-encoded."""
    paths = sorted(p for p in (data_dir / FACEGEN_DIRS[1] / plugin).glob('*.dds')
                   if only is None or p.name[:8].upper() in only)
    with ThreadPoolExecutor() as pool:
        return sum(pool.map(vanilla_face_texture, paths))


def cloth_pointer_sizes(nif_bytes: bytes) -> list:
    """Each BSClothExtraData packfile's pointer size (8 on 64-bit PC)."""
    return [raw[CLOTH_POINTER_SIZE_AT] for kind, raw in nif_file.read(nif_bytes).blocks if kind == 'BSClothExtraData']


def drawn_parts(nif_bytes: bytes) -> set:
    """A FaceGeom NIF's shape names: the EditorIDs of the head parts the CK drew."""
    nif = nif_file.read(nif_bytes)
    names = [b['name'] if isinstance(b, dict) else struct.unpack_from('<i', b)[0]
             for kind, b in nif.blocks if kind in facegeom.SHAPES]
    return {nif.strings[i] for i in names}


def outdated(plugin_path: Path, data_dir: Path, master_dirs=()) -> list:
    """`plugin_path`'s FaceGeom NIFs in `data_dir` drawing other head parts than their NPC_ now has (masters
    and their files from `data_dir`, then `master_dirs`).
    See: docs/fork/fo4_spikes.md#stale-facegen
    """
    nifs, plugin = sorted((data_dir / FACEGEN_DIRS[0] / plugin_path.name).glob('*')), plugin_path.name
    src = facegeom.Sources(plugin_path, [data_dir, *master_dirs]) if nifs else None
    stale = []
    for path in nifs:
        npc, race, female, _ = facegeom.npc_face(src, plugin, int(path.stem, 16))
        parts = {facegeom.zstr(p.first(b'EDID')) for p in facegeom.head_parts(src, npc, race, female)}
        stale += [path] if parts != drawn_parts(path.read_bytes()) else []
    return stale


def checked(nifs: list) -> int:
    """How many FaceGeom NIFs `nifs` are; raise if any carries cloth physics for another pointer size than the
    game's."""
    wrong = [p.name for p in nifs if set(cloth_pointer_sizes(p.read_bytes())) - {GAME_POINTER_SIZE}]
    if wrong:
        raise SystemExit(f'the Creation Kit wrote cloth physics for another platform than {CK_TARGET}: {wrong}')
    return len(nifs)


def export(plugin: str, data_dir: Path, ck: bool = True) -> int:
    """Clear, run the CK (unless not `ck`: an earlier run's files wait where MO2 put them), collect `plugin`'s
    FaceGen; NIFs collected. Raise when an NPC the CK exports has no FaceGeom NIF (complete)."""
    if ck:
        clear(plugin, data_dir)
        run_ck(plugin, data_dir)
    nifs = checked(collect(plugin, data_dir))
    complete(plugin, data_dir)
    return nifs


def fallback(plugin: str, data_dir: Path, failed: dict) -> list:
    """Give the `failed` NPCs ({FormID: error}) the CK's FaceGen: ours set aside outside MO2's view (so the CK's
    lands in overwrite), the CK run, only those NPCs' files kept (re-encoded at vanilla's formats), ours put back.
    A CK that fails, or leaves one of them without a FaceGeom NIF (complete), leaves those NPCs without FaceGen,
    reported (FALLBACK_FAILED; the faces stage then fails). Report lines.
    See: docs/fork/fo4_facegen_plan.md#own-stage
    """
    stems = {f'{form_id:08X}' for form_id in failed}
    aside = Path(tempfile.mkdtemp(prefix='own_facegen_'))
    for folder in FACEGEN_DIRS:
        if (data_dir / folder / plugin).is_dir():
            shutil.move(str(data_dir / folder / plugin), str(aside / folder.name))
    try:
        run_ck(plugin, data_dir)
        nifs = checked(collect(plugin, data_dir, stems))
        complete(plugin, data_dir, stems)
        lines = [f'CK fallback: FaceGen for {nifs} of {len(failed)} failed NPCs, '
                 f'{vanilla_textures(plugin, data_dir, stems)} textures at vanilla size']
    except SystemExit as e:
        lines = [f'{FALLBACK_FAILED}, {len(failed)} NPCs have no FaceGen: {e}']
    for folder in FACEGEN_DIRS:
        if (aside / folder.name).is_dir():
            shutil.copytree(aside / folder.name, data_dir / folder / plugin, dirs_exist_ok=True)
    shutil.rmtree(aside, ignore_errors=True)
    return lines


def own_export(job: tuple, forms: list, textures: bool = True) -> list:
    """Write our own FaceGen for `forms` (facegen_own.export_own; face textures only with `textures`), the failed
    ones from the CK (fallback); report lines, each failure with its error."""
    data_dir, plugin = job[1], job[2]
    written, kept, skipped, failed = facegen_own.export_own(job, forms, textures)
    lines = [f'own FaceGen written: {written + kept} ({kept} from the work cache), not exported (as the CK): '
             f'{skipped}, failed: {len(failed)}']
    lines += [f'  {form_id:08X} {error}' for form_id, error in sorted(failed.items())]
    return lines + (fallback(plugin, data_dir, failed) if failed else [])


def geometry(plugin: str) -> tuple:
    """The archive prefix of the FaceGeom folder this stage rewrites."""
    return ((FACEGEN_DIRS[0] / plugin).as_posix().lower() + '/',)


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
    print('textures packed:', pack_textures(data_dir, plugin, (LUT_FOLDER, CLASSIC_FOLDER), prune=False))
    print('files packed into the Main and voices archives:', pack_main(data_dir, plugin, geometry(plugin)))
    if not keep_loose:
        print('loose files the archives hold, removed:', drop_packed(data_dir, plugin))


def heads(job: tuple, own: bool, forms: list = None, ck: bool = True) -> bool:
    """Write the plugin's FaceGen heads: ours (own_export) for every NPC, the old ones cleared first, or only the
    FaceGeom NIFs of refitted `forms` (the refit changes sliders, which no face texture reads); else the CK's
    export of every NPC (not `ck`: an earlier run's, collected); printed. False when a CK fallback left NPCs
    without FaceGen.
    See: docs/fork/fo4_facegen_plan.md#second-pass
    """
    data_dir, plugin = job[1], job[2]
    if not own:
        print('FaceGeom NIFs:', export(plugin, data_dir, ck))
        return True
    if forms is None:
        clear(plugin, data_dir)
    lines = own_export(job, facegen_own.own_npcs(data_dir / plugin) if forms is None else forms, forms is None)
    for line in lines:
        print(line, flush=True)
    return not any(line.startswith(FALLBACK_FAILED) for line in lines)


def main():
    """Export, refine, export again, skin and pack; print what was done. The faces stamp records the plugin build
    this ran on (faces_stale); exit 2 when a CK fallback left NPCs without FaceGen."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('--keep-loose', action='store_true',
                    help="Keep the loose copies of what the plugin's archives hold (a build folder fo4_deploy copies)")
    ap.add_argument('--collected', action='store_true',
                    help="Don't run the CK first: collect the FaceGen an earlier CK run left where MO2 puts it")
    ap.add_argument('--own-facegen', action='store_true',
                    help="Write the FaceGen heads ourselves; the Creation Kit only for NPCs that fail")
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    data_dir, export_dir = Path(args.data), Path(args.export)
    plugin_path = data_dir / args.plugin
    write_faces_stamp(plugin_path, 'running', sys.argv[1:], Path(os.getcwd()))
    print('loose files restored from the Main archive:', restore(data_dir, args.plugin))
    job = (export_dir, data_dir, args.plugin, skin_tone_layers(FALLOUT4_ESM.read_bytes()))
    whole = heads(job, args.own_facegen, ck=not args.collected)
    faces = facegen_skin.fitted_faces(data_dir, args.plugin)
    for line in facegen_skin.refine(job, faces):
        print(line)
    if faces:
        whole = heads(job, args.own_facegen, [f.form_id for f in faces]) and whole
    if not args.own_facegen:
        print('face textures at vanilla size:', vanilla_textures(args.plugin, data_dir))
    for line in facegen_skin.skin(job, faces):
        print(line)
    pack(data_dir, args.plugin, args.keep_loose)
    if not whole:
        raise SystemExit(f'faces of {args.plugin}: a CK fallback left NPCs without FaceGen (lines above)')
    write_faces_stamp(plugin_path, 'finished', sys.argv[1:], Path(os.getcwd()))


if __name__ == '__main__':
    main()
