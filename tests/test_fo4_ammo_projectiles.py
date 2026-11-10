"""FNV ammunition on Fallout 4: the projectile each round fires.

See: docs/fork/fo4_pipeline.md#nv-ammo
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import consumables as CS


def test_an_embedded_guns_ammo_fires_its_templates_projectile():
    """write_ammo writes each ammo() on the 5.56 round's DNAM; ammo an embedded gun fires takes the projectile of
    its FO4 template's ammo (the lowest FNV weapon FormID's), other ammo keeps the 5.56 projectile."""
    added = []
    cons = CS.Consumables.__new__(CS.Consumables)
    cons.builder = SimpleNamespace(counts=Counter(), projectiles=SimpleNamespace(ammo=lambda fnv: None),
                                   writer=SimpleNamespace(derive_formid=lambda site, key: 0x03000000 | key,
                                                          add_record=lambda sig, rec: added.append(rec)))
    cons.vanilla = {CS.AMMO_TEMPLATE: (0x1F278, {b'DNAM': struct.pack('<I', 0x481F) + bytes(12)})}
    cons.projectiles, cons.fired_by = {0xC1897: struct.pack('<I', 0x9C663), 0xCABA3: struct.pack('<I', 0xCABA4)}, {}
    cons.pending = {0xA1: (b'', b''), 0xA2: (b'', b'')}
    cons.fired_from(0xA1, 0x20, 0xCABA3)
    cons.fired_from(0xA1, 0x10, 0xC1897)
    cons.write_ammo()
    projectiles = [struct.unpack_from('<I', rec, 24 + 6)[0] for rec in added]
    assert projectiles == [0x9C663, 0x481F]


def test_other_ammo_fires_its_own_fnv_projectile():
    """Ammo no creature gun fires takes the projectile spike.projectiles gives it; a creature gun's still wins."""
    added = []
    cons = CS.Consumables.__new__(CS.Consumables)
    cons.builder = SimpleNamespace(counts=Counter(), projectiles=SimpleNamespace(ammo=lambda fnv: 0x125C9B),
                                   writer=SimpleNamespace(derive_formid=lambda site, key: 0x03000000 | key,
                                                          add_record=lambda sig, rec: added.append(rec)))
    cons.vanilla = {CS.AMMO_TEMPLATE: (0x1F278, {b'DNAM': struct.pack('<I', 0x481F) + bytes(12)})}
    cons.projectiles, cons.fired_by = {0xC1897: struct.pack('<I', 0x9C663)}, {}
    cons.pending = {0xA1: (b'', b''), 0xA2: (b'', b'')}
    cons.fired_from(0xA1, 0x10, 0xC1897)
    cons.write_ammo()
    assert [struct.unpack_from('<I', rec, 24 + 6)[0] for rec in added] == [0x9C663, 0x125C9B]
