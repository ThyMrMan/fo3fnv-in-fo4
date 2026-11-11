"""What a mod would rerun in a replayed build: a game build's read log (fo4_import.pipeline.read_log) against the
records each mod changes and adds.

    py -3.14 -m tools.audit.read_log_report --log output/fo4_cache/read_log/FalloutNV.esm
        --game export/FalloutNV.esm --mod "export/Landscape Disposition Fix" [--mod ...] [--limit 20]
        [--check <mod export> <its build's recording> <the plugin it wrote>]

Always: the recording's summary and the size of the journal it makes. Per --mod: the units that read a record it
changes, by kind; and for each type it adds a record to, the units that read the whole type, with the fields read
on every record, on some, where it was asked and the narrower question it could be recorded as. Per --check: each
record of the mod's plugin by whether a replay reruns the unit that wrote it, and the build's time by the same.

See: docs/fork/fo4_build_speed.md#replay-spike
"""

import argparse
import collections
import io
import json
import sys
from pathlib import Path

import numpy as np

from fo4_import.base.master_overrides import KEPT
from fo4_import.pipeline.export_index import held_types, master_names, master_records, own_records
from tes5_import.base.tes5_reader import walk

SUFFIX = '.reads'
#: Field names the recorder logs for a read of some field (records-only mode) and of every field.
ANY, WHOLE = '?', '*'
#: Unit kinds holding derived data other units read without a logged read: a hit on one is a hit on its askers.
DATA_KINDS = frozenset({'memo', 'init'})
#: Fields naming the record itself: a type read only by them on every record is a keyed lookup.
IDENTITY = frozenset({'FormID', 'EditorID', 'Signature'})
#: A whole-type reader filtering on more fields than this is an aggregate, not a question.
MAX_FILTER = 3
#: The columns of a recording's records written (read_log._written).
WRITE_FIELDS = ('unit', 'fid', 'sig', 'size', 'hash')


def _loaded(folder: Path) -> list:
    """The (meta, arrays) of each process log of the newest run in `folder`."""
    logs = [np.load(path) for path in sorted(folder.glob(f'*{SUFFIX}'))]
    metas = [json.loads(bytes(log['meta'])) for log in logs]
    if not logs:
        raise SystemExit(f'{folder}: no {SUFFIX} file')
    newest = max(int(meta['run'] or 0) for meta in metas)
    return [(meta, log) for meta, log in zip(metas, logs) if int(meta['run'] or 0) == newest]


class Recording:
    """A run's process logs merged: units, export files, field names and questions numbered once; `unit`, `rec`,
    `field` are the reads kept per unit (sorted by unit), `sets` the big ones shared by the units of `set_units`."""

    def __init__(self, folder: Path):
        """Read the newest run in `folder`."""
        self.units, self.fields, self.names, self.files = {}, {}, {}, {}
        self.sets, self.set_units, self.unit_sets = [], collections.defaultdict(list), collections.defaultdict(list)
        self.where, self.sites, self.problems = collections.defaultdict(set), collections.Counter(), []
        self.top, self.processes, self.with_fields = 0, 0, True
        self.verdicts, self.spent = {}, collections.Counter()
        parts = collections.defaultdict(list)
        for meta, log in _loaded(folder):
            self._merge(meta, log, parts)
            self._merge_writes(meta, log, parts)
        merged = {name: np.concatenate(chunks) if chunks else np.zeros(0, np.int64) for name, chunks in parts.items()}
        self.writes = {name: merged.get(f'write_{name}', np.zeros(0, np.int64)) for name in WRITE_FIELDS}
        order = np.lexsort((merged['field'], merged['rec'], merged['unit']))
        self.unit, self.rec, self.field = (merged[name][order] for name in ('unit', 'rec', 'field'))
        self.start = np.searchsorted(self.unit, np.arange(len(self.units) + 1))
        self.edges, self.asked = (merged['edge_a'], merged['edge_b']), (merged['asked_a'], merged['asked_b'])
        self.unit_list, self.field_list = list(self.units), list(self.fields)
        self.name_list, self.kinds = list(self.names), np.array([kind for kind, _ in self.units])

    def _file_shift(self, files: list) -> tuple:
        """(first record numbers, the shift of each to this recording's numbering) of a process's `files`."""
        bases, shifts = [], []
        for folder, sig, base, count, path in files:
            key = (folder.lower(), sig, count)
            if key not in self.files:
                self.files[key] = self.top
                self.top += count
            bases.append(base)
            shifts.append(self.files[key] - base)
        return np.array(bases, np.int64), np.array(shifts, np.int64)

    def _merge(self, meta: dict, log, parts: dict) -> None:
        """Add one process's log, its numbers mapped to this recording's."""
        unit = np.array([self.units.setdefault((kind, key), len(self.units)) for kind, key in meta['units']], np.int64)
        field = np.array([self.fields.setdefault(name, len(self.fields)) for name in meta['field_names']], np.int64)
        name = np.array([self.names.setdefault(text, len(self.names)) for text in meta['names']] or [0], np.int64)
        bases, shifts = self._file_shift(meta['files'])
        moved = lambda rec: rec.astype(np.int64) + shifts[np.searchsorted(bases, rec, side='right') - 1]
        parts['unit'].append(unit[log['unit']])
        parts['rec'].append(moved(log['rec']))
        parts['field'].append(field[log['field']])
        first, starts = len(self.sets), log['big_start']
        big_rec, big_field = moved(log['big_rec']), field[log['big_field']]
        self.sets += [(big_rec[a:b], big_field[a:b]) for a, b in zip(starts[:-1], starts[1:])]
        for uid, sid in zip(unit[log['big_a']], log['big_b']):
            self.set_units[first + int(sid)].append(int(uid))
            self.unit_sets[int(uid)].append(first + int(sid))
        for key, table in (('edge', unit), ('asked', name)):
            parts[f'{key}_a'].append(unit[log[f'{key}_a']])
            parts[f'{key}_b'].append(table[log[f'{key}_b']])
        for kind, places in meta['where'].items():
            self.where[kind].update(places)
        self.sites.update({(op, place): count for op, place, count in meta['sites']})
        self.problems += [f'unit not found: {name}' for name in meta['missing']]
        self.problems += [f'recorder error x{count}: {text}' for text, count in meta['errors'].items()]
        self.processes, self.with_fields = self.processes + 1, self.with_fields and meta['fields']

    def _merge_writes(self, meta: dict, log, parts: dict) -> None:
        """Add one process's records written, verdicts and unit times (a log of format 2 or later)."""
        if 'write_unit' not in log:
            return
        unit = np.array([self.units[kind, key] for kind, key in meta['units']], np.int64)
        parts['write_unit'].append(unit[log['write_unit']])
        for name in WRITE_FIELDS[1:]:
            parts[f'write_{name}'].append(log[f'write_{name}'])
        self.verdicts.update(zip(log['verdict_fid'].tolist(), (meta['verdicts'][i] for i in log['verdict_kind'])))
        self.spent.update(dict(zip(unit[log['spent_unit']].tolist(), log['spent_s'].tolist())))

    def labels(self, renamed: tuple = ('', '')) -> list:
        """Each unit's (kind, key), (old, new) `renamed` in its key."""
        return [(kind, key.replace(*renamed) if renamed[0] else key) for kind, key in self.unit_list]

    def file(self, folder: str, sig: str) -> tuple:
        """(first record number, count) of `folder`'s type `sig`; (0, 0) if not parsed."""
        found = [(base, key[2]) for key, base in self.files.items() if key[:2] == (folder.lower(), sig)]
        return max(found, key=lambda item: item[1], default=(0, 0))

    def reads(self, uid: int, base: int, count: int) -> tuple:
        """(record numbers, field ids) unit `uid` read in records `base` to `base + count`, each pair once."""
        recs, fields = self.rec[self.start[uid]:self.start[uid + 1]], self.field[self.start[uid]:self.start[uid + 1]]
        chunks = [(recs, fields)] + [self.sets[sid] for sid in self.unit_sets.get(uid, ())]
        codes = np.unique(np.concatenate([rec << 32 | field for rec, field in chunks]))
        codes = codes[(codes >> 32 >= base) & (codes >> 32 < base + count)]
        return codes >> 32, codes & 0xFFFFFFFF

    def askers(self, hit: set, data_only: bool) -> set:
        """`hit` and every unit that asked one of them, and so on up; `data_only`: only through DATA_KINDS units
        (a unit that asked a maker took a FormID back, one that asked a memo took what it derived)."""
        seen, frontier = set(hit), set(hit)
        while frontier:
            spread = [uid for uid in frontier if not data_only or self.kinds[uid] in DATA_KINDS]
            parents = set(self.edges[0][np.isin(self.edges[1], np.array(spread, np.int64))].tolist()) if spread else set()
            frontier = parents - seen
            seen |= frontier
        return seen


def changes(game: Path, mod: Path) -> dict:
    """{type: ({position in the game's type file: fields the mod changes}, records the mod adds, overrides of
    another master's records, overrides equal to the game's)} of mod export `mod` against game export `game`."""
    masters = [name.lower() for name in master_names(str(mod))]
    if game.name.lower() not in masters:
        raise SystemExit(f'{mod}: {game.name} is not among its masters {masters} (pass the plugin\'s export folder)')
    out = {}
    for sig in held_types(mod):
        theirs = master_records(str(mod), str(game), sig)
        at = {rec.get('FormID'): position for position, rec in enumerate(theirs)}
        changed, counts = {}, collections.Counter()
        for rec in (rec for rec in own_records(mod, sig) if 'FormID' in rec):
            position = at.get(rec['FormID'])
            differing = {key for key in rec.keys() | theirs[position].keys()
                         if rec.get(key) != theirs[position].get(key)} if position is not None else set()
            if differing:
                changed[position] = differing
            counts['same' if position is not None and not differing else
                   'added' if position is None and int(rec['FormID'], 16) >> 24 >= len(masters) else
                   'other' if position is None else 'changed'] += 1
        out[sig] = (changed, counts['added'], counts['other'], counts['same'])
    return out


def _hit_units(recording: Recording, numbers: np.ndarray, codes: np.ndarray) -> tuple:
    """(units reading a record of `numbers`, units reading one of `codes`: record << 32 | field id)."""
    by_record = set(recording.unit[np.isin(recording.rec, numbers)].tolist())
    by_field = set(recording.unit[np.isin(recording.rec << 32 | recording.field, codes)].tolist())
    for sid, (recs, fields) in enumerate(recording.sets):
        by_record |= set(recording.set_units[sid]) if np.isin(recs, numbers).any() else set()
        by_field |= set(recording.set_units[sid]) if np.isin(recs << 32 | fields, codes).any() else set()
    return by_record, by_field


def _changed_codes(recording: Recording, game: Path, changed: dict) -> tuple:
    """(record numbers, record << 32 | field id codes) of the records and fields the mod changes (changes())."""
    numbers, codes = [], []
    for sig, (positions, *_) in changed.items():
        base, count = recording.file(game.name, sig)
        for position, fields in positions.items() if count else ():
            numbers.append(base + position)
            ids = [recording.fields[name] for name in (*fields, ANY, WHOLE) if name in recording.fields]
            codes += [base + position << 32 | fid for fid in ids]
    return np.array(numbers, np.int64), np.array(codes, np.int64)


def changed_readers(recording: Recording, game: Path, changed: dict) -> list:
    """Report lines: how many units read a record the mod changes (`changed`: changes()), by kind: any field of
    it, a field that differs, then with the askers of the data units among those, then with every asker."""
    numbers, codes = _changed_codes(recording, game, changed)
    by_record, by_field = _hit_units(recording, numbers, codes)
    columns = (by_record, by_field, recording.askers(by_field, True), recording.askers(by_field, False))
    lines = [f'  records changed and read by the game build: {len(set(numbers))}',
             f'  {"kind":<16}{"units":>9}{"record":>9}{"field":>9}{"+memo":>9}{"+askers":>9}']
    totals = collections.Counter(recording.kinds.tolist())
    tallies = [collections.Counter(recording.kinds[list(column)].tolist()) for column in columns]
    for kind in sorted(totals, key=lambda kind: -tallies[1][kind]):
        if any(tally[kind] for tally in tallies):
            lines.append(f'  {kind:<16}{totals[kind]:>9}' + ''.join(f'{tally[kind]:>9}' for tally in tallies))
    lines.append(f'  {"all":<16}{len(recording.kinds):>9}' + ''.join(f'{len(column):>9}' for column in columns))
    data = sorted(' '.join(recording.unit_list[uid]) for uid in by_field if recording.kinds[uid] != 'process'
                  and (recording.kinds[uid] in DATA_KINDS or recording.kinds[uid] == 'stage'))
    return lines + [f'  setup units among them (their derived data is read without a log): {len(data)}'] + [
        f'    {name}' for name in data]


def question(sig: str, filters: set) -> str:
    """The narrower question a whole-type read filtering on fields `filters` could be recorded as, or aggregate."""
    named = sorted(filters - {ANY, WHOLE})
    keys = [name for name in named if name not in IDENTITY]
    if filters & {ANY, WHOLE} or len(keys) > MAX_FILTER or not named:
        return 'aggregate'
    if not keys:
        return f'{sig} by {" or ".join(named)} (a keyed lookup)'
    return f'{sig} where {", ".join(keys)} = ...'


def _full_readers(recording: Recording, base: int, count: int) -> set:
    """Units whose kept reads, or one shared big read, touch every record of `base` to `base + count`."""
    inside = (recording.rec >= base) & (recording.rec < base + count)
    pairs = np.unique(recording.unit[inside] << 32 | recording.rec[inside])
    units, touched = np.unique(pairs >> 32, return_counts=True)
    full = set(units[touched == count].tolist())
    for sid, (recs, _) in enumerate(recording.sets):
        if len(np.unique(recs[(recs >= base) & (recs < base + count)])) == count:
            full |= set(recording.set_units[sid])
    return full


def _asking(recording: Recording, folder: str, sig: str) -> dict:
    """{unit: [where it asked]} of the units that asked for export `folder`'s whole type `sig` (export_records,
    own_records) or walked the source plugin for it (or for every type)."""
    out = collections.defaultdict(list)
    for uid, name in zip(*recording.asked):
        kind, *rest = recording.name_list[name].split('\t')
        if kind == 'records' and (rest[1].lower(), rest[2]) == (folder.lower(), sig):
            out[int(uid)].append(f'{rest[0]} at {rest[3]}')
        elif kind == 'walk' and (rest[0] == WHOLE or sig in rest[0].split(',')):
            out[int(uid)].append(f'binary walk {rest[0]} at {rest[2]}')
    return out


def _reader(recording: Recording, uid: int, span: tuple, asked: list) -> tuple:
    """(kind, fields read on every record the unit read, places asked) of a whole-type reader, then (records
    read, fields read on some): how units are grouped, and what a group adds up."""
    recs, fields = recording.reads(uid, *span)
    read = len(np.unique(recs))
    ids, on = np.unique(fields, return_counts=True)
    every = frozenset(recording.field_list[fid] for fid, n in zip(ids.tolist(), on.tolist()) if n == read)
    some = {recording.field_list[fid] for fid, n in zip(ids.tolist(), on.tolist()) if n < read}
    places = tuple(sorted(set(asked))) or tuple(sorted(recording.where.get(recording.kinds[uid], ())))[:2]
    return (str(recording.kinds[uid]), every, places), (read, some)


def type_readers(recording: Recording, game: Path, sig: str, limit: int) -> list:
    """Report lines: the units reading all of the game's type `sig` (every record read, or the type asked for),
    grouped by kind, filter fields and place."""
    span = recording.file(game.name, sig)
    asking = _asking(recording, game.name, sig)
    groups = collections.defaultdict(list)
    for uid in sorted(_full_readers(recording, *span) | set(asking) if span[1] else set(asking)):
        key, facts = _reader(recording, uid, span, asking.get(uid, []))
        groups[key].append((uid, *facts))
    lines = [f'  {sig}: {span[1]} records in the game; {sum(map(len, groups.values()))} whole-type readers'
             + ('' if span[1] else ' (the build never parsed this type)')]
    for (kind, every, places), members in sorted(groups.items(), key=lambda item: -len(item[1]))[:limit]:
        some = collections.Counter(name for _, _, names in members for name in names)
        read = sorted({read for _, read, _ in members})
        lines += [f'    {kind} x{len(members)} (e.g. {" ".join(recording.unit_list[members[0][0]])}): '
                  f'read {read[0]}{f"-{read[-1]}" if len(read) > 1 else ""} of {span[1]} records',
                  f'      on every record read: {", ".join(sorted(every)) or "nothing"}',
                  f'      on some: {", ".join(name for name, _ in some.most_common(8)) or "nothing"}'
                  f'{f" (+{len(some) - 8} more)" if len(some) > 8 else ""}',
                  f'      at: {"; ".join(places) or "unknown"}',
                  f'      could be: {question(sig, set(every))}']
    return lines


def summary(recording: Recording, limit: int) -> list:
    """Report lines about the recording itself: its size, units by kind, whole-record reads by place, problems."""
    kinds = collections.Counter(recording.kinds.tolist())
    big = sum(len(recs) for recs, _ in recording.sets)
    lines = [f'recording: {recording.processes} process(es), {len(recording.units)} units, {len(recording.files)} '
             f'export files ({recording.top} records), {len(recording.unit)} reads kept per unit, {big} in '
             f'{len(recording.sets)} shared big reads, {len(recording.edges[0])} edges, {len(recording.asked[0])} '
             f'questions; fields {"logged" if recording.with_fields else "NOT logged (records only)"}',
             'units by kind: ' + ', '.join(f'{kind} {count}' for kind, count in kinds.most_common())]
    lines += [f'whole-record reads and writes by place (top {limit}; a copy ends the log of later reads):']
    lines += [f'  {count:>9} {op:<14} {place}' for (op, place), count in recording.sites.most_common(limit)]
    return lines + [f'PROBLEM {text}' for text in recording.problems]


def mod_report(recording: Recording, game: Path, mod: Path, limit: int) -> list:
    """Report lines for one mod: its changes by type, the units reading a changed record, the whole-type readers
    of each type it adds to."""
    found = changes(game, mod)
    lines = [f'\n== {mod.name} ==', '  type  changed  added  other-master  same-as-game']
    lines += [f'  {sig:<5}{len(changed):>8}{added:>7}{other:>14}{same:>14}'
              for sig, (changed, added, other, same) in found.items()]
    lines += ['  (1) units that read a record the mod changes'] + changed_readers(recording, game, found)
    lines.append('  (2) whole-type readers of each type the mod adds a record to')
    for sig in (sig for sig, (_, added, _, _) in found.items() if added):
        lines += type_readers(recording, game, sig, limit)
    return lines


def _delta(units: np.ndarray, values: np.ndarray, *rest: np.ndarray) -> dict:
    """Pairs (unit, value, rest...) as a journal stores them: sorted, each unit's count, values as steps from the
    unit's last one."""
    order = np.lexsort((*reversed(rest), values, units))
    units, values = units[order], values[order]
    steps = np.diff(values, prepend=0)
    first = np.ones(len(units), bool)
    first[1:] = units[1:] != units[:-1]
    steps[first] = values[first]
    out = {'counts': np.bincount(units).astype(np.uint32), 'steps': steps.astype(np.int64)}
    return out | {f'rest{i}': column[order].astype(np.uint32) for i, column in enumerate(rest)}


def _zipped(arrays: dict) -> tuple:
    """(raw bytes, zip-compressed bytes) of `arrays` saved as one npz."""
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **{name: np.ascontiguousarray(array) for name, array in arrays.items()})
    return sum(array.nbytes for array in arrays.values()), buffer.tell()


def _journal_parts(recording: Recording) -> dict:
    """{part: arrays} of the journal `recording` makes: reads by record and by field, shared big reads, writes,
    the units asked, the questions, the unit names."""
    units, recs, fields = recording.unit, recording.rec, recording.field
    pairs = np.unique(units << 32 | recs)
    big = [np.unique(set_recs) for set_recs, _ in recording.sets]
    members = np.array([(uid, sid) for sid, uids in recording.set_units.items() for uid in uids], np.int64)
    writes = recording.writes
    text = '\n'.join([*('\t'.join(label) for label in recording.unit_list), *recording.name_list]).encode()
    return {'reads by record': _delta(pairs >> 32, pairs & 0xFFFFFFFF),
            'reads by field': _delta(units, recs, fields),
            'shared big reads': {'steps': np.concatenate([np.diff(b, prepend=0) for b in big] or [np.zeros(0)]),
                                 'members': members.reshape(-1, 2), 'sizes': np.array([len(b) for b in big])},
            'records written': _delta(writes['unit'], writes['fid']),
            'units asked': {'a': recording.edges[0], 'b': recording.edges[1]},
            'questions': {'a': recording.asked[0], 'b': recording.asked[1]},
            'names': {'text': np.frombuffer(text, np.uint8)}}


def journal_size(recording: Recording) -> list:
    """Report lines: the journal this recording makes, part by part and in all, raw and zip-compressed, with reads
    by record or by field (record bytes are the plugin's, not the journal's)."""
    lines = ['journal (zip-compressed npz; record bytes stay in the plugin):',
             f'  {"part":<20}{"items":>12}{"raw MB":>10}{"zipped MB":>11}']
    sizes = {}
    for part, arrays in _journal_parts(recording).items():
        sizes[part] = _zipped(arrays)
        items = max(len(array) for array in arrays.values())
        lines.append(f'  {part:<20}{items:>12}{sizes[part][0] / 1e6:>10.1f}{sizes[part][1] / 1e6:>11.1f}')
    for kept, other in (('reads by record', 'reads by field'), ('reads by field', 'reads by record')):
        left = [part for part in sizes if part != other]
        lines.append(f'  all, {kept}: {sum(sizes[p][0] for p in left) / 1e6:.1f} MB raw, '
                     f'{sum(sizes[p][1] for p in left) / 1e6:.1f} MB zipped')
    fids, size = recording.writes['fid'], recording.writes['size'].sum()
    return lines + [f'  records written {len(fids)} ({len(np.unique(fids))} FormIDs, {size / 1e6:.1f} MB of bytes)']


def _walkers(recording: Recording, sigs: set) -> set:
    """Units that walked the binary source for one of `sigs` (logged per type)."""
    return {int(uid) for uid, name in zip(*recording.asked) if recording.name_list[name].startswith('walk\t')
            and set(recording.name_list[name].split('\t')[1].split(',')) & sigs}


def _moved_into(game: Path, mod: Path) -> set:
    """('cell refs', cell) labels of the cells the mod moves a game REFR into."""
    theirs = {rec['FormID']: rec.get('ParentCELL') for rec in master_records(str(mod), str(game), 'REFR')}
    return {('cell refs', rec['ParentCELL']) for rec in own_records(mod, 'REFR') if rec.get('ParentCELL')
            and rec['FormID'] in theirs and theirs[rec['FormID']] != rec['ParentCELL']}


def rerun(recording: Recording, game: Path, found: dict) -> set:
    """Game units a replayed build of a mod (`found`: changes()) runs: readers of a field it changes, and binary
    walkers of a type it changes, with the askers of the data units among them; the whole-type readers of each type
    it adds a record to."""
    changed = {sig for sig, (positions, *_) in found.items() if positions}
    hit = _hit_units(recording, *_changed_codes(recording, game, found))[1] | _walkers(recording, changed | {WHOLE})
    out = recording.askers(hit, True)
    for sig in (sig for sig, (_, added, _, _) in found.items() if added):
        span = recording.file(game.name, sig)
        out |= set(_asking(recording, game.name, sig)) | (_full_readers(recording, *span) if span[1] else set())
    return out


def _status(units: set, labels: list, runs: set, known: set) -> str:
    """How a replay makes a record written by mod-build `units`: rerun, a new unit, outside any unit, or MISSED."""
    if not units:
        return 'no writer logged'
    if all(labels[uid][0] == 'process' for uid in units):
        return 'outside any unit'
    if any(labels[uid] in runs for uid in units):
        return 'rerun'
    return 'new unit' if any(labels[uid] not in known for uid in units) else 'MISSED'


def _times(mod_rec: Recording, labels: list, runs: set, known: set) -> list:
    """Report lines: the mod build's units and their own seconds by how a replay treats each."""
    spent = collections.Counter()
    for uid, seconds in mod_rec.spent.items():
        spent['outside any unit' if labels[uid][0] == 'process' else 'rerun' if labels[uid] in runs
              else 'new unit' if labels[uid] not in known else 'replayed'] += seconds
    count = collections.Counter('rerun' if label in runs else 'new unit' if label not in known else 'replayed'
                                for label in labels if label[0] != 'process')
    return [f'  units {sum(count.values())}: ' + ', '.join(f'{k} {v}' for k, v in count.most_common()),
            '  seconds: ' + ', '.join(f'{k} {v:.0f}' for k, v in spent.most_common())]


def replay_check(game_rec: Recording, game: Path, mod: Path, mod_rec: Recording, plugin: Path, limit: int) -> list:
    """Report lines: each record of the mod's built `plugin` by how a replay would make it (_status from the units
    `mod_rec` saw write it); MISSED records would be lost or the game's, so the replayed plugin would differ."""
    game_labels, labels = game_rec.labels(), mod_rec.labels((mod.name, game.name))
    runs = {game_labels[uid] for uid in rerun(game_rec, game, changes(game, mod))} | _moved_into(game, mod)
    known = set(game_labels)
    writers = collections.defaultdict(set)
    for uid, fid in zip(mod_rec.writes['unit'].tolist(), mod_rec.writes['fid'].tolist()):
        writers[fid].add(uid)
    tally, missed = collections.Counter(), []
    for rec, _ in walk(plugin.read_bytes(), bodies=()):
        verdict = mod_rec.verdicts.get(rec.form_id)
        status = ("the master's copy, heading kept records" if verdict is not None and verdict not in KEPT
                  else _status(writers.get(rec.form_id, set()), labels, runs, known))
        tally[status] += 1
        if status == 'MISSED':
            names = sorted({' '.join(labels[uid]) for uid in writers[rec.form_id]})
            missed.append(f'    {rec.sig.decode()} {rec.form_id:08X} '
                          f'({mod_rec.verdicts.get(rec.form_id, "own")}): {"; ".join(names)[:160]}')
    return ([f'\n== replay check: {plugin.name} ==', f'  game units rerun: {len(runs)} of {len(known)}',
             '  plugin records: ' + ', '.join(f'{k} {v}' for k, v in tally.most_common())]
            + _times(mod_rec, labels, runs, known) + missed[:limit])


def main() -> None:
    """Print the recording's summary and journal size, then each mod's report and replay check."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--log', required=True, type=Path, help="The recording's folder (its <pid>.reads files)")
    parser.add_argument('--game', type=Path, help='The export the recording was built from')
    parser.add_argument('--mod', type=Path, action='append', default=[], help="A mod plugin's export folder")
    parser.add_argument('--check', nargs=3, type=Path, action='append', default=[],
                        metavar=('MOD_EXPORT', 'MOD_LOG', 'MOD_PLUGIN'),
                        help="A mod's export, the recording of its own build and the plugin that build wrote")
    parser.add_argument('--limit', type=int, default=20, help='Groups and places printed per list')
    args = parser.parse_args()
    if (args.mod or args.check) and not args.game:
        parser.error('--mod and --check need --game')
    sys.stdout.reconfigure(encoding='utf-8')
    recording = Recording(args.log)
    print('\n'.join(summary(recording, args.limit) + journal_size(recording)))
    for mod in args.mod:
        print('\n'.join(mod_report(recording, args.game, mod, args.limit)))
    for mod, log, plugin in args.check:
        print('\n'.join(replay_check(recording, args.game, mod, Recording(log), plugin, args.limit)))


if __name__ == '__main__':
    main()
