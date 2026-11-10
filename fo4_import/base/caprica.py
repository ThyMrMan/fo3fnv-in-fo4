"""Caprica, an open-source Papyrus compiler, ahead of Fallout 4's own: the scripts it compiles skip the slow one.

Caprica (external/caprica, MIT) compiles FO4 Papyrus in seconds where FO4's
PapyrusCompiler takes about 0.25 s a script. Two differences shape its use:

- Its parser rejects a few header constructs FO4's compiler accepts, so it
  reads a patched copy of the header folders (`safe_headers`, PATCHES). A
  script that needs what a patch changed fails in Caprica and falls back.
- It stops at the first script that fails (serial; its parallel mode
  crashes there) and has no switch to go on. `compile_files` deals the
  scripts into folders run at once, drops each failing script and runs its
  folder again. A script whose every message is a known source error
  (`source_error`) keeps those as its errors; any other failure (a crash,
  a timeout, a header or construct Caprica cannot read) is left to FO4's
  compiler.

See: docs/fork/fo4_pipeline.md#caprica
"""

import hashlib
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.memory_budget import memory_workers
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
#: One Caprica error line: the script, its source line, the message.
ERROR = re.compile(r'^([^\\/\s]+)\.psc \((\d+), [\d:]+\): (?:Fatal )?Error: (.+)$', re.M)
#: Caprica messages that are FO4's compiler's errors too and stay in Caprica's words (FO4's has several per kind).
SAME_ERRORS = re.compile(r"Unresolved identifier '\w+'!|No implicit conversion from '[^']+' to '[^']+' exists!"
                         r"|You cannot assign to the const property '\w+'\."
                         r"|The <, <=, >, >=, -, \*, /, and % operators are only valid on integers and floats!")
#: Caprica messages with one FO4 compiler wording: a call to no function, a cast between unrelated types.
NO_FUNCTION, BAD_CAST = (re.compile(r"Unresolved function name '(\w+)'!"),
                         re.compile(r"Cannot convert from '([^']+)' to '([^']+)'!"))
#: Caprica's message for an event the parent scripts do not have, and the event a source line declares.
NEW_EVENT, EVENT_NAME = 'Non-native scripts cannot define new events.', re.compile(r'^\s*Event\s+(\w+)', re.I)
#: Seconds one Caprica run may take: a bound, not an estimate (the whole corpus compiles in about a minute).
TIMEOUT = 1800
#: One Caprica's memory (it reads every import file: 270-313 MB with 31,961), and what its runs leave free.
CAPRICA_BYTES, SPARE_BYTES = 512 << 20, 2 << 30


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


def _run(folder: Path, out_dir: Path, imports: str) -> tuple:
    """One Caprica run over `folder` into `out_dir`, serial (its parallel mode crashes on a failing script):
    (exit code, output), (None, '') when it ran past TIMEOUT."""
    cmd = [str(CAPRICA), '-g', 'fallout4', '-q', '--ignorecwd', '-f', str(FLAGS), '-o', str(out_dir),
           '-i', imports, str(folder)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=str(out_dir), timeout=TIMEOUT, **POPEN_FLAGS)
    except subprocess.TimeoutExpired:
        return None, ''
    return done.returncode, done.stdout + done.stderr


def source_error(message: str, line: str) -> 'str | None':
    """Caprica error `message` (at source text `line`) as the script's own error, in FO4's compiler's words
    where it has one wording for it; None when the message is not known to be an error of the source.
    See: docs/fork/fo4_pipeline.md#caprica-errors
    """
    call, cast = NO_FUNCTION.fullmatch(message), BAD_CAST.fullmatch(message)
    if call:
        return f'{call[1]} is not a function or does not exist'
    if cast:
        return f'cannot cast a {cast[1].lower()} to a {cast[2].lower()}, types are incompatible'
    event = EVENT_NAME.match(line) if message == NEW_EVENT else None
    if event:
        return f'new event {event[1].lower()} cannot be defined because the script is not flagged as native'
    return message if SAME_ERRORS.fullmatch(message) else None


def _errors(output: str, folder: Path) -> dict:
    """{lower-case script of `folder`: its source_error messages, None for each that is not one} in a run's output."""
    found = {}
    for name, line, message in ERROR.findall(output):
        path = folder / f'{name}.psc'
        if path.is_file():
            lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
            error = source_error(message.strip(), lines[int(line) - 1] if int(line) <= len(lines) else '')
            if error not in found.setdefault(name.lower(), []):
                found[name.lower()].append(error)
    return found


def _drain(folder: Path, out_dir: Path, imports: str) -> tuple:
    """Run Caprica over `folder` until it is empty: each run's compiled scripts and the one it stopped at leave
    it. (names compiled, {script: [its errors]} for those whose every message is a source_error, runs made).
    A run naming no script of the folder (a crash, a timeout, a header Caprica cannot read) ends it; unless that
    run ended cleanly, what it wrote is deleted (a .pex may be half written)."""
    written, errors, runs = set(), {}, 0
    while any(folder.glob('*.psc')):
        (code, output), runs = _run(folder, out_dir, imports), runs + 1
        names = {p.stem.lower() for p in folder.glob('*.psc')}
        made = {n for n in names if (out_dir / f'{n}.pex').is_file()}
        found = _errors(output, folder)
        if not found and made != names:
            for name in made if code != 0 else ():
                (out_dir / f'{name}.pex').unlink()
            written |= made if code == 0 else set()
            break
        written |= made
        errors.update({name: messages for name, messages in found.items() if None not in messages})
        for name in made | set(found):
            (folder / f'{name}.psc').unlink(missing_ok=True)
    return written, errors, runs


def compile_files(files: list, out_dir: Path, imports: str, workers: int = 1) -> tuple:
    """Compile `files` (.psc paths) into `out_dir` with Caprica against import list `imports` (the scripts' own
    folder first): (lower-case names it wrote a .pex for, {name: [errors]} of those failing on their own source,
    Caprica runs made). The files are dealt into up to `workers` folders, as many as free memory holds a
    Caprica for, all drained at once (_drain). A script in neither result is left to FO4's compiler.
    See: docs/fork/fo4_pipeline.md#caprica-errors
    """
    root = out_dir / '_caprica'
    shutil.rmtree(root, ignore_errors=True)
    folders = [root / str(n) for n in range(memory_workers(min(workers, len(files)), CAPRICA_BYTES, SPARE_BYTES))]
    for folder in folders:
        folder.mkdir(parents=True)
    for i, path in enumerate(files):
        shutil.copy2(path, folders[i % len(folders)] / path.name)
    rest = caprica_imports(imports)
    with ThreadPoolExecutor(max_workers=len(folders)) as pool:
        results = list(pool.map(lambda folder: _drain(folder, out_dir, f'{folder};{rest}'), folders))
    shutil.rmtree(root, ignore_errors=True)
    return (set().union(*(r[0] for r in results)), {name: messages for r in results for name, messages in r[1].items()},
            sum(r[2] for r in results))
