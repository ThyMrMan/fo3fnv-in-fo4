"""Copies of an FNV projectile's Fallout4.esm stand-in carrying FNV's flight and explosion numbers.

Each FNV projectile flies its stand-in (spike.projectiles) as a copy: its range FNV's; its speed and gravity
FNV's when the stand-in flies (Missile or Lobber; FO4's bullets and lasers are hitscan beams, where speed means
nothing); its explosion, when both the stand-in explodes and FNV's projectile has one, a copy of the stand-in's
with FNV's damage, force and radius (FNV's one radius as the outer, the inner scaled with it). The models,
lights, sounds and impacts stay the stand-in's. A thrown weapon's copy also takes FNV's fuse (Alt. Trigger proximity
and timer, else the table's for one FNV sets off another way: C4's detonator) when the stand-in has one; when FNV's
projectile has no explosion (a spear: the thrown object itself), none, FNV's model and its pick-up and pinning flags.
FormIDs are hashed from FNV's (SITES).

See: docs/fork/fo4_pipeline.md#projectile-copies
See: docs/fork/fo4_thrown_weapons.md#timers
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.attack_spells import AttackSpells
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FO4 PROJ DNAM offsets: Flags (u16), Type (u16), Gravity, Speed, Range (floats), Explosion (FormID).
FLAGS_AT, TYPE_AT, GRAVITY_AT, SPEED_AT, RANGE_AT, EXPLOSION_AT = 0, 2, 4, 8, 12, 32
#: FO4 PROJ DNAM Explosion - Alt. Trigger - Proximity, then its Timer (floats).
FUSE_AT = 24
#: FO4 PROJ DNAM Default Weapon Source: the weapon a disarmed or picked-up projectile gives (xEdit's FO4 PROJ).
SOURCE_AT = 60
#: PROJ flags Explosion and Alt. Trigger (the same bits in FNV and FO4); the types that fly (Missile, Lobber, Arrow).
EXPLODES, ALT_TRIGGER, FLYING = 0x2, 0x4, (1, 2, 0x40)
#: PROJ flags an inert thrown copy takes from FNV's (the same bits): Muzzle Flash, Can Be Picked Up, Pins Limbs.
THROWN_FLAGS = 0x8 | 0x40 | 0x100
#: FO4 EXPL DATA offsets: Force, Damage, Inner Radius, Outer Radius (floats).
FORCE_AT, DAMAGE_AT, INNER_AT, OUTER_AT = 24, 28, 32, 36
#: derive_formid sites (key: FNV FormID).
SITES = {'PROJ': 'FNV PROJ copy', 'EXPL': 'FNV EXPL copy'}


def _float(rec: dict, key: str) -> float:
    """An export float field; 0 when blank."""
    return float(rec.get(key) or 0.0)


def flight(dnam: bytes, rec: dict) -> bytes:
    """Stand-in PROJ DNAM `dnam` with FNV PROJ `rec`'s range, and its speed and gravity when the stand-in flies."""
    out = bytearray(dnam)
    struct.pack_into('<f', out, RANGE_AT, _float(rec, 'DATA.Range'))
    if struct.unpack_from('<H', out, TYPE_AT)[0] in FLYING:
        struct.pack_into('<ff', out, GRAVITY_AT, _float(rec, 'DATA.Gravity'), _float(rec, 'DATA.Speed'))
    return bytes(out)


def thrown(dnam: bytes, rec: dict, fuses: dict) -> bytes:
    """Stand-in PROJ DNAM `dnam` as FNV PROJ `rec` thrown: FNV's fuse when the stand-in has one (FNV's own when it
    sets Alt. Trigger, else `fuses`' {EditorID: (proximity, timer)}); when FNV's has no explosion (inert: a spear),
    none, and FNV's THROWN_FLAGS."""
    out, flags = bytearray(dnam), int(rec.get('DATA.Flags') or 0)
    own = struct.unpack_from('<H', out, FLAGS_AT)[0]
    fuse = ((_float(rec, 'DATA.AltTriggerProximity'), _float(rec, 'DATA.AltTriggerTimer')) if flags & ALT_TRIGGER
            else fuses.get(rec.get('EditorID')))
    if own & ALT_TRIGGER and fuse:
        struct.pack_into('<ff', out, FUSE_AT, *fuse)
    if not flags & EXPLODES:
        struct.pack_into('<H', out, FLAGS_AT, own & ~EXPLODES & ~THROWN_FLAGS | flags & THROWN_FLAGS)
        struct.pack_into('<I', out, EXPLOSION_AT, 0)
    return bytes(out)


def inert(rec: dict) -> bool:
    """Whether thrown FNV PROJ `rec` is the object itself: no Explosion flag."""
    return not int(rec.get('DATA.Flags') or 0) & EXPLODES


def with_model(subs: list, path: str, bounds) -> list:
    """PROJ `subs` on model `path`: MODL and OBND replaced in place, MODT dropped."""
    new = {b'MODL': f'{path}\0'.encode(), **({b'OBND': struct.pack('<6h', *bounds)} if bounds else {})}
    return [(tag, new.get(tag, data)) for tag, data in subs if tag != b'MODT']


def blast(data: bytes, rec: dict) -> bytes:
    """Stand-in EXPL DATA `data` with FNV EXPL `rec`'s force, damage and radius (inner radius scaled along)."""
    out = bytearray(data)
    inner, outer = struct.unpack_from('<ff', out, INNER_AT)
    radius = _float(rec, 'DATA.Radius')
    scaled = inner * radius / outer if outer > 0 else inner
    struct.pack_into('<ffff', out, FORCE_AT, _float(rec, 'DATA.Force'), _float(rec, 'DATA.Damage'), scaled, radius)
    return bytes(out)


def _with(subs: list, rec: dict, tag: bytes, data: bytes) -> bytes:
    """`subs` packed as FNV `rec`'s copy: its EditorID and name (FULL, else none), `tag`'s data set to `data`.
    See: docs/fork/fo4_thrown_weapons.md#names
    """
    name = rec.get('FULL')
    swap = {b'EDID': f'FNV_{rec["EditorID"]}\0'.encode(), b'FULL': f'{name}\0'.encode('cp1252', 'replace'),
            tag: data}
    return b''.join(pack_subrecord(t.decode(), swap.get(t, d)) for t, d in subs if t != b'FULL' or name)


class ProjectileCopies:
    """The stand-in copies of one build, each written once through its writer."""

    def __init__(self, builder, stand_ins: set, fuses: 'dict | None' = None, own_models: frozenset = frozenset()):
        """Index the `stand_ins` (Fallout4.esm PROJ FormIDs) and their explosions, and FNV's explosions; `fuses`
        {FNV EditorID: (proximity, timer)} for thrown projectiles FNV sets off another way; `own_models`, the FNV
        explosions (EditorIDs) shown on their own model."""
        self.builder, self.made, self.vanilla, self.fuses = builder, {}, {}, fuses or {}
        self.own_models = own_models
        for rec, _ in walk(builder.fo4, b'PROJ', b'EXPL'):
            if rec.sig == b'EXPL' or rec.form_id in stand_ins:
                self.vanilla[rec.form_id] = list(subrecords(rec.body))
        self.explosions = {int(r['FormID'], 16): r for r in export_records(builder.export_dir, 'EXPL')}
        self.enchantments = {int(r['FormID'], 16): r for r in export_records(builder.export_dir, 'ENCH')}
        self.spells = None

    def _effect(self, subs: list, rec: dict) -> list:
        """Stand-in EXPL `subs` with FNV EXPL `rec`'s enchantment, converted (AttackSpells.explosion), as its object
        effect (EITM, before MNAM and DATA) when the stand-in has none; else unchanged.
        See: docs/fork/fo4_thrown_weapons.md#effects
        """
        ench = self.enchantments.get(int(rec.get('EITM') or '0', 16))
        if ench is None or any(tag == b'EITM' for tag, _ in subs):
            return subs
        self.spells = self.spells or AttackSpells(self.builder)
        fid = self.spells.explosion(ench)
        if not fid:
            return subs
        at = next(i for i, (tag, _) in enumerate(subs) if tag in (b'MNAM', b'DATA'))
        return subs[:at] + [(b'EITM', struct.pack('<I', fid))] + subs[at:]

    def copy(self, stand_in: int, rec: dict, is_thrown: bool = False, own_model: bool = False, source: int = 0) -> int:
        """The copy of `stand_in` flying FNV PROJ `rec` (a thrown weapon's when `is_thrown`: thrown(), on FNV's
        model when inert or `own_model`; weapon `source` its default source), written once; the stand-in when it
        has no DNAM."""
        fnv = int(rec['FormID'], 16)
        subs = self.vanilla.get(stand_in, [])
        found = dict(subs)
        if b'DNAM' not in found:
            return stand_in
        if fnv not in self.made:
            dnam = bytearray(flight(found[b'DNAM'], rec))
            dnam = bytearray(thrown(dnam, rec, self.fuses)) if is_thrown else dnam
            explosion = self._explosion(struct.unpack_from('<I', dnam, EXPLOSION_AT)[0], rec, dnam)
            struct.pack_into('<I', dnam, EXPLOSION_AT, explosion)
            if source and len(dnam) >= SOURCE_AT + 4:
                struct.pack_into('<I', dnam, SOURCE_AT, source)
            fid = self.made[fnv] = self.builder.writer.derive_formid(SITES['PROJ'], fnv)
            if is_thrown and (inert(rec) or own_model) and rec.get('Model.MODL'):
                subs = with_model(subs, *self.builder.mesh(rec['Model.MODL']))
            body = _with(subs, rec, b'DNAM', bytes(dnam))
            self.builder.writer.add_record('PROJ', pack_fo4_record('PROJ', fid, 0, body))
            self.builder.counts['PROJ (stand-in copy)'] += 1
        return self.made[fnv]

    def _explosion(self, stand_in: int, rec: dict, dnam: bytes) -> int:
        """The copy's explosion: explosion() when both explode, else `stand_in`."""
        fnv = int(rec.get('DATA.Explosion') or '0', 16)
        exploding = struct.unpack_from('<H', dnam, FLAGS_AT)[0] & EXPLODES
        return self.explosion(stand_in, fnv) if exploding else stand_in

    def explosion(self, stand_in: int, fnv: int) -> int:
        """The copy of Fallout4.esm explosion `stand_in` with FNV explosion `fnv`'s numbers, enchantment and (when
        listed) model, written once; `stand_in` itself when either is unknown."""
        if not (fnv in self.explosions and stand_in in self.vanilla):
            return stand_in
        key = (SITES['EXPL'], fnv, stand_in)
        if key not in self.made:
            subs = self._effect(self.vanilla[stand_in], self.explosions[fnv])
            own = self.explosions[fnv]
            if own['EditorID'] in self.own_models and own.get('Model.MODL'):
                subs = with_model(subs, *self.builder.mesh(own['Model.MODL']))
            data = blast(dict(subs)[b'DATA'], own)
            fid = self.made[key] = self.builder.writer.derive_formid(SITES['EXPL'], f'{fnv:08X} {stand_in:08X}')
            body = _with(subs, self.explosions[fnv], b'DATA', data)
            self.builder.writer.add_record('EXPL', pack_fo4_record('EXPL', fid, 0, body))
            self.builder.counts['EXPL (stand-in copy)'] += 1
        return self.made[key]
