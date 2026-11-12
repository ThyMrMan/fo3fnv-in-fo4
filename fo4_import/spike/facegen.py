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

The CK's targets are XB1, X64, PS4 and W32. W32 rewrites a hair's cloth
physics (BSClothExtraData's Havok packfile) with 4-byte pointers; the 64-bit
game misreads it and long hair stretches to the floor. X64 keeps 8-byte ones,
as vanilla FaceGen does.

See: docs/fork/fo4_spikes.md#spike-2-facegen
"""

import argparse
import shutil
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fo4_import.base.ba2_pack import drop_packed, pack_main, pack_textures, restore_packed, staging_root
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.classic_look import CLASSIC_FOLDER
from fo4_import.face import facegeom
from fo4_import.face.texture import vanilla_face_texture
from fo4_import.face.tint import skin_tone_layers
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import creation_kit
from fo4_import.spike import facegen_skin
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
CK_TIMEOUT, CK_FACE_SECONDS = 900, 2.0


def npc_count(plugin_path: Path) -> int:
    """How many NPC_ records the plugin at `plugin_path` holds."""
    return sum(1 for _ in walk(plugin_path.read_bytes(), b'NPC_', bodies=()))


def ck_timeout(faces: int) -> float:
    """CK seconds for `faces` faces: CK_FACE_SECONDS each, at least CK_TIMEOUT."""
    return max(CK_TIMEOUT, faces * CK_FACE_SECONDS)


def run_ck(plugin: str, data_dir: Path = None) -> None:
    """Export `plugin`'s FaceGen with the CK, timed for `data_dir`'s copy's NPCs."""
    timeout = ck_timeout(npc_count(data_dir / plugin) if data_dir else 0)
    creation_kit.run(f'-ExportFaceGenData:{plugin} {CK_TARGET}', timeout, f'exporting {plugin}')


def clear(plugin: str, data_dir: Path) -> None:
    """Remove `plugin`'s FaceGen from `data_dir`, so the CK's lands in overwrite."""
    for folder in FACEGEN_DIRS:
        shutil.rmtree(data_dir / folder / plugin, ignore_errors=True)


def collect(plugin: str, data_dir: Path) -> list:
    """Move `plugin`'s FaceGen files from where MO2 put them (creation_kit.output_dir) into `data_dir`; the FaceGeom
    NIFs moved."""
    nifs = []
    for folder in FACEGEN_DIRS:
        source = creation_kit.output_dir() / folder / plugin
        for path in sorted(source.glob('*')) if source.exists() else []:
            target = data_dir / folder / plugin / path.name
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


def vanilla_textures(plugin: str, data_dir: Path) -> int:
    """How many of `plugin`'s face textures vanilla_face_texture re-encoded."""
    with ThreadPoolExecutor() as pool:
        return sum(pool.map(vanilla_face_texture, sorted((data_dir / FACEGEN_DIRS[1] / plugin).glob('*.dds'))))


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


def export(plugin: str, data_dir: Path) -> int:
    """Clear, run the CK and collect `plugin`'s FaceGen; the FaceGeom NIFs collected. Raise if any carries cloth
    physics for another pointer size than the game's."""
    clear(plugin, data_dir)
    run_ck(plugin, data_dir)
    nifs = collect(plugin, data_dir)
    wrong = [p.name for p in nifs if set(cloth_pointer_sizes(p.read_bytes())) - {GAME_POINTER_SIZE}]
    if wrong:
        raise SystemExit(f'the Creation Kit wrote cloth physics for another platform than {CK_TARGET}: {wrong}')
    return len(nifs)


def pack(data_dir: Path, plugin: str, keep_loose: bool) -> None:
    """The plugin's archives packed again with its FaceGen (pack_textures pruning nothing: this run staged no
    texture), then the loose copies they hold dropped unless `keep_loose`; printed.
    See: docs/fork/fo4_pipeline.md#main-archive
    """
    print('textures packed:', pack_textures(data_dir, plugin, (LUT_FOLDER, CLASSIC_FOLDER), prune=False))
    print('files packed into the Main archive:', pack_main(data_dir, plugin))
    if not keep_loose:
        print('loose files the archives hold, removed:', drop_packed(data_dir, plugin))


def main():
    """Export, refine, export again, skin and pack; print what was done."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('--keep-loose', action='store_true',
                    help="Keep the loose copies of what the plugin's archives hold (a build folder fo4_deploy copies)")
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    data_dir, export_dir = Path(args.data), Path(args.export)
    print('loose files restored from the Main archive:', restore_packed(data_dir, args.plugin))
    print('FaceGeom NIFs:', export(args.plugin, data_dir))
    job = (export_dir, data_dir, args.plugin, skin_tone_layers(FALLOUT4_ESM.read_bytes()))
    faces = facegen_skin.fitted_faces(data_dir / args.plugin)
    for line in facegen_skin.refine(job, faces):
        print(line)
    if faces:
        print('FaceGeom NIFs, refined:', export(args.plugin, data_dir))
    print('face textures at vanilla size:', vanilla_textures(args.plugin, data_dir))
    for line in facegen_skin.skin(job, faces):
        print(line)
    pack(data_dir, args.plugin, args.keep_loose)


if __name__ == '__main__':
    main()
