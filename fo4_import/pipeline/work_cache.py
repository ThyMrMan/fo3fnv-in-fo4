"""Converted assets kept on disk across builds: the value of a piece of work, keyed by everything it reads.

A key is the work's site, the code_tag() of the module doing it, and the
bytes it reads (source files, images, settings); the value is pickled. A
rebuild with nothing changed reads each value back instead of converting
again. The cache is this machine's only, like the mesh cache. An entry's
time is when a build last used it; prune() drops what no build used lately.

See: docs/fork/fo4_pipeline.md#region-measured
"""

import functools
import hashlib
import os
import pickle
import time
from pathlib import Path

from asset_convert.texture.dds_codec import normal_dds
from asset_convert.texture.image_transcode import encode_dds
from fo4_import.nif.convert_static import glow_image, spec_image
from fo4_import.pipeline.code_tag import ROOT, code_tag

CACHE = ROOT / 'output' / 'fo4_cache' / 'work'
#: Days an entry of a cache prune() is given may go unused before it is deleted.
UNUSED_DAYS = 14


def key(site: str, module: str, inputs: tuple) -> str:
    """The key of `site`'s work in `module` on `inputs` (bytes, or values keyed by their repr)."""
    digest = hashlib.sha1(f'{site}\0{code_tag(module)}'.encode())
    for part in inputs:
        digest.update(b'\0' + (part if isinstance(part, bytes) else repr(part).encode()))
    return digest.hexdigest()


def _entry(site: str, module: str, inputs: tuple) -> Path:
    """The cache file of `site`'s work in `module` on `inputs`."""
    name = key(site, module, inputs)
    return CACHE / site / name[:2] / name


def lookup(site: str, module: str, inputs: tuple, default=None):
    """The value kept for `site`, `module` and `inputs` (its entry marked used); else `default`."""
    entry = _entry(site, module, inputs)
    if not entry.exists():
        return default
    os.utime(entry)
    return pickle.loads(entry.read_bytes())


def store(site: str, module: str, inputs: tuple, value):
    """Keep `value` for `site`, `module` and `inputs`; `value`."""
    entry = _entry(site, module, inputs)
    entry.parent.mkdir(parents=True, exist_ok=True)
    partial = entry.with_suffix(f'.{os.getpid()}.tmp')
    partial.write_bytes(pickle.dumps(value))
    partial.replace(entry)
    return value


def cached(site: str, module: str, inputs: tuple, make):
    """make()'s value, kept for `site`, `module` and `inputs` (module notes)."""
    missing = object()
    value = lookup(site, module, inputs, missing)
    return store(site, module, inputs, make()) if value is missing else value


def deferred(site: str, inputs: tuple, make) -> tuple:
    """(key, getter of cached(..., make)) of this module's `site` work on `inputs`."""
    return key(site, __name__, inputs), functools.partial(cached, site, __name__, inputs, make)


def _spec_dds(normal: bytes, smooth: float, red: 'int | None') -> bytes:
    """normal_dds() of spec_image(normal, smooth), its red channel set to `red` when given."""
    image = spec_image(normal, smooth)
    if red is not None:
        image[:, :, 0] = red
    return normal_dds(image)


def spec_map(normal: bytes, smooth: float, red: 'int | None' = None) -> tuple:
    """deferred() FO4 specular map of FNV normal map bytes (_spec_dds)."""
    return deferred('spec_map', (normal, smooth, red), functools.partial(_spec_dds, normal, smooth, red))


def _glow_dds(diffuse: bytes, glow: bytes, cut: 'int | None') -> bytes:
    """encode_dds() of glow_image(diffuse, glow, cut)."""
    return encode_dds(glow_image(diffuse, glow, cut))


def glow_map(diffuse: bytes, glow: bytes, cut: 'int | None') -> tuple:
    """deferred() FO4 glow map of FNV diffuse and glow map bytes (_glow_dds)."""
    return deferred('glow_map', (diffuse, glow, cut), functools.partial(_glow_dds, diffuse, glow, cut))


def _files(folder) -> list:
    """Every file under `folder` as os.DirEntry (its stat read with the listing)."""
    out = []
    for entry in os.scandir(folder):
        out += _files(entry.path) if entry.is_dir(follow_symlinks=False) else [entry]
    return out


def prune(folders: tuple, days: int = UNUSED_DAYS) -> int:
    """Delete every file under `folders` (cache roots) no build used or wrote for `days` days; the count."""
    before = time.time() - days * 86400
    old = [e for folder in folders if Path(folder).is_dir() for e in _files(folder) if e.stat().st_mtime < before]
    for entry in old:
        os.unlink(entry.path)
    return len(old)
