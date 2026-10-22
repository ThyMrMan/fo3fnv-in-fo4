"""FNV's teammate perks as FO4 companion perks, for the cell spike.

FNV's `AddPerk <perk> 1` (the teammates flag) applies the perk's entry points
to each active companion, its owner tab naming the companion (GetIsID). FO4
applies a perk to its holder only, so this does as vanilla's
CompanionInspirational: the player holds the FNV perk with no effects, and
each companion it names holds (NPC PRKR) a perk of its entry points, on while
that companion is a teammate and the player holds the FNV perk.

See: docs/fork/fo4_perks.md#teammate-perks
"""

import re
import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.swaps import SCRIPT_SOURCES

#: `[<ref>.]AddPerk|RemovePerk <perk> <n>`, n nonzero (FNV's teammates flag), on a line before any comment.
TEAMMATE_CALL = re.compile(r'(?im)^[^;\r\n]*\b(?:add|remove)perk[ \t]+(\w+)[ \t,]+0*[1-9]')
#: FNV CTDA head: type (comparison in the top 3 bits), value, function, first parameter (xEdit).
FNV_CTDA, COMPARISON = '<B3xfH2xI', 0xE0
#: FNV GetIsID; FO4's player reference (PlayerRef).
GET_IS_ID, PLAYER_REF = 72, 0x14
#: derive_formid key of a teammate perk's companion perk (key: the FNV perk's FormID).
COMPANION_KEY = 'PERK {} teammates'


def teammate_edids(export_dir: Path) -> frozenset:
    """Lowercased EditorIDs of perks scripts add or remove with the teammates flag."""
    texts = (text for sig, fields in SCRIPT_SOURCES.items() for rec in export_records(export_dir, sig)
             for key, text in rec.items() if key.endswith(fields))
    return frozenset(edid.lower() for text in texts for edid in TEAMMATE_CALL.findall(text))


def named_companions(rec: dict) -> list:
    """FNV NPCs (FormIDs, sorted) that perk `rec`'s entry points name on their owner tab (GetIsID == 1)."""
    out = set()
    for i in range(int(rec.get('EffectCount', 0) or 0)):
        k = 0
        while f'Effect[{i}].Tab[{k}].RunOn' in rec:
            if rec[f'Effect[{i}].Tab[{k}].RunOn'] == '0':
                out.update(_is_id(rec, f'Effect[{i}].Tab[{k}]'))
            k += 1
    return sorted(out)


def _is_id(rec: dict, tab: str) -> list:
    """The forms tab `tab`'s `GetIsID <form> == 1` conditions name."""
    out, j = [], 0
    while f'{tab}.Condition[{j}].Raw' in rec:
        kind, value, func, form = struct.unpack_from(FNV_CTDA, bytes.fromhex(rec[f'{tab}.Condition[{j}].Raw']))
        if func == GET_IS_ID and value == 1.0 and not kind & COMPARISON:
            out.append(form)
        j += 1
    return out


def companion_gate(player_perk: int) -> bytes:
    """A companion perk's gate: holder is a teammate, the player has `player_perk`."""
    return (R.pack_ctda(0, 1.0, C.FO4.index('GetPlayerTeammate'))
            + R.pack_ctda(0, 1.0, C.FO4.index('HasPerk'), player_perk, run_on=R.RUN_REFERENCE, ref=PLAYER_REF))


class Teammates:
    """FNV's teammate perks: {FNV perk: (its FO4 companion perk, the FNV NPCs holding it)}, and an NPC's ones."""

    def __init__(self, builder, export_dir: Path, records: list):
        """The teammate perks of FNV PERK `records`, each with its companion perk."""
        flagged = teammate_edids(export_dir)
        self.perks = {int(r['FormID'], 16): (builder.new_id(COMPANION_KEY.format(r['FormID'])), named_companions(r))
                      for r in records if r.get('EditorID', '').lower() in flagged}

    def held_by(self, npc: int) -> list:
        """The FO4 companion perks FNV NPC `npc` holds."""
        return sorted(fid for fid, npcs in self.perks.values() if npc in npcs)
