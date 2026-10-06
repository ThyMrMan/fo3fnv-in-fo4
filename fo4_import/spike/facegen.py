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
from fo4_import.face.bake import bake, face_shape
from fo4_import.face.fnv_head import coefficients, head
from fo4_import.face.texture import face_texture, fnv_texture, write_dds
from fo4_import.base.install import FALLOUT4_ESM
from tes5_import.base.tes5_reader import REC_HDR, SUB_HDR, first_sub, subrecords, walk
from tes5_import.base.text_reader import parse_export_file

MO2 = Path(r'C:\Modlists\fo3fnv-in-fo4')
CK_EXECUTABLE, CK_PROCESS = 'Creation Kit', 'CreationKit.exe'
#: Folders (under Meshes / Textures) the CK writes a plugin's FaceGen into.
FACEGEN_DIRS = (Path('Meshes/Actors/Character/FaceGenData/FaceGeom'),
                Path('Textures/Actors/Character/FaceCustomization'))
#: Seconds to wait for the CK to finish, and between checks.
CK_TIMEOUT, CK_POLL = 900, 5
#: Fallout4.esm HumanRace, and the tint slot (xEdit's TETI enum) of its Skin Tone options.
HUMAN_RACE, SKIN_TONE_SLOT = 0x13746, 12
#: Face variant -> (head shape bake.bake makes, face texture texture.face_texture makes or None).
BAKED_VARIANTS ={'C1': ('C1', None), 'C2': ('C2', None), 'T1': ('C1', 'T1'), 'T2': ('C1', 'T2')}


def run_ck(plugin: str) -> None:
    """Export `plugin`'s FaceGen with the CK through MO2 and wait for the CK to exit."""
    subprocess.run([str(MO2 / 'ModOrganizer.exe'), 'run', '-e', CK_EXECUTABLE, '-a',
                    f'-ExportFaceGenData:{plugin} W32'], check=True, **POPEN_FLAGS)
    deadline = time.time() + CK_TIMEOUT
    while time.time() < deadline:
        time.sleep(CK_POLL)
        listing = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {CK_PROCESS}'], capture_output=True,
                                 text=True, **POPEN_FLAGS).stdout
        if CK_PROCESS not in listing:
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


def _variant_npcs(plugin_path: Path) -> dict:
    """{FormID: (FNV EditorID, variant)} of the plugin's NPCs named `FNV_<EditorID>_<baked variant>`."""
    out = {}
    for rec, _ in walk(plugin_path.read_bytes(), b'NPC_'):
        edid = (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')
        stem, _, variant = edid.rpartition('_')
        if edid.startswith('FNV_') and variant in BAKED_VARIANTS:
            out[rec.form_id & 0xFFFFFF] = (stem[len('FNV_'):], variant)
    return out


def _first(value):
    """An export value that may repeat: its first."""
    return value[0] if isinstance(value, list) else value


def fnv_face(export_dir: Path, edid: str) -> tuple:
    """(FNV head, (race head texture, colour offset)) of FNV NPC `edid`, from its race's head part and FaceGen."""
    npc = next(r for r in parse_export_file(str(export_dir / 'NPC_.txt')) if r.get('EditorID') == edid)
    race = next(r for r in parse_export_file(str(export_dir / 'RACE.txt')) if r['FormID'] == npc['RNAM.Race'])
    part = 'FemalePart[0]' if int(npc.get('ACBS.Flags', 0)) & 1 else 'MalePart[0]'
    model = _first(race[part + '.Model'])
    fnv = head(export_dir / 'meshes', model, npc.get('FGGS', ''), npc.get('FGGA', ''))
    egt = (export_dir / 'meshes' / model.replace(chr(92), '/').lower()).with_suffix('.egt')
    texture = export_dir / 'textures' / _first(race[part + '.Texture']).replace(chr(92), '/').lower()
    return fnv, fnv_texture(texture, egt, coefficients(npc.get('FGTS', ''), 50))


def bake_variants(export_dir: Path, data_dir: Path, plugin: str) -> list:
    """Bake every C-variant NPC's FaceGeom NIF in `data_dir`; [(EditorID, variant)] baked."""
    done, faces, tone_layers = [], {}, skin_tone_layers()
    for form_id, (edid, variant) in sorted(_variant_npcs(data_dir / plugin).items()):
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
    raw = bytearray(plugin_path.read_bytes())
    rec = next(r for r, _ in walk(bytes(raw), b'NPC_') if r.form_id & 0xFFFFFF == form_id)
    pos, end, layer = rec.offset + REC_HDR, rec.offset + REC_HDR + rec.size, None
    while pos < end:
        tag, size = raw[pos:pos + 4], struct.unpack_from('<H', raw, pos + 4)[0]
        data = pos + SUB_HDR
        if tag == b'QNAM':
            rgba = struct.unpack_from('<4f', raw, data)
            struct.pack_into('<4f', raw, data, *(min(c * s, 1.0) for c, s in zip(rgba, scale)), rgba[3])
        elif tag == b'TETI':
            layer = struct.unpack_from('<HH', raw, data)[1]
        elif tag == b'TEND' and layer in layers and size >= 4:
            raw[data + 1:data + 4] = bytes(min(round(raw[data + 1 + i] * scale[i]), 255) for i in range(3))
        pos = data + size
    plugin_path.write_bytes(bytes(raw))


def main():
    """Export, collect and bake; print what was done."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--data', required=True, help='The mod folder holding the plugin')
    ap.add_argument('plugin', help='Plugin file name')
    args = ap.parse_args()
    data_dir = Path(args.data)
    clear(args.plugin, data_dir)
    run_ck(args.plugin)
    print('FaceGeom NIFs:', len(collect(args.plugin, data_dir)))
    for edid, variant in bake_variants(Path(args.export), data_dir, args.plugin):
        print(f'baked {edid} {variant}')


if __name__ == '__main__':
    main()
