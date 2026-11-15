"""Units of a build that replay from their journal: the changes a unit made to adopted state, the reads it made,
the units it asked for in between, and what it returned.

A unit is one call of a maker (a site: CellBuilder.base) for one key (an FNV FormID). Run live, its changes and
reads are logged (journal_state) and every other unit it asks for is logged in place as an ask. A journal replays
when every read it logged still finds what it found (stale()); replayed, the same changes are made again and each
ask asks that unit again (replayed or live in turn), so the memos and records come out as a live run leaves them.

See: docs/fork/fo4_plugin_layout.md#journal-units
"""

import collections
import functools
import os
import pickle
import re
import zlib
from pathlib import Path

from fo4_import.base import ba2_pack, source_fault
from fo4_import.pipeline import elric_cache, mesh_cache, ran_code
from fo4_import.pipeline import journal_state as JS
from fo4_import.pipeline.code_identity import changed, hashes

#: The op of a unit asking another: (None, ASK, (site, key)).
ASK = 'ask'
#: The environment variable naming a build's journal store file (opt-in while phase 6 is checked).
ENV = 'F3NV_JOURNAL'
#: The store's format: a store of another (or of another export) keeps no journal.
FORMAT = 2
#: (module, name) of module-level state units change: held pre-Elric meshes, staged textures, faults, clamp counts.
GLOBALS = ((elric_cache, '_HELD'), (ba2_pack, '_RUNS'), (source_fault, 'FAULTS'), (mesh_cache, 'CLAMPED'))
#: Ops that change the one key or value their first argument names; any other change touches its whole target.
_KEYED = frozenset({'set', 'del', 'add', 'discard'})


class Store:
    """The journals of a build: {(site, key): journal}, and which units replayed, ran live, and why."""

    def __init__(self, journals: 'dict | None' = None):
        """A store holding `journals`."""
        self.journals = {} if journals is None else journals
        self.ran, self.replayed, self.why = [], [], {}


#: The store of the running build; None: units run live and nothing is kept.
STORE = [None]
#: {site: the unit-running maker}, to ask a unit again in a replay.
_SITES = {}
#: {site: its done(owner, key)}.
_DONE = {}


def _journal(ops: list, result, ran: set) -> dict:
    """The journal of a live run: its ops, whether any is UNJOURNALED, its result pickled with names, and the
    identity of every repo function that ran in it (the units it asked included)."""
    bad = any(op[1] == JS.UNJOURNALED for op in ops)
    try:
        frozen_result = JS.frozen_value(result)
    except Exception:
        frozen_result, bad = None, True
    return {'ops': _settled(ops), 'result': frozen_result, 'unjournaled': bad, 'code': hashes(ran)}


def _settled(ops: list) -> list:
    """`ops` with one FILE op per file written, with its digest."""
    files = sorted({op[2][0] for op in ops if op[1] == JS.FILE})
    return [op for op in ops if op[1] != JS.FILE] + [(None, JS.FILE, (path, JS.file_digest(path))) for path in files]


class _Wrote:
    """What a journal's changes (and its asked units') wrote: keyed slots, the names with keyed slots, whole
    targets, and the names of what they made."""

    def __init__(self):
        """Nothing written yet."""
        self.slots, self.keyed, self.whole, self.made = set(), set(), set(), set()

    def change(self, name: str, change: str, args: tuple) -> None:
        """Note one change op."""
        if change in _KEYED:
            key = JS.thawed_value(args[0])
            self.slots.add((name, key))
            self.keyed.add(name)
            self.made.add(f'{name}[{key!r}]')
        else:
            self.whole.add(name)
            if change == 'attr':
                self.made.add(f'{name}.{JS.thawed_value(args[0])}')

    def covers(self, name: str, kind: str, key) -> bool:
        """Whether a read of `name` finds something this journal wrote, or an object it made (`name` or a name it
        is under)."""
        if name in self.whole or (kind in (JS.GET, JS.HAS) and (name, key) in self.slots):
            return True
        if kind in (JS.ALL, JS.LEN) and name in self.keyed:
            return True
        return name in self.made or any(name[:i] in self.made for i, c in enumerate(name) if c in '[.')


def stale(owner, journal: dict, store: Store, wrote: '_Wrote | None' = None) -> 'str | None':
    """Why `journal` cannot replay on this build's state now (None: it can): it is unjournaled, a read finds
    something else, or a unit it asks (not done yet) has no journal or one that cannot replay. The asked units'
    writes are noted in `wrote`, so this journal's later reads of them are theirs to check."""
    if journal['unjournaled']:
        return 'unjournaled'
    moved = changed(journal['code'])
    if moved:
        return f'code {moved}'
    wrote = _Wrote() if wrote is None else wrote
    for name, change, args in journal['ops']:
        if change == ASK:
            why = _asked(owner, args, store, wrote)
        elif change == JS.FILE:
            why = None if JS.file_digest(args[0]) == args[1] else f'file {args[0]}'[:200]
        elif change == JS.READ:
            why = None if wrote.covers(name, args[0], args[1]) or JS.read_holds(name, *args) else (
                f'read {name} {args[0]} {args[1]!r}'[:200])
        else:
            why = wrote.change(name, change, args)
        if why:
            return why
    return None


def _asked(owner, ask: tuple, store: Store, wrote: _Wrote) -> 'str | None':
    """stale() of a unit asked (site, key), its writes noted in `wrote`; None when it is done already."""
    site, key = ask
    if _DONE[site](owner, key):
        return None
    child = store.journals.get((site, key))
    if child is None:
        return f'asks {site} {key!r}, not journaled'
    why = stale(owner, child, store, wrote)
    return None if why is None else f'asks {site} {key!r}: {why}'


def _segments(ops: list) -> list:
    """`ops` cut at each ask: [(changes before it, the ask or None)], reads and files left out."""
    out, run = [], []
    for op in ops:
        if op[1] == ASK:
            out.append((run, op[2]))
            run = []
        elif op[1] not in (JS.READ, JS.FILE):
            run.append(op)
    return [*out, (run, None)]


def _replay(owner, journal: dict) -> tuple:
    """(True, its result) of `journal`'s changes made on this build's state, each unit it asked asked in place;
    (False, why) when its first changes cannot be thawed here (nothing made: the unit runs live). Each run of
    changes is thawed whole before any is made."""
    with JS.recording(None):
        for n, (changes, ask) in enumerate(_segments(journal['ops'])):
            try:
                thawed = [(name, change, [JS.thawed_value(v) for v in args]) for name, change, args in changes]
            except Exception as exc:
                if n:
                    raise
                return False, f'thaw {exc!r}'[:200]
            for name, change, args in thawed:
                JS.make_change(name, change, args)
            if ask is not None:
                _SITES[ask[0]](owner, ask[1])
    for _, change, args in journal['ops']:
        if change == JS.FILE and args[1] is not None:
            os.utime(args[0])
    return True, JS.thawed_value(journal['result'])


def _live(make, owner, key, site: str, store: Store):
    """`make`(owner, key) run live, its new journal kept."""
    with ran_code.capture() as ran, JS.recording([]) as ops:
        result = make(owner, key)
    store.journals[site, key] = _journal(ops, result, ran)
    store.ran.append((site, key))
    return result


def unit(site: str, done):
    """Decorate maker method `site` (called with the owner and one key) as a unit: `done(owner, key)` says its
    memo already holds the key (a plain call, no unit). Otherwise, with a STORE, the call is logged as an ask to the
    running unit, then replayed from a journal that can, else run live and its journal kept."""
    def wrap(make):
        """The unit-running form of `make`."""
        @functools.wraps(make)
        def run(owner, key):
            """`make`(owner, key) as a unit."""
            store = STORE[0]
            if store is None or done(owner, key):
                return make(owner, key)
            if JS.RUNNING[0] is not None:
                JS.RUNNING[0].append((None, ASK, (site, key)))
            journal = store.journals.get((site, key))
            why = 'no journal' if journal is None else stale(owner, journal, store)
            if why is None:
                done_now, out = _replay(owner, journal)
                if done_now:
                    store.replayed.append((site, key))
                    return out
                why = out
            store.why[site, key] = why
            return _live(make, owner, key, site, store)
        _SITES[site], _DONE[site] = run, done
        return run
    return wrap


def frozen(store: Store) -> bytes:
    """`store`'s journals as bytes."""
    return pickle.dumps(store.journals, protocol=5)


def thawed(data: bytes) -> Store:
    """A Store of the journals frozen() wrote."""
    return Store(pickle.loads(data))


def export_stamp(export_dir: Path) -> list:
    """(name, size, time) of each export file: what journals were made from."""
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in Path(export_dir).iterdir() if p.is_file())


def begin(builder, export_dir: Path) -> None:
    """With ENV naming a store file: adopt `builder` (journal_state) and run its units against the journals kept
    there for this export (none when the export changed); else nothing."""
    path = os.environ.get(ENV)
    if not path:
        return
    builder = JS.adopt_root(builder, 'builder')
    for module, name in GLOBALS:
        setattr(module, name, JS.adopt_root(getattr(module, name), f'{module.__name__}.{name}'))
    JS.watch_files()
    kept = Path(path)
    body = pickle.loads(zlib.decompress(kept.read_bytes())) if kept.is_file() else {}
    same = body.get('export') == export_stamp(export_dir) and body.get('format') == FORMAT
    STORE[0] = Store(body.get('journals') if same else None)
    print(f'journal: {len(STORE[0].journals)} unit journals kept'
          + ('' if same or not body else ' (none: the export or store format changed)'))


def ended(counts, export_dir: Path):
    """`counts` (the build's), with a store running: what replayed and ran live (and the commonest reasons)
    printed, its journals kept, and it stopped."""
    store = STORE[0]
    if store is None:
        return counts
    why = collections.Counter(re.sub(r'\[[^\]]*\]|\s\S+$', '', reason) for reason in store.why.values())
    print(f'journal: {len(store.replayed)} units replayed, {len(store.ran)} ran live')
    for reason, count in why.most_common(12):
        print(f'journal:   {count} {reason}')
    body = {'format': FORMAT, 'export': export_stamp(export_dir), 'journals': store.journals}
    Path(os.environ[ENV]).write_bytes(zlib.compress(pickle.dumps(body, protocol=5), 1))
    STORE[0] = None
    return counts
