"""FNV's base accuracy as an aim model copy (spike.aim_models)."""

import struct

from fo4_import.spike import aim_models as A
from fo4_import.spike import guns


def test_the_cone_is_fnvs_min_spread_fixed_with_no_bloom_or_narrowing():
    """Min and max FNV's spread, no increase per shot, sneak and iron-sights mults 1; recoil kept."""
    dnam = bytearray(64)
    struct.pack_into('<ffff', dnam, 0, 3.5, 7.0, 0.7, 60.0)
    struct.pack_into('<f', dnam, A.CONE_SNEAK, 0.8)
    struct.pack_into('<f', dnam, 24, 125.0)
    struct.pack_into('<f', dnam, A.CONE_IRON, 0.4)
    out = A.fnv_cone(bytes(dnam), 0.7)
    assert struct.unpack_from('<ffff', out, 0) == (struct.unpack('<f', struct.pack('<f', 0.7))[0],) * 2 + (0.0, 60.0)
    assert struct.unpack_from('<f', out, A.CONE_SNEAK)[0] == 1.0 == struct.unpack_from('<f', out, A.CONE_IRON)[0]
    assert struct.unpack_from('<f', out, 24)[0] == 125.0


def test_a_copied_part_loses_its_cone_properties():
    """Min cone and iron-sights mult properties go; the rest stay, the count fixed."""
    prop = struct.Struct('<B3xB3xH2xIIf')
    data = struct.pack('<II', 0, 3) + bytes(8) + prop.pack(1, 1, 33, 0, 0, -0.25) + prop.pack(
        1, 1, 47, 0, 0, -0.4) + prop.pack(1, 2, 72, 0, 0, 1.0)
    out = guns.without_override(data, guns.CONE_PROPERTIES)
    assert out == struct.pack('<II', 0, 1) + bytes(8) + prop.pack(1, 2, 72, 0, 0, 1.0)
