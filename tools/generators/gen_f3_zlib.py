"""Build the pinned zlib (native/src/f3_zlib: zlib 1.4's deflate) into native/dist, a plain shared library.

    python -m tools.generators.gen_f3_zlib

The library is committed, like native/build.py's modules: fo4_import.base.pinned_zlib loads it through ctypes on
any Python version and raises when it is missing. MSVC is found through vswhere; elsewhere g++/clang++ build it.

See: docs/fork/fo4_pipeline.md#pinned-zlib
"""

import subprocess
import sys
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.pinned_zlib import LIBRARY
from native.build import find_unix_compiler, find_vcvars

ROOT = Path(__file__).resolve().parents[2]
#: The wrapper and zlib's deflate sources it is built from.
SOURCES = ROOT / 'native' / 'src' / 'f3_zlib'
#: Intermediate objects (gitignored).
OBJECTS = ROOT / 'native' / 'build' / 'f3_zlib'
#: The folder vcvars64.bat runs vswhere.exe from by bare name.
INSTALLER = r'%ProgramFiles(x86)%\Microsoft Visual Studio\Installer'


def sources() -> list:
    """The C files compiled into the library: the wrapper, then zlib's."""
    return [SOURCES / 'f3_zlib.c', *sorted((SOURCES / 'zlib').glob('*.c'))]


def build_msvc(vcvars: str) -> int:
    """Compile with MSVC through a batch file (vcvars, then cl); the exit code."""
    OBJECTS.mkdir(parents=True, exist_ok=True)
    files = ' '.join(f'"{path}"' for path in sources())
    bat = OBJECTS / '_build.bat'
    bat.write_text(f'@echo off\nset "PATH=%PATH%;{INSTALLER}"\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                   f'cl /nologo /LD /O2 /W3 /Fo"{OBJECTS}\\\\" /Fe:"{LIBRARY}" {files} '
                   f'/link /IMPLIB:"{OBJECTS / "f3_zlib.lib"}"\n')
    return subprocess.run([str(bat)], cwd=ROOT, shell=True, **POPEN_FLAGS).returncode


def build_unix(compiler: str) -> int:
    """Compile with g++/clang++ as C, position-independent; the exit code."""
    command = [compiler, '-x', 'c', '-shared', '-fPIC', '-O2', '-o', str(LIBRARY), *map(str, sources())]
    return subprocess.run(command, cwd=ROOT, **POPEN_FLAGS).returncode


def main() -> int:
    """Build the library for this platform; 1 when no compiler is found."""
    toolchain = find_vcvars() if sys.platform == 'win32' else find_unix_compiler()
    if not toolchain:
        print('no C compiler found (MSVC through vswhere, or g++/clang++ on PATH)', file=sys.stderr)
        return 1
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    code = build_msvc(toolchain) if sys.platform == 'win32' else build_unix(toolchain)
    print(f'{LIBRARY}: {LIBRARY.stat().st_size} bytes' if code == 0 else 'BUILD FAILED')
    return code


if __name__ == '__main__':
    sys.exit(main())
