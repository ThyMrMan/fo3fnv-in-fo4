"""The app's work folder in use: this process and the stages it starts read the export, the build's caches, run
logs and replacement files from it (asset_convert.paths.DATA_ENV), never from the app folder, so a new release can
replace or sit beside the old one. What an older release kept in its own app folder moves there on first start.

See: docs/fork/fo4_gui.md#work-folder
"""

import os
from pathlib import Path

from asset_convert import paths as data_paths
from fo4_import.app import settings as S
from fo4_import.base import release

#: What a release up to f3nv-0.3 kept in its app folder and the work folder now holds.
MOVED = ('export', 'output', 'replacements')


def use(settings: dict) -> Path:
    """Point this process and its stages at `settings`' work folder; the folder."""
    folder = S.work_dir(settings)
    os.environ[data_paths.DATA_ENV] = str(folder)
    return folder


def tag(folder: Path) -> 'tuple | None':
    """The release key of the app folder `folder` (its VERSION file's tag); None when it has none."""
    try:
        return release.key((folder / 'VERSION').read_text(encoding='utf-8').strip())
    except OSError:
        return None


def old_folders(app_dir: Path) -> list:
    """`app_dir`, then the older releases' app folders beside it, newest first."""
    now = tag(app_dir)
    beside = [p for p in app_dir.parent.iterdir() if p.is_dir() and p != app_dir and (tag(p) or now) < now]
    return [app_dir, *sorted(beside, key=tag, reverse=True)]


def adopt(settings: dict, app_dir: Path = S.APP_DIR) -> list:
    """Move each MOVED folder that released app folder `app_dir`, else the newest older release beside it, holds
    into the work folder where that has none yet (links left alone); a line per folder moved or that could not
    be. Nothing for a checkout (no VERSION tag).
    See: docs/fork/fo4_gui.md#work-folder
    """
    if tag(app_dir) is None:
        return []
    work, lines, folders = S.work_dir(settings), [], old_folders(app_dir)
    for name in MOVED:
        new = work / name
        old = next((f / name for f in folders if (f / name).is_dir() and not (f / name).is_symlink()
                    and not (f / name).is_junction()), None)
        if old is None or new.exists():
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            lines.append(f'Moved {old} to {new}.')
        except OSError as error:
            lines.append(f'Could not move {old} to {work} ({error.strerror}): move it there yourself.')
    return lines
