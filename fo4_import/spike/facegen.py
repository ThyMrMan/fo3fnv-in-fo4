"""Spike 2 step 4: FaceGen for the cell's NPCs, from the Creation Kit, with FNV face shapes baked in.

    py -3.14 -m fo4_import.spike.facegen --export <FalloutNV.esm export> --data <mod folder> FNVCellSpike.esp

Runs the CK's `-ExportFaceGenData:<plugin> W32` through MO2 (so it loads the
profile's plugins), moves the FaceGeom NIFs and face tint textures it writes
from MO2's overwrite into the mod folder, then bakes the FNV face into every
NPC whose EditorID ends in a C variant (face.bake), from the FNV NPC its
EditorID names.

See: docs/fork/fo4_spikes.md#spike-2-facegen
"""

import argparse
import shutil
import struct
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.face.bake import bake, face_shape
from fo4_import.face.sculpt import load_basis as sculpt_basis
from fo4_import.face.texture import face_texture, write_dds
from fo4_import.face.tint import load_basis as tint_basis, scaled_tone
from fo4_import.spike.face_fit import npc_subrecords, refine_sculpt, refine_tint, variant_npcs
from fo4_import.spike.fnv_npc import fnv_face
from tes5_import.base.tes5_reader import subrecords, walk

MO2 = Path(r'C:\Modlists\fo3fnv-in-fo4')
CK_EXECUTABLE, CK_PROCESS = 'Creation Kit', 'CreationKit.exe'
#: Folders (under Meshes / Textures) the CK writes a plugin's FaceGen into.
FACEGEN_DIRS = (Path('Meshes/Actors/Character/FaceGenData/FaceGeom'),
                Path('Textures/Actors/Character/FaceCustomization'))
#: Where CKPE writes a zipped crash log and dump when the CK crashes.
CK_CRASHES = FALLOUT4_DIR / 'Logs' / 'CKPE' / 'Crashes'
#: Seconds to wait for the CK to finish, and between checks.
CK_TIMEOUT, CK_POLL = 900, 5
#: Fallout4.esm HumanRace, and the tint slot (xEdit's TETI enum) of its Skin Tone options.
HUMAN_RACE, SKIN_TONE_SLOT = 0x13746, 12
#: Face variants with fitted sculpt regions, with fitted tint layers, and how many CK rounds refine them.
SCULPTED, TINTED, REFINE_ROUNDS = frozenset({'ST', 'STH'}), frozenset({'ST', 'STH'}), 2
#: Face variant -> (head shape bake.bake makes or None, face texture texture.face_texture makes or None).
BAKED_VARIANTS = {'C1': ('C1', None), 'C2': ('C2', None), 'T1': ('C1', 'T1'), 'T2': ('C1', 'T2')}


def run_ck(plugin: str) -> None:
    """Export `plugin`'s FaceGen with the CK through MO2 and wait for the CK to exit; raise if it crashed."""
    started = time.time()
    subprocess.run([str(MO2 / 'ModOrganizer.exe'), 'run', '-e', CK_EXECUTABLE, '-a',
                    f'-ExportFaceGenData:{plugin} W32'], check=True, **POPEN_FLAGS)
    while time.time() < started + CK_TIMEOUT:
        time.sleep(CK_POLL)
        listing = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {CK_PROCESS}'], capture_output=True,
                                 text=True, **POPEN_FLAGS).stdout
        if CK_PROCESS not in listing:
            crashes = [p for p in CK_CRASHES.glob('*.zip') if p.stat().st_mtime > started]
            if crashes:
                raise SystemExit(f'the Creation Kit crashed exporting {plugin}: see {max(crashes)}')
            return
    raise SystemExit('the Creation Kit did not finish')


def clear(plugin: str, data_dir: Path) -> None:
    """Remove `plugin`'s FaceGen from `data_dir`, so the CK's lands in overwrite."""
    for folder in FACEGEN_DIRS:
        shutil.rmtree(data_dir / folder / plugin, ignore_errors=True)


def collect(plugin: str, data_dir: Path) -> list:
    """Move `plugin`'s FaceGen files from MO2's overwrite into `data_dir`; the FaceGeom NIFs moved."""
    nifs = []
    for folder in FACEGEN_DIRS:
        source = MO2 / 'overwrite' / folder / plugin
        for path in sorted(source.glob('*')) if source.exists() else []:
            target = data_dir / folder / plugin / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            nifs += [target] if path.suffix.lower() == '.nif' else []
    return nifs


def bake_variants(export_dir: Path, data_dir: Path, plugin: str) -> list:
    """Bake every C-variant NPC's FaceGeom NIF in `data_dir`; [(EditorID, variant)] baked."""
    done, faces, tone_layers = [], {}, skin_tone_layers()
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


def skin_tone_layers() -> frozenset:
    """HumanRace's tint option indices in the Skin Tone slot (male and female), from Fallout4.esm."""
    out = set()
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), b'RACE'):
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


def export(plugin: str, data_dir: Path) -> int:
    """Clear, run the CK and collect `plugin`'s FaceGen; the FaceGeom NIFs collected."""
    clear(plugin, data_dir)
    run_ck(plugin)
    return len(collect(plugin, data_dir))


def main():
    """Export, collect and bake; print what was done."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    data_dir, export_dir = Path(args.data), Path(args.export)
    print('FaceGeom NIFs:', export(args.plugin, data_dir))
    for round_ in range(REFINE_ROUNDS + 1):
        refined = refine_fits(export_dir, data_dir, args.plugin, apply=round_ < REFINE_ROUNDS)
        for line in refined:
            print(line)
        if refined and round_ < REFINE_ROUNDS:
            export(args.plugin, data_dir)
    for edid, variant in bake_variants(export_dir, data_dir, args.plugin):
        print(f'baked {edid} {variant}')


if __name__ == '__main__':
    main()
