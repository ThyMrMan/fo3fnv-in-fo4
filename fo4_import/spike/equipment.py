"""FNV weapons (WEAP) and armor (ARMO) as FO4 records, for the cell spike.

Each converted piece the replacement table (spike.replacements) gives a
Fallout4.esm `stats` or `fnv` target is a copy of that record, so it keeps
its models, animations, sounds, keywords and mod templates, with FNV's
name, value and weight over them (`item` targets are the records
themselves, spike.items). A weapon also takes FNV's base damage, and a gun
FNV's magazine size and ammunition (when it converts); the entry's `mods`
replace its default parts. In `fnv` mode a melee weapon shows FNV's own
mesh (nif.weapon), on the template's animations, without its mods; a gun
is written on the FO4 gun held, fired and laid out most like it
(spike.gun_choice; the target when none matches) and shows its mesh on that
gun's receiver skeleton, through copies of its default mods (spike.guns,
experimental); so does headgear FNV draws in
its head's frame (nif.headgear), through its own armor addon (ARMA) with
FNV's slots and the template addon's races, and an FNV outfit (a skinned
upper-body mesh) moved onto FO4's body (nif.outfit), through its own addon
with the template addon's slots and races and FNV's sleeves in first person;
FNV's alternate textures, which tell an outfit's variants apart on one mesh,
become material swaps (MSWP) on its models. Armor takes the protection FNV
gives it as its armor rating, unscaled: DT (all FNV armor), else DR (FO3's),
and drops the template's resistances. Condition and the template's scripts
are dropped. An FNV piece the table does not name is skipped and counted.
FormIDs are hashed from FNV's (SITES), so no other record's id moves.

See: docs/fork/fo4_spikes.md#spike-4-equipment
See: docs/fork/fo4_spikes.md#spike-4-melee
See: docs/fork/fo4_spikes.md#spike-4-headgear
See: docs/fork/fo4_spikes.md#spike-4-outfits
"""

import struct

from fo4_import.base import strings
from fo4_import.base.install import fnv_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif import headgear, outfit, weapon
from fo4_import.pipeline.work_cache import cached
from fo4_import.spike.gun_choice import GUN_TYPES
from fo4_import.spike.guns import Guns
from fo4_import.spike.replacements import BASE, Replacement
from fo4_import.spike import records as R
from fo4_import.spike.statics import swapped_material, write_assets
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid sites (key: FNV FormID).
SITES = {'WEAP': 'FNV WEAP', 'ARMO': 'FNV ARMO', 'ARMA': 'FNV ARMA', 'MSWP': 'FNV MSWP'}
#: FO4 WEAP DNAM offsets: ammo, capacity, animation type, weight, value, base damage.
DNAM_AMMO, DNAM_CAPACITY, DNAM_ANIM, DNAM_WEIGHT, DNAM_VALUE, DNAM_DAMAGE = 0, 52, 54, 59, 63, 67
#: FO4 WEAP DNAM animation type of a gun.
ANIM_GUN = 9
#: Template subrecords a copy leaves out: scripts, armor's resistances, naming rules (they add words to FNV's name).
DROPPED = (b'VMAD', b'DAMA', b'INRD')
#: A piece on FNV's own mesh drops the template's model data (an armor's female world model too) and mod templates.
OWN_MODEL_DROPPED = (b'MODT', b'MO2T', b'MO2S', b'MOD4', b'MO4T', b'MO4S', b'MO4C', b'MO4F')
TEMPLATES = (b'OBTE', b'STOP')
#: Armor addon subrecords copied from the template's: race, priorities, additional races.
ADDON_KEPT = (b'RNAM', b'DNAM')
#: Unlisted FNV armor -> (BMDT biped bits it covers, Fallout4.esm template FNV's mesh goes on), first match.
ARMOR_DEFAULTS = ((0x4, 'ClothesPrewarShortSleeves'), (0x1 | 0x200 | 0x400, 'ClothesMobsterhat'),
                  (0x800, 'ClothesEyeGlasses'), (0x4000 | 0x10000, 'Clothes_Raider_SurgicalMask'))
#: Unlisted FNV melee weapon by animation type -> entry: hand to hand on FO4's knuckles, one- and two-handed on FNV's mesh.
MELEE_DEFAULTS = {0: Replacement(BASE, 'Knuckles', 'stats'), 1: Replacement(BASE, 'TireIron', 'fnv'),
                  2: Replacement(BASE, 'BaseballBat', 'fnv')}
SEXES = ('male', 'female')
#: FNV biped flag of the upper body (an outfit).
UPPER_BODY = 0x4
#: FO4 armor addon model subrecords: third person male, female; first person male, female.
THIRD_PERSON, FIRST_PERSON = (b'MOD2', b'MOD3'), (b'MOD4', b'MOD5')
#: FNV ARMO alternate textures: male worn, male world, female worn model.
FNV_MALE_SWAP, FNV_WORLD_SWAP, FNV_FEMALE_SWAP = b'MODS', b'MO2S', b'MO3S'
#: FO4 model subrecord -> the material swap subrecord after it.
SWAP_OF = {b'MOD2': b'MO2S', b'MOD3': b'MO3S', b'MOD4': b'MO4S', b'MOD5': b'MO5S'}
#: Localized subrecords: Fallout4.esm stores a string ID, a copy the text.
LOCALIZED = (b'FULL', b'DESC')
#: FNV ARMO DNAM: DR (int16, times DR_SCALE) at 0, DT (float) at DT_AT when it is that long.
DR_SCALE, DT_AT = 100, 4


def _edid(subs: list) -> str:
    """The EditorID in a subrecord list."""
    return dict(subs).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')


def _rigid(path) -> bool:
    """headgear.rigid(`path`), cached."""
    return cached('rigid', 'fo4_import.nif.headgear', (path.read_bytes(),), lambda: headgear.rigid(path))


def _default(rec: dict) -> 'Replacement | None':
    """An unlisted FNV armor's or melee weapon's default entry (ARMOR_DEFAULTS, MELEE_DEFAULTS); else None."""
    if rec.get('Signature') == 'WEAP':
        return MELEE_DEFAULTS.get(int(rec.get('DNAM.FalloutAnimType', -1)))
    covers = int(rec.get('BMDT.BipedFlags', 0)) if rec.get('Signature') == 'ARMO' else 0
    return next((Replacement(BASE, edid, 'fnv') for bits, edid in ARMOR_DEFAULTS if covers & bits), None)


def _bod2(slots: tuple) -> bytes:
    """BOD2: the FO4 biped slots (30 and up) as flag bits."""
    return struct.pack('<I', sum(1 << (slot - 30) for slot in slots))


def _alternates(body: bytes, sets: dict) -> list:
    """[(shape index, (diffuse, normal))] of an FNV alternate-texture subrecord, by texture set (`sets`)."""
    n, pos, out = struct.unpack_from('<I', body)[0], 4, []
    for _ in range(n):
        size = struct.unpack_from('<I', body, pos)[0]
        txst, index = struct.unpack_from('<Ii', body, pos + 4 + size)
        if txst in sets:
            out.append((index, sets[txst]))
        pos += 4 + size + 8
    return out


def _fnv_fields() -> dict:
    """{FNV FormID: fields the export drops}, read from FalloutNV.esm: a weapon's ammo (NAM0); an armor's
    value, weight (DATA), rating (DNAM: DT, else DR) and alternate textures. An ammo form list (FLST)
    gives its first entry."""
    raw = fnv_esm()
    lists = {rec.form_id: first_sub(rec.body, b'LNAM') for rec, _ in walk(raw, b'FLST')}
    sets = {rec.form_id: tuple((first_sub(rec.body, t) or b'').rstrip(b'\0').decode('cp1252')
                               for t in (b'TX00', b'TX01')) for rec, _ in walk(raw, b'TXST')}
    out = {}
    for rec, _ in walk(raw, b'WEAP', b'ARMO'):
        ammo, data, dnam = (first_sub(rec.body, t) for t in (b'NAM0', b'DATA', b'DNAM'))
        if rec.sig == b'WEAP' and ammo:
            fid = struct.unpack('<I', ammo)[0]
            out[rec.form_id] = {'ammo': struct.unpack('<I', lists[fid])[0] if lists.get(fid) else fid}
        elif rec.sig == b'ARMO' and data and dnam:
            value, _, weight = struct.unpack_from('<iif', data)
            dt = struct.unpack_from('<f', dnam, DT_AT)[0] if len(dnam) >= DT_AT + 4 else 0.0
            rating = dt or struct.unpack_from('<h', dnam)[0] / DR_SCALE
            out[rec.form_id] = {'value': value, 'weight': weight, 'rating': rating, 'alternates': {
                sig: _alternates(first_sub(rec.body, sig), sets) for sig in (FNV_MALE_SWAP, FNV_WORLD_SWAP,
                                                                           FNV_FEMALE_SWAP) if first_sub(rec.body, sig)}}
    return out


class Equipment:
    """FO4 weapons and armor, each written once through a cell builder (its items convert the ammunition)."""

    def __init__(self, builder):
        """Index the Fallout4.esm templates the table names, their strings and FNV's dropped fields."""
        self.builder, self.fnv, self.strings, self.table = builder, _fnv_fields(), strings.load(), builder.table
        self.fits, self.statics, self.poses, self.bodies, self.worn_paths = {}, {}, {}, {}, {}
        self.guns = Guns(builder, self.strings)
        wanted = {r.edid for r in self.table.values() if r.base and r.mode != 'item'} | {e for _, e in ARMOR_DEFAULTS} | {
            r.edid for r in MELEE_DEFAULTS.values()}
        self.vanilla, self.addons = {}, {}
        for rec, _ in walk(builder.fo4, b'WEAP', b'ARMO', b'ARMA'):
            subs = list(subrecords(rec.body))
            if rec.sig == b'ARMA':
                self.addons[rec.form_id] = subs
            elif _edid(subs) in wanted:
                self.vanilla[_edid(subs)] = subs

    def _entry(self, rec: dict):
        """FNV `rec`'s Fallout4.esm-copy entry (else its _default), or None."""
        entry = self.table.get(rec.get('EditorID')) or _default(rec)
        return entry if entry and entry.base and entry.mode != 'item' and entry.edid in self.vanilla else None

    def _template(self, rec: dict) -> 'dict | None':
        """{sig: body} of the Fallout4.esm record FNV `rec` is written on, or None."""
        entry = self._entry(rec)
        return dict(self.vanilla[entry.edid]) if entry else None

    def _copy(self, rec: dict, data: dict, templates: 'list | None' = None, drop: tuple = (),
              source: 'list | None' = None) -> list:
        """The template's subrecords (`source`, else its entry's) for FNV `rec`: EDID, the first FULL and
        `data` {sig: bytes} replaced (each once), the other localized strings as their text, `drop` left out;
        `templates` (subrecords) replaces its mod templates (OBTE ... STOP) when given."""
        named, skipping, used, out = False, False, set(), []
        for sig, body in source or self.vanilla[self._entry(rec).edid]:
            if templates is not None and sig in TEMPLATES:
                out += templates if sig == TEMPLATES[0] else []
                skipping = sig == TEMPLATES[0]
                continue
            if skipping or sig in DROPPED or sig in used or (sig in drop and sig not in data):
                continue
            if sig in data:
                used.add(sig)
                out.append((sig, data[sig]))
                swap = SWAP_OF.get(sig)
                if swap in data and swap not in used:
                    used.add(swap)
                    out.append((swap, data[swap]))
                continue
            if sig == b'EDID':
                body = f'FNV_{rec["EditorID"]}\0'.encode()
            elif sig == b'FULL' and not named:
                body, named = (rec.get('FULL', '') + '\0').encode(), True
            elif sig in LOCALIZED:
                body = self.strings.get(struct.unpack('<I', body)[0], b'') + b'\0'
            out.append((sig, body))
        return out

    def weap(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 weapon for FNV WEAP `rec` (FormID `fnv`) on its table entry's target (an `fnv` gun on the
        FO4 gun spike.gun_choice picks, when one matches); a gun the table leaves out is that FO4 gun itself, its
        chosen parts, FNV's stats; None without either."""
        entry = self._entry(rec)
        gun = int(rec.get('DNAM.FalloutAnimType', -1)) in GUN_TYPES and 'Model.MODL' in rec
        chosen = self.guns.choose(rec) if gun and (entry is None or entry.mode == 'fnv') else None
        if entry is None and chosen is None:
            return None
        source = chosen[1] if chosen else self.vanilla[entry.edid]
        template = dict(source)
        dnam = bytearray(template[b'DNAM'])
        struct.pack_into('<f', dnam, DNAM_WEIGHT, float(rec.get('DATA.Weight', 0.0)))
        struct.pack_into('<I', dnam, DNAM_VALUE, int(rec.get('DATA.Value', 0)))
        struct.pack_into('<H', dnam, DNAM_DAMAGE, int(rec.get('DATA.Damage', 0)))
        if dnam[DNAM_ANIM] == ANIM_GUN:
            struct.pack_into('<H', dnam, DNAM_CAPACITY, int(rec.get('DATA.ClipSize', 0)))
            ammo = self.fnv.get(fnv, {}).get('ammo')
            made = self.builder.items.item(ammo) if ammo else None
            if made is not None:
                struct.pack_into('<I', dnam, DNAM_AMMO, made)
        data = {b'DNAM': bytes(dnam)}
        if entry and entry.mode == 'fnv' and dnam[DNAM_ANIM] < ANIM_GUN and 'Model.MODL' in rec:
            data.update(self._own_model(rec['Model.MODL'], int(rec.get('DNAM.FalloutAnimType', -1))))
            return self._write('WEAP', fnv, self._copy(rec, data, [], OWN_MODEL_DROPPED))
        if chosen and entry is None:
            templates = self.guns.combination(source, chosen[0].includes)
        else:
            templates = (self.guns.templates(fnv, rec, chosen[0], source, chosen[2]) if chosen
                         else self.guns.with_mods(source, entry.mods) if entry.mods else None)
        return self._write('WEAP', fnv, self._copy(rec, data, templates, source=source))

    def _own_model(self, model: str, anim_type: int) -> dict:
        """{sig: body} pointing a weapon's world and first-person models (FNV uses one mesh) at FNV `model`,
        posed as FNV holds a weapon of `anim_type` (nif.weapon.held_pose)."""
        if anim_type not in self.poses:
            self.poses[anim_type] = weapon.held_pose(self.builder.export_dir, anim_type)
        path, bounds = self.builder.weapon_mesh(model, self.poses[anim_type])
        out = {b'MODL': (path + '\0').encode(), b'MOD4': (path + '\0').encode()}
        if bounds:
            out[b'OBND'] = struct.pack('<6h', *bounds)
        return out

    def armo(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 armor for FNV ARMO `rec` (FormID `fnv`); None without a substitute."""
        template, fields = self._template(rec), self.fnv.get(fnv)
        if template is None or fields is None:
            return None
        data = struct.pack('<if', fields['value'], fields['weight']) + template[b'DATA'][8:12]
        fnam = bytearray(template[b'FNAM'])
        struct.pack_into('<H', fnam, 0, round(fields['rating']))
        subs = {b'DATA': data, b'FNAM': bytes(fnam)}
        own = (self._headgear(fnv, rec, template) or self._outfit(fnv, rec, template)
               if self._entry(rec).mode == 'fnv' else None)
        subs.update(own or {})
        return self._write('ARMO', fnv, self._copy(rec, subs, [] if own else None, OWN_MODEL_DROPPED if own else ()))

    def _headgear(self, fnv: int, rec: dict, template: dict) -> 'dict | None':
        """{sig: body} putting FNV headgear `rec` on its own meshes and armor addon; None when it is not
        rigid headgear (nif.headgear)."""
        slots = headgear.slots(int(rec.get('BMDT.BipedFlags', 0)))
        worn, world = rec.get('Male.BipedModel.MODL'), rec.get('Male.WorldModel.MODL')
        meshes = self.builder.export_dir / 'meshes'
        if not (slots and worn and world and _rigid(meshes / worn.replace('\\', '/').lower())):
            return None
        models = {sig: self._worn(rec.get(f'{sex.title()}.BipedModel.MODL') or worn, sex, slots)
                  for sig, sex in zip(THIRD_PERSON, SEXES)}
        addon = self._addon(fnv, rec, struct.unpack('<I', template[b'MODL'])[0], _bod2(slots), models)
        return {b'BOD2': _bod2(slots), **self._world(world, addon)}

    def _world(self, world: str, addon: int) -> dict:
        """{sig: body} of an armor's FNV world model and its one addon."""
        path, bounds = self.builder.mesh(world)
        out = {b'MOD2': (path + '\0').encode(), b'INDX': bytes(2), b'MODL': struct.pack('<I', addon)}
        if bounds:
            out[b'OBND'] = struct.pack('<6h', *bounds)
        return out

    def _static(self, model: str) -> tuple:
        """(FO4 path under Meshes, NIF bytes) of FNV `model` converted as a static, once."""
        if model not in self.statics:
            path, _ = write_assets(self.builder.export_dir, model, self.builder.data_dir, animated=False)
            self.statics[model] = path, (self.builder.data_dir / 'Meshes' / path).read_bytes()
        return self.statics[model]

    def _worn(self, model: str, sex: str, slots: tuple) -> str:
        """The FO4 worn mesh of FNV headgear `model` fitted to `sex`'s head; its path under Meshes."""
        if sex not in self.fits:
            self.fits[sex] = headgear.head_fit(self.builder.export_dir, sex)
        path, static = self._static(model)
        out = path if sex == SEXES[0] else path[:-len('.nif')] + f'_{sex}.nif'
        (self.builder.data_dir / 'Meshes' / out).write_bytes(headgear.worn(static, self.fits[sex], slots))
        return out

    def _outfit(self, fnv: int, rec: dict, template: dict) -> 'dict | None':
        """{sig: body} putting FNV outfit `rec` (upper body, skinned) on its own meshes moved onto FO4's body
        and its own armor addon, with the template addon's slots; None when it is not one (nif.outfit)."""
        worn, world = rec.get('Male.BipedModel.MODL'), rec.get('Male.WorldModel.MODL')
        meshes = self.builder.export_dir / 'meshes'
        if not (int(rec.get('BMDT.BipedFlags', 0)) & UPPER_BODY and worn and world) or _rigid(
                meshes / worn.replace('\\', '/').lower()):
            return None
        models, swaps = {}, {}
        for sex, third, first, alternates in zip(SEXES, THIRD_PERSON, FIRST_PERSON, (FNV_MALE_SWAP, FNV_FEMALE_SWAP)):
            model = rec.get(f'{sex.title()}.BipedModel.MODL') or worn
            models[third], models[first] = self._body_worn(model, sex)
            swap = self._swap(fnv, rec, alternates, self._static(model)[1], model)
            if swap:
                swaps[SWAP_OF[third]] = swaps[SWAP_OF[first]] = swap
        vanilla = struct.unpack('<I', template[b'MODL'])[0]
        bod2 = dict(self.addons[vanilla])[b'BOD2']
        out = self._world(world, self._addon(fnv, rec, vanilla, bod2, models, swaps))
        swap = self._swap(fnv, rec, FNV_WORLD_SWAP, (self.builder.data_dir / 'Meshes' / out[b'MOD2'][:-1].decode(
            'cp1252')).read_bytes(), world)
        return {**out, SWAP_OF[b'MOD2']: struct.pack('<I', swap)} if swap else out

    def _swap(self, fnv: int, rec: dict, sig: bytes, static: bytes, model: str) -> 'int | None':
        """The MSWP (made once) putting FNV ARMO `rec`'s alternate textures `sig` on converted `model` (its
        static NIF `static`): each listed shape's material to a copy with the texture set's maps; None without."""
        alternates = self.fnv.get(fnv, {}).get('alternates', {}).get(sig)
        fnv_path = self.builder.export_dir / 'meshes' / model.replace('\\', '/').lower()
        materials = cached('shape_materials', 'fo4_import.nif.outfit', (static, fnv_path.read_bytes()),
                           lambda: outfit.shape_materials(static, fnv_path)) if alternates else {}
        pairs = sorted({(materials[i], swapped_material(self.builder.export_dir, self.builder.data_dir, materials[i],
                                                        textures)) for i, textures in alternates or () if i in materials})
        pairs = [(a[len('materials\\'):], b[len('materials\\'):]) for a, b in pairs if a != b]
        if not pairs:
            return None
        fid = self.builder.writer.derive_formid(SITES['MSWP'], f'{fnv:08X} {sig.decode()}')
        self.builder.writer.add_record('MSWP', R.pack_mswp(fid, f'FNV_MS_{rec["EditorID"]}_{sig.decode()}', pairs))
        self.builder.counts['MSWP'] += 1
        return fid

    def _body_worn(self, model: str, sex: str) -> tuple:
        """(third-, first-person path under Meshes) of FNV outfit `model` moved onto `sex`'s FO4 body."""
        if (model, sex) in self.worn_paths:
            return self.worn_paths[model, sex]
        path, static = self._static(model)
        stem = path[:-len('.nif')] + ('' if sex == SEXES[0] else f'_{sex}')
        fnv_path = self.builder.export_dir / 'meshes' / model.replace('\\', '/').lower()
        out = []
        for name, first in ((f'{stem}.nif', False), (f'{stem}_1stperson.nif', True)):
            (self.builder.data_dir / 'Meshes' / name).write_bytes(cached(
                'outfit_worn', 'fo4_import.nif.outfit', (static, fnv_path.read_bytes(), sex, first),
                lambda: outfit.worn(static, fnv_path, self._body(sex), first)))
            out.append(name)
        self.worn_paths[model, sex] = tuple(out)
        return self.worn_paths[model, sex]

    def _body(self, sex: str):
        """outfit.body_fit() of `sex`, made once."""
        if sex not in self.bodies:
            self.bodies[sex] = outfit.body_fit(self.builder.export_dir, sex)
        return self.bodies[sex]

    def _addon(self, fnv: int, rec: dict, template: int, bod2: bytes, models: dict, swaps: dict = None) -> int:
        """An armor addon for FNV `rec` on `models` {MOD2..MOD5: path} and their material `swaps`
        {MO2S..MO5S: MSWP}, with `bod2` and the template addon's races."""
        vanilla = self.addons[template]
        subs = [(b'EDID', f'FNV_AA_{rec["EditorID"]}\0'.encode()), (b'BOD2', bod2)]
        subs += [(sig, body) for sig, body in vanilla if sig in ADDON_KEPT]
        for sig in (s for s in THIRD_PERSON + FIRST_PERSON if s in models):
            subs.append((sig, (models[sig] + '\0').encode()))
            if SWAP_OF[sig] in (swaps or {}):
                subs.append((SWAP_OF[sig], struct.pack('<I', swaps[SWAP_OF[sig]])))
        subs += [(sig, body) for sig, body in vanilla if sig == b'MODL']
        return self._write('ARMA', fnv, subs)

    def test_items(self, rounds: int) -> list:
        """[(FO4 FormID, count)]: every weapon and armor the table names, made now, and `rounds` of each gun's ammo."""
        out, items = [], self.builder.items
        for edid in self.table:
            fnv = items.names.get(edid.lower())
            kind = items.records.get(fnv, ('',))[0] if fnv is not None else ''
            made = items.item(fnv) if kind in ('WEAP', 'ARMO') else None
            if made is None:
                continue
            ammo = self.fnv.get(fnv, {}).get('ammo')
            out += [(made, 1)] + ([(items.item(ammo), rounds)] if ammo and items.item(ammo) else [])
        return out

    def _write(self, sig: str, fnv: int, subs: list) -> int:
        """Add a `sig` record of `subs` on its hashed FormID; the FormID."""
        fid = self.builder.writer.derive_formid(SITES[sig], fnv)
        body = b''.join(pack_subrecord(s.decode(), b) for s, b in subs)
        self.builder.writer.add_record(sig, pack_fo4_record(sig, fid, 0, body))
        self.builder.counts[sig] += 1
        return fid
