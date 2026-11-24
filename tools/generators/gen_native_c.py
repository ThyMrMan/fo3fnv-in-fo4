"""Build the plain C programs and libraries in native/src into native/dist (TARGETS).

    python -m tools.generators.gen_native_c              # every target
    python -m tools.generators.gen_native_c xwma_enc     # just these

The built files are committed, like native/build.py's modules, so a machine without a compiler runs the pipeline.
MSVC is found through vswhere; elsewhere gcc/clang build them.

See: docs/fork/fo4_pipeline.md#pinned-zlib
"""

import subprocess
import sys
from pathlib import Path

from asset_convert.paths import XWMA_ENC
from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.pinned_zlib import LIBRARY
from native.build import find_unix_compiler, find_vcvars

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'native'
#: The folder vcvars64.bat runs vswhere.exe from by bare name.
INSTALLER = r'%ProgramFiles(x86)%\Microsoft Visual Studio\Installer'


def targets() -> dict:
    """{name: (output, C sources, shared library?, MSVC defines)}: the pinned zlib and the xWMA encoder."""
    zlib = NATIVE / 'src' / 'f3_zlib'
    xwma = NATIVE / 'src' / 'xwma'
    return {'f3_zlib': (LIBRARY, [zlib / 'f3_zlib.c', *sorted((zlib / 'zlib').glob('*.c'))], True, ()),
            'xwma_enc': (XWMA_ENC, [xwma / 'main.c', xwma / 'xwma_encoder.c'], False,
                         ('_USE_MATH_DEFINES', '_CRT_SECURE_NO_WARNINGS'))}


def build_msvc(name: str, target: tuple, vcvars: str) -> int:
    """Compile `target` with MSVC through a batch file (vcvars, then cl); the exit code."""
    output, sources, shared, defines = target
    objects = NATIVE / 'build' / name
    objects.mkdir(parents=True, exist_ok=True)
    files = ' '.join(f'"{path}"' for path in sources)
    flags = ' '.join(f'/D{define}' for define in defines) + (' /LD' if shared else '')
    link = f' /link /IMPLIB:"{objects / (name + ".lib")}"' if shared else ''
    bat = objects / '_build.bat'
    bat.write_text(f'@echo off\nset "PATH=%PATH%;{INSTALLER}"\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                   f'cl /nologo /O2 /fp:precise /W3 {flags} /Fo"{objects}\\\\" /Fe:"{output}" {files}{link}\n')
    return subprocess.run([str(bat)], cwd=ROOT, shell=True, **POPEN_FLAGS).returncode


def build_unix(target: tuple, compiler: str) -> int:
    """Compile `target` with gcc/clang as C (position-independent for a library); the exit code."""
    output, sources, shared, _ = target
    kind = ['-shared', '-fPIC'] if shared else []
    command = [compiler, '-x', 'c', *kind, '-O2', '-o', str(output), *map(str, sources), *([] if shared else ['-lm'])]
    return subprocess.run(command, cwd=ROOT, **POPEN_FLAGS).returncode


def main(names: list) -> int:
    """Build the named TARGETS (all when none) for this platform; 1 when no compiler is found or one fails."""
    toolchain = find_vcvars() if sys.platform == 'win32' else find_unix_compiler()
    if not toolchain:
        print('no C compiler found (MSVC through vswhere, or gcc/clang on PATH)', file=sys.stderr)
        return 1
    failed = 0
    for name, target in targets().items():
        if names and name not in names:
            continue
        target[0].parent.mkdir(parents=True, exist_ok=True)
        code = build_msvc(name, target, toolchain) if sys.platform == 'win32' else build_unix(target, toolchain)
        print(f'{target[0]}: {target[0].stat().st_size} bytes' if code == 0 else f'{name}: BUILD FAILED')
        failed |= code != 0
    return int(failed)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
