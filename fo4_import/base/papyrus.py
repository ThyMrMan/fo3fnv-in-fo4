"""Fallout 4's own Papyrus compiler: one `-all` batch over a folder, F4SE then Base headers.

The compiler scans its working directory and fails on any path over 260
characters, so it runs from the output folder. The headers are unpacked once
from the Fallout 4 install: the Creation Kit's script zips and F4SE's loose
sources (neither may be redistributed).

See: docs/fork/fo4_spikes.md#spike-3-gate
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR

FO4_COMPILER = FALLOUT4_DIR / 'Papyrus Compiler' / 'PapyrusCompiler.exe'
#: Where the install keeps script sources: the Creation Kit's zips in subfolders, F4SE's .psc loose.
INSTALL_SOURCES = FALLOUT4_DIR / 'Data' / 'Scripts' / 'Source'
FO4_HEADERS = Path(__file__).resolve().parents[2] / 'output' / 'fo4_cache' / 'fo4_headers'
#: The file Base must hold for the headers to count as unpacked.
FLAGS_FILE = 'Institute_Papyrus_Flags.flg'


def unpack_headers(sources: Path = INSTALL_SOURCES, headers: Path = FO4_HEADERS) -> bool:
    """Fill `headers` once from `sources`: every Creation Kit zip (Base, the DLC, Creation Club) into Base, F4SE's
    .psc into F4SE. Whether the headers are there."""
    done = headers / '.done'
    if done.is_file():
        return True
    for archive in sorted(sources.glob('*/*.zip')):
        with zipfile.ZipFile(archive) as z:
            z.extractall(headers / 'Base')
    (headers / 'F4SE').mkdir(parents=True, exist_ok=True)
    for psc in sources.glob('*.psc'):
        shutil.copy2(psc, headers / 'F4SE' / psc.name)
    if (headers / 'Base' / FLAGS_FILE).is_file() and (headers / 'F4SE' / 'F4SE.psc').is_file():
        done.write_text('', encoding='utf-8')
        return True
    return False


def header_dirs() -> str:
    """FO4 scripts' import order: F4SE, then Base, unpacked first if needed.
    See: docs/fork/fo4_level_up_plan.md#dropped
    """
    unpack_headers()
    return f'{FO4_HEADERS / "F4SE"};{FO4_HEADERS / "Base"}'


def compile_folder(folder: Path, out_dir: Path, imports: str) -> str:
    """Compile every .psc in `folder` into `out_dir`; the compiler's combined output ('' without it installed)."""
    if not FO4_COMPILER.is_file():
        return ''
    r = subprocess.run([str(FO4_COMPILER), str(folder), '-all', '-q', f'-i={imports}', f'-o={out_dir}',
                        f'-f={FLAGS_FILE}'],
                       capture_output=True, text=True, cwd=str(out_dir), **POPEN_FLAGS)
    return r.stdout + r.stderr
