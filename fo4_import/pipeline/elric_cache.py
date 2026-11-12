"""elric.process() through an on-disk cache: Elric runs only on the NIFs it has not done; finish() also keeps
each finished NIF, so a NIF seen before is not read, grafted and written again.

An entry is Elric's output for one pre-Elric NIF, keyed by that NIF's bytes
and a tag over Elric's own files (its exe, DLLs and settings); a NIF Elric
crashes on alone is kept as an empty entry. Elric writes a few uninitialised
bytes into its physics, so two fresh runs differ; a cached entry makes every
rebuild after the first byte for byte the same. Elric runs as one instance:
four at once never finished (no CPU after nine minutes). A NIF with Havok
input is held in memory (hold()) rather than written, since FO4 cannot load
it; finish() writes only the finished NIF, and only when its bytes changed,
so a game running beside the build never loads a half-made mesh.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import functools
import hashlib
import os
import tempfile
from pathlib import Path

from fo4_import.base.source_fault import faulted
from fo4_import.nif import elric
from fo4_import.pipeline import mesh_cache, work_cache
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.ran_code import ran_while
from fo4_import.pipeline.work_cache import UNUSED_DAYS, prune, store

CACHE = ROOT / 'output' / 'fo4_cache' / 'elric'
#: The work-cache site of a finished NIF.
SITE = 'elric_finish'
#: {normcased NIF path: pre-Elric bytes} held this run until finish() writes them finished.
_HELD = {}
#: {normcased NIF path: [mark(), collision ok]} of each NIF finish() wrote this run.
MARKS = {}
#: NIF paths finish() left unwritten this run: a master ships the same finished NIF.
LEFT = []


@functools.cache
def elric_tag() -> bytes:
    """A SHA-1 over Elric's exe, DLLs and settings."""
    digest = hashlib.sha1()
    for path in sorted(p for p in elric.ELRIC.rglob('*') if p.suffix.lower() in ('.exe', '.dll', '.esf')):
        digest.update(path.name.encode() + b'\0' + path.read_bytes())
    return digest.digest()


def _entry(data: bytes):
    """The cache file of one pre-Elric NIF."""
    key = hashlib.sha1(elric_tag() + data).hexdigest()
    return CACHE / key[:2] / key


def write_new(target: Path, data: bytes) -> None:
    """Write `data` to `target`, its folder made, unless the file already holds exactly that (then it is touched,
    marking it made by this build: stale_files); any NIF held for `target` is dropped."""
    _HELD.pop(os.path.normcase(str(target)), None)
    if target.is_file() and target.stat().st_size == len(data) and target.read_bytes() == data:
        os.utime(target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def write_mesh(path: Path, data: bytes) -> None:
    """Hold NIF `data` for `path` until finish() when it has Havok input, else write_new() it."""
    if elric.has_havok(data):
        _HELD[os.path.normcase(str(path))] = data
    else:
        write_new(Path(path), data)


def mesh_bytes(path: Path) -> bytes:
    """The NIF for `path` as the build made it: held (write_mesh) or on disk."""
    held = _HELD.get(os.path.normcase(str(path)))
    return Path(path).read_bytes() if held is None else held


def mark(inputs: tuple) -> 'str | None':
    """`inputs`' elric_finish key and code record digest, while current."""
    made_by = work_cache.current(SITE, inputs)
    return None if made_by is None else f'{work_cache.key(SITE, inputs)}:{made_by}'


def finish(paths: list, theirs: 'dict | None' = None) -> list:
    """elric.finish() through work_cache (a NIF finished before, same bytes, Elric and the code that ran finishing
    it, comes from the cache) on each path's mesh_bytes(), run on staged copies; each finished NIF written with
    write_new(), one with a source fault not cached, its [mark(), ok] kept in MARKS. A path `theirs` ({normcased
    path: [mark, ok]}, a master's) gives the same mark is not written (LEFT). The paths left without collision.
    See: docs/fork/fo4_build_speed.md#keys
    See: docs/fork/fo4_build_speed.md#fixed
    """
    failed, todo = [], {}
    for path in dict.fromkeys(Path(p) for p in paths):
        data = _HELD.pop(os.path.normcase(str(path)), None) or path.read_bytes()
        inputs = (elric_tag(), hashlib.sha1(data).digest())
        made = mark(inputs)
        shipped = (theirs or {}).get(os.path.normcase(str(path)))
        if made is None:
            todo[path] = inputs, data
        elif shipped and shipped[0] == made:
            path.unlink(missing_ok=True)
            LEFT.append(path)
            failed += [] if shipped[1] else [path]
        else:
            ok, done = work_cache.kept(SITE, inputs)
            write_new(path, done)
            MARKS[os.path.normcase(str(path))] = [made, ok]
            failed += [] if ok else [path]
    return failed + _run(todo)


def _run(todo: dict) -> list:
    """finish()'s work for `todo` ({path: (inputs, pre-Elric bytes)}), none cached: elric.finish on staged copies,
    each result stored (but a source fault's), written and marked; the paths left without collision."""
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        staged = {path: Path(tmp) / f'{i:05d}.nif' for i, path in enumerate(todo)}
        for path, (_, data) in todo.items():
            staged[path].write_bytes(data)
        finished = functools.partial(elric.finish, list(staged.values()), process, list(todo))
        failed_now, ran = ran_while(finished) if todo else ((), {})
        for path, (inputs, _) in todo.items():
            ok, data = staged[path] not in failed_now, staged[path].read_bytes()
            if not faulted(path):
                store(SITE, 'fo4_import.nif.elric', inputs, (ok, data), ran)
                MARKS[os.path.normcase(str(path))] = [mark(inputs), ok]
            write_new(path, data)
            failed += [] if ok else [path]
    return failed


def process(sources: dict) -> dict:
    """elric.process(sources) (Elric's output by name; a NIF it crashes on left out), cached (module notes)."""
    done, todo = {}, {}
    for name, data in sources.items():
        entry = _entry(data)
        if entry.exists():
            done[name] = entry.read_bytes()
            os.utime(entry)
        else:
            todo[name] = data
    done.update(elric.process(todo) if todo else {})
    for name in todo:
        entry = _entry(todo[name])
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_bytes(done.get(name, b''))
    return {name: out for name, out in done.items() if out}


def prune_caches(days: int = UNUSED_DAYS) -> int:
    """Delete mesh, work and Elric cache entries unused for `days` days; the count."""
    return prune((mesh_cache.CACHE, work_cache.CACHE, CACHE), days)
