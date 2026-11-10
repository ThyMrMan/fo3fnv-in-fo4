"""The Classic Look plugin: shadow copies lose their shadows, FNV imagespaces take Classic LUTs, nothing else.

See: docs/fork/fo4_look.md#route-lights
"""
import struct

import numpy as np
import pytest

from fo4_import import classic_look as CL
from fo4_import.base.install import masters_of
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike import imagespace as IM
from fo4_import.spike import light_roles as LR
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

LIGHT = (512, (255, 200, 150), 0x1, 1.0, 90.0, (0.2, 0.3, 0.0))


def _imgs(fid: int, lut: str) -> bytes:
    """An IMGS with the base HDR (Tonemap E 0.02, middle grey 0.18) and TX00 `lut`."""
    hnam = struct.pack('<9f', 10.0, 0.02, 0.5, 0.2, 15.0, 0.5, 1.0, 1.0, 0.18)
    return pack_fo4_record('IMGS', fid, 0, pack_subrecord('EDID', b'FNV_Test\0') + pack_subrecord('HNAM', hnam)
                           + pack_subrecord('TX00', lut.encode() + b'\0'))


def _built(tmp_path):
    """A built plugin with a Key light, its shadow copy, an FNV imagespace and its LUT file; its path."""
    writer = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False)
    key = R.pack_ligh(0x01000800, 'FNV_LightKey', (0,) * 6, '', LIGHT, 1.0)
    writer.add_record('LIGH', key)
    writer.add_record('LIGH', LR.shadow_copy(key, 0x01000801))
    writer.add_record('IMGS', _imgs(0x01000802, f'{IM.LUT_FOLDER}\\FNV_Test.dds'))
    writer.next_object_id = 0x01000900
    plugin = tmp_path / 'FalloutNV.esm'
    writer.write(str(plugin))
    IM.write_lut(IM.Cinematic(1.0, (1.0, 1.0, 1.0), 0.0), 'FNV_Test', tmp_path)
    return plugin


def test_classic_overrides_only_shadow_copies_and_fnv_imagespaces(tmp_path):
    """One light (the copy, now shadowless) and one imagespace, on the built FormIDs, the built plugin a master."""
    plugin = _built(tmp_path)
    assert CL.build(plugin, tmp_path, tmp_path / 'out') == {'LIGH': 1, 'IMGS': 1}
    data = (tmp_path / 'out' / 'FalloutNV - Classic Look.esl').read_bytes()
    assert masters_of(data) == ['Fallout4.esm', 'FalloutNV.esm']
    made = {rec.form_id: dict(subrecords(rec.body)) for rec, _ in walk(data, b'LIGH', b'IMGS')}
    assert set(made) == {0x01000801, 0x01000802}
    assert struct.unpack_from('<I', made[0x01000801][b'DATA'], CL.FLAGS_AT)[0] & CL.SHADOWS == 0
    assert made[0x01000802][b'TX00'] == f'{CL.CLASSIC_FOLDER}\\FNV_Test.dds'.encode() + b'\0'
    assert struct.unpack_from('<2f', made[0x01000802][b'HNAM'], 16) == pytest.approx((1.40, 1.40), abs=0.01)
    assert (tmp_path / 'out' / 'Textures/Effects/LUTs/FNVClassic/FNV_Test.dds').is_file()


def test_the_classic_lut_of_an_identity_shows_fnvs_straight_display():
    """At the classic exposure, FO4's curve then the Classic LUT show exposed colour c as c^(1/2.2)."""
    tonemap_e, grey = 0.02, 0.18
    lut = IM.read_lut(IM.lut_dds(CL.classic_lut(IM.read_lut(IM.lut_dds(IM.identity())), (tonemap_e, grey))))
    c = np.array([[0.05, 0.05, 0.05], [0.18, 0.18, 0.18], [0.5, 0.5, 0.5]])
    shown = IM.apply_lut(IM.fo4_display(CL.classic_exposure(tonemap_e, grey) * c, tonemap_e), lut)
    assert shown == pytest.approx(c ** (1 / 2.2), abs=0.02)
