"""FNV control tokens in message text as Fallout 4's.

FNV writes a control as `&sUActn<action>;`, shown as its verb and key
("press Space"), or `&-sUActn<action>;`, the key alone. FO4 writes
`[<event>]`, its control map's event shown as the key ("Press [Jump] to
jump", as vanilla's tutorials). Grab, FNV's own key, is FO4's held
Activate. Other tokens (fixed keys, pad buttons, the player's name) stay.

See: docs/fork/fo4_pipeline.md#npcs
"""

import re

#: FNV action (lower case) -> (FO4 control event, verb). FNV's Use attacks; Activate activates.
CONTROLS = {'forward': ('Forward', 'press'), 'back': ('Back', 'press'), 'sldleft': ('StrafeLeft', 'press'),
            'sldright': ('StrafeRight', 'press'), 'use': ('PrimaryAttack', 'press'),
            'block': ('SecondaryAttack', 'hold'), 'activate': ('Activate', 'press'),
            'rdyitem': ('ReadyWeapon', 'press'), 'crouch': ('Sneak', 'press'), 'vats': ('VATS', 'press'),
            'menumode': ('Pipboy', 'press'), 'jump': ('Jump', 'press'), 'run': ('Sprint', 'hold'),
            'grab': ('Activate', 'hold')}
TOKEN = re.compile(r'&(-?)sUActn(\w+);', re.IGNORECASE)


def fo4_controls(text: str) -> str:
    """`text` with FNV's action tokens (CONTROLS) as FO4's; other tokens unchanged."""
    def token(match) -> str:
        """One token as FO4's, with its verb unless FNV's names the key alone."""
        found = CONTROLS.get(match.group(2).lower())
        if found is None:
            return match.group(0)
        return f'[{found[0]}]' if match.group(1) else f'{found[1]} [{found[0]}]'
    return TOKEN.sub(token, text)
