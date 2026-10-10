"""elric.process() through an on-disk cache: Elric runs only on the NIFs it has not done.

An entry is Elric's output for one pre-Elric NIF, keyed by that NIF's bytes
and a tag over Elric's own files (its exe, DLLs and settings); a NIF Elric
crashes on alone is kept as an empty entry. Elric writes a few uninitialised
bytes into its physics, so two fresh runs differ; a cached entry makes every
rebuild after the first byte for byte the same. Elric runs as one instance:
four at once never finished (no CPU after nine minutes).

See: docs/fork/fo4_pipeline.md#skeleton
"""

import functools
import hashlib

from fo4_import.nif import elric
from fo4_import.pipeline.code_tag import ROOT

CACHE = ROOT / 'output' / 'fo4_cache' / 'elric'


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


def process(sources: dict) -> dict:
    """elric.process(sources) (Elric's output by name; a NIF it crashes on left out), cached (module notes)."""
    done, todo = {}, {}
    for name, data in sources.items():
        entry = _entry(data)
        if entry.exists():
            done[name] = entry.read_bytes()
        else:
            todo[name] = data
    done.update(elric.process(todo) if todo else {})
    for name in todo:
        entry = _entry(todo[name])
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_bytes(done.get(name, b''))
    return {name: out for name, out in done.items() if out}
