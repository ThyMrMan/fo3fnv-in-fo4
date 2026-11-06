"""The Creation Kit as a build step: run it through MO2 (so it loads the profile's plugins and mods), wait for it,
and find where its new files land.

MO2 sends the files the CK creates to the selected profile's custom overwrite for the Creation Kit executable
when it has one (`[custom_overwrites]` in the profile's settings.ini), else to its overwrite folder. Files the CK
edits that already exist in a mod are edited where they are.

See: docs/fork/fo4_own_rig.md#anim-info
"""

import configparser
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.pipeline.build_inputs import asked

MO2 = Path(r'C:\Modlists\fo3fnv-in-fo4')
#: The questions the build asks MO2 (build_inputs.asked): which mod holds a Data file, where the CK's files land.
HOLDING, OUTPUT = 'mo2 holding', 'mo2 output'
CK_EXECUTABLE, CK_PROCESS = 'Creation Kit', 'CreationKit.exe'
#: Where CKPE writes a zipped crash log and dump when the CK crashes.
CK_CRASHES = FALLOUT4_DIR / 'Logs' / 'CKPE' / 'Crashes'
#: Seconds between checks that the CK is still running.
CK_POLL = 5


def run(arguments: str, timeout: float, what: str) -> None:
    """Run the CK with `arguments` through MO2 and wait for it to exit; raise if its write target is a disabled mod
    (MO2 would wait on an error dialog), it crashed, or it took longer than `timeout` seconds (`what` names the
    job in the error)."""
    target = output_dir()
    if target.parent.name == 'mods' and f'+{target.name}' not in modlist():
        raise SystemExit(f'MO2 sends the Creation Kit\'s new files to mod "{target.name}", which the selected '
                         f'profile has disabled: enable it, or clear the Creation Kit\'s write target, then rebuild')
    started = time.time()
    subprocess.run([str(MO2 / 'ModOrganizer.exe'), 'run', '-e', CK_EXECUTABLE, '-a', arguments], check=True,
                   **POPEN_FLAGS)
    while time.time() < started + timeout:
        time.sleep(CK_POLL)
        listing = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {CK_PROCESS}'], capture_output=True, text=True,
                                 **POPEN_FLAGS).stdout
        if CK_PROCESS not in listing:
            crashes = [p for p in CK_CRASHES.glob('*.zip') if p.stat().st_mtime > started]
            if crashes:
                raise SystemExit(f'the Creation Kit crashed {what}: see {max(crashes)}')
            return
    raise SystemExit(f'the Creation Kit did not finish {what} in {timeout:.0f}s')


def profile_dir() -> Path:
    """MO2's selected profile's folder."""
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


def written_since(rel: Path, since: float) -> list:
    """[(file, its path under the Data folder, whether it is in output_dir)] of the files under `rel` the CK wrote
    from `since` on: new ones in output_dir(), edited ones in the enabled mods holding them."""
    out, found = output_dir(), []
    for root in _roots():
        folder = root / rel
        for path in sorted(folder.rglob('*')) if folder.is_dir() else ():
            if path.is_file() and path.stat().st_mtime >= since:
                found.append((path, path.relative_to(root), root == out))
    return found


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
