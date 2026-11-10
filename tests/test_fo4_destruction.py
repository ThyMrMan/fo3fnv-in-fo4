"""FNV destruction data (DEST) as FO4's: stages kept, explosions as stand-in copies, models converted.

See: docs/fork/fo4_pipeline.md#damage-stages
"""

import collections
import struct
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUTNV_ESM, source_walk
from fo4_import.spike import destruction as D
from fo4_import.spike import records as R
from fo4_import.spike.cell import _static
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

CAR03 = 0x17790


class _Copies:
    """ProjectileCopies' explosion copier: FNV explosion 0x100 is SmallNukeExplosion, 0x200 has no stand-in."""

    def __init__(self):
        """FNV's explosions by FormID."""
        self.explosions = {0x100: {'EditorID': 'SmallNukeExplosion'}, 0x200: {'EditorID': 'NoSuchExplosion'}}

    def explosion(self, stand_in: int, fnv: int) -> int:
        """A copy id naming both."""
        return stand_in << 8 | fnv >> 8


def _destruction(tmp_path, blocks: dict) -> D.Destruction:
    """A Destruction over `blocks`, Fallout4.esm's CarNukeLargeVehicles at 0x23D3B, an export holding one mesh."""
    (tmp_path / 'meshes' / 'vehicles').mkdir(parents=True)
    (tmp_path / 'meshes' / 'vehicles' / 'carhulk03.nif').write_bytes(b'')
    made = D.Destruction.__new__(D.Destruction)
    made.builder = SimpleNamespace(projectiles=SimpleNamespace(copies=_Copies()), counts=collections.Counter(),
                                   export_dir=tmp_path, mesh=lambda m: (f'fnv\\{m.lower()}', None))
    made.blocks, made.explosions, made.debris, made.debris_names = blocks, {'CarNukeLargeVehicles': 0x23D3B}, {}, {7: 'X'}
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
    assert set(made.builder.counts) == {'destruction explosion left out (NoSuchExplosion)',
                                       'destruction debris left out (X)',
                                       'destruction stage model left out (in no archive)'}
    assert made.of(1) == b''


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
