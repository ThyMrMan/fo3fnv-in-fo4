"""Copies of an FNV projectile's Fallout4.esm stand-in carrying FNV's flight and explosion numbers.

Each FNV projectile flies its stand-in (spike.projectiles) as a copy: its range FNV's; its speed and gravity
FNV's when the stand-in flies (Missile or Lobber; FO4's bullets and lasers are hitscan beams, where speed means
nothing); its explosion, when both the stand-in explodes and FNV's projectile has one, a copy of the stand-in's
with FNV's damage, force and radius (FNV's one radius as the outer, the inner scaled with it). The models,
lights, sounds and impacts stay the stand-in's. FormIDs are hashed from FNV's (SITES).

See: docs/fork/fo4_pipeline.md#projectile-copies
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FO4 PROJ DNAM offsets: Flags (u16), Type (u16), Gravity, Speed, Range (floats), Explosion (FormID).
FLAGS_AT, TYPE_AT, GRAVITY_AT, SPEED_AT, RANGE_AT, EXPLOSION_AT = 0, 2, 4, 8, 12, 32
#: FO4 PROJ flag Explosion; the types that fly (Missile, Lobber).
EXPLODES, FLYING = 0x2, (1, 2)
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


def blast(data: bytes, rec: dict) -> bytes:
    """Stand-in EXPL DATA `data` with FNV EXPL `rec`'s force, damage and radius (inner radius scaled along)."""
    out = bytearray(data)
    inner, outer = struct.unpack_from('<ff', out, INNER_AT)
    radius = _float(rec, 'DATA.Radius')
    scaled = inner * radius / outer if outer > 0 else inner
    struct.pack_into('<ffff', out, FORCE_AT, _float(rec, 'DATA.Force'), _float(rec, 'DATA.Damage'), scaled, radius)
    return bytes(out)


def _with(subs: list, edid: str, tag: bytes, data: bytes) -> bytes:
    """`subs` packed with EditorID `edid` and `tag`'s data set to `data`."""
    swap = {b'EDID': f'{edid}\0'.encode(), tag: data}
    return b''.join(pack_subrecord(t.decode(), swap.get(t, d)) for t, d in subs)


class ProjectileCopies:
    """The stand-in copies of one build, each written once through its writer."""

    def __init__(self, builder, stand_ins: set):
        """Index the `stand_ins` (Fallout4.esm PROJ FormIDs) and their explosions, and FNV's explosions."""
        self.builder, self.made, self.vanilla = builder, {}, {}
        for rec, _ in walk(builder.fo4, b'PROJ', b'EXPL'):
            if rec.sig == b'EXPL' or rec.form_id in stand_ins:
                self.vanilla[rec.form_id] = list(subrecords(rec.body))
        self.explosions = {int(r['FormID'], 16): r for r in export_records(builder.export_dir, 'EXPL')}

    def copy(self, stand_in: int, rec: dict) -> int:
        """The copy of `stand_in` flying FNV PROJ `rec`, written once; the stand-in when it has no DNAM."""
        fnv = int(rec['FormID'], 16)
        subs = self.vanilla.get(stand_in, [])
        found = dict(subs)
        if b'DNAM' not in found:
            return stand_in
        if fnv not in self.made:
            dnam = bytearray(flight(found[b'DNAM'], rec))
            explosion = self._explosion(struct.unpack_from('<I', dnam, EXPLOSION_AT)[0], rec, dnam)
            struct.pack_into('<I', dnam, EXPLOSION_AT, explosion)
            fid = self.made[fnv] = self.builder.writer.derive_formid(SITES['PROJ'], fnv)
            body = _with(subs, f'FNV_{rec["EditorID"]}', b'DNAM', bytes(dnam))
            self.builder.writer.add_record('PROJ', pack_fo4_record('PROJ', fid, 0, body))
            self.builder.counts['PROJ (stand-in copy)'] += 1
        return self.made[fnv]

    def _explosion(self, stand_in: int, rec: dict, dnam: bytes) -> int:
        """The explosion the copy carries: a copy of `stand_in` with FNV's numbers when both explode, else it."""
        fnv = int(rec.get('DATA.Explosion') or '0', 16)
        exploding = struct.unpack_from('<H', dnam, FLAGS_AT)[0] & EXPLODES
        if not (exploding and fnv in self.explosions and stand_in in self.vanilla):
            return stand_in
        key = (SITES['EXPL'], fnv, stand_in)
        if key not in self.made:
            subs = self.vanilla[stand_in]
            data = blast(dict(subs)[b'DATA'], self.explosions[fnv])
            fid = self.made[key] = self.builder.writer.derive_formid(SITES['EXPL'], f'{fnv:08X} {stand_in:08X}')
            body = _with(subs, f'FNV_{self.explosions[fnv]["EditorID"]}', b'DATA', data)
            self.builder.writer.add_record('EXPL', pack_fo4_record('EXPL', fid, 0, body))
            self.builder.counts['EXPL (stand-in copy)'] += 1
        return self.made[key]
