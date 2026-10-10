"""FNV AI packages as FO4 package instances, for the cell spike.

FO4 packages, like Skyrim's, are instances of template packages filled with
data inputs. Each FNV package becomes a copy of a vanilla FO4 instance of the
matching template with its destination, conditions and EditorID replaced:
Travel to a reference (a Sit when the reference is furniture: FNV seats an
actor who travels to a chair), Sandbox, and Dialogue with the player on
the GREETING (a ForceGreet on the Greeting subtype, waiting at FNV's
location, as 108 vanilla force greets do). The copied instances have no
conditions, scripts or owner quest and a direct reference as first input.
Other package types, and packages naming forms or conditions that do not
convert, are left out and counted.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.say_topics import conditions_of
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Vanilla instances copied per template (Parsons' travel, a Children of Atom sit, a Minutemen sandbox, Kendra's greet).
INSTANCES = {'Travel': 0x248982, 'Sit': 0x2471DB, 'Sandbox': 0x24674E, 'ForceGreet': 0x1BEAD3}
#: FNV PKDT types converted.
FNV_TRAVEL, FNV_SANDBOX, FNV_DIALOGUE = '6', '12', '15'
#: FNV PTDT target of a Dialogue package that talks to the player.
PLAYER_TARGET = '00000014'
#: FNV PLDT location types FO4 shares: near reference, in cell, near current (package start) location, editor location.
SHARED_LOCATIONS = ('0', '1', '2', '3')
NEAR_REFERENCE = 0
#: PKDT general flags FNV and FO4 define alike (xEdit wbPackageFlags), e.g. Weapons Unequipped 0x200000.
SHARED_FLAGS = 0x1 | 0x4 | 0x40 | 0x80 | 0x200 | 0x400 | 0x20000 | 0x40000 | 0x200000 | 0x800000 | 0x8000000
#: PTDA target type: a specific reference.
TARGET_REFERENCE = 0


class Packages:
    """FO4 copies of FNV packages; `package` writes one through the builder, `greets` lists the force greets."""

    def __init__(self, builder, export_dir, furniture: set):
        """Index FNV packages and read the vanilla instances; `furniture` holds the FNV references that are seats."""
        self.builder, self.furniture, self.made, self.greets = builder, furniture, {}, []
        self.packs = {r['FormID']: r for r in export_records(export_dir, 'PACK')}
        wanted = {fid: name for name, fid in INSTANCES.items()}
        self.vanilla = {wanted[r.form_id]: r.body for r, _ in walk(builder.fo4, b'PACK') if r.form_id in wanted}

    def for_npc(self, npc: dict, form_map: dict) -> list:
        """FO4 FormIDs of FNV NPC `npc`'s packages that convert, in its order; `form_map` maps FNV forms."""
        out = []
        for i in range(int(npc.get('AIPackageCount', 0) or 0)):
            fid = self.package(npc[f'AIPackage[{i}]'], form_map)
            out += [fid] if fid else []
        return out

    def package(self, fnv: str, form_map: dict) -> int:
        """The FO4 package for FNV package `fnv` (made once), 0 when it does not convert."""
        if fnv not in self.made:
            rec = self.packs[fnv]
            plan = self._plan(rec, form_map)
            conditions = conditions_of(rec, form_map, {})
            if plan is None or conditions is None:
                self.builder.counts[f'package left out: {rec["EditorID"]}'] += 1
                self.made[fnv] = 0
            else:
                self.made[fnv] = fid = self.builder.fnv_id(fnv)
                self.builder.writer.add_record('PACK', pack_package(fid, f'FNV_{rec["EditorID"]}',
                                                                   self.vanilla[plan[0]], plan[1], conditions,
                                                                   int(rec.get('PKDT.Flags', 0))))
                self.builder.counts['PACK'] += 1
                self.greets += [fid] if plan[0] == 'ForceGreet' else []
        return self.made[fnv]

    def _plan(self, rec: dict, form_map: dict) -> 'tuple | None':
        """(template, first input payload) for FNV package `rec`; None when it does not convert."""
        kind, place = rec.get('PKDT.Type'), rec.get('PLDT.Type')
        if kind not in (FNV_TRAVEL, FNV_SANDBOX, FNV_DIALOGUE) or place not in SHARED_LOCATIONS or (
                kind == FNV_DIALOGUE and not _greets_player(rec)):
            return None
        ref = int(rec.get('PLDT.Location', '0'), 16)
        if int(place) == NEAR_REFERENCE and ref not in form_map:
            return None
        target, radius = form_map.get(ref, 0), int(rec.get('PLDT.Radius', 0))
        if kind == FNV_TRAVEL and int(place) == NEAR_REFERENCE and ref in self.furniture:
            return 'Sit', struct.pack('<iI', TARGET_REFERENCE, target)
        template = {FNV_TRAVEL: 'Travel', FNV_SANDBOX: 'Sandbox', FNV_DIALOGUE: 'ForceGreet'}[kind]
        return template, struct.pack('<iIi', int(place), target, radius)


def _greets_player(rec: dict) -> bool:
    """True when Dialogue package `rec` opens the GREETING (no topic) with the player."""
    return rec.get('PTDT.Target') == PLAYER_TARGET and not int(rec.get('PKDD.Topic', '0'), 16)


def pack_package(fid: int, edid: str, vanilla: bytes, first_input: bytes, conditions: bytes, flags: int) -> bytes:
    """A copy of vanilla instance `vanilla`: our EditorID, conditions after PSDT, its first PLDT/PTDA from `first_input`.

    The input keeps the vanilla payload's bytes past `first_input`. PKDT's
    general flags become FNV's `flags` the two games share (SHARED_FLAGS).
    """
    out, replaced = b'', False
    for tag, data in subrecords(vanilla):
        if tag == b'EDID':
            data = edid.encode() + b'\0'
        elif tag == b'PKDT':
            data = struct.pack('<I', flags & SHARED_FLAGS) + data[4:]
        elif tag in (b'PLDT', b'PTDA') and not replaced:
            data, replaced = first_input + data[len(first_input):], True
        out += pack_subrecord(tag.decode(), data) + (conditions if tag == b'PSDT' else b'')
    return pack_fo4_record('PACK', fid, 0, out)
