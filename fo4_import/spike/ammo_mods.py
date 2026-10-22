"""FNV ammunition subtypes as Fallout 4 ammo object mods, carrying FNV's ammo effects (AMEF).

FNV lets a gun load any ammo of its list (WEAP NAM0, a FLST). Fallout 4's
own way to change a gun's ammo is an object mod setting its Ammo, crafted at
the weapons workbench: all 11 of Fallout4.esm's (the Alien Blaster's
AmmoStandard and AmmoConversion at ap_gun_Mag, the .38 receivers). So every
ammo list a converted gun loads, with two or more ammo that convert, becomes
one mod per ammo at our own attach point (POINT_EDID), targeting the list's
own mod-association keyword, which each gun loading the list carries; the
gun's default combination includes its first ammo's mod, as the Alien
Blaster's includes AmmoStandard. A recipe is free (no components, no bench),
as 69 of Fallout4.esm's mod recipes are.
Each mod also adds its round's keyword (mark), so the Ammo Type hotkey
(ammo_switch) can tell which round a gun holds.

A mod carries the ammo's effects as properties: damage on AttackDamage,
spread on both aim cones, a projectile count on NumProjectiles, and DT on
the target's damage resistance the way vanilla's armor-piercing receivers
do it: the mod adds an enchantment applying a perk (Mod Target Damage
Resistance) and a weapon actor value the perk reads. DT subtracted comes off
flat (converted armor rates FNV's DT unscaled); DT multiplied scales it.
Condition and fatigue have no Fallout 4 counterpart and are counted.

See: docs/fork/fo4_pipeline.md#nv-ammo
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.gun_choice import INCLUDE_SIZE, OBTS_DEFAULT, includes_at
from fo4_import.spike.perks import ENTRY_POINT, PERK_DATA, pack_effect, pack_perk
from fo4_import.spike.type_tests import with_keywords
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: derive_formid sites (keys: FNV list FormID; list and ammo FormIDs; shared records' EditorIDs; FNV ammo FormID).
KEYWORD_SITE, MOD_SITE, RECIPE_SITE, SHARED_SITE, LOADED_SITE = (
    'FNV ammo list keyword', 'FNV ammo mod', 'FNV ammo mod recipe', 'FNV ammo shared', 'FNV ammo loaded keyword')
#: Our attach point (its workbench name) and the keyword types: attach point, mod association.
POINT_EDID, POINT_NAME, ATTACH_POINT, MOD_ASSOCIATION = 'FNV_ap_Ammo', 'Ammo', 2, 5
#: FNV AMEF DATA types and operations (xEdit's FNV AMEF).
DAMAGE, DR, DT, SPREAD, CONDITION, FATIGUE = range(6)
ADD_OP, MULTIPLY_OP, SUBTRACT_OP = range(3)
TYPE_NAMES = ('damage', 'DR', 'DT', 'spread', 'condition', 'fatigue')
#: OMOD property value types, functions and properties (xEdit's wbObjectModProperties, wbWeaponPropertyEnum).
INT, FLOAT, FORM, FORM_FLOAT = 0, 1, 4, 6
SET, MUL_ADD, ADD = 0, 1, 2
ATTACK_DAMAGE, KEYWORDS, MIN_CONE, MAX_CONE, NUM_PROJECTILES, AMMO, ENCHANTMENTS, ACTOR_VALUES = (28, 31, 33, 34, 51,
                                                                                               61, 65, 94)
PROPERTY = struct.Struct('<B3xB3xH2x4s4sf')
#: Vanilla's second value on an Ammo SET (11 of 11), Enchantments ADD (150 of 151), Keywords ADD (2,253 of 2,295).
FORM_VALUE2 = 440
#: OMOD DATA head: include and property counts, two bools, form type, rank, tier, attach point.
OMOD_HEAD = struct.Struct('<II2x4s2xI')
#: Fallout4.esm's armor-piercing records the DT records copy (actor value, perk effect, enchantment).
PENETRATION = {b'AVIF': 'ArmorPenetration', b'MGEF': 'ModArmorPenetrationAddPerkEffect',
               b'ENCH': 'enchModArmorPenetration'}
#: Entry point Mod Target Damage Resistance, functions Add / Multiply 1 + AV Mult, EPFT, tabs (ModArmorPenetrationPerk).
TARGET_RESISTANCE, ADD_AV_MULT, MULTIPLY_AV_MULT, AV_PARAM, RESISTANCE_TABS = 37, 5, 14, 8, 3
#: The DT records: actor values (DT taken off, DT multiplier less one), their perk and its effect and enchantment.
DT_OFF, DT_MULT = 'FNV_AmmoDTReduction', 'FNV_AmmoDTMultiplier'
DT_PERK, DT_EFFECT, DT_ENCH = 'FNV_AmmoDTPerk', 'FNV_AmmoDTPerkEffect', 'FNV_enchAmmoDT'
#: MGEF DATA offset of its Perk to Apply (xEdit's FO4 MGEF DATA).
PERK_TO_APPLY = 136
LOCALIZED = (b'FULL', b'DESC')


def prop(vtype: int, func: int, which: int, value1: bytes, value2: bytes = bytes(4)) -> bytes:
    """One 24-byte OMOD property."""
    return PROPERTY.pack(vtype, func, which, value1, value2, 0.0)


def scaled(which: int, op: int, value: float) -> bytes:
    """Float property `which` by FNV's `op` and `value`; multiply: MUL+ADD v-1."""
    if op == MULTIPLY_OP:
        return prop(FLOAT, MUL_ADD, which, struct.pack('<f', value - 1.0))
    return prop(FLOAT, ADD, which, struct.pack('<f', -value if op == SUBTRACT_OP else value))


def omod_data(point: int, props: list) -> bytes:
    """A weapon OMOD DATA at attach point `point`, `props` sorted."""
    ordered = sorted(props, key=lambda p: struct.unpack_from('<H', p, 8)[0])
    return OMOD_HEAD.pack(0, len(ordered), b'WEAP', point) + bytes(8) + b''.join(ordered)


def with_point(subs: list, point: int) -> list:
    """Gun `subs` offering attach point `point` (APPR), added before its object template when it has no APPR."""
    if any(t == b'APPR' for t, _ in subs):
        return [(t, d + struct.pack('<I', point) if t == b'APPR' and struct.pack('<I', point) not in d else d)
                for t, d in subs]
    at = next((i for i, (t, _) in enumerate(subs) if t == b'OBTE'), len(subs))
    return subs[:at] + [(b'APPR', struct.pack('<I', point))] + subs[at:]


def with_default(subs: list, mod: int) -> list:
    """Gun `subs` whose default combination (OBTS) also includes `mod`."""
    out = []
    for tag, body in subs:
        if tag == b'OBTS' and body[OBTS_DEFAULT]:
            count = struct.unpack_from('<I', body)[0]
            end = includes_at(body) + INCLUDE_SIZE * count
            body = struct.pack('<I', count + 1) + body[4:end] + struct.pack('<IBBB', mod, 0, 0, 1) + body[end:]
        out.append((tag, body))
    return out


class AmmoMods:
    """Ammo mods for the build's converted guns, each list's written once; `loaded` names every gun's ammo."""

    def __init__(self, builder):
        """Index the export's ammo lists, ammo and ammo effects."""
        export_dir = builder.export_dir
        self.builder, self.point, self.dt = builder, None, None
        self.lists = {int(r['FormID'], 16): r for r in export_records(export_dir, 'FLST')}
        self.ammo = {int(r['FormID'], 16): r for r in export_records(export_dir, 'AMMO')}
        self.effects = {int(r['FormID'], 16): r for r in export_records(export_dir, 'AMEF')}
        self.made, self.loaded, self.marks = {}, {}, {}

    def wire(self, fnv: int, subs: list) -> list:
        """Converted gun `subs` (FNV WEAP `fnv`) loading every converted ammo of its FNV list: the list's keyword and
        our attach point added, its first ammo's mod in its default combination; unchanged for a single ammo."""
        rec = self.builder.items.records.get(fnv, (None, {}))[1]
        source = int(rec.get('NAM0', '0'), 16)
        ammo = members(self.lists[source]) if source in self.lists else [source] if source in self.ammo else []
        if ammo:
            self.loaded.setdefault(ammo[0], {})[fnv] = ammo
        if source not in self.lists or not any(t == b'OBTS' for t, _ in subs):
            return subs
        keyword, mods = self._list_mods(source, ammo)
        if len(mods) < 2:
            return subs
        subs = with_point(with_keywords(subs, [keyword]), self._point())
        return with_default(subs, mods[0][1]) if mods[0][0] == ammo[0] else subs

    def test_items(self, rounds: int) -> list:
        """[(FO4 FormID, count)]: `rounds` of every ammo a wired gun loads but its first."""
        return [(self.builder.items.item(a), rounds) for _, mods in self.made.values() for a, _ in mods[1:]]

    def _list_mods(self, source: int, ammo: list) -> tuple:
        """(keyword, [(FNV ammo, its mod)]) of FNV list `source` (`ammo` its entries), written once; no mods with
        fewer than two converted ammo."""
        if source not in self.made:
            converted = [a for a in ammo if a in self.ammo and self.builder.items.item(a) is not None]
            if len(converted) < 2:
                self.made[source] = (None, [])
            else:
                edid = self.lists[source]['EditorID']
                keyword = self._keyword(KEYWORD_SITE, f'{source:08X}', f'FNV_ma_{edid}', MOD_ASSOCIATION)
                self.made[source] = (keyword, [(a, self._mod(source, a, keyword)) for a in converted])
        return self.made[source]

    def mark(self, ammo: int) -> int:
        """The keyword FNV ammo `ammo`'s mods add to a gun, telling a script which round it holds; written once.
        See: docs/fork/fo4_pipeline.md#ammo-switch
        """
        if ammo not in self.marks:
            edid = f'FNV_AmmoLoaded_{self.ammo[ammo]["EditorID"]}'
            self.marks[ammo] = self._keyword(LOADED_SITE, f'{ammo:08X}', edid, 0)
        return self.marks[ammo]

    def _point(self) -> int:
        """Our ammo attach point keyword, written once."""
        if self.point is None:
            self.point = self._keyword(SHARED_SITE, POINT_EDID, POINT_EDID, ATTACH_POINT, POINT_NAME)
        return self.point

    def _keyword(self, site: str, key: str, edid: str, kind: int, name: str = '') -> int:
        """A keyword of type `kind`, written now."""
        fid = self.builder.writer.derive_formid(site, key)
        self.builder.writer.add_record('KYWD', R.pack_kywd(fid, edid, kind, name))
        return fid

    def _mod(self, source: int, ammo: int, keyword: int) -> int:
        """FNV ammo `ammo` of list `source` as an OMOD setting the gun's ammo, with its effects, and its free recipe."""
        rec, key = self.ammo[ammo], f'{source:08X} {ammo:08X}'
        props, notes = self._effects(rec)
        props.append(prop(FORM, SET, AMMO, struct.pack('<I', self.builder.items.item(ammo)),
                          struct.pack('<I', FORM_VALUE2)))
        props.append(prop(FORM, ADD, KEYWORDS, struct.pack('<I', self.mark(ammo)), struct.pack('<I', FORM_VALUE2)))
        fid = self.builder.writer.derive_formid(MOD_SITE, key)
        edid = f'FNV_mod_{self.lists[source]["EditorID"]}_{rec["EditorID"]}'
        subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', rec.get('FULL', ''))
        subs += pack_string_subrecord('DESC', ', '.join(notes)) + pack_subrecord('DATA', omod_data(self._point(), props))
        self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', fid, 0, subs + R.pack_u32('MNAM', keyword)))
        recipe = pack_string_subrecord('EDID', f'FNV_co_{edid[len("FNV_"):]}') + R.pack_u32('CNAM', fid)
        self.builder.writer.add_record('COBJ', pack_fo4_record('COBJ', self.builder.writer.derive_formid(
            RECIPE_SITE, key), 0, recipe + pack_subrecord('INTV', struct.pack('<HH', 1, 0))))
        self.builder.counts['ammo mods'] += 1
        return fid

    def _effects(self, rec: dict) -> tuple:
        """([OMOD property], [effect note]) of FNV ammo `rec`: its projectile count and effects; one Fallout 4
        lacks is counted."""
        props, notes, i = [], [], 0
        count = int(rec.get('DAT2.ProjPerShot', 0))
        if count:
            props.append(prop(INT, SET, NUM_PROJECTILES, struct.pack('<I', count)))
        while f'RCIL[{i}]' in rec:
            effect = self.effects.get(int(rec[f'RCIL[{i}]'], 16), {})
            kind, op, value = (int(effect.get('DATA.Type', -1)), int(effect.get('DATA.Operation', 0)),
                               float(effect.get('DATA.Value', 0.0)))
            made = self._effect(kind, op, value)
            if made:
                props += made
                notes.append(f'{effect.get("FULL", "")} {"x" if op == MULTIPLY_OP else "-" if op == SUBTRACT_OP else "+"}'
                             f'{value:g}')
            else:
                self.builder.counts[f'ammo effect left out ({TYPE_NAMES[kind] if 0 <= kind < 6 else kind})'] += 1
            i += 1
        if any(struct.unpack_from('<H', p, 8)[0] == ACTOR_VALUES for p in props):
            props.append(prop(FORM, ADD, ENCHANTMENTS, struct.pack('<I', self._dt()[DT_ENCH]),
                              struct.pack('<I', FORM_VALUE2)))
        return props, notes

    def _effect(self, kind: int, op: int, value: float) -> list:
        """The OMOD properties of one FNV ammo effect; [] for one Fallout 4 lacks."""
        if kind == DAMAGE:
            return [scaled(ATTACK_DAMAGE, op, value)]
        if kind == SPREAD:
            return [scaled(MIN_CONE, op, value), scaled(MAX_CONE, op, value)]
        if kind != DT:
            return []
        av, amount = ((DT_MULT, value - 1.0) if op == MULTIPLY_OP else
                      (DT_OFF, value if op == SUBTRACT_OP else -value))
        return [prop(FORM_FLOAT, ADD, ACTOR_VALUES, struct.pack('<I', self._dt()[av]), struct.pack('<f', amount))]

    def _dt(self) -> dict:
        """{EditorID: FormID} of the DT records (DT_*), copies of Fallout4.esm's armor-piercing ones, written once."""
        if self.dt is None:
            ids = {e: self.builder.writer.derive_formid(SHARED_SITE, e) for e in (DT_OFF, DT_MULT, DT_PERK,
                                                                                  DT_EFFECT, DT_ENCH)}
            vanilla = _vanilla(self.builder.fo4)
            for edid, sig, name in ((DT_OFF, b'AVIF', 'Ammo DT Reduction'), (DT_MULT, b'AVIF', 'Ammo DT Multiplier'),
                                    (DT_EFFECT, b'MGEF', 'Ammo DT'), (DT_ENCH, b'ENCH', 'Ammo DT')):
                self._copy(sig, ids[edid], edid, name, vanilla[sig], ids)
            effects = b''.join(pack_effect(ENTRY_POINT, bytes([TARGET_RESISTANCE, func, RESISTANCE_TABS]), {}, [
                (b'EPFT', bytes([AV_PARAM])), (b'EPFB', struct.pack('<H', n)), (b'EPFD', struct.pack('<If', ids[av], mult))])
                for n, (func, av, mult) in enumerate(((ADD_AV_MULT, DT_OFF, -1.0), (MULTIPLY_AV_MULT, DT_MULT, 1.0))))
            self.builder.writer.add_record('PERK', pack_perk(ids[DT_PERK], (DT_PERK, '', ''), b'',
                                                             struct.pack(PERK_DATA, 0, 0, 1, 0, 1), 0, effects))
            self.dt = ids
        return self.dt

    def _copy(self, sig: bytes, fid: int, edid: str, name: str, subs: list, ids: dict) -> None:
        """Write vanilla `subs` as `edid` named `name` (_copied)."""
        out = b''.join(pack_subrecord(tag.decode(), _copied(sig, tag, body, (edid, name), ids)) for tag, body in subs)
        self.builder.writer.add_record(sig.decode(), pack_fo4_record(sig.decode(), fid, 0, out))


def _copied(sig: bytes, tag: bytes, body: bytes, text: tuple, ids: dict) -> bytes:
    """Subrecord `tag` of a `sig` copy named `text` (EditorID, name): strings as text, a perk effect's perk and an
    enchantment's effect ours (`ids`)."""
    if tag == b'EDID':
        return (text[0] + '\0').encode()
    if tag in LOCALIZED:
        return ((text[1] if tag == b'FULL' else '') + '\0').encode()
    if tag == b'DATA' and sig == b'MGEF':
        return body[:PERK_TO_APPLY] + struct.pack('<I', ids[DT_PERK]) + body[PERK_TO_APPLY + 4:]
    return struct.pack('<I', ids[DT_EFFECT]) if tag == b'EFID' else body


def members(rec: dict) -> list:
    """An export FLST's entries, as FormIDs."""
    out, i = [], 0
    while f'LNAM[{i}]' in rec:
        out.append(int(rec[f'LNAM[{i}]'], 16))
        i += 1
    return out


def _vanilla(fo4: bytes) -> dict:
    """{sig: subrecords} of Fallout4.esm's PENETRATION records."""
    out = {}
    for rec, _ in walk(fo4, *PENETRATION):
        subs = list(subrecords(rec.body))
        if dict(subs).get(b'EDID', b'').rstrip(b'\0').decode() == PENETRATION[rec.sig]:
            out[rec.sig] = subs
    return out
