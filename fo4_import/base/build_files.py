"""Where a build keeps its own records of a plugin (the build stamp, file list, FormID ledger, inputs record,
archive records, finished-mesh and animation-data lists): the BOOKS folder beside the plugin. MO2 and its
virtual file system skip a `.mohidden` path, so the game's Data lists none of them, and the records still
travel with the plugin's folder. A record an older build left beside the plugin moves in on first use.

See: docs/fork/fo4_pipeline.md#build-files
"""

import shutil
from pathlib import Path

#: The folder, beside a plugin, holding the build's records of it.
BOOKS = 'F3NV_Build.mohidden'


def moved_in(old: Path) -> Path:
    """Where the record an older build kept at `old` (beside the plugin) lives now, in BOOKS beside it; an old
    one moves there first, replacing an older new one, or goes when the new one is newer."""
    old = Path(old)
    new = old.parent / BOOKS / old.name
    if not old.exists():
        return new
    if new.exists() and new.stat().st_mtime < old.stat().st_mtime:
        _remove(new)
    if new.exists():
        _remove(old)
    else:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    return new


def _remove(path: Path) -> None:
    """Delete file or folder `path`."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def all_moved_in(folder: Path, pattern: str) -> list:
    """`folder`'s records matching glob `pattern`, sorted, old ones moved in first."""
    for old in sorted(Path(folder).glob(pattern)):
        moved_in(old)
    return sorted((Path(folder) / BOOKS).glob(pattern))
