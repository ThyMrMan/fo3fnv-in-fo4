"""Which Fallout 4 projectile a converted FNV gun or round flies (spike.projectiles, data/projectiles.json).

See: docs/fork/fo4_pipeline.md#nv-ammo
"""
import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import guns, projectiles as P
from fo4_import.spike import projectile_copies as C
from fo4_import.spike.attack_spells import ENIT_EXPLOSION, pack_explosion_ench
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FalloutNV.esm and the DLCs whose projectiles the table names.
FNV_PLUGINS = ('FalloutNV', 'GunRunnersArsenal', 'DeadMoney', 'HonestHearts', 'OldWorldBlues', 'LonesomeRoad')
LASER, PLASMA, SLUG_PROJ, ODD = 0x14B0F, 0x15C2E, 0x157B5A, 0x99
BEAM, BOLT, SHOT = 0x9C663, 0x125C9B, 0x1F674
CELL, SLUG = 0x14B0E, 0x157B59
TABLE = {'BeamLaserProjectile': 'LaserRifleBeamRed', 'PlasmaProjectile': 'PlasmaProjectileLarge',
         '12GaSlugProjectile': 'ProjectileShotgun'}
EXPORT = {
    'PROJ': [{'FormID': f'{f:08X}', 'EditorID': e} for f, e in ((LASER, 'BeamLaserProjectile'), (PLASMA, 'PlasmaProjectile'),
                                                                (SLUG_PROJ, '12GaSlugProjectile'), (ODD, 'OddProjectile'))],
    'AMMO': [{'FormID': f'{CELL:08X}', 'DAT2.Projectile': '00000000'},
             {'FormID': f'{SLUG:08X}', 'DAT2.Projectile': f'{SLUG_PROJ:08X}'}],
    'FLST': [{'FormID': '00000500', 'LNAM[0]': f'{CELL:08X}'}],
    'WEAP': [{'FormID': '00000300', 'NAM0': f'{CELL:08X}', 'DNAM.Projectile': f'{LASER:08X}', 'DNAM.Flags1': '32'},
             {'FormID': '00000400', 'NAM0': '00000500', 'DNAM.Projectile': f'{PLASMA:08X}', 'DNAM.Flags1': '0'},
             {'FormID': '00000600', 'NAM0': f'{CELL:08X}', 'DNAM.Projectile': f'{LASER:08X}', 'DNAM.Flags1': '0'}],
    'EXPL': [],
}


def _projectiles(monkeypatch, table: dict = TABLE) -> P.Projectiles:
    """Projectiles over EXPORT and a Fallout4.esm of the table's three targets."""
    fo4 = [(SimpleNamespace(sig=b'PROJ', form_id=f, body=pack_subrecord('EDID', f'{e}\0'.encode())), None)
           for f, e in ((BEAM, 'LaserRifleBeamRed'), (BOLT, 'PlasmaProjectileLarge'), (SHOT, 'ProjectileShotgun'))]
    monkeypatch.setattr(P, 'walk', lambda raw, *sigs: fo4)
    monkeypatch.setattr(P, 'export_records', lambda export, sig: EXPORT[sig])
    return P.Projectiles(SimpleNamespace(fo4=b'', export_dir='x', counts=Counter()), table)


def test_a_gun_flies_its_own_fnv_projectile(monkeypatch):
    """The gun's DNAM projectile, through the table."""
    found = _projectiles(monkeypatch)
    assert found.gun({'DNAM.Projectile': f'{PLASMA:08X}'}) == BOLT and found.gun({}) is None


def test_a_round_flies_its_override_else_its_first_unembedded_gun(monkeypatch):
    """Slug: its DAT2 projectile; cell: its lowest-FormID unembedded gun's."""
    found = _projectiles(monkeypatch)
    assert found.override(SLUG) == SHOT and found.ammo(SLUG) == SHOT
    assert found.override(CELL) is None and found.ammo(CELL) == BOLT


def test_an_unmapped_projectile_is_counted_once(monkeypatch):
    """A projectile the table leaves out gives None, counted once."""
    found = _projectiles(monkeypatch)
    assert found.of(ODD) is None and found.of(ODD) is None
    assert found.builder.counts == Counter({'projectile not mapped (OddProjectile)': 1})


def test_a_missing_fo4_target_is_refused(monkeypatch):
    """A table naming a projectile Fallout4.esm lacks fails the build."""
    with pytest.raises(ValueError, match='NoSuchProjectile'):
        _projectiles(monkeypatch, {**TABLE, 'OddProjectile': 'NoSuchProjectile'})


def test_fnam_takes_the_count_and_override(monkeypatch):
    """FNAM keeps its bytes but the projectile count and the Override Projectile FormID."""
    found, fnam = _projectiles(monkeypatch), bytes(range(41))
    out = found.fnam(fnam, {'DNAM.Projectile': f'{LASER:08X}', 'DNAM.ProjectileCount': '7'})
    assert out[P.FNAM_COUNT] == 7 and struct.unpack_from('<I', out, P.FNAM_OVERRIDE)[0] == BEAM
    assert out[:P.FNAM_COUNT] == fnam[:P.FNAM_COUNT] and out[P.FNAM_OVERRIDE + 4:] == fnam[P.FNAM_OVERRIDE + 4:]
    unmapped = found.fnam(fnam, {'DNAM.Projectile': f'{ODD:08X}'})
    assert unmapped[P.FNAM_COUNT] == 1 and unmapped[P.FNAM_OVERRIDE:] == fnam[P.FNAM_OVERRIDE:]


def test_without_override_drops_only_override_projectile():
    """An OMOD DATA loses its property 80 and keeps the rest, the count fixed."""
    prop = struct.Struct('<B3xB3xH2xIIf')
    head = struct.pack('<II', 0, 2) + bytes(8)
    data = head + prop.pack(4, 0, 80, 0x1234, 440, 0.0) + prop.pack(1, 2, 72, 0, 0, 0.0)
    out = guns.without_override(data)
    assert guns.overrides_projectile(data) and not guns.overrides_projectile(out)
    assert out == struct.pack('<II', 0, 1) + bytes(8) + prop.pack(1, 2, 72, 0, 0, 0.0)


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_the_table_names_real_projectiles():
    """Every target is a Fallout4.esm projectile; every key an FNV or FNV DLC one (when the exports are here)."""
    fo4 = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252') for r, _ in walk(FALLOUT4_ESM.read_bytes(),
                                                                                                    b'PROJ')}
    table = P.load_table()
    assert set(table.values()) <= fo4
    exports = [P.TABLE.parents[2] / 'export' / f'{name}.esm' for name in FNV_PLUGINS]
    if all((export / 'PROJ.txt').exists() for export in exports):
        assert set(table) <= {r['EditorID'] for export in exports for r in export_records(export, 'PROJ')}


def test_a_copy_flies_fnvs_range_and_speed_only_when_the_stand_in_flies():
    """Range always; gravity and speed for a Missile or Lobber, not a hitscan Beam."""
    rec = {'DATA.Range': '20000', 'DATA.Speed': '1550', 'DATA.Gravity': '1.5'}
    missile, beam = bytearray(64), bytearray(64)
    struct.pack_into('<HHfff', missile, 0, 0xA, 1, 0.0, 2500.0, 15000.0)
    struct.pack_into('<HHfff', beam, 0, 0x1, 4, 0.0, 1000.0, 10000.0)
    assert struct.unpack_from('<fff', C.flight(bytes(missile), rec), 4) == (1.5, 1550.0, 20000.0)
    assert struct.unpack_from('<fff', C.flight(bytes(beam), rec), 4) == (0.0, 1000.0, 20000.0)


def test_an_explosion_copy_takes_fnvs_force_damage_and_radius():
    """FNV's force and damage; its radius as the outer, the inner scaled along."""
    data = bytearray(64)
    struct.pack_into('<ffff', data, C.FORCE_AT, 150.0, 550.0, 135.0, 500.0)
    out = C.blast(bytes(data), {'DATA.Force': '450', 'DATA.Damage': '200', 'DATA.Radius': '1000'})
    assert struct.unpack_from('<ffff', out, C.FORCE_AT) == (450.0, 200.0, 270.0, 1000.0)


def _stand_in(flags: int, explosion: int = 0x55) -> bytes:
    """A 36-byte FO4 PROJ DNAM head: `flags`, Lobber, fuse 50 / 2 s, `explosion`."""
    return struct.pack('<HHfffIIffI', flags, 2, 1.0, 900.0, 500.0, 0, 0, 50.0, 2.0, explosion)


def test_a_thrown_copy_takes_fnv_fuse_or_the_table_and_drops_a_missing_explosion():
    """FNV's Alt. Trigger fuse on a stand-in with one; C4's from the table; a spear (no Explosion flag) none."""
    head = _stand_in(C.EXPLODES | C.ALT_TRIGGER)
    mine = {'DATA.Flags': str(C.EXPLODES | C.ALT_TRIGGER), 'DATA.AltTriggerProximity': '100', 'DATA.AltTriggerTimer': '3'}
    assert struct.unpack_from('<ff', C.thrown(head, mine, {}), C.FUSE_AT) == (100.0, 3.0)
    c4 = {'EditorID': 'C4Projectile', 'DATA.Flags': str(C.EXPLODES)}
    assert struct.unpack_from('<ff', C.thrown(head, c4, {'C4Projectile': (0.0, 15.0)}), C.FUSE_AT) == (0.0, 15.0)
    spear = C.thrown(head, {'DATA.Flags': str(C.ALT_TRIGGER)}, {})
    assert not struct.unpack_from('<H', spear)[0] & C.EXPLODES and struct.unpack_from('<I', spear, C.EXPLOSION_AT)[0] == 0
    assert C.thrown(_stand_in(C.EXPLODES), mine, {}) == _stand_in(C.EXPLODES)


def test_the_fuse_table_names_fnv_projectiles_the_projectile_table_maps():
    """Every fuse is for a mapped FNV projectile (a stand-in copy carries it)."""
    assert set(P.load_fuses()) <= set(P.load_table()) and P.load_fuses()['C4Projectile'] == (0.0, 15.0)


def test_an_inert_thrown_copy_shows_fnvs_model_and_takes_its_pickup_and_pinning():
    """A spear's copy: FNV's Pins Limbs and Can Be Picked Up, the stand-in's Muzzle Flash gone; its model and
    bounds replaced in place, the stand-in's texture hashes dropped."""
    spear = {'DATA.Flags': str(0x144)}
    flags = struct.unpack_from('<H', C.thrown(_stand_in(0x108), spear, {}))[0]
    assert flags & C.THROWN_FLAGS == 0x140 and C.inert(spear) and not C.inert({'DATA.Flags': '6'})
    subs = [(b'EDID', b'x\0'), (b'OBND', bytes(12)), (b'FULL', b''), (b'MODL', b'old\0'), (b'MODT', b'h'), (b'DNAM', b'')]
    out = C.with_model(subs, 'Weapons\\spear.nif', (1, 2, 3, 4, 5, 6))
    assert [t for t, _ in out] == [b'EDID', b'OBND', b'FULL', b'MODL', b'DNAM']
    assert dict(out)[b'MODL'] == b'Weapons\\spear.nif\0' and dict(out)[b'OBND'] == struct.pack('<6h', 1, 2, 3, 4, 5, 6)


def test_an_explosion_copy_takes_fnvs_enchantment_only_when_the_stand_in_has_none(monkeypatch):
    """FNV's converted enchantment goes in as EITM before MNAM; a stand-in with its own object effect keeps it."""
    copies = C.ProjectileCopies.__new__(C.ProjectileCopies)
    copies.builder, copies.enchantments = None, {0x14DDDD: {'EditorID': 'EnchStunGrenadeEffect'}}
    copies.spells = SimpleNamespace(explosion=lambda ench: 0xABC)
    rec = {'EITM': '0014DDDD'}
    plain = [(b'EDID', b''), (b'MODL', b''), (b'MNAM', b''), (b'DATA', b'')]
    out = copies._effect(plain, rec)
    assert [t for t, _ in out] == [b'EDID', b'MODL', b'EITM', b'MNAM', b'DATA'] and dict(out)[b'EITM'] == struct.pack('<I', 0xABC)
    own = [(b'EDID', b''), (b'EITM', b'\1\0\0\0'), (b'DATA', b'')]
    assert copies._effect(own, rec) == own and copies._effect(plain, {}) == plain


def test_an_explosion_enchantment_is_laid_out_as_vanillas():
    """EDID, OBND, the plasma grenade's ENIT, then the effect pairs."""
    subs = subrecords(pack_explosion_ench(0x800, 'FNV_X', b'')[24:])
    assert [t for t, _ in subs] == [b'EDID', b'OBND', b'ENIT'] and dict(subs)[b'ENIT'] == ENIT_EXPLOSION
    assert ENIT_EXPLOSION.hex() == '000000000000000001000000000000000100000006000000' + '00' * 12
