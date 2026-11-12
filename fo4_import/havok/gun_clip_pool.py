"""Gun clips made cold in worker processes, a whole gun per job (GunClips.recorded), before the build replays them.

A worker converts into a data folder of its own and hands back the files; the caller keeps them (gun_clips.keep).
Workers hand out no FormID (a kept value holds placeholders for the gun's own keywords) and write no shared
folder, so the build that then replays every gun from the cache writes the same records whatever order the
workers finish in.

See: docs/fork/fo4_build_speed.md#keys
"""

import concurrent.futures
import mmap
import tempfile
from pathlib import Path

from core.build_resources import pool_workers
from core.process_job import join_pool_job
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.source_fault import SourceFault
from fo4_import.havok.gun_clips import GunClips, is_kept, keep
from fo4_import.pipeline import mesh_cache, work_cache
from fo4_import.pipeline.export_index import Layered

#: What a gun clip worker commits, for the worker count (build_resources.pool_workers).
WORKER_BYTES = 1 << 30
#: A worker process's GunClips and the temporary data folder it writes into (_start).
_worker = {}


def _start(meshes: tuple, caches: tuple) -> None:
    """A worker's start: join the pool job; the caller's (work, mesh) cache folders; a GunClips over the export
    meshes `meshes` ((layer folders, parts): Layered's) writing into a folder of its own."""
    join_pool_job()
    work_cache.CACHE, mesh_cache.CACHE = caches
    _worker['data'] = tempfile.TemporaryDirectory()
    with open(FALLOUT4_ESM, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as esm:
        _worker['clips'] = GunClips(esm, Layered(meshes[0], *meshes[1]), Path(_worker['data'].name))


def _convert(args: tuple) -> 'tuple | None':
    """GunClips.recorded(args) in this worker; None for a source fault, left for the build to meet and count."""
    try:
        return _worker['clips'].recorded(args)
    except SourceFault:
        return None


def warm(jobs: list, export_meshes, workers: int = 0) -> int:
    """Keep the clips of each of `jobs` [(GunClips.key, GunClips.recorded args)] not kept yet, made in `workers`
    processes (by default the resource profile's, no more than the guns to make); how many were made."""
    todo = [(key, args) for key, args in jobs if not is_kept(key)]
    if not todo:
        return 0
    workers = pool_workers(WORKER_BYTES, len(todo), workers)
    meshes = (export_meshes.folders, export_meshes.parts) if isinstance(export_meshes, Layered) \
        else ((export_meshes,), ())
    started = (meshes, (work_cache.CACHE, mesh_cache.CACHE))
    with concurrent.futures.ProcessPoolExecutor(workers, initializer=_start, initargs=started) as pool:
        for (key, _), found in zip(todo, pool.map(_convert, [args for _, args in todo], chunksize=1)):
            if found is not None:
                keep(key, found)
    return len(todo)
