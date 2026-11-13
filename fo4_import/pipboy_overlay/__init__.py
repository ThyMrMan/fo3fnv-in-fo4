"""Cleanroom UI's movie inside the Pip-Boy, Interface/CRUI_Pipboy.swf, installed with the masterless build.

CleanroomUI.dll loads it into the open Pip-Boy menu with a Loader (its
pipboy.cpp); it draws the CND line, the repair and ammo lists and other mods'
item-card lines from the DLL's data. Built by Cleanroom UI (fo4_import.cleanroom).

See: docs/fork/swf_framework.md#pipboy
"""

from pathlib import Path

from fo4_import import cleanroom

#: The movie in a data folder, as Cleanroom UI's build writes it.
FILES = ('Interface/CRUI_Pipboy.swf',)
#: DEPRECATED: our own movie before Cleanroom UI's, which F3NV.dll loaded; install deletes it.
OLD_MOVIE = 'Interface/F3NV_Pipboy.swf'


def install(data_dir: Path) -> int:
    """Copy the movie into `data_dir` and delete OLD_MOVIE; 1 if installed."""
    (Path(data_dir) / OLD_MOVIE).unlink(missing_ok=True)
    return len(cleanroom.install(data_dir, FILES))
