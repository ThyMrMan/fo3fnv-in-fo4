"""The source game's files behind an export: its Data folder and plugin, as asset_convert's source registry knows
them (export/FalloutNV.esm: the New Vegas install's Data; export/Fallout3.esm: Fallout 3's; export/<mod>: a mod
`convert.py --import-mod` imported, its plugin under the mod's _source).

See: docs/fork/fo4_pipeline.md#source-plugin
"""

from pathlib import Path

from asset_convert.sources import source_registry
from core.mod_sources import PLUGIN_SUFFIXES

#: Each source game's own plugins, the game first: New Vegas's five DLC and four pre-order packs, Fallout 3's DLC.
GAME_PLUGINS = {
    'fnv': ('FalloutNV.esm', 'DeadMoney.esm', 'HonestHearts.esm', 'OldWorldBlues.esm', 'LonesomeRoad.esm',
            'GunRunnersArsenal.esm', 'CaravanPack.esm', 'ClassicPack.esm', 'MercenaryPack.esm', 'TribalPack.esm'),
    'fo3': ('Fallout3.esm', 'Anchorage.esm', 'ThePitt.esm', 'BrokenSteel.esm', 'PointLookout.esm', 'Zeta.esm'),
}


def export_root(export_dir) -> Path:
    """The export folder holding `export_dir` (the one with the registry); its parent when none has one."""
    export_dir = Path(export_dir)
    return next((p for p in export_dir.parents if source_registry.registry_path(p).is_file()), export_dir.parent)


def plugin_name(export_dir) -> str:
    """The plugin file name the export at `export_dir` holds: its folder's name, or an imported mod's one plugin."""
    name = Path(export_dir).name
    if name.lower().endswith(PLUGIN_SUFFIXES):
        return name
    plugins = source_registry.mod_plugins(export_root(export_dir), name)
    if len(plugins) != 1:
        raise SystemExit(f'{name}: not one imported plugin in this mod folder ({plugins}); pass its plugin folder')
    return plugins[0]


def plugin_stem(export_dir) -> str:
    """plugin_name() without its extension."""
    return Path(plugin_name(export_dir)).stem


def record_dir(export_dir, plugin: str) -> Path:
    """The export folder of `plugin`'s records beside `export_dir`: export/<plugin>, else an imported mod's."""
    root = export_root(export_dir)
    plain = root / plugin
    return plain if plain.is_dir() else source_registry.record_dir(root, plugin)


def asset_dirs(export_dir) -> tuple:
    """`export_dir`, then the mod folder holding its assets when that differs (a mod shipping several plugins)."""
    export_dir = Path(export_dir)
    shared = source_registry.asset_root(export_root(export_dir), plugin_name(export_dir))
    return (export_dir,) if shared == export_dir or not shared.is_dir() else (export_dir, shared)


def source_data(export_dir) -> 'Path | None':
    """The Data folder the export `export_dir` came from; None if unknown."""
    data = source_registry.directory_for(export_root(export_dir), plugin_name(export_dir))
    return Path(data) if data else None


def source_plugin(export_dir) -> Path:
    """The plugin file the export at `export_dir` was read from: an imported mod's kept copy, else its Data's."""
    name = plugin_name(export_dir)
    imported = source_registry.plugin_binary(export_root(export_dir), name)
    data = source_data(export_dir)
    plugin = imported or (data / name if data else None)
    if plugin is None or not plugin.is_file():
        raise SystemExit(f'{name}: no source plugin registered for this export (source_registry)')
    return plugin
