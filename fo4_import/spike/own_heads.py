"""A mod's own hair, eyes and face skin carried to its FO4 NPCs as head parts and a face texture set.

A plugin with masters that authors its own HAIR, EYES or RACE record ships
the look FNV draws from it (hair mesh and texture, eye texture, race head
texture); the nearest vanilla FO4 part (spike.head_parts) loses it. For an
NPC using one:

- Hair: the mod's hair mesh worn on FO4's head (Equipment.head_worn), split
  for hats (nif.hair_mesh), on a copy of its material whose diffuse is its
  texture in the NPC's FNV hair colour (fnv_npc.hair_rgb), set as vanilla
  hair's (HAIR_MATERIAL); a new hair head part takes the chosen vanilla
  hair's place, extras and all.
- Eyes: copies of the chosen vanilla eyes and their texture set, its
  diffuse FNV's eye texture carried across by face.eyes.
- Face skin (own race): a copy of HumanRace's default face texture set
  whose diffuse is FNV's whole face (texture.face_texture T2: race skin and
  FaceGen colour) on FO4's face UVs, named by FTST; the tint fit keeps only
  its brows and takes T2's skin tone, as the texture holds the rest.

Every record is new and keyed by authored data, so no FormID moves.
See: docs/fork/fo4_facegen_plan.md#own-heads
"""

import hashlib
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.texture.image_transcode import encode_dds
from fo4_import.base.writer import pack_fo4_record
from fo4_import.face import hair, sculpt, tint
from fo4_import.face.bake import face_shape, positions, triangles, uvs
from fo4_import.face.eyes import eye_texture
from fo4_import.face.texture import dds_like, face_texture
from fo4_import.nif import bgsm
from fo4_import.nif import file as nif_file
from fo4_import.nif.hair_mesh import HAIR_REST, as_hair, hat_field
from fo4_import.pipeline.elric_cache import write_new
from fo4_import.pipeline.export_index import export_masters, own_records
from fo4_import.spike import fnv_npc
from fo4_import.spike import records as R
from fo4_import.spike.void_actors import copy_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of the records made here; folder (under Meshes, Materials, Textures) of their assets.
SITE, FOLDER = 'FNV own head', 'fnv\\own\\'
#: The FNV record types whose own copy in a plugin with masters means it ships its own look.
OWN_TYPES = ('HAIR', 'EYES', 'RACE')
#: Fallout4.esm HumanRace, and its default face texture set per sex (female?).
HUMAN_RACE, FACE_SETS = 0x13746, {False: b'DFTM', True: b'DFTF'}
#: Vanilla human hair materials' settings: alpha-tested at 90, two-sided, no glow.
HAIR_MATERIAL = {'alpha_test': True, 'alpha_test_ref': 90, 'alpha_blend': False, 'two_sided': True,
                 'glowmap': False}


def brows_only(values: np.ndarray, female: bool) -> np.ndarray:
    """Tint fit `values` with every option but its basis' brows at 0."""
    _, options, _, brows = tint.load_basis(female)
    return np.array([v if o in brows else 0.0 for o, v in zip(options, values)])


def shown_scale(raw: np.ndarray, face: tuple, female: bool) -> np.ndarray:
    """Per channel, how much brighter the game draws face set diffuse `raw` at the default skin tone: the tint
    basis baseline's (the CK's export of a default face) median over `face`'s texels over `raw`'s."""
    mask = tint.face_mask(face)
    seen = np.median(tint.reduced(tint.load_basis(female)[2])[mask][:, :3], 0)
    drawn = np.median(tint.reduced(raw)[mask][:, :3], 0)
    return seen / np.maximum(drawn, 1.0)


def _texture_path(stem: str) -> bytes:
    """A texture set's path subrecord for `stem` (under Textures, no extension)."""
    return (stem + '.dds\0').encode()


def _archive_dds(assets, path: bytes) -> bytes:
    """DDS bytes of texture set path `path` from the game's archives."""
    name = path.rstrip(b'\0').decode().replace('/', '\\').lower()
    return assets.archives.read('textures\\' + name)


class OwnHeads:
    """The own head parts and face sets of one build's NPCs (module notes), each made once."""

    def __init__(self, builder, export_dir: Path):
        """Made for `builder`'s build of the plugin exported at `export_dir`."""
        self.builder, self.export_dir = builder, export_dir
        self.made, self.records, self.own = {}, None, None

    def owns(self, sig: str, form_id: 'str | None') -> bool:
        """Whether FNV record `form_id` (export hex) of type `sig` is one the plugin, having masters, makes: in its
        own load slot, so not an override of a master's."""
        if self.own is None:
            slot = len(export_masters(self.export_dir))
            self.own = {s: {r['FormID'] for r in own_records(self.export_dir, s) if int(r['FormID'], 16) >> 24 == slot}
                        if slot else set() for s in OWN_TYPES}
        return form_id in self.own[sig]

    def of(self, npc: dict, female: bool, chosen, tinted, assets) -> tuple:
        """(head part swaps {vanilla part: own parts} for head_parts_edit, FTST edit or None, the tint fit to use)
        of FNV NPC `npc`, given its chosen vanilla parts and tint fit."""
        swaps = {}
        if chosen.hair is not None and self.owns('HAIR', npc.get('HNAM.Hair')):
            own = self._hair(npc, female, assets)
            swaps.update({chosen.hair: [own]} if own else {})
        if chosen.eyes is not None and self.owns('EYES', npc.get('ENAM.Eyes')):
            swaps[chosen.eyes] = [self._eyes(npc, female, chosen.eyes, assets)] + assets.extras(chosen.eyes)
        own_race = tinted is not None and self.owns('RACE', npc.get('RNAM.Race'))
        face = self._face(npc, female, assets) if own_race else None
        if face is None:
            return swaps, None, tinted
        return swaps, R.with_face(face[0]), (brows_only(tinted[0], female), face[1], tinted[2])

    def _fo4(self, form_id: int):
        """Fallout4.esm's HDPT, TXST or RACE record `form_id` (indexed once)."""
        if self.records is None:
            self.records = {r.form_id: r for r, _ in walk(self.builder.fo4, b'HDPT', b'TXST', b'RACE')}
        return self.records[form_id]

    def _add(self, sig: str, key: str, make) -> int:
        """The FormID of record `key`, made by `make(fid)` (its packed bytes) and counted the first time."""
        if key not in self.made:
            fid = self.builder.writer.derive_formid(SITE, key)
            self.builder.writer.add_record(sig, make(fid))
            self.builder.counts[f'{sig} (a mod\'s own head)'] += 1
            self.made[key] = fid
        return self.made[key]

    def _write_texture(self, stem: str, rgba: np.ndarray, like: bytes = None) -> None:
        """RGBA uint8 `rgba` as Textures\\`stem`.dds (full mips), in the format and size of vanilla DDS `like` when
        it takes that texture's place (the CK refuses a face texture whose format differs from its race's).
        See: docs/fork/fo4_facegen_plan.md#ck-face-texture-format
        """
        path = self.builder.data_dir / 'Textures' / f'{stem}.dds'
        data = dds_like(rgba, like) if like else encode_dds(Image.fromarray(rgba, 'RGBA'))
        write_new(path, data)

    def _hair(self, npc: dict, female: bool, assets) -> 'int | None':
        """The hair head part of FNV NPC `npc`'s own hair in its colour (module notes); None when its mesh is not
        drawn on the head."""
        rec = fnv_npc.record(self.export_dir, 'HAIR', npc['HNAM.Hair'])
        colour = ''.join(f'{int(npc[f"HCLR.{c}"]):02x}' for c in 'RGB')
        sex = 'female' if female else 'male'
        key = f'HAIR {rec["FormID"]} {sex} {colour}'
        if key in self.made:
            return self.made[key]
        mesh = self._hair_mesh(rec, sex, colour, npc, assets)
        if mesh is None:
            return None
        subs = (pack_subrecord('EDID', f'FNV_{rec["EditorID"]}_{sex}_{colour}\0'.encode())
                + pack_subrecord('MODL', (mesh + '\0').encode())
                + pack_subrecord('DATA', bytes([hair.FEMALE if female else hair.MALE]))
                + pack_subrecord('PNAM', struct.pack('<I', hair.HAIR)))
        return self._add('HDPT', key, lambda fid: pack_fo4_record('HDPT', fid, 0, subs))

    def _hair_mesh(self, rec: dict, sex: str, colour: str, npc: dict, assets) -> 'str | None':
        """FNV hair `rec` as an FO4 hair mesh in `colour` for `sex`, written once; its path under Meshes."""
        worn = self.builder.equipment.head_worn(rec['Model.MODL'], sex, (HAIR_REST,))
        if worn is None:
            return None
        static, nif = worn
        stem = f'{FOLDER}{Path(static).stem}_{colour}'
        material = self._hair_material(nif, rec, npc, stem)
        out = f'{stem}_{sex}.nif'
        write_new(self.builder.data_dir / 'Meshes' / out, as_hair(nif, hat_field(assets.archives), material))
        return out

    def _hair_material(self, nif: bytes, rec: dict, npc: dict, stem: str) -> str:
        """A copy of worn hair NIF `nif`'s material as HAIR_MATERIAL, its diffuse FNV hair `rec`'s texture in
        `npc`'s colour, both written as `stem`; its path from Materials\\ on."""
        parsed = nif_file.read(nif)
        source = min(parsed.strings[b['name']] for kind, b in parsed.blocks if kind == 'BSLightingShaderProperty')
        mat = bgsm.read((self.builder.data_dir / source).read_bytes())
        drawn = fnv_npc.hair_rgb(fnv_npc.asset(self.export_dir, 'textures', rec['ICON']), npc)
        self._write_texture(stem, np.clip(drawn, 0, 255).astype(np.uint8))
        mat['textures'].update(diffuse=f'{stem}.dds'.replace('\\', '/'), glow='')
        mat.update(HAIR_MATERIAL)
        write_new(self.builder.data_dir / 'Materials' / f'{stem}.bgsm', bgsm.write(mat))
        return f'materials\\{stem}.bgsm'

    def _eyes(self, npc: dict, female: bool, vanilla: int, assets) -> int:
        """A copy of vanilla eyes head part `vanilla` on a copy of its texture set wearing FNV NPC `npc`'s own eye
        texture (face.eyes)."""
        eyes = fnv_npc.record(self.export_dir, 'EYES', npc['ENAM.Eyes'])
        key = f'EYES {eyes["FormID"]} {npc["RNAM.Race"]} {vanilla:08X}'
        if key not in self.made:
            stem = f'{FOLDER}{Path(eyes["ICON"]).stem.lower()}_{vanilla:08x}'
            tnam = struct.unpack('<I', assets.parts[vanilla][b'TNAM'][0])[0]
            fo4 = _archive_dds(assets, assets.texture_sets[tnam][b'TX00'][0])
            self._write_texture(stem, self._eye_rgba(npc, female, vanilla, fo4, eyes, assets), fo4)
            txst = self._add('TXST', f'{key} TXST', lambda fid: copy_record(
                self._fo4(tnam), fid, f'FNV_{eyes["EditorID"]}_Eyes', {b'TX00': _texture_path(stem)}))
            data = bytes([assets.parts[vanilla][b'DATA'][0][0] & ~hair.PLAYABLE])
            self._add('HDPT', key, lambda fid: copy_record(self._fo4(vanilla), fid, f'FNV_{eyes["EditorID"]}',
                                                           {b'TNAM': struct.pack('<I', txst), b'DATA': data},
                                                           drop=frozenset({b'MODT'})))
        return self.made[key]

    def _eye_rgba(self, npc: dict, female: bool, vanilla: int, diffuse: bytes, eyes: dict, assets) -> np.ndarray:
        """face.eyes.eye_texture of FNV NPC `npc`'s eye texture (EYES `eyes`) onto vanilla eyes `vanilla`'s mesh
        and its texture set's `diffuse` (DDS bytes)."""
        export_dir = self.export_dir
        at = fnv_npc.frame(export_dir, npc['EditorID'], face_shape(sculpt.load_basis(female)[2])[0])
        points, tris, uv, _ = hair.fnv_shape(fnv_npc.eye_mesh(export_dir, at.race, at.part))
        raw, _ = assets.shapes(vanilla)[0]
        fo4 = hair.image(diffuse)
        fnv = hair.image(fnv_npc.asset(export_dir, 'textures', eyes['ICON']))
        return eye_texture(fo4, (positions(raw), uvs(raw), triangles(raw)), (at.to_fo4(points), tris, uv), fnv)

    def _face(self, npc: dict, female: bool, assets) -> 'tuple | None':
        """(face set, skin tone scale: _face_set) of FNV NPC `npc`, made once per race, sex and FaceGen colour
        (FGTS: all its face texture depends on); None when its race wears FNV's stock head skin (the sliders carry
        its FaceGen colour, as for the game's own races)."""
        colour = hashlib.sha1(npc.get('FGTS', '').encode()).hexdigest()[:12]
        name = f'{npc["RNAM.Race"]}_{"f" if female else "m"}_{colour}'.lower()
        if name not in self.made:
            fnv, pieces = fnv_npc.fnv_face(self.export_dir, npc['EditorID'])
            self.made[name] = None if pieces[2] is None else self._face_set(name, female, assets, fnv, pieces)
        return self.made[name]

    def _face_set(self, name: str, female: bool, assets, fnv, pieces: tuple) -> tuple:
        """(a copy of HumanRace's default face texture set of `female`'s sex wearing the whole face texture (T2)
        of fnv_face's `fnv` and `pieces`, both named by `name`; its skin tone scale)."""
        race = dict(subrecords(self._fo4(HUMAN_RACE).body))
        vanilla = self._fo4(struct.unpack('<I', race[FACE_SETS[female]])[0])
        diffuse = _archive_dds(assets, dict(subrecords(vanilla.body))[b'TX00'])
        fo4 = hair.image(diffuse)
        face = face_shape(sculpt.load_basis(female)[2])
        rgba, tone = face_texture(fo4, face, fnv, pieces, 'T2', shown_scale(fo4, face, female))
        stem = f'{FOLDER}face_{name}_d'
        self._write_texture(stem, rgba, diffuse)
        fid = self._add('TXST', f'FACE {name}', lambda fid: copy_record(
            vanilla, fid, f'FNV_Face_{name}', {b'TX00': _texture_path(stem)}))
        return fid, tone
