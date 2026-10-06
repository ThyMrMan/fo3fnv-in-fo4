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
import subprocess
import time
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.face.bake import bake
from fo4_import.face.fnv_head import head
from tes5_import.base.tes5_reader import walk, first_sub
from tes5_import.base.text_reader import parse_export_file

MO2 = Path(r'C:\Modlists\fo3fnv-in-fo4')
CK_EXECUTABLE, CK_PROCESS = 'Creation Kit', 'CreationKit.exe'
#: Folders (under Meshes / Textures) the CK writes a plugin's FaceGen into.
FACEGEN_DIRS = (Path('Meshes/Actors/Character/FaceGenData/FaceGeom'),
                Path('Textures/Actors/Character/FaceCustomization'))
#: Seconds to wait for the CK to finish, and between checks.
CK_TIMEOUT, CK_POLL = 900, 5
BAKED_VARIANTS = ('C1', 'C2')


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
    """{FormID: (FNV EditorID, variant)} of the plugin's NPCs named `FNV_<EditorID>_<C variant>`."""
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


def fnv_face(export_dir: Path, edid: str):
    """The FNV head (mean and NPC) of FNV NPC `edid`, from its race's head part and its FaceGen."""
    npc = next(r for r in parse_export_file(str(export_dir / 'NPC_.txt')) if r.get('EditorID') == edid)
    race = next(r for r in parse_export_file(str(export_dir / 'RACE.txt')) if r['FormID'] == npc['RNAM.Race'])
    part = 'FemalePart[0].Model' if int(npc.get('ACBS.Flags', 0)) & 1 else 'MalePart[0].Model'
    return head(export_dir / 'meshes', _first(race[part]), npc.get('FGGS', ''), npc.get('FGGA', ''))


def bake_variants(export_dir: Path, data_dir: Path, plugin: str) -> list:
    """Bake every C-variant NPC's FaceGeom NIF in `data_dir`; [(EditorID, variant)] baked."""
    done, faces = [], {}
    for form_id, (edid, variant) in sorted(_variant_npcs(data_dir / plugin).items()):
        path = data_dir / FACEGEN_DIRS[0] / plugin / f'{form_id:08X}.NIF'
        if not path.exists():
            continue
        if edid not in faces:
            faces[edid] = fnv_face(export_dir, edid)
        path.write_bytes(bake(path.read_bytes(), faces[edid], variant))
        done.append((edid, variant))
    return done


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
