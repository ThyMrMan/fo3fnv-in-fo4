"""A vertex UV past the half-float range BSVertexData stores (fo4_import.nif.blocks.half_uv)."""

import struct

from fo4_import.nif import blocks as B


def test_a_uv_past_the_half_float_range_is_clamped_and_counted():
    """A UV of 55 million becomes the largest half float, counted; 0.25 stays."""
    before = B.CLAMPED['uv']
    assert B.half_uv((0.5, 55130300.0)) == (0.5, B.HALF_MAX) and B.half_uv((-1e9, 2.0)) == (-B.HALF_MAX, 2.0)
    assert B.half_uv((0.25, 0.75)) == (0.25, 0.75) and B.CLAMPED['uv'] - before == 2


def test_pack_vertex_writes_a_clamped_uv_instead_of_failing():
    """A huge UV packs (it raised OverflowError before)."""
    out = B.pack_vertex({'uv': (55130300.0, 0.5)}, B.VA_UV)
    assert struct.unpack('<2e', out) == (B.HALF_MAX, 0.5)
