"""The MO2 instance the build reads a profile's mod order through, and where MO2 sends the Creation Kit's new files.

MO2 sends the files the CK creates to the selected profile's custom overwrite for the Creation Kit executable
when it has one (`[custom_overwrites]` in the profile's settings.ini), else to its overwrite folder. No build
step runs the CK any more; recorded build inputs still ask where its files land.

See: docs/fork/fo4_own_rig.md#anim-info
"""

import configparser
import os
from pathlib import Path
from urllib.parse import quote

from fo4_import.pipeline.build_inputs import asked

#: The MO2 instance the build reads through: F3NV_MO2 (the app sets it from its MO2 mod source), else the developer's.
MO2 = Path(os.environ.get('F3NV_MO2') or r'C:\Modlists\fo3fnv-in-fo4')
#: Environment: the MO2 profile the faces stage reads through, in place of MO2's selected one.
PROFILE_ENV = 'F3NV_MO2_PROFILE'
#: The questions the build asks MO2 (build_inputs.asked): which mod holds a Data file, where the CK's files land.
HOLDING, OUTPUT = 'mo2 holding', 'mo2 output'
CK_EXECUTABLE = 'Creation Kit'


def profile_dir() -> Path:
    """The folder of the profile PROFILE_ENV names, else MO2's selected one."""
    if os.environ.get(PROFILE_ENV):
        return MO2 / 'profiles' / os.environ[PROFILE_ENV]
    main = configparser.ConfigParser(interpolation=None, strict=False)
    main.read(MO2 / 'ModOrganizer.ini', encoding='utf-8')
    profile = main.get('General', 'selected_profile', fallback='')
    return MO2 / 'profiles' / profile.removeprefix('@ByteArray(').removesuffix(')')


def modlist() -> list:
    """The selected profile's modlist.txt lines (`+name` enabled, `-name` disabled)."""
    path = profile_dir() / 'modlist.txt'
    return path.read_text(encoding='utf-8').splitlines() if path.is_file() else []


def _roots() -> list:
    """Where the CK's files can be: output_dir(), then the enabled mods."""
    return list(dict.fromkeys([output_dir()] + [MO2 / 'mods' / line[1:] for line in modlist() if line.startswith('+')]))


def _files() -> tuple:
    """MO2's ini, and the selected profile's mod list and settings."""
    profile = profile_dir()
    return MO2 / 'ModOrganizer.ini', profile / 'modlist.txt', profile / 'settings.ini'


def holding(rel: Path) -> 'Path | None':
    """Data path `rel` in the first of _roots() holding it, or None; logged."""
    found = next((root / rel for root in _roots() if (root / rel).is_file()), None)
    asked(HOLDING, Path(rel).as_posix(), str(found) if found else None, _files())
    return found


def ask(kind: str, arg: str) -> 'str | None':
    """Logged question `kind` (HOLDING or OUTPUT) about `arg`, answered now."""
    found = holding(Path(arg)) if kind == HOLDING else output_dir()
    return str(found) if found else None


def output_dir() -> Path:
    """Where MO2 puts the files the CK creates: the selected profile's custom overwrite mod for it, else overwrite;
    logged as a build input."""
    settings = configparser.ConfigParser(interpolation=None, strict=False)
    settings.optionxform = str
    settings.read(profile_dir() / 'settings.ini', encoding='utf-8')
    custom = settings.get('custom_overwrites', quote(CK_EXECUTABLE), fallback='')
    out = MO2 / 'mods' / custom if custom else MO2 / 'overwrite'
    asked(OUTPUT, '', str(out), _files())
    return out
