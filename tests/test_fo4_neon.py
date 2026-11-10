"""Neon as vanilla builds it: the saloon's SAL tubes additive at vanilla's neon scale, the glow bake not linearised.

See: docs/fork/fo4_look.md#route-neon
"""
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F
from fo4_import.nif.glow_scale import fo4_glow

SALOON_LIGHTS = Path('export/FalloutNV.esm/meshes/architecture/goodsprings/nv_prospectorsaloon-neon_lights.nif')


def _dds(rgba: np.ndarray) -> bytes:
    """An RGBA array as a DDS file."""
    out = io.BytesIO()
    Image.fromarray(rgba.astype(np.uint8), 'RGBA').save(out, 'DDS')
    return out.getvalue()


@pytest.mark.skipif(not SALOON_LIGHTS.exists(), reason='needs the FalloutNV.esm export')
def test_the_sal_tubes_are_additive_ranked_as_unlit_tubes():
    """Shape05's blended unlit tubes (emission x7.5, animated) blend additively at fo4_glow('tube', 7.5)."""
    nif = F.read(F.write(C.convert(str(SALOON_LIGHTS), 'export/FalloutNV.esm').nif))
    shapes = {nif.strings[b['name']]: b for k, b in nif.blocks if k == 'BSTriShape'}
    for name in ('Shape05:0', 'Shape05:1'):
        shape = shapes[name]
        assert nif.blocks[shape['alpha_property']][1]['alpha_flags'] == C.NEON_ALPHA[0]
        assert nif.blocks[shape['shader']][1]['base_color_scale'] == pytest.approx(fo4_glow('tube', 7.5))


def test_the_neon_bake_is_raised_to_white_and_linear():
    """With a cut the bake is raised to white and linearised: a half-bright texel drops to its ^ 2.2."""
    diffuse = np.zeros((4, 4, 4))
    diffuse[..., :3], diffuse[..., 3] = 200, 255
    glow = np.zeros((4, 4, 4))
    glow[..., 3], glow[:2, ..., :3], glow[2:, ..., :3] = 255, 255, 128
    baked = np.asarray(C.glow_image(_dds(diffuse), _dds(glow), cut=64))
    assert baked[0, 0, 0] == 255 and baked[3, 3, 0] == pytest.approx(255 * (128 / 255) ** 2.2, abs=2)
