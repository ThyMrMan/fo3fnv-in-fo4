"""Cache keys that hold: a site's code record keeps what per-process memos ran for it, versioned sites, their
honesty check, and pruning entries no lookup takes.

See: docs/fork/fo4_build_speed.md#keys
"""

import functools
import hashlib
import json

import numpy as np
import pytest

from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import ran_code as RC
from fo4_import.pipeline import work_cache as WC
from tests import fo4_versions as V

HERE = 'tests/test_fo4_cache_keys.py::'
#: The per-process memo _memoized fills.
_MEMO = {}


def _expensive() -> int:
    """A repo function that only a memo's first fill runs."""
    return 7


def _memoized() -> int:
    """_expensive()'s value, worked out once per process (_MEMO)."""
    if 'value' not in _MEMO:
        _MEMO['value'] = _expensive()
    return _MEMO['value']


def _entry_value(n: int) -> int:
    """One entry's value, read through the memo."""
    return _memoized() + n


def _record_of(cache, site: str, inputs: tuple) -> dict:
    """The code record of `site`'s entry for `inputs` in work cache `cache`."""
    name = WC.key(site, inputs)
    return json.loads(WC.ran_path(cache / site / name[:2] / name).read_text(encoding='utf-8'))


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An empty work cache and memo."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(RC, 'SITES', {})
    _MEMO.clear()
    return tmp_path / 'work'


def test_a_memo_filled_for_entry_one_is_in_entry_two_record(cache):
    """The memoized helper runs during entry 1 only, yet entry 2 of the same site records it."""
    for n in (1, 2):
        assert WC.cached('memo_site', __name__, (n,), functools.partial(_entry_value, n)) == 7 + n
    entry_two = _record_of(cache, 'memo_site', (2,))
    assert HERE + '_expensive' in entry_two and HERE + '_entry_value' in entry_two


def test_ran_while_keeps_sites_apart(cache):
    """ran_while's site is the code its maker runs: another maker's record holds none of this one's memo work."""
    _, first = RC.ran_while(lambda: _entry_value(1))
    _, second = RC.ran_while(lambda: _entry_value(2))
    _, again = RC.ran_while(functools.partial(_entry_value, 3))
    assert HERE + '_expensive' in first and HERE + '_expensive' not in second | again


def test_a_versioned_entry_keys_on_its_version_alone(cache):
    """A versioned value is kept whatever code ran, with an empty code record; a new version makes it again."""
    made = []
    make = lambda: made.append(1) or len(made)
    assert WC.versioned('site', 1, (b'in',), make) == 1 == WC.versioned('site', 1, (b'in',), make)
    assert WC.versioned('site', 2, (b'in',), make) == 2
    assert _record_of(cache, 'site', WC.versioned_inputs(1, (b'in',))) == {}


@pytest.fixture
def records(tmp_path, monkeypatch):
    """An empty reference record folder; recording off."""
    monkeypatch.setattr(V, 'RECORDS', tmp_path / 'versions')
    monkeypatch.delenv(V.RECORD_ENV, raising=False)
    return monkeypatch


def _record(monkeypatch, version, references: dict) -> None:
    """Record `references` under `version`."""
    monkeypatch.setenv(V.RECORD_ENV, '1')
    with pytest.raises(pytest.skip.Exception):
        V.check('site', version, references)
    monkeypatch.delenv(V.RECORD_ENV)


def _refs(a_in: bytes, a_out, b_out) -> dict:
    """References 'a' (inputs `a_in`, value `a_out`) and 'b' (value `b_out`)."""
    return {'a': ((a_in, 1), lambda: a_out), 'b': ((b'b',), lambda: b_out)}


def test_the_version_check_fails_a_change_under_the_same_version(records):
    """Same results pass; a changed result under the same version and inputs fails, and recording it is refused;
    a bumped version needs the references recorded again, then passes."""
    _record(records, 1, _refs(b'a', np.arange(3.0), {'x', 'y'}))
    V.check('site', 1, _refs(b'a', np.arange(3.0), {'y', 'x'}))
    changed = _refs(b'a', np.arange(3.0) + 1e-15, {'x', 'y'})
    with pytest.raises(AssertionError, match='bump the version'):
        V.check('site', 1, changed)
    records.setenv(V.RECORD_ENV, '1')
    with pytest.raises(AssertionError, match='bump the version'):
        V.check('site', 1, changed)
    records.delenv(V.RECORD_ENV)
    with pytest.raises(AssertionError, match='not recorded'):
        V.check('site', 2, changed)
    _record(records, 2, changed)
    V.check('site', 2, changed)


def test_new_inputs_are_recorded_not_judged(records):
    """A reference whose inputs changed says nothing about the version: it fails until recorded, and recording it
    under the same version is allowed."""
    _record(records, 1, _refs(b'a', 1, 2))
    with pytest.raises(AssertionError, match=r"\['a'\] not recorded"):
        V.check('site', 1, _refs(b'new', 5, 2))
    _record(records, 1, _refs(b'new', 5, 2))
    V.check('site', 1, _refs(b'new', 5, 2))


def test_digest_tells_float_bits_and_ignores_set_order():
    """-0.0 and 0.0 differ, as do arrays of other types; set order does not count."""
    assert V.digest(0.0) != V.digest(-0.0) and V.digest(np.zeros(2)) != V.digest(np.zeros(2, np.float32))
    assert V.digest(frozenset(('a', 'b', 'c'))) == V.digest(frozenset(('c', 'b', 'a')))


def _elric_stand_in(paths: list, run, names: list) -> list:
    """Stand in for elric.finish: append b'+' to each staged mesh; none fails."""
    for path in paths:
        path.write_bytes(path.read_bytes() + b'+')
    return []


def test_a_finished_mesh_keeps_the_code_that_ran_finishing_it(cache, tmp_path, monkeypatch):
    """elric_finish's entry keys on Elric's tag and the mesh bytes; its record is what ran finishing (the stand-in),
    not every function of nif.elric's import tree."""
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'finish', _elric_stand_in)
    mesh = tmp_path / 'a.nif'
    mesh.write_bytes(b'a')
    assert EC.finish([mesh]) == [] and mesh.read_bytes() == b'a+'
    record = _record_of(cache, 'elric_finish', (b'tag', hashlib.sha1(b'a').digest()))
    assert HERE + '_elric_stand_in' in record and not any(k.startswith('fo4_import/base/') for k in record)


def _put(path, text: str = 'x') -> None:
    """Write `text` to `path`, making its folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_prune_drops_unnamed_sites_and_unrecorded_entries(cache):
    """Sites no code names go whole; an entry with no code record and a partial go; a recorded entry, a versioned
    one (empty record) and their records stay."""
    for site in ('bordered_map', 'normal_dds'):
        _put(cache / site / 'ab' / 'abcd')
    kept = [cache / 'spec_map' / 'ab' / 'ab01', cache / 'spec_map' / 'ab' / 'ab01.ran',
            cache / 'tint_fit' / 'cd' / 'cd01', cache / 'tint_fit' / 'cd' / 'cd01.ran']
    for path in kept:
        _put(path, '{}' if path.suffix == '.ran' else 'x')
    for path in (cache / 'spec_map' / 'ab' / 'ab02', cache / 'tint_fit' / 'cd' / 'cd02.1234.tmp'):
        _put(path)
    assert WC.prune_unnamed(cache) == ['bordered_map', 'normal_dds']
    assert WC.prune_unrecorded((cache, cache / 'missing')) == 2
    assert sorted(p for p in cache.rglob('*') if p.is_file()) == sorted(kept)
