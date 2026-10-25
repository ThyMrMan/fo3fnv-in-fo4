"""The app's choices: one JSON file saying where every file lives.

The file is `fo4_app.json` beside the app when one is there (portable), else in the OS's config folder. An empty
string means "detect" for a game and "default" for a folder; `defaults()` is the full shape, and a saved file is
laid over it key by key, so older files gain new keys.

See: docs/fork/fo4_gui.md#choices
"""

import json
import os
import sys
from pathlib import Path

from core import game_dirs
from core.mod_sources import from_settings

APP_DIR = Path(__file__).resolve().parents[2]
FILE_NAME = 'fo4_app.json'
#: The games the app converts from, and the folder name each gets under the work folder.
SOURCES = {'falloutnv': 'FalloutNV', 'fallout3': 'Fallout3'}
GAMES = ('fallout4', 'falloutnv', 'fallout3')
OUTPUT_KINDS = ('folder', 'zip')
#: Where a source's replacement file lives: beside the app, in its output folder, or a path of the user's.
REPLACEMENT_PLACES = ('app', 'output', 'custom')


def defaults() -> dict:
    """A fresh copy of every setting with its default."""
    return {
        'version': 1,
        'source': 'falloutnv',
        'games': {game: '' for game in GAMES},
        'mod_sources': [],
        'work_dir': '',
        'tools': {'wine': '', 'nifskope': ''},
        'per_source': {source: {'output': {'kind': 'folder', 'path': ''},
                                'replacements': {'where': 'app', 'path': ''},
                                'scripts': '', 'profile': ''} for source in SOURCES},
    }


def config_dir() -> Path:
    """This OS's folder for the app's settings."""
    home = Path.home()
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', home / 'AppData' / 'Roaming')) / 'F3NV'
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'F3NV'
    return Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')) / 'f3nv'


def settings_path() -> Path:
    """The settings file: beside the app when one is there, else in config_dir()."""
    portable = APP_DIR / FILE_NAME
    return portable if portable.is_file() else config_dir() / FILE_NAME


def load(path: 'Path | None' = None) -> dict:
    """The saved settings at `path` (default settings_path()) over defaults(); defaults() when none are saved."""
    path = Path(path) if path else settings_path()
    saved = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    settings = _merged(defaults(), saved)
    check(settings)
    return settings


def save(settings: dict, path: 'Path | None' = None) -> Path:
    """Write `settings` to `path` (default settings_path()); the path written."""
    check(settings)
    path = Path(path) if path else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
    return path


def check(settings: dict) -> None:
    """Refuse settings naming an unknown source, output kind, replacement place or mod source kind."""
    if settings['source'] not in SOURCES:
        raise ValueError(f"source {settings['source']!r} is not one of {tuple(SOURCES)}")
    for source, block in settings['per_source'].items():
        if block['output']['kind'] not in OUTPUT_KINDS:
            raise ValueError(f"{source}: output kind {block['output']['kind']!r} is not one of {OUTPUT_KINDS}")
        if block['replacements']['where'] not in REPLACEMENT_PLACES:
            raise ValueError(f"{source}: replacements in {block['replacements']['where']!r}, not one of "
                             f'{REPLACEMENT_PLACES}')
    mod_sources(settings)


def game_dir(settings: dict, game: str) -> 'Path | None':
    """Where `game` is installed: the user's choice, else detected, else None."""
    chosen = settings['games'].get(game)
    return Path(chosen) if chosen else game_dirs.find(game)


def work_dir(settings: dict) -> Path:
    """Exports and caches: the user's choice, else `work` in config_dir()."""
    return Path(settings['work_dir']) if settings['work_dir'] else config_dir() / 'work'


def output_dir(settings: dict, source: str) -> Path:
    """`source`'s output: the user's choice, else default_output_dir()."""
    chosen = settings['per_source'][source]['output']['path']
    return Path(chosen) if chosen else default_output_dir(settings, source)


def default_output_dir(settings: dict, source: str) -> Path:
    """`source`'s output when none is chosen: `output/<game>` in work_dir()."""
    return work_dir(settings) / 'output' / SOURCES[source]


def scripts_dir(settings: dict, source: str) -> Path:
    """`source`'s converted scripts: the user's choice, else the default."""
    chosen = settings['per_source'][source]['scripts']
    return Path(chosen) if chosen else default_scripts_dir(settings, source)


def default_scripts_dir(settings: dict, source: str) -> Path:
    """`source`'s scripts when none are chosen: `scripts/<master>` in work_dir()."""
    return work_dir(settings) / 'scripts' / f'{SOURCES[source]}.esm'


def replacement_file(settings: dict, source: str) -> Path:
    """`source`'s replacement file, at the place the user chose (REPLACEMENT_PLACES)."""
    block = settings['per_source'][source]['replacements']
    if block['where'] == 'custom':
        if not block['path']:
            raise ValueError(f'{source}: replacements are set to a custom path, but no path is given')
        return Path(block['path'])
    if block['where'] == 'output':
        return output_dir(settings, source) / 'replacements.json'
    return APP_DIR / 'replacements' / f'{source}.json'


def mod_sources(settings: dict) -> list:
    """The enabled mod sources (core.mod_sources.ModSource), in order."""
    return from_settings(settings['mod_sources'])


def _merged(base: dict, over: dict) -> dict:
    """`base` with `over`'s keys laid on top, nested dicts merged key by key."""
    out = dict(base)
    for key, value in over.items():
        out[key] = _merged(base[key], value) if isinstance(value, dict) and isinstance(base.get(key), dict) \
            else value
    return out
