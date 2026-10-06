"""The reference a source script's call without a receiver acts on, where the base type alone does not say.

See: docs/fork/fo4_spikes.md#spike-3-vdoctors
"""


def stage_subject(xref, current_event: str, extends: str) -> str:
    """`Game.GetPlayer()` in an FO3/FNV quest stage fragment, which the engine runs on the player; else ''."""
    fallout = bool(xref and xref.is_fallout())
    return 'Game.GetPlayer()' if fallout and extends == 'Quest' and current_event == 'Fragment' else ''
