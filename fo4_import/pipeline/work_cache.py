"""Converted assets kept on disk across builds: the value of a piece of work, keyed by everything it reads.

A key is the work's site, the code_tag() of the module doing it, and the
bytes it reads (source files, images, settings); the value is pickled. A
rebuild with nothing changed reads each value back instead of converting
again. The cache is this machine's only, like the mesh cache.

See: docs/fork/fo4_pipeline.md#region-measured
"""

import hashlib
import os
import pickle

import numpy as np

from asset_convert.texture.dds_codec import normal_dds
from asset_convert.texture.image_transcode import encode_dds
from fo4_import.pipeline.code_tag import ROOT, code_tag

CACHE = ROOT / 'output' / 'fo4_cache' / 'work'


def _entry(site: str, module: str, inputs: tuple):
    """The cache file of `site`'s work in `module` on `inputs` (bytes, or values keyed by their repr)."""
    digest = hashlib.sha1(f'{site}\0{code_tag(module)}'.encode())
    for part in inputs:
        digest.update(b'\0' + (part if isinstance(part, bytes) else repr(part).encode()))
    return CACHE / site / (key := digest.hexdigest())[:2] / key


def lookup(site: str, module: str, inputs: tuple, default=None):
    """The value kept for `site`, `module` and `inputs`; else `default`."""
    entry = _entry(site, module, inputs)
    return pickle.loads(entry.read_bytes()) if entry.exists() else default


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


def _image_inputs(image: np.ndarray) -> tuple:
    """An image's shape, type and pixels as cache inputs."""
    return image.shape, str(image.dtype), np.ascontiguousarray(image).tobytes()


def normal_map(image: np.ndarray) -> bytes:
    """dds_codec.normal_dds(`image`), cached."""
    return cached('normal_dds', 'asset_convert.texture.dds_codec', _image_inputs(image), lambda: normal_dds(image))


def colour_map(image) -> bytes:
    """image_transcode.encode_dds(`image`), cached."""
    pixels = np.asarray(image)
    return cached('encode_dds', 'asset_convert.texture.image_transcode', _image_inputs(pixels) + (image.mode,),
                  lambda: encode_dds(image))
