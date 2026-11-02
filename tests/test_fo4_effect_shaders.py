"""Which Fallout 4 effect shader a converted FNV script's EffectShader property plays (spike.effect_shaders).

See: docs/fork/script_markers.md#effect-shaders
"""
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import effect_shaders as E
from fo4_import.spike.attach import ObjectScripts
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.writer import pack_subrecord

STEALTH, SHOCK = 0x102B7E, 0x6F122
TABLE = {'NightkinCloakFXShader': 'StealthBoyInvisibilityEffect', 'PulseDisableFXShader': 'ShockDamageFXS'}


def _shaders(monkeypatch, table: dict = TABLE) -> E.EffectShaders:
    """EffectShaders over a Fallout4.esm of the table's two targets."""
    fo4 = [(SimpleNamespace(form_id=f, body=pack_subrecord('EDID', f'{e}\0'.encode())), None)
           for f, e in ((STEALTH, 'StealthBoyInvisibilityEffect'), (SHOCK, 'ShockDamageFXS'))]
    monkeypatch.setattr(E, 'walk', lambda raw, *sigs: fo4)
    return E.EffectShaders(SimpleNamespace(fo4=b'', counts=Counter()), table)


def test_a_property_plays_its_fo4_shader_ignoring_case(monkeypatch):
    """The property's FNV name, in any case, gives the table's FO4 shader."""
    found = _shaders(monkeypatch)
    assert found.of('NightkinCloakFXShader') == STEALTH and found.of('pulsedisablefxshader') == SHOCK


def test_an_unmapped_shader_is_counted_once(monkeypatch):
    """A shader the table leaves out gives None, counted once."""
    found = _shaders(monkeypatch)
    assert found.of('OddShader') is None and found.of('oddshader') is None
    assert found.builder.counts == Counter({'EffectShader not mapped (OddShader)': 1})


def test_a_target_fallout4_lacks_is_refused(monkeypatch):
    """A table naming a shader Fallout4.esm lacks raises."""
    with pytest.raises(ValueError):
        _shaders(monkeypatch, {'Odd': 'NoSuchShader'})


@pytest.mark.parametrize('kind, owner', [('EffectShader', 'effect_shaders'), ('ImageSpaceModifier', 'imods'),
                                         ('Package', 'packages'), ('Idle', 'idles')])
def test_attach_fills_a_named_property_from_its_maker(kind, owner):
    """The property filler asks the builder's maker for the property's name."""
    maker = SimpleNamespace(of=lambda name: (owner, name), modifier=lambda name: (owner, name),
                            named=lambda name: (owner, name))
    scripts = object.__new__(ObjectScripts)
    scripts.builder = SimpleNamespace(**{owner: maker})
    assert scripts._made(kind, 'NightkinCloakFXShader') == (owner, 'NightkinCloakFXShader')


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_the_table_names_real_shaders():
    """Every target is a Fallout4.esm shader; every key an FNV one (when the export is here)."""
    fo4 = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')
           for r, _ in walk(FALLOUT4_ESM.read_bytes(), b'EFSH')}
    table = E.load_table()
    assert set(table.values()) <= fo4
    export = E.TABLE.parents[2] / 'export' / 'FalloutNV.esm'
    if (export / 'EFSH.txt').exists():
        assert {k.lower() for k in table} <= {r['EditorID'].lower() for r in export_records(export, 'EFSH')}
