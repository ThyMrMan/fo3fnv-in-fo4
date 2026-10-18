"""The source game's files behind an export: its Data folder and plugin, as asset_convert's source registry knows
them (export/FalloutNV.esm: the New Vegas install's Data; export/Fallout3.esm: Fallout 3's).

See: docs/fork/fo4_pipeline.md#source-plugin
"""

from pathlib import Path

from asset_convert.sources import source_registry


def source_data(export_dir) -> 'Path | None':
    """The Data folder the export `export_dir` came from; None if unknown."""
    export_dir = Path(export_dir)
    data = source_registry.directory_for(export_dir.parent, export_dir.name)
    return Path(data) if data else None


def source_plugin(export_dir) -> Path:
    """The plugin file the export at `export_dir` was read from."""
    data = source_data(export_dir)
    plugin = data / Path(export_dir).name if data else None
    if plugin is None or not plugin.is_file():
        raise SystemExit(f'{Path(export_dir).name}: no source plugin registered for this export (source_registry)')
    return plugin
