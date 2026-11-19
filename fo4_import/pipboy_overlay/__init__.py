"""Cleanroom UI's movies for the Pip-Boy, installed with the masterless build: Interface/CRUI_Pipboy.swf and the
pad's action menu, Interface/CRUI_PipboyActions.swf.

CleanroomUI.dll loads CRUI_Pipboy.swf into the open Pip-Boy menu with a
Loader (its pipboy.cpp); it draws the CND line, the repair and ammo lists and
other mods' item-card lines from the DLL's data. View on a pad opens the
action menu (pad.cpp, CRUI_PipboyActions.psc). Built by Cleanroom UI
(fo4_import.cleanroom).

See: docs/fork/swf_framework.md#pipboy
"""

from pathlib import Path

from fo4_import import cleanroom

#: The movies in a data folder, as Cleanroom UI's build writes them.
FILES = ('Interface/CRUI_Pipboy.swf', 'Interface/CRUI_PipboyActions.swf')
#: DEPRECATED: our own movie before Cleanroom UI's, which F3NV.dll loaded; install deletes it.
OLD_MOVIE = 'Interface/F3NV_Pipboy.swf'


def install(data_dir: Path) -> int:
    """Copy the movies into `data_dir` and delete OLD_MOVIE; the count installed."""
    (Path(data_dir) / OLD_MOVIE).unlink(missing_ok=True)
    return len(cleanroom.install(data_dir, FILES))
