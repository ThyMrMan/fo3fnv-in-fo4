"""Clear script properties that name a record the build never wrote.

The build hands out a FormID as soon as something might be written (a placed
creature, a package a script names, a talking activator) and resolves script
properties through it; some of those records are left out later (no FO4
base, not a radio station, a package that does not convert). Such a property
dangles: FO4Edit reports it unresolved and the game gives the script a
reference to nothing. After the plugin is written, every VMAD object property
naming this plugin's own index but no record in it is set to None (FormID 0)
in place: the VMAD keeps its size, so nothing else in the file moves.

VMADs are walked as `fo4_import.base.vmad` writes them: plain scripts on any
record, then the fragment script INFO, PACK, SCEN, TERM and PERK embed, and a
quest's stage script, alias objects and alias scripts.

See: docs/fork/fo4_pipeline.md#dangling-script-properties
"""

import struct
from pathlib import Path

from tes5_import.base.tes5_reader import FLAG_COMPRESSED, REC_HDR, walk

#: Property types (Papyrus VMAD v6): object, string, int, float, bool, variable, struct, and their arrays (+10).
OBJECT, STRING, INT, FLOAT, BOOL, VARIABLE, STRUCT = 1, 2, 3, 4, 5, 6, 7
SCALAR_SIZE = {INT: 4, FLOAT: 4, BOOL: 1}
#: Records whose VMAD carries an embedded fragment script after the plain ones.
FRAGMENTED = (b'INFO', b'PACK', b'SCEN', b'TERM', b'PERK')
#: Of those, the ones whose fragment block has no flags byte before its script (xEdit wbVMADFragmentedPERK).
UNFLAGGED = (b'TERM', b'PERK')
#: Object format -> the FormID's offset in an 8-byte object (xEdit wbScriptPropertyObject: v1 first, v2 last).
FORMID_AT = {1: 0, 2: 4}


class Unreadable(ValueError):
    """A VMAD this walker does not follow; its properties are left as they are."""


def _wstring(data: bytes, pos: int) -> int:
    """The position after one length-prefixed string."""
    return pos + 2 + struct.unpack_from('<H', data, pos)[0]


def _value(data: bytes, pos: int, kind: int, found: list) -> int:
    """The position after one property value of type `kind`, its object FormIDs' offsets added to `found`."""
    if kind == OBJECT:
        found.append(pos + 4)
        return pos + 8
    if kind == STRING:
        return _wstring(data, pos)
    if kind in SCALAR_SIZE:
        return pos + SCALAR_SIZE[kind]
    if kind == VARIABLE:
        return _value(data, pos + 1, data[pos], found)
    if kind == STRUCT:
        return _members(data, pos + 4, struct.unpack_from('<I', data, pos)[0], found)
    if kind - 10 in (OBJECT, STRING, INT, FLOAT, BOOL, VARIABLE, STRUCT):
        count, pos = struct.unpack_from('<I', data, pos)[0], pos + 4
        for _ in range(count):
            pos = _value(data, pos, kind - 10, found)
        return pos
    raise Unreadable(f'property type {kind}')


def _members(data: bytes, pos: int, count: int, found: list) -> int:
    """The position after `count` named properties (name, type, status, value)."""
    for _ in range(count):
        pos = _wstring(data, pos)
        kind = data[pos]
        pos = _value(data, pos + 2, kind, found)
    return pos


def _entry(data: bytes, pos: int, found: list) -> int:
    """The position after one script entry (name, status, properties)."""
    pos = _wstring(data, pos)
    return _members(data, pos + 3, struct.unpack_from('<H', data, pos + 1)[0], found)


def _scripts(data: bytes, pos: int, found: list) -> int:
    """The position after a VMAD header and its plainly attached scripts."""
    count = struct.unpack_from('<H', data, pos + 4)[0]
    pos += 6
    for _ in range(count):
        pos = _entry(data, pos, found)
    return pos


def _quest_tail(data: bytes, pos: int, found: list) -> None:
    """A quest's stage script (an empty name when none), its stages, then each alias's object and scripts."""
    stages, pos = struct.unpack_from('<H', data, pos + 1)[0], pos + 3
    pos = _entry(data, pos, found) if struct.unpack_from('<H', data, pos)[0] else pos + 2
    for _ in range(stages):
        pos = _wstring(data, _wstring(data, pos + 9))
    aliases, pos = struct.unpack_from('<h', data, pos)[0], pos + 2
    for _ in range(aliases):
        found.append(pos + 4)
        pos = _scripts(data, pos + 8, found)


def script_spans(sig: bytes, vmad: bytes) -> list:
    """[(script name, start, end)] of `vmad`'s (a record of type `sig`) script entries: the plain ones, then the
    fragment script of a fragmented record or a quest's stage script; aliases' scripts are not listed."""
    starts, pos = [], 6
    for _ in range(struct.unpack_from('<H', vmad, 4)[0]):
        starts.append(pos)
        pos = _entry(vmad, pos, [])
    if pos < len(vmad) and sig in FRAGMENTED:
        starts.append(pos + (1 if sig in UNFLAGGED else 2))
    elif pos + 5 <= len(vmad) and sig == b'QUST' and struct.unpack_from('<H', vmad, pos + 3)[0]:
        starts.append(pos + 3)
    return [(vmad[at + 2:_wstring(vmad, at)].decode('utf-8'), at, _entry(vmad, at, [])) for at in starts]


def object_offsets(sig: bytes, vmad: bytes) -> list:
    """Offsets in `vmad` (a record of type `sig`) of every object's FormID: each object property's and each quest
    alias's own, placed by the VMAD's object format; Unreadable for another format or an object past its end."""
    lead = FORMID_AT.get(struct.unpack_from('<h', vmad, 2)[0])
    if lead is None:
        raise Unreadable(f'object format {vmad[2:4].hex()}')
    found = []
    pos = _scripts(vmad, 0, found)
    if pos < len(vmad) and sig in FRAGMENTED:
        _entry(vmad, pos + (1 if sig in UNFLAGGED else 2), found)
    elif pos < len(vmad) and sig == b'QUST':
        _quest_tail(vmad, pos, found)
    if found and max(found) + 4 > len(vmad):
        raise Unreadable('an object past the end')
    return [at - 4 + lead for at in found]


def _vmads(raw: bytes, record) -> list:
    """(file offset of the payload, payload) of each VMAD subrecord of `record` in plugin bytes `raw`; none for a
    compressed record (land, navmesh: no scripts), whose bytes are not subrecords."""
    if record.flags & FLAG_COMPRESSED:
        return []
    out, pos, end, pending = [], record.offset + REC_HDR, record.end, None
    while pos + 6 <= end:
        tag, size = raw[pos:pos + 4], struct.unpack_from('<H', raw, pos + 4)[0]
        pos += 6
        if tag == b'XXXX':
            pending = struct.unpack_from('<I', raw, pos)[0]
            pos += size
            continue
        size, pending = (pending, None) if pending is not None else (size, None)
        if tag == b'VMAD':
            out.append((pos, raw[pos:pos + size]))
        pos += size
    return out


def clear_dangling(path: Path, own: int) -> dict:
    """Set to None, in the plugin at `path`, every script property naming plugin index `own` but no record in it;
    {'cleared': n, 'unreadable': VMADs not walked}."""
    raw = bytearray(path.read_bytes())
    written, scripted = set(), []
    for record, _ in walk(bytes(raw), bodies=()):
        written.add(record.form_id)
        scripted.append(record)
    counts = {'cleared': 0, 'unreadable': 0}
    for record in scripted:
        for start, vmad in _vmads(raw, record):
            try:
                offsets = object_offsets(record.sig, vmad)
            except (Unreadable, struct.error, IndexError):
                counts['unreadable'] += 1
                continue
            for at in offsets:
                fid = struct.unpack_from('<I', raw, start + at)[0]
                if fid >> 24 == own and fid not in written:
                    struct.pack_into('<I', raw, start + at, 0)
                    counts['cleared'] += 1
    path.write_bytes(bytes(raw))
    return counts
