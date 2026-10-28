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
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.writer import pack_subrecord

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
}


def _projectiles(monkeypatch, table: dict = TABLE) -> P.Projectiles:
    """Projectiles over EXPORT and a Fallout4.esm of the table's three targets."""
    fo4 = [(SimpleNamespace(form_id=f, body=pack_subrecord('EDID', f'{e}\0'.encode())), None)
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
    """Every target is a Fallout4.esm projectile; every key an FNV one (when the export is here)."""
    fo4 = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252') for r, _ in walk(FALLOUT4_ESM.read_bytes(),
                                                                                                    b'PROJ')}
    table = P.load_table()
    assert set(table.values()) <= fo4
    export = P.TABLE.parents[2] / 'export' / 'FalloutNV.esm'
    if (export / 'PROJ.txt').exists():
        assert set(table) <= {r['EditorID'] for r in export_records(export, 'PROJ')}
