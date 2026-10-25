"""Game files by their path inside Data (`meshes\\x.nif`), over Data-like folders, ignoring case as the game does.

Loose files win over archives, as in the game. Folders are given winning first (core.mod_sources.data_dirs);
the first folder holding a loose file wins. Archives (`*.ba2`) are each folder's, the winning folder's first and,
within one folder, a later name before an earlier one (fo4_import.base.ba2.Archives' order). Both indexes are
built on first use.

See: docs/fork/fo4_gui.md#preview
"""

import os
from pathlib import Path

from fo4_import.base.ba2 import Archive

ARCHIVE_SUFFIX = '.ba2'


def key(path: str) -> str:
    """A Data path as the indexes hold it: lowercase, backslashes, no leading slash."""
    return path.replace('/', '\\').lower().lstrip('\\')


def mesh_path(model: str) -> str:
    """The Data path of a record's model (MODL/MOD2 are relative to `meshes`)."""
    path = key(model)
    return path if path.startswith('meshes\\') else f'meshes\\{path}'


class Files:
    """Loose files and archived files under `dirs` (Data-like folders, winning first)."""

    def __init__(self, dirs: list):
        """Look up files in `dirs`, the winning folder first."""
        self.dirs = [Path(d) for d in dirs]
        self._loose, self._archived = None, None

    def loose(self) -> dict:
        """{Data path: file} of every loose file, the winning folder's kept."""
        if self._loose is None:
            self._loose = {}
            for folder in self.dirs:
                for root, _, names in os.walk(folder):
                    rel = Path(root).relative_to(folder)
                    for name in names:
                        self._loose.setdefault(key(str(rel / name)), Path(root) / name)
        return self._loose

    def archived(self) -> dict:
        """{Data path: Archive} of every archived file, the winning archive's kept."""
        if self._archived is None:
            self._archived = {}
            for archive in self.archives():
                for name in archive.entries:
                    self._archived.setdefault(name, archive)
        return self._archived

    def archives(self) -> list:
        """Every folder's BA2s, winning first."""
        found = []
        for folder in self.dirs:
            if folder.is_dir():
                found += sorted((p for p in folder.iterdir() if p.suffix.lower() == ARCHIVE_SUFFIX and p.is_file()),
                                key=lambda p: p.name.lower(), reverse=True)
        return [Archive(p) for p in found]

    def where(self, path: str) -> 'Path | Archive | None':
        """The loose file or the archive `path` comes from, or None."""
        wanted = key(path)
        return self.loose().get(wanted) or self.archived().get(wanted)

    def read(self, path: str) -> 'bytes | None':
        """The bytes of `path` (a texture from an archive as a one-mip DDS), or None when no folder has it."""
        source = self.where(path)
        if source is None:
            return None
        return source.read_bytes() if isinstance(source, Path) else source.read(key(path))
