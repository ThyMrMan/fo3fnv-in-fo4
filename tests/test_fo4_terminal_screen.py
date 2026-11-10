"""A converted terminal's screen: the largest unlit shape FNV textures, never a glare pane drawn through WHITE.

See: docs/fork/fo4_pipeline.md#terminals
"""

from types import SimpleNamespace

from fo4_import.nif import terminal as T
from fo4_import.nif.convert_static import WHITE


def _nif(texture: str) -> SimpleNamespace:
    """A mesh whose block 0 is an unlit effect shader drawing `texture`."""
    return SimpleNamespace(blocks=[('BSEffectShaderProperty', {'name': -1, 'source_texture': texture})])


def test_a_screen_textured_shape_is_a_screen():
    """vcontrolpanel04's glass, textured vcontrolpanelsscreen01, carries the menu."""
    assert T._unlit(_nif('textures\fnv\dungeons\vault\vcontrolpanelsscreen01.dds'), {'shader': 0})


def test_an_untextured_glare_pane_is_not_a_screen():
    """Its larger untextured falloff pane, drawn through WHITE, does not."""
    assert not T._unlit(_nif(WHITE), {'shader': 0})
    assert not T._unlit(_nif(''), {'shader': 0})
