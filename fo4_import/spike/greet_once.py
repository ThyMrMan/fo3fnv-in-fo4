"""FNV Dialogue packages aimed at the player, talking once per run on Fallout 4.

FNV leaves a Dialogue package that has talked as the actor's current package,
parked on its done step, until another package takes over; picking the same
package again does nothing. FO4's ForceGreet, which stands in for it, is picked
again as soon as its talk ends, so the actor grabs the player again. Each
ForceGreet copy gets a number: the talk opening (F3NV_Greeting) sets the
speaker's helper actor value DialogueDone to its package's number, the copy
needs that value not to be its number, and a parked copy right after it in the
actor's list (HoldPosition near the actor, the same conditions) needs it to be.
The parked copy's change fragment (F3NV_DialogueDone) clears the value when
another package takes over: FNV's restart.

See: docs/fork/fo4_pipeline.md#greet-once
"""

import struct

from fo4_import.base.vmad import package_fragments
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike.factions import hidden_faction
from fo4_import.spike import records as R
from fo4_import.spike.records import pack_flst
from tes5_import.base.writer import pack_subrecord

#: The helper actor value holding the number of the Dialogue package its actor last talked in.
DONE_AV = 'DialogueDone'
#: The parked copy's script and its fragment flag: OnChange (FO4 PACK fragments: begin 1, end 2, change 4).
DONE_SCRIPT, CHANGE_FRAGMENT = 'F3NV_DialogueDone', 0x04
#: derive_formid sites: a package's parked copy (key: FNV package), the list of numbered ForceGreets.
SITE, LIST_SITE = 'FNV PACK dialogue done', 'FNV dialogue greets'
#: derive_formid site of a day_marked package's faction (key: FNV package).
DAY_SITE = 'FNV PACK done today'
#: CTDA compare operators == and !=; FO4's GetValue and GetInFaction.
EQUAL, NOT_EQUAL, GET_VALUE, GET_IN_FACTION = 0x00, 0x20, C.FO4.index('GetValue'), C.FO4.index('GetInFaction')
#: FO4 PLDT location type Near Self (xEdit), where the parked copy holds.
NEAR_SELF = 12


class GreetOnce:
    """The numbered ForceGreets of a build and their parked copies."""

    def __init__(self, builder, helper_index: int):
        """For `builder`, reading the helper plugin (master `helper_index`)'s DialogueDone."""
        self.builder, self.av, self.greets, self.parked = builder, actor_value_form(DONE_AV, helper_index), [], {}
        self.walks, self.days = 0, {}

    def number(self, fid: int) -> int:
        """ForceGreet `fid`'s number (its place in the list, from 1), noting it."""
        self.greets.append(fid)
        return len(self.greets)

    def walk_number(self) -> int:
        """A SayTo walk-up's number: -1, -2, ..., apart from ForceGreets'."""
        self.walks += 1
        return -self.walks

    def unspoken(self, number: int) -> bytes:
        """The condition a numbered ForceGreet adds: its actor has not talked in it."""
        return R.pack_ctda(NOT_EQUAL, float(number), GET_VALUE, self.av)

    def day_faction(self, rec: dict) -> int:
        """The hidden FACT a day_marked FNV package `rec` puts its actor in as it ends; written once."""
        if rec['FormID'] not in self.days:
            self.days[rec['FormID']] = fid = self.builder.writer.derive_formid(DAY_SITE, int(rec['FormID'], 16))
            self.builder.writer.add_record('FACT', hidden_faction(fid, f'FNV_{rec["EditorID"]}Done'))
            self.builder.counts['FACT (package done today)'] += 1
        return self.days[rec['FormID']]

    def undone(self, rec: dict) -> bytes:
        """A day_marked `rec`'s condition: its actor is not in its day_faction."""
        return R.pack_ctda(EQUAL, 0.0, GET_IN_FACTION, self.day_faction(rec))

    def park(self, fnv: str, number: int, copy, walk_up: bool = False) -> int:
        """Write FNV package `fnv`'s parked copy with `copy(fid, EditorID suffix, template, first input, extra
        conditions, VMAD)`, after its ForceGreet (or `walk_up` SayTo) numbered `number`; its FormID."""
        fid = self.builder.writer.derive_formid(SITE, int(fnv, 16))
        values = {'Done': ('int', number), **({'WalkUp': ('bool', True)} if walk_up else {})}
        vmad = pack_subrecord('VMAD', package_fragments(DONE_SCRIPT, CHANGE_FRAGMENT, None, values))
        copy(fid, 'Done', 'HoldPosition', struct.pack('<iIi', NEAR_SELF, 0, 0),
             R.pack_ctda(EQUAL, float(number), GET_VALUE, self.av), vmad)
        self.builder.scripts.used.append(DONE_SCRIPT)
        self.builder.counts['PACK HoldPosition (dialogue done)'] += 1
        self.parked[fnv] = fid
        return fid

    def write_list(self) -> int:
        """The FLST of the numbered ForceGreets, in number order (F3NV_Greeting's Greets); 0 without any."""
        if not self.greets:
            return 0
        fid = self.builder.writer.derive_formid(LIST_SITE, 'list')
        self.builder.writer.add_record('FLST', pack_flst(fid, 'FNV_DialogueGreets', self.greets))
        return fid
