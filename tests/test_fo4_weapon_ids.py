"""A converted FNV weapon takes a hashed FormID, thrown ones included, so a weapon already built never moves.

See: docs/fork/fo4_thrown_weapons.md#checks
"""

from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import equipment as E


class _Writer:
    """Hashes to a fixed id and keeps what is added."""

    def __init__(self):
        """Nothing added yet."""
        self.added = []

    def derive_formid(self, site: str, key) -> int:
        """The hashed id."""
        return 0x0B00ABCD

    def add_record(self, sig: str, data: bytes) -> None:
        """Keep `data` of type `sig`."""
        self.added.append((sig, data))


def test_a_weapon_takes_its_hashed_id():
    """_write puts a WEAP on the writer's hashed id, never the builder's FNV id."""
    builder = SimpleNamespace(writer=_Writer(), counts=Counter(), fnv_id=lambda fnv: 0x0B000000 | fnv)
    eq = SimpleNamespace(builder=builder, condition=SimpleNamespace(wire=lambda fnv, fid, subs: subs),
                         ammo_mods=SimpleNamespace(wire=lambda f, s: s), fired={})
    assert E.Equipment._write(eq, 'WEAP', 0x00004330, []) == 0x0B00ABCD
