"""convert_static.convert() through an on-disk cache, and many meshes converted at once in worker processes.

An entry is keyed by the source NIF's bytes, the call's pose and animated
flag, the ADDN mapping (nif.addons) and the winding-repair switch; it keeps
the size and modification time of every FNV texture the mesh uses, and
beside it (`.ran`) the identity of every repo function that ran converting
it. A changed texture or function makes it a miss. The cache is this
machine's only (a file's time may stand for its contents). An entry's time
is when a build last used it (prune()). cached_files() keeps the bytes a mesh
is written as in the work cache, keyed by the same key and that conversion's
code record.

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_plugin_layout.md#code-identity
"""

import concurrent.futures
import functools
import hashlib
import os
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import numpy as np

from core.collision_options import WINDING_FIX_ENV_VAR
from core.build_resources import pool_workers
from core.process_job import join_pool_job, limit_own_memory, total_memory
from fo4_import.base.file_stamps import Stamps
from fo4_import.base.source_fault import SourceFault
from fo4_import.nif import bgem, bgsm, blocks
from fo4_import.nif import file as nif_file
from fo4_import.nif.addons import addon_map
from fo4_import.nif.convert_static import Converted, convert, texture_source
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.ran_code import ran_while
from fo4_import.pipeline.work_cache import current_ran, lookup, ran_path, store, write_ran
from fo4_import.pipeline.export_index import export_file

CACHE = ROOT / 'output' / 'fo4_cache' / 'meshes'
#: OBND's range: six signed 16-bit coordinates.
OBND_RANGE = (-32768, 32767)


class MeshFiles(NamedTuple):
    """A converted mesh as written: its NIF's bytes, ((material path, BGSM or BGEM bytes), ...), its OBND
    (mesh_bounds) and the Converted fields texture staging and load doors read."""
    nif: bytes
    materials: tuple
    bounds: 'tuple | None'
    textures: set
    spec_maps: dict
    glow_maps: dict
    animatable: bool
    #: How many vertices had a UV past the half-float range (nif.blocks.half_uv).
    clamped: int = 0


#: {mesh path: MeshFiles.clamped} of the meshes cached_files gave this process, for the build's count.
CLAMPED = {}
#: Mesh paths a warm() worker ran out of its memory cap on this run; cached_convert faults them, never retries.
TOO_LARGE = set()
#: A mesh worker's memory cap: this share of the machine's RAM, at least MIN_WORKER_MEMORY.
WORKER_MEMORY_SHARE, MIN_WORKER_MEMORY = 8, 2 * 2 ** 30
#: What a mesh worker commits, for the worker count (build_resources.pool_workers): 0.17 GB measured, large meshes more.
WORKER_BYTES = 512 << 20
#: Threads warm() checks kept entries in: the check waits on opening small files, not on the CPU.
CHECK_THREADS = 16


def mesh_bounds(nif) -> 'tuple | None':
    """OBND: the integer box around every shape's vertices, held in OBND's signed 16-bit range; None for a mesh with
    none."""
    pts = np.array([v['position'] for kind, b in nif.blocks if kind == 'BSTriShape' for v in b['vertices']])
    if not len(pts):
        return None
    lo, hi = np.floor(pts.min(axis=0)), np.ceil(pts.max(axis=0))
    return tuple(int(v) for v in np.clip(np.concatenate([lo, hi]), *OBND_RANGE))


def mesh_files(converted: Converted) -> MeshFiles:
    """The files converted mesh `converted` is written as."""
    materials = [(p, bgsm.write(m)) for p, m in converted.materials.items()]
    materials += [(p, bgem.write(m)) for p, m in converted.effects.items()]
    before = blocks.CLAMPED['uv']
    nif = nif_file.write(converted.nif)
    return MeshFiles(nif, tuple(materials), mesh_bounds(converted.nif), converted.textures, converted.spec_maps,
                     converted.glow_maps, converted.animatable, blocks.CLAMPED['uv'] - before)


def _key(source: bytes, pose: 'dict | None', animated: bool, addons: dict) -> str:
    """The cache key of one convert() call (the module notes)."""
    parts = (repr(sorted((pose or {}).items())), str(animated), os.environ.get(WINDING_FIX_ENV_VAR, ''),
             repr(sorted(addons.items())))
    return hashlib.sha1(source + '\0'.join(parts).encode()).hexdigest()


def _stamps(converted: 'Converted | MeshFiles', texture_root) -> dict:
    """{FNV texture path: (size, mtime) or None} of the textures `converted` was made from."""
    if texture_root is None:
        return {}
    used = set(converted.textures) | {normal for normal, _ in converted.spec_maps.values()}
    out = {}
    for texture in sorted(used):
        path = export_file(texture_root, texture_source(texture).replace('\\', '/'))
        out[texture] = (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None
    return out


def _entry(path, texture_root, pose: 'dict | None', animated: bool, addons: 'dict | None') -> tuple:
    """(cache file, `addons` else `texture_root`'s ADDN mapping) of a convert() call; SourceFault for a model no
    export layer holds."""
    addons = (addon_map(str(texture_root)) if texture_root else {}) if addons is None else addons
    if not Path(path).is_file():
        raise SourceFault(path, 'missing model (in no export layer)')
    key = _key(Path(path).read_bytes(), pose, animated, addons)
    return CACHE / key[:2] / f'{key}.pkl', addons


def cached_files(path, texture_root=None, pose: dict = None, animated: bool = True) -> MeshFiles:
    """mesh_files() of cached_convert(path, texture_root, pose, animated), kept in the work cache under the mesh
    key with its texture stamps; a current one marks its mesh entry used, so prune() keeps the Converted too."""
    entry, addons = _entry(path, texture_root, pose, animated, None)
    made_by = current_ran(entry)
    kept = lookup('mesh_files', __name__, (entry.stem, made_by)) if made_by else None
    if kept is not None and kept[0] == _stamps(kept[1], texture_root):
        if entry.exists():
            os.utime(entry)
        CLAMPED[str(path)] = kept[1].clamped
        return kept[1]
    files, ran = ran_while(lambda: mesh_files(cached_convert(path, texture_root, pose, animated, addons)))
    CLAMPED[str(path)] = files.clamped
    return store('mesh_files', __name__, (entry.stem, current_ran(entry)), (_stamps(files, texture_root), files),
                 ran)[1]


def cached_convert(path, texture_root=None, pose: dict = None, animated: bool = True, addons: dict = None) -> Converted:
    """convert(path, texture_root, pose, animated) with `texture_root`'s ADDN mapping (addon_map() unless given),
    from the cache when its entry and the code that made it are current (module notes)."""
    if _same(path) in TOO_LARGE:
        raise SourceFault(path, f'mesh too large to convert (over {worker_memory() / 2 ** 30:.1f} GB)')
    entry, addons = _entry(path, texture_root, pose, animated, addons)
    if entry.exists() and current_ran(entry):
        stamps, converted = pickle.loads(entry.read_bytes())
        if stamps == _stamps(converted, texture_root):
            os.utime(entry)
            os.utime(ran_path(entry))
            return converted
    converted, ran = ran_while(lambda: _convert(path, texture_root, pose, animated, addons))
    entry.parent.mkdir(parents=True, exist_ok=True)
    partial = entry.with_suffix(f'.{os.getpid()}.tmp')
    partial.write_bytes(pickle.dumps((_stamps(converted, texture_root), converted)))
    partial.replace(entry)
    write_ran(entry, ran)
    return converted


def _convert(path, texture_root, pose: 'dict | None', animated: bool, addons: dict) -> Converted:
    """convert(path, ...); a SourceFault it raises names `path`."""
    try:
        return convert(str(path), texture_root, pose, animated, addons)
    except SourceFault as fault:
        raise fault.at(path) from None


def worker_memory() -> int:
    """A mesh worker's memory cap in bytes (module constants)."""
    return max(MIN_WORKER_MEMORY, total_memory() // WORKER_MEMORY_SHARE)


def _join_capped() -> None:
    """A mesh worker's initializer: join the build's job, cap its memory."""
    join_pool_job()
    limit_own_memory(worker_memory())


def _warm(job: tuple) -> tuple:
    """One worker's cached_convert(*job), the mesh discarded: (ran out of memory, its texture stamps as JSON; None
    when it failed: a mesh that fails is left to fail where it is used)."""
    try:
        converted = cached_convert(*job)
    except MemoryError:
        return True, None
    except Exception:
        return False, None
    return False, {t: list(s) if s else None for t, s in _stamps(converted, job[1]).items()}


def _memo(stamps: Stamps, path: Path, addons: dict) -> dict:
    """warm()'s memo of `path` ({'key', 'textures'}, _kept) by its stamp."""
    make = lambda f: {'key': _key(f.read_bytes(), None, True, addons), 'textures': None}
    return stamps.value(path, make) if path.is_file() else {'key': '', 'textures': None}


def _kept(memo: dict, texture_root) -> bool:
    """Whether a warm() memo entry ({'key', 'textures'}) names a current cache entry, its textures unchanged since
    a worker last checked them; its code record marked used (cached_files marks the entry). False sends the mesh
    to a worker, which checks it fully."""
    entry = CACHE / memo['key'][:2] / f"{memo['key']}.pkl"
    if memo['textures'] is None or not entry.exists() or current_ran(entry) is None:
        return False
    now = _stamps(SimpleNamespace(textures=list(memo['textures']), spec_maps={}), texture_root)
    if {t: list(s) if s else None for t, s in now.items()} != memo['textures']:
        return False
    os.utime(ran_path(entry))
    return True


def warm(paths: list, texture_root, workers: int = 0) -> int:
    """Fill the cache for convert(path, texture_root) of every path in `paths` in worker processes (`workers`, else
    the resource profile's: build_resources.pool_workers), each capped at worker_memory(); the ADDN mapping read once;
    how many were converted. A mesh whose entry a
    file-stamp memo shows current (_kept) stays out of the pool.
    See: docs/fork/fo4_build_speed.md#worker-memory
    See: docs/fork/fo4_build_speed.md#fixed
    """
    addons = addon_map(str(texture_root)) if texture_root else {}
    setting = hashlib.sha1(f'{texture_root}|{_key(b"", None, True, addons)}'.encode()).hexdigest()
    stamps = Stamps(CACHE / 'warm' / f'{setting}.json')
    memos = {str(p): _memo(stamps, Path(p), addons) for p in paths}
    with concurrent.futures.ThreadPoolExecutor(max_workers=CHECK_THREADS) as threads:
        kept = list(threads.map(functools.partial(_kept, texture_root=texture_root), memos.values()))
    jobs = [(p, str(texture_root), None, True, addons) for p, done in zip(memos, kept) if not done]
    workers = pool_workers(WORKER_BYTES, len(jobs), workers)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, initializer=_join_capped) as pool:
        for job, (too_large, textures) in zip(jobs, pool.map(_warm, jobs, chunksize=1)):
            memos[job[0]]['textures'] = textures
            if too_large:
                TOO_LARGE.add(_same(job[0]))
    stamps.save()
    return len(jobs)


def _same(path) -> str:
    """`path` spelled one way, whatever its slashes and case."""
    return os.path.normcase(os.path.abspath(str(path)))
