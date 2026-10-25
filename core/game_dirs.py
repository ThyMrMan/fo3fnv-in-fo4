"""Where a game is installed, on Windows, macOS or Linux: the Windows registry (source_paths), then Steam's
libraries on any OS (Proton installs on Linux included). Returns the game folder, the one holding `Data`.

See: docs/fork/fo4_gui.md#cross-platform
"""

import os
import re
import sys
from pathlib import Path

from source_paths import find_game_path

#: Game -> its Steam app ids, most common first (Fallout 3 GOTY, then the original release).
STEAM_APPS = {'fallout4': (377160,), 'falloutnv': (22380,), 'fallout3': (22370, 22300)}
#: Quoted values in Steam's text files (libraryfolders.vdf, appmanifest_*.acf), backslashes escaped.
_VDF_VALUE = r'"{key}"\s+"((?:[^"\\]|\\.)*)"'


def find(game: str) -> 'Path | None':
    """The folder `game` is installed in (registry first, then Steam), or None."""
    data = find_game_path(game)
    if data:
        return Path(data).parent
    return steam_app_dir(STEAM_APPS.get(game, ()))


def steam_roots() -> list:
    """Folders Steam may be installed in on this OS, the ones that exist."""
    home = Path.home()
    if sys.platform == 'win32':
        candidates = [_steam_registry_path(), Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
                      / 'Steam']
    elif sys.platform == 'darwin':
        candidates = [home / 'Library' / 'Application Support' / 'Steam']
    else:
        candidates = [home / '.steam' / 'steam', home / '.local' / 'share' / 'Steam',
                      home / '.var' / 'app' / 'com.valvesoftware.Steam' / '.local' / 'share' / 'Steam']
    return _unique(c for c in candidates if c and (c / 'steamapps').is_dir())


def steam_libraries(roots: 'list | None' = None) -> list:
    """Every Steam library folder (holding `steamapps`) the roots' libraryfolders.vdf name, roots included."""
    found = []
    for root in steam_roots() if roots is None else roots:
        found.append(Path(root))
        vdf = Path(root) / 'steamapps' / 'libraryfolders.vdf'
        if vdf.is_file():
            found += [Path(p) for p in _vdf_values(vdf.read_text(encoding='utf-8', errors='replace'), 'path')]
    return _unique(f for f in found if (f / 'steamapps').is_dir())


def steam_app_dir(app_ids: tuple, roots: 'list | None' = None) -> 'Path | None':
    """The install folder of the first of `app_ids` a Steam library has a manifest for, if it holds `Data`."""
    libraries = steam_libraries(roots)
    for app in app_ids:
        for library in libraries:
            manifest = library / 'steamapps' / f'appmanifest_{app}.acf'
            if not manifest.is_file():
                continue
            names = _vdf_values(manifest.read_text(encoding='utf-8', errors='replace'), 'installdir')
            folder = library / 'steamapps' / 'common' / names[0] if names else None
            if folder and (folder / 'Data').is_dir():
                return folder
    return None


def _vdf_values(text: str, key: str) -> list:
    """Every value of `key` in a Steam text file, unescaped."""
    return [v.replace('\\\\', '\\') for v in re.findall(_VDF_VALUE.format(key=key), text)]


def _steam_registry_path() -> 'Path | None':
    """Steam's folder as Windows records it for this user, or None."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            return Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        return None


def _unique(paths) -> list:
    """`paths` without repeats (compared resolved and case-folded), in order."""
    seen, out = set(), []
    for path in paths:
        key = os.path.normcase(str(Path(path).resolve()))
        if key not in seen:
            seen.add(key)
            out.append(Path(path))
    return out
