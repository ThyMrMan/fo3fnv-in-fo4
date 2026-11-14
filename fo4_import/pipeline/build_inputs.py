"""What a build's output is a function of, recorded as it runs and kept as `<plugin>.inputs.json`: the files it
opened and folders it listed, the programs it ran, the repo functions that ran (code_identity), the questions it
asked its masters' builds (MASTERS) and its command. Every process of the build records (worker processes through
ENV); build_plan checks the record.

See: docs/fork/fo4_plugin_layout.md#which-builds
"""

import atexit
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
from pathlib import Path

from fo4_import.base.build_files import moved_in
from fo4_import.pipeline import ran_code
from fo4_import.pipeline.code_identity import hashes
from fo4_import.pipeline.code_tag import ROOT

#: The folder each process of a recorded build writes its record into (set for worker processes).
ENV = 'F3NV_BUILD_INPUTS'
SUFFIX, FORMAT = '.inputs.json', 1
#: The folder each process of a plugin's build writes its record into (start(), record_dir()).
RECORD_SUFFIX = '.record'
#: Files up to this size are also kept by SHA-1, so a rewrite with the same bytes is not a change.
HASHED = 64 << 20
_EVENTS = frozenset({'open', 'os.listdir', 'os.scandir', 'subprocess.Popen'})
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
#: This process's record: files read and written, folders listed, programs run, questions asked (asked), files left out.
_SEEN = {'reads': set(), 'writes': set(), 'dirs': set(), 'programs': set(), 'asked': set(), 'covered': set()}
#: `on` while this process records; `main` in the process that writes the build's record (start()).
_STATE = {'on': False, 'main': False}


def norm(path) -> 'str | None':
    """`path` absolute and case-folded; None for a descriptor or nothing."""
    if path is None or isinstance(path, int):
        return None
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def _writes(mode, flags) -> bool:
    """Whether an open with `mode` (None for os.open) and `flags` can write."""
    return any(c in mode for c in 'wax+') if isinstance(mode, str) else bool((flags or 0) & _WRITE_FLAGS)


def _program(executable, args) -> 'str | None':
    """The program a Popen runs: its executable, else the first of `args` (a list, or on Windows one command line,
    its first token quoted or not)."""
    if executable is not None:
        return os.fsdecode(executable)
    if isinstance(args, (list, tuple)):
        return os.fsdecode(args[0]) if args else None
    line = os.fsdecode(args).strip() if isinstance(args, (str, bytes)) else ''
    if line.startswith('"'):
        return line[1:].split('"', 1)[0]
    return line.split(' ', 1)[0] or None


def _audit(event: str, args: tuple) -> None:
    """The audit hook: note opens, listings and programs while recording."""
    if event not in _EVENTS or not _STATE['on']:
        return
    if event == 'open':
        path = norm(args[0])
        if path:
            _SEEN['writes' if _writes(args[1], args[2]) else 'reads'].add(path)
    elif event == 'subprocess.Popen':
        program = _program(args[0], args[1])
        if program:
            _SEEN['programs'].add(program)
    else:
        path = norm(args[0] if args[0] is not None else '.')
        if path:
            _SEEN['dirs'].add(path)


def inputs_path(plugin: Path) -> Path:
    """`plugin`'s inputs record (SUFFIX), in the build records beside it (build_files)."""
    return moved_in(plugin.with_name(plugin.name + SUFFIX))


def record_dir(plugin: Path) -> Path:
    """The folder `plugin`'s build processes record into (RECORD_SUFFIX)."""
    return moved_in(plugin.with_name(plugin.name + RECORD_SUFFIX))


def start(folder: Path) -> None:
    """Record this process and every worker process it starts into `folder` (emptied first)."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    os.environ[ENV] = str(folder)
    _STATE['main'] = True
    resume()


def resume() -> None:
    """Record this process when its build records (ENV set); a worker's record is written to ENV's folder at exit."""
    if not os.environ.get(ENV) or _STATE['on']:
        return
    if not _STATE['main']:
        atexit.register(_dump)
    sys.addaudithook(_audit)
    ran_code.start()
    _STATE['on'] = True


def asked(kind: str, arg: str, answer: 'str | None', files: tuple = ()) -> None:
    """Log question `kind` about `arg` and its `answer` (build_plan asks it again); `files` and folders, read to
    answer it, are left out of the record: the answer stands for them.
    See: docs/fork/fo4_mod_builds.md#mo2-answers
    """
    if _STATE['on']:
        _SEEN['asked'].add(json.dumps([kind, arg, answer]))
    leave_out(files)


def leave_out(paths) -> None:
    """Leave files and folders `paths` out of the record (an answer covers them)."""
    if _STATE['on']:
        _SEEN['covered'].update(norm(p) for p in paths)


def _natives() -> set:
    """The repo's native extensions loaded in this process."""
    return {f for m in list(sys.modules.values()) if (f := getattr(m, '__file__', None) or '').endswith('.pyd')
            and norm(f).startswith(norm(ROOT) + os.sep)}


def _dump() -> None:
    """Write this process's record into ENV's folder as `<pid>.json`, whole or not at all (a reader globs *.json)."""
    _STATE['on'] = False
    body = {**{k: sorted(v) for k, v in _SEEN.items()}, 'ran': sorted(ran_code.RAN), 'natives': sorted(_natives())}
    part = Path(os.environ[ENV]) / f'{os.getpid()}.json'
    part.with_suffix('.tmp').write_text(json.dumps(body), encoding='utf-8')
    os.replace(part.with_suffix('.tmp'), part)


def stamp(path: Path) -> 'list | None':
    """[size, mtime_ns, SHA-1 or None] of file `path` (SHA-1 up to HASHED bytes); None when it is not a file."""
    try:
        stat = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    digest = hashlib.sha1(path.read_bytes()).hexdigest() if stat.st_size <= HASHED else None
    return [stat.st_size, stat.st_mtime_ns, digest]


def listing(path: Path) -> 'str | None':
    """A SHA-1 of folder `path`'s sorted entry names; None when it is not a folder."""
    try:
        return hashlib.sha1('\0'.join(sorted(os.listdir(path))).encode()).hexdigest()
    except OSError:
        return None


def program(name: str) -> 'list | None':
    """stamp() of the program `name` runs (searched on PATH when bare)."""
    found = name if os.path.isabs(name) else shutil.which(name)
    return stamp(Path(found)) if found else None


class MasterLog:
    """The questions a dependent build asks its built masters, with the answers it got: whether each FO4 FormID is
    held, each master ledger lookup, each master record read (signature, SHA-1), each master's own masters, each
    texture a master packed, each master script compiled against. Their files are left out of the file record
    (`covered`): these answers stand for them."""

    def __init__(self):
        """Nothing asked yet."""
        self.held, self.ledgers, self.records, self.headers = {}, {}, {}, {}
        self.staged, self.scripts, self.covered, self.paths = {}, {}, set(), {}

    def cover(self, kind: str, path) -> None:
        """Leave master file `path` (a built `plugin`, `ledger` or texture `manifest`) out of the file record."""
        self.covered.add(norm(path))
        self.paths.setdefault(kind, [])
        if str(path) not in self.paths[kind]:
            self.paths[kind].append(str(path))

    def record(self, fid: int, sig: bytes, body: 'bytes | None') -> None:
        """Log master record `fid` (`sig`) and its body's SHA-1 (None: absent)."""
        self.records[fid] = [sig.decode('latin-1'), hashlib.sha1(body).hexdigest() if body is not None else None]

    def ledger(self, site: str, key, answer: 'int | None') -> None:
        """Log the masters' ledgers' `answer` for `key` at `site` (None: none)."""
        self.ledgers[site, repr(key)] = answer

    def header(self, path, masters: list) -> None:
        """Built master `path` lists `masters`."""
        self.headers[str(path)] = list(masters)

    def texture(self, key: str, signatures: list) -> None:
        """Log the masters' packed `signatures` of texture `key`."""
        self.staged[key] = list(signatures)

    def script(self, path: Path) -> None:
        """The build compiled against master script `path`."""
        self.scripts[str(path)] = hashlib.sha1(path.read_bytes()).hexdigest()
        self.covered.add(norm(path))

    def body(self) -> dict:
        """The log as JSON-ready data."""
        return {'held': {f'{k:08X}': v for k, v in sorted(self.held.items())},
                'ledgers': [[*k, v] for k, v in sorted(self.ledgers.items(), key=repr)],
                'records': {f'{k:08X}': v for k, v in sorted(self.records.items())},
                'headers': self.headers, 'staged': self.staged, 'scripts': self.scripts, 'paths': self.paths}


#: The running build's master questions.
MASTERS = MasterLog()
_WORD = re.compile(rb'[A-Za-z_][A-Za-z0-9_]*')


def master_scripts(sources: list, folders: tuple) -> list:
    """The scripts in `folders` (a master's converted .psc) that scripts `sources` name, and those name in turn:
    what the compiler reads to compile `sources`."""
    index = {}
    for folder in folders:
        for path in Path(folder).glob('*.psc'):
            index.setdefault(path.stem.lower(), path)
    todo, seen = [Path(s) for s in sources if Path(s).is_file()], set()
    while todo:
        words = {w.decode().lower() for w in _WORD.findall(todo.pop().read_bytes())}
        new = {index[w] for w in words if w in index} - seen
        seen |= new
        todo += new
    return sorted(seen)


class Held(frozenset):
    """A built master's FormIDs (master_overrides.held_by) that logs each membership asked into MASTERS."""

    def __contains__(self, fid) -> bool:
        """Whether `fid` is held, logged."""
        answer = frozenset.__contains__(self, fid)
        MASTERS.held[fid] = answer
        return answer


def _merged(folder: Path) -> dict:
    """This process's record and every worker's in `folder`, merged."""
    out = {**{k: set(v) for k, v in _SEEN.items()}, 'ran': set(ran_code.RAN), 'natives': _natives()}
    for part in folder.glob('*.json'):
        for k, v in json.loads(part.read_text(encoding='utf-8')).items():
            out[k] |= set(v)
    return out


def _parents(paths: set) -> set:
    """Every folder above each of `paths` (a listing of one changes when the build writes below it)."""
    out = set()
    for path in paths:
        parent = os.path.dirname(path)
        while parent not in out and parent != os.path.dirname(parent):
            out.add(parent)
            parent = os.path.dirname(parent)
    return out


def _outside(path: str, skip: tuple) -> bool:
    """Whether `path` is an input: not under a `skip` root, not Python code or a cache."""
    return not path.startswith(skip) and not path.endswith(('.py', '.pyc', '.pyd'))


def _skipped(data_dir: Path, folder: Path) -> tuple:
    """Case-folded roots no input lives under (outputs, caches, Python)."""
    roots = [data_dir, folder, ROOT / 'output' / 'fo4_cache', sys.prefix, sys.base_prefix]
    return tuple(norm(r) + os.sep for r in roots)


def _environment() -> dict:
    """Python's version and the third-party distributions loaded, with their versions (copies vendored inside
    another package left out: their package's version stands for them)."""
    top = {m.split('.')[0] for m, mod in list(sys.modules.items()) if getattr(mod, '__file__', None)
           and 'site-packages' in mod.__file__}
    dists = importlib.metadata.packages_distributions()
    found = {importlib.metadata.distribution(d) for name in top for d in dists.get(name, ())}
    kept = [d for d in found if '_vendor' not in str(getattr(d, '_path', ''))]
    return {'python': sys.version, 'packages': dict(sorted((d.metadata['Name'], d.version) for d in kept))}


def write(plugin: Path, data_dir: Path, argv: list) -> Path:
    """Write `<plugin>.inputs.json` from this process's and its workers' records (module notes); its path."""
    folder = Path(os.environ[ENV])
    _STATE['on'] = False
    seen, skip = _merged(folder), _skipped(data_dir, folder)
    written = seen['writes'] | seen['covered'] | MASTERS.covered
    reads = sorted(p for p in seen['reads'] - written if _outside(p, skip))
    dirs = sorted(p for p in seen['dirs'] - _parents(seen['writes']) - seen['covered'] if not p.startswith(skip))
    body = {'format': FORMAT, 'argv': argv, 'environment': _environment(),
            'files': {p: s for p in reads if (s := stamp(Path(p)))},
            'dirs': {p: d for p in dirs if (d := listing(Path(p)))},
            'programs': {p: s for p in sorted(seen['programs']) if (s := program(p))},
            'natives': {p: stamp(Path(p)) for p in sorted(seen['natives'])},
            'code': hashes(seen['ran']), 'masters': MASTERS.body(),
            'asked': [json.loads(q) for q in sorted(seen['asked'])]}
    out = inputs_path(plugin)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=0, sort_keys=True), encoding='utf-8')
    return out
