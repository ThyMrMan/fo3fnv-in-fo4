"""The work cache: an entry another process holds open is left as it is, its value the same by its key."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from fo4_import.pipeline import work_cache as WC


def test_an_entry_held_open_elsewhere_keeps_its_copy(tmp_path, monkeypatch):
    """Replacing an existing entry that Windows refuses keeps that entry and drops the partial; with no entry the
    error stands."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path)
    assert WC.store('site', __name__, (b'x',), 1) == 1
    refuse = lambda self, target: (_ for _ in ()).throw(PermissionError(5, 'Access is denied'))
    monkeypatch.setattr(Path, 'replace', refuse)
    assert WC.store('site', __name__, (b'x',), 1) == 1 and not list(tmp_path.rglob('*.tmp'))
    with pytest.raises(PermissionError):
        WC.store('site', __name__, (b'y',), 2)


def test_a_group_keeps_its_two_newest_entries(tmp_path, monkeypatch):
    """One NPC's face stored under a third set of inputs (its record changed twice) deletes the oldest entry and
    its code record; the two newest and another NPC's entry stay, and storing the same inputs again keeps them."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path)
    for inputs in ((b'first',), (b'second',), (b'third',), (b'third',)):
        WC.store_latest('face', '', ('fnv.esm', 1), inputs, inputs[0], {})
    WC.store_latest('face', '', ('fnv.esm', 2), (b'other',), b'other', {})
    assert not WC.present('face', (b'first',)) and not list(tmp_path.rglob(WC.key('face', (b'first',)) + '*'))
    assert [WC.lookup('face', '', (k,)) for k in (b'second', b'third', b'other')] == [b'second', b'third', b'other']


def test_threads_storing_one_entry_together(tmp_path, monkeypatch):
    """Threads of one process storing the same entry at once (two voice lines with the same recording) all finish,
    the entry and its code record kept, no partial left."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path)
    with ThreadPoolExecutor(16) as pool:
        stored = list(pool.map(lambda _: WC.store_versioned('site', 1, (b'x',), b'value'), range(400)))
    assert stored == [b'value'] * 400 and WC.lookup_versioned('site', 1, (b'x',)) == b'value'
    assert not list(tmp_path.rglob('*.tmp'))
