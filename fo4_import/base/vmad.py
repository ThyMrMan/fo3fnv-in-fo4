"""Fallout 4 VMAD: scripts attached to a record, and the INFO and QUST fragment blocks.

Fallout 4's VMAD is Skyrim's at version 6: the same object format 2, script
entries and property layout (`script_convert.pipeline.script_entry`). The
fragment blocks differ: bind data version 3, an INFO's block embeds the whole
script entry (its properties included) where Skyrim names only the file, and
a quest stage fragment's stage is 32 bits. Vanilla Fallout 4 INFOs and quests
with fragments attach no other scripts.

See: docs/fork/fo4_spikes.md#spike-3-vmad
"""

import struct

from script_convert.pipeline import pack_wstring, script_entry

VERSION, OBJECT_FORMAT, BIND_DATA = 6, 2, 3
#: INFO fragment flags: OnBegin, OnEnd.
INFO_BEGIN, INFO_END = 0x01, 0x02
_PROP_OBJECT, _PROP_INT, _PROP_FLOAT, _PROP_BOOL, _PROP_OBJECTS = 1, 3, 4, 5, 11


def _header(count: int = 0) -> bytes:
    """Version, object format and the count of plainly attached scripts."""
    return struct.pack('<HHH', VERSION, OBJECT_FORMAT, count)


def object_scripts(scripts: list) -> bytes:
    """VMAD attaching [(script, {property: FormID}, {property: (kind, value)})] to an object record."""
    return _header(len(scripts)) + b''.join(script_entry(*s) for s in scripts)


def info_fragments(script: str, object_props: dict = None, value_props: dict = None,
                   begin: str = 'Fragment_Begin', end: str = 'Fragment_End') -> bytes:
    """An INFO's VMAD: `script`'s OnBegin and OnEnd fragments (a None name leaves that one out)."""
    flags = (INFO_BEGIN if begin else 0) | (INFO_END if end else 0)
    out = _header() + struct.pack('<bB', BIND_DATA, flags) + script_entry(script, object_props, value_props)
    for fragment in (begin, end):
        if fragment:
            out += struct.pack('<B', 1) + pack_wstring(script) + pack_wstring(fragment)
    return out


def quest_fragments(script: str, stages: list, object_props: dict = None, value_props: dict = None,
                    aliases: list = (), scripts: list = ()) -> bytes:
    """A QUST's VMAD: plainly attached `scripts`, stage fragments, then alias scripts.

    `stages` is [(stage, log index, fragment function)] of `script` ('' when
    none); `aliases` is [(alias id, quest FormID, [(script, object props, value props)])];
    `scripts` is [(script, object props, value props)].
    """
    out = _header(len(scripts)) + b''.join(script_entry(*s) for s in scripts)
    out += struct.pack('<bH', BIND_DATA, len(stages))
    out += script_entry(script, object_props, value_props) if script else pack_wstring('')
    for stage, index, fragment in stages:
        out += struct.pack('<IIB', stage, index, 1) + pack_wstring(script) + pack_wstring(fragment)
    out += struct.pack('<h', len(aliases))
    for alias, quest, scripts in aliases:
        out += struct.pack('<HhI', 0, alias, quest) + _header(len(scripts))
        out += b''.join(script_entry(*s) for s in scripts)
    return out


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


class Unsupported(ValueError):
    """A VMAD part the packers do not write (strings, structs, alias-bound objects, other arrays)."""


def _wstring(data: bytes, pos: int) -> tuple:
    """(text, position after) of one length-prefixed string."""
    n = struct.unpack_from('<H', data, pos)[0]
    return data[pos + 2:pos + 2 + n].decode('utf-8'), pos + 2 + n


def _property(data: bytes, pos: int) -> tuple:
    """(kind, value, position after) of one property's type, status and payload."""
    kind, status = struct.unpack_from('<BB', data, pos)
    pos += 2
    if status != 1:
        raise Unsupported(f'property status {status}')
    if kind == _PROP_OBJECT:
        _, alias, fid = struct.unpack_from('<HhI', data, pos)
        if alias != -1:
            raise Unsupported('alias-bound object')
        return 'object', fid, pos + 8
    if kind in (_PROP_INT, _PROP_FLOAT, _PROP_BOOL):
        fmt, name = {_PROP_INT: ('<i', 'int'), _PROP_FLOAT: ('<f', 'float'), _PROP_BOOL: ('<B', 'bool')}[kind]
        return name, struct.unpack_from(fmt, data, pos)[0], pos + struct.calcsize(fmt)
    if kind == _PROP_OBJECTS:
        count = struct.unpack_from('<I', data, pos)[0]
        items = [struct.unpack_from('<HhI', data, pos + 4 + 8 * i) for i in range(count)]
        if any(alias != -1 for _, alias, _ in items):
            raise Unsupported('alias-bound object array')
        return 'objects', [fid for _, _, fid in items], pos + 4 + 8 * count
    raise Unsupported(f'property type {kind}')


def read_entry(data: bytes, pos: int) -> tuple:
    """((script, {property: FormID}, {property: (kind, value)}), position after) of one script entry."""
    name, pos = _wstring(data, pos)
    flags, count = struct.unpack_from('<BH', data, pos)
    pos += 3
    if flags:
        raise Unsupported(f'script flags {flags}')
    objects, values = {}, {}
    for _ in range(count):
        prop, pos = _wstring(data, pos)
        kind, value, pos = _property(data, pos)
        if kind == 'object':
            objects[prop] = value
        else:
            values[prop] = (kind, value)
    return (name, objects, values), pos
