"""Write fo4_import/nif/fnv_layouts.json: every nif.xml struct, bitstruct and basic type as the converter's patched
pyffi declares them, frozen for fo4_import.nif.fnv_schema, so reading an FNV/FO3 NIF needs no pyffi metadata.

    py -3.14 tools/generators/gen_fnv_nif_layouts.py

Rerun after changing a pyffi patch that alters a layout; tests/test_fo4_fnv_reader.py fails while the file is stale.

See: docs/fork/research/fnv_nif_reader.md#schema
"""

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fo4_import.nif.fnv_schema import KEYS, LAYOUTS_PATH
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
#: Python operators of pyffi's expression operators that differ.
OPERATORS = {'&&': 'and', '||': 'or'}


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

def source(node) -> str:
    """Python source of a pyffi Expression node over `s`; a type name tests `s` against fnv_schema's class `F.X`."""
    if isinstance(node, Expression):
        left, op, right = source(node._left), node._op, source(node._right)
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


def optional(node) -> 'str | None':
    """source() of `node`; None for none."""
    return None if node is None else source(node)


def gate(attr) -> 'str | None':
    """Python source over header `s` (version, user_version, user_version_2) of whether `attr` exists; None: always."""
    if getattr(attr, 'is_abstract', False):
        return 'False'
    parts = [f's.version >= {attr.ver1:#x}' if attr.ver1 is not None else '',
             f's.version <= {attr.ver2:#x}' if attr.ver2 is not None else '',
             f's.user_version == {attr.userver}' if getattr(attr, 'userver', None) is not None else '',
             optional(getattr(attr, 'vercond', None)) or '']
    return ' and '.join(p for p in parts if p) or None


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

def basic(t) -> list:
    """[reader kind, struct format] of basic pyffi type `t`; ['refused', why] for one whose read is its own."""
    if t.__name__ in CUSTOM:
        return [CUSTOM[t.__name__], 'B']
    if next(c for c in t.__mro__ if 'read' in vars(c)) not in READ_BY:
        return ['refused', f'pyffi type {t.__name__} reads its own way']
    if issubclass(t, (BitStructBase, EnumBase)):
        return ['bits' if issubclass(t, BitStructBase) else 'num', t._struct]
    kind = next((k for base, k in KINDS if issubclass(t, base)), None)
    if kind:
        return [kind, '?' if kind == 'bool' else 'i' if kind in ('ref', 'ptr', 'string') else '']
    if issubclass(t, NUMBERS):
        return ['num', 'f' if issubclass(t, common.Float) else t._struct]
    return ['refused', f'no reader for pyffi type {t.__name__}']


def link_kind(t) -> str:
    """'ref', 'ptr', 'struct' (a struct holding links), 'template' or '' (no links) of pyffi field type `t`."""
    if t is type(None):
        return 'template'
    if issubclass(t, NifFormat.Ptr):
        return 'ptr'
    if issubclass(t, NifFormat.Ref):
        return 'ref'
    return 'struct' if issubclass(t, StructBase) and t._has_links else ''


def name_of(t) -> 'str | None':
    """The name of type `t`; '*' for the template placeholder, None for none."""
    return '*' if t is type(None) else None if t is None else t.__name__


def generated(t) -> bool:
    """Whether NifFormat names struct `t` (a nif.xml struct, not a helper mixin)."""
    return isinstance(t, type) and issubclass(t, StructBase) and getattr(NifFormat, t.__name__, None) is t


def exists(gate_source: 'str | None') -> bool:
    """Whether a field with gate `gate_source` exists in any file version fnv_reader reads (KEYS)."""
    if gate_source is None:
        return True
    test = eval(f'lambda s: {gate_source}')
    return any(test(types.SimpleNamespace(version=v, user_version=u, user_version_2=b)) for v, u, b in KEYS)


def struct_layout(cls, used: set) -> list:
    """[[name, type, template, arg, arr1, arr2, cond, gate, link kind], ...] of struct `cls`'s attributes as pyffi
    lists them, less exact repeats and fields no KEYS version has whose name holds no link (pyffi's get_refs
    walks those names at every version); the non-struct types they use are added to `used`."""
    out, linked = [], {a.name for a in cls._attribute_list if link_kind(a.type_)}
    for a in cls._attribute_list:
        row = [a.name, name_of(a.type_), name_of(a.template), a.arg, optional(a.arr1), optional(a.arr2),
               optional(a.cond), gate(a), link_kind(a.type_)]
        if row in out or not (a.name in linked or exists(row[7])):
            continue
        used |= {t for t in (a.type_, a.template) if isinstance(t, type) and t is not type(None)
                 and not issubclass(t, StructBase)}
        out.append(row)
    return out


def layouts() -> dict:
    """{'structs': {name: layout}, 'basics': {name: [kind, format]}, 'bits': {name: [[field, bits, gate], ...]}}."""
    structs, used = {}, set()
    for name in sorted(dir(NifFormat)):
        t = getattr(NifFormat, name)
        if generated(t):
            structs[name] = struct_layout(t, used)
    basics = {t.__name__: basic(t) for t in sorted(used, key=lambda t: t.__name__)}
    bits = {t.__name__: [[a.name, a.numbits, gate(a)] for a in t._attribute_list]
            for t in sorted(used, key=lambda t: t.__name__) if issubclass(t, BitStructBase)}
    return {'structs': structs, 'basics': basics, 'bits': bits}


def text() -> str:
    """The JSON text of layouts(), one struct per line."""
    data = layouts()
    parts = []
    for section, table in data.items():
        rows = ',\n'.join(f'  {json.dumps(k)}: {json.dumps(v)}' for k, v in table.items())
        parts.append(f'{json.dumps(section)}: {{\n{rows}\n}}')
    return '{\n' + ',\n'.join(parts) + '\n}\n'


def main() -> None:
    """Write fnv_schema's layouts file."""
    LAYOUTS_PATH.write_text(text(), encoding='utf-8', newline='\n')
    print(f'wrote {LAYOUTS_PATH} ({LAYOUTS_PATH.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
