"""Install check: does this machine have what the README's "What you need" lists, and, after a conversion, does
each converted plugin sit in its own enabled MO2 mod with F3NV.dll in an F4SE/Plugins folder? Reads the app's
settings and the MO2 instance; writes nothing. One line per check; exit code 1 when any needs attention.

Usage: py -3.14 -m tools.validate.fo4_install_check [--settings F] [--mo2 DIR] [--profile NAME] [--work DIR]

See: docs/fork/fo4_plan_release.md#install-check
"""

import argparse
import ctypes
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from core.mod_sources import ModSource, data_dirs, find_file, mo2_layout, read_mo2_ini
from core.setup_check import exe_version
from fo4_import.app import settings as S
from fo4_import.base.build_files import all_moved_in
from fo4_import.base.source import GAME_PLUGINS
from fo4_import.pipeline.build_steps import STAMP_SUFFIX, stamp_path
from fo4_import.pipeline.creation_kit import CK_EXECUTABLE, MO2

GAME_VERSION = (1, 11, 240)
GB = 1 << 30
DISK_GB, RAM_GB = 100, 32
CK_URL = 'https://store.steampowered.com/app/1946160/'
F4SE_URL = 'https://f4se.silverlock.org/'
MO2_URL = 'https://github.com/ModOrganizer2/modorganizer'
F4SE_LOADER = 'f4se_loader.exe'
PLUGINS = Path('F4SE', 'Plugins')
RUNTIME_DLL = 'F3NV.dll'
#: Every F4SE plugin the output ships: ours, then Cleanroom UI's (fo4_import.cleanroom DIALOGUE_DLL, FRAMEWORK_DLL).
RUNTIME_DLLS = (RUNTIME_DLL, 'CleanroomDialogue.dll', 'CleanroomUI.dll')
BASE_PLUGIN, *FNV_DLC = GAME_PLUGINS['fnv']
#: (mod, the file it puts in Data, download page) per README mod; {version} is the game's version, dashed.
REQUIRED_MODS = (
    ('Address Library for F4SE Plugins', 'F4SE/Plugins/version-{version}.bin',
     'https://www.nexusmods.com/fallout4/mods/47327'),
    ('Mod Configuration Menu', 'F4SE/Plugins/mcm.dll', 'https://www.nexusmods.com/fallout4/mods/21497'),
    ('Black Landscape Fix (F4SE)', 'F4SE/Plugins/BlackLandscapeFixRD.dll',
     'https://www.nexusmods.com/fallout4/mods/108574'),
)
#: (mod, its file) of mods that must be off: F3NV.dll's dialogue menu refuses its hooks while XDI.dll loads.
CONFLICTING_MODS = (('Extended Dialogue Interface', 'F4SE/Plugins/XDI.dll'),)
#: Statuses that need nothing done.
PASSING = ('OK', 'NOT YET')


# ---------------------------------------------------------------------------
#  Shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Check:
    """One report line: what was checked, OK or the problem (MISSING, WRONG VERSION, ...), and what to do."""
    name: str
    status: str
    detail: str

    def line(self) -> str:
        """The check as one printed line."""
        return f'{self.status:<13} {self.name}: {self.detail}'


@dataclass(frozen=True)
class Machine:
    """What the checks read: game folders, Fallout4.exe's version, the MO2 instance and profile ('' = its
    selected one), the work folder, and installed RAM in bytes (None when unknown)."""
    fallout4: 'Path | None'
    falloutnv: 'Path | None'
    version: tuple
    mo2: 'Path | None'
    profile: str
    work: Path
    ram: 'int | None'


@dataclass(frozen=True)
class Mods:
    """The folders the game sees through MO2 (winning first), MO2 mods the profile leaves off, the game's Data and
    overwrite folders, and the profile's enabled plugins (None when unread)."""
    dirs: tuple
    off: tuple
    shared: tuple
    plugins: 'frozenset | None'


def _found(name: str, path: Path, missing: str) -> Check:
    """OK naming `path` when it is a file, else MISSING with `missing`."""
    return Check(name, 'OK', str(path)) if path.is_file() else Check(name, 'MISSING', missing)


def dotted(version: tuple) -> str:
    """`version`'s numbers joined by dots."""
    return '.'.join(map(str, version))


# ---------------------------------------------------------------------------
#  Fallout 4, the Creation Kit, F4SE
# ---------------------------------------------------------------------------

def game_checks(m: Machine) -> list:
    """Fallout 4 and its version, the Creation Kit, and F4SE for that version."""
    if not m.fallout4 or not (m.fallout4 / 'Fallout4.exe').is_file():
        return [Check('Fallout 4', 'MISSING', 'not found; install it from Steam and start it once, or choose its '
                      'folder in the app')]
    return [Check('Fallout 4', 'OK', str(m.fallout4)), version_check(m.version),
            _found('Creation Kit', m.fallout4 / 'CreationKit.exe',
                   f'install the Fallout 4 Creation Kit from Steam: {CK_URL}'),
            f4se_check(m.fallout4, m.version)]


def version_check(version: tuple) -> Check:
    """OK when Fallout4.exe is GAME_VERSION, else WRONG VERSION."""
    need = dotted(GAME_VERSION)
    if version[:3] == GAME_VERSION:
        return Check('Fallout 4 version', 'OK', need)
    shown = dotted(version[:3]) if version else 'unreadable'
    return Check('Fallout 4 version', 'WRONG VERSION', f'{shown}; the converter needs {need}, and F4SE and the '
                 'Address Library must match it')


def f4se_check(game: Path, version: tuple) -> Check:
    """F4SE's loader in the game folder and its DLL for the game's version."""
    if not (game / F4SE_LOADER).is_file():
        return Check('F4SE', 'MISSING', f'copy F4SE {dotted(GAME_VERSION)} ({F4SE_URL}) into {game}')
    dll = f"f4se_{'_'.join(map(str, (version or GAME_VERSION)[:3]))}.dll"
    if (game / dll).is_file():
        return Check('F4SE', 'OK', dll)
    others = ', '.join(sorted(p.name for p in game.glob('f4se_1_*.dll'))) or 'no f4se_*.dll'
    return Check('F4SE', 'WRONG VERSION', f'{others} found, {dll} needed; install F4SE for {dotted(GAME_VERSION)} '
                 f'from {F4SE_URL}')


# ---------------------------------------------------------------------------
#  MO2
# ---------------------------------------------------------------------------

def has_mo2(m: Machine) -> bool:
    """Whether `m` names a folder holding ModOrganizer.ini."""
    return bool(m.mo2) and (m.mo2 / 'ModOrganizer.ini').is_file()


def executables(instance: Path) -> dict:
    """{title: binary} of an MO2 instance's executables."""
    section = read_mo2_ini(instance / 'ModOrganizer.ini').get('customExecutables', {})
    return {title: Path(section.get(key[:-len('title')] + 'binary', '')) for key, title in section.items()
            if key.endswith('\\title')}


def mo2_checks(m: Machine) -> list:
    """The MO2 instance, its profile, its game folder, and its Creation Kit and F4SE executables."""
    if not has_mo2(m):
        where = f' at {m.mo2}' if m.mo2 else ''
        return [Check('Mod Organizer 2', 'MISSING', f'no MO2 instance (a folder holding ModOrganizer.ini){where}; '
                      f'install MO2 ({MO2_URL}) and choose it in the app, or pass --mo2')]
    general, folders = mo2_layout(m.mo2)
    profile = m.profile or general.get('selected_profile', '')
    out = [Check('Mod Organizer 2', 'OK', str(m.mo2)),
           _found('MO2 profile', folders['profiles'] / profile / 'modlist.txt',
                  f'profile "{profile}" has no modlist.txt; pick an existing profile')]
    game = general.get('gamePath')
    if m.fallout4 and game and os.path.normcase(Path(game).resolve()) != os.path.normcase(m.fallout4.resolve()):
        out.append(Check('MO2 game folder', 'WRONG', f'MO2 manages {game}, not {m.fallout4}'))
    exes = executables(m.mo2)
    ck = exes.get(CK_EXECUTABLE)
    out.append(Check(f'MO2 "{CK_EXECUTABLE}" executable', 'OK', str(ck)) if ck and ck.is_file() else
               Check(f'MO2 "{CK_EXECUTABLE}" executable', 'MISSING', f'add an MO2 executable titled '
                     f'"{CK_EXECUTABLE}" running CreationKit.exe; the build runs the CK through it'))
    f4se = next((title for title, binary in exes.items() if binary.name.lower() == F4SE_LOADER), None)
    out.append(Check('MO2 F4SE executable', 'OK', f'"{f4se}" (play through it)') if f4se else
               Check('MO2 F4SE executable', 'MISSING', f'add an MO2 executable running {F4SE_LOADER}'))
    return out


def mod_folders(m: Machine) -> Mods:
    """What the game sees: the MO2 profile's folders when there is a usable instance, else the game's Data."""
    game = (m.fallout4 / 'Data',) if m.fallout4 else ()
    if not has_mo2(m):
        return Mods(game, (), game, None)
    general, folders = mo2_layout(m.mo2)
    profile = folders['profiles'] / (m.profile or general.get('selected_profile', ''))
    try:
        dirs = tuple(data_dirs([ModSource(m.mo2, 'mo2_profile', m.profile)]))
    except FileNotFoundError:
        return Mods(game, (), game, None)
    mods = folders['mods']
    off = tuple(sorted((p for p in mods.iterdir() if p.is_dir() and p not in dirs), key=lambda p: p.name.casefold())
                ) if mods.is_dir() else ()
    shared = tuple(d for d in dirs if d.parent != mods)
    return Mods(dirs, off, shared, enabled_plugins(profile / 'plugins.txt'))


def enabled_plugins(path: Path) -> 'frozenset | None':
    """Lowercase names a plugins.txt enables (`*`), or None when there is none."""
    if not path.is_file():
        return None
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return frozenset(line[1:].strip().lower() for line in lines if line.startswith('*'))


def holder(rel: Path, dirs: tuple) -> 'Path | None':
    """The first of `dirs` holding `rel` (names in any case), or None."""
    return next((d for d in dirs if find_file(rel.name, [d / rel.parent])), None)


def mod_checks(m: Machine, mods: Mods) -> list:
    """Each README mod's file where the game sees it, else in an MO2 mod the profile leaves off, else missing."""
    version = '-'.join(map(str, (*m.version[:3], 0) if m.version else (*GAME_VERSION, 0)))
    out = []
    for name, file, url in REQUIRED_MODS:
        rel = Path(file.format(version=version))
        on, off = holder(rel, mods.dirs), holder(rel, mods.off)
        if on:
            out.append(Check(name, 'OK', f'{rel.name} in "{on.name}"'))
        elif off:
            out.append(Check(name, 'NOT ENABLED', f'MO2 mod "{off.name}" has {rel.name}; enable it in the profile'))
        else:
            out.append(Check(name, 'MISSING', f'{rel.name} not found; install it in MO2: {url}'))
    return out + conflict_checks(mods)


def conflict_checks(mods: Mods) -> list:
    """CONFLICT for each CONFLICTING_MODS file the game sees."""
    found = [(name, rel, holder(Path(rel), mods.dirs)) for name, rel in CONFLICTING_MODS]
    return [Check(name, 'CONFLICT', f'{Path(rel).name} in "{on.name}"; disable that mod: the converted dialogue '
                  'uses the menu of F3NV.dll') for name, rel, on in found if on]


# ---------------------------------------------------------------------------
#  New Vegas, disk, RAM
# ---------------------------------------------------------------------------

def fnv_checks(fnv: 'Path | None') -> list:
    """FalloutNV.esm in the New Vegas install, and which DLC it has."""
    data = fnv / 'Data' if fnv else None
    if not data or not find_file(BASE_PLUGIN, [data]):
        return [Check('Fallout: New Vegas', 'MISSING', 'FalloutNV.esm not found; install New Vegas (Steam or GOG) '
                      'or choose its folder in the app')]
    have = [d for d in FNV_DLC if find_file(d, [data])]
    lacking = [d for d in FNV_DLC if d not in have]
    dlc = f"{len(have)} of {len(FNV_DLC)}" + (f"; not installed (they won't convert): {', '.join(lacking)}"
                                             if lacking else '')
    return [Check('Fallout: New Vegas', 'OK', str(fnv)), Check('New Vegas DLC', 'OK', dlc)]


def disk_check(free: int, where: Path) -> Check:
    """OK with at least DISK_GB free, else LOW."""
    shown = f'{free / GB:.0f} GB free on {where.anchor or where}'
    if free >= DISK_GB * GB:
        return Check('Free disk', 'OK', shown)
    return Check('Free disk', 'LOW', f'{shown}; allow about {DISK_GB} GB for the export, caches and output')


def ram_check(ram: 'int | None') -> Check:
    """OK with at least RAM_GB installed, else LOW."""
    if ram is None:
        return Check('RAM', 'OK', f'could not be read; {RAM_GB} GB recommended')
    shown = f'{ram / GB:.0f} GB'
    return Check('RAM', 'OK', shown) if ram >= RAM_GB * GB else \
        Check('RAM', 'LOW', f'{shown}; {RAM_GB} GB recommended, the build may run out of memory')


def installed_ram() -> 'int | None':
    """Physically installed RAM in bytes (Windows), or None."""
    kb = ctypes.c_ulonglong()
    try:
        ok = ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(kb))
    except AttributeError:
        return None
    return kb.value * 1024 if ok else None


def free_bytes(folder: Path) -> int:
    """Free bytes on the drive of `folder`, or of its nearest existing parent."""
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    return shutil.disk_usage(folder).free


# ---------------------------------------------------------------------------
#  After a conversion
# ---------------------------------------------------------------------------

def converted(dirs: tuple) -> dict:
    """{folder: [plugin]} of the folders holding a converted plugin and its build stamp."""
    out = {}
    for folder in dirs:
        for stamp in all_moved_in(folder, '*' + STAMP_SUFFIX):
            plugin = stamp.name[:-len(STAMP_SUFFIX)]
            if (folder / plugin).is_file():
                out.setdefault(folder, []).append(plugin)
    return out


def stamp_status(path: Path) -> str:
    """The `status` a build stamp records ('' when unreadable)."""
    try:
        return json.loads(path.read_text(encoding='utf-8')).get('status', '')
    except (OSError, ValueError):
        return ''


def plugin_check(plugin: str, folder: Path, found: dict, mods: Mods) -> Check:
    """One converted plugin: in its own enabled MO2 mod, once, finished, and ticked in the plugin list."""
    together = [p for p in found[folder] if p != plugin]
    elsewhere = [f.name for f, plugins in found.items() if f != folder and plugin.lower() in map(str.lower, plugins)]
    status = stamp_status(stamp_path(folder / plugin))
    if folder in mods.shared:
        return Check(plugin, 'WRONG PLACE', f'in {folder}; move it into its own MO2 mod')
    if together:
        return Check(plugin, 'WRONG PLACE', f'MO2 mod "{folder.name}" also holds {", ".join(together)}; give each '
                     'plugin its own mod folder')
    if elsewhere:
        return Check(plugin, 'WRONG PLACE', f'in "{folder.name}" and also {", ".join(elsewhere)}; keep one')
    if status != 'finished':
        return Check(plugin, 'UNFINISHED', f'its build stamp says "{status}"; rebuild it')
    if mods.plugins is not None and plugin.lower() not in mods.plugins:
        return Check(plugin, 'NOT ENABLED', f'in "{folder.name}" but not ticked in the profile\'s plugin list')
    return Check(plugin, 'OK', f'in its own MO2 mod "{folder.name}"')


def output_checks(mods: Mods) -> list:
    """Each converted plugin's place, then each of RUNTIME_DLLS; NOT YET when nothing is converted."""
    found = converted(mods.dirs)
    if not found:
        return [Check('Converted plugins', 'NOT YET', 'none where the game sees them; run this again after '
                      'converting and adding the output to MO2')]
    out = [plugin_check(plugin, folder, found, mods) for folder, plugins in found.items() for plugin in plugins]
    for name in RUNTIME_DLLS:
        dll = holder(PLUGINS / name, mods.dirs)
        out.append(Check(name, 'OK', f'in "{dll.name}"') if dll else
                   Check(name, 'MISSING', f'copy tes_runtime/dist/{name} into F4SE/Plugins in the mod '
                         f'holding {BASE_PLUGIN}'))
    return out


# ---------------------------------------------------------------------------
#  The report
# ---------------------------------------------------------------------------

def checks(m: Machine, free: int) -> list:
    """Every check for `m` (`free` bytes free on its work drive), README order."""
    mods = mod_folders(m)
    return [*game_checks(m), *fnv_checks(m.falloutnv), *mo2_checks(m), *mod_checks(m, mods),
            ram_check(m.ram), disk_check(free, m.work), *output_checks(mods)]


def machine(args: argparse.Namespace) -> Machine:
    """This machine as the app's settings (or the arguments) describe it."""
    return machine_from(S.load(args.settings), args.mo2, args.profile, args.work)


def machine_from(settings: dict, mo2: 'Path | None' = None, profile: 'str | None' = None,
                 work: 'Path | None' = None) -> Machine:
    """This machine as `settings` describe it, `mo2`, `profile` and `work` overriding them when given."""
    source = next((s for s in S.mod_sources(settings) if s.kind == 'mo2_profile'), None)
    mo2 = mo2 or (source.folder if source else MO2)
    profile = profile if profile is not None else (source.profile if source else '')
    fallout4 = S.game_dir(settings, 'fallout4')
    version = exe_version(fallout4 / 'Fallout4.exe') if fallout4 else ()
    return Machine(fallout4, S.game_dir(settings, 'falloutnv'), version, Path(mo2), profile,
                   work or S.work_dir(settings), installed_ram())


def main(argv=None) -> int:
    """Print one line per check and a summary; 1 when any needs attention."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--settings', type=Path, help="the app's settings file (default: the app's own)")
    ap.add_argument('--mo2', type=Path, help="MO2 instance folder (default: the app's MO2 mod source)")
    ap.add_argument('--profile', help='MO2 profile (default: the mod source\'s, else MO2\'s selected one)')
    ap.add_argument('--work', type=Path, help="folder whose drive needs the free space (default: the app's work)")
    m = machine(ap.parse_args(argv))
    report = checks(m, free_bytes(m.work))
    for check in report:
        print(check.line())
    todo = [c for c in report if c.status not in PASSING]
    print(f'\n{len(todo)} of {len(report)} checks need attention.' if todo else f'\nAll {len(report)} checks OK.')
    return 1 if todo else 0


if __name__ == '__main__':
    sys.exit(main())
