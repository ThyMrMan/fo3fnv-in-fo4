"""Fallout 4's own Papyrus compiler: one `-all` batch over a folder, F4SE then Base headers.

The compiler scans its working directory and fails on any path over 260
characters, so it runs from the output folder.

See: docs/fork/fo4_spikes.md#spike-3-gate
"""

import subprocess
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR

FO4_COMPILER = FALLOUT4_DIR / 'Papyrus Compiler' / 'PapyrusCompiler.exe'
FO4_HEADERS = Path(__file__).resolve().parents[2] / 'references' / 'fo4_scripts'
#: LevelUpMenuEx's script sources (the character rules call PRKF:PRKF).
LEVELUP_MENU_HEADERS = FO4_HEADERS.parent / 'LevelUpMenuEx' / 'Data' / 'Scripts' / 'Source' / 'User'
def header_dirs() -> str:
    """FO4 scripts' import order: F4SE, Base, LevelUpMenuEx."""
    return f'{FO4_HEADERS / "F4SE"};{FO4_HEADERS / "Base"};{LEVELUP_MENU_HEADERS}'


def compile_folder(folder: Path, out_dir: Path, imports: str) -> str:
    """Compile every .psc in `folder` into `out_dir`; the compiler's combined output."""
    r = subprocess.run([str(FO4_COMPILER), str(folder), '-all', '-q', f'-i={imports}', f'-o={out_dir}',
                        '-f=Institute_Papyrus_Flags.flg'],
                       capture_output=True, text=True, cwd=str(out_dir), **POPEN_FLAGS)
    return r.stdout + r.stderr
