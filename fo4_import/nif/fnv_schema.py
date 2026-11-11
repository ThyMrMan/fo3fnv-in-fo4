"""The FNV/FO3 NIF schema for fnv_reader: what to read for each struct type at one file version, compiled once per
process from pyffi's nif.xml classes (patched as the converter reads them), and the classes blocks are read into.

A block class mirrors pyffi's: same name, bases, field names and helper methods (`tree`, `get_transform`, ...),
the helpers bound to FORMAT, where a struct name gives our class. A field never read reads pyffi's default.

See: docs/fork/research/fnv_nif_reader.md#schema
"""

import functools
import types
from typing import NamedTuple

import numpy as np

from asset_convert.nif.pyffi_monkey_patch import apply_patches

apply_patches()
from pyffi.formats.nif import NifFormat
from pyffi.object_models import common
from pyffi.object_models.xml.bit_struct import BitStructBase
from pyffi.object_models.xml.enum import EnumBase
from pyffi.object_models.xml.expression import Expression
from pyffi.object_models.xml.struct_ import StructBase

#: Basic pyffi types read as one fixed-size number (by their struct format).
NUMBERS = (common.Int, common.Float, NifFormat.StringOffset)
#: pyffi basic types read as their own kind (fnv_reader._READERS), most specific first.
KINDS = ((NifFormat.Ptr, 'ptr'), (NifFormat.Ref, 'ref'), (NifFormat.string, 'string'),
         (NifFormat.bool, 'bool'), (NifFormat.ShortString, 'short'), (NifFormat.LineString, 'line'),
         (NifFormat.ByteArray, 'bytes'), (NifFormat.ByteMatrix, 'matrix'), (common.SizedString, 'sized'),
         (common.Char, 'char'))
#: The pyffi classes whose read() fnv_reader's kinds reproduce; a basic type reading any other way is refused.
READ_BY = frozenset((common.Int, common.Float, NifFormat.Ref, NifFormat.string, NifFormat.bool, NifFormat.ShortString,
                     NifFormat.LineString, NifFormat.ByteArray, NifFormat.ByteMatrix, common.SizedString,
                     common.Char, EnumBase, BitStructBase))
#: Basic types the converter's pyffi patches give their own read, by name: their fnv_reader kind.
CUSTOM = {'NumUVSets': 'uvsets'}
#: Method names of pyffi structs that read, write or walk pyffi's own storage; never borrowed.
IO_NAMES = frozenset(('read', 'write', 'get_size', 'fix_links', 'get_links', 'get_refs', 'get_strings',
                      'get_hash', '__init__', '__str__', '__repr__', 'deepcopy', 'replace_global_node',
                      'get_attribute', 'set_attribute', 'get_basic_attribute', 'set_basic_attribute',
                      'get_template_attribute', 'set_template_attribute', '_get_filtered_attribute_list',
                      '__getattr__', '__setattr__', '__getattribute__'))
#: numpy dtype of each struct format character; '?' is pyffi's one-byte bool.
DTYPES = {'f': '<f4', 'i': '<i4', 'I': '<u4', 'h': '<i2', 'H': '<u2', 'b': 'i1', 'B': 'u1', 'q': '<i8',
          'Q': '<u8', '?': '?'}
#: Python operators of pyffi's expression operators that differ.
OPERATORS = {'&&': 'and', '||': 'or'}


# ---------------------------------------------------------------------------
# Values read
# ---------------------------------------------------------------------------

class Field(NamedTuple):
    """One field of a struct plan: its name, reader kind, struct format, sub-type (struct: (pyffi class, template);
    bits: BitFields class), argument, counts and condition (callables of the struct being read, or None)."""
    name: str
    kind: str
    fmt: str
    sub: object
    arg: object
    arr1: object
    arr2: object
    cond: object


class Struct:
    """A NIF block or compound read by fnv_reader: fields are attributes; a field never read is pyffi's default."""

    def __init__(self, template=None, argument=None, parent=None):
        """An empty struct (every field at its default), as pyffi's constructor."""
        self.arg = argument

    def __getattr__(self, name):
        """pyffi's default for field `name`, kept; AttributeError for no such field."""
        value = default(type(self).PYFFI, name)
        self.__dict__[name] = value
        return value

    def get_refs(self, data=None) -> list:
        """The blocks this struct references (not points to), as pyffi's get_refs()."""
        return _linked(self, False)

    def get_links(self, data=None) -> list:
        """The blocks this struct references or points to, as pyffi's get_links()."""
        return _linked(self, True)


def _linked(s: Struct, pointers: bool) -> list:
    """The blocks struct `s` links to as pyffi's get_refs()/get_links() find them without file data: its attribute
    list unfiltered by version, the first field of each name whose condition holds; pointers too when `pointers`.

    See: docs/fork/research/fnv_nif_reader.md#compat
    """
    out, seen = [], set()
    for name, cond, kind in link_fields(type(s).PYFFI):
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

def _active(attr, key: tuple) -> bool:
    """Whether a pyffi attribute exists at file version `key` (version, user version, BS version)."""
    version, user, bsver = key
    if getattr(attr, 'is_abstract', False):
        return False
    if attr.ver1 is not None and version < attr.ver1 or attr.ver2 is not None and version > attr.ver2:
        return False
    if getattr(attr, 'userver', None) is not None and user != attr.userver:
        return False
    vercond = getattr(attr, 'vercond', None)
    header = types.SimpleNamespace(version=version, user_version=user, user_version_2=bsver)
    return vercond is None or bool(vercond.eval(header))


@functools.cache
def bit_fields(cls, key: tuple) -> type:
    """Our BitFields class of pyffi bitstruct `cls` at file version `key`."""
    body, shift = {'PYFFI': cls}, 0
    for attr in (a for a in cls._attribute_list if _active(a, key)):
        body[attr.name] = _bit_property(shift, (1 << attr.numbits) - 1)
        shift += attr.numbits
    return type(cls.__name__, (BitFields,), {**body, 'MASK': (1 << shift) - 1})


def _source(node) -> str:
    """Python source of a pyffi Expression node over struct `s`."""
    if isinstance(node, Expression):
        left, op, right = _source(node._left), node._op, _source(node._right)
        if not op:
            return left
        if op == '!':
            return f'(not {right})'
        return f'({left} {OPERATORS.get(op, op)} {right})'
    if isinstance(node, str):
        return "''" if node in ('', '""') else 's.' + node
    if isinstance(node, type):
        return f'isinstance(s, F.{node.__name__})'
    return repr(node)


@functools.cache
def _compiled(expression) -> object:
    """A callable of struct `s` evaluating pyffi `expression`; None for none."""
    if expression is None:
        return None
    return eval(f'lambda s: {_source(expression)}', {'F': FORMAT})


def kind_of(t) -> tuple:
    """(reader kind, struct format) of pyffi type `t`; TypeError for a basic type whose read is its own."""
    if issubclass(t, StructBase):
        return 'struct', ''
    if t.__name__ in CUSTOM:
        return CUSTOM[t.__name__], 'B'
    if next(c for c in t.__mro__ if 'read' in vars(c)) not in READ_BY:
        raise TypeError(f'pyffi type {t.__name__} reads its own way')
    if issubclass(t, (BitStructBase, EnumBase)):
        return 'bits' if issubclass(t, BitStructBase) else 'num', t._struct
    kind = next((k for base, k in KINDS if issubclass(t, base)), None)
    if kind:
        return kind, '?' if kind == 'bool' else 'i' if kind in ('ref', 'ptr', 'string') else ''
    if issubclass(t, NUMBERS):
        return 'num', 'f' if issubclass(t, common.Float) else t._struct
    raise TypeError(f'no reader for pyffi type {t.__name__}')


def _field(attr, key: tuple, template) -> Field:
    """The Field of pyffi attribute `attr` in a struct read with `template` at version `key`."""
    t = attr.type_ if attr.type_ is not type(None) else template
    sub_template = attr.template if attr.template is not type(None) else template
    kind, fmt = kind_of(t)
    sub = (t, sub_template) if kind == 'struct' else bit_fields(t, key) if kind == 'bits' else None
    return Field(attr.name, kind, fmt, sub, attr.arg, _compiled(attr.arr1), _compiled(attr.arr2),
                 _compiled(attr.cond))


def _link_kind(t) -> str:
    """'ref', 'ptr', 'struct' (a struct holding links), 'template' or '' (no links) for pyffi type `t`."""
    if t is type(None):
        return 'template'
    if issubclass(t, NifFormat.Ptr):
        return 'ptr'
    if issubclass(t, NifFormat.Ref):
        return 'ref'
    return 'struct' if issubclass(t, StructBase) and t._has_links else ''


@functools.cache
def link_fields(cls) -> tuple:
    """((name, condition, link kind), ...) of struct `cls`, all versions."""
    return tuple((a.name, _compiled(a.cond), _link_kind(a.type_)) for a in cls._attribute_list)


@functools.cache
def plan(cls, key: tuple, template=None) -> tuple:
    """(fields, any duplicate name) of pyffi struct `cls` at version `key`; a field after one of its name that
    has no condition is never read, so left out."""
    fields, always = [], set()
    for attr in (a for a in cls._attribute_list if _active(a, key) and a.name not in always):
        fields.append(_field(attr, key, template))
        always |= {attr.name} if attr.cond is None else set()
    return tuple(fields), len({f.name for f in fields}) < len(fields)


@functools.cache
def fixed_dtype(cls, key: tuple, template=None):
    """The numpy dtype of pyffi struct `cls` when every instance has the same layout (only numbers and such
    structs, no condition, count or duplicate); else None."""
    fields, dups = plan(cls, key, template)
    parts = []
    for f in fields:
        if dups or f.cond or f.arr1 or f.kind not in ('num', 'bool', 'struct'):
            return None
        sub = fixed_dtype(f.sub[0], key, f.sub[1]) if f.kind == 'struct' else np.dtype(DTYPES[f.fmt])
        if sub is None:
            return None
        parts.append((f.name, sub))
    return np.dtype(parts) if parts else None


# ---------------------------------------------------------------------------
# Our classes, mirroring pyffi's
# ---------------------------------------------------------------------------

class _Format:
    """NifFormat as the borrowed helpers see it: a struct class name gives ours (klass), anything else pyffi's."""

    def __getattr__(self, name):
        """Our class for pyffi struct `name`, else pyffi's attribute; kept once looked up."""
        value = getattr(NifFormat, name)
        if isinstance(value, type) and issubclass(value, StructBase):
            value = klass(value)
        setattr(self, name, value)
        return value


#: The NifFormat namespace of borrowed helpers and of converter code reading our blocks.
FORMAT = _Format()


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
            bases.append(klass(base))
            continue
        more_bases, more = _split(base)
        bases += [b for b in more_bases if b not in bases]
        helpers = {**more, **helpers}
    own = {n: _rebound(v) for n, v in vars(cls).items() if n not in IO_NAMES and n not in cls._names}
    return bases, {**helpers, **{n: v for n, v in own.items() if v is not None}}


@functools.cache
def klass(cls) -> type:
    """Our class of pyffi struct `cls`: its name, mirrored bases, helpers."""
    bases, helpers = _split(cls)
    return type(cls.__name__, tuple(bases) or (Struct,), {**helpers, 'PYFFI': cls})


# ---------------------------------------------------------------------------
# Defaults of fields never read
# ---------------------------------------------------------------------------

@functools.cache
def _pyffi_default(cls):
    """A default-constructed pyffi instance of `cls`, once per process."""
    return cls()


def ours(value):
    """pyffi value `value` as ours: a struct as our struct, a bitstruct as BitFields, an array as a list."""
    if isinstance(value, StructBase):
        out = klass(type(value))()
        out.__dict__.update({n: ours(getattr(value, n)) for n in type(value)._names})
        return out
    if isinstance(value, BitStructBase):
        return bit_fields(type(value), (0, 0, 0))(int(value))
    if isinstance(value, list):
        return [ours(v) for v in value]
    return value


def default(cls, name: str):
    """pyffi's default of field `name` of struct `cls`, as ours."""
    if name.startswith('_') or name not in cls._names:
        raise AttributeError(name)
    return ours(getattr(_pyffi_default(cls), name))
