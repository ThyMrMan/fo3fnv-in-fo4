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


def _efsh(edid: str, fill: tuple, edge: tuple, flags: int = 0, particles: str = '') -> dict:
    """An FNV EFSH export record."""
    colors = {f'DATA.{part}Color{c}': str(v) for part, rgb in (('Fill', fill), ('Edge', edge))
              for c, v in zip('RGB', rgb)}
    return {'EditorID': edid, 'DATA.Flags': str(flags), 'ICO2': particles, **colors}


#: The export's shaders: the two listed, a shock one on the pulse's sparks, a pale green one on no listed texture.
EXPORT = [_efsh('NightkinCloakFXShader', (119, 218, 255), (164, 206, 240), 8),
          _efsh('PulseDisableFXShader', (119, 218, 255), (164, 206, 240), 0, 'Effects\\FXShockParticles01.dds'),
          _efsh('ModShockShader', (0, 0, 0), (0, 0, 0), 0, 'effects/fxshockparticles01.dds'),
          _efsh('ModPaleShader', (100, 200, 250), (160, 200, 240), 0)]


#: A mod's stealth armor script: its shader where the Chameleon spell changes, its death shader in another branch.
STEALTH_ARMOR = {
    'EFSH': [_efsh('ModStealthShader', (0, 0, 0), (0, 0, 0), 1), _efsh('ModDeathShader', (0, 0, 0), (0, 0, 0), 1)],
    'SPEL': [{'EditorID': 'ModCloakSpell', 'EffectCount': '2', 'Effect[0].ActorValue': '42',
              'Effect[1].ActorValue': '49'}],
    'SCPT': [{'SCTX': 'scn ModArmorScript\r\nBEGIN GameMode\r\n\tif bOn == 1 ; cloak\r\n\t\tPMS ModStealthShader\r\n'
                      '\t\tplayer.AddSpell ModCloakSpell\r\n\tendif\r\n\tif GetDead\r\n\t\tpms ModDeathShader\r\n'
                      '\tendif\r\nEND\r\n'}],
    'INFO': [{'ResultScript': 'pms ModDeathShader'}], 'PACK': [{'OnBegin.Script': 'RemoveSpell OtherSpell'}]}


def _shaders(monkeypatch, table: dict = TABLE, export: 'dict | None' = None) -> E.EffectShaders:
    """EffectShaders over a Fallout4.esm of the table's two targets and `export` {type: records} (EFSH: EXPORT)."""
    fo4 = [(SimpleNamespace(form_id=f, body=pack_subrecord('EDID', f'{e}\0'.encode())), None)
           for f, e in ((STEALTH, 'StealthBoyInvisibilityEffect'), (SHOCK, 'ShockDamageFXS'))]
    monkeypatch.setattr(E, 'walk', lambda raw, *sigs: fo4)
    monkeypatch.setattr(E, 'export_records', lambda folder, sig: (export or {'EFSH': EXPORT}).get(sig, []))
    return E.EffectShaders(SimpleNamespace(fo4=b'', counts=Counter(), export_dir='x'), table)


def test_a_shader_played_where_a_cloak_spell_changes_is_the_stealth_boys(monkeypatch):
    """The armor's shader shares a branch with AddSpell of a Chameleon spell: the stealth boy's. Its death shader,
    the same black untextured kind but in another branch, routes by color, never onto the cloak's stealth boy."""
    found = _shaders(monkeypatch, export={**STEALTH_ARMOR, 'EFSH': EXPORT + STEALTH_ARMOR['EFSH']})
    assert found.of('ModStealthShader') == STEALTH and found.of('ModDeathShader') == SHOCK
    assert found.stealth == {'modstealthshader'}
    assert found.builder.counts == Counter({'EffectShader route (stealth)': 1,
                                            'EffectShader route (nearest color)': 1})


def test_script_branches_split_at_control_lines_and_drop_comments():
    """A branch per if/else/end line; comments dropped."""
    assert E.branches('scn X\r\nbegin GameMode\r\n  pms A ; addspell B\r\nelse\r\naddspell C\r\nend') == [
        'scn X\n', 'begin GameMode\npms A\n', 'else\naddspell C\n', 'end\n']


def test_an_unlisted_shader_takes_a_listed_ones_by_texture_then_color(monkeypatch):
    """The mod's shock shader shares the pulse's particle texture; the pale one is as near the cloak's colors as the
    pulse's, but the cloak plays as the stealth boy, which only stealth shaders reach; each route counted once."""
    found = _shaders(monkeypatch)
    assert found.of('modshockshader') == SHOCK and found.of('ModShockShader') == SHOCK
    assert found.of('ModPaleShader') == SHOCK
    assert found.builder.counts == Counter({'EffectShader route (same particle texture)': 1,
                                            'EffectShader route (nearest color)': 1})


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
