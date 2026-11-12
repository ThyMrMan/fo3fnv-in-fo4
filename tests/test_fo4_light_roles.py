"""Key lights cast shadows: the copy's flags and name, and the per-cell cap by radius.

See: docs/fork/fo4_look.md#route-lights
"""
import collections
import struct
from types import SimpleNamespace

from fo4_import.spike import light_roles as LR
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords


def test_key_is_a_word_of_the_editor_id():
    """Key as its own word in any case; a word merely containing it is not."""
    assert LR.is_key('VaultLightKeyCool') and LR.is_key('key_warm') and LR.is_key('NVKeyLight')
    assert not LR.is_key('VaultLightFill') and not LR.is_key('MonkeyLamp')


def test_the_shadow_copy_casts_an_omni_shadow_and_keeps_the_rest():
    """The copy renames to _Shadow, adds Shadow OmniDirectional, clips its shadow at NEAR_CLIP, keeps the rest."""
    light = (512, (255, 200, 150), 0x1 | 0x8, 1.0, 90.0, (0.2, 0.3, 0.0))
    record = R.pack_ligh(0x100, 'FNV_LightKey', (0,) * 6, '', light, 1.5)
    copy = dict(subrecords(LR.shadow_copy(record, 0x200)[LR.HEADER:]))
    source = dict(subrecords(record[LR.HEADER:]))
    assert copy[b'EDID'] == b'FNV_LightKey_Shadow\0'
    assert struct.unpack_from('<I', copy[b'DATA'], LR.FLAGS_AT)[0] == 0x1 | 0x8 | LR.SHADOW_OMNI
    assert copy[b'DATA'][:LR.FLAGS_AT] == source[b'DATA'][:LR.FLAGS_AT] and copy[b'FNAM'] == source[b'FNAM']
    assert struct.unpack_from('<f', copy[b'DATA'], LR.NEAR_CLIP_AT)[0] == LR.NEAR_CLIP == 64.0
    assert abs(struct.unpack_from('<f', source[b'DATA'], LR.NEAR_CLIP_AT)[0] - 7.217) < 1e-4
    after = LR.NEAR_CLIP_AT + 4
    assert copy[b'DATA'][LR.FLAGS_AT + 4:LR.NEAR_CLIP_AT] == source[b'DATA'][LR.FLAGS_AT + 4:LR.NEAR_CLIP_AT]
    assert copy[b'DATA'][after:] == source[b'DATA'][after:]
    assert struct.unpack_from('<I', LR.shadow_copy(record, 0x200), 12)[0] == 0x200


def test_each_cell_shadows_its_widest_key_lights_up_to_the_cap():
    """Nine Key references: the six widest (a reference's own radius first) place the copy; a Fill never does."""
    shadows = LR.ShadowLights.__new__(LR.ShadowLights)
    shadows.builder = SimpleNamespace(counts=collections.Counter())
    shadows.radii, shadows.copies = {0xA: 100.0}, {0xA: 0xF00A}
    refs = [{'FormID': f'{i:08X}', 'NAME': '0000000A', 'XRDS.Radius': str(10 * i)} for i in range(1, 10)]
    refs.append({'FormID': '000000FF', 'NAME': '0000000B'})
    chosen = shadows.chosen(refs)
    assert chosen == {f'{i:08X}' for i in range(4, 10)}
    assert shadows.base_of(refs[8], 0xA, chosen) == 0xF00A and shadows.base_of(refs[0], 0xA, chosen) == 0xA
    assert shadows.base_of(refs[9], 0xB, chosen) == 0xB and shadows.builder.counts['key lights casting a shadow'] == 1
