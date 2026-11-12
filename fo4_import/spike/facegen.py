"""Spike 2 step 4: FaceGen for the cell's NPCs, from the Creation Kit, with FNV face shapes baked in.

    py -3.14 -m fo4_import.spike.facegen --export <FalloutNV.esm export> --data <mod folder> FalloutNV.esm

Runs the CK's `-ExportFaceGenData:<plugin> X64` through MO2 (so it loads the
profile's plugins), moves the FaceGeom NIFs and face tint textures it writes
from where MO2 put them (creation_kit) into the mod folder, then bakes the FNV face into every
NPC whose EditorID ends in a C variant (face.bake), from the FNV NPC its
EditorID names. Then the face textures (2048 square, one mip) are
re-encoded at vanilla's sizes and formats with full mips. Last, the
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

import numpy as np
from PIL import Image

from fo4_import.base.ba2_pack import drop_packed, pack_main, pack_textures, restore_packed, staging_root
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.classic_look import CLASSIC_FOLDER
from fo4_import.face import facegeom
from fo4_import.face.bake import bake, face_shape
from fo4_import.face.sculpt import load_basis as sculpt_basis
from fo4_import.face.texture import face_texture, vanilla_face_texture, write_dds
from fo4_import.face.tint import load_basis as tint_basis, scaled_tone
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import creation_kit
from fo4_import.spike.face_fit import npc_subrecords, refine_sculpt, refine_tint, variant_npcs
from fo4_import.spike.fnv_npc import fnv_face
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
#: Fallout4.esm HumanRace, and the tint slot (xEdit's TETI enum) of its Skin Tone options.
HUMAN_RACE, SKIN_TONE_SLOT = 0x13746, 12
#: Face variants with fitted sculpt regions, with fitted tint layers, and how many CK rounds refine them.
SCULPTED, TINTED, REFINE_ROUNDS = frozenset({'ST', 'STH'}), frozenset({'ST', 'STH'}), 2
#: Face variant -> (head shape bake.bake makes or None, face texture texture.face_texture makes or None).
BAKED_VARIANTS = {'C1': ('C1', None), 'C2': ('C2', None), 'T1': ('C1', 'T1'), 'T2': ('C1', 'T2')}


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


def bake_variants(export_dir: Path, data_dir: Path, plugin: str) -> list:
    """Bake every C-variant NPC's FaceGeom NIF in `data_dir`; [(EditorID, variant)] baked."""
    done, faces, tone_layers = [], {}, skin_tone_layers(FALLOUT4_ESM.read_bytes())
    for form_id, (edid, variant) in sorted(variant_npcs(data_dir / plugin, BAKED_VARIANTS).items()):
        path = data_dir / FACEGEN_DIRS[0] / plugin / f'{form_id:08X}.NIF'
        if not path.exists():
            continue
        if edid not in faces:
            faces[edid] = fnv_face(export_dir, edid)
        fnv, pieces = faces[edid]
        shape, texture = BAKED_VARIANTS[variant]
        if texture:
            diffuse = data_dir / FACEGEN_DIRS[1] / plugin / f'{form_id:08X}_d.dds'
            fo4_rgba = np.asarray(Image.open(diffuse).convert('RGBA'))
            rgba, tone = face_texture(fo4_rgba, face_shape(path.read_bytes()), fnv, pieces, texture)
            write_dds(rgba, diffuse)
            scale_skin_tone(data_dir / plugin, form_id, tone, tone_layers)
        if shape:
            path.write_bytes(bake(path.read_bytes(), fnv, shape))
        done.append((edid, variant))
    return done


def skin_tone_layers(esm: bytes) -> frozenset:
    """HumanRace's tint option indices in the Skin Tone slot (male and female), from Fallout4.esm's bytes `esm`."""
    out = set()
    for rec, _ in walk(esm, b'RACE'):
        if rec.form_id == HUMAN_RACE:
            out |= {struct.unpack('<HH', d)[1] for tag, d in subrecords(rec.body)
                    if tag == b'TETI' and struct.unpack('<HH', d)[0] == SKIN_TONE_SLOT}
    return frozenset(out)


def scale_skin_tone(plugin_path: Path, form_id: int, scale, layers: frozenset) -> None:
    """Multiply NPC `form_id`'s texture lighting (QNAM) and Skin Tone layer colour by `scale`, in place.

    Both keep their sizes, so the plugin's bytes are patched where they lie.
    """
    raw, layer = bytearray(plugin_path.read_bytes()), None
    for tag, data, size in npc_subrecords(raw, form_id):
        if tag == b'TETI':
            layer = struct.unpack_from('<HH', raw, data)[1]
        if tag == b'QNAM' or (tag == b'TEND' and layer in layers and size >= 4):
            raw[data:data + size] = scaled_tone(tag, bytes(raw[data:data + size]), scale)
    plugin_path.write_bytes(bytes(raw))


def refine_fits(export_dir: Path, data_dir: Path, plugin: str, apply: bool) -> list:
    """Measure every fitted NPC's export and, with `apply`, refine its fit; one report line each."""
    lines, plugin_path = [], data_dir / plugin
    note = '; refined' if apply else ''
    for form_id, (edid, variant) in sorted(variant_npcs(plugin_path, SCULPTED | TINTED).items()):
        stem = f'{form_id:08X}'
        if sculpt_basis() is not None:
            nif = data_dir / FACEGEN_DIRS[0] / plugin / f'{stem}.NIF'
            captured = refine_sculpt(plugin_path, form_id, edid, nif, export_dir, apply)
            lines.append(f'{edid} {variant}: shape captures {captured:.0%}{note}')
        if variant in TINTED and tint_basis() is not None:
            diffuse = data_dir / FACEGEN_DIRS[1] / plugin / f'{stem}_d.dds'
            captured = refine_tint(plugin_path, form_id, edid, diffuse, export_dir, apply)
            lines.append(f'{edid} {variant}: colour captures {captured:.0%}{note}')
    return lines


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


def export(plugin: str, data_dir: Path, ck: bool = True) -> int:
    """Clear, run the CK (unless not `ck`: an earlier run's files wait where MO2 put them) and collect `plugin`'s
    FaceGen; the FaceGeom NIFs collected. Raise if any carries cloth physics for another pointer size than the
    game's."""
    if ck:
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
    print('files packed into the Main and voices archives:', pack_main(data_dir, plugin))
    if not keep_loose:
        print('loose files the archives hold, removed:', drop_packed(data_dir, plugin))


def main():
    """Export, collect, bake and pack; print what was done."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('--keep-loose', action='store_true',
                    help="Keep the loose copies of what the plugin's archives hold (a build folder fo4_deploy copies)")
    ap.add_argument('--collected', action='store_true',
                    help="Don't run the CK first: collect the FaceGen an earlier CK run left where MO2 puts it")
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    data_dir, export_dir = Path(args.data), Path(args.export)
    print('loose files restored from the Main archive:', restore_packed(data_dir, args.plugin))
    print('FaceGeom NIFs:', export(args.plugin, data_dir, not args.collected))
    for round_ in range(REFINE_ROUNDS + 1):
        refined = refine_fits(export_dir, data_dir, args.plugin, apply=round_ < REFINE_ROUNDS)
        for line in refined:
            print(line)
        if refined and round_ < REFINE_ROUNDS:
            export(args.plugin, data_dir)
    for edid, variant in bake_variants(export_dir, data_dir, args.plugin):
        print(f'baked {edid} {variant}')
    print('face textures at vanilla size:', vanilla_textures(args.plugin, data_dir))
    pack(data_dir, args.plugin, args.keep_loose)


if __name__ == '__main__':
    main()
