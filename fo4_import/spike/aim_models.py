"""FNV's base accuracy on a converted gun: a copy of its stand-in's aim model with FNV's cone.

FalloutNV.exe fires a shot within (Min Spread + Spread x the actor's spread, which stays 0 for the player) degrees
of the aim (0x523A0C; 0x9AB715 picks a uniform radius and angle), whatever the stance: aiming and crouching change
the player's sway, not the cone, and nothing widens it per shot. So the copy's cone of fire is Min Spread at both
ends, with no increase per shot and sneak and iron-sights mults of 1; its recoil, sway and stability stay the
stand-in's. The copy's FormID is hashed from the FNV gun's (SITE).

See: docs/fork/fo4_combat_feel.md#base-accuracy
"""

import struct

from fo4_import.base.install import plugin_walk
from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV WEAP DNAM offset of Min Spread (float, degrees).
FNV_MIN_SPREAD = 16
#: FO4 AMDL DNAM offsets: cone min and max angle, increase per shot, sneak mult, iron sights mult (floats).
CONE_MIN, CONE_MAX, CONE_INCREASE, CONE_SNEAK, CONE_IRON = 0, 4, 8, 20, 56
SITE = 'FNV AMDL copy'


def fnv_min_spreads(plugin: bytes) -> dict:
    """{FNV WEAP FormID: Min Spread} of `plugin`'s weapons with a DNAM long enough."""
    out = {}
    for rec, _ in plugin_walk(plugin, b'WEAP'):
        dnam = first_sub(rec.body, b'DNAM') or b''
        if len(dnam) >= FNV_MIN_SPREAD + 4:
            out[rec.form_id] = struct.unpack_from('<f', dnam, FNV_MIN_SPREAD)[0]
    return out


def fnv_cone(dnam: bytes, spread: float) -> bytes:
    """AMDL DNAM `dnam` with a fixed cone of `spread` degrees: no bloom, no sneak or iron-sights narrowing."""
    out = bytearray(dnam)
    struct.pack_into('<fff', out, CONE_MIN, spread, spread, 0.0)
    struct.pack_into('<f', out, CONE_SNEAK, 1.0)
    if len(out) >= CONE_IRON + 4:
        struct.pack_into('<f', out, CONE_IRON, 1.0)
    return bytes(out)


class AimModels:
    """The aim model copies of one build, each written once."""

    def __init__(self, builder):
        """Index Fallout4.esm's aim models and FNV's Min Spreads."""
        self.builder, self.made = builder, {}
        self.vanilla = {rec.form_id: list(subrecords(rec.body)) for rec, _ in walk(builder.fo4, b'AMDL')}
        self.spreads = fnv_min_spreads(None)

    def of(self, fnv: int, edid: str, stand_in: int) -> int:
        """The aim model gun `fnv` (EditorID `edid`) uses: a copy of `stand_in` with FNV's cone, else it."""
        subs, spread = self.vanilla.get(stand_in), self.spreads.get(fnv & 0xFFFFFF)
        if not subs or spread is None or b'DNAM' not in dict(subs):
            return stand_in
        if fnv not in self.made:
            fid = self.made[fnv] = self.builder.writer.derive_formid(SITE, fnv)
            swap = {b'EDID': f'FNV_{edid}_AM\0'.encode(), b'DNAM': fnv_cone(dict(subs)[b'DNAM'], spread)}
            body = b''.join(pack_subrecord(t.decode(), swap.get(t, d)) for t, d in subs)
            self.builder.writer.add_record('AMDL', pack_fo4_record('AMDL', fid, 0, body))
            self.builder.counts['AMDL (FNV cone)'] += 1
        return self.made[fnv]
