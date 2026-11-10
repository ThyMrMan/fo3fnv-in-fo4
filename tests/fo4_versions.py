"""The honesty check of a versioned work-cache site (work_cache.versioned): its reference results, recomputed,
against the digests recorded under its `<SITE>_VERSION`.

    from tests.fo4_versions import check
    check(CLIP_SITE, GUN_CLIPS_VERSION, {'Varmint rifle': (inputs, make), '9mm pistol': (inputs, make)})

Each reference is the site's key inputs and the maker of its value for them. The record,
`tests/fo4_versions/<site>.json`, keeps the version and each reference's inputs and result digests. A result
that changed while the version and its inputs did not fails: bump the version. A new version, or a reference
whose inputs changed, fails until recorded again by running the test with F3NV_RECORD_VERSIONS=1, which still
refuses to record a changed result under an unchanged version and inputs.

See: docs/fork/fo4_build_speed.md#keys
"""

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

#: Where each site's reference digests are recorded.
RECORDS = Path(__file__).parent / 'fo4_versions'
#: Set to record the references computed now.
RECORD_ENV = 'F3NV_RECORD_VERSIONS'


def canonical(value):
    """`value` as nested tuples that print the same in every process: arrays and bytes by digest, dataclasses by
    fields, sets sorted, dicts and sequences in order, anything else by repr (exact for floats)."""
    if isinstance(value, np.ndarray):
        value = (value.dtype.str, value.shape, np.ascontiguousarray(value).tobytes())
    if isinstance(value, (bytes, bytearray, memoryview)):
        return 'sha1', hashlib.sha1(value).hexdigest()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return 'dict', tuple((canonical(k), canonical(v)) for k, v in value.items())
    if isinstance(value, (set, frozenset)):
        return 'set', tuple(sorted(repr(canonical(v)) for v in value))
    if isinstance(value, (list, tuple)):
        return type(value).__name__, tuple(canonical(v) for v in value)
    return type(value).__name__, repr(value)


def digest(value) -> str:
    """A SHA-1 of canonical(`value`)."""
    return hashlib.sha1(repr(canonical(value)).encode()).hexdigest()


def _stale(recorded: 'dict | None', version, found: dict) -> list:
    """Names in `found` the record cannot judge (new version or inputs)."""
    if recorded is None or recorded['version'] != version:
        return sorted(found)
    return sorted(n for n in found if recorded['references'].get(n, {}).get('inputs') != found[n]['inputs'])


def check(site: str, version, references: dict) -> None:
    """Recompute `references` ({name: (key inputs, maker of the value)} of `site`) against its record: fail on a
    result changed under the same version and inputs, or on one the record cannot judge (module notes)."""
    path = RECORDS / f'{site}.json'
    found = {name: {'inputs': digest(inputs), 'result': digest(make())}
             for name, (inputs, make) in sorted(references.items())}
    recorded = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    stale = _stale(recorded, version, found)
    changed = [n for n in found if n not in stale and recorded['references'][n]['result'] != found[n]['result']]
    assert not changed, f'{site}: {changed} changed while version {version!r} and inputs stayed: bump the version'
    if not stale:
        return
    assert os.environ.get(RECORD_ENV), f'{site}: {stale} not recorded under version {version!r}; run with {RECORD_ENV}=1'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'version': version, 'references': found}, indent=1, sort_keys=True) + '\n',
                    encoding='utf-8')
    pytest.skip(f'{site}: {stale} recorded under version {version!r}')
