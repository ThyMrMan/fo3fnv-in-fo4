"""The FNV/FO3 NIF schema for fnv_reader: what to read for each struct type at one file version, compiled from the
frozen layouts in fnv_layouts.json (tools/generators/gen_fnv_nif_layouts.py), and the classes blocks are read into.

A block class mirrors pyffi's: same name, bases, field names and helper methods (`tree`, `get_transform`, ...),
the helpers bound to FORMAT, where a struct name gives our class. A field never read reads pyffi's default.
Our classes and pyffi's accept each other's instances in isinstance(), so converter code naming NifFormat's
classes, and a pyffi object made beside our blocks, work with either reader.

See: docs/fork/research/fnv_nif_reader.md#schema
"""

import functools
import json
import types
from pathlib import Path
from typing import NamedTuple

import numpy as np

from asset_convert.nif.pyffi_monkey_patch import apply_patches

apply_patches()
from pyffi.formats.nif import NifFormat
from pyffi.object_models.xml.bit_struct import BitStructBase
from pyffi.object_models.xml.struct_ import StructBase

#: The file version, user version and BS versions fnv_reader reads; anything else is pyffi's.
VERSION, USER_VERSION, BS_VERSIONS = 0x14020007, 11, range(35)
#: Every (version, user version, BS version) fnv_reader reads.
KEYS = tuple((VERSION, USER_VERSION, b) for b in BS_VERSIONS)
#: The frozen layouts.
LAYOUTS_PATH = Path(__file__).with_name('fnv_layouts.json')
#: numpy dtype on disk of each struct format character; '?' is pyffi's one-byte bool.
DTYPES = {'f': '<f4', 'i': '<i4', 'I': '<u4', 'h': '<i2', 'H': '<u2', 'b': 'i1', 'B': 'u1', 'q': '<i8',
          'Q': '<u8', '?': '?'}
#: Struct names whose pyffi arrays are numpy views comparing by value (nif_geom_array); ours compare so too.
BY_VALUE = frozenset(('Vector3', 'Color4', 'TexCoord', 'Vector4'))


# ---------------------------------------------------------------------------
# Values read
# ---------------------------------------------------------------------------

@functools.cache
def layouts() -> dict:
    """The frozen layouts: {'structs': ..., 'basics': ..., 'bits': ...}."""
    return json.loads(LAYOUTS_PATH.read_text(encoding='utf-8'))


class Field(NamedTuple):
    """One field of a struct plan: its name, reader kind, struct format, sub-type (struct: (name, template);
    bits: BitFields class), argument, counts and condition (callables of the struct being read, or None)."""
    name: str
    kind: str
    fmt: str
    sub: object
    arg: object
    arr1: object
    arr2: object
    cond: object


class _Ours(type):
    """The metaclass of our structs: an instance of the pyffi struct a class mirrors is an instance too."""

    def __instancecheck__(cls, obj) -> bool:
        """isinstance() of `obj`: ours, or pyffi's struct of the class mirrored."""
        if type.__instancecheck__(cls, obj):
            return True
        theirs = cls.__dict__.get('PYFFI')
        return theirs is not None and type.__instancecheck__(theirs, obj)


class Struct(metaclass=_Ours):
    """A NIF block or compound read by fnv_reader: fields are attributes; a field never read is pyffi's default."""

    def __init__(self, template=None, argument=None, parent=None):
        """An empty struct of `template` (a type name), as pyffi's constructor."""
        self.__dict__['_template'] = template
        self.arg = argument

    def __getattr__(self, name):
        """pyffi's default for field `name`, kept; AttributeError for no such field."""
        value = default(type(self).PYFFI, name, self.__dict__.get('_template'))
        self.__dict__[name] = value
        return value

    def __setattr__(self, name, value):
        """Set `name`; a pyffi class set as `__class__` becomes ours."""
        if name == '__class__' and not isinstance(value, _Ours):
            value = klass(value.__name__)
        object.__setattr__(self, name, value)

    def get_refs(self, data=None) -> list:
        """The blocks this struct references (not points to), as pyffi's get_refs()."""
        return _linked(self, False)

    def get_links(self, data=None) -> list:
        """The blocks this struct references or points to, as pyffi's get_links()."""
        return _linked(self, True)


def _theirs(cls, obj) -> bool:
    """isinstance() for pyffi struct `cls`: pyffi's instance, or ours mirroring it."""
    if type.__instancecheck__(cls, obj):
        return True
    return type.__instancecheck__(Struct, obj) and issubclass(type(obj).PYFFI, cls)


type(StructBase).__instancecheck__ = _theirs


def _linked(s: Struct, pointers: bool) -> list:
    """The blocks struct `s` links to as pyffi's get_refs()/get_links() find them without file data: its attribute
    list unfiltered by version, the first field of each name whose condition holds; pointers too when `pointers`.

    See: docs/fork/research/fnv_nif_reader.md#compat
    """
    out, seen = [], set()
    for name, cond, kind in link_fields(type(s).__name__):
        if name in seen or cond is not None and not cond(s):
            continue
        seen.add(name)
        out += _blocks_in(getattr(s, name), kind, pointers) if kind else []
    return out


def _blocks_in(value, kind: str, pointers: bool) -> list:
    """The blocks a field value of link kind `kind` ('ref', 'ptr', 'struct' or 'template') holds."""
    if isinstance(value, list):
        return [b for v in value for b in _blocks_in(v, kind, pointers)]
    if value is None or kind == 'ptr' and not pointers:
        return []
    if kind in ('ref', 'ptr'):
        return [value]
    return _linked(value, pointers) if isinstance(value, Struct) else []


class BitFields:
    """A bitstruct value: `int()` gives the whole, each field is an attribute; bits no field names read as 0, as
    pyffi drops them."""
    MASK = ~0

    def __init__(self, value: int = 0):
        """The bitstruct with stored `value`, bits outside MASK dropped."""
        self.value = int(value) & self.MASK

    def __int__(self) -> int:
        """The stored integer."""
        return self.value

    __index__ = __int__

    def __and__(self, other) -> int:
        """The stored integer and `other`, as pyffi."""
        return self.value & int(other)

    def __or__(self, other) -> int:
        """The stored integer or `other`, as pyffi."""
        return self.value | int(other)


def _bit_property(shift: int, mask: int) -> property:
    """A property reading and writing bits `mask` << `shift` of BitFields.value."""
    def get(self):
        """The field's bits."""
        return (self.value >> shift) & mask

    def put(self, bits):
        """Store `bits` in the field."""
        self.value = (self.value & ~(mask << shift)) | ((int(bits) & mask) << shift)
    return property(get, put)


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@functools.cache
def _compiled(source: 'str | None') -> object:
    """A callable of struct `s` evaluating Python `source`; None for none."""
    if source is None:
        return None
    return eval(f'lambda s: {source}', {'F': FORMAT})


@functools.cache
def _exists(gate: 'str | None', key: tuple) -> bool:
    """Whether a field with version gate `gate` exists at file version `key`."""
    header = types.SimpleNamespace(version=key[0], user_version=key[1], user_version_2=key[2])
    return gate is None or bool(_compiled(gate)(header))


@functools.cache
def bit_fields(name: str, key: tuple) -> type:
    """Our BitFields class of bitstruct `name` at file version `key`."""
    body, shift = {}, 0
    for field_name, bits, gate in layouts()['bits'][name]:
        if _exists(gate, key):
            body[field_name] = _bit_property(shift, (1 << bits) - 1)
            shift += bits
    return type(name, (BitFields,), {**body, 'MASK': (1 << shift) - 1})


def kind_of(name: 'str | None') -> tuple:
    """(reader kind, struct format) of type `name`; TypeError for none, or a type read its own way."""
    if name in layouts()['structs']:
        return 'struct', ''
    kind, fmt = layouts()['basics'].get(name) or ('refused', f'no type {name}')
    if kind == 'refused':
        raise TypeError(fmt)
    return kind, fmt


def _field(row: list, key: tuple, template) -> Field:
    """The Field of layout `row` in a struct read with `template` at version `key`."""
    name, t, sub_template, arg, arr1, arr2, cond = row[:7]
    t = template if t == '*' else t
    sub_template = template if sub_template == '*' else sub_template
    kind, fmt = kind_of(t)
    sub = (t, sub_template) if kind == 'struct' else bit_fields(t, key) if kind == 'bits' else None
    return Field(name, kind, fmt, sub, arg, _compiled(arr1), _compiled(arr2), _compiled(cond))


@functools.cache
def link_fields(name: str) -> tuple:
    """((field, condition, link kind), ...) of struct `name`, all versions."""
    return tuple((row[0], _compiled(row[6]), row[8]) for row in layouts()['structs'][name])


@functools.cache
def plan(name: str, key: tuple, template=None) -> tuple:
    """(fields, any duplicate name) of struct `name` at version `key`; a field after one of its name that has no
    condition is never read, so left out."""
    fields, always = [], set()
    for row in layouts()['structs'][name]:
        if row[0] in always or not _exists(row[7], key):
            continue
        fields.append(_field(row, key, template))
        always |= {row[0]} if row[6] is None else set()
    return tuple(fields), len({f.name for f in fields}) < len(fields)


@functools.cache
def fixed_dtype(name: str, key: tuple, template=None):
    """The numpy dtype on disk of struct `name` when every instance has the same layout (only numbers and such
    structs, no condition, count or duplicate); else None."""
    fields, dups = plan(name, key, template)
    parts = []
    for f in fields:
        if dups or f.cond or f.arr1 or f.kind not in ('num', 'bool', 'struct'):
            return None
        sub = fixed_dtype(f.sub[0], key, f.sub[1]) if f.kind == 'struct' else np.dtype(DTYPES[f.fmt])
        if sub is None:
            return None
        parts.append((f.name, sub))
    return np.dtype(parts) if parts else None


@functools.cache
def wide(dtype: np.dtype) -> np.dtype:
    """`dtype` with float32 as float64, as pyffi holds floats.

    See: docs/fork/research/fnv_nif_reader.md#compat
    """
    if dtype.names is None:
        return np.dtype('<f8') if dtype == np.dtype('<f4') else dtype
    return np.dtype([(n, wide(dtype.fields[n][0])) for n in dtype.names])


# ---------------------------------------------------------------------------
# Our classes, mirroring pyffi's
# ---------------------------------------------------------------------------

class _Format:
    """NifFormat as the borrowed helpers see it: a struct class name gives ours (klass), anything else pyffi's."""

    def __getattr__(self, name):
        """Our class for struct `name`, else pyffi's attribute; kept once looked up."""
        value = klass(name) if name in layouts()['structs'] else getattr(NifFormat, name)
        setattr(self, name, value)
        return value


#: The NifFormat namespace of borrowed helpers and of converter code reading our blocks.
FORMAT = _Format()
#: Method names of pyffi structs that read, write or walk pyffi's own storage; never borrowed.
IO_NAMES = frozenset(('read', 'write', 'get_size', 'fix_links', 'get_links', 'get_refs', 'get_strings',
                      'get_hash', '__init__', '__str__', '__repr__', 'deepcopy', 'replace_global_node',
                      'get_attribute', 'set_attribute', 'get_basic_attribute', 'set_basic_attribute',
                      'get_template_attribute', 'set_template_attribute', '_get_filtered_attribute_list',
                      '__getattr__', '__setattr__', '__getattribute__'))


def _generated(cls) -> bool:
    """Whether NifFormat names `cls` (a nif.xml struct, not a mixin)."""
    return getattr(NifFormat, cls.__name__, None) is cls


def _rebound(value):
    """Function, property or class/static method `value` with its globals' NifFormat as FORMAT; None for other
    values."""
    if isinstance(value, types.FunctionType):
        out = types.FunctionType(value.__code__, {**value.__globals__, 'NifFormat': FORMAT}, value.__name__,
                                 value.__defaults__, value.__closure__)
        out.__kwdefaults__ = value.__kwdefaults__
        return out
    if isinstance(value, property):
        return property(*(_rebound(f) if f else None for f in (value.fget, value.fset, value.fdel)))
    if isinstance(value, (classmethod, staticmethod)):
        return type(value)(_rebound(value.__func__))
    return None


def _split(cls) -> tuple:
    """(our base classes, borrowed helpers) of pyffi struct `cls`: generated bases mirrored, helper mixins
    flattened into the helpers."""
    bases, helpers = [], {}
    for base in cls.__bases__:
        if base is StructBase or not issubclass(base, StructBase):
            continue
        if _generated(base):
            bases.append(klass(base.__name__))
            continue
        more_bases, more = _split(base)
        bases += [b for b in more_bases if b not in bases]
        helpers = {**more, **helpers}
    own = {n: _rebound(v) for n, v in vars(cls).items() if n not in IO_NAMES and n not in cls._names}
    return bases, {**helpers, **{n: v for n, v in own.items() if v is not None}}


@functools.cache
def klass(name: str) -> type:
    """Our class of struct `name`: its name, mirrored bases, pyffi's helpers."""
    cls = getattr(NifFormat, name)
    bases, helpers = _split(cls)
    return _Ours(name, tuple(bases) or (Struct,), {**helpers, 'PYFFI': cls})


# ---------------------------------------------------------------------------
# Rows of fixed-layout struct arrays
# ---------------------------------------------------------------------------

def columns(array: np.ndarray) -> dict:
    """{field: column} of structured `array`; a struct field's as its columns."""
    return {n: columns(array[n]) if array.dtype[n].names else array[n] for n in array.dtype.names}


def _row_property(f: Field, key: tuple) -> property:
    """A property of row field `f` reading and writing its column at the row's index."""
    name = f.name
    if f.kind != 'struct':
        return property(lambda s: s._c[name][s._i].item(),
                        lambda s, v: s._c[name].__setitem__(s._i, v))
    sub = (f.sub[0], key, f.sub[1])
    return property(lambda s: row_class(*sub)(s._c[name], s._i),
                    lambda s, v: copy_row(row_class(*sub)(s._c[name], s._i), v))


def _by_value(s, other) -> bool:
    """Whether every field of row `s` equals `other`'s, as pyffi's numpy views compare."""
    if other is None:
        return False
    try:
        return all(getattr(s, n) == getattr(other, n) for n in s._c)
    except AttributeError:
        return NotImplemented


def _row_init(s, c: dict, i: int) -> None:
    """The row `i` of columns `c`."""
    object.__setattr__(s, '_c', c)
    object.__setattr__(s, '_i', i)


@functools.cache
def row_class(name: str, key: tuple, template=None) -> type:
    """Our class of fixed-layout struct `name` (version `key`) whose instance reads and writes one row of
    columns: row_class(...)(columns, index), as pyffi's numpy-backed array views."""
    body = {'__slots__': ('_c', '_i'), '__init__': _row_init}
    body.update({f.name: _row_property(f, key) for f in plan(name, key, template)[0]})
    if name in BY_VALUE:
        body.update(__eq__=_by_value, __ne__=lambda s, o: not _by_value(s, o), __hash__=None)
    return _Ours(name, (klass(name),), body)


def copy_row(row, value) -> None:
    """Every field of `value` into `row`."""
    for name in row._c:
        setattr(row, name, getattr(value, name))


# ---------------------------------------------------------------------------
# Defaults of fields never read
# ---------------------------------------------------------------------------

@functools.cache
def _pyffi_default(cls, template: 'str | None'):
    """A default pyffi `cls` of `template` (a type name), once per process."""
    return cls(template=getattr(NifFormat, template) if template else None)


def ours(value):
    """pyffi value `value` as ours: a struct as our struct, a bitstruct as BitFields, an array as a list."""
    if type.__instancecheck__(Struct, value):
        return value
    if isinstance(value, StructBase):
        out = klass(type(value).__name__)()
        out.__dict__.update({n: ours(getattr(value, n)) for n in type(value)._names})
        return out
    if isinstance(value, BitStructBase):
        return bit_fields(type(value).__name__, KEYS[-1])(int(value))
    if isinstance(value, list):
        return [ours(v) for v in value]
    return value


def default(cls, name: str, template: 'str | None' = None):
    """pyffi's default of field `name` of pyffi `cls` of `template`, as ours."""
    if name.startswith('_') or name not in cls._names:
        raise AttributeError(f"'{cls.__name__}' object has no attribute '{name}'")
    return ours(getattr(_pyffi_default(cls, template), name))
