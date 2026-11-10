"""FNV grass clamps its texture and keeps vertex colours: the tip triangle and dark flecks came from wrapping.

See: docs/fork/fo4_look.md#grass-flecks
"""
from pathlib import Path

import pytest

from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F

GRASS = Path('export/FalloutNV.esm/meshes/landscape/grass/grasswasteland02.nif')


@pytest.mark.skipif(not GRASS.exists(), reason='needs the FalloutNV.esm export')
def test_grass_clamps_its_texture_and_keeps_vertex_colours():
    """GrassWasteland02's blades: shader clamp 0 and Vertex_Colors; the BGSM tiles in neither direction."""
    converted = C.convert(str(GRASS), 'export/FalloutNV.esm')
    nif = F.read(F.write(converted.nif))
    shaders = [b for k, b in nif.blocks if k == 'BSLightingShaderProperty']
    assert shaders and all(s['clamp'] == 0 and s['flags2'] & C.VERTEX_COLORS for s in shaders)
    assert converted.materials and all(m['tile_flags'] == 0 and '_grass' in path
                                       for path, m in converted.materials.items())
