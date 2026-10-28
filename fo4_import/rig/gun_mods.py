"""An own-rig creature's guns, equipped all at once as FO4's robots and turrets equip theirs: an actor object mod
per gun forcing it into the inventory (ForcedInventory) at an attach point named for its equip slot, the NPC
offering those attach points (APPR) and including the mods in its default object template combination.

See: docs/fork/fo4_own_rig.md#ranged
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import records as R
from fo4_import.spike.ammo_mods import ADD, FORM, FORM_VALUE2, omod_data, prop
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

SITE = 'FNV RIG gun'
#: Actor object mod property ForcedInventory (xEdit's wbActorPropertyEnum); keyword type Attach Point.
FORCED_INVENTORY, ATTACH_POINT = 1, 2
#: An object template combination with one include per mod: counts, levels, no addon index, default, no keywords.
OBTS_HEAD = struct.Struct('<II4xhBxxx')
#: The NPC subrecords this replaces, and the one its attach points and object template go before (vanilla's order).
REPLACED, BEFORE = (b'APPR', b'OBTE', b'OBTF', b'OBTS', b'STOP'), b'CNAM'


def obts(mods: list) -> bytes:
    """A default object template combination including `mods`, each always used."""
    return OBTS_HEAD.pack(len(mods), 0, -1, 1) + b''.join(struct.pack('<IBBB', mod, 0, 0, 1) for mod in mods)


def with_forced(points: list, mods: list):
    """A record edit giving an NPC attach points `points` and one default object template combination of `mods`,
    before its CNAM; None without mods."""
    if not mods:
        return None
    block = (pack_subrecord('APPR', struct.pack(f'<{len(points)}I', *points))
             + pack_subrecord('OBTE', struct.pack('<I', 1)) + pack_subrecord('OBTF', b'')
             + pack_string_subrecord('FULL', 'Default') + pack_subrecord('OBTS', obts(mods))
             + pack_subrecord('STOP', b''))

    def edit(subs: bytes) -> bytes:
        """The subrecords with the attach points and object template replaced."""
        out, skipping = b'', False
        for tag, data in subrecords(subs):
            skipping = tag in REPLACED[1:4] or (skipping and tag == b'FULL')
            out += block if tag == BEFORE else b''
            if tag not in REPLACED and not skipping:
                out += pack_subrecord(tag.decode(), data)
        return out
    return edit


class GunMods:
    """The build's gun mods and their attach points, each written once."""

    def __init__(self, builder):
        self.builder, self.points, self.mods = builder, {}, {}

    def point(self, slot: int) -> int:
        """The attach point keyword of equip slot `slot` (an EQUP FormID)."""
        if slot not in self.points:
            edid = f'FNV_ap_GunSlot{slot:08X}'
            self.points[slot] = fid = self.builder.writer.derive_formid(SITE, edid)
            self.builder.writer.add_record('KYWD', R.pack_kywd(fid, edid, ATTACH_POINT))
        return self.points[slot]

    def mod(self, fnv: int, gun: int, slot: int) -> int:
        """The actor mod forcing FO4 gun `gun` (FNV's `fnv`, in equip slot `slot`) into the inventory."""
        if fnv not in self.mods:
            self.mods[fnv] = fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X}')
            data = omod_data(self.point(slot), [prop(FORM, ADD, FORCED_INVENTORY, struct.pack('<I', gun),
                                                     struct.pack('<I', FORM_VALUE2))], b'NPC_')
            subs = pack_string_subrecord('EDID', f'FNV_mod_Gun{fnv:08X}') + pack_subrecord('DATA', data)
            self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', fid, 0, subs))
        return self.mods[fnv]

    def edit(self, guns: list):
        """with_forced() of `guns` [(FNV FormID, FO4 gun, slot)], each slot's first."""
        first = {slot: (fnv, gun) for fnv, gun, slot in reversed(guns)}
        return with_forced([self.point(slot) for slot in first],
                           [self.mod(fnv, gun, slot) for slot, (fnv, gun) in first.items()])
