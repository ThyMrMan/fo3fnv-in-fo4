"""FNV AI packages as FO4 package instances, for the cell spike.

FO4 packages, like Skyrim's, are instances of template packages filled with
data inputs. Each FNV package becomes a copy of a vanilla FO4 instance of the
matching template with its destination, conditions and EditorID replaced:
Travel to a reference (a Sit when the reference is furniture: FNV seats an
actor who travels to a chair) and Sandbox. The copied instances have no
conditions, scripts or owner quest and a direct reference as first input.
Other package types, and packages naming forms or conditions that do not
convert, are left out and counted.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.say_topics import conditions_of
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.text_reader import parse_export_file
from tes5_import.base.writer import pack_subrecord

#: Vanilla instances copied per template (Parsons' travel, a Children of Atom sit, a Minutemen sandbox).
INSTANCES = {'Travel': 0x248982, 'Sit': 0x2471DB, 'Sandbox': 0x24674E}
#: FNV PKDT types converted.
FNV_TRAVEL, FNV_SANDBOX = '6', '12'
#: FNV PLDT location types FO4 shares: near reference, in cell, near current (package start) location, editor location.
SHARED_LOCATIONS = ('0', '1', '2', '3')
NEAR_REFERENCE = 0
#: PTDA target type: a specific reference.
TARGET_REFERENCE = 0


class Packages:
    """FO4 copies of FNV packages; `package` writes one through the builder."""

    def __init__(self, builder, export_dir, furniture: set):
        """Index FNV packages and read the vanilla instances; `furniture` holds the FNV references that are seats."""
        self.builder, self.furniture, self.made = builder, furniture, {}
        self.packs = {r['FormID']: r for r in parse_export_file(str(export_dir / 'PACK.txt'))}
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
                self.made[fnv] = fid = self.builder.new_id()
                self.builder.writer.add_record('PACK', pack_package(fid, f'FNV_{rec["EditorID"]}',
                                                                   self.vanilla[plan[0]], plan[1], conditions))
                self.builder.counts['PACK'] += 1
        return self.made[fnv]

    def _plan(self, rec: dict, form_map: dict) -> 'tuple | None':
        """(template, first input payload) for FNV package `rec`; None when it does not convert."""
        kind, place = rec.get('PKDT.Type'), rec.get('PLDT.Type')
        if kind not in (FNV_TRAVEL, FNV_SANDBOX) or place not in SHARED_LOCATIONS:
            return None
        ref = int(rec.get('PLDT.Location', '0'), 16)
        if int(place) == NEAR_REFERENCE and ref not in form_map:
            return None
        target, radius = form_map.get(ref, 0), int(rec.get('PLDT.Radius', 0))
        if kind == FNV_TRAVEL and int(place) == NEAR_REFERENCE and ref in self.furniture:
            return 'Sit', struct.pack('<iI', TARGET_REFERENCE, target)
        return ('Travel' if kind == FNV_TRAVEL else 'Sandbox'), struct.pack('<iIi', int(place), target, radius)


def pack_package(fid: int, edid: str, vanilla: bytes, first_input: bytes, conditions: bytes) -> bytes:
    """A copy of vanilla instance `vanilla`: our EditorID, conditions after PSDT, its first PLDT/PTDA from `first_input`.

    The input keeps the vanilla payload's bytes past `first_input`.
    """
    out, replaced = b'', False
    for tag, data in subrecords(vanilla):
        if tag == b'EDID':
            data = edid.encode() + b'\0'
        elif tag in (b'PLDT', b'PTDA') and not replaced:
            data, replaced = first_input + data[len(first_input):], True
        out += pack_subrecord(tag.decode(), data) + (conditions if tag == b'PSDT' else b'')
    return pack_fo4_record('PACK', fid, 0, out)
