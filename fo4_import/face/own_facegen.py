"""A test mod of our own FaceGen for a few NPCs: our FaceGeom NIF (facegeom) with FNV's shape baked in (bake),
the CK's face texture with FNV's FaceGen colour (texture.face_texture T1), and a plugin overriding the NPCs with
their skin tone scaled as T1 wants (tint.with_tone), as the build's faces stage does.

    py -3.14 -m fo4_import.face.own_facegen --plugin <deepest plugin> --dirs <masters' folders...>
        --export <an FNV export> --out temp/facegen_heads/<mod name> --npcs <plugin>:<FormID>...

Scratch only: it writes a mod folder under --out and touches nothing the build or the game reads.

See: docs/fork/fo4_facegen_plan.md#phase-1-our-own-facegeom
"""

import argparse
import struct
from pathlib import Path

import numpy as np

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.source import record_dir
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import facegeom, tint
from fo4_import.face.bake import bake, face_shape
from fo4_import.face.texture import face_texture, vanilla_face_texture, write_dds
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.fnv_npc import fnv_face
from fo4_import.spike.sculpt_calibration import TEMPLATES
from tes5_import.base.tes5_reader import subrecords, walk, zstr
from tes5_import.base.writer import pack_subrecord

#: Where a mod's FaceGen goes under its folder (Meshes, Textures).
GEOM_DIR = Path('Meshes/Actors/Character/FaceGenData/FaceGeom')
FACE_DIR = Path('Textures/Actors/Character/FaceCustomization')
#: The prefix our NPC EditorIDs put before FNV's.
FNV_PREFIX = 'FNV_'
#: The test mod's plugin, and the record header flag of a compressed body.
PLUGIN, COMPRESSED = 'FaceGen Test.esp', 0x40000


def fnv_edid(npc: facegeom.Rec) -> str:
    """The FNV EditorID our NPC record was converted from."""
    edid = facegeom.zstr(npc.first(b'EDID'))
    if not edid.startswith(FNV_PREFIX):
        raise ValueError(f'{edid} is not a converted FNV NPC')
    return edid[len(FNV_PREFIX):]


def write_face(out: Path, stem: str, faces: tuple) -> np.ndarray:
    """The NPC's _d: the CK's untinted face of its sex's template (tint basis baseline) with FNV's FaceGen colour
    (T1), at vanilla's format; `faces` = (female, FO4 face shape, FNV head, pieces). The tone scale T1 wants."""
    female, face, fnv, pieces = faces
    rgba, tone = face_texture(tint.load_basis(female)[2], face, fnv, pieces, 'T1')
    out.mkdir(parents=True, exist_ok=True)
    write_dds(rgba, out / f'{stem}_d.dds')
    vanilla_face_texture(out / f'{stem}_d.dds')
    return tone


def write_npc(src: facegeom.Sources, npc_key: tuple, export: Path, out: Path, shape: str) -> tuple:
    """Write one NPC's FaceGeom NIF (FNV's `shape` baked in) and T1 face texture (none for an NPC naming its own
    face set) under mod folder `out`; `npc_key` = (plugin, local id). (report line, (female, tone scale) or None)."""
    plugin, form_id = npc_key
    npc, race, female, _ = facegeom.npc_face(src, plugin, form_id)
    stem, edid = f'{form_id & 0xFFFFFF:08X}', fnv_edid(npc)
    nif = facegeom.build(src, plugin, form_id)
    fnv, pieces = fnv_face(record_dir(export, plugin), edid)
    eyes = next(facegeom.zstr(p.first(b'EDID')) for p in facegeom.head_parts(src, npc, race, female)
                if facegeom.part_type(p) == facegeom.EYES_PART)
    geom = out / GEOM_DIR / plugin / f'{stem}.nif'
    geom.parent.mkdir(parents=True, exist_ok=True)
    geom.write_bytes(bake(nif, fnv, shape, eyes))
    if npc.first(b'FTST'):
        return f'{stem} {edid}: shape {shape}, its own face set: the CK face texture and tone kept', None
    tone = write_face(out / FACE_DIR / plugin, stem, (female, face_shape(nif), fnv, pieces))
    return f'{stem} {edid}: shape {shape}, face T1, skin tone x{np.round(tone, 3).tolist()}', (female, tone)


def master_names(data: bytes) -> list:
    """A plugin's MAST names as written."""
    size = struct.unpack_from('<I', data, 4)[0]
    return [zstr(d) for tag, d in subrecords(data[24:24 + size]) if tag == b'MAST']


def template_tones(esm: bytes, layers: frozenset) -> dict:
    """{female: (QNAM, Skin Tone TETI, its TEND)} of each sex's tint basis template in Fallout4.esm bytes `esm`."""
    out = {}
    for rec, _ in walk(esm, b'NPC_'):
        female = next((f for f, fid in TEMPLATES.items() if fid == rec.form_id), None)
        if female is None:
            continue
        subs, teti = dict(subrecords(rec.body)), None
        for tag, data in subrecords(rec.body):
            teti = data if tag == b'TETI' else teti
            if tag == b'TEND' and struct.unpack('<HH', teti)[1] in layers:
                out[female] = (subs[b'QNAM'], teti, data)
    return out


def with_template_tone(body: bytes, template: tuple, scale, layers: frozenset) -> bytes:
    """NPC subrecords `body` with QNAM and the Skin Tone layer replaced by `template`'s (template_tones) times
    `scale`, as a T1 face's untinted template has them."""
    qnam, teti, tend = template
    out, skin = b'', False
    for tag, data in subrecords(body):
        if tag == b'TETI':
            skin = struct.unpack('<HH', data)[1] in layers
            data = teti if skin else data
        elif tag == b'TEND' and skin:
            data = tint.scaled_tone(b'TEND', tend, scale)
        elif tag == b'QNAM':
            data = tint.scaled_tone(b'QNAM', qnam, scale)
        out += pack_subrecord(tag.decode(), data)
    return out


def tone_plugin(path: Path, plugins: list, tones: dict) -> list:
    """Write `path`: overrides of the NPCs in `tones` {(plugin, local id): (female, scale)} with their template's
    tone scaled (with_template_tone); `plugins` are the source paths, deepest last, whose masters and selves begin
    its own. Its masters."""
    datas = {p.name: p.read_bytes() for p in plugins}
    order = master_names(datas[plugins[-1].name]) + [plugins[-1].name]
    esm = FALLOUT4_ESM.read_bytes()
    layers = skin_tone_layers(esm)
    templates = template_tones(esm, layers)
    w = FO4PluginWriter(masters=order, is_esm=False, description='FaceGen test: skin tones')
    for name, data in datas.items():
        own = len(master_names(data))
        if [m.lower() for m in order[:own + 1]] != [m.lower() for m in master_names(data) + [name]]:
            raise ValueError(f'{name} masters are not a prefix of {order}')
        wanted = {fid for (plugin, fid) in tones if plugin == name}
        for rec, _ in walk(data, b'NPC_'):
            if rec.form_id >> 24 == own and rec.form_id & 0xFFFFFF in wanted:
                female, scale = tones[name, rec.form_id & 0xFFFFFF]
                subs = with_template_tone(rec.body, templates[female], scale, layers)
                w.add_record('NPC_', pack_fo4_record('NPC_', rec.form_id, rec.flags & ~COMPRESSED, subs))
    w.write(str(path))
    return order


def main(argv=None) -> None:
    """Write the test mod folder --out for --npcs (plugin:FormID) of --plugin and its masters."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--plugin', type=Path, required=True, help='the deepest plugin; its masters are found in --dirs')
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='folders holding masters, loose files and BA2s')
    p.add_argument('--export', type=Path, required=True, help='an FNV export folder (others found beside it)')
    p.add_argument('--out', type=Path, required=True, help='the test mod folder (scratch)')
    p.add_argument('--npcs', nargs='+', required=True, help='plugin:FormID (hex)')
    p.add_argument('--shape', default='C2F', choices=('C1', 'C2', 'C2F'), help='bake.bake variant')
    args = p.parse_args(argv)
    src = facegeom.Sources(args.plugin, [args.plugin.parent] + args.dirs)
    tones = {}
    for item in args.npcs:
        plugin, fid = item.rsplit(':', 1)
        line, tones[plugin, int(fid, 16)] = write_npc(src, (plugin, int(fid, 16)), args.export, args.out, args.shape)
        print(line, flush=True)
    folders = [args.plugin.parent] + args.dirs
    plugins = [next(d / name for d in folders if (d / name).is_file())
               for name in dict.fromkeys(plugin for plugin, _ in tones) if name != args.plugin.name]
    toned = {npc: tone for npc, tone in tones.items() if tone}
    print('plugin masters:', tone_plugin(args.out / PLUGIN, plugins + [args.plugin], toned))


if __name__ == '__main__':
    main()
