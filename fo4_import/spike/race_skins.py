"""Each FNV look race's skin: a copy of the human race's clean skin (SkinNaked) and its addons, whose texture sets
copy the clean ones with only the diffuse changed, to Fallout 4's clean body or hands under FNV's race dirt
(race_body), wherever the race's texture for that part and sex is not FNV's stock one. Races sharing their four
textures share one skin. FormIDs are hashed from those FNV texture paths.

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
from fo4_import.spike.fnv_npc import asset, body_shade
from fo4_import.spike.void_actors import copy_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of a look race's skin records (key: its FNV texture paths and the vanilla record copied).
SITE = 'FNV RACE SKIN'
#: Fallout4.esm's human race (its WNAM is the clean skin copied) and dirty skin (its fade at the neck is followed).
HUMAN, DIRTY = 'HumanRace', 'SkinNakedDirty'
#: The FNV race parts a skin draws, in key order: body and hands, male then female.
PARTS = ('MalePart[0]', 'MalePart[1]', 'FemalePart[0]', 'FemalePart[1]')
#: Per part key, FNV's stock texture, which a race's own is measured against.
STOCK = {'MalePart[0]': 'characters\\male\\upperbodymale.dds', 'MalePart[1]': 'characters\\male\\handmale.dds',
         'FemalePart[0]': 'characters\\female\\upperbodyfemale.dds',
         'FemalePart[1]': 'characters\\female\\handfemale.dds'}
#: An addon's texture set subrecord per sex (female?).
SEX_SET = {False: b'NAM0', True: b'NAM1'}
#: The folder under Textures the diffuses go in, and their version (part of each one's staging signature).
TEXTURES, VERSION = 'FNV\\Skin', 1


def race_textures(race: dict) -> tuple:
    """FNV `race`'s texture per PARTS (each part's second texture, the head's coming first), lower case; None
    where it is the stock one or missing."""
    out = []
    for part in PARTS:
        textures = race.get(part + '.Texture')
        own = textures[1].lower() if isinstance(textures, list) and len(textures) > 1 else STOCK[part]
        out.append(None if own == STOCK[part] else own)
    return tuple(out)


def part_at(female: bool, part: int) -> int:
    """The PARTS index of FNV body part `part` (0 body, 1 hands) of sex `female`."""
    return 2 * female + part


@dataclass
class Vanilla:
    """Fallout4.esm's records the skins copy: {FormID: record} of ARMO, ARMA, TXST, the clean and dirty skins'
    addons in order, the tint basis templates' QNAM RGB per sex (female?)."""

    records: dict
    clean: list
    dirty: list
    template: dict


def vanilla(fo4: bytes) -> Vanilla:
    """Vanilla's records for the skins, read from Fallout4.esm bytes `fo4`."""
    records, named = {}, {}
    for rec, _ in walk(fo4, b'RACE', b'ARMO', b'ARMA', b'TXST'):
        records[rec.form_id], named[_edid(rec)] = rec, rec
    clean = records[_form(named[HUMAN], b'WNAM')]
    tones = template_tones(fo4, skin_tone_layers(fo4))
    template = {f: np.array(struct.unpack('<4f', q)[:3]) for f, (q, _, _) in tones.items()}
    return Vanilla(records, [clean, *_addons(clean, records)], _addons(named[DIRTY], records), template)


def _addons(skin, records: dict) -> list:
    """The addon records skin `skin` lists."""
    return [records[struct.unpack('<I', d)[0]] for t, d in subrecords(skin.body) if t == b'MODL']


def _edid(rec) -> str:
    """`rec`'s EditorID."""
    return dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')


def _form(rec, tag: bytes) -> int:
    """The FormID in `rec`'s subrecord `tag`."""
    return struct.unpack('<I', dict(subrecords(rec.body))[tag])[0]


def _path(txst) -> str:
    """Texture set `txst`'s diffuse path (TX00) under Textures."""
    return dict(subrecords(txst.body))[b'TX00'].rstrip(b'\0').decode('cp1252')


def _part(addon) -> int:
    """The FNV race part (0 body, 1 hands) vanilla skin addon `addon` draws."""
    return 0 if struct.unpack_from('<I', dict(subrecords(addon.body))[b'BOD2'])[0] & BODY_SLOT else 1


class RaceSkins:
    """The look races' skins of one build, each written once."""

    def __init__(self, builder, export_dir: Path, races: list):
        """For `builder`, FNV export `export_dir` and its RACE records `races`."""
        self.builder, self.export_dir = builder, export_dir
        self.keys = {int(r['FormID'], 16): race_textures(r) for r in races}
        self.made, self.looks, self.vanilla, self.archives = {}, {}, None, None

    def skin(self, race: int) -> 'int | None':
        """The skin (ARMO) of FNV race `race`, written once; None for a race on FNV's stock textures."""
        key = self.keys.get(race)
        if key is None or not any(key):
            return None
        if key not in self.made:
            self.vanilla = self.vanilla or vanilla(self.builder.fo4)
            self.made[key] = self._write(key)
        return self.made[key]

    def _write(self, key: tuple) -> int:
        """Write the skin of FNV textures `key` (PARTS order): its texture sets, addons and ARMO; the ARMO's id."""
        skin, *addons = self.vanilla.clean
        name, write, ids = '|'.join(t or '-' for t in key), self.builder.writer, {}
        edid = f'FNV_LookSkin_{Path(next(t for t in key if t)).parent.name}'
        for addon in addons:
            sets = {SEX_SET[f]: struct.pack('<I', self._set(key, addon, f)) for f in SEX_SET}
            fid = ids[addon.form_id] = write.derive_formid(SITE, f'{name} {addon.form_id:06X}')
            write.add_record('ARMA', copy_record(addon, fid, f'{edid}_{_edid(addon)}', sets))
        fid = write.derive_formid(SITE, f'{name} ARMO')
        write.add_record('ARMO', copy_record(skin, fid, edid, edit=lambda tag, data: (
            pack_subrecord('MODL', struct.pack('<I', ids[struct.unpack('<I', data)[0]])) if tag == b'MODL'
            else pack_subrecord(tag.decode(), data))))
        self.builder.counts['look race skins'] += 1
        return fid

    def _set(self, key: tuple, addon, female: bool) -> int:
        """The texture set addon `addon` draws for sex `female`: vanilla's clean one, or its copy on FNV's race
        texture (key), whose diffuse is staged."""
        clean, at = self.vanilla.records[_form(addon, SEX_SET[female])], part_at(female, _part(addon))
        if key[at] is None:
            return clean.form_id
        rel = f'{TEXTURES}\\{Path(key[at]).with_suffix("").as_posix().replace("/", chr(92))}_d.dds'
        stage_texture(self.builder.data_dir, rel, functools.partial(self._plan, key, at, clean))
        fid = self.builder.writer.derive_formid(SITE, f'{key[at]} {clean.form_id:06X}')
        named = f'FNV_LookSkin_{Path(key[at]).parent.name}_{Path(key[at]).stem}'
        self.builder.writer.add_record('TXST', copy_record(clean, fid, named,
                                                           {b'TX00': rel.encode('cp1252') + b'\0'}))
        return fid

    def _plan(self, key: tuple, at: int, clean_set) -> tuple:
        """stage_texture's (signature, writer) of part `at`'s diffuse."""
        sources = [asset(self.export_dir, 'textures', p) for p in (key[at], STOCK[PARTS[at]])]
        stamp = ' '.join(f'{p.name} {p.stat().st_size} {p.stat().st_mtime_ns}' for p in sources if p.is_file())
        return f'race skin {VERSION} {key[at]} {stamp}', functools.partial(self._diffuse, key, at, clean_set)

    def _diffuse(self, key: tuple, at: int, clean_set, target: Path) -> None:
        """Write part `at`'s diffuse (race_body.drawn_dirt) at `target`, in clean set `clean_set`'s format."""
        self.archives = self.archives or Archives(FALLOUT4_DIR / 'Data')
        clean = self.archives.read('textures\\' + _path(clean_set))
        dirt, weight, tint, shade = self._look(key, at >= 2)
        if at % 2:
            dirt, weight = race_body.hand_dirt(*self._fnv(key, at), shade), 1.0
        target.write_bytes(dds_like(race_body.drawn_dirt(hair.image(clean), dirt, weight, tint), clean))

    def _fnv(self, key: tuple, at: int) -> tuple:
        """(FNV race texture of part `at`, the part's stock texture) as float RGBA."""
        paths = (key[at], STOCK[PARTS[at]])
        return tuple(hair.image(asset(self.export_dir, 'textures', p)).astype(float) for p in paths)

    def _look(self, key: tuple, female: bool) -> tuple:
        """_made_look of `key` and sex `female`, made once."""
        if (key, female) not in self.looks:
            self.looks[key, female] = self._made_look(key, female)
        return self.looks[key, female]

    def _made_look(self, key: tuple, female: bool) -> tuple:
        """(the body's dirt carried onto FO4's body, ones on FNV's stock body; its fade at the neck; the skin tint
        of a race NPC of T1 tone; the race's overall shade, fnv_npc.body_shade) for `key` and sex `female`."""
        at, sex = part_at(female, 0), 'female' if female else 'male'
        paths = [asset(self.export_dir, 'textures', p) for p in (key[at], STOCK[PARTS[at]])] if key[at] else []
        shade = body_shade(*paths) if paths else np.ones(3)
        fit = self.builder.equipment.body(sex)
        distance = race_body.neck_distance(fit)
        clean, dirty = (hair.image(self.archives.read('textures\\' + _path(self.vanilla.records[_form(
            next(a for a in addons if _part(a) == 0), SEX_SET[female])]))).astype(float)
            for addons in (self.vanilla.clean[1:], self.vanilla.dirty))
        weight = race_body.fade_curve(distance, clean, dirty)
        base = np.median(race_body.resized(clean, distance.shape)[distance < race_body.FADE_STEP][:, :3], 0)
        tint = tint_for(tinted(base, self.vanilla.template[female]) * shade, base)
        if not paths:
            return np.ones(3), weight, tint, shade
        dirt = race_body.dirt(*self._fnv(key, at), shade)
        return race_body.carried(fit, race_body.fnv_body(self.export_dir, sex, fit), dirt), weight, tint, shade
