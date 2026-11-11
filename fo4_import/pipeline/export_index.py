"""The export, each type file parsed once a run and shared by every reader.

An export whose plugin has masters (an FNV DLC on FalloutNV.esm, a mod on it and the DLCs; `_HEADER.txt` lists
them all as `Master[i]`) is read with theirs: a type's records are the plugin's own, then each master's own it
does not override (by FormID), the last master first, each renumbered into the plugin's FormID numbering
(master_space), so every reference into a master resolves.

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_plugin_layout.md#dlc
"""

import functools
import os
import re
from pathlib import Path

from fo4_import.base.source import GAME_PLUGINS, asset_dirs, plugin_name, record_dir, source_plugin
from fo4_import.pipeline.master_space import byte_map, identity, renumber_record
from tes5_import.base.text_reader import parse_export_file

#: A `_HEADER.txt` master line.
MASTER_LINE = re.compile(r'^Master\[\d+\]=(.+)$')
#: Record flags: Deleted, and the Initially Disabled a deleted master reference is placed with instead.
DELETED, DISABLED = 0x20, 0x800
#: Placed types a plugin's deletion of its master's record undeletes and disables (dlc-deleted).
PLACED = frozenset({'REFR', 'ACHR', 'ACRE', 'PGRE', 'PMIS', 'PBEA', 'PFLA', 'PCBE'})
#: Environment variable naming asset overlay folders (os.pathsep-separated), searched before every export.
OVERLAY_ENV = 'F3NV_OVERLAYS'


@functools.cache
def _parsed(path: str) -> tuple:
    """Every record in the export file at `path` (() for none), parsed once."""
    return tuple(parse_export_file(path))


@functools.cache
def master_names(export_dir: str) -> tuple:
    """The master file names `export_dir`'s _HEADER.txt lists, in order."""
    header = Path(export_dir) / '_HEADER.txt'
    lines = header.read_text(encoding='utf-8').splitlines() if header.is_file() else []
    return tuple(m.group(1).strip() for m in map(MASTER_LINE.match, lines) if m)


@functools.cache
def export_masters(export_dir: str) -> tuple:
    """The export folders of `export_dir`'s plugin's masters, in its order; raise for one not exported."""
    folders = tuple(str(record_dir(export_dir, name)) for name in master_names(export_dir))
    missing = [f for f in folders if not Path(f).is_dir()]
    if missing:
        raise SystemExit(f'{Path(export_dir).name}: export its masters first: {missing}')
    return folders


@functools.cache
def _layered(export_dir: str, sig: str) -> tuple:
    """Type `sig`'s records of `export_dir` and then of its masters, each FormID once (the newest); one the plugin
    deletes is gone, but a master's placed reference stays, disabled (FO4 mishandles a deleted master reference).
    See: docs/fork/fo4_plugin_layout.md#dlc-deleted
    """
    layers = (own_records(export_dir, sig), *(master_records(export_dir, f, sig)
                                              for f in reversed(export_masters(export_dir))))
    out, seen, deleted = [], set(), set()
    for depth, rec in ((depth, rec) for depth, layer in enumerate(layers) for rec in layer):
        fid = rec['FormID']
        if fid in deleted and sig in PLACED:
            deleted.discard(fid)
            out.append({**rec, 'RecordFlags': str(int(rec.get('RecordFlags', '0')) | DISABLED)})
        elif fid not in seen and depth < len(layers) - 1 and int(rec.get('RecordFlags', '0')) & DELETED:
            deleted.add(fid)
        elif fid not in seen:
            out.append(rec)
        seen.add(fid)
    return tuple(out)


@functools.cache
def master_records(export_dir: str, folder: str, sig: str) -> tuple:
    """own_records() of master export `folder` in `export_dir`'s FormID numbering (master_space)."""
    mapping, recs = master_map(export_dir, folder), own_records(folder, sig)
    if identity(mapping):
        return recs
    return tuple(renumber_record(rec, mapping, source_game(export_dir)) for rec in recs)


@functools.cache
def master_map(export_dir: str, folder: str) -> tuple:
    """master_space.byte_map of master export `folder` into `export_dir`'s numbering."""
    return byte_map(master_names(export_dir), plugin_name(folder), master_names(folder))


def source_game(export_dir) -> str:
    """'fo3' for an export on Fallout3.esm, else 'fnv'."""
    return 'fo3' if root_export(export_dir).name.lower() == 'fallout3.esm' else 'fnv'


def plugin_sources(export_dir) -> tuple:
    """(plugin file, FormID map, game) of the plugin, then its masters newest first."""
    folder, game = str(export_dir), source_game(export_dir)
    masters = ((source_plugin(m), master_map(folder, m), game) for m in reversed(export_masters(folder)))
    return ((source_plugin(folder), (), game), *masters)


def export_records(export_dir, sig: str) -> tuple:
    """Type `sig`'s records in `export_dir`, its masters' behind them; shared, so callers never change them."""
    folder = str(export_dir)
    if export_masters(folder):
        return _layered(folder, sig)
    return _parsed(str(Path(folder) / f'{sig}.txt'))


def export_chain(export_dir) -> tuple:
    """asset_dirs(`export_dir`), then its masters' exports: a lookup's layer order."""
    if not (Path(export_dir) / '_HEADER.txt').is_file():
        return (Path(export_dir),)
    chain = (*asset_dirs(export_dir), *(f for m in export_masters(str(export_dir)) for f in export_chain(m)))
    return tuple(dict.fromkeys(chain))


@functools.cache
def _asset_chain(export_dir: str) -> tuple:
    """export_chain(), then, for a plugin with masters, the exports of its game's own plugins (GAME_PLUGINS) it
    leaves out: New Vegas finds a model in any archive it loads, not only its masters'.
    See: docs/fork/fo4_build_speed.md#faults
    """
    chain = export_chain(export_dir)
    if not export_masters(export_dir):
        return chain
    game = (record_dir(export_dir, name) for name in GAME_PLUGINS[source_game(export_dir)])
    return tuple(dict.fromkeys((*chain, *(folder for folder in game if folder.is_dir()))))


def asset_chain(export_dir) -> tuple:
    """_asset_chain(): an asset lookup's layer order (not records')."""
    return _asset_chain(str(export_dir))


def export_file(export_dir, *parts) -> Path:
    """`parts` in the first of overlays() and asset_chain() holding it (Layered.path).
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    return Layered((*overlays(), *asset_chain(export_dir)), *parts).path()


def replaced_file(export_dir, *parts) -> 'Path | None':
    """export_file()'s file's next layer down holding `parts`, or None."""
    found = [p for p in (Path(f).joinpath(*parts) for f in (*overlays(), *asset_chain(export_dir))) if p.exists()]
    return found[1] if len(found) > 1 else None


def overlays() -> tuple:
    """The asset overlay folders OVERLAY_ENV names, first searched first.
    See: docs/fork/fo4_plugin_layout.md#asset-overlays
    """
    return tuple(Path(p) for p in os.environ.get(OVERLAY_ENV, '').split(os.pathsep) if p)


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
    """`parts` under `export_dir`, layered over asset_chain()."""
    return Layered(asset_chain(export_dir), *parts)


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
