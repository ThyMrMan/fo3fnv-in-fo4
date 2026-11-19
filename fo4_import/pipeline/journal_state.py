"""Build state a unit changes, logged as it changes, so a replay can change it again without running the unit.

The containers and maker objects a build shares are adopted: a dict, list, set, Counter or defaultdict becomes its
tracked kind here, an object of our packages gets a tracked class, a tuple is rebuilt of adopted items, and each is
named by its path from a root (`builder.equipment.guns.receivers`, `builder.made[74565]`). While a unit runs
(recording()), every change to an adopted object is logged to it as a primitive op, its values pickled when it is
made: objects made in that op whole, other adopted ones as their names. apply() makes the same changes from the ops,
here or in another build whose names hold the same objects.

See: docs/fork/fo4_plugin_layout.md#journal-state
"""

import collections
import contextlib
import copyreg
import enum
import hashlib
import io
import os
import pickle
import sys
import threading
from pathlib import Path

#: The packages whose objects are adopted (given a tracked class); anything else is a value, pickled whole.
PACKAGES = ('fo4_import.', 'tes5_import.', 'asset_convert.')
#: The running unit's op list (None while no unit records) and the thread it runs on.
RUNNING = [None, None]
#: {name: adopted object} of this process.
NAMES = {}
#: {original class: its tracked subclass}.
_CLASSES = {}
#: The tracked subclasses made (_CLASSES' values).
_OBJECT_KINDS = set()
#: ids of the objects named in the op being logged: pickled whole, not as names.
_FRESH = set()
#: The op of a change whose value could not be pickled: its unit cannot be replayed.
UNJOURNALED = 'unjournaled'
#: A read op, (name, READ, (kind, key, digest found)); kinds: a key's value, held or not, the length, everything.
READ, GET, HAS, LEN, ALL = 'read', 'get', 'has', 'len', 'all'
#: What a read of a key not held finds.
ABSENT = '\0absent'
#: A file a unit wrote: (None, FILE, (path,)) as logged, (None, FILE, (path, digest)) once the unit ends.
FILE = 'file'
#: os.open flags that write.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
#: [True] once watch_files() hooked file writes.
_WATCHING = []
#: Merge rules: an attribute op adding an amount, or keeping the larger value.
ADD, MAX = 'add', 'max'
#: {(class qualified name, attribute): rule} of running totals and high-water marks units update.
MERGES = {('PluginWriter', '_record_count'): ADD, ('PluginWriter', '_derive_collisions'): ADD,
          ('PluginWriter', '_derive_max_probe'): MAX, ('LedgerWriter', 'left_to_masters'): ADD,
          ('CellBuilder', 'top'): MAX}
#: {id: (plain container, its tracked copy)} of the adoption running: one copy for every reference.
_COPIES = {}
#: Qualified names of our classes whose objects are read-only input: left plain, their attributes not walked.
INPUTS = {'Layered'}
#: The recursion limit adoption needs for deep state.
DEPTH = 20000
#: Types whose objects could not be given a tracked class, with counts.
UNTRACKED = collections.Counter()


class Untracked(Exception):
    """A change apply() cannot make: a name no object holds here."""


def _log(target, *change) -> None:
    """Log `change` to adopted `target` in the running unit, its values pickled now; a value that cannot be is
    logged as UNJOURNALED (the unit cannot be replayed)."""
    name, ops = target.__dict__.get('_jname'), RUNNING[0]
    object.__setattr__(target, '_jver', target.__dict__.get('_jver', 0) + 1)
    if ops is not None and name is not None:
        try:
            if threading.get_ident() != RUNNING[1]:
                raise RuntimeError('changed from another thread')
            ops.append((name, change[0], tuple(frozen_value(v) for v in change[1:])))
        except Exception as exc:
            ops.append((None, UNJOURNALED, (f'{name} {change[0]}: {exc!r}'[:300],)))
    _FRESH.clear()


def _audit(event: str, args: tuple) -> None:
    """sys.audit hook: a file the running unit opens to write, renames into place or touches, logged as FILE."""
    ops = RUNNING[0]
    if ops is None or threading.get_ident() != RUNNING[1]:
        return
    if event == 'open':
        path, mode, flags = args
        writing = any(c in mode for c in 'wax+') if isinstance(mode, str) else bool((flags or 0) & _WRITE_FLAGS)
    elif event in ('os.rename', 'os.replace', 'os.utime'):
        path, writing = args[1] if event != 'os.utime' else args[0], True
    else:
        return
    if writing and isinstance(path, (str, bytes, os.PathLike)):
        ops.append((None, FILE, (os.path.abspath(os.fsdecode(path)),)))


def watch_files() -> None:
    """Log the files each unit writes from now on (once per process)."""
    if not _WATCHING:
        sys.addaudithook(_audit)
        _WATCHING.append(True)


def file_digest(path: str) -> 'bytes | None':
    """A 16-byte digest of the file at `path`; None when there is none."""
    try:
        return hashlib.blake2b(Path(path).read_bytes(), digest_size=16).digest()
    except OSError:
        return None


def _read(target, kind: str, key, value) -> None:
    """Log a read of adopted `target` in the running unit: its `kind`, `key` and what it found (digest)."""
    ops = RUNNING[0]
    if ops is None or not type(target)._jreads or threading.get_ident() != RUNNING[1]:
        return
    name = target.__dict__.get('_jname')
    if name is not None:
        ops.append((name, READ, (kind, key, _contents(target) if kind == ALL else digest(value))))


def fingerprint(value):
    """What a read found, comparable across builds: a scalar as itself, an adopted object as its name, a source
    record as its FormID (the export's identity covers its fields), containers by their items (a set's and a dict's
    sorted: their order follows string hashing, which differs per process), else its pickle."""
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if _adopted(value):
        return '@', value._jname
    if _input(value):
        return 'input', value.get('FormID') if isinstance(value, dict) else type(value).__qualname__
    if isinstance(value, (tuple, list)):
        return ('t', *(fingerprint(v) for v in value))
    if isinstance(value, (set, frozenset)):
        return ('s', *sorted(repr(fingerprint(v)) for v in value))
    if isinstance(value, dict):
        return ('d', *sorted(repr((fingerprint(k), fingerprint(v))) for k, v in dict.items(value)))
    try:
        return 'p', hashlib.blake2b(frozen_value(value), digest_size=12).digest()
    except Exception:
        return '?', type(value).__qualname__


def plain_dict(target: dict) -> dict:
    """A plain dict of `target`'s items, read without logging a read."""
    return dict(dict.items(target))


def digest(value) -> bytes:
    """A 12-byte digest of fingerprint(`value`)."""
    return hashlib.blake2b(repr(fingerprint(value)).encode(), digest_size=12).digest()


def _contents(target) -> bytes:
    """digest() of an adopted container's whole contents, as a plain copy; kept until the container changes."""
    kept = target.__dict__.get('_jdigest')
    version = target.__dict__.get('_jver', 0)
    if kept is not None and kept[0] == version:
        return kept[1]
    copy = {dict: plain_dict, list: list.copy, set: set.copy}
    found = digest(next(make(target) for kind, make in copy.items() if isinstance(target, kind)))
    object.__setattr__(target, '_jdigest', (version, found))
    return found


def read_holds(name: str, kind: str, key, found: bytes) -> bool:
    """Whether a logged read of `name` (`kind`, `key`) finds what it `found` in this build's state."""
    target = NAMES.get(name)
    if target is None:
        return False
    if kind == ALL:
        return _contents(target) == found
    if kind == LEN:
        return digest(type(target).__mro__[-2].__len__(target)) == found
    if kind == HAS:
        return digest(type(target).__mro__[-2].__contains__(target, key)) == found
    return digest(dict.get(target, key, ABSENT)) == found


def frozen_value(value) -> bytes:
    """`value` pickled, adopted objects not made in this op as their names."""
    out = io.BytesIO()
    _Pickler(out, protocol=5).dump(value)
    return out.getvalue()


class _Pickler(pickle.Pickler):
    """Pickles an adopted object not made in the op being logged as its name."""

    def persistent_id(self, obj):
        """The name of an adopted object kept from before, else None."""
        if id(obj) in _FRESH or not _adopted(obj):
            return None
        return obj._jname


class _Unpickler(pickle.Unpickler):
    """Unpickles a name as the adopted object it names here."""

    def persistent_load(self, pid):
        """The object `pid` names; Untracked when none does."""
        if pid not in NAMES:
            raise Untracked(pid)
        return NAMES[pid]


def thawed_value(data: bytes):
    """The value pickled in `data`, names as their objects."""
    return _Unpickler(io.BytesIO(data)).load()



class TDict(dict):
    """A dict whose changes are logged as set and del ops, and its reads as reads."""

    _jreads = True

    def __reduce_ex__(self, protocol):
        """Pickled as a plain dict (adopted again where it is put)."""
        return dict, (plain_dict(self),)

    def __getitem__(self, key):
        """The value of `key` (a defaultdict's or Counter's missing one as theirs), read."""
        try:
            value = dict.__getitem__(self, key)
        except KeyError:
            _read(self, GET, key, ABSENT)
            raise
        _read(self, GET, key, value)
        return value

    def get(self, key, default=None):
        """dict.get, read."""
        value = dict.get(self, key, ABSENT)
        _read(self, GET, key, value)
        return default if value is ABSENT else value

    def __contains__(self, key):
        """Whether `key` is held, read."""
        held = dict.__contains__(self, key)
        _read(self, HAS, key, held)
        return held

    def __len__(self):
        """dict.__len__, read."""
        _read(self, LEN, None, dict.__len__(self))
        return dict.__len__(self)

    def __iter__(self):
        """The keys, every item read."""
        _read(self, ALL, None, self)
        return dict.__iter__(self)

    def keys(self):
        """dict.keys, every item read."""
        _read(self, ALL, None, self)
        return dict.keys(self)

    def values(self):
        """dict.values, every item read."""
        _read(self, ALL, None, self)
        return dict.values(self)

    def items(self):
        """dict.items, every item read."""
        _read(self, ALL, None, self)
        return dict.items(self)

    def copy(self):
        """A plain dict of the items, every item read."""
        _read(self, ALL, None, self)
        return plain_dict(self)

    def __setitem__(self, key, value):
        """Set `key`, its value adopted under this dict's name."""
        value = adopt(value, _child(self, f'[{key!r}]'))
        dict.__setitem__(self, key, value)
        _log(self, 'set', key, value)

    def __delitem__(self, key):
        """Delete `key`."""
        dict.__delitem__(self, key)
        _log(self, 'del', key)

    def setdefault(self, key, default=None):
        """dict.setdefault, a missing key set through __setitem__."""
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def update(self, *args, **kwargs):
        """dict.update through __setitem__."""
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def __ior__(self, other):
        """self |= other through update()."""
        self.update(other)
        return self

    def pop(self, key, *default):
        """dict.pop through __delitem__."""
        if key not in self:
            return dict.pop(self, key, *default)
        value = dict.__getitem__(self, key)
        del self[key]
        return value

    def popitem(self):
        """dict.popitem through __delitem__."""
        key = next(reversed(self))
        return key, self.pop(key)

    def clear(self):
        """Delete every key."""
        dict.clear(self)
        _log(self, 'clear')


class TCounter(TDict, collections.Counter):
    """A Counter whose changes are logged as the amounts they add (a replay adds them to the counts it finds), its
    reads not logged (counts report, they decide nothing); update and |= as a Counter's."""

    update, __ior__ = collections.Counter.update, collections.Counter.__ior__
    _jreads = False

    def __getitem__(self, key):
        """The count of `key`, 0 when none."""
        return dict.get(self, key, 0)

    def __setitem__(self, key, value):
        """Set the count of `key`, logged as the amount added."""
        added = value - dict.get(self, key, 0)
        dict.__setitem__(self, key, value)
        _log(self, 'add', key, added)

    def add(self, key, amount) -> None:
        """Add `amount` to the count of `key` (a logged add made again)."""
        self[key] = dict.get(self, key, 0) + amount

    def __reduce_ex__(self, protocol):
        """Pickled as a plain Counter."""
        return collections.Counter, (plain_dict(self),)

    def copy(self):
        """A plain Counter of the same counts."""
        return collections.Counter(self)


class TDefaultDict(TDict, collections.defaultdict):
    """A defaultdict whose missing keys are set through __setitem__."""

    def __reduce_ex__(self, protocol):
        """Pickled as a plain defaultdict."""
        return collections.defaultdict, (self.default_factory, plain_dict(self))

    def copy(self):
        """A plain defaultdict of the same factory and items."""
        return collections.defaultdict(self.default_factory, self)

    def __missing__(self, key):
        """The default factory's value for `key`, set."""
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = self.default_factory()
        return dict.__getitem__(self, key)


class TList(list):
    """A list whose changes are logged as the list method that made them, or its whole contents after a sort."""

    _jreads = True

    def __reduce_ex__(self, protocol):
        """Pickled as a plain list."""
        return list, (list.copy(self),)

    def __getitem__(self, index):
        """list.__getitem__, the whole list read."""
        _read(self, ALL, None, self)
        return list.__getitem__(self, index)

    def __iter__(self):
        """list.__iter__, the whole list read."""
        _read(self, ALL, None, self)
        return list.__iter__(self)

    def __reversed__(self):
        """list.__reversed__, the whole list read."""
        _read(self, ALL, None, self)
        return list.__reversed__(self)

    def __contains__(self, value):
        """list.__contains__, the whole list read."""
        _read(self, ALL, None, self)
        return list.__contains__(self, value)

    def __len__(self):
        """list.__len__, read."""
        _read(self, LEN, None, list.__len__(self))
        return list.__len__(self)

    def index(self, *args):
        """list.index, the whole list read."""
        _read(self, ALL, None, self)
        return list.index(self, *args)

    def count(self, value):
        """list.count, the whole list read."""
        _read(self, ALL, None, self)
        return list.count(self, value)

    def copy(self):
        """A plain copy, the whole list read."""
        _read(self, ALL, None, self)
        return list.copy(self)

    def _did(self, name: str, *args):
        """Log list method `name` with `args`."""
        _log(self, 'list', name, *args)

    def append(self, value):
        """list.append, `value` adopted."""
        value = adopt(value, _child(self, f'[{list.__len__(self)}]'))
        list.append(self, value)
        self._did('append', value)

    def extend(self, values):
        """list.extend through append()."""
        for value in list(values):
            self.append(value)

    def __iadd__(self, values):
        """self += values through extend()."""
        self.extend(values)
        return self

    def insert(self, index, value):
        """list.insert, `value` adopted."""
        value = adopt(value, _child(self, f'[+{index}]'))
        list.insert(self, index, value)
        self._did('insert', index, value)

    def __setitem__(self, index, value):
        """list.__setitem__, a value (not a slice's) adopted."""
        value = value if isinstance(index, slice) else adopt(value, _child(self, f'[{index}]'))
        list.__setitem__(self, index, value)
        self._did('__setitem__', index, value)

    def __delitem__(self, index):
        """list.__delitem__."""
        list.__delitem__(self, index)
        self._did('__delitem__', index)

    def pop(self, index=-1):
        """list.pop."""
        value = list.pop(self, index)
        self._did('pop', index)
        return value

    def remove(self, value):
        """list.remove."""
        list.remove(self, value)
        self._did('remove', value)

    def clear(self):
        """list.clear."""
        list.clear(self)
        self._did('clear')

    def sort(self, *args, **kwargs):
        """list.sort, logged as the sorted contents."""
        list.sort(self, *args, **kwargs)
        self._did('__setitem__', slice(None), list.copy(self))

    def reverse(self):
        """list.reverse."""
        list.reverse(self)
        self._did('reverse')

    def __imul__(self, times):
        """self *= times, logged as the contents."""
        list.__imul__(self, times)
        self._did('__setitem__', slice(None), list.copy(self))
        return self


class TSet(set):
    """A set whose changes are logged as add and discard ops."""

    _jreads = True

    def __reduce_ex__(self, protocol):
        """Pickled as a plain set."""
        return set, (set.copy(self),)

    def __contains__(self, value):
        """Whether `value` is held, read."""
        held = set.__contains__(self, value)
        _read(self, HAS, value, held)
        return held

    def __len__(self):
        """set.__len__, read."""
        _read(self, LEN, None, set.__len__(self))
        return set.__len__(self)

    def __iter__(self):
        """set.__iter__, the whole set read."""
        _read(self, ALL, None, self)
        return set.__iter__(self)

    def _whole(self) -> set:
        """A plain copy, the whole set read."""
        _read(self, ALL, None, self)
        return set.copy(self)

    def copy(self):
        """A plain copy, the whole set read."""
        return self._whole()

    def __or__(self, other):
        """self | other, plain."""
        return self._whole() | other

    def __and__(self, other):
        """self & other, plain."""
        return self._whole() & other

    def __sub__(self, other):
        """self - other, plain."""
        return self._whole() - other

    def __xor__(self, other):
        """self ^ other, plain."""
        return self._whole() ^ other

    def union(self, *others):
        """set.union, plain."""
        return self._whole().union(*others)

    def intersection(self, *others):
        """set.intersection, plain."""
        return self._whole().intersection(*others)

    def difference(self, *others):
        """set.difference, plain."""
        return self._whole().difference(*others)

    def issubset(self, other):
        """set.issubset."""
        return self._whole().issubset(other)

    def issuperset(self, other):
        """set.issuperset."""
        return self._whole().issuperset(other)

    def isdisjoint(self, other):
        """set.isdisjoint."""
        return self._whole().isdisjoint(other)

    def add(self, value):
        """set.add."""
        if not set.__contains__(self, value):
            set.add(self, value)
            _log(self, 'add', value)

    def discard(self, value):
        """set.discard."""
        if set.__contains__(self, value):
            set.discard(self, value)
            _log(self, 'discard', value)

    def remove(self, value):
        """set.remove through discard(), a read of `value`."""
        if value not in self:
            raise KeyError(value)
        self.discard(value)

    def pop(self):
        """set.pop through discard()."""
        value = next(iter(self))
        self.discard(value)
        return value

    def update(self, *others):
        """set.update through add()."""
        for other in others:
            for value in list(other):
                self.add(value)

    def difference_update(self, *others):
        """set.difference_update through discard()."""
        for other in others:
            for value in list(other):
                self.discard(value)

    def intersection_update(self, *others):
        """set.intersection_update through discard()."""
        kept = set.copy(self).intersection(*others)
        for value in [v for v in set.copy(self) if v not in kept]:
            self.discard(value)

    def symmetric_difference_update(self, other):
        """set.symmetric_difference_update through add() and discard()."""
        for value in set(other):
            if value in self:
                self.discard(value)
            else:
                self.add(value)

    def clear(self):
        """set.clear through discard()."""
        for value in set.copy(self):
            self.discard(value)

    def __ior__(self, other):
        """self |= other."""
        self.update(other)
        return self

    def __isub__(self, other):
        """self -= other."""
        self.difference_update(other)
        return self

    def __iand__(self, other):
        """self &= other."""
        self.intersection_update(other)
        return self

    def __ixor__(self, other):
        """self ^= other."""
        self.symmetric_difference_update(other)
        return self


#: (plain type, its tracked kind), most derived first.
_KINDS = ((collections.Counter, TCounter), (collections.defaultdict, TDefaultDict), (dict, TDict), (list, TList),
          (set, TSet))
_CONTAINERS = frozenset(kind for _, kind in _KINDS)



def _merge(owner: type, name: str) -> 'str | None':
    """The MERGES rule of attribute `name` on a class of `owner`'s, else None."""
    return next((MERGES[c.__qualname__, name] for c in owner.__mro__ if (c.__qualname__, name) in MERGES), None)


def _setattr(self, name, value):
    """Set attribute `name`, its value adopted under the object's name, logged; a MERGES attribute already set is
    logged as its rule's op (the amount added, or the value to keep the larger of), none when it did not change."""
    old = self.__dict__.get(name, ABSENT)
    value = adopt(value, _child(self, f'.{name}'))
    super(type(self), self).__setattr__(name, value)
    rule = None if old is ABSENT else _merge(type(self), name)
    if rule is None:
        _log(self, 'attr', name, value)
    elif old != value:
        _log(self, rule, name, value - old if rule == ADD else value)


def _merged(target, rule: str, name: str, value) -> None:
    """Make a MERGES op again: add `value` to attribute `name`, or keep the larger."""
    old = getattr(target, name)
    setattr(target, name, old + value if rule == ADD else max(old, value))


def _delattr(self, name):
    """Delete attribute `name`, logged."""
    super(type(self), self).__delattr__(name)
    _log(self, 'delattr', name)


def rebuilt(cls: type, args: tuple):
    """A new `cls` object by its __new__ with `args` (state follows)."""
    return cls.__new__(cls, *args)


def _reduce_ex(self, protocol):
    """The own class's pickling, made as the own class (so it unpickles plain, adopted where put)."""
    tracked, base = type(self), type(self).__mro__[1]
    out = super(tracked, self).__reduce_ex__(protocol)
    if isinstance(out, tuple) and out[0] is copyreg.__newobj__:
        return (rebuilt, (base, out[1][1:]), *out[2:])
    return out


def _tracked_class(cls: type) -> type:
    """The tracked subclass of `cls`, made once."""
    if cls not in _CLASSES:
        made = type(cls.__name__, (cls,), {'__setattr__': _setattr, '__delattr__': _delattr,
                                           '__reduce_ex__': _reduce_ex, '__module__': cls.__module__,
                                           '__qualname__': cls.__qualname__})
        _CLASSES[cls] = made
        _OBJECT_KINDS.add(made)
    return _CLASSES[cls]


def _ours(value) -> bool:
    """An object of PACKAGES with a __dict__: not a class, enum member or exception."""
    return (not isinstance(value, (type, enum.Enum, BaseException)) and type(value).__module__.startswith(PACKAGES)
            and hasattr(value, '__dict__'))


def _adopted(value) -> bool:
    """`value` is adopted: tracked, and the object its name holds."""
    kind = type(value)
    return (kind in _CONTAINERS or kind in _OBJECT_KINDS) and NAMES.get(value.__dict__.get('_jname')) is value



def _child(parent, suffix: str) -> 'str | None':
    """The name of `parent`'s item or attribute `suffix`; None when `parent` has none."""
    name = parent.__dict__.get('_jname')
    return None if name is None else name + suffix


def _name(target, name: str) -> None:
    """Give `target` its name; made in the op being logged."""
    object.__setattr__(target, '_jname', name)
    NAMES[name] = target
    _FRESH.add(id(target))


def _copied(value, kind: type, name: str):
    """A tracked copy of container `value` named `name`, its items adopted under it; the same copy for every
    reference to `value` while the copies are kept (adopt_root, a unit)."""
    if id(value) in _COPIES:
        return _COPIES[id(value)][1]
    made = kind.__new__(kind)
    if kind is TDefaultDict:
        collections.defaultdict.__init__(made, value.default_factory)
    _COPIES[id(value)] = (value, made)
    _name(made, name)
    if isinstance(value, dict):
        for key, item in dict.items(value):
            dict.__setitem__(made, key, adopt(item, f'{name}[{key!r}]'))
    elif isinstance(value, list):
        list.extend(made, [adopt(item, f'{name}[{i}]') for i, item in enumerate(list.copy(value))])
    else:
        set.update(made, value)
    return made


def _object(value, name: str):
    """Our object `value` given its tracked class and `name`, its attributes adopted under it."""
    try:
        object.__setattr__(value, '__class__', _tracked_class(type(value).__mro__[0] if type(value) not in
                                                               _OBJECT_KINDS else type(value).__mro__[1]))
    except TypeError:
        UNTRACKED[type(value).__qualname__] += 1
        return value
    _name(value, name)
    for attr, item in list(vars(value).items()):
        if attr != '_jname':
            object.__setattr__(value, attr, adopt(item, f'{name}.{attr}'))
    return value


def _tuple(value: tuple, name: str) -> tuple:
    """`value` with its items adopted under `name` (the same tuple when none changes)."""
    items = [adopt(item, f'{name}[{i}]') for i, item in enumerate(value)]
    if all(a is b for a, b in zip(items, value)):
        return value
    return type(value)._make(items) if hasattr(type(value), '_make') else type(value)(items)


def _input(value) -> bool:
    """`value` is read-only input: a source record or an object of INPUTS."""
    if type(value) is dict:
        return next(iter(value), None) == 'Signature' and 'FormID' in value
    return type(value).__qualname__ in INPUTS


def adopt(value, name: str):
    """`value` adopted under `name`: a builtin container (not a subclass, counted in UNTRACKED) as a tracked copy,
    our object in place, a tuple rebuilt of adopted items, an object already adopted as it is; anything else, input
    or any value with no `name`, unchanged."""
    if name is None or _adopted(value) or _input(value):
        return value
    kind = type(value)
    if kind in _CONTAINERS or kind in _OBJECT_KINDS:
        return _object(value, name) if kind in _OBJECT_KINDS else _copied(value, kind, name)
    if isinstance(value, tuple):
        return _tuple(value, name)
    plain = next((tracked for base, tracked in _KINDS if kind is base), None)
    if plain is not None:
        return _copied(value, plain, name)
    if any(isinstance(value, base) for base, _ in _KINDS):
        UNTRACKED[kind.__qualname__] += 1
        return value
    return _object(value, name) if _ours(value) else value


def adopt_root(value, name: str):
    """`value` adopted under `name` outside any unit (setup): nothing logged."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), DEPTH))
    with recording(None):
        made = adopt(value, name)
    _FRESH.clear()
    _COPIES.clear()
    return made



@contextlib.contextmanager
def recording(ops: 'list | None'):
    """Log the changes made inside to `ops` (None: to none); a nested recording logs its own, then this one again."""
    outer = tuple(RUNNING)
    RUNNING[:] = ops, threading.get_ident()
    try:
        yield ops
    finally:
        RUNNING[:] = outer
        if outer[0] is None:
            _COPIES.clear()


def _change(target, change: str, args: list) -> None:
    """Make one logged change to `target`."""
    if change == 'list':
        getattr(target, args[0])(*args[1:])
        return
    if change in (ADD, MAX) and not isinstance(target, (dict, set)):
        _merged(target, change, *args)
        return
    made = {'attr': setattr, 'delattr': delattr, 'set': lambda t, k, v: t.__setitem__(k, v),
            'del': lambda t, k: t.__delitem__(k)}.get(change)
    if made is None:
        getattr(target, change)(*args)
    else:
        made(target, *args)


def apply(ops: list) -> None:
    """make_change() of each change in `ops`, reads skipped."""
    for name, change, frozen in ops:
        if change != READ:
            make_change(name, change, [thawed_value(v) for v in frozen])


def make_change(name: str, change: str, args: list) -> None:
    """Make a logged change on what `name` holds here (else Untracked)."""
    if name not in NAMES:
        raise Untracked(name)
    _change(NAMES[name], change, args)
