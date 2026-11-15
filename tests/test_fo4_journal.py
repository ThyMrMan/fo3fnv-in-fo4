"""Units replayed from their journals leave the build's state as running them live did.

See: docs/fork/fo4_plugin_layout.md#journal-units
"""

import collections
import os

import pytest

from fo4_import.pipeline import journal as J
from fo4_import.pipeline import journal_state as JS


class Builder:
    """Stands for CellBuilder: a base unit that asks for its parts' bases, a memo, records and counts."""

    def __init__(self, parts: dict, sizes: dict):
        """`parts`: {FormID: parts asked first}; `sizes`: {FormID: record size}."""
        self.parts, self.sizes, self.made, self.records = parts, sizes, {}, []
        self.counts = collections.Counter()

    @J.unit('test base', lambda builder, fid: fid in builder.made)
    def base(self, fid: int) -> int:
        """Ask for each part's base, then write this one's record; its new FormID."""
        if fid in self.made:
            return self.made[fid]
        LIVES.append(fid)
        made = [self.base(part) for part in self.parts.get(fid, ())]
        self.made[fid] = fid + 0x01000000
        self.records.append(('STAT', fid, tuple(made), self.sizes.get(fid, 1)))
        self.counts['STAT'] += 1
        return self.made[fid]


PARTS = {1: (2, 3), 2: (3,), 4: (2,)}
#: The FormIDs whose base ran live in the last _build().
LIVES = []


@pytest.fixture(autouse=True)
def _own_state(monkeypatch):
    """Each test with its own names, store and adopted package."""
    monkeypatch.setattr(JS, 'NAMES', {})
    monkeypatch.setattr(JS, 'PACKAGES', (Builder.__module__,))
    monkeypatch.setattr(J, 'STORE', [None])


def _build(store: J.Store, sizes: 'dict | None' = None) -> Builder:
    """A Builder of record `sizes` adopted, then bases 1 and 4 asked for with `store`."""
    LIVES.clear()
    builder = JS.adopt_root(Builder(PARTS, sizes or {}), 'builder')
    J.STORE[0] = store
    assert builder.base(1) == 0x01000001 and builder.base(4) == 0x01000004
    return builder


def _state(builder: Builder) -> tuple:
    """The builder's output: memo, records, counts."""
    return dict(builder.made), list(builder.records), dict(builder.counts)


def test_a_replayed_build_equals_the_live_one_and_runs_no_unit():
    """Every unit's journal replays, the ones it asked for too: same memo, records (in the same order) and counts;
    nothing ran live."""
    live = _build(J.Store())
    JS.NAMES.clear()
    replayed_store = J.thawed(J.frozen(J.STORE[0]))
    again = _build(replayed_store)
    assert _state(again) == _state(live) and LIVES == []
    assert sorted(replayed_store.replayed) == [('test base', key) for key in (1, 2, 3, 4)]


def test_an_invalid_journal_runs_live_and_the_units_it_asks_still_replay():
    """Unit 2's journal invalid: it runs live, and 1, which asks it first, with it; 4 asks it done and replays."""
    live = _build(J.Store())
    JS.NAMES.clear()
    store = J.thawed(J.frozen(J.STORE[0]))
    store.journals['test base', 2]['unjournaled'] = True
    again = _build(store)
    assert _state(again) == _state(live) and LIVES == [1, 2]


@pytest.mark.parametrize('changed, lives', [(4, [4]), (3, [1, 2, 3])])
def test_a_unit_whose_read_finds_something_else_runs_live_with_the_units_asking_it(changed, lives):
    """A setup input one unit reads changed: that unit runs live, and every unit asking it before it is done; the
    state as a live build of the new input's; the counts add up rather than being set to the old totals."""
    _build(J.Store())
    JS.NAMES.clear()
    store = J.thawed(J.frozen(J.STORE[0]))
    again = _build(store, {changed: 9})
    JS.NAMES.clear()
    fresh = _build(J.Store(), {changed: 9})
    assert _state(again) == _state(fresh) and sorted(store.ran) == [('test base', k) for k in lives]
    assert dict(again.counts) == {'STAT': 4}


def test_a_unit_whose_code_changed_runs_live():
    """Unit 3's journal names a function identity that is not the code's now: 3 runs live, with 1 and 2 that ask
    it first; every journal names the test's own base among the code it ran."""
    _build(J.Store())
    JS.NAMES.clear()
    store = J.thawed(J.frozen(J.STORE[0]))
    assert all(any(key.endswith('Builder.base') for key in j['code']) for j in store.journals.values())
    store.journals['test base', 3]['code'] = dict.fromkeys(store.journals['test base', 3]['code'], 'old')
    _build(store)
    assert sorted(store.ran) == [('test base', k) for k in (1, 2, 3)] and store.why['test base', 3].startswith('code')


class Writer:
    """Stands for a maker writing a file per key into `folder`."""

    def __init__(self, folder):
        """An empty memo writing into `folder`."""
        self.folder, self.made = str(folder), {}

    @J.unit('test file', lambda maker, key: key in maker.made)
    def make(self, key: str) -> str:
        """Write `key`.txt; its path."""
        LIVES.append(key)
        path = os.path.join(self.folder, f'{key}.txt')
        with open(path, 'w', encoding='utf-8') as out:
            out.write(key)
        self.made[key] = path
        return path


def _written(tmp_path, store: J.Store) -> Writer:
    """A Writer adopted, files a and b made with `store`."""
    LIVES.clear()
    JS.NAMES.clear()
    JS.watch_files()
    writer = JS.adopt_root(Writer(tmp_path), 'writer')
    J.STORE[0] = store
    writer.make('a'), writer.make('b')
    return writer


def test_a_replay_touches_the_files_its_unit_wrote_and_a_lost_one_runs_it_live(tmp_path):
    """Replayed, a unit's files are touched (kept by the build's stale-file pass); one deleted since makes its unit
    run live and write it again."""
    _written(tmp_path, J.Store())
    store = J.thawed(J.frozen(J.STORE[0]))
    os.utime(tmp_path / 'a.txt', (0, 0))
    os.remove(tmp_path / 'b.txt')
    _written(tmp_path, store)
    assert LIVES == ['b'] and store.why['test file', 'b'].startswith('file')
    assert (tmp_path / 'a.txt').stat().st_mtime > 0 and (tmp_path / 'b.txt').read_text(encoding='utf-8') == 'b'
