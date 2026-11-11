"""A test mod of our own FaceGen for a few NPCs: our FaceGeom NIF (facegeom), FNV's shape baked in (bake) and
FNV's face texture (texture.face_texture T2), with the face set's normal and smooth/spec maps as the NPC's own.

    py -3.14 -m fo4_import.face.own_facegen --plugin <plugin> --dirs <masters...> --export <FNV export>
        --out temp/facegen_heads/<mod name> --npcs <FormID>...

Scratch only: it writes a mod folder under --out and touches nothing the build or the game reads.

See: docs/fork/fo4_facegen_plan.md#phase-1-our-own-facegeom
"""

import argparse
from pathlib import Path

from fo4_import.face import facegeom, tint
from fo4_import.face.bake import bake, face_shape
from fo4_import.face.texture import face_texture, vanilla_face_texture, write_dds
from fo4_import.spike.fnv_npc import fnv_face

#: Where a mod's FaceGen goes under its folder (Meshes, Textures).
GEOM_DIR = Path('Meshes/Actors/Character/FaceGenData/FaceGeom')
FACE_DIR = Path('Textures/Actors/Character/FaceCustomization')
#: The prefix our NPC EditorIDs put before FNV's.
FNV_PREFIX = 'FNV_'
#: Face texture set slots of the normal and smooth/spec maps.
NORMAL_SLOT, SPECULAR_SLOT = 1, 7


def face_set_textures(src: facegeom.Sources, npc: facegeom.Rec, race: facegeom.Rec, female: bool) -> list:
    """The NPC's face texture set's slots (FTST), else the race's default set's."""
    owner, tag = (npc, b'FTST') if npc.first(b'FTST') else (race, facegeom.FACE_SETS[female])
    return facegeom.txst_slots(src, src.get(owner, owner.first(tag)))


def fnv_edid(npc: facegeom.Rec) -> str:
    """The FNV EditorID our NPC record was converted from."""
    edid = facegeom.zstr(npc.first(b'EDID'))
    if not edid.startswith(FNV_PREFIX):
        raise ValueError(f'{edid} is not a converted FNV NPC')
    return edid[len(FNV_PREFIX):]


def write_textures(src: facegeom.Sources, out: Path, stem: str, faces: tuple) -> tuple:
    """The NPC's _d (FNV's whole face, T2, on the CK's default face) and its face set's _msn and _s, at vanilla's
    formats; `faces` = (FO4 face shape, FNV head, pieces, npc, race, female). The skin tone scale T2 wants."""
    face, fnv, pieces, npc, race, female = faces
    out.mkdir(parents=True, exist_ok=True)
    rgba, tone = face_texture(tint.load_basis(female)[2], face, fnv, pieces, 'T2')
    write_dds(rgba, out / f'{stem}_d.dds')
    slots = face_set_textures(src, npc, race, female)
    for suffix, slot in (('_msn', NORMAL_SLOT), ('_s', SPECULAR_SLOT)):
        (out / f'{stem}{suffix}.dds').write_bytes(src.read('textures\\' + slots[slot]))
    for suffix in ('_d', '_msn', '_s'):
        vanilla_face_texture(out / f'{stem}{suffix}.dds')
    return tone


def write_npc(src: facegeom.Sources, plugin: str, form_id: int, export_dir: Path, out: Path, shape: str) -> str:
    """Write one NPC's FaceGeom NIF (FNV's `shape` baked in) and face textures under mod folder `out`; a report
    line."""
    npc, race, female, _ = facegeom.npc_face(src, plugin, form_id)
    stem, edid = f'{form_id & 0xFFFFFF:08X}', fnv_edid(npc)
    nif = facegeom.build(src, plugin, form_id)
    fnv, pieces = fnv_face(export_dir, edid)
    geom = out / GEOM_DIR / plugin / f'{stem}.nif'
    geom.parent.mkdir(parents=True, exist_ok=True)
    geom.write_bytes(bake(nif, fnv, shape))
    tone = write_textures(src, out / FACE_DIR / plugin, stem, (face_shape(nif), fnv, pieces, npc, race, female))
    return f'{stem} {edid}: shape {shape}, face T2, skin tone scale T2 wants {[round(float(t), 3) for t in tone]}'


def main(argv=None) -> None:
    """Write the test mod folder --out for --npcs of --plugin."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--plugin', type=Path, required=True)
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='folders holding masters, loose files and BA2s')
    p.add_argument('--export', type=Path, required=True, help='the FNV plugin\'s export folder')
    p.add_argument('--out', type=Path, required=True, help='the test mod folder (scratch)')
    p.add_argument('--npcs', nargs='+', required=True, help='FormIDs (hex)')
    p.add_argument('--shape', default='C1', choices=('C1', 'C2'), help='bake.bake variant')
    args = p.parse_args(argv)
    src = facegeom.Sources(args.plugin, [args.plugin.parent] + args.dirs)
    for npc in args.npcs:
        print(write_npc(src, args.plugin.name, int(npc, 16), args.export, args.out, args.shape), flush=True)


if __name__ == '__main__':
    main()
