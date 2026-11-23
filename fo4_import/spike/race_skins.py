"""Each FNV look race's skin: a copy of its body kind's clean skin (the FO4 race's WNAM: SkinNaked, SkinGhoulNaked)
and its addons, whose texture sets copy the clean ones with only the diffuse changed (a set drawing through a
material gets a copy of that material), to Fallout 4's clean body or hands under FNV's race dirt (race_body),
wherever the race's texture for that part and sex is not its kind's stock one. Races sharing their four textures
share one skin. FormIDs are hashed from those FNV texture paths.

See: docs/fork/fo4_look_races_plan.md#body
"""

import functools
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.base.ba2_pack import stage_texture
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face import hair, race_body
from fo4_import.face.facegeom import BODY_SLOT
from fo4_import.face.own_facegen import template_tones
from fo4_import.face.skin_tint import tint_for, tinted
from fo4_import.face.texture import dds_like
from fo4_import.face.tint import skin_tone_layers
from fo4_import.nif import bgsm
from fo4_import.spike.fnv_npc import asset, body_shade
from fo4_import.spike.void_actors import copy_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of a look race's skin records (key: its FNV texture paths and the vanilla record copied).
SITE = 'FNV RACE SKIN'
#: Fallout4.esm's dirty human skin: its fade at the neck is followed (every kind's skin draws the same body).
DIRTY = 'SkinNakedDirty'
#: The FNV race parts a skin draws, in key order: body and hands, male then female.
PARTS = ('MalePart[0]', 'MalePart[1]', 'FemalePart[0]', 'FemalePart[1]')
#: An addon's texture set subrecord per sex (female?).
SEX_SET = {False: b'NAM0', True: b'NAM1'}
#: The folder under Textures and Materials the copies go in, and the diffuses' version (in their staging signature).
FOLDER, VERSION = 'FNV\\Skin', 1


@dataclass(frozen=True)
class Kind:
    """A body kind's look skins: the FO4 race whose skin they copy, FNV's stock texture per PARTS (a race of the
    kind is a look race where its own differs), and whether its NPCs' skin tone carries their race's shade (a
    fitted face) or is the body NPC's own. Every look is measured against PLAIN's stock and drawn on PLAIN's
    clean skin, where both games' skin is plain.
    See: docs/fork/fo4_look_races_plan.md#body-transfer
    """

    race: str
    stock: tuple
    fitted: bool


#: The body kinds (npcs.body_kind's prefix) whose NPCs wear a look skin.
KINDS = {'human': Kind('HumanRace', ('characters\\male\\upperbodymale.dds', 'characters\\male\\handmale.dds',
                                     'characters\\female\\upperbodyfemale.dds', 'characters\\female\\handfemale.dds'),
                       True),
         'ghoul': Kind('GhoulRace', ('characters\\ghoul\\upperbodymale.dds', 'characters\\ghoul\\handmale.dds',
                                     'characters\\ghoulfemale\\upperbodyfemale.dds',
                                     'characters\\ghoulfemale\\handfemale.dds'), False)}
#: The kind whose skin is plain in both games.
PLAIN = 'human'


def race_textures(race: dict, stock: tuple) -> tuple:
    """FNV `race`'s texture per PARTS (each part's second texture, the head's coming first), lower case; None
    where it is the `stock` one or missing."""
    out = []
    for part, plain in zip(PARTS, stock):
        textures = race.get(part + '.Texture')
        own = textures[1].lower() if isinstance(textures, list) and len(textures) > 1 else plain
        out.append(None if own == plain else own)
    return tuple(out)


def part_at(female: bool, part: int) -> int:
    """The PARTS index of FNV body part `part` (0 body, 1 hands) of sex `female`."""
    return 2 * female + part


@dataclass
class Vanilla:
    """Fallout4.esm's records the skins copy: {FormID: record} of ARMO, ARMA, TXST, {kind: [its clean skin, its
    addons]}, the dirty skin's addons, the tint basis templates' QNAM RGB per sex (female?)."""

    records: dict
    clean: dict
    dirty: list
    template: dict


def vanilla(fo4: bytes) -> Vanilla:
    """Vanilla's records for the skins, read from Fallout4.esm bytes `fo4`."""
    records, named = {}, {}
    for rec, _ in walk(fo4, b'RACE', b'ARMO', b'ARMA', b'TXST'):
        records[rec.form_id], named[_edid(rec)] = rec, rec
    skins = {name: records[_form(named[kind.race], b'WNAM')] for name, kind in KINDS.items()}
    clean = {name: [skin, *_addons(skin, records)] for name, skin in skins.items()}
    tones = template_tones(fo4, skin_tone_layers(fo4))
    template = {f: np.array(struct.unpack('<4f', q)[:3]) for f, (q, _, _) in tones.items()}
    return Vanilla(records, clean, _addons(named[DIRTY], records), template)


def _addons(skin, records: dict) -> list:
    """The addon records skin `skin` lists."""
    return [records[struct.unpack('<I', d)[0]] for t, d in subrecords(skin.body) if t == b'MODL']


def _edid(rec) -> str:
    """`rec`'s EditorID."""
    return dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')


def _form(rec, tag: bytes) -> int:
    """The FormID in `rec`'s subrecord `tag`."""
    return struct.unpack('<I', dict(subrecords(rec.body))[tag])[0]


def _text(rec, tag: bytes) -> str:
    """`rec`'s string subrecord `tag`, '' when it has none."""
    return dict(subrecords(rec.body)).get(tag, b'').rstrip(b'\0').decode('cp1252')


def _part(addon) -> int:
    """The FNV race part (0 body, 1 hands) vanilla skin addon `addon` draws."""
    return 0 if struct.unpack_from('<I', dict(subrecords(addon.body))[b'BOD2'])[0] & BODY_SLOT else 1


def _copy_path(fnv_texture: str, suffix: str) -> str:
    """The copy's path (under Textures or Materials) for FNV texture `fnv_texture`."""
    return f'{FOLDER}\\{Path(fnv_texture).with_suffix("").as_posix().replace("/", chr(92))}{suffix}'


class RaceSkins:
    """The look races' skins of one build, each written once."""

    def __init__(self, builder, export_dir: Path, races: list, bodies: dict):
        """For `builder`, FNV export `export_dir`, its RACEs, the body NPCs {kind: rec}."""
        self.builder, self.export_dir, self.bodies = builder, export_dir, bodies
        self.races = {int(r['FormID'], 16): r for r in races}
        self.made, self.looks, self.keys, self.vanilla, self.archives = {}, {}, {}, None, None

    def skin(self, race: int, kind: str) -> 'int | None':
        """The skin (ARMO) of FNV race `race` for body kind `kind` (npcs.body_kind), written once; None for a kind
        without look skins or a race on its kind's stock textures."""
        name = kind.split('_')[0]
        key = self._key(race, name) if name in KINDS and race in self.races else None
        if key is None or not any(key):
            return None
        if (name, key) not in self.made:
            self.vanilla = self.vanilla or vanilla(self.builder.fo4)
            self.archives = self.archives or Archives(FALLOUT4_DIR / 'Data')
            self.made[name, key] = self._write(name, key)
        return self.made[name, key]

    def _key(self, race: int, name: str) -> tuple:
        """race_textures of `race` for kind `name`, a texture the export lacks counted and taken as stock; once."""
        if (race, name) not in self.keys:
            key = race_textures(self.races[race], KINDS[name].stock)
            kept = tuple(t if t and asset(self.export_dir, 'textures', t).is_file() else None for t in key)
            self.builder.counts['look race textures not exported'] += sum(map(bool, key)) - sum(map(bool, kept))
            self.keys[race, name] = kept
        return self.keys[race, name]

    def _write(self, name: str, key: tuple) -> int:
        """Write kind `name`'s skin of FNV textures `key`: its texture sets, addons and ARMO; the ARMO's id."""
        skin, *addons = self.vanilla.clean[name]
        sign, write, ids = '|'.join(t or '-' for t in key), self.builder.writer, {}
        edid = f'FNV_LookSkin_{Path(next(t for t in key if t)).parent.name}'
        for addon in addons:
            sets = {SEX_SET[f]: struct.pack('<I', self._set(name, key, addon, f)) for f in SEX_SET}
            fid = ids[addon.form_id] = write.derive_formid(SITE, f'{sign} {addon.form_id:06X}')
            write.add_record('ARMA', copy_record(addon, fid, f'{edid}_{_edid(addon)}', sets))
        fid = write.derive_formid(SITE, f'{sign} ARMO' if name == 'human' else f'{sign} {name} ARMO')
        write.add_record('ARMO', copy_record(skin, fid, edid, edit=lambda tag, data: (
            pack_subrecord('MODL', struct.pack('<I', ids[struct.unpack('<I', data)[0]])) if tag == b'MODL'
            else pack_subrecord(tag.decode(), data))))
        self.builder.counts['look race skins'] += 1
        return fid

    def _set(self, name: str, key: tuple, addon, female: bool) -> int:
        """The texture set addon `addon` draws for sex `female`: vanilla's clean one, or its copy on FNV's race
        texture (key), whose diffuse is staged (and, drawn through a material, that material copied)."""
        clean, at = self.vanilla.records[_form(addon, SEX_SET[female])], part_at(female, _part(addon))
        if key[at] is None:
            return clean.form_id
        rel = _copy_path(key[at], '_d.dds')
        stage_texture(self.builder.data_dir, rel, functools.partial(self._plan, name, key, at, clean))
        values = {b'TX00': rel.encode('cp1252') + b'\0'}
        if _text(clean, b'MNAM'):
            values = {b'MNAM': self._material(clean, key[at], rel).encode('cp1252') + b'\0'}
        fid = self.builder.writer.derive_formid(SITE, f'{key[at]} {clean.form_id:06X}')
        named = f'FNV_LookSkin_{Path(key[at]).parent.name}_{Path(key[at]).stem}'
        self.builder.writer.add_record('TXST', copy_record(clean, fid, named, values))
        return fid

    def _material(self, clean_set, fnv_texture: str, diffuse: str) -> str:
        """Write a copy of texture set `clean_set`'s material drawing `diffuse`; its path under Materials."""
        mat = bgsm.read(self.archives.read('materials\\' + _text(clean_set, b'MNAM')))
        mat['textures']['diffuse'] = diffuse.replace('\\', '/')
        rel = _copy_path(fnv_texture, '.bgsm')
        target = self.builder.data_dir / 'Materials' / rel.replace('\\', '/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bgsm.write(mat))
        return rel

    def _clean_diffuse(self, txst) -> bytes:
        """Texture set `txst`'s diffuse DDS: its own (TX00), else its material's."""
        path = _text(txst, b'TX00') or bgsm.read(self.archives.read('materials\\' + _text(txst, b'MNAM')))[
            'textures']['diffuse']
        return self.archives.read('textures\\' + path.replace('/', '\\'))

    def _plan(self, name: str, key: tuple, at: int, clean_set) -> tuple:
        """stage_texture's (signature, writer) of part `at`'s diffuse."""
        sources = [asset(self.export_dir, 'textures', p) for p in (key[at], KINDS[PLAIN].stock[at])]
        stamp = ' '.join(f'{p.name} {p.stat().st_size} {p.stat().st_mtime_ns}' for p in sources if p.is_file())
        return f'race skin {VERSION} {key[at]} {stamp}', functools.partial(self._diffuse, name, key, at, clean_set)

    def _diffuse(self, name: str, key: tuple, at: int, clean_set, target: Path) -> None:
        """Write part `at`'s diffuse (race_body.drawn_dirt) at `target`, in clean set `clean_set`'s format; another
        kind's draws PLAIN's clean diffuse under the dirt."""
        clean = self._clean_diffuse(clean_set)
        dirt, weight, tint, shade = self._look(name, key, at >= 2)
        if at % 2:
            dirt, weight = race_body.hand_dirt(*self._fnv(key, at), shade), 1.0
        base = None if name == PLAIN else hair.image(self._clean_diffuse(self._plain_set(at)))
        target.write_bytes(dds_like(race_body.drawn_dirt(hair.image(clean), dirt, weight, tint, base), clean))

    def _plain_set(self, at: int):
        """PLAIN's clean texture set of part `at`."""
        addon = next(a for a in self.vanilla.clean[PLAIN][1:] if _part(a) == at % 2)
        return self.vanilla.records[_form(addon, SEX_SET[at >= 2])]

    def _fnv(self, key: tuple, at: int) -> tuple:
        """(FNV race texture of part `at`, PLAIN's stock one) as float RGBA."""
        paths = (key[at], KINDS[PLAIN].stock[at])
        return tuple(hair.image(asset(self.export_dir, 'textures', p)).astype(float) for p in paths)

    def _look(self, name: str, key: tuple, female: bool) -> tuple:
        """_made_look of kind `name`, `key` and sex `female`, made once."""
        if (name, key, female) not in self.looks:
            self.looks[name, key, female] = self._made_look(name, key, female)
        return self.looks[name, key, female]

    def _made_look(self, name: str, key: tuple, female: bool) -> tuple:
        """(the body's dirt carried onto FO4's body, ones on the stock body; its fade at the neck; the skin tint;
        the race shade, fnv_npc.body_shade, or ones) for kind `name`, `key` and sex `female`. A fitted kind's tint
        is a T1-tone face's (the template's neck times the shade); another's is its body NPC's own QNAM."""
        at, sex, kind = part_at(female, 0), 'female' if female else 'male', KINDS[name]
        paths = [asset(self.export_dir, 'textures', p) for p in (key[at], KINDS[PLAIN].stock[at])] if key[at] else []
        shade = body_shade(*paths) if paths and kind.fitted else np.ones(3)
        fit = self.builder.equipment.body(sex)
        distance = race_body.neck_distance(fit)
        dirty_set = self.vanilla.records[_form(next(a for a in self.vanilla.dirty if _part(a) == 0), SEX_SET[female])]
        clean, dirty = (hair.image(self._clean_diffuse(s)).astype(float) for s in (self._plain_set(at), dirty_set))
        weight = race_body.fade_curve(distance, clean, dirty)
        base = np.median(race_body.resized(clean, distance.shape)[distance < race_body.FADE_STEP][:, :3], 0)
        tint = tint_for(tinted(base, self.vanilla.template[female]) * shade, base) if kind.fitted else np.array(
            struct.unpack('<4f', dict(subrecords(self.bodies[f'{name}_{sex}'].body))[b'QNAM'])[:3])
        if not paths:
            return np.ones(3), weight, tint, shade
        dirt = race_body.dirt(*self._fnv(key, at), shade)
        return race_body.carried(fit, race_body.fnv_body(self.export_dir, sex, fit), dirt), weight, tint, shade
