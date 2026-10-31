"""The export, each type file parsed once a run and shared by every reader.

An export whose plugin has masters (an FNV DLC on FalloutNV.esm; `_HEADER.txt` lists them as `Master[i]`) is
read with theirs, the exports of the same names beside it: a type's records are the plugin's own, then each
master's it does not override (by FormID), so every reference into a master resolves.

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_plugin_layout.md#dlc
"""

import functools
import re
from pathlib import Path

from tes5_import.base.text_reader import parse_export_file

#: A `_HEADER.txt` master line.
MASTER_LINE = re.compile(r'^Master\[\d+\]=(.+)$')


@functools.cache
def _parsed(path: str) -> tuple:
    """Every record in the export file at `path` (() for none), parsed once."""
    return tuple(parse_export_file(path))


@functools.cache
def export_masters(export_dir: str) -> tuple:
    """The export folders of `export_dir`'s plugin's masters, in its order; raise for one not exported."""
    header = Path(export_dir) / '_HEADER.txt'
    lines = header.read_text(encoding='utf-8').splitlines() if header.is_file() else []
    names = [m.group(1).strip() for m in map(MASTER_LINE.match, lines) if m]
    folders = tuple(str(Path(export_dir).parent / name) for name in names)
    missing = [f for f in folders if not Path(f).is_dir()]
    if missing:
        raise SystemExit(f'{Path(export_dir).name}: export its masters first: {missing}')
    return folders


@functools.cache
def _layered(export_dir: str, sig: str) -> tuple:
    """Type `sig`'s records of `export_dir` and then of its masters, each FormID once (the newest)."""
    out, seen = [], set()
    own = _parsed(str(Path(export_dir) / f'{sig}.txt'))
    for records in (own, *(export_records(folder, sig) for folder in export_masters(export_dir))):
        for rec in records:
            if rec['FormID'] not in seen:
                seen.add(rec['FormID'])
                out.append(rec)
    return tuple(out)


def export_records(export_dir, sig: str) -> tuple:
    """Type `sig`'s records in `export_dir`, its masters' behind them; shared, so callers never change them."""
    folder = str(export_dir)
    if export_masters(folder):
        return _layered(folder, sig)
    return _parsed(str(Path(folder) / f'{sig}.txt'))


def export_chain(export_dir) -> tuple:
    """`export_dir`, then its masters' exports: the order a lookup layers them."""
    if not (Path(export_dir) / '_HEADER.txt').is_file():
        return (Path(export_dir),)
    return (Path(export_dir), *(f for m in export_masters(str(export_dir)) for f in export_chain(m)))


def export_file(export_dir, *parts) -> Path:
    """`parts` in the first export of export_chain() holding it (Layered.path).
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    return Layered(export_chain(export_dir), *parts).path()


class Layered:
    """A path under folders searched in order (a DLC's, then its masters'): joining it with / stays layered, file
    by file; using it (str, open, is_file, read_bytes...) uses the first folder's path that exists, else the
    first folder's."""

    def __init__(self, folders: tuple, *parts):
        """`parts` (a folder, then names) under each of `folders`."""
        self.folders, self.parts = tuple(folders), parts

    def __truediv__(self, rel) -> 'Layered':
        """`rel` under this path, still layered."""
        return Layered(self.folders, *self.parts, rel)

    def path(self) -> Path:
        """The first folder's path that exists, else the first folder's."""
        paths = [Path(f).joinpath(*self.parts) for f in self.folders]
        return next((p for p in paths if p.exists()), paths[0])

    def __fspath__(self) -> str:
        """The resolved path."""
        return str(self.path())

    __str__ = __fspath__

    def __getattr__(self, name: str):
        """The resolved path's attribute (is_file, read_bytes, iterdir...)."""
        return getattr(self.path(), name)


def asset_root(export_dir, *parts) -> Layered:
    """`parts` under `export_dir`, layered over its masters' exports."""
    return Layered(export_chain(export_dir), *parts)


def own_records(export_dir, sig: str) -> tuple:
    """Type `sig`'s records the plugin holds: its own and its overrides."""
    return _parsed(str(Path(export_dir) / f'{sig}.txt'))


def held_types(export_dir) -> list:
    """The record types the plugin of `export_dir` holds, by its export files."""
    return sorted(p.stem for p in Path(export_dir).glob('*.txt') if not p.stem.startswith('_'))


def root_export(export_dir) -> Path:
    """The masterless export under `export_dir`'s master chain: its game."""
    masters = export_masters(str(export_dir))
    return root_export(masters[0]) if masters else Path(export_dir)
