"""FNV destruction data (DEST) as FO4's: stages kept, explosions as stand-in copies, models converted.

See: docs/fork/fo4_pipeline.md#damage-stages
"""

import collections
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fo4_import.base.install import FALLOUTNV_ESM, source_walk
from fo4_import.spike import destruction as D
from fo4_import.spike import explosion_routes as X
from fo4_import.spike import records as R
from fo4_import.spike.cell import _static
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

CAR03 = 0x17790


class _Copies:
    """ProjectileCopies' explosion copier: FNV explosion 0x100 is SmallNukeExplosion, 0x300 a big unlisted one on
    its art, 0x400 unknown."""

    def __init__(self):
        """FNV's explosions by FormID."""
        self.explosions = {0x100: {'EditorID': 'SmallNukeExplosion', 'Model.MODL': 'Effects\\Big.NIF',
                                   'DATA.Radius': '1200', 'DATA.Damage': '150'},
                           0x300: {'EditorID': 'BusNuke', 'Model.MODL': 'effects\\big.nif', 'DATA.Radius': '900',
                                   'DATA.Damage': '200'}}
        self.enchantments = {}

    def explosion(self, stand_in: int, fnv: int) -> int:
        """A copy id naming both."""
        return stand_in << 8 | fnv >> 8


class _Writer:
    """A plugin writer keeping what it is given."""

    def __init__(self):
        """No records yet."""
        self.records = []

    def derive_formid(self, site: str, key) -> int:
        """A FormID naming the key."""
        return 0x900 + key

    def add_record(self, sig: str, record: bytes) -> None:
        """Keep `record`."""
        self.records.append((sig, record))


def _destruction(tmp_path, blocks: dict, debris: dict = None) -> D.Destruction:
    """A Destruction over `blocks` and FNV `debris` {FormID: DEBR body}, Fallout4.esm's CarNukeLargeVehicles at
    0x23D3B, an export holding two meshes."""
    for mesh in ('vehicles/carhulk03.nif', 'gore/bit01.nif'):
        (tmp_path / 'meshes' / mesh).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / 'meshes' / mesh).write_bytes(b'')
    builder = SimpleNamespace(projectiles=SimpleNamespace(copies=_Copies()), counts=collections.Counter(),
                              export_dir=tmp_path, mesh=lambda m: (f'fnv\\{m.lower()}', None), writer=_Writer(), fo4=b'')
    with patch.object(D, 'source_walk', lambda *sigs: iter(())):
        made = D.Destruction(builder)
    made.blocks, made.explosions = blocks, {'CarNukeLargeVehicles': 0x23D3B}
    made.fnv_debris = {fid: SimpleNamespace(form_id=fid, body=body) for fid, body in (debris or {}).items()}
    return made


def _stage(health: int, stage: int, flags: int, explosion: int, debris: int = 0, count: int = 0) -> bytes:
    """A DSTD."""
    return D.STAGE.pack(health, 0, stage, flags, 1, explosion, debris, count)


def test_a_stage_keeps_its_numbers_takes_a_stand_in_copy_and_a_converted_model(tmp_path):
    """Car03's destroy stage: FNV's health, stage and flags; SmallNukeExplosion as a copy of CarNukeLargeVehicles;
    the hulk model converted; DMDT dropped; an unmapped explosion and debris left out and counted."""
    block = [(b'DEST', struct.pack('<iBB2x', 325, 2, 1)), (b'DSTD', _stage(65, 4, 5, 0x100)),
             (b'DMDL', b'Vehicles\\CarHulk03.NIF\0'), (b'DMDT', b'\1' * 12), (b'DSTF', b''),
             (b'DSTD', _stage(0, 5, 0, 0x200, 7, 3)), (b'DMDL', b'Vehicles\\Gone.NIF\0'), (b'DSTF', b'')]
    made = _destruction(tmp_path, {CAR03: block})
    subs = subrecords(made.of(CAR03))
    assert [t for t, _ in subs] == [b'DEST', b'DSTD', b'DMDL', b'DSTF', b'DSTD', b'DSTF']
    assert subs[0][1] == block[0][1] and subs[2][1] == b'fnv\\vehicles\\carhulk03.nif\0'
    assert D.STAGE.unpack(subs[1][1]) == (65, 0, 4, 5, 1, 0x23D3B << 8 | 1, 0, 0)
    assert D.STAGE.unpack(subs[4][1]) == (0, 0, 5, 0, 1, 0, 0, 0)
    assert set(made.builder.counts) == {'destruction explosion route (hand table)',
                                       'destruction explosion left out (00000200)',
                                       'destruction debris left out (00000007)',
                                       'destruction stage model left out (in no archive)'}
    assert made.of(1) == b''


def test_an_unlisted_explosion_takes_a_listed_ones_stand_in_and_debris_converts(tmp_path):
    """BusNuke (unlisted) shares SmallNukeExplosion's art: its stand-in, counted once; FNV debris 7 is written as
    FO4's with its one exported model converted, the other dropped."""
    debris = (pack_subrecord('EDID', b'GoreBits\0') + pack_subrecord('DATA', b'\x32Gore\\Bit01.NIF\0\x01')
              + pack_subrecord('MODT', b'\0' * 8) + pack_subrecord('DATA', b'\x14Gore\\Gone.NIF\0\x01'))
    made = _destruction(tmp_path, {CAR03: [(b'DEST', bytes(8)), (b'DSTD', _stage(0, 5, 0, 0x300, 7, 3)),
                                           (b'DSTF', b'')]}, {7: debris})
    stage = D.STAGE.unpack(subrecords(made.of(CAR03) + made.of(CAR03))[1][1])
    assert stage[5:] == (0x23D3B << 8 | 3, 0x907, 3)
    assert made.builder.counts == collections.Counter({'destruction explosion route (same art)': 1,
                                                       'DEBR (converted)': 1})
    (sig, record), = made.builder.writer.records
    assert sig == 'DEBR' and subrecords(record[24:]) == [(b'EDID', b'FNV_GoreBits\0'),
                                                        (b'DATA', b'\x32fnv\\gore\\bit01.nif\0\x01')]


def _expl(edid: str, radius: int, damage: int, ench: str = '', impacts: str = '0') -> dict:
    """An FNV EXPL export record."""
    return {'EditorID': edid, 'DATA.Radius': str(radius), 'DATA.Damage': str(damage), 'EITM': ench,
            'DATA.ImpactDataSet': impacts}


def test_explosion_routes_go_by_kind_then_damage_nearest_in_size():
    """A fire-enchanted blast takes the fire trap's stand-in (resist value 52 alike, though another effect); an
    unenchanted one the damaging listed one of its impacts, else of nearest radius; with nothing listed, None."""
    names = {'ExplosionTrapGas': 1, 'fragGrenadeExplosion': 2, 'CarExplosion': 3, 'pulseGrenadeExplosion': 4}
    listed = {1: _expl('GasTrapFireBurst', 300, 6, '00000A01'), 2: _expl('AmmoBoxExplosion', 500, 50, impacts='9'),
              3: _expl('LargeExplosion', 650, 150), 4: _expl('vHDGeneratorExplosion', 800, 800, '00000A03')}
    kinds = lambda: X.effect_kinds({0xA01: {'Effect[0].EFID': 'Fire'}, 0xA02: {'Effect[0].EFID': 'Burn'},
                                    0xA03: {'Effect[0].EFID': 'EMP'}},
                                   [{'EditorID': 'Fire', 'DATA.ResistValue': '52'},
                                    {'EditorID': 'Burn', 'DATA.ResistValue': '52'},
                                    {'EditorID': 'EMP', 'DATA.ResistValue': X.NO_RESIST}])
    routes = X.ExplosionRoutes(names, listed, kinds)
    assert routes.route(_expl('Incendiary', 450, 75, '00000A02')) == ('same kind', 'ExplosionTrapGas',
                                                                      'GasTrapFireBurst')
    assert routes.route(_expl('Shell', 1000, 90, impacts='9')) == ('same kind', 'fragGrenadeExplosion',
                                                                   'AmmoBoxExplosion')
    assert routes.route(_expl('Tank', 1000, 5000)) == ('same kind', 'CarExplosion', 'LargeExplosion')
    assert routes.route(_expl('Stun', 450, 15, '00000B00')) == ('same damage', 'CarExplosion', 'LargeExplosion')
    assert routes.route(listed[1]) == ('hand table', 'ExplosionTrapGas', '')
    assert X.ExplosionRoutes(names, {}, kinds).route(_expl('Lone', 10, 0)) is None


def test_destruction_goes_after_the_model_and_makes_a_static_movable():
    """DEST follows MODL in an MSTT and ACTI (xEdit wbDefinitionsFO4 order); a STAT with destruction is an MSTT."""
    dest = pack_subrecord('DEST', bytes(8))
    sig, mstt = _static('STAT', 1, 'X', 'a.nif', (0,) * 6, dest=dest)
    acti = R.pack_acti(2, 'Y', '', 'a.nif', (0,) * 6, b'', '', dest=dest)
    assert sig == 'MSTT'
    for record in (mstt, acti):
        tags = [t for t, _ in subrecords(record[24:])]
        assert tags[tags.index(b'MODL') + 1] == b'DEST'


@pytest.mark.skipif(not FALLOUTNV_ESM.exists(), reason='needs FalloutNV.esm')
def test_car03s_block_reads_from_the_source_plugin():
    """Car03 (MSTT): health 325, six stages, the fifth with its hulk model."""
    block = D.destruction_blocks(source_walk(b'MSTT'))[CAR03]
    assert struct.unpack_from('<iB', block[0][1]) == (325, 6)
    assert sum(t == b'DSTD' for t, _ in block) == 6
    assert (b'DMDL', b'Vehicles\\CarHulk03.NIF\0') in block
