"""Cleanroom UI's level-up menu, installed with the masterless build: its movie, Interface/CRUI_LevelUp.swf, and the
words of every CleanroomUI movie, CleanroomUI_<language>.txt (fo4_import.cleanroom).

CRUI_LevelUp.psc registers the movie with F4SE and opens it in place of
LevelUpMenu (F3NV_CharacterRules); the data it shows comes from the build's
tables on that script (fo4_import/spike/level_up.py). The MCM page for its
options is ours (mcm/, options.py).

See: docs/fork/fo4_level_up_plan.md#menu
"""

from pathlib import Path

from fo4_import import cleanroom

#: DEPRECATED: the movie's path before CRUI_LevelUp, which install deletes.
OLD_MOVIE = 'Interface/F3NV_LevelUp.swf'


def install(data_dir: Path) -> int:
    """Copy the movie and words into `data_dir`, deleting an older build's OLD_MOVIE; how many files were copied."""
    (Path(data_dir) / OLD_MOVIE).unlink(missing_ok=True)
    return len(cleanroom.install(data_dir, cleanroom.LEVEL_UP_FILES))
