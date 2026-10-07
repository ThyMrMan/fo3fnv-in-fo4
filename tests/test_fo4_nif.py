"""FO4 meshes and materials from FNV statics: formats, tangent convention, specular, glass.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

from pathlib import Path

import numpy as np
import pytest

from fo4_import.nif import bgem, bgsm
from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F

SHELF = Path('export/FalloutNV.esm/meshes/furniture/shelveswoodenhalf02.nif')


def test_tangent_frame_is_du_then_dv():
    """A quad whose u runs along +X and v along +Y: dP/du is +X, dP/dv +Y (FO4 stores dv as 'tangent')."""
    pos = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], float)
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    nrm = np.tile((0.0, 0.0, 1.0), (4, 1))
    du, dv = C.tangent_frame(pos, uv, nrm, np.array([(0, 1, 2), (0, 2, 3)]))
    assert np.allclose(du, (1, 0, 0)) and np.allclose(dv, (0, 1, 0))


def test_glossiness_maps_to_ggx_smoothness():
    """Power 0 is rough; 60 (the FNV shelf) is about 0.58."""
    assert C.smoothness(0.0) == 0.0
    assert C.smoothness(60.0) == pytest.approx(0.5762, abs=1e-3)


def test_spec_map_sits_beside_the_normal_map():
    """x_n.dds gives fnv\\x_s.dds."""
    assert C.spec_map_path('textures\\furniture\\Shelves01_n.dds') == 'fnv\\furniture\\shelves01_s.dds'


@pytest.mark.parametrize('module, template, key', [(bgsm, C.MATERIAL, 'diffuse'), (bgem, C.GLASS_EFFECT, 'base')])
def test_material_templates_write_and_read_back(module, template, key):
    """The lit and glass templates survive write then read unchanged."""
    names = bgsm.TEXTURES if module is bgsm else bgem.TEXTURES
    mat = dict(template, textures={n: '' for n in names})
    mat['textures'][key] = 'fnv/a/b.dds'
    if module is bgsm:
        mat['root_material'] = ''
    assert module.write(module.read(module.write(mat))) == module.write(mat)


@pytest.mark.skipif(not SHELF.exists(), reason='needs the FalloutNV.esm export')
def test_converted_shelf_round_trips_through_the_fo4_reader():
    """The FNV shelf as one lit shape, then its collision as pre-Elric Havok blocks; it reads back identically."""
    converted = C.convert(str(SHELF))
    raw = F.write(converted.nif)
    assert F.write(F.read(raw)) == raw
    assert [k for k, _ in converted.nif.blocks] == ['NiNode', 'BSTriShape', 'BSLightingShaderProperty',
                                                    'BSShaderTextureSet', 'BSXFlags', 'NiTriStripsData',
                                                    'bhkNiTriStripsShape', 'bhkRigidBody', 'bhkCollisionObject']
