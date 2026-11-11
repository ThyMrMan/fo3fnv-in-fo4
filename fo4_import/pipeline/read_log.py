"""Read recording, the spike of the replay plan: which export records each maker call (a unit) of a build reads.

    py -3.14 -m fo4_import.pipeline.read_log [--no-assets] <the arguments of fo4_import.pipeline.run>

A normal build never imports this module. The command binds the recorder over the build's readers at run time,
runs the build, and writes `output/fo4_cache/read_log/<plugin>/<pid>.reads` per process, which
tools/audit/read_log_report.py reads: reads, the records each unit packed, drop_unchanged's verdicts, unit times.
F3NV_READ_LOG_FIELDS=0 logs records without their fields. --no-assets leaves out the file-only steps.

See: docs/fork/fo4_build_speed.md#replay-spike
See: docs/fork/fo4_plugin_layout.md#incremental
"""

import argparse
import array
import atexit
import collections
import contextlib
import functools
import hashlib
import importlib
import inspect
import json
import os
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np

from fo4_import.base import install as source_install
from fo4_import.base import master_overrides
from fo4_import.pipeline import export_index, ran_code, run, stage_timer
from fo4_import.pipeline.code_identity import SEP, relative
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.rig import anim_info
from fo4_import.spike import build_finish
from tes5_import.base import text_reader, writer

#: Environment of a recorded run: the log folder (a worker process records when set), its run id, its watched roots.
ENV, RUN_ENV, ROOTS_ENV = 'F3NV_READ_LOG', 'F3NV_READ_LOG_RUN', 'F3NV_READ_LOG_ROOTS'
#: Environment: '0' logs which records are read, not which fields.
FIELDS_ENV = 'F3NV_READ_LOG_FIELDS'
SUFFIX, FORMAT = '.reads', 2
#: This module's sys.monitoring tool id (ran_code holds 4) and name.
TOOL, NAME = 3, 'f3nv read log'
#: This file as ran_code names it: a recorder, kept out of every code record from its import on.
SELF = 'fo4_import/pipeline/read_log.py'
#: A read is `record number << SHIFT | field id`; field ids 0 and 1 are ANY (some field) and WHOLE (every field).
SHIFT, ANY, WHOLE = 20, '?', '*'
#: A unit's run reading this many (record, field) pairs keeps them as one sorted array shared by equal runs.
BIG = 4096
#: A running unit holding this many reads when it asks another unit keeps them as such an array, its set emptied.
FLUSH = 1 << 20
#: Makers run as units: (module, qualified name, unit kind, the started frame's values naming the unit).
UNITS = (
    ('fo4_import.spike.cell', 'CellBuilder.base', 'base', ('fnv_fid',)),
    ('fo4_import.spike.cell', 'CellBuilder.load_door', 'load door', ('fnv_fid',)),
    ('fo4_import.spike.cell', '_placed', 'cell refs', ('refs.0.ParentCELL',)),
    ('fo4_import.spike.cell', '_interior', 'cell', ('cell.FormID',)),
    ('fo4_import.spike.items', 'Items.item', 'item', ('fnv_fid',)),
    ('fo4_import.spike.npcs', 'Npcs.base', 'npc', ('fnv',)),
    ('fo4_import.spike.npcs', 'Npcs._creature', 'creature', ('fnv',)),
    ('fo4_import.spike.npcs', 'Npcs._list', 'npc list', ('fnv',)),
    ('fo4_import.spike.npcs', 'Npcs._actor', 'actor', ('ref.FormID',)),
    ('fo4_import.spike.creatures', 'Creatures.base', 'creature base', ('fnv',)),
    ('fo4_import.spike.exterior', 'Exterior.__init__', 'world scope', ('world',)),
    ('fo4_import.spike.exterior', 'Exterior.group', 'world', ('self.world.EditorID',)),
    ('fo4_import.spike.exterior', 'Exterior._land', 'land', ('rec.ParentCELL',)),
    ('fo4_import.spike.say_topics', 'SayTopics.build', 'quest topics', ('quest.FormID',)),
    ('fo4_import.spike.say_topics', 'SayTopics.info', 'info', ('rec.FormID',)),
    ('fo4_import.spike.conversation', 'Conversations.__init__', 'quest lines', ('quest.FormID',)),
    ('fo4_import.spike.conversation', 'Conversations.talk', 'talk', ('self.quest.FormID', 'prop')),
    ('fo4_import.spike.quest', 'quest_record', 'quest', ('rec.FormID',)),
    ('fo4_import.spike.packages', 'Packages.package', 'package', ('fnv',)),
    ('fo4_import.spike.packages', 'Packages.for_npc', 'packages of', ('npc.FormID',)),
    ('fo4_import.pipeline.run', 'scope_models', 'stage', 'scope models'),
    ('fo4_import.pipeline.run', 'exteriors', 'stage', 'world names'),
    ('fo4_import.pipeline.build_steps', 'convert_scripts', 'stage', 'script conversion'),
)
#: Packages whose classes' `__init__` taking `builder` or `export_dir` are units of kind init.
MAKER_PACKAGES = ('fo4_import.spike.', 'fo4_import.casino.')
#: Packages whose module-level functools.cache functions are units of kind memo; these of them are left alone.
MEMO_PACKAGES, MEMO_SKIPPED = ('fo4_import.',), ('fo4_import.pipeline.',)
#: export_index's caches holding parsed records, emptied when recording starts and stops.
RECORD_CACHES = ('_parsed', '_layered', 'master_records')
#: build_finish steps that write files only (meshes, LOD, sounds, archives, compiled scripts): left out by --no-assets.
ASSET_STEPS = ('_collision', '_object_lod', '_assets', '_compile', '_gun_anim_text', '_main_archive')
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_CACHED = type(functools.cache(len))
_TIMED = stage_timer.timed('')(len).__code__
ran_code.RECORDERS = ran_code.RECORDERS | {SELF}


class _Null:
    """The running read set while nothing records."""

    def add(self, code) -> None:
        """Drop `code`."""


class FieldIds(dict):
    """{field name: id}, a name numbered on first use; past 1 << SHIFT names a new one is ANY."""

    def __missing__(self, key) -> int:
        """Number `key`, one thread at a time."""
        with _LOCK:
            if not _HAS(self, key):
                dict.__setitem__(self, key, len(self) if len(self) < 1 << SHIFT else 0)
            return _GETITEM(self, key)


class Log:
    """One process's recording: files and units numbered, each unit's reads, edges and questions."""

    def __init__(self):
        """Nothing recorded; unit 0 is the process, file 0 a record of no export file."""
        self.on, self.thread, self.quiet, self.folder = False, threading.get_ident(), 0, None
        self.rec, self.roots, self.hooked = Rec, (), False
        self.files, self.file_ids, self.top = [['', '', 0, 1, '']], {}, 1
        self.units, self.unit_ids = [('process', str(os.getpid()))], {}
        self.stack, self.codes, self.live = [0], [None], [set()]
        self.stores, self.sets, self.set_ids, self.bigs = {}, [], {}, set()
        self.edges, self.asked, self.names, self.call_names = set(), set(), {}, {}
        self.sites, self.errors = collections.Counter(), collections.Counter()
        self.unit_codes, self.call_codes, self.where = {}, {}, {}
        self.patched, self.missing, self.environ = [], [], {}
        self.writes, self.verdicts, self.spent = [], {}, collections.Counter()
        self.clock = [[time.perf_counter(), 0.0]]

    def reset(self) -> None:
        """Forget everything recorded; the audit hook stays known."""
        hooked = self.hooked
        self.__init__()
        self.hooked = hooked


_NULL, _LOCK = _Null(), threading.Lock()
_CUR = _NULL
_FID = FieldIds({ANY: 0, WHOLE: 1})
_GETITEM, _GET, _HAS, _ITEMS = dict.__getitem__, dict.get, dict.__contains__, dict.items


def _whole(rec, op: str) -> None:
    """Log every field of `rec` read by `op`, counted by the place that called the Rec method."""
    if _CUR is not _NULL:
        _CUR.add(rec.kf | 1)
        frame = sys._getframe(2)
        LOG.sites[op, frame.f_code, frame.f_lineno] += 1


class Rec(dict):
    """An export record logging each read to the running unit: the field, or WHOLE for a read of them all
    (iteration, a copy, repr, pickling). Copies are plain dicts, as is a Rec unpickled; its repr is a dict's."""

    __slots__ = ('kf',)

    def __new__(cls, *args, **kwargs):
        """An empty record of no export file (file 0)."""
        self = dict.__new__(cls)
        self.kf = 0
        return self

    def __getitem__(self, key):
        _CUR.add(self.kf + _FID[key])
        return _GETITEM(self, key)

    def get(self, key, default=None):
        _CUR.add(self.kf + _FID[key])
        return _GET(self, key, default)

    def __contains__(self, key):
        _CUR.add(self.kf + _FID[key])
        return _HAS(self, key)

    def __iter__(self):
        _whole(self, 'iter')
        return dict.__iter__(self)

    def keys(self):
        _whole(self, 'keys')
        return dict.keys(self)

    def items(self):
        _whole(self, 'items')
        return _ITEMS(self)

    def values(self):
        _whole(self, 'values')
        return dict.values(self)

    def copy(self):
        _whole(self, 'copy')
        return dict(_ITEMS(self))

    def __or__(self, other):
        _whole(self, 'or')
        return dict(_ITEMS(self)) | other

    def __ror__(self, other):
        """`other | self`, a plain dict."""
        _whole(self, 'or')
        out = dict(other)
        out.update(_ITEMS(self))
        return out

    def __repr__(self):
        _whole(self, 'repr')
        return dict.__repr__(self)

    def __reduce__(self):
        _whole(self, 'pickle')
        return dict, (dict(_ITEMS(self)),)


class CoarseRec(Rec):
    """A Rec logging which record is read, not which field."""

    __slots__ = ()

    def __getitem__(self, key):
        _CUR.add(self.kf)
        return _GETITEM(self, key)

    def get(self, key, default=None):
        _CUR.add(self.kf)
        return _GET(self, key, default)

    def __contains__(self, key):
        _CUR.add(self.kf)
        return _HAS(self, key)


def _writer(name: str, reads: bool):
    """dict's method `name` for Rec: a call is counted by its place as a write (`reads`: and logged as ANY)."""
    plain = getattr(dict, name)

    def write(self, *args, **kwargs):
        """Count the write, then make it."""
        if _CUR is not _NULL:
            frame = sys._getframe(1)
            LOG.sites[f'write {name}', frame.f_code, frame.f_lineno] += 1
            _CUR.add(self.kf) if reads else None
        return plain(self, *args, **kwargs)
    return write


for _name in ('__setitem__', '__delitem__', '__ior__', 'update', 'clear', 'popitem'):
    setattr(Rec, _name, _writer(_name, False))
for _name in ('pop', 'setdefault'):
    setattr(Rec, _name, _writer(_name, True))
LOG = Log()


@contextlib.contextmanager
def quiet():
    """Log no read inside the block (the export index's own passes over a type)."""
    global _CUR
    LOG.quiet += 1
    _CUR = _NULL
    try:
        yield
    finally:
        LOG.quiet -= 1
        _CUR = LOG.live[-1] if LOG.on and not LOG.quiet else _NULL


def _file(path: str, count: int) -> int:
    """The first record number of export file `path` holding `count` records (numbered once)."""
    key = (os.path.normcase(os.path.abspath(path)), count)
    if key not in LOG.file_ids:
        LOG.file_ids[key] = LOG.top
        LOG.files.append([Path(path).parent.name, Path(path).stem, LOG.top, count, key[0]])
        LOG.top += count
    return LOG.file_ids[key]


def _records(path, plain: list) -> list:
    """`plain`, the records parsed from export file `path`, as Recs numbered by file and position."""
    base, out = _file(str(path), len(plain)), []
    for at, rec in enumerate(plain):
        made = LOG.rec(rec)
        made.kf = (base + at) << SHIFT
        out.append(made)
    return out


def _same(plain: dict, source) -> dict:
    """`plain`, a changed copy of record `source`, as a Rec of the same number (itself when `source` is no Rec)."""
    if not isinstance(source, Rec):
        return plain
    made = type(source)(plain)
    made.kf = source.kf
    return made


def _parse(original):
    """text_reader.parse_export_file giving Recs."""
    def parse_export_file(filepath):
        return _records(filepath, original(filepath))
    return parse_export_file


def _renumber(original):
    """master_space.renumber_record whose renumbered copy keeps its record's number."""
    def renumber_record(rec, mapping, game):
        """`rec` renumbered, unlogged."""
        with quiet():
            out = original(rec, mapping, game)
        return _same(out, rec)
    return renumber_record


def _layers(original):
    """export_index._layered, unlogged, its disabled copies of deleted master references numbered as the master's
    record of that FormID (the newest not deleted)."""
    @functools.cache
    def layered(export_dir, sig):
        """The layered type, every record a Rec."""
        with quiet():
            out = original(export_dir, sig)
            if all(isinstance(rec, Rec) for rec in out):
                return out
            source = {rec['FormID']: rec for folder in export_index.export_masters(export_dir)
                      for rec in export_index.master_records(export_dir, folder, sig)
                      if not int(rec.get('RecordFlags', '0')) & export_index.DELETED}
            return tuple(rec if isinstance(rec, Rec) else _same(rec, source.get(rec['FormID'])) for rec in out)
    return layered


def _name(*parts) -> int:
    """The number of the question `parts` (tab-joined), new on first sight."""
    text = '\t'.join(parts)
    found = LOG.names.get(text)
    if found is None:
        with _LOCK:
            found = LOG.names.setdefault(text, len(LOG.names))
    return found


def _ask(*parts) -> None:
    """Log the running unit asking the question `parts`."""
    LOG.asked.add(LOG.stack[-1] << 32 | _name(*parts))


def _place(code, line: int) -> str:
    """`<repo file>:<line>` of `line` in `code`."""
    return f'{relative(code.co_filename) or code.co_filename}:{line}'


def _walk(original):
    """install's walk, each walk logged with its signatures, the plugin's size and the place outside install."""
    def walk(raw, *sigs, **kwargs):
        """Log the walk, then make it."""
        if LOG.on and threading.get_ident() == LOG.thread:
            frame = sys._getframe(1)
            while frame.f_back is not None and frame.f_globals is vars(source_install):
                frame = frame.f_back
            wanted = ','.join(sorted(sig.decode('latin-1') if isinstance(sig, bytes) else str(sig)
                                     for sig in sigs)) or WHOLE
            _ask('walk', wanted, str(len(raw)), _place(frame.f_code, frame.f_lineno))
        return original(raw, *sigs, **kwargs)
    return walk


def _layered_path(original):
    """Layered.path, the path it answers logged."""
    def path(self):
        """The resolved path, logged."""
        found = original(self)
        if LOG.on:
            _ask('asset', str(found))
        return found
    return path


def _packed(original):
    """writer.pack_record, each record packed logged to the running unit (unit 0 off the main thread): (unit,
    FormID, signature, size, a 64-bit hash of its bytes). Packing, not adding: a group is added after its units."""
    def pack_record(*args, **kwargs):
        """The record, logged."""
        blob = original(*args, **kwargs)
        if LOG.on:
            uid = LOG.stack[-1] if threading.get_ident() == LOG.thread else 0
            digest = hashlib.blake2b(blob, digest_size=8).digest()
            LOG.writes.append((uid, struct.unpack_from('<I', blob, 12)[0], struct.unpack_from('<I', blob)[0],
                               len(blob), int.from_bytes(digest, 'little', signed=True)))
        return blob
    return pack_record


def _verdict(original):
    """master_overrides._kind, each master record's verdict kept by FormID (the last one judged)."""
    def kind(sig, fid, record, kept, context):
        """The verdict, logged."""
        out = original(sig, fid, record, kept, context)
        LOG.verdicts[fid] = out[0]
        return out
    return kind


def _skipped(*_args, **_kwargs) -> None:
    """An asset step left out (no_assets)."""


def _not_needed(*_args, **_kwargs) -> bool:
    """No Creation Kit run (no_assets)."""
    return False


def no_assets() -> None:
    """Leave out ASSET_STEPS and the Creation Kit (it reads MO2)."""
    for name in ASSET_STEPS:
        _set(build_finish, name, _skipped)
    _set(anim_info, 'needed', _not_needed)


def _audit(event: str, args: tuple) -> None:
    """The audit hook: a file under a watched root opened for reading is logged to the running unit."""
    if event != 'open' or not LOG.on or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    mode, flags = args[1], args[2]
    if set(mode) & set('wax+') if isinstance(mode, str) else (flags or 0) & _WRITE_FLAGS:
        return
    path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
    if path.startswith(LOG.roots):
        _ask('open', path)


def _unit(kind: str, key) -> int:
    """The number of unit (`kind`, `key`), new on first sight."""
    found = LOG.unit_ids.get((kind, key))
    if found is None:
        found = LOG.unit_ids[kind, key] = len(LOG.units)
        LOG.units.append((kind, key))
    return found


def _fold(uid: int, reads) -> None:
    """Keep `reads` (codes) of unit `uid`: few in its array, BIG or more as a sorted array kept once per content."""
    if len(reads) < BIG:
        store = LOG.stores.setdefault(uid, array.array('q'))
        store.extend(reads)
        if len(store) >= 16 * BIG:
            _fold(uid, set(LOG.stores.pop(uid)))
        return
    codes = np.fromiter(reads, dtype=np.int64, count=len(reads))
    codes.sort()
    digest = hashlib.blake2b(codes.tobytes(), digest_size=16).digest()
    if digest not in LOG.set_ids:
        LOG.set_ids[digest] = len(LOG.sets)
        LOG.sets.append(codes)
    LOG.bigs.add(uid << 32 | LOG.set_ids[digest])


def _enter(uid: int, code=None) -> int:
    """Start unit `uid`, asked by the running one, as the running unit; the stack depth to _exit_to()."""
    global _CUR
    if len(LOG.live[-1]) >= FLUSH:
        _fold(LOG.stack[-1], LOG.live[-1])
        LOG.live[-1].clear()
    LOG.edges.add(LOG.stack[-1] << 32 | uid)
    LOG.stack.append(uid)
    LOG.codes.append(code)
    LOG.live.append(set())
    LOG.clock.append([time.perf_counter(), 0.0])
    if not LOG.quiet:
        _CUR = LOG.live[-1]
    return len(LOG.stack) - 1


def _exit_to(depth: int) -> None:
    """End the units at stack `depth` and above, keeping their reads and own time (less the units they asked);
    the unit below runs again."""
    global _CUR
    while len(LOG.stack) > max(depth, 1):
        uid, reads = LOG.stack.pop(), LOG.live.pop()
        LOG.codes.pop()
        start, inner = LOG.clock.pop()
        took = time.perf_counter() - start
        LOG.spent[uid] += took - inner
        LOG.clock[-1][1] += took
        if reads:
            _fold(uid, reads)
    if not LOG.quiet:
        _CUR = LOG.live[-1]


def _part(value, name: str):
    """`value`'s item (a dict's key, read unlogged; a sequence's index) or attribute `name`; None without."""
    if isinstance(value, dict):
        return _GET(value, name)
    if name.isdigit():
        return value[int(name)] if len(value) > int(name) else None
    return getattr(value, name, None)


def _text(value) -> str:
    """A short label of a unit key's part: a FormID in hex, a path's name, a string, else its type."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f'{value:08X}'
    if isinstance(value, str):
        return value[:80]
    return value.name if isinstance(value, Path) else type(value).__name__ if value is not None else '-'


def _key(local, paths: tuple) -> str:
    """The unit key that frame paths `paths` (`a.b.0.c`) name in `local`."""
    parts = (functools.reduce(_part, path.split('.')[1:], local[path.split('.')[0]]) for path in paths)
    return ' '.join(_text(part) for part in parts)


def _type_asked(code, frame) -> None:
    """Log the running unit asking export_records/own_records (`frame`) for a whole type, with the caller's place;
    the export index's own calls are left out."""
    caller = frame.f_back
    if LOG.quiet or caller.f_code.co_filename == code.co_filename:
        return
    local = frame.f_locals
    key = (code, caller.f_code, caller.f_lineno, local['sig'], str(local['export_dir']))
    if key not in LOG.call_names:
        LOG.call_names[key] = _name('records', code.co_name, Path(key[4]).name, key[3], _place(key[1], key[2]))
    LOG.asked.add(LOG.stack[-1] << 32 | LOG.call_names[key])


def _started(code, _offset) -> None:
    """sys.monitoring PY_START and PY_RESUME of a watched function: its unit starts, keyed from its frame, or a
    whole type is asked for. An error is counted, never raised into the build."""
    if threading.get_ident() != LOG.thread:
        return
    try:
        frame, spec = sys._getframe(1), LOG.unit_codes.get(code)
        if spec is None:
            _type_asked(code, frame)
        else:
            _enter(_unit(spec[0], spec[1] if isinstance(spec[1], str) else _key(frame.f_locals, spec[1])), code)
    except Exception as exc:
        LOG.errors[f'{code.co_qualname}: {exc!r}'[:200]] += 1


def _left(code, _offset, _value) -> None:
    """PY_RETURN, PY_YIELD, PY_UNWIND: a watched function's unit ends."""
    if code in LOG.unit_codes and threading.get_ident() == LOG.thread and code in LOG.codes:
        _exit_to(len(LOG.codes) - 1 - LOG.codes[::-1].index(code))


def _memo(cached, name: str):
    """`cached` (a functools.cache function) with each call a unit of its arguments, so a hit is an edge too."""
    @functools.wraps(cached)
    def asked(*args, **kwargs):
        """The cached value, asked for by the running unit."""
        if not LOG.on or threading.get_ident() != LOG.thread:
            return cached(*args, **kwargs)
        depth = _enter(_unit('memo', (name, args, tuple(kwargs.items()))))
        try:
            return cached(*args, **kwargs)
        finally:
            _exit_to(depth)
    asked.__wrapped__ = getattr(cached, '__wrapped__', cached)
    asked.cache_clear, asked.cache_info, asked.cache_parameters = (
        cached.cache_clear, cached.cache_info, cached.cache_parameters)
    return asked


def _set(owner, name: str, value) -> None:
    """Bind `owner`.`name` to `value`, remembering what it was (uninstall)."""
    LOG.patched.append((owner, name, getattr(owner, name)))
    setattr(owner, name, value)


def _repo_modules(prefixes: tuple = ('',), skipped: tuple = ()) -> list:
    """The loaded repo modules named under `prefixes` and not under `skipped`."""
    return [module for name, module in list(sys.modules.items())
            if name.startswith(prefixes) and not (skipped and name.startswith(skipped))
            and relative(getattr(module, '__file__', None) or '')]


def _rebind(swaps: dict) -> None:
    """Bind every loaded repo module's global that is an object of `swaps` ({id: (object, stand-in)}) to its
    stand-in: a name imported from its module is a binding of its own."""
    for module in _repo_modules():
        for name, value in list(vars(module).items()):
            if id(value) in swaps and swaps[id(value)][0] is value:
                _set(module, name, swaps[id(value)][1])


def _memos() -> dict:
    """_rebind() swaps of every module-level functools.cache function of MEMO_PACKAGES."""
    swaps = {}
    for module in _repo_modules(MEMO_PACKAGES, MEMO_SKIPPED):
        for name, value in list(vars(module).items()):
            if isinstance(value, _CACHED) and getattr(value, '__module__', '') == module.__name__:
                swaps[id(value)] = (value, _memo(value, f'{module.__name__.rsplit(".", 1)[-1]}.{name}'))
    return swaps


def _watch(code, kind: str, key) -> None:
    """Run `code` as a unit of `kind` keyed `key`, unless it is one."""
    if code not in LOG.unit_codes:
        LOG.unit_codes[code] = (kind, key)
        LOG.where.setdefault(kind, set()).add(_place(code, code.co_firstlineno))


def _watched() -> None:
    """Fill LOG.unit_codes from the loaded modules: UNITS (one not found goes to LOG.missing), every
    stage_timer.timed function as a stage, and every MAKER_PACKAGES class's `__init__` that takes `builder` or
    `export_dir` as an init."""
    for module, qualname, kind, key in UNITS:
        found = functools.reduce(lambda owner, part: getattr(owner, part, None), qualname.split('.'),
                                 sys.modules.get(module))
        code = getattr(inspect.unwrap(found), '__code__', None) if found is not None else None
        _watch(code, kind, key) if code else LOG.missing.append(f'{module}.{qualname}')
    for module in _repo_modules(('fo4_import.',)):
        for value in list(vars(module).values()):
            if getattr(value, '__code__', None) is _TIMED and value.__module__ == module.__name__:
                stage = value.__closure__[_TIMED.co_freevars.index('name')].cell_contents
                _watch(value.__wrapped__.__code__, 'stage', stage)
    for module in _repo_modules(MAKER_PACKAGES):
        for value in list(vars(module).values()):
            code = getattr(vars(value).get('__init__'), '__code__', None) if isinstance(value, type) else None
            if code and value.__module__ == module.__name__ and {'builder', 'export_dir'} & set(
                    code.co_varnames[:code.co_argcount]):
                _watch(code, 'init', f'{module.__name__.rsplit(".", 1)[-1]}.{value.__qualname__}')


def _monitor(on: bool) -> None:
    """Turn sys.monitoring for the watched functions on or off: starts and ends of units (unwinds process-wide,
    as they are no local event) and starts of the whole-type readers."""
    events = sys.monitoring.events
    if on:
        sys.monitoring.use_tool_id(TOOL, NAME)
    for event, callback in ((events.PY_START, _started), (events.PY_RESUME, _started), (events.PY_RETURN, _left),
                            (events.PY_YIELD, _left), (events.PY_UNWIND, _left)):
        sys.monitoring.register_callback(TOOL, event, callback if on else None)
    unit = events.PY_START | events.PY_RESUME | events.PY_RETURN | events.PY_YIELD
    for code in LOG.unit_codes:
        sys.monitoring.set_local_events(TOOL, code, unit if on else 0)
    for code in LOG.call_codes:
        sys.monitoring.set_local_events(TOOL, code, events.PY_START if on else 0)
    sys.monitoring.set_events(TOOL, events.PY_UNWIND if on else 0)
    if not on:
        sys.monitoring.free_tool_id(TOOL)


def _clear_records() -> None:
    """Empty the export index's record caches (parsed again on use)."""
    for name in RECORD_CACHES:
        getattr(export_index, name).cache_clear()


def _roots(folders) -> tuple:
    """Case-folded prefixes of `folders`, as named and as resolved."""
    found = {os.path.normcase(str(form)) for folder in folders if folder
             for form in (os.path.abspath(folder), os.path.realpath(folder))}
    return tuple(sorted(root.rstrip(os.sep) + os.sep for root in found))


def install(folder, roots=(), fields: 'bool | None' = None) -> None:
    """Record this process, and each worker process it starts, into `folder`: file opens under `roots` (the
    export root, the scripts folder), fields too unless `fields` is False (None: FIELDS_ENV). Records parsed
    earlier are parsed again."""
    global _CUR
    if LOG.on:
        return
    if sys.monitoring.get_tool(TOOL) is not None:
        raise SystemExit(f'read log: sys.monitoring tool {TOOL} is taken by {sys.monitoring.get_tool(TOOL)}')
    LOG.reset()
    _FID.clear()
    _FID.update({ANY: 0, WHOLE: 1})
    fields = os.environ.get(FIELDS_ENV, '1') != '0' if fields is None else fields
    LOG.folder, LOG.roots, LOG.rec = Path(folder), _roots(roots), Rec if fields else CoarseRec
    LOG.environ = {name: os.environ.get(name) for name in (ENV, RUN_ENV, ROOTS_ENV, FIELDS_ENV)}
    os.environ.update({ENV: str(folder), ROOTS_ENV: os.pathsep.join(LOG.roots), FIELDS_ENV: '1' if fields else '0'})
    os.environ.setdefault(RUN_ENV, str(time.time_ns()))
    _clear_records()
    _watched()
    LOG.call_codes = {fn.__code__: fn.__name__ for fn in (export_index.export_records, export_index.own_records)}
    _rebind({id(text_reader.parse_export_file): (text_reader.parse_export_file,
                                                 _parse(text_reader.parse_export_file)),
             id(writer.pack_record): (writer.pack_record, _packed(writer.pack_record)), **_memos()})
    _set(export_index, 'renumber_record', _renumber(export_index.renumber_record))
    _set(export_index, '_layered', _layers(getattr(export_index, '_layered')))
    _set(source_install, 'walk', _walk(source_install.walk))
    _set(export_index.Layered, 'path', _layered_path(export_index.Layered.path))
    _set(master_overrides, '_kind', _verdict(getattr(master_overrides, '_kind')))
    ran_code.RAN.difference_update([key for key in ran_code.RAN if key.startswith(SELF + SEP)])
    _monitor(True)
    if not LOG.hooked:
        sys.addaudithook(_audit)
        LOG.hooked = True
    LOG.on, _CUR = True, LOG.live[-1]


def uninstall() -> None:
    """Stop recording; put back every name and environment variable install() set (the audit hook stays, idle)."""
    global _CUR
    if not LOG.on:
        return
    LOG.on, _CUR = False, _NULL
    _monitor(False)
    for owner, name, value in reversed(LOG.patched):
        setattr(owner, name, value)
    LOG.patched.clear()
    _clear_records()
    for name, value in LOG.environ.items():
        os.environ.pop(name, None) if value is None else os.environ.update({name: value})


def resume() -> None:
    """In a worker of a recorded run (ENV set), record too; logged at exit."""
    if os.environ.get(ENV) and not LOG.on:
        install(os.environ[ENV], [root for root in os.environ.get(ROOTS_ENV, '').split(os.pathsep) if root])
        atexit.register(lambda: dump() if len(LOG.files) > 1 or LOG.asked else None)


def _small() -> tuple:
    """(unit, code) arrays of the reads kept in units' own arrays, sorted, each pair once."""
    held = [(uid, np.frombuffer(store, dtype=np.int64)) for uid, store in LOG.stores.items() if len(store)]
    if not held:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    units = np.repeat(np.array([uid for uid, _ in held], dtype=np.int64), [len(codes) for _, codes in held])
    codes = np.concatenate([codes for _, codes in held])
    order = np.lexsort((codes, units))
    units, codes = units[order], codes[order]
    keep = np.ones(len(codes), dtype=bool)
    keep[1:] = (units[1:] != units[:-1]) | (codes[1:] != codes[:-1])
    return units[keep], codes[keep]


def _pairs(packed: set) -> tuple:
    """The (high, low) 32-bit halves of each of `packed`, as arrays in sorted order."""
    both = np.sort(np.fromiter(packed, dtype=np.int64, count=len(packed)))
    return (both >> 32).astype(np.uint32), (both & 0xFFFFFFFF).astype(np.uint32)


def _label(key) -> str:
    """A unit key as text: a memo's function and arguments, else the key."""
    if isinstance(key, str):
        return key
    name, args, kwargs = key
    return f'{name}({", ".join([*map(_text, args), *(f"{k}={_text(v)}" for k, v in kwargs)])})'


def _question(text: str) -> str:
    """Question `text` with its path, when under a watched root, cut to the part below the root."""
    kind, _, rest = text.partition('\t')
    if kind not in ('open', 'asset'):
        return text
    path = os.path.normcase(rest)
    root = next((root for root in LOG.roots if path.startswith(root)), '')
    return f'{kind}\t{path[len(root):]}'


def _meta() -> dict:
    """The log's tables as JSON-ready data: files, field names, questions, units, places and counts."""
    fields = [ANY] * len(_FID)
    for name, number in _FID.items():
        fields[number] = str(name) if number or name == ANY else fields[0]
    return {'format': FORMAT, 'pid': os.getpid(), 'run': os.environ.get(RUN_ENV, ''), 'argv': sys.argv[1:],
            'fields': LOG.rec is Rec, 'shift': SHIFT, 'files': LOG.files, 'field_names': fields,
            'names': [_question(text) for text in sorted(LOG.names, key=LOG.names.get)],
            'units': [[kind, _label(key)] for kind, key in LOG.units],
            'where': {kind: sorted(places) for kind, places in LOG.where.items()},
            'sites': [[op, _place(code, line), count] for (op, code, line), count in LOG.sites.most_common()],
            'missing': LOG.missing, 'errors': dict(LOG.errors), 'verdicts': sorted(set(LOG.verdicts.values()))}


def _written() -> dict:
    """dump()'s arrays of the records written (write_*: unit, FormID, signature, size, hash), each master record's
    verdict (verdict_fid, verdict_kind: its index in meta's verdicts) and each unit's own seconds (spent_*)."""
    writes = np.array(LOG.writes, dtype=np.int64).reshape(-1, 5)
    kinds = sorted(set(LOG.verdicts.values()))
    LOG.spent[0] = time.perf_counter() - LOG.clock[0][0] - LOG.clock[0][1]
    out = {f'write_{name}': writes[:, i] for i, name in enumerate(('unit', 'fid', 'sig', 'size', 'hash'))}
    out['verdict_fid'] = np.array(list(LOG.verdicts), dtype=np.uint32)
    out['verdict_kind'] = np.array([kinds.index(kind) for kind in LOG.verdicts.values()], dtype=np.uint16)
    out['spent_unit'] = np.array(list(LOG.spent), dtype=np.uint32)
    out['spent_s'] = np.array(list(LOG.spent.values()), dtype=np.float64)
    return out


def dump() -> Path:
    """Write this process's log as `<folder>/<pid>.reads` (numpy arrays, zipped; `meta` is JSON); its path."""
    _exit_to(1)
    if LOG.live[0]:
        _fold(0, set(LOG.live[0]))
        LOG.live[0].clear()
    units, codes = _small()
    starts = np.cumsum([0] + [len(codes) for codes in LOG.sets])
    big = np.concatenate(LOG.sets) if LOG.sets else np.zeros(0, np.int64)
    arrays = {'unit': units.astype(np.uint32), 'rec': (codes >> SHIFT).astype(np.uint32),
              'field': (codes & ((1 << SHIFT) - 1)).astype(np.uint32), 'big_start': starts,
              'big_rec': (big >> SHIFT).astype(np.uint32), 'big_field': (big & ((1 << SHIFT) - 1)).astype(np.uint32)}
    for name, packed in (('big', LOG.bigs), ('edge', LOG.edges), ('asked', LOG.asked)):
        arrays[f'{name}_a'], arrays[f'{name}_b'] = _pairs(packed)
    arrays.update(_written())
    LOG.folder.mkdir(parents=True, exist_ok=True)
    path = LOG.folder / f'{os.getpid()}{SUFFIX}'
    with open(path, 'wb') as out:
        np.savez_compressed(out, meta=np.frombuffer(json.dumps(_meta()).encode(), dtype=np.uint8), **arrays)
    return path


def main() -> None:
    """Run fo4_import.pipeline.run's command recorded; the log is written, and its path printed, even when the
    build fails."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    for flag in ('--export', '--out', '--scripts'):
        parser.add_argument(flag, type=Path)
    parser.add_argument('--no-assets', action='store_true')
    known = parser.parse_known_args()[0]
    sys.argv = [arg for arg in sys.argv if arg != '--no-assets']
    plugin = known.out.name if known.out else 'unnamed'
    os.environ[RUN_ENV] = str(time.time_ns())
    install(os.environ.get(ENV) or ROOT / 'output' / 'fo4_cache' / 'read_log' / plugin,
            [known.export.parent if known.export else None, known.scripts])
    if known.no_assets:
        no_assets()
    try:
        run.main()
    finally:
        print(f'read log: {dump()}')
        if LOG.missing or LOG.errors:
            print(f'read log: units not found {LOG.missing}; errors {dict(LOG.errors)}')
        uninstall()


if __name__ in ('__main__', '__mp_main__'):
    _canonical = importlib.import_module('fo4_import.pipeline.read_log')
    _canonical.main() if __name__ == '__main__' else _canonical.resume()
