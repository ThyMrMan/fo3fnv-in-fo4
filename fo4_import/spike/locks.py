"""The FNV locks FO4's lock tiers cannot hold, for the cell spike.

FO4 gates its Advanced, Expert and Master tiers (lock levels 50, 75, 100)
on perk entry points, which the hidden FNV_SkillGates perk (spike.perks)
sets from FNV's Lockpick and Science, so FNV's levels 50, 75 and 100 need
nothing more. FO4's Novice tier holds both FNV's 0 and 25 and opens at any
skill, and an FNV terminal's password note is no FO4 key (a KEYM). A placed
lock of level 25, or a terminal with a password note, runs LOCK_SCRIPT,
which holds its activation to FNV's rule.

See: docs/fork/fo4_pipeline.md#lock-script
"""

from fo4_import.base.vmad import object_scripts
from fo4_import.helpers_plugin import actor_value_form

#: The script holding a lock to FNV's rule, and the one FNV level FO4's tiers leave ungated (Novice holds 0 and 25).
LOCK_SCRIPT, EASY = 'F3NV_FalloutLock', 25


def lock_vmad(builder, ref: dict) -> bytes:
    """The VMAD data of LOCK_SCRIPT on placed FNV reference `ref` when FO4's tiers cannot hold its lock (Easy, or a
    password note); b'' otherwise."""
    level, note, terminal = lock_of(builder, ref)
    password = (builder.items.item(note) or 0) if note else 0
    if level != EASY and not password:
        return b''
    builder.counts['locks held by script: Easy'] += level == EASY
    builder.counts['locks held by script: password note'] += bool(password)
    skill = actor_value_form('Science' if terminal else 'Lockpick', builder.scripts.helper_index)
    objects = {'Skill': skill, **({'Password': password} if password else {})}
    return object_scripts([(LOCK_SCRIPT, objects, {'IsTerminal': ('bool', terminal)})])


def lock_of(builder, ref: dict) -> tuple:
    """(level, password note's FNV FormID or 0, is a terminal) of `ref`'s lock: its own XLOC, else its terminal
    base's (Terminals.lock_of); level None when it has neither."""
    if 'XLOC.Level' in ref:
        return int(ref['XLOC.Level']), 0, False
    readables = getattr(builder, 'readables', None)
    lock = readables.terminals.lock_of(ref) if readables else None
    return (lock[0], lock[2], True) if lock else (None, 0, False)
