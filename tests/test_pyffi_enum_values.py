"""PyFFI enum fields keep a value their nif.xml does not list when set or copied, as a read keeps it.

See: docs/commentary/asset_convert_nif.md#enum-values-kept
"""

from asset_convert.nif import pyffi_monkey_patch
from pyffi.formats.nif import NifFormat


def test_fallout3_tangent_flags_survive_a_strip_to_shape_copy():
    """ExtraVectorsFlags 20 (Fallout 3: tangents plus an unnamed bit) set on strips data survives the shape copy;
    a listed value still sets, and clearing the tangents bit leaves the other bit."""
    assert pyffi_monkey_patch.apply_patches()
    strips = NifFormat.NiTriStrips()
    strips.data = NifFormat.NiTriStripsData()
    strips.data.extra_vectors_flags = 20
    assert strips.data.extra_vectors_flags == 20
    shape = strips.get_interchangeable_tri_shape()
    assert shape.data.extra_vectors_flags == 20
    shape.data.extra_vectors_flags = shape.data.extra_vectors_flags & ~0x10
    assert shape.data.extra_vectors_flags == 4
    shape.data.extra_vectors_flags = 16
    assert shape.data.extra_vectors_flags == 16
