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
so a game running beside the build never loads a half-made mesh. A NIF our
own physics writer covers (nif/hknp_write.py: convex, round and mesh bodies) never reaches
Elric or its cache.

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_hknp_writer.md#seam
"""

import concurrent.futures
import functools
import hashlib
import os
import tempfile
import zlib
from pathlib import Path

from core.build_resources import pool_workers
from core.process_job import join_pool_job
from fo4_import.base.source_fault import FAULTS, SourceFault, count, faulted
from fo4_import.nif import elric, hknp_write
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import mesh_cache, work_cache
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.ran_code import ran_alone
from fo4_import.pipeline.work_cache import UNUSED_DAYS, prune, store

CACHE = ROOT / 'output' / 'fo4_cache' / 'elric'
#: The work-cache site of a finished NIF.
SITE = 'elric_finish'
#: Meshes to finish before finished_each spreads them over worker processes, and the memory each worker is given.
POOLED, WORKER_BYTES = 16, 512 << 20
#: {normcased NIF path: pre-Elric bytes} held this run until finish() writes them finished.
_HELD = {}
#: {normcased NIF path: [mark(), collision ok]} of each NIF finish() wrote this run.
MARKS = {}
#: {normcased NIF path: its finish() inputs} of each NIF finish() left unwritten this run (a master ships it alike).
LEFT = {}
#: Each pre-Elric NIF finish() took, zlib-compressed and named by its SHA-1 (keep_input), for a meshes replay.
INPUT_STORE = ROOT / 'output' / 'fo4_cache' / 'pre_elric'
#: {NIF path: SHA-1 of its pre-Elric bytes} of each NIF finish() took this run, in order.
INPUTS = {}


def keep_input(data: bytes) -> str:
    """Keep pre-Elric NIF `data` in INPUT_STORE (once; a kept one marked used); its SHA-1.
    See: docs/fork/fo4_plugin_layout.md#meshes-replay
    """
    key = hashlib.sha1(data).hexdigest()
    path = INPUT_STORE / key[:2] / key
    try:
        work_cache.mark_used(path, path.stat().st_mtime)
    except OSError:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(f'.{os.getpid()}.tmp')
        partial.write_bytes(zlib.compress(data, 1))
        partial.replace(path)
    return key


def kept_input(key: str) -> 'bytes | None':
    """The pre-Elric NIF keep_input() kept as `key`; None when it is gone."""
    try:
        return zlib.decompress((INPUT_STORE / key[:2] / key).read_bytes())
    except OSError:
        return None


@functools.cache
def elric_tag() -> bytes:
    """A SHA-1 over Elric's exe, DLLs and settings."""
    digest = hashlib.sha1()
    for path in sorted(p for p in elric.ELRIC.rglob('*') if p.suffix.lower() in ('.exe', '.dll', '.esf')):
        digest.update(path.name.encode() + b'\0' + path.read_bytes())
    return digest.digest()


def entry(data: bytes, cache: 'Path | None' = None) -> Path:
    """The cache file of one pre-Elric NIF, under `cache` (default: CACHE now)."""
    key = hashlib.sha1(elric_tag() + data).hexdigest()
    return (cache or CACHE) / key[:2] / key


def write_new(target: Path, data: bytes) -> None:
    """Write `data` to `target`, its folder made, unless the file already holds exactly that (then it is touched,
    marking it made by this build: stale_files); any NIF held for `target` is dropped."""
    _HELD.pop(os.path.normcase(str(target)), None)
    try:
        same = target.stat().st_size == len(data) and target.read_bytes() == data
    except OSError:
        same = False
    if same:
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
    """The NIF for `path` as the build made it: held (write_mesh), finished but left to a master (LEFT; the
    cached finished NIF), or on disk."""
    key = os.path.normcase(str(path))
    if key in _HELD:
        return _HELD[key]
    return work_cache.kept(SITE, LEFT[key])[1] if key in LEFT else Path(path).read_bytes()


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
        INPUTS[str(path)] = keep_input(data)
        inputs = (elric_tag(), hashlib.sha1(data).digest())
        made = mark(inputs)
        shipped = (theirs or {}).get(os.path.normcase(str(path)))
        if made is None:
            todo[path] = inputs, data
        elif shipped and shipped[0] == made:
            path.unlink(missing_ok=True)
            LEFT[os.path.normcase(str(path))] = inputs
            failed += [] if shipped[1] else [path]
        else:
            ok, done = work_cache.kept(SITE, inputs)
            write_new(path, done)
            MARKS[os.path.normcase(str(path))] = [made, ok]
            failed += [] if ok else [path]
    return failed + _run(todo)


def _run(todo: dict) -> list:
    """finish()'s work for `todo` ({path: (inputs, pre-Elric bytes)}), none cached: each mesh finished alone
    (finished_each), then the ones needing a new Elric run in one batch; each result stored (but a source fault's),
    written and marked; the paths left without collision."""
    failed, waiting = [], {}
    for path, ok, data, ran, faults in finished_each({path: data for path, (_, data) in todo.items()}):
        if ok is None:
            waiting[path] = todo[path][1]
        else:
            failed += _keep(path, todo[path][0], ok, data, ran, faults)
    for path, ok, data, ran, faults in _batch(waiting):
        failed += _keep(path, todo[path][0], ok, data, ran, faults)
    return failed


def _keep(path: Path, inputs: tuple, ok: bool, data: bytes, ran: dict, faults: list) -> list:
    """Count `faults`, store and mark mesh `path`'s finished `data` (not after a fault), write it; [path] if not ok."""
    for fault in faults:
        count(SourceFault(*fault))
    if not faulted(path):
        store(SITE, 'fo4_import.nif.elric', inputs, (ok, data), ran)
        MARKS[os.path.normcase(str(path))] = [mark(inputs), ok]
    write_new(path, data)
    return [] if ok else [path]


def finished_each(meshes: dict):
    """finish_one() of each of `meshes` ({path: pre-Elric bytes}), as each is done: in worker processes (the resource
    profile's, pool_workers) when there are POOLED or more."""
    jobs = list(meshes.items())
    if len(jobs) < POOLED:
        yield from map(finish_one, jobs)
        return
    workers = pool_workers(WORKER_BYTES, len(jobs))
    with concurrent.futures.ProcessPoolExecutor(workers, initializer=join_pool_job) as pool:
        yield from pool.map(finish_one, jobs, chunksize=4)


def finish_one(job: tuple) -> tuple:
    """(path, ok, finished bytes, code record, faults met) of `job` = (path, pre-Elric bytes) through elric.finish
    with no new Elric run (cached_process); ok None when it needs one (NeedsElric).
    See: docs/fork/fo4_build_speed.md#collision-pool
    """
    path, data = job
    before = set(FAULTS)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / 'mesh.nif'
        staged.write_bytes(data)
        try:
            failed, ran = ran_alone(functools.partial(elric.finish, [staged], cached_process, [path]))
        except NeedsElric:
            return path, None, b'', {}, []
        return path, not failed, staged.read_bytes(), ran, [f for f in FAULTS if f not in before]


def _batch(meshes: dict) -> list:
    """[(path, ok, finished bytes, code record, faults met)] of `meshes` ({path: pre-Elric bytes}) through one
    elric.finish on staged copies, Elric run once for them all."""
    if not meshes:
        return []
    before = set(FAULTS)
    with tempfile.TemporaryDirectory() as tmp:
        staged = {path: Path(tmp) / f'{i:05d}.nif' for i, path in enumerate(meshes)}
        for path, data in meshes.items():
            staged[path].write_bytes(data)
        failed, ran = ran_alone(functools.partial(elric.finish, list(staged.values()), process, list(meshes)))
        faults = [f for f in FAULTS if f not in before]
        return [(path, staged[path] not in failed, staged[path].read_bytes(), ran, faults) for path in meshes]


class NeedsElric(Exception):
    """A mesh neither our writer nor Elric's cache finishes: it waits for _batch's Elric run."""


def _needs_elric(sources: dict) -> dict:
    """Stand in for elric.process in a worker: NeedsElric."""
    raise NeedsElric(sorted(sources))


def cached_process(sources: dict) -> dict:
    """process() running no Elric: NeedsElric for a mesh only a new run finishes."""
    return process(sources, _needs_elric)


def ours(data: bytes) -> 'bytes | None':
    """NIF `data` finished by our physics writer; None where it does not cover it.
    See: docs/fork/fo4_hknp_writer.md#seam
    """
    made = hknp_write.finish(nif_file.read(data))
    return None if made is None else nif_file.write(made)


def process(sources: dict, run=None) -> dict:
    """Each pre-Elric NIF finished by name: by ours() where it covers it, else `run` (default elric.process),
    cached (module notes); a NIF Elric crashes on is left out."""
    done, todo = {}, {}
    for name, data in sources.items():
        done[name] = ours(data)
        if done[name] is not None:
            continue
        cached = entry(data)
        if cached.exists():
            done[name] = cached.read_bytes()
            os.utime(cached)
        else:
            todo[name] = data
    done.update((run or elric.process)(todo) if todo else {})
    for name in todo:
        cached = entry(todo[name])
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(done[name] or b'')
    return {name: out for name, out in done.items() if out}


def prune_caches(days: int = UNUSED_DAYS) -> int:
    """Delete the mesh, work, Elric and pre-Elric entries unused `days` days; how many."""
    return prune((mesh_cache.CACHE, work_cache.CACHE, CACHE, INPUT_STORE), days)
