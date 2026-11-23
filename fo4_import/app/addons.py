"""What the Convert screen converts besides the game: its DLC (found in the game's Data folder) and imported mods
(a mod folder, `convert.py --import-mod`). No Qt here.

Each source game keeps its add-ons in its settings block (`addons`: plugin, mod folder, output folder) and the one
chosen (`target`, '' for the game). An add-on builds into its own output folder, its masters' built plugins found
in theirs. Its build scope comes from its own export once exported (build_scope): the worldspaces it adds that a
door or script reaches, whole; the master worldspaces whose grid cells it changes, the largest as a region around
those cells and the others whole; with neither, its own first interior as the start cell.

See: docs/fork/fo4_gui.md#addons
"""

import collections
import struct
from dataclasses import dataclass
from pathlib import Path

from asset_convert.sources import source_registry
from fo4_import.app import settings as S
from fo4_import.base.install import masters_of
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.export_index import export_masters, export_records, own_records
from fo4_import.pipeline.run import edited_grids, reached_worlds

#: Plugin file suffixes an add-on can have.
PLUGIN_SUFFIXES = ('.esm', '.esp')
#: FNV CELL DATA flag of an interior cell.
INTERIOR = 0x1
#: A record header's size, and the bytes a plugin header is read from.
HEADER = 24


@dataclass(frozen=True)
class Target:
    """What a run converts: the source `plugin`, its imported `mod` folder ('' for the game and DLC), the output
    folder, and whether it is the game itself."""
    plugin: str
    mod: str
    output: Path
    game: bool


def entries(settings: dict, source: str) -> list:
    """`source`'s add-on entries ({plugin, mod, output})."""
    return settings['per_source'][source].setdefault('addons', [])


def entry(settings: dict, source: str, plugin: str) -> 'dict | None':
    """The add-on entry for `plugin` (any case), or None."""
    return next((e for e in entries(settings, source) if e['plugin'].lower() == plugin.lower()), None)


def add(settings: dict, source: str, plugin: str, mod: str = '') -> dict:
    """`plugin` added to `source`'s add-ons (kept when already there); its entry."""
    found = entry(settings, source, plugin)
    if found is None:
        found = {'plugin': plugin, 'mod': mod, 'output': ''}
        entries(settings, source).append(found)
    return found


def output(settings: dict, source: str, plugin: str, master: str) -> Path:
    """Where `plugin` builds: the game's output for `master`, else its entry's folder, else default_output."""
    if plugin.lower() == master.lower():
        return S.output_dir(settings, source)
    chosen = (entry(settings, source, plugin) or {}).get('output')
    return Path(chosen) if chosen else default_output(settings, source, plugin)


def default_output(settings: dict, source: str, plugin: str) -> Path:
    """An add-on's output when none is chosen: the folder beside the game's output holding its build stamp
    (an earlier build's, whatever its name), else the game's mod folder name for its stem there
    (S.mod_folder_name: `F3NV FNV - DeadMoney`).
    See: docs/fork/fo4_gui.md#addons
    """
    parent = S.output_dir(settings, source).parent
    built = [d for d in (parent.iterdir() if parent.is_dir() else ()) if stamp_path(d / plugin).is_file()]
    return built[0] if built else parent / S.mod_folder_name(source, Path(plugin).stem)


def target(settings: dict, source: str, master: str) -> Target:
    """The chosen target of `source` (the game, master `master`, when none or an unknown one is chosen)."""
    name = settings['per_source'][source].get('target', '')
    chosen = entry(settings, source, name) if name else None
    if chosen is None:
        return Target(master, '', S.output_dir(settings, source), True)
    return Target(chosen['plugin'], chosen['mod'], output(settings, source, chosen['plugin'], master), False)


def dlc(data: Path, master: str) -> list:
    """The plugins in game Data folder `data` built on `master` (the DLC and packs), sorted."""
    if not data.is_dir():
        return []
    found = [p.name for p in data.iterdir() if p.suffix.lower() in PLUGIN_SUFFIXES and p.name.lower() != master.lower()
             and master.lower() in (m.lower() for m in plugin_masters(p))]
    return sorted(found, key=str.lower)


def plugin_masters(path: Path) -> list:
    """The master file names in plugin `path`'s header ([] when unreadable)."""
    try:
        with open(path, 'rb') as handle:
            head = handle.read(HEADER)
            return masters_of(head + handle.read(struct.unpack_from('<I', head, 4)[0])) if len(head) == HEADER else []
    except OSError:
        return []


def mod_plugins(folder: Path) -> list:
    """The plugin files in mod folder `folder` (its root or its Data folder), sorted."""
    roots = [folder, *(p for p in folder.iterdir() if p.is_dir() and p.name.lower() == 'data')] if folder.is_dir() \
        else []
    return sorted((p for root in roots for p in root.iterdir() if p.suffix.lower() in PLUGIN_SUFFIXES),
                  key=lambda p: p.name.lower())


def source_file(settings: dict, source: str, chosen: Target, export_root: Path) -> 'Path | None':
    """The plugin file `chosen` converts: the imported copy, else the mod folder's, else the game Data's."""
    if chosen.mod:
        kept = source_registry.plugin_binary(export_root, chosen.plugin)
        if kept:
            return Path(kept)
        return next((p for p in mod_plugins(Path(chosen.mod)) if p.name.lower() == chosen.plugin.lower()), None)
    game = S.game_dir(settings, source)
    return game / 'Data' / chosen.plugin if game else None


def build_scope(export_dir: Path, region: 'tuple | None' = None) -> list:
    """fo4_import.pipeline.run's --world/--region/--whole and cell arguments for an add-on export (build scope in
    the module notes); `region` (grid corners) replaces the derived one on the largest changed master worldspace.
    See: docs/fork/fo4_gui.md#addons
    """
    folder, worlds = str(export_dir), export_records(str(export_dir), 'WRLD')
    own = len(export_masters(folder))
    cells = export_records(folder, 'CELL')
    reached = reached_worlds(folder, cells)
    size = collections.Counter(c.get('ParentWRLD') for c in cells if 'XCLC.X' in c)
    new = [w for w in own_records(folder, 'WRLD') if int(w['FormID'], 16) >> 24 == own and w.get('EditorID')
           and w['FormID'] in reached and size[w['FormID']]]
    changed = {world: grids for world, grids in edited_grids(folder).items() if int(world, 16) >> 24 != own}
    names = {w['FormID']: w['EditorID'] for w in worlds if w.get('EditorID')}
    masters = sorted((w for w in changed if w in names), key=lambda w: -size[w])
    if not masters:
        return ['--world', *(names[w['FormID']] for w in new), '--whole'] if new else _start_cell(folder)
    corners = region or (*min(changed[masters[0]]), *min(changed[masters[0]]))
    rest = [w['EditorID'] for w in new] + [names[w] for w in masters[1:]]
    return ['--world', names[masters[0]], *rest, '--region', *map(str, corners)]


def _start_cell(folder: str) -> list:
    """[the add-on's first own interior's EditorID], its new ones first; [] with none."""
    own = len(export_masters(folder))
    inside = [c for c in own_records(folder, 'CELL') if int(c.get('DATA.Flags', 0)) & INTERIOR and c.get('EditorID')]
    inside.sort(key=lambda c: int(c['FormID'], 16) >> 24 != own)
    return [inside[0]['EditorID']] if inside else []
