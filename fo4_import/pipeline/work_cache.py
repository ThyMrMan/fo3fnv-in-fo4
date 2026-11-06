"""Converted assets kept on disk across builds: the value of a piece of work, keyed by everything it reads.

A key is the work's site and the bytes it reads (source files, images, settings); the value is pickled. Beside
it, `<entry>.ran` keeps the identity of every repo function that ran making it (ran_code, code_identity): an
entry whose functions all keep their identity is current, so an edit to code the work never ran keeps it. A
value stored without that record keeps every function of its module's import tree (code_tag.tagged_files). The
cache is this machine's only; an entry's time is when a build last used it, and prune() drops what no build used.

See: docs/fork/fo4_plugin_layout.md#code-identity
"""

import functools
import hashlib
import json
import os
import pickle
import time
from pathlib import Path

from asset_convert.texture.dds_codec import normal_dds
from asset_convert.texture.image_transcode import encode_dds
from fo4_import.nif.convert_static import glow_image, spec_image
from fo4_import.pipeline.code_identity import changed, hashes, relative, module_keys
from fo4_import.pipeline.code_tag import ROOT, tagged_files
from fo4_import.pipeline.ran_code import ran_while

CACHE = ROOT / 'output' / 'fo4_cache' / 'work'
#: Days an entry of a cache prune() is given may go unused before it is deleted.
UNUSED_DAYS = 14
RAN_SUFFIX = '.ran'


def key(site: str, inputs: tuple) -> str:
    """The key of `site`'s work on `inputs` (bytes, or values keyed by their repr)."""
    digest = hashlib.sha1(site.encode())
    for part in inputs:
        digest.update(b'\0' + (part if isinstance(part, bytes) else repr(part).encode()))
    return digest.hexdigest()


def _entry(site: str, inputs: tuple) -> Path:
    """The cache file of `site`'s work on `inputs`."""
    name = key(site, inputs)
    return CACHE / site / name[:2] / name


def ran_path(entry: Path) -> Path:
    """The record of the code that made cache file `entry`."""
    return entry.with_name(entry.name + RAN_SUFFIX)


def current_ran(entry: Path) -> 'str | None':
    """A SHA-1 of the code record of `entry` when every function in it keeps its identity; else None."""
    try:
        text = ran_path(entry).read_text(encoding='utf-8')
    except OSError:
        return None
    return hashlib.sha1(text.encode()).hexdigest() if changed(json.loads(text)) is None else None


def module_ran(module: str) -> dict:
    """{key: identity} of every function in `module`'s import tree (store's fallback)."""
    rels = {relative(str(p)) for p in tagged_files(module).values()}
    return hashes(k for rel in rels if rel for k in module_keys(rel))


def write_ran(entry: Path, ran: dict) -> None:
    """Keep `ran` as `entry`'s code record."""
    partial = ran_path(entry).with_suffix(f'.{os.getpid()}.tmp')
    partial.write_text(json.dumps(ran, sort_keys=True), encoding='utf-8')
    partial.replace(ran_path(entry))


def lookup(site: str, module: str, inputs: tuple, default=None):
    """The value kept for `site` and `inputs` while its code is current (its entry marked used); else `default`.
    `module` is store()'s."""
    entry = _entry(site, inputs)
    if not entry.exists() or current_ran(entry) is None:
        return default
    os.utime(entry)
    os.utime(ran_path(entry))
    return pickle.loads(entry.read_bytes())


def store(site: str, module: str, inputs: tuple, value, ran: 'dict | None' = None):
    """Keep `value` for `site` and `inputs`, made by the functions `ran` ({key: identity}; None: every function
    of `module`'s import tree); `value`. When another process holds the entry open (two mesh workers making the
    same map), its copy stands."""
    entry = _entry(site, inputs)
    entry.parent.mkdir(parents=True, exist_ok=True)
    partial = entry.with_suffix(f'.{os.getpid()}.tmp')
    partial.write_bytes(pickle.dumps(value))
    try:
        partial.replace(entry)
    except PermissionError:
        if not entry.exists():
            raise
        partial.unlink(missing_ok=True)
        return value
    write_ran(entry, ran if ran is not None else module_ran(module))
    return value


def cached(site: str, module: str, inputs: tuple, make):
    """make()'s value, kept for `site` and `inputs` with the code that ran making it (module notes)."""
    missing = object()
    value = lookup(site, module, inputs, missing)
    if value is not missing:
        return value
    value, ran = ran_while(make)
    return store(site, module, inputs, value, ran)


def signature(site: str, module: str, inputs: tuple, make) -> tuple:
    """(signature, getter of cached(site, module, inputs, make)): the signature names the inputs and the code that
    made the kept value (made now when none is current), for stage_texture."""
    getter = functools.partial(cached, site, module, inputs, make)
    entry = _entry(site, inputs)
    if current_ran(entry) is None:
        getter()
    return f'{key(site, inputs)}:{current_ran(entry)}', getter


def deferred(site: str, inputs: tuple, make) -> tuple:
    """signature() of this module's `site` work on `inputs`."""
    return signature(site, __name__, inputs, make)


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
