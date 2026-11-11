"""FNV's `[Speech 50]` tag on a dialogue option whose lines check one of the player's skills or SPECIAL.

FalloutNV.exe writes the tag from the line's condition, not the text (its dialogue menu's `[%s` / `%s %d/%d`
strings, 0xC71200); the authored prompt has none. A check is two lines with one prompt, one gated at or above
the number and one below, so the build's one option for them takes the tag of the first such test it finds: a
GetActorValue on the player (run on the Target, or on the player's reference) of a skill or SPECIAL, compared
with a number. FNV's failed `[Speech 30/50]` shows here as `[Speech 50]`: the text cannot hold the player's value.

See: docs/fork/fo4_build_next.md#speech-tag
"""

from fo4_import.spike import conditions as C
from fo4_import.spike.say_topics import raws

#: FNV actor value indices of SPECIAL (Strength to Luck) and the skills (Barter to Unarmed).
SPECIAL, SKILLS = range(5, 12), range(32, 46)
#: FNV condition run-on Target and Reference; the player's reference.
TARGET, REFERENCE, PLAYER = 1, 2, 0x14
#: CTDA operators (high three bits) -> the number the check needs, from its value.
NEEDED = {0x40: 1, 0x60: 0, 0x80: 0, 0xA0: 1}
#: Condition flag: compare with a global, not a number.
USE_GLOBAL = 0x04


def skill_check(raw: str) -> 'tuple | None':
    """(FNV actor value index, number needed) of FNV condition `raw` when it checks the player's skill or SPECIAL."""
    cond = C.parse(raw)
    on_player = cond['run_on'] == TARGET or (cond['run_on'] == REFERENCE and cond['ref'] == PLAYER)
    op = cond['op_flags'] & 0xE0
    if cond['func'] != 'GetActorValue' or not on_player or op not in NEEDED or cond['op_flags'] & USE_GLOBAL:
        return None
    if cond['p1'] not in SPECIAL and cond['p1'] not in SKILLS:
        return None
    return cond['p1'], int(round(cond['value'])) + NEEDED[op]


def tag_check(text: str, members: list) -> 'tuple | None':
    """The check tagged() writes on `text`: (actor value index, number needed)."""
    if text.lstrip().startswith('['):
        return None
    return next((check for rec in members for check in map(skill_check, raws(rec)) if check), None)


def tagged(text: str, members: list) -> str:
    """Prompt `text` led by FNV's tag of tag_check(), if any."""
    found = tag_check(text, members)
    return f'[{C.FNV_AV_NAMES[found[0]]} {found[1]}] {text}' if found else text
