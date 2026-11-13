"""FNV classes a line tests (GetIsClass) as Fallout 4 classes, so the test converts as itself.

A converted human otherwise takes Fallout4.esm's Citizen (npcs.HUMAN_CLASS). Each FNV class some
line tests is written once as a copy of Citizen (its properties and data, not its localized name)
under the FNV EditorID, and NPCs of that FNV class take it.

See: docs/fork/fo4_dialogue_gaps.md#classes
"""

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.say_topics import parsed
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The FNV test of a class.
TEST = 'GetIsClass'
#: Citizen's subrecords a copy keeps.
KEPT = (b'PRPS', b'DATA')


class Classes:
    """The FO4 classes made for the FNV classes `lines` test, each written once through `builder`."""

    def __init__(self, builder, lines, names: dict, citizen: int):
        """The `names` classes `lines` test; any other maps to `citizen`."""
        self.builder, self.citizen, self.names, self.made = builder, citizen, names, {}
        self.tested = {c['p1'] for line in lines for c in parsed(line) if c['func'] == TEST} & names.keys()

    def of(self, fnv: int) -> int:
        """The FO4 class of an NPC of FNV class `fnv`: its own copy when a line tests it, else Citizen."""
        if fnv not in self.tested:
            return self.citizen
        if fnv not in self.made:
            self.made[fnv] = self._write(fnv)
        return self.made[fnv]

    def form_map(self) -> dict:
        """{FNV class: FO4 class} of every tested class."""
        return {fnv: self.of(fnv) for fnv in sorted(self.tested)}

    def _write(self, fnv: int) -> int:
        """Write the copy of Citizen for FNV class `fnv`; its FormID."""
        body = next(r.body for r, _ in walk(self.builder.fo4, b'CLAS') if r.form_id == self.citizen)
        kept = b''.join(pack_subrecord(tag.decode(), data) for tag, data in subrecords(body) if tag in KEPT)
        fid = self.builder.fnv_id(fnv)
        edid = pack_subrecord('EDID', f'FNV_{self.names[fnv]}'.encode('cp1252') + b'\0')
        self.builder.writer.add_record('CLAS', pack_fo4_record('CLAS', fid, 0, edid + kept))
        self.builder.counts['CLAS (tested by a line)'] += 1
        return fid

