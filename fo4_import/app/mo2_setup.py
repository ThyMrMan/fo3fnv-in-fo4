"""Mod Organizer setup and Play from the Finished screen. No Qt here.

The app's MO2 mod source names the instance and profile. Setting up enables the target's output folder (it must be
a mod folder of that instance) in the profile's mod list, highest priority, and its plugins in the profile's
plugin list and load order, after what is there: the game's plugin, its helper plugin and its Classic Look when
built, or an add-on's plugin. Each file changed is backed up first (`<file>.f3nv-backup`). MO2 rewrites these
files when it closes, so setup refuses while it runs. Play starts F4SE through MO2's F4SE executable for that
profile, or the game folder's f4se_loader.exe without MO2.

See: docs/fork/fo4_gui.md#mo2-setup
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.mod_sources import mo2_layout, profile_dir
from core.subprocess_flags import POPEN_FLAGS
from fo4_import.app import settings as S
from fo4_import.app import stages
from fo4_import.classic_look import plugin_name
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from tools.validate.fo4_install_check import F4SE_LOADER, executables

MO2_EXE, MO2_PROCESS = 'ModOrganizer.exe', 'ModOrganizer.exe'
BACKUP = '.f3nv-backup'
#: The profile files setup edits: the mod list, and the plugin list and load order.
MODLIST, PLUGINS, LOADORDER = 'modlist.txt', 'plugins.txt', 'loadorder.txt'


@dataclass(frozen=True)
class Instance:
    """An MO2 instance folder, the profile used ('' never: the selected one when the source names none), its mods
    folder and that profile's folder."""
    folder: Path
    profile: str
    mods: Path
    profile_dir: Path


def instance(settings: dict) -> 'Instance | None':
    """The app's MO2 mod source as an Instance, or None when there is none with a ModOrganizer.ini."""
    source = next((s for s in S.mod_sources(settings) if s.kind == 'mo2_profile'), None)
    if source is None or not (source.folder / 'ModOrganizer.ini').is_file():
        return None
    general, folders = mo2_layout(source.folder)
    profile = source.profile or general.get('selected_profile', '')
    return Instance(source.folder, profile, folders['mods'], profile_dir(general, folders, profile))


def environment(settings: dict) -> dict:
    """The stages' environment: the MO2 instance the Creation Kit runs through."""
    found = instance(settings)
    return {'F3NV_MO2': str(found.folder)} if found else {}


def plugins(settings: dict, source: str) -> list:
    """The target's built plugins to enable, in load order: the game's own three when built, or an add-on's."""
    chosen, built = stages.target(settings, source), stages.plugin_path(settings, source)
    names = [built.name, FALLOUT4_HELPER_PLUGIN, plugin_name(stages.GAMES[source]['plugin'])] if chosen.game \
        else [built.name]
    return [name for name in names if (chosen.output / name).is_file()]


def blocker(settings: dict, source: str, running=None) -> str:
    """Why setup cannot run now ('' when it can); `running()` says whether MO2 runs (default: mo2_running)."""
    found, folder = instance(settings), stages.target(settings, source).output
    if found is None:
        return 'no MO2 instance is set: add your MO2 profile as a mod source on the Setup screen'
    if folder.parent.resolve() != found.mods.resolve():
        return f'the output folder {folder} is not a mod folder of {found.mods}: choose one there'
    if not plugins(settings, source):
        return f'nothing is built in {folder} yet'
    if (running or mo2_running)():
        return 'Mod Organizer is running: close it first (it rewrites its lists when it closes)'
    return ''


def set_up(settings: dict, source: str) -> list:
    """Enable the target's mod and plugins in the MO2 profile (blocker() must be ''); the changes made, as lines."""
    found, folder = instance(settings), stages.target(settings, source).output
    names = plugins(settings, source)
    changes = [f'mod list: {line}' for line in _edit(found.profile_dir / MODLIST, enable_mod, folder.name)]
    changes += [f'plugins: {line}' for line in _edit(found.profile_dir / PLUGINS, enable_plugins, names)]
    changes += [f'load order: {line}' for line in _edit(found.profile_dir / LOADORDER, ordered, names)]
    return changes or ['already set up']


def _edit(path: Path, change, arg) -> list:
    """Apply `change(lines, arg) -> (lines, notes)` to text file `path`, backed up first when it changes; notes."""
    old = path.read_text(encoding='utf-8-sig').splitlines() if path.is_file() else []
    new, notes = change(old, arg)
    if new != old:
        if path.is_file():
            shutil.copyfile(path, path.with_name(path.name + BACKUP))
        path.write_text('\n'.join(new) + '\n', encoding='utf-8')
    return notes


def enable_mod(lines: list, name: str) -> tuple:
    """modlist.txt `lines` with mod `name` enabled (`+`), added under the header comments when absent; notes."""
    if f'+{name}' in lines:
        return lines, []
    if f'-{name}' in lines:
        return [f'+{name}' if line == f'-{name}' else line for line in lines], [f'enabled {name}']
    top = next((i for i, line in enumerate(lines) if not line.startswith('#')), len(lines))
    return lines[:top] + [f'+{name}'] + lines[top:], [f'added and enabled {name}']


def enable_plugins(lines: list, names: list) -> tuple:
    """plugins.txt `lines` with each of `names` ticked (`*`), appended in order when absent; notes."""
    out, notes, known = list(lines), [], {line.lstrip('*').lower(): i for i, line in enumerate(lines)}
    for name in names:
        at = known.get(name.lower())
        if at is None:
            out.append(f'*{name}')
            notes.append(f'added {name}')
        elif not out[at].startswith('*'):
            out[at] = f'*{out[at]}'
            notes.append(f'ticked {name}')
    return out, notes


def ordered(lines: list, names: list) -> tuple:
    """loadorder.txt `lines` with each of `names` appended in order when absent; notes."""
    have = {line.lower() for line in lines}
    added = [name for name in names if name.lower() not in have]
    return lines + added, [f'added {name}' for name in added]


def mo2_running() -> bool:
    """Whether Mod Organizer runs (Windows; False elsewhere)."""
    if sys.platform != 'win32':
        return False
    listing = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {MO2_PROCESS}'], capture_output=True, text=True,
                             **POPEN_FLAGS).stdout
    return MO2_PROCESS.lower() in listing.lower()


def play_command(settings: dict) -> tuple:
    """(argv, folder to run in) starting F4SE: through MO2's F4SE executable for the profile, else the game's
    f4se_loader.exe; ((), why) when neither is there."""
    found = instance(settings)
    if found is not None:
        title = next((t for t, binary in executables(found.folder).items() if binary.name.lower() ==
                      F4SE_LOADER), None)
        if title is None:
            return (), f'MO2 has no executable running {F4SE_LOADER}: add F4SE to its executables'
        return (str(found.folder / MO2_EXE), '-p', found.profile, 'run', '-e', title), str(found.folder)
    game = S.game_dir(settings, 'fallout4')
    loader = game / F4SE_LOADER if game else None
    if loader is None or not loader.is_file():
        return (), f'no {F4SE_LOADER} in the Fallout 4 folder: install F4SE'
    return (str(loader),), str(game)


def play(settings: dict) -> str:
    """Start the game (play_command); '' when started, else why not."""
    argv, where = play_command(settings)
    if not argv:
        return where
    subprocess.Popen(list(argv), cwd=where, **POPEN_FLAGS)
    return ''
