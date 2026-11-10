"""Light-only region imposters (the Strip's night glow) are kept and placed Is Full LOD.

See: docs/fork/fo4_look.md#route-horizon
"""
import struct
from types import SimpleNamespace

from fo4_import.spike import glow_cards as GC
from fo4_import.spike import records as R


def test_only_imposters_whose_mesh_is_light_only_are_glow_cards(monkeypatch, tmp_path):
    """Of three imposters and a plain ref, the two placing the unlit card count; a lit skyline copy does not."""
    records = {'REFR': [{'FormID': f'0000000{i}', 'NAME': base} for i, base in ((1, '0A'), (2, '0A'), (3, '0B'),
                                                                               (4, '0A'))],
               'ACTI': [{'FormID': '0000000A', 'Model.MODL': 'strip\\glow.nif'}],
               'STAT': [{'FormID': '0000000B', 'Model.MODL': 'strip\\wall.nif'}], 'MSTT': []}
    monkeypatch.setattr(GC, 'imposters', lambda: frozenset({1, 2, 3}))
    monkeypatch.setattr(GC, 'export_records', lambda _dir, sig: records[sig])
    monkeypatch.setattr(GC, 'light_only', lambda _dir, model: model == 'strip\\glow.nif')
    GC.glow_cards.cache_clear()
    assert GC.glow_cards(tmp_path) == {1, 2}
    GC.glow_cards.cache_clear()


def test_unlit_blend_needs_both_the_unlit_shader_and_blending():
    """An unlit shape with blending is light; without blending, or lit, it is not."""
    unlit, lit = type('BSShaderNoLightingProperty', (), {}), type('BSShaderPPLightingProperty', (), {})
    blend = type('NiAlphaProperty', (), {'flags': 0x10ED})
    shape = lambda *props: SimpleNamespace(get_properties=lambda: list(props))
    assert GC.unlit_blend(shape(unlit(), blend()))
    assert not GC.unlit_blend(shape(unlit())) and not GC.unlit_blend(shape(lit(), blend()))


def test_a_full_lod_reference_carries_the_flag_beside_persistent():
    """pack_refr's full_lod sets 0x10000; persistent keeps 0x400."""
    flags = struct.unpack_from('<I', R.pack_refr(0x10, 0x20, (0, 0, 0), (0, 0, 0), full_lod=True), 8)[0]
    assert flags == R.FULL_LOD | 0x400
