"""Which FormID a converted FNV weapon takes: thrown and placed ones FNV's own, the rest hashed.

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


def _equipment() -> SimpleNamespace:
    """An Equipment stand-in whose builder maps FNV ids to 0x0B000000 + the object id."""
    builder = SimpleNamespace(writer=_Writer(), counts=Counter(), fnv_id=lambda fnv: 0x0B000000 | fnv & 0xFFFFFF)
    passthrough = SimpleNamespace(wire=lambda fnv, fid, subs: subs)
    return SimpleNamespace(builder=builder, condition=passthrough, ammo_mods=SimpleNamespace(wire=lambda f, s: s),
                           fired={})


def test_a_thrown_weapon_keeps_fnv_id_and_a_gun_is_hashed():
    """Animation types 10 to 13 are thrown or placed; a gun (type 3) is not."""
    assert E._thrown({'DNAM.FalloutAnimType': '10'}) and E._thrown({'DNAM.FalloutAnimType': '13'})
    assert not E._thrown({'DNAM.FalloutAnimType': '3'}) and not E._thrown({})


def test_write_takes_fnv_id_when_asked():
    """`own_id` writes on the builder's FNV id (the old static's); otherwise the hashed one."""
    eq = _equipment()
    assert E.Equipment._write(eq, 'WEAP', 0x00004330, [], own_id=True) == 0x0B004330
    assert E.Equipment._write(eq, 'WEAP', 0x00004330, []) == 0x0B00ABCD
