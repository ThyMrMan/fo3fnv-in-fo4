"""A trap's trigger volume (bhkSimpleShapePhantom) converts, on FNV's trigger layer, after every NiNode.

See: docs/fork/fo4_pipeline.md#trap-triggers
"""
import struct
from pathlib import Path

import pytest

from fo4_import.nif import convert_static as C
from fo4_import.nif import file as F

BEAR_TRAP = next(Path('export/FalloutNV.esm/meshes').rglob('beartrap01.nif'), None) \
    if Path('export/FalloutNV.esm/meshes').exists() else None
#: FNV's and FO4's trigger collision layer.
TRIGGER = 12


@pytest.mark.skipif(BEAR_TRAP is None, reason='needs the FalloutNV.esm export')
def test_the_bear_traps_trigger_converts_on_the_trigger_layer():
    """One phantom in a bhkSPCollisionObject, layer 12, and no NiNode after the first Havok block."""
    nif = F.read(F.write(C.convert(str(BEAR_TRAP), 'export/FalloutNV.esm').nif))
    kinds = [k for k, _ in nif.blocks]
    phantoms = [b for k, b in nif.blocks if k == 'bhkSimpleShapePhantom']
    assert len(phantoms) == 1 and 'bhkSPCollisionObject' in kinds
    assert struct.unpack_from('<B', phantoms[0], 4)[0] == TRIGGER
    first = min(i for i, k in enumerate(kinds) if k.startswith('bhk'))
    assert 'NiNode' not in kinds[first:]
