"""A plugin renamed between builds (FalloutNV.esp to FalloutNV.esm): its old files moved to the new name once.

Fallout 4 files a plugin's voices and FaceGen under folders named for the plugin's file name, extension included
(`Sound/Voice/FalloutNV.esp/...`). A build under a new extension would find none and convert every voice again;
so before it runs, each such folder named for a plugin of the same stem moves to the new name (when the new one
is not there yet), and the old plugin file goes, as a user's older build may still hold both.

See: docs/fork/fo4_plugin_layout.md#saves
"""

import re
import shutil
from pathlib import Path

from fo4_import.base.build_files import BOOKS

#: Plugin extensions a renamed plugin may have had.
EXTENSIONS = ('.esp', '.esm', '.esl')


def is_master(plugin: str) -> bool:
    """Whether plugin file name `plugin` is a master (.esm)."""
    return Path(plugin).suffix.lower() == '.esm'


def old_names(plugin: str) -> list:
    """The file names `plugin` had under another extension."""
    stem, suffix = Path(plugin).stem, Path(plugin).suffix.lower()
    return [stem + ext for ext in EXTENSIONS if ext != suffix]


def move_renamed(plugin: str, parents: list) -> int:
    """Move each `<parent>/<old name>` folder to `<parent>/<plugin>` where that is missing; how many moved."""
    moved = 0
    for parent in parents:
        new = Path(parent) / plugin
        for old in (Path(parent) / name for name in old_names(plugin)):
            if old.is_dir() and not new.exists():
                new.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), str(new))
                moved += 1
    return moved


def retarget_faces(folder: Path, plugin: str) -> int:
    """Point the FaceGen NIFs in `folder` at `plugin`'s face textures: the CK writes each texture path with the
    plugin's file name (`FaceCustomization\\FalloutNV.esp\\...`), so a renamed plugin's faces show purple. The
    names differ in the extension only, so the strings keep their length; how many NIFs changed."""
    old = [re.compile(re.escape(f'FaceCustomization\\{name}\\').encode(), re.IGNORECASE) for name in old_names(plugin)]
    new = f'FaceCustomization\\{plugin}\\'.encode()
    changed = 0
    for path in sorted(Path(folder).glob('*.[nN][iI][fF]')) if Path(folder).is_dir() else []:
        data = path.read_bytes()
        fixed = data
        for pattern in old:
            fixed = pattern.sub(lambda _: new, fixed)
        if fixed != data:
            path.write_bytes(fixed)
            changed += 1
    return changed


def drop_old_plugins(data_dir: Path, plugin: str) -> int:
    """Delete the plugin files `plugin` had under another extension in `data_dir`, with their sidecars
    (`<old name>.files.txt`...; the ledger, named by stem, stays); how many went."""
    gone = [path for name in old_names(plugin) for folder in (Path(data_dir), Path(data_dir) / BOOKS)
            for path in folder.glob(f'{name}*') if path.is_file()]
    for path in gone:
        path.unlink()
    return len(gone)
