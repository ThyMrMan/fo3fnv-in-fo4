"""A test mod of our own FaceGen for a few NPCs, read through an MO2 profile's load order as the CK reads it: our
FaceGeom NIF (facegeom) with FNV's shape baked in (bake), the face and rear head textures drawn from FNV's colour
on both sides of the hairline and faded to the body at the neck (skin_seams), and a plugin overriding the NPCs
with the skin tone those textures are drawn with.

    py -3.14 -m fo4_import.face.own_facegen --profile <MO2 profile folder> --export <an FNV export>
        --out temp/facegen_heads/<mod name> --npcs <plugin>:<FormID>...

Scratch only: it writes a mod folder under --out and touches nothing the build or the game reads.

See: docs/fork/fo4_facegen_plan.md#phase-1-our-own-facegeom
"""

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.source import record_dir
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import facegeom, hair, skin_seams, tint
from fo4_import.face.bake import bake, face_shape, positions, seam_tree, triangles, uvs
from fo4_import.face.texture import dds_like, vanilla_face_texture, write_dds
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import creation_kit
from fo4_import.spike.fnv_npc import fnv_face
from tes5_import.base.tes5_reader import subrecords, walk, zstr
from tes5_import.base.writer import pack_subrecord

#: Where a mod's FaceGen goes under its folder (Meshes, Textures), and the textures folder of its paths.
GEOM_DIR = Path('Meshes/Actors/Character/FaceGenData/FaceGeom')
FACE_DIR, FACE_PATH = Path('Textures/Actors/Character/FaceCustomization'), 'Actors\\Character\\FaceCustomization'
#: The prefix our NPC EditorIDs put before FNV's.
FNV_PREFIX = 'FNV_'
#: The test mod's plugin, and the record header flag of a compressed body.
PLUGIN, COMPRESSED = 'FaceGen Test.esp', 0x40000


@dataclass
class Job:
    """What every NPC of one run shares."""

    src: facegeom.Sources
    export: Path
    out: Path
    shape: str
    #: {female: (QNAM, Skin Tone TETI, its TEND)} of the tint basis templates (template_tones).
    templates: dict


def fnv_edid(npc: facegeom.Rec) -> str:
    """The FNV EditorID our NPC record was converted from."""
    edid = facegeom.zstr(npc.first(b'EDID'))
    if not edid.startswith(FNV_PREFIX):
        raise ValueError(f'{edid} is not a converted FNV NPC')
    return edid[len(FNV_PREFIX):]


def profile_order(profile: Path, mo2: Path, skip: tuple) -> tuple:
    """(MO2's overwrite then the profile's enabled mod folders, highest priority first; its active plugins in
    load order), without the mods and plugins named in `skip`."""
    def lines(name: str, mark: str) -> list:
        """The profile file's entries ticked with `mark`, mark dropped, but `skip`."""
        text = (profile / name).read_text(encoding='utf-8-sig').splitlines()
        return [line[1:] for line in text if line.startswith(mark) and line[1:] not in skip]
    return [mo2 / 'overwrite'] + [mo2 / 'mods' / name for name in lines('modlist.txt', '+')], lines('plugins.txt', '*')


def find(dirs: list, name: str) -> Path:
    """Plugin `name` in the first of `dirs` holding it, else the game's Data."""
    return next((d / name for d in dirs if (d / name).is_file()), FALLOUT4_DIR / 'Data' / name)


def body(src: facegeom.Sources, npc: facegeom.Rec, race: facegeom.Rec, female: bool, slot: int = 0) -> tuple:
    """(positions, UVs, RGB texture) of the NPC's body: its skin's body addon's model and skin texture set
    slot `slot` (0 diffuse, 7 specular)."""
    addon = facegeom.body_addon(src, npc, race)
    mesh = nif_file.read(src.read('meshes\\' + zstr(addon.first(b'MOD3' if female else b'MOD2'))))
    raw = max((b for k, b in mesh.blocks if k in facegeom.SHAPES and isinstance(b, bytes)), key=len)
    rgb = hair.image(src.read('textures\\' + facegeom.body_textures(src, npc, race, female)[slot]))[..., :3]
    return positions(raw), uvs(raw), rgb.astype(float)


def with_rear(job: Job, name: tuple, nif_bytes: bytes, rear: tuple) -> bytes:
    """The FaceGeom NIF with each skin-tint part (the rear head) on its own texture (skin_seams.rear_texture),
    written under the test mod as `<FormID>_rear_d`, and drawn with the NPC's skin tint; `name` = (plugin, stem),
    `rear` = (face points, colour, neck) as rear_texture takes them."""
    plugin, stem = name
    frame, colour, neck = rear
    nif = nif_file.read(nif_bytes)
    for kind, raw in list(nif.blocks):
        sh = nif.blocks[hair.shader_index(raw)][1] if kind in facegeom.SHAPES and isinstance(raw, bytes) else None
        if isinstance(sh, dict) and sh.get('skin_tint') is not None:
            texture_set = nif.blocks[sh['texture_set']][1]['textures']
            own = job.src.read('textures\\' + texture_set[0])
            rgba = skin_seams.rear_texture(hair.image(own), (positions(raw), uvs(raw), triangles(raw)), frame,
                                           colour, neck)
            texture_set[0] = f'{FACE_PATH}\\{plugin}\\{stem}_rear_d.dds'
            (job.out / 'Textures' / texture_set[0].replace('\\', '/')).write_bytes(dds_like(rgba, own))
            sh['skin_tint'] = (*(np.round(neck[1][1] * 255) / 255).tolist(), sh['skin_tint'][3])
    return nif_file.write(nif)


def write_skin(job: Job, who: tuple, nif: bytes, colour: tuple) -> tuple:
    """Write the NPC's face _d and rear head texture; (T1's tone scale, the NIF on its rear texture). `who` =
    (plugin, stem, npc, race, female), `colour` = (FNV head, pieces)."""
    plugin, stem, npc, race, female = who
    face, seam = face_shape(nif), seam_tree(nif)
    template = np.array(struct.unpack('<4f', job.templates[female][0])[:3])

    def tint_of(scale):
        """The skin tint (QNAM) the plugin gives for tone `scale`."""
        return np.clip(template * scale, 0.0, 1.0)
    neck = (seam, body(job.src, npc, race, female), tint_of)
    rgba, tone = skin_seams.face_texture(tint.load_basis(female)[2], face, *colour, neck)
    folder = job.out / FACE_DIR / plugin
    folder.mkdir(parents=True, exist_ok=True)
    write_dds(rgba, folder / f'{stem}_d.dds')
    vanilla_face_texture(folder / f'{stem}_d.dds')
    return tone, with_rear(job, (plugin, stem), nif, (face[0], colour, (seam, (template, tint_of(tone)))))


def write_npc(job: Job, plugin: str, form_id: int) -> tuple:
    """Write one NPC's FaceGeom NIF (FNV's shape baked in) and skin textures (none for an NPC naming its own face
    set, which keeps the CK's) under the test mod. (report line, (female, tone scale) or None)."""
    npc, race, female, _ = facegeom.npc_face(job.src, plugin, form_id)
    stem, edid = f'{form_id & 0xFFFFFF:08X}', fnv_edid(npc)
    nif = facegeom.build(job.src, plugin, form_id)
    fnv, pieces = fnv_face(record_dir(job.export, plugin), edid)
    eyes = next(facegeom.zstr(p.first(b'EDID')) for p in facegeom.head_parts(job.src, npc, race, female)
                if facegeom.part_type(p) == facegeom.EYES_PART)
    tone = None
    if not npc.first(b'FTST'):
        tone, nif = write_skin(job, (plugin, stem, npc, race, female), nif, (fnv, pieces))
    geom = job.out / GEOM_DIR / plugin / f'{stem}.nif'
    geom.parent.mkdir(parents=True, exist_ok=True)
    geom.write_bytes(bake(nif, fnv, job.shape, eyes))
    kept = 'its own face set: the CK face texture and tone kept' if tone is None else \
        f'face and rear head T1, skin tone x{np.round(tone, 3).tolist()}'
    return f'{stem} {edid}: shape {job.shape}, {kept}', None if tone is None else (female, tone)


def master_names(data: bytes) -> list:
    """A plugin's MAST names as written."""
    size = struct.unpack_from('<I', data, 4)[0]
    return [zstr(d) for tag, d in subrecords(data[24:24 + size]) if tag == b'MAST']


def template_tones(esm: bytes, layers: frozenset) -> dict:
    """{female: (QNAM, Skin Tone TETI, its TEND)} of each sex's tint basis template in Fallout4.esm bytes `esm`."""
    out = {}
    for rec, _ in walk(esm, b'NPC_'):
        female = next((f for f, fid in tint.TEMPLATES.items() if fid == rec.form_id), None)
        if female is None:
            continue
        subs, teti = dict(subrecords(rec.body)), None
        for tag, data in subrecords(rec.body):
            teti = data if tag == b'TETI' else teti
            if tag == b'TEND' and struct.unpack('<HH', teti)[1] in layers:
                out[female] = (subs[b'QNAM'], teti, data)
    return out


def with_template_tone(body_subs: bytes, template: tuple, scale, layers: frozenset) -> bytes:
    """NPC subrecords with QNAM and the Skin Tone layer replaced by `template`'s (template_tones) times `scale`,
    as a T1 face's untinted template has them."""
    qnam, teti, tend = template
    out, skin = b'', False
    for tag, data in subrecords(body_subs):
        if tag == b'TETI':
            skin = struct.unpack('<HH', data)[1] in layers
            data = teti if skin else data
        elif tag == b'TEND' and skin:
            data = tint.scaled_tone(b'TEND', tend, scale)
        elif tag == b'QNAM':
            data = tint.scaled_tone(b'QNAM', qnam, scale)
        out += pack_subrecord(tag.decode(), data)
    return out


def tone_plugin(path: Path, plugins: list, tones: dict, tone_data: tuple) -> list:
    """Write `path`: overrides of the NPCs in `tones` {(plugin, local id): (female, scale)} with their template's
    tone scaled (with_template_tone); `plugins` are the source paths, deepest last, whose masters and selves begin
    its own; `tone_data` = (template_tones, Skin Tone options). Its masters."""
    templates, layers = tone_data
    datas = {p.name: p.read_bytes() for p in plugins}
    order = master_names(datas[plugins[-1].name]) + [plugins[-1].name]
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
    """Write the test mod folder --out for --npcs (plugin:FormID) through --profile's load order."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--profile', type=Path, help="MO2 profile folder (default: MO2's selected profile)")
    p.add_argument('--export', type=Path, required=True, help='an FNV export folder (others found beside it)')
    p.add_argument('--out', type=Path, required=True, help='the test mod folder (scratch)')
    p.add_argument('--npcs', nargs='+', required=True, help='plugin:FormID (hex)')
    p.add_argument('--shape', default='C2F', choices=('C1', 'C2', 'C2F'), help='bake.bake variant')
    args = p.parse_args(argv)
    dirs, order = profile_order(args.profile or creation_kit.profile_dir(), creation_kit.MO2, (args.out.name, PLUGIN))
    npcs = [(plugin, int(fid, 16)) for plugin, fid in (item.rsplit(':', 1) for item in args.npcs)]
    names = sorted({plugin for plugin, _ in npcs}, key=lambda n: [o.lower() for o in order].index(n.lower()))
    esm = FALLOUT4_ESM.read_bytes()
    layers = tint.skin_tone_layers(esm)
    job = Job(facegeom.Sources(find(dirs, names[-1]), dirs, order), args.export, args.out, args.shape,
              template_tones(esm, layers))
    tones = {}
    for plugin, fid in npcs:
        line, tones[plugin, fid] = write_npc(job, plugin, fid)
        print(line, flush=True)
    toned = {npc: tone for npc, tone in tones.items() if tone}
    plugins = [find(dirs, name) for name in names]
    print('plugin masters:', tone_plugin(args.out / PLUGIN, plugins, toned, (job.templates, layers)))


if __name__ == '__main__':
    main()
