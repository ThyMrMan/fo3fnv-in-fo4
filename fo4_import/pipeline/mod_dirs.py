"""The folders a build looks for other plugins in: --plugin-dirs, then the Data folders of the app's mod sources
(an MO2 profile, a folder of mods). The build records each plugin it looked up and the file found
(build_inputs.asked), not the app settings or MO2's ini and mod list, so ticking a mod rebuilds only a plugin
whose lookup it changes.

See: docs/fork/fo4_mod_builds.md#mo2-answers
"""

import json
from pathlib import Path

from core.mod_sources import data_dirs, find_file, source_files
from fo4_import.app import settings
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.pipeline.build_inputs import asked, leave_out

FOUND = 'plugin found'


class PluginDirs(tuple):
    """The folders, with `spec` ([--plugin-dirs, settings path or None]) naming how they were found."""
    spec = None


def plugin_dirs(fixed: list, settings_path: 'str | Path | None') -> PluginDirs:
    """The folders `fixed`, then the Data folders of the mod sources in app settings `settings_path` (None: none);
    the files read for them are left out of the build's record (find() logs what was looked up)."""
    sources = settings.mod_sources(settings.load(Path(settings_path))) if settings_path else []
    out = PluginDirs((*map(Path, fixed), *data_dirs(sources)))
    out.spec = [[str(f) for f in fixed], str(settings_path) if settings_path else None]
    leave_out([*(f for s in sources for f in source_files(s)), *([settings_path] if settings_path else [])])
    return out


def find(plugin: str, dirs: tuple) -> 'Path | None':
    """`plugin`'s file (any case) in the game's Data folder or one of `dirs`; logged when `dirs` is a PluginDirs."""
    roots = [FALLOUT4_DIR / 'Data', *dirs]
    found = find_file(plugin, roots)
    if getattr(dirs, 'spec', None) is not None:
        asked(FOUND, json.dumps([plugin, *dirs.spec]), str(found) if found else None, roots)
    return found


def ask(arg: str) -> 'str | None':
    """A logged find() answered now (arg: [plugin, --plugin-dirs, settings path])."""
    plugin, fixed, settings_path = json.loads(arg)
    found = find(plugin, plugin_dirs(fixed, settings_path))
    return str(found) if found else None
