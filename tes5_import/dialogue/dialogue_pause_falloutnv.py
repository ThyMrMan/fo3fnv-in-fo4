"""FO3/FNV dialogue pauses the world: a quest whose PlayerRef alias runs TES4_DialoguePause, and its switch.

Written last in the import, after every other generated record, so the two
new FormIDs never displace another generated record's. The same script puts
each actor the player has talked with in TES4TalkedToPC, which converted
GetTalkedToPC conditions read; that faction takes a fixed id, since the
conditions are converted first.

See: docs/commentary/tes5_import_dialogue.md#fallout-dialogue-pause
See: docs/commentary/tes5_import_dialogue.md#talked-to-pc
"""

import struct

from ..base.conditions_falloutnv import TALKED_FACTION
from ..base.owned_records import emit_global
from ..base.writer import pack_record, pack_string_subrecord, pack_subrecord
from ..record_types.world_falloutnv import is_fallout_source
from .player_alias_quest import player_alias_quest

#: The static script that freezes the other actors while the player talks.
PAUSE_SCRIPT = 'TES4_DialoguePause'

#: The per-game switch, 1 (on) as built; 0 lets the world run on in dialogue.
PAUSE_GLOBAL = 'TES4DialoguePause'

#: The quest hosting the script on its PlayerRef alias.
PAUSE_QUEST = 'TES4DialoguePauseQuest'

#: The faction an actor joins once a dialogue menu with it closes.
TALKED_FACTION_EDID = 'TES4TalkedToPC'

#: Its slot in the conversion-owned fixed-id window (0x42-0x44: the ForceCombat pair, TES4DestroyedRefs).
_TALKED_SLOT = 0x45

#: FACT DATA Hidden From NPC.
_HIDDEN = 0x1


def create_talked_faction(writer) -> dict:
    """Write TES4TalkedToPC for a FO3/FNV plugin and point converted GetTalkedToPC at it; {EditorID: FormID}, else {}."""
    TALKED_FACTION.clear()
    if not is_fallout_source():
        return {}
    fid = writer.chargen_fid_base + _TALKED_SLOT
    subs = pack_string_subrecord('EDID', TALKED_FACTION_EDID) + pack_subrecord('DATA', struct.pack('<I', _HIDDEN))
    writer.add_record('FACT', pack_record('FACT', fid, 0, subs))
    TALKED_FACTION.append(fid)
    return {TALKED_FACTION_EDID: fid}


def build_dialogue_pause(writer) -> int:
    """Write the switch and the quest for a FO3/FNV plugin; the quest's FormID, else 0."""
    if not is_fallout_source():
        return 0
    switch = emit_global(writer, PAUSE_GLOBAL, 's', 1.0)
    fid = writer.derive_formid('SYNTH_QUST', PAUSE_QUEST)
    props = {PAUSE_GLOBAL: switch, TALKED_FACTION_EDID: TALKED_FACTION[0]} if TALKED_FACTION else {PAUSE_GLOBAL: switch}
    player_alias_quest(writer, fid, PAUSE_QUEST, 'TES4 Dialogue Pause', [(PAUSE_SCRIPT, props)])
    return fid
