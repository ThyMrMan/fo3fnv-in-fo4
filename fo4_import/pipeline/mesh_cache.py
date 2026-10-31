"""convert_static.convert() through an on-disk cache, and many meshes converted at once in worker processes.

An entry is keyed by the source NIF's bytes, the call's pose and animated
flag, the ADDN mapping (nif.addons), the winding-repair switch and the
converter's code_tag(); it keeps the size and modification time of every FNV
texture the mesh uses, and a texture that changed since makes it a miss. The
cache is this machine's only (it is never shared, so a file's time may stand
for its contents). An entry's time is when a build last used it (prune()).
cached_files() keeps the bytes a mesh is written as in the work cache under
the same key, checked the same way.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import concurrent.futures
import hashlib
import os
import pickle
from pathlib import Path
from typing import NamedTuple

import numpy as np

from core.collision_options import WINDING_FIX_ENV_VAR
from core.process_job import join_pool_job
from fo4_import.nif import bgem, bgsm
from fo4_import.nif import file as nif_file
from fo4_import.nif.addons import addon_map
from fo4_import.nif.convert_static import Converted, convert, texture_source
from fo4_import.pipeline.code_tag import ROOT, code_tag
from fo4_import.pipeline.work_cache import lookup, store
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
    return MeshFiles(nif_file.write(converted.nif), tuple(materials), mesh_bounds(converted.nif), converted.textures,
                     converted.spec_maps, converted.glow_maps, converted.animatable)


def _key(source: bytes, pose: 'dict | None', animated: bool, addons: dict) -> str:
    """The cache key of one convert() call (the module notes)."""
    parts = (code_tag('fo4_import.nif.convert_static'), repr(sorted((pose or {}).items())), str(animated),
             os.environ.get(WINDING_FIX_ENV_VAR, ''), repr(sorted(addons.items())))
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
    """(cache file, `addons` else `texture_root`'s ADDN mapping) of a convert() call."""
    addons = (addon_map(str(texture_root)) if texture_root else {}) if addons is None else addons
    key = _key(Path(path).read_bytes(), pose, animated, addons)
    return CACHE / key[:2] / f'{key}.pkl', addons


def cached_files(path, texture_root=None, pose: dict = None, animated: bool = True) -> MeshFiles:
    """mesh_files() of cached_convert(path, texture_root, pose, animated), kept in the work cache under the mesh
    key with its texture stamps; a current one marks its mesh entry used, so prune() keeps the Converted too."""
    entry, addons = _entry(path, texture_root, pose, animated, None)
    kept = lookup('mesh_files', __name__, (entry.stem,))
    if kept is not None and kept[0] == _stamps(kept[1], texture_root):
        if entry.exists():
            os.utime(entry)
        return kept[1]
    files = mesh_files(cached_convert(path, texture_root, pose, animated, addons))
    return store('mesh_files', __name__, (entry.stem,), (_stamps(files, texture_root), files))[1]


def cached_convert(path, texture_root=None, pose: dict = None, animated: bool = True, addons: dict = None) -> Converted:
    """convert(path, texture_root, pose, animated) with `texture_root`'s ADDN mapping (addon_map() unless given),
    from the cache when its entry is current (module notes)."""
    entry, addons = _entry(path, texture_root, pose, animated, addons)
    if entry.exists():
        stamps, converted = pickle.loads(entry.read_bytes())
        if stamps == _stamps(converted, texture_root):
            os.utime(entry)
            return converted
    converted = convert(str(path), texture_root, pose, animated, addons)
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
    but one CPU by default); the ADDN mapping is read once, here."""
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    addons = addon_map(str(texture_root)) if texture_root else {}
    jobs = [(str(p), str(texture_root), None, True, addons) for p in paths]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, initializer=join_pool_job) as pool:
        list(pool.map(_warm, jobs, chunksize=1))
