"""The built plugins of a Fallout 4 build's masters, as the build found them, read for the parts audits compare.

A DLC build reads its masters' built plugins from `--plugin-dirs` (its stamp's command names them); preflight's own
`--plugin-dirs` overrides that. A master no folder holds (Fallout4.esm) has no built plugin. A master whose own
masters do not lead the build's is left out, since its FormIDs would read differently.

See: docs/fork/fo4_preflight.md#targets
"""

import shlex
from pathlib import Path

from fo4_import.base.install import file_masters
from tools.validate.preflight.build_history import read_stamp

#: The pipeline option naming the folders that hold built masters.
PLUGIN_DIRS = '--plugin-dirs'


def stamp_dirs(plugin: Path) -> list:
    """The folders the build's `--plugin-dirs` named, from its stamp's command."""
    words = shlex.split(read_stamp(plugin).get('command', ''), posix=False)
    if PLUGIN_DIRS not in words:
        return []
    out = []
    for word in words[words.index(PLUGIN_DIRS) + 1:]:
        if word.startswith('--'):
            break
        out.append(Path(word.strip('"')))
    return out


def master_paths(plugin: Path, masters: tuple, dirs: list) -> list:
    """The built plugin files of `masters` (in load order) found in `dirs` (else the stamp's), whose FormIDs read
    as the build's."""
    out = []
    for name in masters:
        path = next((Path(d) / name for d in dirs or stamp_dirs(plugin) if (Path(d) / name).is_file()), None)
        theirs = file_masters(path) if path is not None else None
        if theirs is not None and list(masters[:len(theirs)]) == list(theirs):
            out.append(path)
    return out
