"""Caprica, an open-source Papyrus compiler, ahead of Fallout 4's own: the scripts it compiles skip the slow one.

Caprica (external/caprica, MIT) compiles FO4 Papyrus in seconds where FO4's
PapyrusCompiler takes about 0.25 s a script. Two differences shape its use:

- Its parser rejects a few header constructs FO4's compiler accepts, so it
  reads a patched copy of the header folders (`safe_headers`, PATCHES). A
  script that needs what a patch changed fails in Caprica and falls back.
- It stops at the first script that fails (serial; its parallel mode
  crashes there). `compile_files` drops each failing script and runs again
  on the rest; what never compiles (and all of them when a header itself
  breaks Caprica) is left to FO4's compiler, whose messages stay the
  build's diagnostics.

See: docs/fork/fo4_pipeline.md#caprica
"""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.file_stamps import Stamps
from fo4_import.base.papyrus import FO4_HEADERS, LEVELUP_MENU_HEADERS

CAPRICA = Path(__file__).resolve().parents[2] / 'external' / 'caprica' / 'Caprica.exe'
FLAGS = FO4_HEADERS / 'Base' / 'Institute_Papyrus_Flags.flg'
#: Where the patched header copies live, one folder per source folder and content.
HEADER_CACHE = Path(__file__).resolve().parents[2] / 'output' / 'fo4_cache' / 'caprica_headers'
#: The header folders FO4's compiler imports that Caprica reads patched.
HEADER_FOLDERS = (FO4_HEADERS / 'F4SE', FO4_HEADERS / 'Base', LEVELUP_MENU_HEADERS)
#: (pattern, replacement) of what Caprica's parser rejects in the headers (the module docs' link lists each).
PATCHES = ((re.compile(r'\A\s+'), ''), (re.compile(r'(?m)^(\s*string\s+)parent(\s*)$'), r'\1parentNode\2'),
           (re.compile(r'\bVar (\w+) = None\b', re.I), r'Var \1'))
#: Caprica's line naming a script it could not compile, and a fatal error's file.
FAILED = re.compile(r"Compilation of '([^']+)\.psc' failed")
FATAL = re.compile(r'([^\\/\s]+)\.psc \(\d+, [\d:]+\): Fatal Error', re.I)
#: Seconds one Caprica run may take: a bound, not an estimate (the whole corpus compiles in about a minute).
TIMEOUT = 1800


def available() -> bool:
    """Whether the bundled Caprica is there."""
    return CAPRICA.is_file()


def _patched(text: str) -> str:
    """A header source with PATCHES applied."""
    for pattern, replacement in PATCHES:
        text = pattern.sub(replacement, text)
    return text


def safe_headers(folder: Path) -> Path:
    """A copy of header folder `folder` with PATCHES applied, made once per content (HEADER_CACHE; each file's hash
    kept by stamp, file_stamps); older copies of it are deleted."""
    files, stamps = sorted(folder.rglob('*.psc')), Stamps(HEADER_CACHE / f'stamps_{folder.name}.json')
    digest = hashlib.sha1(repr(PATCHES).encode())
    for path in files:
        digest.update(str(path.relative_to(folder)).lower().encode() + b'\0'
                      + stamps.value(path, lambda p: hashlib.sha1(p.read_bytes()).hexdigest()).encode())
    stamps.save()
    copy = HEADER_CACHE / f'{folder.name}_{digest.hexdigest()[:12]}'
    if not (copy / '.done').is_file():
        for old in HEADER_CACHE.glob(f'{folder.name}_*'):
            shutil.rmtree(old, ignore_errors=True)
        for path in files:
            target = copy / path.relative_to(folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_patched(path.read_text(encoding='utf-8', errors='surrogateescape')),
                              encoding='utf-8', errors='surrogateescape', newline='')
        (copy / '.done').write_text('', encoding='utf-8')
    return copy


def caprica_imports(imports: str) -> str:
    """Import list `imports`, each HEADER_FOLDERS entry as its safe_headers."""
    known = {str(f.resolve()).lower(): f for f in HEADER_FOLDERS}
    return ';'.join(str(safe_headers(known[str(Path(d).resolve()).lower()])) if str(Path(d).resolve()).lower()
                    in known else d for d in imports.split(';') if d)


def _run(folder: Path, out_dir: Path, imports: str) -> str:
    """One Caprica run over `folder` into `out_dir`, serial (its parallel mode crashes on a failing script, which
    may leave a .pex half written); its output."""
    cmd = [str(CAPRICA), '-g', 'fallout4', '-q', '--ignorecwd', '-f', str(FLAGS), '-o', str(out_dir),
           '-i', imports, str(folder)]
    done = subprocess.run(cmd, capture_output=True, text=True, cwd=str(out_dir), timeout=TIMEOUT, **POPEN_FLAGS)
    return done.stdout + done.stderr


def compile_files(files: list, out_dir: Path, imports: str) -> set:
    """Compile `files` (.psc paths) into `out_dir` with Caprica, against the FO4 compiler's `imports`; the lower-case
    names it wrote a .pex for. Each failing script is dropped and the rest run again; a failure naming no script
    of the batch (a header Caprica cannot read, a crash) ends it with what was written."""
    batch = out_dir / '_caprica'
    shutil.rmtree(batch, ignore_errors=True)
    batch.mkdir(parents=True)
    for path in files:
        shutil.copy2(path, batch / path.name)
    imports, written = caprica_imports(f'{batch};{imports}'), set()
    while any(batch.glob('*.psc')):
        output = _run(batch, out_dir, imports)
        names = {p.stem.lower() for p in batch.glob('*.psc')}
        made = {n for n in names if (out_dir / f'{n}.pex').is_file()}
        failed = {m.lower() for m in FAILED.findall(output) + FATAL.findall(output)} & names
        written |= made
        for name in made | failed:
            (batch / f'{name}.psc').unlink(missing_ok=True)
        if not failed and made != names:
            break
    shutil.rmtree(batch, ignore_errors=True)
    return written
