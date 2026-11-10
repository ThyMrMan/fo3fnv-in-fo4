"""Mods read from plain folders, whatever manages them (MO2, Vortex, by hand).

A source is a folder and a kind:

- `folder_of_mods`: each subfolder is one mod (a generic mod folder, Vortex's staging folder, MO2's `mods`),
  in name order;
- `flat`: one folder laid out like the game's `Data`;
- `mo2_profile`: an MO2 instance (the folder holding `ModOrganizer.ini`): the game's Data, then the profile's
  enabled mods in MO2's priority, then `overwrite`. Read only.

Later sources win over earlier ones; names are matched ignoring case, as the game does.

See: docs/fork/fo4_gui.md#mod-sources
"""

from dataclasses import dataclass
from pathlib import Path

KINDS = ('folder_of_mods', 'flat', 'mo2_profile')
PLUGIN_SUFFIXES = ('.esm', '.esp', '.esl')
#: MO2's stand-in for the instance's base folder in its path settings (PathSettings::BaseDirVariable).
MO2_BASE = '%BASE_DIR%'


# ---------------------------------------------------------------------------
#  Sources
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModSource:
    """A folder of mods and how to read it (KINDS); `profile` names an MO2 profile ('' = the selected one)."""
    folder: Path
    kind: str
    profile: str = ''

    def __post_init__(self):
        """Refuse a kind not in KINDS."""
        if self.kind not in KINDS:
            raise ValueError(f'mod source kind {self.kind!r} is not one of {KINDS}')


def from_settings(entries: list) -> list:
    """ModSources from settings entries ({folder, kind, profile, enabled}), enabled."""
    return [ModSource(Path(e['folder']), e['kind'], e.get('profile', '')) for e in entries if e.get('enabled', True)]


def mod_folders(source: ModSource) -> list:
    """The Data-like folders `source` supplies, lowest priority first."""
    if source.kind == 'flat':
        return [source.folder]
    if source.kind == 'folder_of_mods':
        return sorted((p for p in source.folder.iterdir() if p.is_dir()), key=lambda p: p.name.casefold()) \
            if source.folder.is_dir() else []
    return mo2_folders(source.folder, source.profile)


def data_dirs(sources: list) -> list:
    """Every source's existing Data-like folders, the winning one first."""
    ordered = [f for source in sources for f in mod_folders(source)]
    out = []
    for folder in reversed(ordered):
        if folder.is_dir() and folder not in out:
            out.append(folder)
    return out


def plugins(sources: list) -> dict:
    """{lowercase plugin name: its winning file} over every source."""
    found = {}
    for folder in data_dirs(sources):
        for path in folder.iterdir():
            if path.suffix.lower() in PLUGIN_SUFFIXES and path.is_file():
                found.setdefault(path.name.lower(), path)
    return found


def find_file(name: str, dirs: list) -> 'Path | None':
    """The file called `name` (any case) directly in the first of `dirs` that has it, or None."""
    want = name.lower()
    for folder in map(Path, dirs):
        if (folder / name).is_file():
            return folder / name
        if folder.is_dir():
            match = next((p for p in folder.iterdir() if p.name.lower() == want and p.is_file()), None)
            if match:
                return match
    return None


# ---------------------------------------------------------------------------
#  MO2
# ---------------------------------------------------------------------------

def mo2_profiles(instance: Path) -> list:
    """An MO2 instance's profile names, sorted ([] when the folder holds no ModOrganizer.ini)."""
    if not (Path(instance) / 'ModOrganizer.ini').is_file():
        return []
    folder = mo2_layout(Path(instance))[1]['profiles']
    return sorted((p.name for p in folder.iterdir() if (p / 'modlist.txt').is_file()), key=str.casefold) \
        if folder.is_dir() else []


def mo2_layout(instance: Path) -> tuple:
    """(the ini's General section, {mods, profiles, overwrite: folder}) of an MO2 instance, its settings followed."""
    ini = read_mo2_ini(instance / 'ModOrganizer.ini')
    settings = ini.get('Settings', {})
    base = settings.get('base_directory') or str(instance)
    folders = {name: Path((settings.get(f'{key}_directory') or f'{MO2_BASE}/{name}').replace(MO2_BASE, base))
               for key, name in (('mod', 'mods'), ('profiles', 'profiles'), ('overwrite', 'overwrite'))}
    return ini.get('General', {}), folders


def profile_dir(general: dict, folders: dict, profile: str) -> Path:
    """`profile`'s folder ('' = the selected one) in a mo2_layout instance."""
    return folders['profiles'] / (profile or general.get('selected_profile', ''))


def source_files(source: ModSource) -> list:
    """The files and folders mod_folders reads to answer for `source` (not the mods' own files)."""
    if source.kind == 'mo2_profile':
        general, folders = mo2_layout(source.folder)
        return [source.folder / 'ModOrganizer.ini', profile_dir(general, folders, source.profile) / 'modlist.txt']
    return [source.folder] if source.kind == 'folder_of_mods' else []


def mo2_folders(instance: Path, profile: str = '') -> list:
    """An MO2 instance's Data-like folders for `profile` ('' = its selected profile), lowest priority first."""
    general, folders = mo2_layout(instance)
    enabled = enabled_mods(profile_dir(general, folders, profile) / 'modlist.txt')
    game = [Path(general['gamePath']) / 'Data'] if general.get('gamePath') else []
    return game + [folders['mods'] / name for name in reversed(enabled)] + [folders['overwrite']]


def enabled_mods(modlist: Path) -> list:
    """The mods a profile's modlist.txt enables (`+`), highest priority first, separators left out."""
    if not modlist.is_file():
        raise FileNotFoundError(f'no MO2 profile mod list at {modlist}')
    lines = modlist.read_text(encoding='utf-8', errors='replace').splitlines()
    return [line[1:] for line in lines if line.startswith('+') and not line.endswith('_separator')]


def read_mo2_ini(path: Path) -> dict:
    """{section: {key: value}} of MO2's QSettings ini, byte arrays and doubled backslashes undone."""
    out, section = {}, {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = out.setdefault(line[1:-1], {})
        elif '=' in line and not line.startswith(';'):
            key, _, value = line.partition('=')
            section[key.strip()] = qsettings_value(value.strip())
    return out


def qsettings_value(raw: str) -> str:
    """A QSettings ini value as text: `@ByteArray(...)` unwrapped, quotes dropped, `\\\\` as one backslash."""
    if raw.startswith('@ByteArray(') and raw.endswith(')'):
        raw = raw[len('@ByteArray('):-1]
    if len(raw) > 1 and raw[0] == raw[-1] == '"':
        raw = raw[1:-1]
    return raw.replace('\\\\', '\\')
