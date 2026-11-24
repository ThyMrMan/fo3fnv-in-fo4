"""Each mesh's pre-Elric Havok input finished by our physics writer (nif/hknp_write.py) through the work cache;
finish() keeps each finished NIF, so a NIF seen before is not read, finished and written again.

A NIF with Havok input is held in memory (write_mesh) rather than written,
since FO4 cannot load it; finish() writes only the finished NIF, and only
when its bytes changed, so a game running beside the build never loads a
half-made mesh. A NIF our writer does not cover is written without its
Havok, so without collision, and counted as failed.

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_hknp_writer.md#seam
"""

import concurrent.futures
import functools
import hashlib
import os
import zlib
from pathlib import Path

from core.build_resources import pool_workers
from core.process_job import join_pool_job
from fo4_import.base import touched
from fo4_import.base.source_fault import faulted
from fo4_import.nif import elric, hknp_write
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import mesh_cache, work_cache
from fo4_import.pipeline.ran_code import ran_alone
from fo4_import.pipeline.stage_timer import counted
from fo4_import.pipeline.work_cache import UNUSED_DAYS, prune, store
from asset_convert import paths as data_paths

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
INPUT_STORE = data_paths.FO4_CACHE / 'pre_elric'
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


def write_new(target: Path, data: bytes) -> None:
    """Write `data` to `target`, its folder made, unless the file already holds exactly that (then it is touched,
    marking it made by this build: stale_files); any NIF held for `target` is dropped."""
    _HELD.pop(os.path.normcase(str(target)), None)
    try:
        same = target.stat().st_size == len(data) and target.read_bytes() == data
    except OSError:
        same = False
    if same:
        touched.touch(target)
        return
    touched.forget(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def write_stored(target: Path, site: str, digest: str, stamps: 'dict | None' = None) -> bool:
    """write_new() of the bytes work_cache.store_bytes kept under `site` as `digest`, not read from the cache when
    `target` already holds them (then touched): known by `stamps` ({str path: [size, mtime_ns, digest]}, kept
    up to date) while its size and time match, else by its bytes. False when they are needed and gone.
    See: docs/fork/fo4_build_speed.md#clip-files
    """
    stamps = {} if stamps is None else stamps
    try:
        stat = target.stat()
        same = stamps.get(str(target)) == [stat.st_size, stat.st_mtime_ns, digest] or (
            hashlib.sha1(target.read_bytes()).hexdigest() == digest)
    except OSError:
        same = False
    if same:
        _HELD.pop(os.path.normcase(str(target)), None)
        touched.touch(target)
    else:
        data = work_cache.stored_bytes(site, digest)
        if data is None:
            return False
        write_new(target, data)
    stat = target.stat()
    stamps[str(target)] = [stat.st_size, stat.st_mtime_ns, digest]
    return True


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
    """finished() through work_cache (a NIF finished before, same bytes and the code that ran finishing it, comes
    from the cache) on each path's mesh_bytes(); each finished NIF written with write_new(), one with a source
    fault not cached, its [mark(), ok] kept in MARKS. A path `theirs` ({normcased path: [mark, ok]}, a master's)
    gives the same mark is not written (LEFT). The paths left without collision.
    See: docs/fork/fo4_build_speed.md#keys
    See: docs/fork/fo4_build_speed.md#fixed
    """
    failed, todo = [], {}
    for path in dict.fromkeys(Path(p) for p in paths):
        data = _HELD.pop(os.path.normcase(str(path)), None) or path.read_bytes()
        INPUTS[str(path)] = keep_input(data)
        inputs = (hashlib.sha1(data).digest(),)
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
    """finish()'s work for `todo` ({path: (inputs, pre-Elric bytes)}), none cached: each mesh finished
    (finished_each), stored (but a source-faulted one), written and marked; the paths left without collision."""
    failed = []
    each = finished_each({path: data for path, (_, data) in todo.items()})
    for path, ok, data, ran in counted(each, len(todo), 'meshes'):
        if not faulted(path):
            store(SITE, 'fo4_import.nif.hknp_write', todo[path][0], (ok, data), ran)
            MARKS[os.path.normcase(str(path))] = [mark(todo[path][0]), ok]
        write_new(path, data)
        failed += [] if ok else [path]
    return failed


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
    """(path, ok, finished bytes, code record) of `job` = (path, pre-Elric bytes) through finished().
    See: docs/fork/fo4_build_speed.md#collision-pool
    """
    path, data = job
    (ok, out), ran = ran_alone(functools.partial(finished, data))
    return path, ok, out, ran


def finished(data: bytes) -> tuple:
    """(covered, NIF `data` with our physics for its Havok input, or without that input where our writer does not
    cover it); `data` itself when it has none."""
    nif = nif_file.read(data)
    if elric.havok_start(nif) is None:
        return True, data
    made = hknp_write.finish(nif)
    return made is not None, nif_file.write(made if made is not None else elric.without_havok(nif_file.read(data)))


def prune_caches(days: int = UNUSED_DAYS) -> int:
    """Delete the mesh, work and pre-Elric entries unused `days` days; how many."""
    return prune((mesh_cache.CACHE, work_cache.CACHE, INPUT_STORE), days)
