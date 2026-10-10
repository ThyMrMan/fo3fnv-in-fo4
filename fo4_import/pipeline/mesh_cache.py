"""convert_static.convert() through an on-disk cache, and many meshes converted at once in worker processes.

An entry is keyed by the source NIF's bytes, the call's pose and animated
flag, the winding-repair switch and the converter's code_tag(); it keeps the
size and modification time of every FNV texture the mesh uses, and a texture
that changed since makes it a miss. The cache is this machine's only (it is
never shared, so a file's time may stand for its contents).

See: docs/fork/fo4_pipeline.md#skeleton
"""

import concurrent.futures
import hashlib
import os
import pickle
from pathlib import Path

from core.collision_options import WINDING_FIX_ENV_VAR
from core.process_job import join_pool_job
from fo4_import.nif.convert_static import Converted, convert, texture_source
from fo4_import.pipeline.code_tag import ROOT, code_tag

CACHE = ROOT / 'output' / 'fo4_cache' / 'meshes'


def _key(source: bytes, pose: 'dict | None', animated: bool) -> str:
    """The cache key of one convert() call (the module notes)."""
    parts = (code_tag('fo4_import.nif.convert_static'), repr(sorted((pose or {}).items())), str(animated),
             os.environ.get(WINDING_FIX_ENV_VAR, ''))
    return hashlib.sha1(source + '\0'.join(parts).encode()).hexdigest()


def _stamps(converted: Converted, texture_root) -> dict:
    """{FNV texture path: (size, mtime) or None} of the textures `converted` was made from."""
    if texture_root is None:
        return {}
    used = set(converted.textures) | {normal for normal, _ in converted.spec_maps.values()}
    out = {}
    for texture in sorted(used):
        path = Path(texture_root) / texture_source(texture).replace('\\', '/')
        out[texture] = (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None
    return out


def cached_convert(path, texture_root=None, pose: dict = None, animated: bool = True) -> Converted:
    """convert(path, texture_root, pose, animated), from the cache when its entry is current (module notes)."""
    entry = CACHE / (key := _key(Path(path).read_bytes(), pose, animated))[:2] / f'{key}.pkl'
    if entry.exists():
        stamps, converted = pickle.loads(entry.read_bytes())
        if stamps == _stamps(converted, texture_root):
            return converted
    converted = convert(str(path), texture_root, pose, animated)
    entry.parent.mkdir(parents=True, exist_ok=True)
    partial = entry.with_suffix(f'.{os.getpid()}.tmp')
    partial.write_bytes(pickle.dumps((_stamps(converted, texture_root), converted)))
    partial.replace(entry)
    return converted


def _warm(job: tuple) -> None:
    """One worker's cached_convert(*job), the mesh discarded; a mesh that fails is left to fail where it is used."""
    try:
        cached_convert(*job)
    except Exception:
        return


def warm(paths: list, texture_root, workers: int = 0) -> None:
    """Fill the cache for convert(path, texture_root) of every path in `paths`, in `workers` processes (all
    but one CPU by default)."""
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    jobs = [(str(p), str(texture_root)) for p in paths]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, initializer=join_pool_job) as pool:
        list(pool.map(_warm, jobs, chunksize=1))
