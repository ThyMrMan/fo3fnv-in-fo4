"""FNV weapon mods (IMOD) as Fallout 4 object mods (OMOD), installed at the weapons workbench.

FNV keeps a mod's effect on the gun: WEAP's three slots (WMI1-3) name an
IMOD and DNAM gives each slot an effect and a value. So each (gun, slot)
becomes an OMOD that only that converted gun takes (its own mod-association
keyword replaces the gun's vanilla ma_* ones), and the IMOD becomes the loose
mod item (a MISC with ObjectTypeLooseMod) the workbench fits it from. Its
recipe has no components and needs a hidden perk no one holds (the lock), so
the workbench lists the mod, locked, and a carried mod item fits it: FNV's
mods are items, never crafted. The OMOD sits at the attach point
vanilla gives that kind of part (POINTS, the first free one the gun's parts
offer) and copies the FO4 gun's own part of that kind (its largest magazine,
a scope, a suppressor: model, slots, keywords, not its numbers), else the
gun's default part there (all of it), with FNV's effect as properties.

See: docs/fork/fo4_pipeline.md#weapon-mods
"""

import math
import struct
from dataclasses import dataclass

from fo4_import.base.install import source_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import records as R
from fo4_import.spike.conditions import FO4
from fo4_import.spike.perks import PERK_DATA, pack_perk
from fo4_import.spike.gun_choice import OBTS_DEFAULT, includes
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid sites (key: the FNV gun's FormID, with the slot for a mod and its recipe; the lock perk's EditorID).
MOD_SITE, RECIPE_SITE, KEYWORD_SITE, LOCK_SITE = ('FNV weapon mod', 'FNV weapon mod recipe', 'FNV weapon mod keyword',
                                                 'FNV weapon mod lock')
#: The hidden perk no one holds, which every FNV mod recipe needs: EditorID, the name a locked recipe shows.
LOCK_EDID, LOCK_NAME = 'FNV_WeaponModFound', 'Mod Item'
#: Condition function HasPerk; perk DATA of a hidden, unplayable one-rank perk.
HAS_PERK, LOCK_DATA = FO4.index('HasPerk'), struct.pack(PERK_DATA, 0, 0, 1, 0, 1)
#: FNV WEAP mod effects (xEdit's wbModEffectEnum).
(DAMAGE, CAPACITY, SPREAD, WEIGHT, REGEN_SHOTS, REGEN_SECONDS, EQUIP_TIME, RATE, PROJECTILE_SPEED, CONDITION,
 SILENCE, SPLIT_BEAM, VATS, ZOOM, _UNKNOWN, SUPPRESSOR) = range(1, 17)
EFFECT_NAMES = {REGEN_SHOTS: 'regenerate ammo', REGEN_SECONDS: 'regenerate ammo', EQUIP_TIME: 'equip time',
                PROJECTILE_SPEED: 'projectile speed', CONDITION: 'max condition', VATS: 'VATS bonus'}
#: FNV WEAP DNAM: Flags1 (Is Automatic 0x2), min spread, Flags2 (Scope has NightVision), effects, values A.
FNV_FLAGS1, FNV_AUTOMATIC, FNV_SPREAD, FNV_FLAGS2, FNV_NIGHT_VISION = 12, 0x2, 16, 56, 0x1000
FNV_EFFECTS, FNV_VALUES = 140, 152
SLOT_SIGS = (b'WMI1', b'WMI2', b'WMI3')
RECEIVER, BARREL, GRIP = 'ap_gun_receiver', 'ap_gun_Barrel', 'ap_gun_Grip'
#: Effect -> attach points in preference order (vanilla's part roles); any other effect: OTHER_POINTS.
POINTS = {CAPACITY: ('ap_gun_Mag', BARREL, RECEIVER), ZOOM: ('ap_gun_Scope',), SILENCE: ('ap_gun_Muzzle',),
          SUPPRESSOR: ('ap_gun_Muzzle',), SPREAD: (BARREL, RECEIVER), PROJECTILE_SPEED: (BARREL, RECEIVER),
          SPLIT_BEAM: (BARREL, RECEIVER), WEIGHT: (GRIP, RECEIVER, BARREL)}
OTHER_POINTS = (RECEIVER, BARREL, GRIP)
#: OMOD property value types, functions and properties (xEdit's wbObjectModProperties, wbWeaponPropertyEnum).
INT, FLOAT, BOOL, FORM, ENUM = 0, 1, 2, 4, 5
SET, MUL_ADD, ADD = 0, 1, 2
(SPEED, ATTACK_DELAY, AMMO_CAPACITY, ATTACK_DAMAGE, WEIGHT_PROP, KEYWORDS, MIN_CONE, MAX_CONE, HAS_SCOPE,
 FOV_MULT, NUM_PROJECTILES, SOUND_LEVEL, ZOOM_DATA) = 0, 4, 12, 28, 30, 31, 33, 34, 48, 49, 51, 59, 67
PROPERTY = struct.Struct('<B3xB3xH2xIIf')
#: Vanilla's second value on a keyword ADD (2,253 of 2,295) and on a ZoomData SET (126 of 126).
KEYWORD_VALUE2, ZOOM_VALUE2 = 440, 441
#: SoundLevel Silent; a bool property's true, as vanilla writes it (value 1, value 2 1).
SILENT, TRUE = 2, 1
#: Fallout 4's default world field of view, which a zoom FOV mult divides.
FO4_WORLD_FOV = 70.0
ZOOMS = ('ZM_Standard_Scope_x2', 'ZM_Standard_Scope_x4', 'ZM_Standard_Scope_x6', 'ZM_Standard_Scope_x10')
NIGHT_ZOOMS = ('ZM_Standard_Scope_x4_NightVision', 'ZM_Standard_Scope_x6_NightVision',
               'ZM_Standard_Scope_x10_NightVision')
SCOPE_KEYWORDS, NIGHT_KEYWORD = ('HasScope', 'dn_HasScope'), 'dn_HasNightVision'
SILENCER_KEYWORDS = ('HasSilencer', 's_20_Silenced', 'dn_HasMuzzle_Suppressor')
LOOSE_MOD_KEYWORD, MOD_ASSOCIATION = 'ObjectTypeLooseMod', 5
#: OMOD subrecords a copy keeps from its part (the rest are FNV's or ours).
KEPT = (b'MODL', b'MODT', b'FNAM', b'NAM1')


@dataclass(frozen=True)
class Gun:
    """An FNV gun's mod data: EditorID, automatic, min spread, night-vision scope and [(slot, IMOD, effect, value)]."""
    edid: str
    automatic: bool
    spread: float
    night_vision: bool
    slots: tuple


@dataclass
class Part:
    """An OMOD's DATA split up: header (bools, form type, rank, tier), attach point, slots, raw items and
    includes, properties as raw 24-byte entries."""
    header: bytes
    point: int
    slots: list
    items: bytes
    includes: bytes
    properties: list


def parse_part(data: bytes) -> Part:
    """An OMOD DATA as a Part."""
    count, n_props = struct.unpack_from('<II', data)
    point, n_slots = struct.unpack_from('<II', data, 16)
    pos = 24 + 4 * n_slots
    n_items = struct.unpack_from('<I', data, pos)[0]
    start = pos + 4 + 8 * n_items
    end = start + 7 * count
    return Part(data[8:16], point, list(struct.unpack_from(f'<{n_slots}I', data, 24)), data[pos + 4:start],
                data[start:end], [data[end + 24 * i:end + 24 * (i + 1)] for i in range(n_props)])


def pack_part(part: Part) -> bytes:
    """A Part as OMOD DATA."""
    return (struct.pack('<II', len(part.includes) // 7, len(part.properties)) + part.header
            + struct.pack(f'<II{len(part.slots)}I', part.point, len(part.slots), *part.slots)
            + struct.pack('<I', len(part.items) // 8) + part.items + part.includes + b''.join(part.properties))


def prop(vtype: int, func: int, which: int, value1, value2=0) -> bytes:
    """One property entry; a FLOAT's values are floats, the rest ints."""
    pack = '<ff' if vtype == FLOAT else '<II'
    return struct.pack('<B3xB3xH2x', vtype, func, which) + struct.pack(pack, value1, value2) + bytes(4)


def _key(entry: bytes) -> tuple:
    """What an added property replaces: the same keyword, else the same property."""
    _, _, which, value1, _, _ = PROPERTY.unpack(entry)
    return (which, value1) if which == KEYWORDS else (which,)


def fnv_guns(raw: bytes) -> tuple:
    """({FNV WEAP FormID: Gun} of the guns with mod slots, {IMOD FormID: {sig: body}}) read from plugin `raw`."""
    guns, imods = {}, {}
    for rec, _ in walk(raw, b'WEAP', b'IMOD'):
        subs = dict(subrecords(rec.body))
        if rec.sig == b'IMOD':
            imods[rec.form_id] = subs
            continue
        named = [(i, struct.unpack('<I', subs[sig])[0]) for i, sig in enumerate(SLOT_SIGS) if sig in subs]
        if not named:
            continue
        dnam = subs[b'DNAM']
        effects, values = struct.unpack_from('<3I', dnam, FNV_EFFECTS), struct.unpack_from('<3f', dnam, FNV_VALUES)
        guns[rec.form_id] = Gun(subs[b'EDID'].rstrip(b'\0').decode('cp1252'), bool(dnam[FNV_FLAGS1] & FNV_AUTOMATIC),
                                struct.unpack_from('<f', dnam, FNV_SPREAD)[0],
                                bool(struct.unpack_from('<I', dnam, FNV_FLAGS2)[0] & FNV_NIGHT_VISION),
                                tuple((i, imod, effects[i], values[i]) for i, imod in named))
    return guns, imods


def _text(subs: dict, sig: bytes) -> str:
    """A string subrecord's text ('' when absent)."""
    return subs.get(sig, b'').rstrip(b'\0').decode('cp1252')


class WeaponMods:
    """FNV's weapon mods written through a cell builder: `wire` for a converted gun, `loose` for an IMOD item."""

    def __init__(self, builder, mods: dict):
        """FNV's guns and IMODs; Fallout4.esm's OMODs `mods` {FormID: subrecords} as parts, its zoom presets."""
        self.builder, self.kw, self.mods = builder, builder.keywords, mods
        self.guns, self.imods = fnv_guns(source_esm())
        self.parts = {fid: parse_part(dict(subs)[b'DATA']) for fid, subs in mods.items()}
        self.targets = {fid: set(_ids(dict(subs).get(b'MNAM', b''))) for fid, subs in mods.items()}
        self.vanilla_ma = {fid for name, fid in self.kw.items() if name.startswith('ma_')}
        self.zooms, self.lock = {}, None
        for rec, _ in walk(builder.fo4, b'ZOOM'):
            subs = dict(subrecords(rec.body))
            self.zooms[_text(subs, b'EDID')] = (rec.form_id, struct.unpack_from('<f', subs[b'GNAM'])[0])

    def loose(self, fnv: int, rec: dict) -> int:
        """Item maker: the loose mod MISC (on FNV's FormID) for IMOD `fnv`, FNV's name, model, value and weight."""
        subs = self.imods[fnv]
        model, bounds = self.builder.mesh(_text(subs, b'MODL')) if b'MODL' in subs else ('', None)
        value, weight = struct.unpack('<If', subs[b'DATA'])
        fid = self.builder.fnv_id(fnv)
        self.builder.writer.add_record('MISC', R.pack_misc(
            fid, f'FNV_{rec["EditorID"]}', _text(subs, b'FULL'), model,
            bounds or struct.unpack('<6h', subs[b'OBND']), value, weight, keywords=(self.kw[LOOSE_MOD_KEYWORD],)))
        self.builder.counts['MISC (loose weapon mods)'] += 1
        return fid

    def test_items(self) -> list:
        """[(loose mod, 1)] of every FNV IMOD, for the test chest."""
        made = [self.builder.items.item(fid) for fid in sorted(self.imods)]
        return [(fid, 1) for fid in made if fid is not None]

    def wire(self, fnv: int, subs: list) -> list:
        """Converted gun `subs` (FNV WEAP `fnv`) with its own mod-association keyword for vanilla's ma_* ones; its
        FNV mods written (OMOD, fitted from its loose item)."""
        gun = self.guns.get(fnv)
        keyword = self._keyword(fnv, gun) if gun else None
        ours = [keyword] if keyword else []
        out = [(sig, _pack_ids([k for k in _ids(body) if k not in self.vanilla_ma] + ours) if sig == b'KWDA' else body)
               for sig, body in subs]
        count = len(dict(out).get(b'KWDA', b'')) // 4
        if gun:
            self._mods(fnv, gun, subs, keyword)
        return [(sig, struct.pack('<I', count) if sig == b'KSIZ' else body) for sig, body in out]

    def _keyword(self, fnv: int, gun: Gun) -> int:
        """The mod-association keyword gun `fnv`'s mods target (written once per gun)."""
        fid = self.builder.writer.derive_formid(KEYWORD_SITE, f'{fnv:08X}')
        self.builder.writer.add_record('KYWD', R.pack_kywd(fid, f'FNV_ma_{gun.edid}', MOD_ASSOCIATION))
        return fid

    def _mods(self, fnv: int, gun: Gun, subs: list, keyword: int) -> None:
        """Each of gun `fnv`'s slots as an OMOD at a free attach point its converted record's (`subs`) parts offer;
        a slot with no such point is counted."""
        weapon = dict(subs)
        defaults = {self.parts[f].point: f for f in _default_parts(subs) if f in self.parts}
        offered = set(_ids(weapon.get(b'APPR', b''))) | {s for f in defaults.values() for s in self.parts[f].slots}
        taken = set()
        for slot, imod, effect, value in gun.slots:
            point = next((self.kw[p] for p in POINTS.get(effect, OTHER_POINTS)
                          if self.kw[p] in offered and self.kw[p] not in taken), None)
            if point is None:
                self.builder.counts['weapon mod skipped (no free attach point)'] += 1
                continue
            taken.add(point)
            base = self._counterpart(effect, point, set(_ids(weapon.get(b'KWDA', b''))), gun.night_vision)
            omod = self._omod(fnv, gun, (slot, imod, effect, value), (point, base or defaults.get(point), bool(base)),
                              keyword)
            self._recipe(fnv, gun, slot, imod, omod)

    def _counterpart(self, effect: int, point: int, keywords: set, night: bool) -> 'int | None':
        """The FO4 gun's own part of `effect`'s kind at `point` (MNAM in its `keywords`): its largest magazine, its
        scope (night vision as `night` first) or suppressor; lowest FormID on ties; None."""
        wants = {CAPACITY: AMMO_CAPACITY, ZOOM: HAS_SCOPE}.get(effect)
        silencer = self.kw['HasSilencer'] if effect in (SILENCE, SUPPRESSOR) else None
        if wants is None and silencer is None:
            return None
        best = None
        for fid, part in self.parts.items():
            if part.point != point or not self.targets[fid] & keywords:
                continue
            props = [PROPERTY.unpack(p) for p in part.properties]
            found = [p for p in props if (p[2] == wants) or (p[2] == KEYWORDS and p[3] == silencer)]
            if not found:
                continue
            capacity = -struct.unpack('<f', struct.pack('<I', found[0][3]))[0] if wants == AMMO_CAPACITY else 0.0
            nv = any(p[2] == KEYWORDS and p[3] == self.kw[NIGHT_KEYWORD] for p in props) != night
            score = (capacity, nv, fid)
            best = min(best or score, score)
        return best[2] if best else None

    def _omod(self, fnv: int, gun: Gun, slot: tuple, place: tuple, keyword: int) -> int:
        """The OMOD of `slot` (index, IMOD, effect, value) on gun `fnv`: `place` (attach point, the part copied or
        None, whether that is a counterpart whose numbers give way to FNV's)."""
        index, imod, effect, value = slot
        point, base, counterpart = place
        part = self.parts[base] if base else Part(b'\0\0WEAP\0\0', point, [], b'', b'', [])
        kept = [p for p in part.properties if not counterpart or PROPERTY.unpack(p)[0] not in (INT, FLOAT)]
        added = self._effect(effect, value, gun)
        keys = {_key(p) for p in added}
        props = [p for p in kept if _key(p) not in keys] + added
        if not added:
            self.builder.counts[f'weapon mod with no FO4 effect ({EFFECT_NAMES.get(effect, effect)})'] += 1
        fnv_subs, base_subs = self.imods[imod], dict(self.mods.get(base, []))
        fid = self.builder.writer.derive_formid(MOD_SITE, f'{fnv:08X} {index}')
        subs = [(b'EDID', f'FNV_mod_{gun.edid}_{_text(fnv_subs, b"EDID")}\0'.encode('cp1252')),
                (b'FULL', fnv_subs.get(b'FULL', b'\0')), (b'DESC', fnv_subs.get(b'DESC', b'\0'))]
        subs += [(sig, base_subs[sig]) for sig in KEPT[:2] if sig in base_subs]
        subs += [(b'DATA', pack_part(Part(part.header, point, part.slots, part.items, part.includes, props))),
                 (b'MNAM', struct.pack('<I', keyword))]
        subs += [(sig, base_subs[sig]) for sig in KEPT[2:3] if sig in base_subs]
        subs += [(b'LNAM', struct.pack('<I', self.builder.items.item(imod)))]
        subs += [(sig, base_subs[sig]) for sig in KEPT[3:] if sig in base_subs]
        self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', fid, 0, b''.join(
            pack_subrecord(s.decode(), b) for s, b in subs)))
        self.builder.counts['OMOD (FNV weapon mods)'] += 1
        return fid

    def _recipe(self, fnv: int, gun: Gun, slot: int, imod: int, omod: int) -> None:
        """The COBJ listing `omod` at the weapons workbench: no components, no bench keyword, gated on the lock perk
        no one holds, so it shows locked and only a carried mod item fits it.
        See: docs/fork/fo4_pipeline.md#weapon-mods
        """
        fid = self.builder.writer.derive_formid(RECIPE_SITE, f'{fnv:08X} {slot}')
        edid = f'FNV_co_mod_{gun.edid}_{_text(self.imods[imod], b"EDID")}'
        locked = R.pack_ctda(0, 1.0, HAS_PERK, self._lock())
        body = pack_subrecord('EDID', (edid + '\0').encode()) + locked + R.pack_u32('CNAM', omod)
        self.builder.writer.add_record('COBJ', pack_fo4_record('COBJ', fid, 0, body + pack_subrecord(
            'INTV', struct.pack('<HH', 1, 0))))
        self.builder.counts['COBJ (FNV weapon mods)'] += 1

    def _lock(self) -> int:
        """The hidden perk every FNV mod recipe needs, written once."""
        if self.lock is None:
            self.lock = self.builder.writer.derive_formid(LOCK_SITE, LOCK_EDID)
            self.builder.writer.add_record('PERK', pack_perk(self.lock, (LOCK_EDID, LOCK_NAME, ''), b'', LOCK_DATA, 0,
                                                             b''))
        return self.lock

    def _effect(self, effect: int, value: float, gun: Gun) -> list:
        """The properties giving FNV `effect` of `value` on `gun`; [] for one Fallout 4 has no property for."""
        if effect in (CAPACITY, DAMAGE, WEIGHT):
            which = {CAPACITY: AMMO_CAPACITY, DAMAGE: ATTACK_DAMAGE, WEIGHT: WEIGHT_PROP}[effect]
            return [prop(FLOAT, ADD, which, -value if effect == WEIGHT else value)]
        if effect == SPREAD:
            cut = -min(value / gun.spread, 1.0) if gun.spread else 0.0
            return [prop(FLOAT, MUL_ADD, MIN_CONE, cut), prop(FLOAT, MUL_ADD, MAX_CONE, cut)]
        if effect == RATE:
            return [prop(FLOAT, MUL_ADD, SPEED, value) if gun.automatic
                    else prop(FLOAT, MUL_ADD, ATTACK_DELAY, -value / (1.0 + value))]
        if effect == SPLIT_BEAM:
            return [prop(INT, ADD, NUM_PROJECTILES, round(value)),
                    prop(FLOAT, MUL_ADD, ATTACK_DAMAGE, 1.0 / (1.0 + round(value)) - 1.0)]
        if effect == ZOOM:
            return self._scope(value, gun.night_vision)
        if effect in (SILENCE, SUPPRESSOR):
            return [prop(ENUM, SET, SOUND_LEVEL, SILENT)] + [prop(FORM, ADD, KEYWORDS, self.kw[k], KEYWORD_VALUE2)
                                                             for k in SILENCER_KEYWORDS]
        return []

    def _scope(self, fov: float, night: bool) -> list:
        """A scope showing FNV's `fov` degrees: the vanilla zoom preset nearest it (night vision ones when `night`),
        its FOV mult set to Fallout 4's world FOV over `fov`, HasScope and the scope keywords."""
        mult = FO4_WORLD_FOV / fov
        preset = min((self.zooms[n] for n in (NIGHT_ZOOMS if night else ZOOMS)),
                     key=lambda z: abs(math.log(z[1] / mult)))[0]
        names = SCOPE_KEYWORDS + ((NIGHT_KEYWORD,) if night else ())
        return ([prop(BOOL, SET, HAS_SCOPE, TRUE, TRUE), prop(FORM, SET, ZOOM_DATA, preset, ZOOM_VALUE2),
                 prop(FLOAT, SET, FOV_MULT, mult)]
                + [prop(FORM, ADD, KEYWORDS, self.kw[k], KEYWORD_VALUE2) for k in names])


def _ids(body: bytes) -> list:
    """The FormIDs in a packed array subrecord."""
    return list(struct.unpack(f'<{len(body) // 4}I', body))


def _pack_ids(ids: list) -> bytes:
    """FormIDs packed as an array subrecord."""
    return struct.pack(f'<{len(ids)}I', *ids)


def _default_parts(subs: list) -> list:
    """The parts of a WEAP's default object template combination ([] without one)."""
    return next((includes(body) for sig, body in subs if sig == b'OBTS' and body[OBTS_DEFAULT]), [])
