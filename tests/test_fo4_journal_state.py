"""A unit's changes to shared build state, logged and made again on another build's state.

See: docs/fork/fo4_plugin_layout.md#journal-state
"""

import collections
import pickle
import threading

import pytest

from fo4_import.pipeline import journal_state as JS


class Maker:
    """Stands for a maker object of the build (its module adopted as ours by _own_names)."""

    def __init__(self):
        """Empty memos of every kind."""
        self.made, self.counts, self.by_anim = {}, collections.Counter(), collections.defaultdict(list)
        self.keyed, self.order, self.child = set(), [], None



def _state(maker: Maker) -> dict:
    """`maker`'s state as plain values."""
    child = None if maker.child is None else dict(vars(maker.child), _jname=None)
    return {'made': dict(maker.made), 'counts': dict(maker.counts), 'by_anim': {k: list(v) for k, v in
            maker.by_anim.items()}, 'keyed': set(maker.keyed), 'order': list(maker.order),
            'child': {k: v for k, v in (child or {}).items() if k != '_jname'}}


def _unit(maker: Maker) -> None:
    """Stands for a unit: every kind of change, a value stored and then changed again, a new object."""
    maker.made[0x1234] = {'fid': 7, 'parts': []}
    maker.made[0x1234]['parts'].append('mesh.nif')
    maker.counts['WEAP'] += 1
    maker.counts.update(['ARMO', 'ARMO'])
    maker.by_anim[3].append(0x1234)
    maker.keyed |= {'a', 'b'}
    maker.keyed.discard('a')
    maker.order.extend([3, 1, 2])
    maker.order.sort()
    maker.child = Maker()
    maker.child.made.setdefault('k', []).append(1)


@pytest.fixture(autouse=True)
def _own_names(monkeypatch):
    """Each test with its own name table."""
    monkeypatch.setattr(JS, 'NAMES', {})
    monkeypatch.setattr(JS, 'PACKAGES', (Maker.__module__,))


def _recorded() -> tuple:
    """(maker, ops) of _unit() run on an adopted Maker."""
    maker = JS.adopt_root(Maker(), 'builder')
    with JS.recording([]) as ops:
        _unit(maker)
    return maker, ops


def test_a_units_changes_made_again_on_a_fresh_build_give_the_same_state():
    """The ops applied to another build's adopted Maker (its own names) leave it as the unit left the first."""
    maker, ops = _recorded()
    ops = pickle.loads(pickle.dumps(ops))
    JS.NAMES.clear()
    again = JS.adopt_root(Maker(), 'builder')
    JS.apply(ops)
    assert _state(again) == _state(maker)
    assert _state(again)['counts'] == {'WEAP': 1, 'ARMO': 2} and again.order == [1, 2, 3]
    assert again.made[0x1234] == {'fid': 7, 'parts': ['mesh.nif']}


def test_changes_outside_a_unit_are_not_logged_and_a_nested_unit_logs_its_own():
    """No ops without recording(); a nested recording takes its own changes, the outer one the rest."""
    maker = JS.adopt_root(Maker(), 'builder')
    maker.counts['setup'] += 1
    with JS.recording([]) as outer:
        maker.counts['outer'] += 1
        with JS.recording([]) as inner:
            maker.counts['inner'] += 1
        maker.counts['outer'] += 1
    assert [op[0] for op in outer] == ['builder.counts'] * 2 and len(inner) == 1


def test_a_value_that_cannot_be_pickled_marks_the_unit_unjournaled():
    """A lock stored in a memo: the build goes on, and the unit's ops say it cannot be replayed."""
    maker = JS.adopt_root(Maker(), 'builder')
    with JS.recording([]) as ops:
        maker.made['lock'] = threading.Lock()
    assert ops[0][1] == JS.UNJOURNALED and isinstance(maker.made['lock'], type(threading.Lock()))


def test_a_name_this_build_does_not_hold_is_untracked():
    """apply() of an op on a name nothing here holds raises Untracked."""
    with pytest.raises(JS.Untracked):
        JS.apply([('builder.nowhere', 'set', (pickle.dumps(1), pickle.dumps(2)))])


def test_adopted_state_pickles_plain_for_a_worker():
    """A pool worker given adopted state gets plain containers and the maker's own class."""
    maker, _ = _recorded()
    copy = pickle.loads(pickle.dumps(maker))
    assert type(copy.made) is dict and type(copy.counts) is collections.Counter
    assert type(copy.by_anim) is collections.defaultdict and type(copy.child) is Maker.__mro__[0]


def test_running_totals_and_high_water_marks_merge_into_what_a_replay_finds():
    """A MERGES total adds its change, a high-water mark keeps the larger, an unchanged mark logs nothing: applied
    to state that moved on since, both still land where the build's own run would."""
    JS.MERGES[Maker.__qualname__, 'total'] = JS.ADD
    JS.MERGES[Maker.__qualname__, 'top'] = JS.MAX
    try:
        maker = JS.adopt_root(Maker(), 'builder')
        maker.total, maker.top = 10, 5
        with JS.recording([]) as ops:
            maker.total += 3
            maker.top = max(maker.top, 8)
            maker.top = max(maker.top, 2)
        assert [op[1] for op in ops] == [JS.ADD, JS.MAX]
        maker.total, maker.top = 20, 9
        JS.apply(ops)
        assert (maker.total, maker.top) == (23, 9)
    finally:
        del JS.MERGES[Maker.__qualname__, 'total'], JS.MERGES[Maker.__qualname__, 'top']
