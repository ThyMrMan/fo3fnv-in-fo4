"""Converter helper functions kept in the script that calls them: `with_helpers` appends each one a generated
script calls but does not define, so a record script and a fragment script (terminal, topic, package, quest) get
the same helper whichever path wrote the call.
See: docs/fork/nvse_script_language.md#script-helpers
"""

import re

from script_convert import anim_playing_falloutnv as anim_playing

#: The read GetPCMovedCell converts to.
PC_MOVED_CELL = 'TES4_PCMovedCell'
#: JIP LN GetPCMovedCell: 1 when the player's cell differs from the one this script saw at its last call.
PC_MOVED_CELL_DECLARE = ['Cell TES4_PCCell', '', f'Int Function {PC_MOVED_CELL}()',
                         '  {JIP GetPCMovedCell: 1 when the player changed cell since this script last asked.}',
                         '  Cell now = Game.GetPlayer().GetParentCell()',
                         '  If now == TES4_PCCell',
                         '    Return 0',
                         '  EndIf',
                         '  TES4_PCCell = now',
                         '  Return 1',
                         'EndFunction', '']
#: {helper function: the lines declaring it and its variables}.
HELPERS = {anim_playing.READ: anim_playing.DECLARE, PC_MOVED_CELL: PC_MOVED_CELL_DECLARE}


def with_helpers(text: str) -> str:
    """Script `text` with every helper it calls but does not define appended."""
    for name, lines in HELPERS.items():
        if re.search(rf'\b{name}\(', text) and not re.search(rf'(?im)^\s*\w+\s+Function\s+{name}\(', text):
            text = text.rstrip('\n') + '\n\n' + '\n'.join(lines) + '\n'
    return text
