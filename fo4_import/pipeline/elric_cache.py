"""elric.process() through an on-disk cache: Elric runs only on the NIFs it has not done; finish() also keeps
each finished NIF, so a NIF seen before is not read, grafted and written again.

An entry is Elric's output for one pre-Elric NIF, keyed by that NIF's bytes
and a tag over Elric's own files (its exe, DLLs and settings); a NIF Elric
crashes on alone is kept as an empty entry. Elric writes a few uninitialised
bytes into its physics, so two fresh runs differ; a cached entry makes every
rebuild after the first byte for byte the same. Elric runs as one instance:
four at once never finished (no CPU after nine minutes). finish() keys a NIF
by the SHA-1 of its bytes, taken from written() when the build wrote it, so
the file is not read back.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import functools
import hashlib
import os
from pathlib import Path

from fo4_import.nif import elric
from fo4_import.pipeline import mesh_cache, work_cache
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.work_cache import UNUSED_DAYS, lookup, prune, store

CACHE = ROOT / 'output' / 'fo4_cache' / 'elric'
#: {normcased NIF path: (SHA-1, size, mtime_ns)} of the NIFs written() this run.
_WRITTEN = {}


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


def written(path: Path, data: bytes) -> None:
    """Note that `data` was just written to the NIF at `path` (finish() keys on it)."""
    stat = Path(path).stat()
    _WRITTEN[os.path.normcase(str(path))] = (hashlib.sha1(data).digest(), stat.st_size, stat.st_mtime_ns)


def _digest(path: Path) -> bytes:
    """The SHA-1 of the NIF at `path`: written()'s while the file is unchanged since, else read from it."""
    known, stat = _WRITTEN.get(os.path.normcase(str(path))), path.stat()
    if known and known[1:] == (stat.st_size, stat.st_mtime_ns):
        return known[0]
    return hashlib.sha1(path.read_bytes()).digest()


def finish(paths: list) -> list:
    """elric.finish(paths, process()) through work_cache: a NIF finished before (same bytes, Elric and code) is
    written back from the cache; the paths left without collision."""
    failed, todo = [], {}
    for path in dict.fromkeys(Path(p) for p in paths):
        inputs = (elric_tag(), _digest(path))
        done = lookup('elric_finish', 'fo4_import.nif.elric', inputs)
        if done is None:
            todo[path] = inputs
            continue
        ok, data = done
        path.write_bytes(data)
        failed += [] if ok else [path]
    newly = set(elric.finish(list(todo), process) if todo else ())
    for path, inputs in todo.items():
        store('elric_finish', 'fo4_import.nif.elric', inputs, (path not in newly, path.read_bytes()))
    return failed + sorted(newly)


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
