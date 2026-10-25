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
its head's frame or skins to its head bone (nif.headgear; a worn mesh of its
own per slots), through its own armor addon (ARMA) with FNV's slots and the
template addon's races, and an FNV outfit (a skinned upper-body mesh) moved
onto FO4's body (nif.outfit), through its own addon with the template
addon's slots and races and FNV's sleeves in first person; FNV's alternate
textures, which tell variants apart on one mesh, become material swaps
(MSWP) on its models. A piece FNV gives no world model keeps the template's;
one no FNV-mesh path takes keeps all its models, both counted. Armor takes the protection FNV
gives it as its armor rating, unscaled: DT (all FNV armor), else DR (FO3's),
and drops the template's resistances. Condition and the template's scripts
are dropped; the piece carries FNV's own script instead (a faction outfit's
equip events). An FNV piece the table does not name is skipped and counted.
FormIDs are hashed from FNV's (SITES), so no other record's id moves.

See: docs/fork/fo4_spikes.md#spike-4-equipment
See: docs/fork/fo4_spikes.md#spike-4-melee
See: docs/fork/fo4_spikes.md#spike-4-headgear
See: docs/fork/fo4_spikes.md#spike-4-outfits
"""

import struct
from pathlib import Path

from fo4_import.spike.type_tests import with_keywords
from fo4_import.spike.ammo_mods import AmmoMods
from fo4_import.spike.condition import Condition
from fo4_import.base import strings
from fo4_import.base.install import source_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif import headgear, outfit, weapon
from fo4_import.pipeline.elric_cache import mesh_bytes, write_new
from fo4_import.pipeline.work_cache import cached
from fo4_import.spike.gun_choice import GUN_TYPES
from fo4_import.spike.guns import Guns
from fo4_import.spike.weapon_mods import WeaponMods
from fo4_import.spike.replacements import Replacement, Rules
from fo4_import.spike import records as R
from fo4_import.spike.statics import swapped_material, write_assets
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord
from tes5_import.record_types.equipment_falloutnv import WEAPON_ANIM_LISTS

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
#: An armor's world model data and swap, kept with the template's world model when FNV has none.
WORLD_MODEL_DATA = (b'MO2T', b'MO2S')
TEMPLATES = (b'OBTE', b'STOP')
#: Armor addon subrecords copied from the template's: race, priorities, additional races.
ADDON_KEPT = (b'RNAM', b'DNAM')
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


def default_entry(rec: dict, rules: Rules) -> 'Replacement | None':
    """An unlisted FNV armor's or melee weapon's entry from the table's `rules` (armor, melee); else None."""
    if rec.get('Signature') == 'WEAP':
        return rules.melee.get(int(rec.get('DNAM.FalloutAnimType', -1)))
    covers = int(rec.get('BMDT.BipedFlags', 0)) if rec.get('Signature') == 'ARMO' else 0
    return next((entry for bits, entry in rules.armor if covers & bits), None)


def _sex_suffix(sex: str) -> str:
    """A worn mesh's file name suffix for `sex`: none for male."""
    return '' if sex == SEXES[0] else f'_{sex}'


def _on_template(rec: dict) -> str:
    """Why no FNV-mesh path takes FNV armor `rec`: no worn model, headgear not drawn on the head, a rigid upper
    body, or slots neither headgear nor upper body."""
    flags = int(rec.get('BMDT.BipedFlags', 0))
    if not rec.get('Male.BipedModel.MODL'):
        return 'no FNV worn model'
    if headgear.slots(flags):
        return 'headgear not on the head'
    return 'rigid upper body' if flags & UPPER_BODY else 'other slots'


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
    value, health, weight (DATA), rating (DNAM: DT, else DR) and alternate textures. An ammo form list (FLST)
    gives its first entry."""
    raw = source_esm()
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
            value, health, weight = struct.unpack_from('<iif', data)
            dt = struct.unpack_from('<f', dnam, DT_AT)[0] if len(dnam) >= DT_AT + 4 else 0.0
            rating = dt or struct.unpack_from('<h', dnam)[0] / DR_SCALE
            out[rec.form_id] = {'value': value, 'weight': weight, 'rating': rating, 'health': health,
                                'alternates': {sig: _alternates(first_sub(rec.body, sig), sets)
                                               for sig in (FNV_MALE_SWAP, FNV_WORLD_SWAP, FNV_FEMALE_SWAP)
                                               if first_sub(rec.body, sig)}}
    return out


class Equipment:
    """FO4 weapons and armor, each written once through a cell builder (its items convert the ammunition)."""

    def __init__(self, builder):
        """Index the Fallout4.esm templates the table names, their strings and FNV's dropped fields."""
        self.builder, self.fnv, self.strings, self.table = builder, _fnv_fields(), strings.load(), builder.table
        self.fits, self.statics, self.poses, self.bodies, self.worn_paths = {}, {}, {}, {}, {}
        self.guns = Guns(builder, self.strings)
        self.weapon_mods = WeaponMods(builder, self.guns.mods)
        self.by_anim = {kind: set() for kind in WEAPON_ANIM_LISTS}
        rules = self.table.rules
        wanted = {r.edid for r in [*self.table.values(), *(e for _, e in rules.armor), *rules.melee.values()]
                  if r.base and r.mode != 'item'}
        self.vanilla, self.addons = {}, {}
        for rec, _ in walk(builder.fo4, b'WEAP', b'ARMO', b'ARMA'):
            subs = list(subrecords(rec.body))
            if rec.sig == b'ARMA':
                self.addons[rec.form_id] = subs
            elif _edid(subs) in wanted:
                self.vanilla[_edid(subs)] = subs
        self.ammo_mods, self.condition = AmmoMods(builder), Condition(builder)

    def _entry(self, rec: dict):
        """FNV `rec`'s Fallout4.esm-copy entry (else its _default), or None."""
        entry = self.table.get(rec.get('EditorID')) or default_entry(rec, self.table.rules)
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
                out += [(sig, f'FNV_{rec["EditorID"]}\0'.encode())] + self._script(rec)
                continue
            if sig == b'FULL' and not named:
                body, named = (rec.get('FULL', '') + '\0').encode(), True
            elif sig in LOCALIZED:
                body = self.strings.get(struct.unpack('<I', body)[0], b'') + b'\0'
            out.append((sig, body))
        return out

    def _script(self, rec: dict) -> list:
        """[(VMAD, FNV `rec`'s converted script attached and filled)]; [] without one.
        See: docs/fork/fo4_pipeline.md#disguises
        """
        vmad = self.builder.scripts.vmad(int(rec['SCRI'], 16)) if rec.get('SCRI') else b''
        return [(b'VMAD', vmad)] if vmad else []

    def weap(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 weapon for FNV WEAP `rec` (_weapon), listed under its FNV animation type (anim_lists)."""
        fid = self._weapon(fnv, rec)
        if fid is not None and int(rec.get('DNAM.FalloutAnimType', -1)) in self.by_anim:
            self.by_anim[int(rec['DNAM.FalloutAnimType'])].add(fid)
        return fid

    def anim_list(self, name: str) -> 'int | None':
        """Weapon list `name`'s FormID (WEAPON_ANIM_LISTS); None for another name."""
        return self.builder.writer.derive_formid('FLST', name) if name in WEAPON_ANIM_LISTS.values() else None

    def write_anim_lists(self) -> None:
        """Write every animation type's list of the converted weapons, empty or not, so a property always binds.
        See: docs/commentary/script_convert.md#fallout-weapon-anim-type
        """
        for kind, name in WEAPON_ANIM_LISTS.items():
            body = pack_string_subrecord('EDID', name) + b''.join(
                pack_subrecord('LNAM', struct.pack('<I', fid)) for fid in sorted(self.by_anim[kind]))
            self.builder.writer.add_record('FLST', pack_fo4_record('FLST', self.anim_list(name), 0, body))

    def _weapon(self, fnv: int, rec: dict) -> 'int | None':
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
        data, marks = {b'DNAM': bytes(dnam)}, self.builder.type_keywords.of(fnv)
        if entry and entry.mode == 'fnv' and dnam[DNAM_ANIM] < ANIM_GUN and 'Model.MODL' in rec:
            data.update(self._own_model(rec['Model.MODL'], int(rec.get('DNAM.FalloutAnimType', -1))))
            return self._write('WEAP', fnv, with_keywords(self._copy(rec, data, [], OWN_MODEL_DROPPED), marks))
        if chosen and entry is None:
            templates = self.guns.combination(source, chosen[0].includes)
        else:
            templates = (self.guns.templates(fnv, rec, chosen[0], source, chosen[2]) if chosen
                         else self.guns.with_mods(source, entry.mods) if entry.mods
                         else self.guns.default_only(source))
        copy = self.weapon_mods.wire(fnv, self._copy(rec, data, templates, source=source))
        return self._write('WEAP', fnv, with_keywords(copy, marks))

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
        """The FO4 armor for FNV ARMO `rec` (FormID `fnv`); None without a substitute. One no FNV-mesh path takes
        keeps the template's models, counted by why (_on_template)."""
        template, fields = self._template(rec), self.fnv.get(fnv)
        if template is None or fields is None:
            return None
        data = struct.pack('<ifI', fields['value'], fields['weight'], max(fields.get('health', 0), 0))
        fnam = bytearray(template[b'FNAM'])
        struct.pack_into('<H', fnam, 0, round(fields['rating']))
        subs = {b'DATA': data, b'FNAM': bytes(fnam)}
        own = (self._headgear(fnv, rec, template) or self._outfit(fnv, rec, template)
               if self._entry(rec).mode == 'fnv' else None)
        if own is None and self._entry(rec).mode == 'fnv':
            self.builder.counts[f"ARMO on the template's models ({_on_template(rec)})"] += 1
        subs.update(own or {})
        dropped = tuple(s for s in OWN_MODEL_DROPPED if b'MOD2' in subs or s not in WORLD_MODEL_DATA) if own else ()
        return self._write('ARMO', fnv, self._copy(rec, subs, [] if own else None, dropped))

    def _fnv_path(self, model: str) -> Path:
        """FNV model `model`'s file in the export."""
        return self.builder.export_dir / 'meshes' / model.replace('\\', '/').lower()

    def _on_head(self, model: str, sex: str) -> tuple:
        """(whether FNV headgear `model` is drawn on `sex`'s head: rigid, or skinned to its head bone; the
        matrix moving a skinned one into the head's frame: headgear.head_frame)."""
        path = self._fnv_path(model)
        if _rigid(path):
            return True, None
        head = self._fnv_path(headgear.FNV_HEADS[sex])
        frame = cached('head_frame', 'fo4_import.nif.headgear', (path.read_bytes(), head.read_bytes()),
                       lambda: headgear.head_frame(path, head))
        return frame is not None, frame

    def _headgear(self, fnv: int, rec: dict, template: dict) -> 'dict | None':
        """{sig: body} putting FNV headgear `rec` on its own meshes (with its alternate textures) and armor addon;
        None when it is not headgear drawn on the head (_on_head)."""
        slots = headgear.slots(int(rec.get('BMDT.BipedFlags', 0)))
        worn = rec.get('Male.BipedModel.MODL')
        models = {sex: rec.get(f'{sex.title()}.BipedModel.MODL') or worn for sex in SEXES}
        heads = {sex: self._on_head(model, sex) for sex, model in models.items()} if slots and worn else {}
        if not heads or not all(on for on, _ in heads.values()):
            return None
        paths = {sig: self._worn(models[sex], sex, slots, heads[sex][1]) for sig, sex in zip(THIRD_PERSON, SEXES)}
        swaps = {SWAP_OF[sig]: swap for sig, swap in zip(THIRD_PERSON, self._worn_swaps(fnv, rec, models)) if swap}
        addon = self._addon(fnv, rec, struct.unpack('<I', template[b'MODL'])[0], _bod2(slots), paths, swaps)
        return {b'BOD2': _bod2(slots), **self._world(fnv, rec, addon)}

    def _worn_swaps(self, fnv: int, rec: dict, models: dict) -> list:
        """Per sex, _swap() of `rec`'s worn alternates on `models` {sex: FNV model}."""
        return [self._swap(fnv, rec, sig, self._static(models[sex])[1], models[sex])
                for sex, sig in zip(SEXES, (FNV_MALE_SWAP, FNV_FEMALE_SWAP))]

    def _world(self, fnv: int, rec: dict, addon: int) -> dict:
        """{sig: body} of FNV ARMO `rec`'s one addon and its world model with its alternate textures; without an
        FNV world model the template's stays (counted)."""
        world = rec.get('Male.WorldModel.MODL')
        out = {b'INDX': bytes(2), b'MODL': struct.pack('<I', addon)}
        if not world:
            self.builder.counts["ARMO on the template's world model (FNV has none)"] += 1
            return out
        path, bounds = self.builder.mesh(world)
        out[b'MOD2'] = (path + '\0').encode()
        if bounds:
            out[b'OBND'] = struct.pack('<6h', *bounds)
        swap = self._swap(fnv, rec, FNV_WORLD_SWAP, mesh_bytes(self.builder.data_dir / 'Meshes' / path), world)
        return {**out, SWAP_OF[b'MOD2']: struct.pack('<I', swap)} if swap else out

    def _static(self, model: str) -> tuple:
        """(FO4 path under Meshes, NIF bytes) of FNV `model` converted as a static, once."""
        if model not in self.statics:
            path, _ = write_assets(self.builder.export_dir, model, self.builder.data_dir, animated=False)
            self.statics[model] = path, mesh_bytes(self.builder.data_dir / 'Meshes' / path)
        return self.statics[model]

    def _worn(self, model: str, sex: str, slots: tuple, frame) -> str:
        """The FO4 worn mesh of FNV headgear `model` in `slots` fitted to `sex`'s head (moved by `frame` when
        skinned: _on_head), made once as `<static>_worn_<slots>[_female].nif`, apart from the static; its path
        under Meshes.
        See: docs/fork/fo4_tool_audit.md#meshes
        """
        if (model, sex, slots) not in self.worn_paths:
            if sex not in self.fits:
                self.fits[sex] = headgear.head_fit(self.builder.export_dir, sex)
            path, static = self._static(model)
            out = f'{path[:-len(".nif")]}_worn{"".join(f"_{s}" for s in slots)}{_sex_suffix(sex)}.nif'
            write_new(self.builder.data_dir / 'Meshes' / out, headgear.worn(static, self.fits[sex], slots, frame))
            self.worn_paths[model, sex, slots] = out
        return self.worn_paths[model, sex, slots]

    def _outfit(self, fnv: int, rec: dict, template: dict) -> 'dict | None':
        """{sig: body} putting FNV outfit `rec` (upper body, skinned) on its own meshes moved onto FO4's body
        and its own armor addon, with the template addon's slots; None when it is not one (nif.outfit)."""
        worn = rec.get('Male.BipedModel.MODL')
        if not (int(rec.get('BMDT.BipedFlags', 0)) & UPPER_BODY and worn) or _rigid(self._fnv_path(worn)):
            return None
        models, sexes = {}, {sex: rec.get(f'{sex.title()}.BipedModel.MODL') or worn for sex in SEXES}
        for sex, third, first in zip(SEXES, THIRD_PERSON, FIRST_PERSON):
            models[third], models[first] = self._body_worn(sexes[sex], sex)
        swaps = {SWAP_OF[sig]: swap for third, first, swap in zip(THIRD_PERSON, FIRST_PERSON,
                                                                   self._worn_swaps(fnv, rec, sexes))
                 for sig in (third, first) if swap}
        vanilla = struct.unpack('<I', template[b'MODL'])[0]
        bod2 = dict(self.addons[vanilla])[b'BOD2']
        return self._world(fnv, rec, self._addon(fnv, rec, vanilla, bod2, models, swaps))

    def _swap(self, fnv: int, rec: dict, sig: bytes, static: bytes, model: str) -> 'int | None':
        """The MSWP (made once) putting FNV ARMO `rec`'s alternate textures `sig` on converted `model` (its
        static NIF `static`): each listed shape's material to a copy with the texture set's maps; None without."""
        alternates = self.fnv.get(fnv, {}).get('alternates', {}).get(sig)
        fnv_path = self._fnv_path(model)
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
        stem = path[:-len('.nif')] + _sex_suffix(sex)
        fnv_path = self._fnv_path(model)
        out = []
        for name, first in ((f'{stem}.nif', False), (f'{stem}_1stperson.nif', True)):
            write_new(self.builder.data_dir / 'Meshes' / name, cached(
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
        return out + self.weapon_mods.test_items()

    def _write(self, sig: str, fnv: int, subs: list) -> int:
        """Add a `sig` record of `subs` on its hashed FormID; the FormID."""
        fid = self.builder.writer.derive_formid(SITES[sig], fnv)
        if sig == 'WEAP':
            subs = self.condition.wire(fnv, fid, self.ammo_mods.wire(fnv, subs))
        elif sig == 'ARMO':
            subs = self.condition.wire_armor(fnv, fid, subs, self.fnv.get(fnv, {}))
        body = b''.join(pack_subrecord(s.decode(), b) for s, b in subs)
        self.builder.writer.add_record(sig, pack_fo4_record(sig, fid, 0, body))
        self.builder.counts[sig] += 1
        return fid
